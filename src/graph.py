"""Graph wiring — W1.2 skeleton, W1.4's real score node, W1.5's refine loop + act node.

Flow:
    START -> profile -> planner -> (fan out on dispatch) -> module / event / project
           -> score -> refine_gate -> planner (loop, capped) or act -> END

`profile` is the real node from src.agents.profile (W3.1-W3.3), wired in once those
landed. It reads the committed fixture transcript/resume, not a per-request upload -
see that module's docstring for why accepting a student's own transcript needs a
frozen-contract change that is out of scope here.

`score` is real (see `_score_node` below). It calls Bedrock once per scoring pass -
a single batched call judging every candidate, not one call each - for the two
model-produced components (gap_coverage, role_fit), then calls scoring.compose_score
(pure, W1.4) for the rest. Writes `ranked`, not `candidates`: see the RunState
docstring in state.py for why the two fields are split.

`act` is real too (W1.5). It proposes one PendingAction per ranked candidate, then
calls `interrupt()` and pauses the whole graph until a human resumes it with which
ids to approve. This needs a checkpointer to survive the pause, so `build_graph()`
compiles with `InMemorySaver`. IMPORTANT for W4.4 (Aaron's "approve" endpoint):
InMemorySaver only survives within one process's memory. It is fine for local dev and
for a single long-lived process, but a resume arriving as a separate serverless
invocation (a fresh Lambda/AgentCore container) will not find the paused state. That
persistence problem belongs to W1.6 (S3 state snapshot) or a follow-up - not solved
here, flagged so W4.4 does not build the approve endpoint assuming resume "just works"
across invocations.

The checkpointer's serializer refuses to silently deserialize our own Pydantic/enum
types by default in a future langgraph-checkpoint version (currently just a warning:
"Deserializing unregistered type ... This will be blocked in a future version").
`_CHECKPOINT_MSGPACK_ALLOWLIST` below allow-lists every class actually defined in
state.py, built by introspecting the module rather than hand-listing types, so it
can't go stale as the frozen contract gets amended.
"""

from __future__ import annotations

import inspect
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from src import state as _state_module
from src.agents.event import event_node
from src.agents.module import module_node
from src.agents.planner import planner_node
from src.agents.profile import profile_node
from src.agents.project import project_node
from src.config import (
    AWS_REGION,
    MAX_CANDIDATES_SCORED,
    MAX_REFINE_ITERATIONS,
    MODEL_HAIKU,
    NEVER_AUTOMATED_ACTIONS,
    SCORE_THRESHOLD,
    SCORE_TIMEOUT_SECONDS,
    TOOL_RETRIES,
    TOOL_TIMEOUT_SECONDS,
)
from src.metrics import ModelCallStats, apply_model_call, token_usage
from src.scoring import compose_score
from src.state import (
    Candidate,
    PendingAction,
    Readiness,
    RunMetrics,
    RunState,
    StudentProfile,
    TraceEvent,
    TraceKind,
)

_CHECKPOINT_MSGPACK_ALLOWLIST = [
    obj
    for _, obj in inspect.getmembers(_state_module, inspect.isclass)
    if obj.__module__ == _state_module.__name__
]

# Maps the display names the planner writes into `dispatch` (config.AGENT_NAMES) onto
# the graph node keys those agents actually run as.
NODE_BY_AGENT_NAME = {
    "Module Agent": "module",
    "Event Agent": "event",
    "Project Agent": "project",
}


def _fan_out(state: RunState) -> list[str]:
    dispatch = state.get("dispatch", [])
    nodes = [NODE_BY_AGENT_NAME[name] for name in dispatch if name in NODE_BY_AGENT_NAME]
    return nodes or ["score"]  # nothing dispatched: skip straight to scoring


_SCORE_TOOL_NAME = "score_candidates"

