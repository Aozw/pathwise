"""W3.3 — readiness assessment in src/agents/profile.py.

The model path can't run in CI, so the deterministic assessor and the pure
`_to_readiness` arithmetic are tested directly, and `assess_readiness` /
`profile_node` are driven by monkeypatching the `_call_*_bedrock` functions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import profile as profile_mod
from src.agents.profile import (
    _DimensionAssessment,
    _ReadinessExtracted,
    _to_readiness,
    assess_readiness,
    profile_node,
)
from src.config import ROLE_DIMENSION_WEIGHTS
from src.state import CompletedModule, Dimension, Evidence, StudentProfile

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures"


def _profile(**overrides) -> StudentProfile:
    defaults = dict(
        name="Tan Wei Ling",
        year=2,
        major="Computer Science",
        target_role="backend_infrastructure",
    )
    return StudentProfile(**{**defaults, **overrides})


def _all_dimensions(score: float) -> _ReadinessExtracted:
    return _ReadinessExtracted(
        dimensions=[
            _DimensionAssessment(dimension=d, score=score, rationale="x") for d in Dimension
        ]
    )


# --- deterministic assessor --------------------------------------------------


def test_deterministic_assessment_scores_all_five_dimensions():
    result = assess_readiness(_profile())  # no evidence, no modules -> deterministic
    assert {d.dimension for d in result.readiness.dimensions} == set(Dimension)
    assert result.used_fallback is True


def test_systems_is_the_priority_gap_for_the_fixture_student(monkeypatch: pytest.MonkeyPatch):
    # The real Tan Wei Ling: three systems modules but zero systems evidence, aiming
    # at a systems-heavy role. Systems must come out as the top gap.
    profile = _profile(
        completed_modules=[
            CompletedModule(code="CS2106", title="Introduction to Operating Systems", units=4),
            CompletedModule(code="CS2105", title="Introduction to Computer Networks", units=4),
            CompletedModule(code="CS2100", title="Computer Organisation", units=4),
        ],
        evidence=[
            Evidence(label="rest api", dimension=Dimension.PROGRAMMING, source_text="a"),
            Evidence(label="sql", dimension=Dimension.DATA, source_text="b"),
        ],
    )
    result = assess_readiness(profile)

    assert result.readiness.gaps[0].dimension == Dimension.SYSTEMS
    assert result.readiness.gaps[0].priority == 1
    assert any("systems" in event.message.lower() for event in result.trace)


# --- _to_readiness arithmetic ----------------------------------------------


def test_target_rises_with_the_roles_weight_for_the_dimension():
    readiness = _to_readiness(_all_dimensions(0.0), _profile(target_role="backend_infrastructure"))
    target_by_dim = {g.dimension: g.target for g in readiness.gaps}
    # backend_infrastructure weights systems (.35) far above communication (.05)
    assert target_by_dim[Dimension.SYSTEMS] > target_by_dim[Dimension.COMMUNICATION]


def test_a_dimension_at_or_above_target_is_not_a_gap():
    readiness = _to_readiness(_all_dimensions(1.0), _profile())
    assert readiness.gaps == []
    assert len(readiness.dimensions) == 5  # still scored, just not flagged


def test_gaps_are_ranked_by_weighted_shortfall():
    # Every dimension equally short in absolute terms; ranking must fall out of the
    # role weights alone.
    readiness = _to_readiness(_all_dimensions(0.1), _profile(target_role="backend_infrastructure"))
    ordered = [g.dimension.value for g in readiness.gaps]
    weights = ROLE_DIMENSION_WEIGHTS["backend_infrastructure"]
    assert ordered == sorted(ordered, key=lambda d: weights[d], reverse=True)
    assert [g.priority for g in readiness.gaps] == [1, 2, 3, 4, 5]


def test_model_gap_label_is_used_when_present_else_the_generic_one():
    extracted = _ReadinessExtracted(
        dimensions=[
            _DimensionAssessment(
                dimension=d,
                score=0.0,
                rationale="x",
                gap_label="consensus and replication" if d is Dimension.SYSTEMS else "",
            )
            for d in Dimension
        ]
    )
    readiness = _to_readiness(extracted, _profile())
    label_by_dim = {g.dimension: g.label for g in readiness.gaps}
    assert label_by_dim[Dimension.SYSTEMS] == "consensus and replication"
    assert "Programming fluency" in label_by_dim[Dimension.PROGRAMMING]


# --- assess_readiness paths -----------------------------------------------


def test_assess_readiness_uses_model_result_when_bedrock_succeeds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(profile_mod, "_call_readiness_bedrock", lambda _p: _all_dimensions(0.9))
    result = assess_readiness(_profile())

    assert result.used_fallback is False
    assert all(d.score == 0.9 for d in result.readiness.dimensions)


def test_assess_readiness_falls_back_and_traces(monkeypatch: pytest.MonkeyPatch):
    def boom(_p):
        raise RuntimeError("readiness Bedrock call failed after retry")

    monkeypatch.setattr(profile_mod, "_call_readiness_bedrock", boom)
    result = assess_readiness(_profile())

    assert result.used_fallback is True
    assert any("fallback" in event.message.lower() for event in result.trace)


def test_assess_readiness_rejects_unknown_target_role():
    with pytest.raises(ValueError, match="ROLE_DIMENSION_WEIGHTS"):
        assess_readiness(_profile(target_role="astronaut"))


# --- profile_node --------------------------------------------------------


def test_profile_node_returns_profile_readiness_and_trace(monkeypatch: pytest.MonkeyPatch):
    def unavailable(*_args):
        raise RuntimeError("Bedrock call failed after retry")

    for name in ("_call_bedrock", "_call_resume_bedrock", "_call_readiness_bedrock"):
        monkeypatch.setattr(profile_mod, name, unavailable)

    result = profile_node({})

    assert result["profile"].name == "Tan Wei Ling"
    assert result["profile"].completed_modules  # from the fixture transcript
    assert result["profile"].evidence  # from the fixture resume
    assert result["readiness"].dimensions
    assert result["readiness"].gaps[0].dimension == Dimension.SYSTEMS
    assert result["trace"]
