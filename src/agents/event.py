"""Event Agent node — W2.5.

Real tool wiring, replacing the W1.2 fixture-reading stub: calls
devpost.search_hackathons() (W2.3), which already owns its own timeout/retry/
fixture-fallback and TraceEvent - this node forwards that event untouched (never
claims a fallback happened when it didn't, or vice versa) and adds one of its own
recording the query and count.

The search query is the current top-priority gap's label when one exists (readiness
is populated before this node ever runs - see graph.py), falling back to a generic
default only for a run with no assessed gaps yet.
"""

from __future__ import annotations

from src.state import RunState, TraceEvent, TraceKind
from src.tools.devpost import search_hackathons

_DEFAULT_QUERY = "singapore"


def _query_for(state: RunState) -> str:
    readiness = state.get("readiness")
    if readiness and readiness.gaps:
        return readiness.gaps[0].label
    return _DEFAULT_QUERY


def event_node(state: RunState) -> dict:
    query = _query_for(state)
    candidates, fallback_event = search_hackathons(query)

    trace = [
        TraceEvent(
            kind=TraceKind.OBSERVED,
            agent="Event Agent",
            message=f"Found {len(candidates)} hackathons for query {query!r}",
        )
    ]
    if fallback_event is not None:
        trace.append(fallback_event)

    return {"candidates": candidates, "trace": trace}
