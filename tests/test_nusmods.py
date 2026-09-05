"""Unit tests for W2.1 — src/tools/nusmods.py.

fetch_module_catalogue is the only network-touching function here; it is mocked
throughout per the CLAUDE.md hard rule against calling external APIs from a test.
load_catalogue and refresh_cache are pure file I/O once given a path, so they are
tested against tmp_path fixtures instead of the real data/cache and data/fixtures.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import src.tools.nusmods as nusmods


def _raw_module(**overrides) -> dict:
    defaults = dict(
        moduleCode="CS3210",
        title="Parallel Computing",
        description="Parallel architectures and algorithms.",
        moduleCredit="4",
        department="Computer Science",
    )
    return {**defaults, **overrides}


def test_load_catalogue_prefers_cache_over_fixture(tmp_path):
    cache_path = tmp_path / "cache.json"
    fixture_path = tmp_path / "fixture.json"
    cache_path.write_text(json.dumps([_raw_module(moduleCode="CS3210")]))
    fixture_path.write_text(json.dumps([_raw_module(moduleCode="CS1101S")]))

    with patch.object(nusmods, "CACHE_PATH", cache_path), patch.object(
        nusmods, "FIXTURE_PATH", fixture_path
    ):
        modules = nusmods.load_catalogue()

    assert [m.code for m in modules] == ["CS3210"]


def test_load_catalogue_falls_back_to_fixture_when_cache_missing(tmp_path):
    cache_path = tmp_path / "cache.json"  # never created
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps([_raw_module(moduleCode="CS1101S")]))

    with patch.object(nusmods, "CACHE_PATH", cache_path), patch.object(
        nusmods, "FIXTURE_PATH", fixture_path
    ):
        modules = nusmods.load_catalogue()

    assert [m.code for m in modules] == ["CS1101S"]


def test_load_catalogue_parses_fields_into_nusmods_module(tmp_path):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps([_raw_module(prereqTree={"or": ["CS2100", "CS2106"]})])
    )

    with patch.object(nusmods, "CACHE_PATH", tmp_path / "no-cache.json"), patch.object(
        nusmods, "FIXTURE_PATH", fixture_path
    ):
        [module] = nusmods.load_catalogue()

    assert module.code == "CS3210"
    assert module.title == "Parallel Computing"
    assert module.units == 4.0
    assert module.department == "Computer Science"
    assert module.prereq_tree == {"or": ["CS2100", "CS2106"]}


def test_load_catalogue_handles_missing_module_credit(tmp_path):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps([_raw_module(moduleCredit=None)]))

    with patch.object(nusmods, "CACHE_PATH", tmp_path / "no-cache.json"), patch.object(
        nusmods, "FIXTURE_PATH", fixture_path
    ):
        [module] = nusmods.load_catalogue()

    assert module.units is None


def test_fetch_module_catalogue_returns_parsed_json_on_success():
    response = MagicMock()
    response.json.return_value = [_raw_module()]
    response.raise_for_status.return_value = None

    with patch.object(nusmods.requests, "get", return_value=response) as mock_get:
        result = nusmods.fetch_module_catalogue(academic_year="2025-2026")

    assert result == [_raw_module()]
    mock_get.assert_called_once()
    assert "2025-2026" in mock_get.call_args.args[0]


def test_fetch_module_catalogue_retries_once_then_raises():
    with patch.object(
        nusmods.requests, "get", side_effect=requests.ConnectionError("down")
    ) as mock_get:
        with pytest.raises(RuntimeError):
            nusmods.fetch_module_catalogue()

    assert mock_get.call_count == 1 + nusmods.TOOL_RETRIES


def test_refresh_cache_writes_fetched_payload_to_cache_path(tmp_path):
    cache_path = tmp_path / "nested" / "cache.json"
    payload = [_raw_module()]

    with patch.object(nusmods, "CACHE_PATH", cache_path), patch.object(
        nusmods, "fetch_module_catalogue", return_value=payload
    ):
        result_path = nusmods.refresh_cache()

    assert result_path == cache_path
    assert json.loads(cache_path.read_text()) == payload
