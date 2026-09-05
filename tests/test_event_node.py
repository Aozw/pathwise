"""Unit tests for W2.5 — src/agents/event.py. search_hackathons is mocked; it has
its own tests (test_devpost.py) covering the real network path.
"""

from __future__ import annotations

from unittest.mock import patch

import src.agents.event as event_agent
from src.state import (
    Candidate,
    CandidateKind,
    Dimension,
    Gap,
    Readiness,
    SourceName,
    TraceEvent,
    TraceKind,
)


def _candidate(id_: str) -> Candidate:
    return Candidate(id=id_, kind=CandidateKind.HACKATHON, source=SourceName.DEVPOST, title="x")


def _readiness_with_gap(label: str) -> Readiness:
    return Readiness(
        dimensions=[],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label=label, priority=1, current=0.2, target=0.8)],
    )


def test_event_node_uses_top_gap_label_as_query():
    state = {"readiness": _readiness_with_gap("Distributed systems")}

    with patch.object(
        event_agent, "search_hackathons", return_value=([_candidate("devpost:1")], None)
    ) as mock_search:
        result = event_agent.event_node(state)

    mock_search.assert_called_once_with("Distributed systems")
    assert len(result["candidates"]) == 1
    assert len(result["trace"]) == 1
    assert "Found 1 hackathons" in result["trace"][0].message


def test_event_node_falls_back_to_default_query_when_no_gaps():
    state: dict = {}

    with patch.object(
        event_agent, "search_hackathons", return_value=([], None)
    ) as mock_search:
        event_agent.event_node(state)

    mock_search.assert_called_once_with(event_agent._DEFAULT_QUERY)


def test_event_node_forwards_fallback_trace_event():
    fallback_event = TraceEvent(
        kind=TraceKind.OBSERVED, agent="Event Agent", message="Devpost search failed, used fixture"
    )
    state = {"readiness": _readiness_with_gap("Cloud")}

    with patch.object(
        event_agent, "search_hackathons", return_value=([_candidate("devpost:1")], fallback_event)
    ):
        result = event_agent.event_node(state)

    assert len(result["trace"]) == 2
    assert result["trace"][1] is fallback_event
