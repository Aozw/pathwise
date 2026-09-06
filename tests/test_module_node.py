"""Unit tests for W2.5 — src/agents/module.py.

load_catalogue and fetch_module_detail are mocked (no network in tests, per the
CLAUDE.md hard rule); is_eligible is exercised for real since it's a pure function
already unit tested on its own (test_eligibility.py). Catalogue entries here mirror
the real bulk shape: prereq_tree is always None, prerequisite_text is the only
zero-network signal for whether a module is gated - matching what load_catalogue()
actually returns live (see src/tools/nusmods.py).

W2.1b's shortlist() (src/tools/retrieval.py, its own real Bedrock call) is mocked
here too - none of these tests set state["readiness"], so module_node's fallback
path (no gap, no shortlist call at all) is what runs, same as before W2.1b was
reinstated. The dedicated shortlist-path tests near the bottom set readiness and
mock module_agent.shortlist directly.
"""

from __future__ import annotations

from unittest.mock import patch

import src.agents.module as module_agent
from src.state import (
    CompletedModule,
    Dimension,
    DimensionScore,
    Gap,
    Readiness,
    SourceName,
    StudentProfile,
)
from src.tools.nusmods import NUSModsModule


def _catalogue_module(code: str, prerequisite_text: str | None = None) -> NUSModsModule:
    return NUSModsModule(
        code=code, title=f"Title {code}", description="desc", prerequisite_text=prerequisite_text
    )


def _detail_module(code: str, prereq_tree) -> NUSModsModule:
    return NUSModsModule(code=code, title=f"Title {code}", description="desc", prereq_tree=prereq_tree)


def _profile(completed: list[CompletedModule]) -> StudentProfile:
    return StudentProfile(
        name="Test Student",
        year=2,
        major="Computer Science",
        target_role="backend_infrastructure",
        completed_modules=completed,
    )


def _readiness(label: str = "Systems depth") -> Readiness:
    return Readiness(
        dimensions=[DimensionScore(dimension=Dimension.SYSTEMS, score=0.3, rationale="x")],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label=label, priority=1, current=0.2, target=0.8)],
    )


def test_ungated_modules_skip_the_live_fetch_entirely():
    catalogue = [_catalogue_module("CS1010"), _catalogue_module("CS2106")]
    state = {"profile": _profile([])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail"
    ) as mock_fetch, patch.object(module_agent, "CACHE_PATH") as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    mock_fetch.assert_not_called()
    codes = {c.id for c in result["candidates"]}
    assert codes == {"nusmods:CS1010", "nusmods:CS2106"}
    assert all(c.source == SourceName.FIXTURE for c in result["candidates"])
    assert "live-checked prerequisites for 0" in result["trace"][0].message


def test_gated_module_is_live_checked_and_excluded_when_not_completed():
    catalogue = [_catalogue_module("CS3210", prerequisite_text="must have completed CS2106")]
    state = {"profile": _profile([])}
    detail = _detail_module("CS3210", prereq_tree={"or": ["CS2100", "CS2106"]})

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail", return_value=detail
    ) as mock_fetch, patch.object(module_agent, "CACHE_PATH") as mock_cache_path:
        mock_cache_path.exists.return_value = True
        result = module_agent.module_node(state)

    mock_fetch.assert_called_once_with("CS3210")
    assert result["candidates"] == []
    assert "live-checked prerequisites for 1 (1 confirmed not-yet-eligible)" in result["trace"][0].message


def test_gated_module_is_included_once_prerequisite_is_completed():
    catalogue = [_catalogue_module("CS3210", prerequisite_text="must have completed CS2106")]
    state = {"profile": _profile([CompletedModule(code="CS2106", title="x", units=4.0)])}
    detail = _detail_module("CS3210", prereq_tree={"or": ["CS2100", "CS2106"]})

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail", return_value=detail
    ), patch.object(module_agent, "CACHE_PATH") as mock_cache_path:
        mock_cache_path.exists.return_value = True
        result = module_agent.module_node(state)

    assert [c.id for c in result["candidates"]] == ["nusmods:CS3210"]
    assert result["candidates"][0].source == SourceName.NUSMODS


def test_detail_fetch_failure_falls_back_to_eligible():
    catalogue = [_catalogue_module("CS3210", prerequisite_text="must have completed CS2106")]
    state = {"profile": _profile([])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail", return_value=None
    ), patch.object(module_agent, "CACHE_PATH") as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert [c.id for c in result["candidates"]] == ["nusmods:CS3210"]
    assert "1 detail fetches failed after retry" in result["trace"][0].detail


