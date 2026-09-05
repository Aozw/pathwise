"""Module Agent node — W2.5.

Real tool wiring, replacing the W1.2 fixture-reading stub: load_catalogue() (W2.1,
offline-cached, no network at run time) filtered through is_eligible() (W2.2)
against the student's completed modules, then capped at a fixed number before
returning. The module embedding index / semantic shortlist (W2.1b) is cut per
PLAN.md section 5 - "The Module Agent passes eligible candidates straight to
scoring with a fixed cap" - so config.MAX_CANDIDATES_SCORED, taken in catalogue
order, is that cap. Records the found/eligible/capped funnel in the trace: that
reduction is the token argument PLAN.md wants on the slide.

No timeout/retry/fallback handling here: load_catalogue() is pure file I/O with no
network path at run time (see src/tools/nusmods.py), so the CLAUDE.md hard rule on
external calls does not apply to it.
"""

from __future__ import annotations

from src.config import MAX_CANDIDATES_SCORED, TIME_COST_HOURS
from src.state import Candidate, CandidateKind, RunState, SourceName, TraceEvent, TraceKind
from src.tools.eligibility import is_eligible
from src.tools.nusmods import CACHE_PATH, NUSModsModule, load_catalogue


def _to_candidate(module: NUSModsModule, source: SourceName) -> Candidate:
    return Candidate(
        id=f"nusmods:{module.code}",
        kind=CandidateKind.MODULE,
        source=source,
        title=f"{module.code} {module.title}",
        description=module.description,
        units=module.units,
        prerequisites_met=True,  # already filtered by is_eligible below
        time_cost_hours=TIME_COST_HOURS["module"],
    )


def module_node(state: RunState) -> dict:
    profile = state.get("profile")
    completed_modules = profile.completed_modules if profile else []
    source = SourceName.NUSMODS if CACHE_PATH.exists() else SourceName.FIXTURE

    catalogue = load_catalogue()
    eligible = [m for m in catalogue if is_eligible(m, completed_modules)]
    capped = eligible[:MAX_CANDIDATES_SCORED]

    candidates = [_to_candidate(module, source) for module in capped]

    return {
        "candidates": candidates,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Module Agent",
                message=f"Found {len(catalogue)} modules, {len(eligible)} eligible, "
                f"capped to {len(capped)} for scoring",
                detail="Eligibility filter is src.tools.eligibility.is_eligible (W2.2). "
                "No semantic shortlist (W2.1b is cut per PLAN.md) - the fixed cap is "
                "config.MAX_CANDIDATES_SCORED, taken in catalogue order.",
            )
        ],
    }