_SCORE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "gap_coverage": {"type": "number", "minimum": 0, "maximum": 1},
                    "role_fit": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                    "closed_gaps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The exact priority-gap labels from the list above that "
                        "this candidate genuinely closes. Copy the labels verbatim; omit any "
                        "the candidate only touches superficially. May be empty.",
                    },
                },
                "required": ["candidate_id", "gap_coverage", "role_fit", "rationale"],
            },
            "description": "One judgment per candidate, in the same order given.",
        },
    },
    "required": ["judgments"],
}

# boto's own retry machinery is disabled (max_attempts=1); the retry loop in
# _call_score_bedrock is explicit so a final failure is observable and can write its
# own TraceEvent, matching the pattern in agents/planner.py.
_SCORE_BOTO_CONFIG = BotoConfig(
    connect_timeout=TOOL_TIMEOUT_SECONDS,
    read_timeout=SCORE_TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)

_score_client: Any = None


def _score_bedrock() -> Any:
    global _score_client
    if _score_client is None:
        _score_client = boto3.client(
            "bedrock-runtime", region_name=AWS_REGION, config=_SCORE_BOTO_CONFIG
        )
    return _score_client


class _Judgment(BaseModel):
    candidate_id: str
    gap_coverage: float = Field(ge=0.0, le=1.0)
    role_fit: float = Field(ge=0.0, le=1.0)
    rationale: str
    closed_gaps: list[str] = Field(default_factory=list)


class _ScoreDecision(BaseModel):
    judgments: list[_Judgment]


def _build_score_prompt(
    candidates: list[Candidate], profile: StudentProfile, readiness: Readiness
) -> str:
    gap_lines = "\n".join(
        f"  {gap.priority}. {gap.label} ({gap.dimension}): "
        f"current {gap.current:.2f}, target {gap.target:.2f}"
        for gap in readiness.gaps
    )
    candidate_lines = "\n".join(
        f"  {c.id} [{c.kind}] {c.title} - claims to close: {', '.join(c.closes_gaps) or 'unspecified'}\n"
        f"    {c.description[:200]}"
        for c in candidates
    )
    return (
        f"Student targeting {profile.target_role}.\n"
        f"Ranked priority gaps (1 is highest):\n{gap_lines}\n\n"
        f"Candidates to judge:\n{candidate_lines}\n\n"
        "For every candidate above, give gap_coverage (0-1: how much it would actually "
        "close the priority gaps above, not just what it claims), role_fit (0-1: how "
        "well it fits the target role), a one-sentence rationale, and closed_gaps (the "
        "priority-gap labels it genuinely closes, copied verbatim from the list above). "
        "Call score_candidates with exactly one judgment per candidate id listed above."
    )


def _call_score_bedrock(prompt: str) -> tuple[_ScoreDecision, ModelCallStats]:
    """Returns the decision plus this call's metrics contribution (tokens across every
    attempt, and whether the structured output validated).
    """
    stats = ModelCallStats()
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = _score_bedrock().converse(
                modelId=MODEL_HAIKU,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": _SCORE_TOOL_NAME,
                                "description": "Record gap_coverage and role_fit for every "
                                "candidate given.",
                                "inputSchema": {"json": _SCORE_TOOL_SCHEMA},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": _SCORE_TOOL_NAME}},
                },
                inferenceConfig={"temperature": 0, "maxTokens": 4000},
            )
            input_tokens, output_tokens = token_usage(response)
            stats.input_tokens += input_tokens
            stats.output_tokens += output_tokens
            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    decision = _ScoreDecision.model_validate(block["toolUse"]["input"])
                    stats.schema_validations_passed += 1
                    return decision, stats
            raise ValueError("model did not call the score_candidates tool")
        except ValidationError as exc:
            stats.schema_validations_failed += 1
            last_error = exc
        except (ClientError, BotoCoreError, ValueError, KeyError) as exc:
            last_error = exc
    raise RuntimeError(f"score Bedrock call failed after retry: {last_error}") from last_error


