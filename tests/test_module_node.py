"""Unit tests for W2.5 — src/agents/module.py.

load_catalogue is mocked so these tests don't depend on data/cache/ or
data/fixtures/ contents; is_eligible is exercised for real since it's a pure
function already unit tested on its own (test_eligibility.py).
"""

from __future__ import annotations

from unittest.mock import patch

import src.agents.module as module_agent
from src.state import CompletedModule, SourceName, StudentProfile
from src.tools.nusmods import NUSModsModule


def _nusmods_module(code: str, prereq_tree=None) -> NUSModsModule:
    return NUSModsModule(code=code, title=f"Title {code}", description="desc", prereq_tree=prereq_tree)


def _profile(completed: list[CompletedModule]) -> StudentProfile:
    return StudentProfile(
        name="Test Student",
        year=2,
        major="Computer Science",
        target_role="backend_infrastructure",
        completed_modules=completed,
    )


def test_module_node_filters_ineligible_and_reports_funnel_counts():
    catalogue = [
        _nusmods_module("CS1010"),  # no prereqs, always eligible
        _nusmods_module("CS3210", prereq_tree={"or": ["CS2100", "CS2106"]}),  # blocked
        _nusmods_module("CS2106"),  # no prereqs, always eligible
    ]
    state = {"profile": _profile([])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    codes = {c.id for c in result["candidates"]}
    assert codes == {"nusmods:CS1010", "nusmods:CS2106"}
    assert all(c.source == SourceName.FIXTURE for c in result["candidates"])
    assert all(c.prerequisites_met is True for c in result["candidates"])

    trace = result["trace"][0]
    assert "Found 3 modules" in trace.message
    assert "2 eligible" in trace.message
    assert "capped to 2" in trace.message


def test_module_node_uses_completed_modules_to_unlock_prereqs():
    catalogue = [_nusmods_module("CS3210", prereq_tree={"or": ["CS2100", "CS2106"]})]
    state = {"profile": _profile([CompletedModule(code="CS2106", title="x", units=4.0)])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = True
        result = module_agent.module_node(state)

    assert len(result["candidates"]) == 1
    assert result["candidates"][0].source == SourceName.NUSMODS


def test_module_node_handles_missing_profile():
    catalogue = [_nusmods_module("CS1010")]
    state: dict = {}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert len(result["candidates"]) == 1


def test_module_node_caps_at_max_candidates_scored():
    catalogue = [_nusmods_module(f"CS{i}") for i in range(module_agent.MAX_CANDIDATES_SCORED + 10)]
    state = {"profile": _profile([])}

    with patch.object(module_agent, "load_catalogue", return_value=catalogue), patch.object(
        module_agent, "CACHE_PATH"
    ) as mock_cache_path:
        mock_cache_path.exists.return_value = False
        result = module_agent.module_node(state)

    assert len(result["candidates"]) == module_agent.MAX_CANDIDATES_SCORED
