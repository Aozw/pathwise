"""Module Agent node — W2.5, upgraded with real per-candidate eligibility checking.

load_catalogue() (W2.1) is pure file I/O, no network, and its prereq_tree is always
None on the live path - the bulk catalogue never carries a structured tree (see
src/tools/nusmods.py's docstring). Left as-is, is_eligible() (W2.2) would then pass
almost every module regardless of the student's completed modules.

Fix: the bulk catalogue does carry a free-text `prerequisite_text` field, present
exactly when a module has a prerequisite and empty when it genuinely doesn't. That's
a zero-network signal for which modules are even worth checking. This node walks the
catalogue once, in the existing cheap-heuristic order (W2.1b's semantic shortlist is
cut per PLAN.md, so there is still no relevance ranking): a module with no
prerequisite text is confirmed eligible without any fetch; a module that claims one
gets a live fetch_module_detail() call (W2.1) for its real tree, up to a fixed budget
of `_MAX_DETAIL_FETCHES` live calls per run - bounding worst-case added latency
regardless of how many gated modules the catalogue scan passes over. A module whose
eligibility can't be confirmed (fetch failed, or the budget ran out first) falls back
to eligible, same as before this fix - now the rare case instead of the universal one.

Trace records not just the found/eligible/capped funnel but how many modules were
actually live-checked and how many were *confirmed* not-yet-eligible by a real tree -
the accuracy number PLAN.md's W2.2 description calls out as slide-worthy, now
possible because eligibility is a real determination for most candidates rather than
a permanent unknown.
"""

from __future__ import annotations

from src.config import MAX_CANDIDATES_SCORED, TIME_COST_HOURS
from src.state import Candidate, CandidateKind, RunState, SourceName, TraceEvent, TraceKind
from src.tools.eligibility import is_eligible
from src.tools.nusmods import CACHE_PATH, NUSModsModule, fetch_module_detail, load_catalogue

# One live detail fetch per candidate slot, worst case - bounds this node to at most
# this many sequential live NUSMods calls per run regardless of how many gated
# modules the catalogue scan encounters before filling the cap.
_MAX_DETAIL_FETCHES = MAX_CANDIDATES_SCORED


def _to_candidate(module: NUSModsModule, source: SourceName) -> Candidate:
    return Candidate(
        id=f"nusmods:{module.code}",
        kind=CandidateKind.MODULE,
        source=source,
        title=f"{module.code} {module.title}",
        description=module.description,
        units=module.units,
        prerequisites_met=True,  # every returned candidate passed is_eligible below
        time_cost_hours=TIME_COST_HOURS["module"],
    )


def module_node(state: RunState) -> dict:
    profile = state.get("profile")
    completed_modules = profile.completed_modules if profile else []
    source = SourceName.NUSMODS if CACHE_PATH.exists() else SourceName.FIXTURE

    catalogue = load_catalogue()

    selected: list[NUSModsModule] = []
    detail_fetch_count = 0
    detail_fetch_failures = 0
    confirmed_ineligible = 0

    for module in catalogue:
        if len(selected) >= MAX_CANDIDATES_SCORED:
            break

        resolved = module
        if module.prerequisite_text and detail_fetch_count < _MAX_DETAIL_FETCHES:
            detail_fetch_count += 1
            detail = fetch_module_detail(module.code)
            if detail is not None:
                resolved = detail
            else:
                detail_fetch_failures += 1

        if is_eligible(resolved, completed_modules):
            selected.append(resolved)
        elif resolved.prereq_tree is not None:
            confirmed_ineligible += 1  # a real tree said no, not a guess

    candidates = [_to_candidate(module, source) for module in selected]

    return {
        "candidates": candidates,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Module Agent",
                message=f"Found {len(catalogue)} modules, live-checked prerequisites for "
                f"{detail_fetch_count} ({confirmed_ineligible} confirmed not-yet-eligible), "
                f"returned {len(candidates)} (cap {MAX_CANDIDATES_SCORED})",
                detail=f"{detail_fetch_failures} detail fetches failed after retry and fell "
                "back to treating that module as eligible, same as before this fix. "
                "Modules with no prerequisite text in the bulk catalogue skip the live "
                "fetch entirely - genuinely eligible, not a guess. No semantic shortlist "
                "(W2.1b is cut per PLAN.md) - catalogue order is still the only ranking.",
            )
        ],
    }