def _score_node(state: RunState) -> dict:
    """Real W1.4 score node: one batched Bedrock call for gap_coverage/role_fit, then
    scoring.compose_score (pure) for time_cost, redundancy_penalty and the weighted
    total. Writes `ranked`, fully replacing it - never `candidates`.

    The model also returns `closed_gaps` per candidate - the gap labels it genuinely
    closes - which is written onto the candidate. scoring.redundancy_penalty then
    matches those gaps' Dimensions against the Dimensions the student already holds
    evidence in (StudentProfile.evidence). Until W3.2/W3.3 populate `evidence` the
    penalty evaluates to 0, but the path is live and the matching is dimension-based,
    so it does not depend on resume text and gap labels sharing a vocabulary.

    A candidate the student has already logged an Outcome against (accepted,
    rejected or withdrew - whichever) is dropped here, deterministically, before
    scoring even runs: re-surfacing something already decided isn't a fresh
    recommendation, and a sub-agent re-running on the next refine iteration has no
    way to know not to hand it back. This is also what guarantees a re-plan changes
    `ranked` rather than depending on the planner's dispatch choice alone - see
    planner.py's docstring for how the planner separately reads outcomes for the
    dispatch decision itself.
    """
    decided_ids = {outcome.candidate_id for outcome in state.get("outcomes", [])}
    all_candidates = state.get("candidates", [])
    already_decided = sum(1 for c in all_candidates if c.id in decided_ids)
    candidates = [c for c in all_candidates if c.id not in decided_ids][:MAX_CANDIDATES_SCORED]
    profile = state["profile"]
    readiness = state["readiness"]

    if not candidates:
        return {
            "ranked": [],
            "trace": [
                TraceEvent(
                    kind=TraceKind.DECIDED, agent="Career Agent", message="No candidates to score"
                )
            ],
        }

    gap_dimensions = {gap.label: gap.dimension for gap in readiness.gaps}
    metrics = state.get("metrics") or RunMetrics()

    trace: list[TraceEvent] = []
    try:
        decision, stats = _call_score_bedrock(_build_score_prompt(candidates, profile, readiness))
        judgments = {j.candidate_id: j for j in decision.judgments}
    except RuntimeError as exc:
        judgments = {}
        stats = ModelCallStats()  # a failed call recorded no tokens or validations
        trace.append(
            TraceEvent(
                kind=TraceKind.DECIDED,
                agent="Career Agent",
                message="Scoring fell back to neutral defaults for every candidate",
                detail=str(exc),
            )
        )

    ranked: list[Candidate] = []
    for candidate in candidates:
        judgment = judgments.get(candidate.id)
        if judgment is None:
            # No real model judgment for this candidate - do not rank it on a
            # fabricated 0.5/0.5 guess. A candidate presented as a scored,
            # ranked recommendation must trace to an actual model judgment.
            continue
        # Keep only labels that are real priority gaps - the model occasionally
        # paraphrases or invents one, and a bad label would silently distort the
        # redundancy penalty.
        closed_gaps = [label for label in judgment.closed_gaps if label in gap_dimensions]
        scored = candidate.model_copy(update={"closes_gaps": closed_gaps})
        scores = compose_score(
            scored, profile, judgment.gap_coverage, judgment.role_fit, gap_dimensions,
            judgment.rationale,
        )
        if scores.total >= SCORE_THRESHOLD:
            ranked.append(scored.model_copy(update={"scores": scores}))

    ranked.sort(key=lambda c: c.scores.total, reverse=True)
    if already_decided:
        trace.append(
            TraceEvent(
                kind=TraceKind.CHANGED,
                agent="Career Agent",
                message=f"Excluded {already_decided} candidate(s) the student already logged "
                "an outcome on",
                detail="A candidate the student has decided on - accepted, rejected or "
                "withdrew - is not offered again as a fresh recommendation.",
            )
        )
    trace.append(
        TraceEvent(
            kind=TraceKind.DECIDED,
            agent="Career Agent",
            message=f"Scored {len(candidates)} candidates, {len(ranked)} above threshold "
            f"{SCORE_THRESHOLD}",
        )
    )
    return {"ranked": ranked, "trace": trace, "metrics": apply_model_call(metrics, stats)}


