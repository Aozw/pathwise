"""Planner node.

STUB for W1.2 (graph skeleton). The real Bedrock call with a structured
{dispatch, skip, rationale} output schema lands in W1.3 — that is the project's core
claim and needs its own careful build. For now this always dispatches every agent, so
the conditional fan-out in graph.py has something real to route.
"""

from __future__ import annotations

from src.config import AGENT_NAMES
from src.state import RunState, TraceEvent, TraceKind


def planner_node(state: RunState) -> dict:
    dispatch = list(AGENT_NAMES)
    return {
        "dispatch": dispatch,
        "skipped": [],
        "trace": [
            TraceEvent(
                kind=TraceKind.PLANNED,
                agent="Career Agent",
                message=f"Dispatching {', '.join(dispatch)}",
                detail="Stub planner: always dispatches every agent, no gap-driven "
                "selection yet. Real planning lands in W1.3.",
            )
        ],
    }
