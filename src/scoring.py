"""Scoring composition — W1.4.

Pure functions only, no I/O. gap_coverage and role_fit are always parameters here,
never computed - the model produces those, somewhere with a Bedrock call, not in this
file. This module owns exactly the deterministic third of ScoreComponents: the time
cost lookup, the redundancy penalty as set logic over evidence already held, and the
weighted sum that combines all four into `total`. Runs standalone in a test with no
fixtures, no network, no Bedrock.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.config import MAX_TIME_COST_HOURS, SCORE_WEIGHTS, TIME_COST_HOURS
from src.state import Candidate, Dimension, ScoreComponents, StudentProfile


def time_cost_score(candidate: Candidate) -> float:
    """1.0 is cheap, 0.0 is maximally expensive, linear in between.

    Uses the candidate's own `time_cost_hours` if a source ever sets it (no source
    does yet); otherwise falls back to the coarse per-kind estimate in
    config.TIME_COST_HOURS. Clamped to [0, 1] since a candidate could in principle
    report more hours than the config ceiling.
    """
    hours = candidate.time_cost_hours
    if hours is None:
        hours = TIME_COST_HOURS[candidate.kind]
    return max(0.0, min(1.0, 1.0 - hours / MAX_TIME_COST_HOURS))


def redundancy_penalty(
    candidate: Candidate,
    profile: StudentProfile,
    gap_dimensions: Mapping[str, Dimension],
) -> float:
    """1.0 is fully redundant: every gap this candidate closes sits in a readiness
    dimension the student already holds evidence in. 0.0 is entirely new ground. A
    candidate that closes no gaps is not redundant, just unscored on this axis.

    Matched at Dimension granularity, not on gap-label strings. Gap labels are free
    text the readiness model produces per run ("Distributed systems"); resume evidence
    is classified independently; the two would never string-match. Both Gap.dimension
    and Evidence.dimension are the closed five-value Dimension enum, so they can.
    `gap_dimensions` maps each Gap.label to its Dimension - the score node builds it
    from the run's readiness.
    """
    if not candidate.closes_gaps:
        return 0.0
    closed_dimensions = {
        gap_dimensions[label] for label in candidate.closes_gaps if label in gap_dimensions
    }
    if not closed_dimensions:
        return 0.0
    evidence_dimensions = {item.dimension for item in profile.evidence}
    return len(closed_dimensions & evidence_dimensions) / len(closed_dimensions)


def weighted_total(
    gap_coverage: float, role_fit: float, time_cost: float, redundancy_penalty_value: float
) -> float:
    """config.SCORE_WEIGHTS already carries redundancy_penalty's weight as negative,
    so a plain weighted sum subtracts it - no special-casing needed here.
    """
    return (
        SCORE_WEIGHTS["gap_coverage"] * gap_coverage
        + SCORE_WEIGHTS["role_fit"] * role_fit
        + SCORE_WEIGHTS["time_cost"] * time_cost
        + SCORE_WEIGHTS["redundancy_penalty"] * redundancy_penalty_value
    )


def compose_score(
    candidate: Candidate,
    profile: StudentProfile,
    gap_coverage: float,
    role_fit: float,
    gap_dimensions: Mapping[str, Dimension],
    rationale: str = "",
) -> ScoreComponents:
    """Combine the model-produced gap_coverage/role_fit with the two components
    computed here into one ScoreComponents, with the weighted total. `gap_dimensions`
    maps Gap.label to Dimension for the redundancy penalty - see redundancy_penalty.
    """
    time_cost = time_cost_score(candidate)
    penalty = redundancy_penalty(candidate, profile, gap_dimensions)
    total = weighted_total(gap_coverage, role_fit, time_cost, penalty)
    return ScoreComponents(
        gap_coverage=gap_coverage,
        role_fit=role_fit,
        time_cost=time_cost,
        redundancy_penalty=penalty,
        total=total,
        rationale=rationale,
    )
