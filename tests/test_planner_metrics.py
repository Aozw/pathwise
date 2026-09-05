"""W3.4 — the planner node's metrics threading.

The Bedrock call is mocked. The point is narrow: planner_node must fold its model
call's tokens and schema-validation outcome into state['metrics'] and pass the
running total forward, and a failed call must not lose the totals already there.
"""

from __future__ import annotations

from unittest.mock import patch

import src.agents.planner as planner
from src.state import (
    Dimension,
    DimensionScore,
    Gap,
    Readiness,
    RunMetrics,
    StudentProfile,
)


def _state() -> dict:
    profile = StudentProfile(
        name="Tan Wei Ling", year=2, major="Computer Science", target_role="backend_infrastructure"
    )
    readiness = Readiness(
        dimensions=[DimensionScore(dimension=d, score=0.5, rationale="x") for d in Dimension],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label="Distributed systems", priority=1, current=0.3, target=0.8)],
    )
    return {"profile": profile, "readiness": readiness, "metrics": RunMetrics(input_tokens=10)}


def test_planner_folds_model_call_stats_into_metrics():
    decision = planner.PlannerDecision(dispatch=["Module Agent"], skip=[], rationale="r")
    stats = planner.ModelCallStats(input_tokens=200, output_tokens=15, schema_validations_passed=1)
    with patch.object(planner, "_call_bedrock", return_value=(decision, stats)):
        result = planner.planner_node(_state())

    assert result["metrics"].input_tokens == 210
    assert result["metrics"].output_tokens == 15
    assert result["metrics"].schema_validations_passed == 1


def test_planner_fallback_keeps_prior_totals_and_adds_nothing():
    with patch.object(planner, "_call_bedrock", side_effect=RuntimeError("boom after retry")):
        result = planner.planner_node(_state())

    assert result["dispatch"]  # fell back to dispatching everyone
    assert result["metrics"].input_tokens == 10  # unchanged
    assert result["metrics"].schema_validations_passed == 0
