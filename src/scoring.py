"""Scoring composition — W1.4.

Pure functions only, no I/O. gap_coverage and role_fit are always parameters here,
never computed - the model produces those, somewhere with a Bedrock call, not in this
file. This module owns exactly the deterministic third of ScoreComponents: the time
cost lookup, the redundancy penalty as set logic over evidence already held, and the
weighted sum that combines all four into `total`. Runs standalone in a test with no
fixtures, no network, no Bedrock.
"""

from __future__ import annotations

from src.config import MAX_TIME_COST_HOURS, SCORE_WEIGHTS, TIME_COST_HOURS
from src.state import Candidate, ScoreComponents, StudentProfile


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


def redundancy_penalty(candidate: Candidate, profile: StudentProfile) -> float:
    """1.0 is fully redundant: every gap this candidate claims to close is already
    covered by evidence the student holds. 0.0 is entirely new ground. A candidate
    that closes no gaps at all is not redundant, just unscored on that axis.
    """
    if not candidate.closes_gaps:
        return 0.0
    already_covered = set(candidate.closes_gaps) & profile.evidence_labels
    return len(already_covered) / len(candidate.closes_gaps)


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
    rationale: str = "",
) -> ScoreComponents:
    """Combine the model-produced gap_coverage/role_fit with the two components
    computed here into one ScoreComponents, with the weighted total.
    """
    time_cost = time_cost_score(candidate)
    penalty = redundancy_penalty(candidate, profile)
    total = weighted_total(gap_coverage, role_fit, time_cost, penalty)
    return ScoreComponents(
        gap_coverage=gap_coverage,
        role_fit=role_fit,
        time_cost=time_cost,
        redundancy_penalty=penalty,
        total=total,
        rationale=rationale,
    )
