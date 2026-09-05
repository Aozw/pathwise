"""Unit tests for W1.4 — src/scoring.py.

Pure functions, no network, no fixtures beyond what's constructed inline. Explicitly
required by PLAN.md's W1.4 description ("Pure functions, no I/O, fully unit tested").
"""

from __future__ import annotations

import math

from src.config import MAX_TIME_COST_HOURS, SCORE_WEIGHTS, TIME_COST_HOURS
from src.scoring import compose_score, redundancy_penalty, time_cost_score, weighted_total
from src.state import Candidate, CandidateKind, Evidence, SourceName, StudentProfile


def _candidate(**overrides) -> Candidate:
    defaults = dict(
        id="nusmods:CS3210",
        kind=CandidateKind.MODULE,
        source=SourceName.NUSMODS,
        title="Parallel Computing",
    )
    return Candidate(**{**defaults, **overrides})


def _profile(**overrides) -> StudentProfile:
    defaults = dict(name="Tan Wei Ling", year=2, major="Computer Science", target_role="backend_infrastructure")
    return StudentProfile(**{**defaults, **overrides})


def test_time_cost_score_uses_config_lookup_by_kind():
    for kind, hours in TIME_COST_HOURS.items():
        score = time_cost_score(_candidate(kind=CandidateKind(kind)))
        assert math.isclose(score, 1.0 - hours / MAX_TIME_COST_HOURS)


def test_time_cost_score_prefers_candidates_own_hours():
    candidate = _candidate(kind=CandidateKind.MODULE, time_cost_hours=30.0)
    assert math.isclose(time_cost_score(candidate), 1.0 - 30.0 / MAX_TIME_COST_HOURS)


def test_time_cost_score_is_clamped_to_zero_and_one():
    assert time_cost_score(_candidate(time_cost_hours=0.0)) == 1.0
    assert time_cost_score(_candidate(time_cost_hours=MAX_TIME_COST_HOURS * 5)) == 0.0


def test_redundancy_penalty_zero_when_no_gaps_claimed():
    assert redundancy_penalty(_candidate(closes_gaps=[]), _profile()) == 0.0


def test_redundancy_penalty_zero_when_evidence_does_not_overlap():
    candidate = _candidate(closes_gaps=["Distributed systems"])
    profile = _profile(evidence=[Evidence(label="rest api", dimension="programming", source_text="x")])
    assert redundancy_penalty(candidate, profile) == 0.0


def test_redundancy_penalty_one_when_fully_covered_by_evidence():
    candidate = _candidate(closes_gaps=["rest api"])
    profile = _profile(evidence=[Evidence(label="rest api", dimension="programming", source_text="x")])
    assert redundancy_penalty(candidate, profile) == 1.0


def test_redundancy_penalty_is_the_overlap_fraction():
    candidate = _candidate(closes_gaps=["rest api", "distributed systems", "sql"])
    profile = _profile(
        evidence=[
            Evidence(label="rest api", dimension="programming", source_text="x"),
            Evidence(label="sql", dimension="data", source_text="y"),
        ]
    )
    assert math.isclose(redundancy_penalty(candidate, profile), 2 / 3)


def test_weighted_total_matches_config_weights_directly():
    total = weighted_total(gap_coverage=1.0, role_fit=1.0, time_cost=1.0, redundancy_penalty_value=0.0)
    expected = SCORE_WEIGHTS["gap_coverage"] + SCORE_WEIGHTS["role_fit"] + SCORE_WEIGHTS["time_cost"]
    assert math.isclose(total, expected)


def test_weighted_total_subtracts_for_full_redundancy():
    without_penalty = weighted_total(0.5, 0.5, 0.5, redundancy_penalty_value=0.0)
    with_penalty = weighted_total(0.5, 0.5, 0.5, redundancy_penalty_value=1.0)
    assert math.isclose(without_penalty - with_penalty, abs(SCORE_WEIGHTS["redundancy_penalty"]))


def test_weighted_total_all_zero_inputs_is_zero():
    assert weighted_total(0.0, 0.0, 0.0, 0.0) == 0.0


def test_compose_score_fills_every_component():
    candidate = _candidate(closes_gaps=["distributed systems"], time_cost_hours=60.0)
    profile = _profile()
    scores = compose_score(candidate, profile, gap_coverage=0.9, role_fit=0.7, rationale="closes the top gap")

    assert scores.gap_coverage == 0.9
    assert scores.role_fit == 0.7
    assert math.isclose(scores.time_cost, time_cost_score(candidate))
    assert scores.redundancy_penalty == redundancy_penalty(candidate, profile)
    assert math.isclose(
        scores.total,
        weighted_total(0.9, 0.7, scores.time_cost, scores.redundancy_penalty),
    )
    assert scores.rationale == "closes the top gap"


def test_compose_score_does_not_fabricate_a_rationale():
    candidate = _candidate()
    profile = _profile()
    scores = compose_score(candidate, profile, gap_coverage=0.5, role_fit=0.5)
    assert scores.rationale == ""
