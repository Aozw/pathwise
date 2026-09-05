"""Project Agent node — W2.5.

Real tool wiring, replacing the W1.2 fixture-reading stub: calls
github.search_projects() (W2.4), which already owns its own timeout/retry/
fixture-fallback and TraceEvent - this node forwards that event untouched and adds
one of its own recording the query and count. Same query-selection approach as
event.py: the current top-priority gap's label, falling back to a generic
approachable-project default when no gap has been assessed yet.
"""

from __future__ import annotations

from src.state import RunState, TraceEvent, TraceKind
from src.tools.github import search_projects

_DEFAULT_QUERY = "good first issue"


def _query_for(state: RunState) -> str:
    readiness = state.get("readiness")
    if readiness and readiness.gaps:
        return readiness.gaps[0].label
    return _DEFAULT_QUERY


def project_node(state: RunState) -> dict:
    query = _query_for(state)
    candidates, fallback_event = search_projects(query)

    trace = [
        TraceEvent(
            kind=TraceKind.OBSERVED,
            agent="Project Agent",
            message=f"Found {len(candidates)} repos for query {query!r}",
        )
    ]
    if fallback_event is not None:
        trace.append(fallback_event)

    return {"candidates": candidates, "trace": trace}
