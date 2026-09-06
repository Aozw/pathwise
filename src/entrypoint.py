"""AgentCore Runtime entrypoint — W4.1 stub, W4.4 real wiring.

Routes three actions onto one LangGraph thread per run_id, keyed by
`payload["action"]`:

    onboard  - first call for a new run. Starts the graph from a fresh RunState.
    run      - a later call carrying a logged Outcome, which the graph's own
               refine loop (see graph._should_refine) turns into a re-plan.
    approve  - resumes the interrupt() raised by graph._act_node with the ids
               the student approved.

`run_id` doubles as the LangGraph `thread_id` and the S3 snapshot key. The
client must echo back the `run_id` it was given by the "onboard" response on
every later call, or each call starts an unrelated fresh run.

Interrupt/resume only actually works within one warm process: see graph.py's
module docstring for why. src.snapshot gives a coarse RunState snapshot across
process restarts, which recovers "onboard" and "run" (state.get() from S3 is a
constructor for a valid RunState value); it does NOT recover an in-flight
interrupt, so an "approve" call arriving at a container that was never the one
holding that interrupt will fail. Acceptable for this deploy's scale (one
warm container for the whole demo); flagged rather than hidden.

Run locally (as a module, from the repo root - the src.* imports below need it on
sys.path, which `python src/entrypoint.py` does not do):
    python -m src.entrypoint
    curl -X POST localhost:8080/invocations \
        -d '{"action": "onboard"}'
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

# AgentCore's deploy tooling invokes this file directly ("python src/entrypoint.py",
# per .bedrock_agentcore.yaml's entrypoint field and the starter toolkit's
# build_entrypoint_array), which puts src/ itself on sys.path rather than its parent -
# the `from src...` imports below would raise ModuleNotFoundError without this. Running
# `python -m src.entrypoint` from the repo root doesn't need it, but this makes both
# invocation styles work rather than relying on whichever one the deploy path picks.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bedrock_agentcore import BedrockAgentCoreApp  # noqa: E402
from langgraph.types import Command, Interrupt  # noqa: E402

from src.config import ROLE_DIMENSION_WEIGHTS  # noqa: E402
from src.graph import graph  # noqa: E402
from src.metrics import write_run_metrics  # noqa: E402
from src.snapshot import load_snapshot, save_snapshot  # noqa: E402
from src.state import (  # noqa: E402
    Candidate,
    DimensionScore,
    Gap,
    Outcome,
    Readiness,
    RunState,
    StudentProfile,
    TraceEvent,
    new_run_state,
)

app = BedrockAgentCoreApp()

_ACTIONS = ("onboard", "run", "approve")


def _dimension_score_json(d: DimensionScore, weights: dict[str, float]) -> dict:
    return {
        "dimension": d.dimension.value,
        "score": d.score,
        "rationale": d.rationale,
        "weight": weights.get(d.dimension.value, 0.0),
    }


def _gap_json(g: Gap) -> dict:
    return {
        "dimension": g.dimension.value,
        "label": g.label,
        "priority": g.priority,
        "current": g.current,
        "target": g.target,
    }


def _readiness_json(readiness: Readiness | None, target_role: str) -> dict | None:
    if readiness is None:
        return None
    weights = ROLE_DIMENSION_WEIGHTS.get(target_role, {})
    return {
        "dimensions": [_dimension_score_json(d, weights) for d in readiness.dimensions],
        "gaps": [_gap_json(g) for g in readiness.gaps],
    }


def _profile_json(profile: StudentProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "name": profile.name,
        "year": profile.year,
        "major": profile.major,
        "target_role": profile.target_role,
        "units_completed": profile.units_completed,
        "units_required": profile.units_required,
    }


def _candidate_json(c: Candidate) -> dict:
    return {
        "id": c.id,
        "kind": c.kind.value,
        "source": c.source.value,
        "title": c.title,
        "description": c.description,
        "url": c.url,
        "deadline": c.deadline.isoformat() if c.deadline else None,
        "closes_gaps": c.closes_gaps,
        "score": c.scores.total if c.scores else None,
        "score_breakdown": (
            {
                "gap_coverage": c.scores.gap_coverage,
                "role_fit": c.scores.role_fit,
                "time_cost": c.scores.time_cost,
                "redundancy_penalty": c.scores.redundancy_penalty,
                "rationale": c.scores.rationale,
            }
            if c.scores
            else None
        ),
    }


def _trace_json(events: list[TraceEvent]) -> list[dict]:
    return [
        {
            "kind": e.kind.value,
            "agent": e.agent,
            "message": e.message,
            "detail": e.detail,
            "at": e.at.isoformat(),
        }
        for e in events
    ]


def _pending_from_interrupt(interrupts: tuple[Interrupt, ...] | None) -> list[dict]:
    """The act node's interrupt() payload is {"kind": "approve_actions", "actions": [...]}.

    An empty list (no interrupts, or the act node found nothing to propose) means
    there is nothing left for the student to approve on this run.
    """
    if not interrupts:
        return []
    payload = interrupts[0].value
    return payload.get("actions", []) if isinstance(payload, dict) else []


def _serialize(result: dict[str, Any], run_id: str) -> dict:
    profile = result.get("profile")
    return {
        "status": "ok",
        "run_id": run_id,
        "awaiting_approval": bool(result.get("__interrupt__")),
        "profile": _profile_json(profile),
        "readiness": _readiness_json(
            result.get("readiness"), profile.target_role if profile else ""
        ),
        "ranked": [_candidate_json(c) for c in result.get("ranked", [])],
        "pending": _pending_from_interrupt(result.get("__interrupt__")),
        "approved": result.get("approved", []),
        "trace": _trace_json(result.get("trace", [])),
    }


def _recover_after_restart(run_id: str) -> tuple[RunState, TraceEvent | None]:
    """Rebuilds a starting RunState when this thread_id has no live in-process
    checkpoint - either it is genuinely new, or a container restart dropped the
    InMemorySaver's memory. `candidates`/`trace` use operator.add: feeding their
    accumulated values back in as fresh graph input would make the reducer add
    them a second time on top of whatever the (now-empty) checkpoint holds, so
    they deliberately start over here rather than replay the S3 snapshot's copy.
    Every other field survives a restart via the snapshot; that gap is the actual
    cost of not having a real S3-backed checkpointer (see src/snapshot.py).
    """
    snapshot_state, fallback_event = load_snapshot(run_id)
    state = new_run_state(run_id)
    if snapshot_state:
        state = {**state, **snapshot_state, "candidates": [], "trace": []}
    return state, fallback_event


def _build_run_input(
    action: str, run_id: str, payload: dict, config: dict
) -> tuple[RunState | dict | Command, list[TraceEvent]]:
    """Resolves what to feed graph.invoke() for a given action.

    "approve" resumes the paused interrupt directly via Command(resume=...) - the
    one case that must NOT go through a plain dict, since that would start a new
    run from START rather than continuing the paused act node.

    "onboard" and "run" both check the live checkpoint first (graph.get_state):
    on the common warm path, the checkpoint already holds everything, so the
    input is either empty ("onboard", nothing new to add) or just the freshly
    logged outcome ("run") - never the reducer fields, to avoid the
    double-counting explained in _recover_after_restart. Only a genuinely cold
    thread_id falls back to the S3 snapshot / a brand new RunState.
    """
    if action == "approve":
        approved_ids = payload.get("approved", [])
        return Command(resume={"approved": approved_ids}), []

    existing = graph.get_state(config).values
    fallback_trace: list[TraceEvent] = []
    if existing:
        state: RunState | dict = {}
        prior_outcomes = existing.get("outcomes", [])
    else:
        state, fallback_event = _recover_after_restart(run_id)
        if fallback_event:
            fallback_trace.append(fallback_event)
        prior_outcomes = state.get("outcomes", [])

    if action == "run":
        outcome_payload = payload.get("outcome") or {}
        outcome = Outcome(
            candidate_id=outcome_payload.get("candidate_id", ""),
            result=outcome_payload.get("result", "not_shortlisted"),
        )
        state = {**state, "outcomes": [*prior_outcomes, outcome]}

    return state, fallback_trace


@app.entrypoint
def invoke(payload: dict) -> dict:
    action = payload.get("action")
    if action not in _ACTIONS:
        return {"status": "error", "message": f"action must be one of {_ACTIONS}, got {action!r}"}

    run_id = payload.get("run_id") or str(uuid.uuid4())
    config = {"configurable": {"thread_id": run_id}}

    graph_input, fallback_trace = _build_run_input(action, run_id, payload, config)

    try:
        result = graph.invoke(graph_input, config=config)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client, not a crash
        return {"status": "error", "run_id": run_id, "message": str(exc)}

    if fallback_trace:
        result["trace"] = [*result.get("trace", []), *fallback_trace]

    # save_snapshot expects a plain RunState - strip __interrupt__ (a tuple of
    # langgraph Interrupt objects, not one of state.py's registered types) so an
    # interrupted run, the common case for "onboard", doesn't fail to serialize.
    snapshot_state = {k: v for k, v in result.items() if not k.startswith("__")}
    save_fallback = save_snapshot(snapshot_state)
    if save_fallback is not None:
        result["trace"] = [*result.get("trace", []), save_fallback]

    # Overwritten on every call for this run_id, so it always reflects the metrics
    # accumulated so far - the same "write at run end" pattern as save_snapshot above,
    # since a demo run is a sequence of onboard/run/approve calls, not one call.
    write_run_metrics(snapshot_state)

    return _serialize(result, run_id)


if __name__ == "__main__":
    app.run()