def test_detail_fetch_budget_is_not_exceeded():
    # Cap and budget are both MAX_CANDIDATES_SCORED, so to observe the budget acting
    # independently of the output cap, the first `budget` gated modules must all be
    # confirmed-ineligible (consuming fetch budget without filling a candidate slot) -
    # only then do the modules past the budget (which skip the fetch entirely and
    # default-eligible) actually get selected.
    budget = module_agent._MAX_DETAIL_FETCHES
    catalogue = [
        _catalogue_module(f"CS{i}", prerequisite_text="must have completed something")
        for i in range(budget + 5)
    ]
    state = {"profile": _profile([])}
    always_blocked = _detail_module("blocked", prereq_tree={"and": ["SOME_NEVER_COMPLETED_CODE"]})

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail", return_value=always_blocked
    ) as mock_fetch, patch.object(module_agent, "CACHE_PATH") as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert mock_fetch.call_count == budget
    # The first `budget` modules were live-checked and confirmed ineligible; the
    # last 5 exceeded the budget, skipped the fetch, and defaulted to eligible.
    assert len(result["candidates"]) == 5


def test_module_node_handles_missing_profile():
    catalogue = [_catalogue_module("CS1010")]
    state: dict = {}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert len(result["candidates"]) == 1


def test_module_node_caps_at_max_candidates_scored():
    catalogue = [
        _catalogue_module(f"CS{i}") for i in range(module_agent.MAX_CANDIDATES_SCORED + 10)
    ]
    state = {"profile": _profile([])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert len(result["candidates"]) == module_agent.MAX_CANDIDATES_SCORED


# --- W2.1b shortlist wiring ---------------------------------------------------


def test_with_a_gap_present_the_whole_catalogue_is_scanned_then_shortlisted():
    """Scan cap must be off when there's a gap to rank against - shortlist(), not
    catalogue order, decides what survives to MAX_CANDIDATES_SCORED."""
    catalogue = [_catalogue_module(f"CS{i}") for i in range(module_agent.MAX_CANDIDATES_SCORED + 10)]
    state = {"profile": _profile([]), "readiness": _readiness()}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path, patch.object(
        module_agent, "shortlist", return_value=(["CS0", "CS1"], False)
    ) as mock_shortlist:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    (gap_text, eligible_ids, k), _ = mock_shortlist.call_args
    assert gap_text == "Systems depth (systems)"
    assert len(eligible_ids) == module_agent.MAX_CANDIDATES_SCORED + 10  # full scan, no early cap
    assert k == module_agent.SHORTLIST_K
    assert [c.id for c in result["candidates"]] == ["nusmods:CS0", "nusmods:CS1"]
    assert "shortlisted to 2 against 'Systems depth (systems)'" in result["trace"][0].message


def test_shortlist_fallback_appends_its_own_trace_event():
    catalogue = [_catalogue_module("CS1010")]
    state = {"profile": _profile([]), "readiness": _readiness()}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path, patch.object(
        module_agent, "shortlist", return_value=(["CS1010"], True)
    ):
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert len(result["trace"]) == 2
    assert "fell back to catalogue order" in result["trace"][1].message


def test_no_readiness_skips_shortlist_entirely():
    catalogue = [_catalogue_module("CS1010")]
    state = {"profile": _profile([])}  # no "readiness" key at all

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path, patch.object(module_agent, "shortlist") as mock_shortlist:
        mock_cache_path.exists.return_value = False
        module_agent.module_node(state)

    mock_shortlist.assert_not_called()


def test_readiness_with_no_eligible_modules_skips_shortlist():
    catalogue = [_catalogue_module("CS3210", prerequisite_text="must have completed CS2106")]
    state = {"profile": _profile([]), "readiness": _readiness()}
    detail = _detail_module("CS3210", prereq_tree={"or": ["CS2106"]})

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "fetch_module_detail", return_value=detail
    ), patch.object(module_agent, "CACHE_PATH") as mock_cache_path, patch.object(
        module_agent, "shortlist"
    ) as mock_shortlist:
        mock_cache_path.exists.return_value = True
        result = module_agent.module_node(state)

    mock_shortlist.assert_not_called()
    assert result["candidates"] == []
