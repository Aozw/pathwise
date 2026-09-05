"""Planner node — W1.3.

The only node where a model determines control flow; everything downstream is
deterministic on purpose, so rankings stay reproducible and auditable. One Bedrock
call, forced into a structured `plan` tool schema, decides which sub-agents to
dispatch this run given the student's ranked priority gaps. Conditional fan-out in
graph.py reads `dispatch` directly. Every skip gets its own reason and its own
TraceEvent — a skip is a decision, not a silence.

Failure handling follows the CLAUDE.md hard rule: one retry, then a fallback that
dispatches every agent (the safe default — nobody is wrongly excluded) and writes a
TraceEvent recording that the fallback fired. There is no JSON fixture for this one;
"dispatch everyone" plays that role, since it is the deterministic safe answer for a
node whose only job is choosing *which* real work happens next.
"""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ValidationError

from src.config import AGENT_NAMES, AWS_REGION, MODEL_HAIKU, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS
from src.metrics import ModelCallStats, apply_model_call, token_usage
from src.state import Readiness, RunMetrics, RunState, StudentProfile, TraceEvent, TraceKind

_TOOL_NAME = "plan"

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "dispatch": {
            "type": "array",
            "items": {"type": "string", "enum": AGENT_NAMES},
            "description": "Agents to run this turn.",
        },
        "skip": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": AGENT_NAMES},
                    "reason": {"type": "string"},
                },
                "required": ["agent", "reason"],
            },
            "description": "Agents deliberately not run this turn, each with a concrete reason.",
        },
        "rationale": {
            "type": "string",
            "description": "One or two sentences on why this dispatch set closes the top gap.",
        },
    },
    "required": ["dispatch", "skip", "rationale"],
}

# boto's own retry machinery is disabled (max_attempts=1); the retry loop below is
# explicit so a final failure is observable and can write its own TraceEvent.
_BOTO_CONFIG = BotoConfig(
    connect_timeout=TOOL_TIMEOUT_SECONDS,
    read_timeout=TOOL_TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)

_client: Any = None


def _bedrock() -> Any:
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=_BOTO_CONFIG)
    return _client


class SkipDecision(BaseModel):
    agent: str
    reason: str


class PlannerDecision(BaseModel):
    dispatch: list[str]
    skip: list[SkipDecision]
    rationale: str


def _build_prompt(profile: StudentProfile, readiness: Readiness) -> str:
    gap_lines = "\n".join(
        f"  {gap.priority}. {gap.label} ({gap.dimension}): "
        f"current {gap.current:.2f}, target {gap.target:.2f}, size {gap.size:.2f}"
        for gap in readiness.gaps
    )
    evidence_line = ", ".join(sorted(profile.evidence_labels)) or "none recorded"
    return (
        f"Student: {profile.year}th year {profile.major}, targeting {profile.target_role}.\n"
        f"Evidence already held: {evidence_line}\n"
        f"Ranked priority gaps (1 is highest):\n{gap_lines}\n\n"
        "Three agents are available, each sourcing one specific kind of candidate:\n"
        "  Module Agent  - NUS modules (coursework) from NUSMods\n"
        "  Event Agent   - hackathons from Devpost\n"
        "  Project Agent - open source projects to contribute to, from GitHub Search\n\n"
        "Decide which to dispatch this turn. Dispatch an agent only if its specific kind "
        "of candidate could plausibly close one of the priority gaps above better than "
        "evidence the student already holds. Skip the rest, with a specific reason per "
        "skip that refers to what that agent actually sources. Call the plan tool with "
        "your decision."
    )


def _call_bedrock(prompt: str) -> tuple[PlannerDecision, ModelCallStats]:
    """Returns the decision plus this call's metrics contribution (tokens spent across
    every attempt, and whether the structured output validated).
    """
    stats = ModelCallStats()
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = _bedrock().converse(
                modelId=MODEL_HAIKU,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": _TOOL_NAME,
                                "description": "Record which agents to dispatch this turn.",
                                "inputSchema": {"json": _TOOL_SCHEMA},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": _TOOL_NAME}},
                },
                inferenceConfig={"temperature": 0, "maxTokens": 500},
            )
            input_tokens, output_tokens = token_usage(response)
            stats.input_tokens += input_tokens
            stats.output_tokens += output_tokens
            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    decision = PlannerDecision.model_validate(block["toolUse"]["input"])
                    stats.schema_validations_passed += 1
                    return decision, stats
            raise ValueError("model did not call the plan tool")
        except ValidationError as exc:
            stats.schema_validations_failed += 1
            last_error = exc
        except (ClientError, BotoCoreError, ValueError, KeyError) as exc:
            last_error = exc
    raise RuntimeError(f"planner Bedrock call failed after retry: {last_error}") from last_error


def _fallback_decision() -> PlannerDecision:
    return PlannerDecision(
        dispatch=list(AGENT_NAMES),
        skip=[],
        rationale="Fallback: Bedrock call failed after retry, dispatching every agent "
        "rather than wrongly excluding one.",
    )


def planner_node(state: RunState) -> dict:
    profile = state["profile"]
    readiness = state["readiness"]
    metrics = state.get("metrics") or RunMetrics()

    trace: list[TraceEvent] = []
    try:
        decision, stats = _call_bedrock(_build_prompt(profile, readiness))
    except RuntimeError as exc:
        decision = _fallback_decision()
        stats = ModelCallStats()  # a failed call recorded no tokens or validations
        trace.append(
            TraceEvent(
                kind=TraceKind.PLANNED,
                agent="Career Agent",
                message="Planner fell back to dispatching every agent",
                detail=str(exc),
            )
        )
    metrics = apply_model_call(metrics, stats)

    trace.append(
        TraceEvent(
            kind=TraceKind.PLANNED,
            agent="Career Agent",
            message=f"Dispatching {', '.join(decision.dispatch) or 'nobody'}",
            detail=decision.rationale,
        )
    )
    for skip in decision.skip:
        trace.append(
            TraceEvent(
                kind=TraceKind.PLANNED,
                agent="Career Agent",
                message=f"Skipping {skip.agent}",
                detail=skip.reason,
            )
        )

    return {
        "dispatch": decision.dispatch,
        "skipped": [skip.agent for skip in decision.skip],
        "trace": trace,
        "metrics": metrics,
    }


if __name__ == "__main__":
    # Manual sanity check, not a pytest test — CLAUDE.md bars tests from calling Bedrock.
    # Run with fresh AWS credentials in .env: python -m src.agents.planner
    from src.config import DEFAULT_ROLE
    from src.state import Dimension, DimensionScore, Gap

    demo_profile = StudentProfile(
        name="Tan Wei Ling",
        year=2,
        major="Computer Science",
        target_role=DEFAULT_ROLE,
        units_completed=72,
    )
    demo_readiness = Readiness(
        dimensions=[
            DimensionScore(dimension=d, score=0.5, rationale="demo") for d in Dimension
        ],
        gaps=[
            Gap(
                dimension=Dimension.SYSTEMS,
                label="Distributed systems",
                priority=1,
                current=0.3,
                target=0.8,
            )
        ],
    )
    result = planner_node({"profile": demo_profile, "readiness": demo_readiness})
    print(json.dumps({**result, "trace": [t.model_dump(mode="json") for t in result["trace"]]}, indent=2))
