"""Planner outcomes wiring — fixed after Step 15 verification found the planner
never read state["outcomes"] at all, so a logged outcome could never change its
dispatch decision. The Bedrock call is mocked throughout, per the CLAUDE.md hard
rule against calling Bedrock or any external API from a test.
"""

from __future__ import annotations

from unittest.mock import patch

import src.agents.planner as planner
from src.state import (
    Candidate,
    CandidateKind,
    Dimension,
    DimensionScore,
    Gap,
    Outcome,
    Readiness,
    SourceName,
    StudentProfile,
)


def _profile() -> StudentProfile:
    return StudentProfile(
        name="Tan Wei Ling", year=2, major="Computer Science", target_role="backend_infrastructure"
    )


def _readiness() -> Readiness:
    return Readiness(
        dimensions=[DimensionScore(dimension=d, score=0.5, rationale="x") for d in Dimension],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label="Distributed systems", priority=1,
                  current=0.3, target=0.8)],
    )


def _repo_candidate() -> Candidate:
    return Candidate(id="github:abc123", kind=CandidateKind.PROJECT, source=SourceName.GITHUB,
                      title="cool-distributed-queue")


def test_describe_outcome_uses_the_candidates_audit_log():
    outcome = Outcome(candidate_id="github:abc123", result="not_shortlisted")
    described = planner._describe_outcome(outcome, [_repo_candidate()])
    assert described == "'cool-distributed-queue' from Project Agent (not_shortlisted)"


def test_describe_outcome_falls_back_when_candidate_not_found():
    outcome = Outcome(candidate_id="nusmods:CS9999", result="withdrew")
    described = planner._describe_outcome(outcome, [])
    assert described == "nusmods:CS9999 (withdrew)"


def test_prompt_says_none_yet_with_no_outcomes():
    prompt = planner._build_prompt(_profile(), _readiness(), [], [])
    assert "none yet" in prompt


def test_prompt_includes_a_logged_outcome():
    outcome = Outcome(candidate_id="github:abc123", result="not_shortlisted")
    prompt = planner._build_prompt(_profile(), _readiness(), [outcome], [_repo_candidate()])
    assert "'cool-distributed-queue' from Project Agent (not_shortlisted)" in prompt


def test_planner_node_forwards_outcomes_and_candidates_to_the_prompt():
    outcome = Outcome(candidate_id="github:abc123", result="not_shortlisted")
    state = {
        "profile": _profile(),
        "readiness": _readiness(),
        "outcomes": [outcome],
        "candidates": [_repo_candidate()],
    }
    decision = planner.PlannerDecision(dispatch=["Module Agent"], skip=[], rationale="r")
    stats = planner.ModelCallStats()

    with patch.object(planner, "_build_prompt", wraps=planner._build_prompt) as spy, \
         patch.object(planner, "_call_bedrock", return_value=(decision, stats)):
        planner.planner_node(state)

    spy.assert_called_once_with(state["profile"], state["readiness"], [outcome], [_repo_candidate()])
