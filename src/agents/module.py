"""Module Agent node — W2.5, upgraded with real per-candidate eligibility checking
and W2.1b's semantic shortlist, reinstated after Step 15 verification against real
Bedrock found the demo path needed it (see retrieval.py's module docstring): without
it, this node's only ranking was NUSMods catalogue order, so the 30 candidates
handed to scoring were essentially unrelated to the student's actual gap, and every
real run scored 0 candidates above threshold.

load_catalogue() (W2.1) is pure file I/O, no network, and its prereq_tree is always
None on the live path - the bulk catalogue never carries a structured tree (see
src/tools/nusmods.py's docstring). Left as-is, is_eligible() (W2.2) would then pass
almost every module regardless of the student's completed modules.

Fix: the bulk catalogue does carry a free-text `prerequisite_text` field, present
exactly when a module has a prerequisite and empty when it genuinely doesn't. That's
a zero-network signal for which modules are even worth checking. This node walks the
whole catalogue once (when there's a gap to shortlist against - see below): a module
with no prerequisite text is confirmed eligible without any fetch; a module that
claims one gets a live fetch_module_detail() call (W2.1) for its real tree, up to a
fixed budget of `_MAX_DETAIL_FETCHES` live calls per run - bounding worst-case added
latency regardless of how many gated modules the catalogue scan passes over. A
module whose eligibility can't be confirmed (fetch failed, or the budget ran out
first) falls back to eligible, same as before this fix - now the rare case instead
of the universal one.

Once the eligible set is known, retrieval.shortlist() ranks it by cosine similarity
to the top priority gap and keeps the top SHORTLIST_K - this is what makes the
candidates sent to scoring actually about the gap, rather than catalogue order. With
no readiness/gaps available yet (state under-populated, e.g. some tests), this node
falls back to its pre-W2.1b behaviour: cap the catalogue scan itself at
MAX_CANDIDATES_SCORED in catalogue order, no shortlist call, no embedding call, no
network beyond the bounded detail fetches - so nothing here depends on a gap being
present to run at all.

Trace records the found/eligible/shortlisted/capped funnel, how many modules were
actually live-checked, and how many were *confirmed* not-yet-eligible by a real
tree - the accuracy number PLAN.md's W2.2 description calls out as slide-worthy, and
the before/after shortlist counts PLAN.md's W2.5 description calls out as the token
argument on the slide.
"""

from __future__ import annotations

from src.config import MAX_CANDIDATES_SCORED, SHORTLIST_K, TIME_COST_HOURS
from src.state import (
    Candidate,
    CandidateKind,
    Readiness,
    RunState,
    SourceName,
    TraceEvent,
    TraceKind,
)
from src.tools.eligibility import is_eligible
from src.tools.nusmods import CACHE_PATH, NUSModsModule, fetch_module_detail, load_catalogue
from src.tools.retrieval import shortlist

# One live detail fetch per candidate slot, worst case - bounds this node to at most
# this many sequential live NUSMods calls per run regardless of how many gated
# modules the catalogue scan encounters before filling the cap.
_MAX_DETAIL_FETCHES = MAX_CANDIDATES_SCORED


def _top_gap_text(readiness: Readiness | None) -> str | None:
    """The gap the shortlist should rank modules against - the same #1 priority gap
    the planner dispatched on and the score node's prompt leads with. None if the
    graph reached this node with no readiness assessment yet, which the caller
    treats as "nothing to shortlist against" rather than an error.
    """
    if readiness is None or not readiness.gaps:
        return None
    top = min(readiness.gaps, key=lambda g: g.priority)
    return f"{top.label} ({top.dimension.value})"


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
    gap_text = _top_gap_text(state.get("readiness"))

    # With a gap to shortlist against, the eligible set has to be gathered from the
    # whole catalogue before ranking - capping the scan itself at MAX_CANDIDATES_SCORED
    # (catalogue order) would defeat the point of shortlisting. Without one, fall back
    # to the old behaviour: cap the scan directly, no shortlist call, no embedding call.
    scan_cap = None if gap_text else MAX_CANDIDATES_SCORED

    eligible: list[NUSModsModule] = []
    detail_fetch_count = 0
    detail_fetch_failures = 0
    confirmed_ineligible = 0

    for module in catalogue:
        if scan_cap is not None and len(eligible) >= scan_cap:
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
            eligible.append(resolved)
        elif resolved.prereq_tree is not None:
            confirmed_ineligible += 1  # a real tree said no, not a guess

    shortlist_used = False
    shortlist_fallback = False
    if gap_text and eligible:
        shortlist_used = True
        by_code = {m.code: m for m in eligible}
        ranked_codes, shortlist_fallback = shortlist(gap_text, list(by_code), SHORTLIST_K)
        selected = [by_code[code] for code in ranked_codes if code in by_code]
    else:
        selected = eligible
    selected = selected[:MAX_CANDIDATES_SCORED]

    candidates = [_to_candidate(module, source) for module in selected]

    funnel = f"Found {len(catalogue)} modules, {len(eligible)} eligible"
    if shortlist_used:
        funnel += f", shortlisted to {len(selected)} against '{gap_text}'"
    funnel += (
        f", live-checked prerequisites for {detail_fetch_count} "
        f"({confirmed_ineligible} confirmed not-yet-eligible), returned {len(candidates)} "
        f"(cap {MAX_CANDIDATES_SCORED})"
    )

    trace = [
        TraceEvent(
            kind=TraceKind.OBSERVED,
            agent="Module Agent",
            message=funnel,
            detail=f"{detail_fetch_failures} detail fetches failed after retry and fell "
            "back to treating that module as eligible. Modules with no prerequisite text "
            "in the bulk catalogue skip the live fetch entirely - genuinely eligible, not "
            "a guess."
            + (
                " Semantic shortlist (W2.1b) ranked the eligible set by cosine similarity "
                "to the top priority gap before capping."
                if shortlist_used and not shortlist_fallback
                else ""
            ),
        )
    ]
    if shortlist_used and shortlist_fallback:
        trace.append(
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Module Agent",
                message="Semantic shortlist unavailable, fell back to catalogue order",
                detail="Either data/index/module_embeddings.npz is missing or the one "
                "runtime embedding call for the gap text failed after retry.",
            )
        )

    return {"candidates": candidates, "trace": trace}