def _refine_gate(state: RunState) -> dict:
    """Increments the refine-loop counter every time it is reached, cap or no cap."""
    iteration = state.get("iteration", 0) + 1
    return {
        "iteration": iteration,
        "trace": [
            TraceEvent(
                kind=TraceKind.DECIDED,
                agent="Career Agent",
                message=f"Refine check: iteration {iteration}/{MAX_REFINE_ITERATIONS}",
            )
        ],
    }


def _should_refine(state: RunState) -> str:
    """Loops back to the planner only when a logged outcome asked for a re-plan and the
    hard cap from config has not been reached. The cap is checked unconditionally — it
    ignores whatever a model might otherwise decide, per the hard rule in CLAUDE.md.
    """
    has_new_outcome = bool(state.get("outcomes"))
    under_cap = state.get("iteration", 0) < MAX_REFINE_ITERATIONS
    return "planner" if (has_new_outcome and under_cap) else "act"


def _act_node(state: RunState) -> dict:
    """Approval interrupt before acting — W1.5.

    Proposes one PendingAction per ranked candidate, then calls interrupt() and pauses
    the whole graph for a human decision. On resume, executes only what was actually
    approved. NEVER_AUTOMATED_ACTIONS is enforced here in code, not just documented:
    nothing a resume payload claims can force through a submit_application-type action,
    so the hard rule in CLAUDE.md holds even against a malformed or malicious resume.
    """
    ranked = state.get("ranked", [])
    proposed = [
        PendingAction(
            id=f"action:{candidate.id}",
            action_type="add_to_roadmap",
            label=f"Add '{candidate.title}' to the roadmap",
            candidate_id=candidate.id,
            auto_approvable=True,
        )
        for candidate in ranked
    ]

    if not proposed:
        return {
            "pending": [],
            "trace": [
                TraceEvent(
                    kind=TraceKind.ACTION,
                    agent="Career Agent",
                    message="No ranked candidates to propose actions for",
                )
            ],
        }

    decision = interrupt(
        {
            "kind": "approve_actions",
            "actions": [action.model_dump(mode="json") for action in proposed],
        }
    )
    requested_ids = set(decision.get("approved", [])) if isinstance(decision, dict) else set()

    by_id = {action.id: action for action in proposed}
    approved = [
        action_id
        for action_id in requested_ids
        if action_id in by_id and by_id[action_id].action_type not in NEVER_AUTOMATED_ACTIONS
    ]

    return {
        "pending": proposed,
        "approved": approved,
        "trace": [
            TraceEvent(
                kind=TraceKind.ACTION,
                agent="Career Agent",
                message=f"Approved {len(approved)} of {len(proposed)} proposed actions",
            )
        ],
    }


def build_graph():
    builder = StateGraph(RunState)

    builder.add_node("profile", profile_node)
    builder.add_node("planner", planner_node)
    builder.add_node("module", module_node)
    builder.add_node("event", event_node)
    builder.add_node("project", project_node)
    builder.add_node("score", _score_node)
    builder.add_node("refine_gate", _refine_gate)
    builder.add_node("act", _act_node)

    builder.add_edge(START, "profile")
    builder.add_edge("profile", "planner")

    builder.add_conditional_edges(
        "planner", _fan_out, ["module", "event", "project", "score"]
    )

    # Fan-in: whichever of module/event/project actually ran, all converge on score.
    builder.add_edge("module", "score")
    builder.add_edge("event", "score")
    builder.add_edge("project", "score")

    builder.add_edge("score", "refine_gate")
    builder.add_conditional_edges("refine_gate", _should_refine, ["planner", "act"])
    builder.add_edge("act", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_MSGPACK_ALLOWLIST)
    return builder.compile(checkpointer=InMemorySaver(serde=serde))


graph = build_graph()
