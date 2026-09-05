"""Unit tests for the score node's closed_gaps wiring — src/graph.py._score_node.

The Bedrock call is mocked (no network in tests, per the CLAUDE.md hard rule);
scoring.compose_score / redundancy_penalty run for real since they are pure and
already unit tested on their own (test_scoring.py). The point here is the seam:
the model's `closed_gaps` must land on the candidate so redundancy_penalty has
something to intersect against, and a label the model invents must not.
"""

from __future__ import annotations

from unittest.mock import patch

import src.graph as graph
from src.state import (
    Candidate,
    CandidateKind,
    Dimension,
    DimensionScore,
    Evidence,
    Gap,
    Readiness,
    SourceName,
    StudentProfile,
)

_GAP = "Distributed systems"


def _candidate(cid: str = "nusmods:CS3210") -> Candidate:
    return Candidate(
        id=cid,
        kind=CandidateKind.MODULE,
        source=SourceName.NUSMODS,
        title="Parallel Computing",
        time_cost_hours=0.0,  # keeps total above SCORE_THRESHOLD even with the penalty
    )


def _readiness() -> Readiness:
    return Readiness(
        dimensions=[DimensionScore(dimension=d, score=0.5, rationale="x") for d in Dimension],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label=_GAP, priority=1, current=0.3, target=0.8)],
    )


def _profile(evidence: list[Evidence] | None = None) -> StudentProfile:
    return StudentProfile(
        name="Tan Wei Ling",
        year=2,
        major="Computer Science",
        target_role="backend_infrastructure",
        evidence=evidence or [],
    )


def _state(profile: StudentProfile) -> dict:
    return {"candidates": [_candidate()], "profile": profile, "readiness": _readiness()}


def _decision(closed_gaps: list[str]) -> graph._ScoreDecision:
    return graph._ScoreDecision(
        judgments=[
            graph._Judgment(
                candidate_id="nusmods:CS3210",
                gap_coverage=1.0,
                role_fit=1.0,
                rationale="closes the top gap",
                closed_gaps=closed_gaps,
            )
        ]
    )


def test_closed_gaps_from_the_model_land_on_the_candidate():
    with patch.object(graph, "_call_score_bedrock", return_value=_decision([_GAP])):
        result = graph._score_node(_state(_profile()))

    assert [c.closes_gaps for c in result["ranked"]] == [[_GAP]]


def test_redundancy_penalty_fires_when_evidence_covers_a_closed_gap():
    evidence = [Evidence(label=_GAP, dimension=Dimension.SYSTEMS, source_text="ran a Raft cluster")]
    with patch.object(graph, "_call_score_bedrock", return_value=_decision([_GAP])):
        result = graph._score_node(_state(_profile(evidence)))

    assert result["ranked"][0].scores.redundancy_penalty == 1.0


def test_a_gap_label_the_model_invents_is_discarded():
    with patch.object(graph, "_call_score_bedrock", return_value=_decision([_GAP, "Made-up gap"])):
        result = graph._score_node(_state(_profile()))

    assert result["ranked"][0].closes_gaps == [_GAP]


def test_fallback_judgment_does_not_invent_closed_gaps():
    # No model judgment -> neutral 0.5/0.5 scores, which fall below SCORE_THRESHOLD,
    # so nothing is ranked. The point is the node handles a missing judgment without
    # crashing on the new closed_gaps path and without attributing gaps it never got.
    err = RuntimeError("score Bedrock call failed after retry: no credentials")
    with patch.object(graph, "_call_score_bedrock", side_effect=err):
        result = graph._score_node(_state(_profile()))

    assert result["ranked"] == []
    assert any("fell back" in event.message for event in result["trace"])
