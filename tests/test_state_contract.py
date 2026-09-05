"""Smoke test for the PR #1 contract.

Deliberately shallow. It proves the types import, construct and round-trip, and
that the committed fixtures are valid. Real behaviour tests belong to whoever
writes the behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

from src import config
from src.state import (
    Candidate,
    CandidateKind,
    CompletedModule,
    Dimension,
    Evidence,
    Gap,
    ScoreComponents,
    SourceName,
    StudentProfile,
    TraceEvent,
    TraceKind,
    new_run_state,
)

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures"


def test_empty_state_has_every_key():
    state = new_run_state("run-001")
    for key in ("run_id", "candidates", "trace", "iteration", "metrics"):
        assert key in state
    assert state["iteration"] == 0
    assert state["candidates"] == []


def test_profile_helpers():
    profile = StudentProfile(
        name="Tan Wei Ling",
        year=2,
        major="Computer Science",
        target_role="backend_infrastructure",
        completed_modules=[
            CompletedModule(code="CS2106", title="Operating Systems", units=4, grade="B+"),
            CompletedModule(code="CS2105", title="Computer Networks", units=4, grade="B"),
        ],
        units_completed=72,
        evidence=[
            Evidence(label="rest api", dimension=Dimension.PROGRAMMING, source_text="Built a REST API in Flask"),
        ],
    )
    assert profile.completed_codes == {"CS2106", "CS2105"}
    assert profile.evidence_labels == {"rest api"}


def test_candidate_round_trips_through_json():
    candidate = Candidate(
        id="nusmods:CS3210",
        kind=CandidateKind.MODULE,
        source=SourceName.NUSMODS,
        title="Parallel Computing",
        units=4,
        prerequisites_met=True,
        closes_gaps=["Distributed systems"],
        scores=ScoreComponents(
            gap_coverage=0.9,
            role_fit=0.8,
            time_cost=0.3,
            redundancy_penalty=0.0,
            total=0.71,
            rationale="Directly closes the top priority gap.",
        ),
    )
    restored = Candidate.model_validate_json(candidate.model_dump_json())
    assert restored == candidate


def test_gap_size():
    gap = Gap(dimension=Dimension.SYSTEMS, label="Distributed systems", priority=1, current=0.2, target=0.8)
    assert abs(gap.size - 0.6) < 1e-9


def test_trace_event_defaults_a_timestamp():
    event = TraceEvent(kind=TraceKind.PLANNED, agent="Career Agent", message="Skipped Project Agent")
    assert event.at is not None


def test_role_weights_sum_to_one():
    for role, weights in config.ROLE_DIMENSION_WEIGHTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, role


def test_every_dimension_is_weighted_for_every_role():
    names = {d.value for d in Dimension}
    for role, weights in config.ROLE_DIMENSION_WEIGHTS.items():
        assert set(weights) == names, role


def test_submission_is_never_auto_approvable():
    assert config.NEVER_AUTOMATED_ACTIONS & config.AUTO_APPROVABLE_ACTIONS == set()
    assert "submit_application" in config.NEVER_AUTOMATED_ACTIONS


def test_fixtures_are_present_and_parse():
    assert (FIXTURES / "transcript.txt").read_text().strip()
    assert (FIXTURES / "resume.txt").read_text().strip()
    for name in ("nusmods_module.json", "nusmods_module_list.json", "devpost_response.json", "github_response.json"):
        json.loads((FIXTURES / name).read_text())
