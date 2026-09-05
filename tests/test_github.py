"""Unit tests for W2.4 — src/tools/github.py.

requests.get is mocked throughout per the CLAUDE.md hard rule against calling
external APIs from a test.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

import src.tools.github as github
from src.state import CandidateKind, SourceName


def _raw_repo(**overrides) -> dict:
    defaults = dict(
        id=1001,
        full_name="example-org/raft-teaching-impl",
        html_url="https://github.com/example-org/raft-teaching-impl",
        description="A readable Raft consensus implementation in Go.",
        stargazers_count=1840,
        language="Go",
        open_issues_count=23,
        topics=["distributed-systems", "consensus", "raft"],
    )
    return {**defaults, **overrides}


def _response(items: list[dict]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"items": items, "total_count": len(items)}
    return response


def test_search_projects_success_returns_typed_candidates_no_event():
    with patch.object(github.requests, "get", return_value=_response([_raw_repo()])):
        candidates, event = github.search_projects("distributed systems")

    assert event is None
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == "github:1001"
    assert candidate.kind == CandidateKind.PROJECT
    assert candidate.source == SourceName.GITHUB
    assert candidate.title == "example-org/raft-teaching-impl"
    assert candidate.url == "https://github.com/example-org/raft-teaching-impl"
    assert candidate.time_cost_hours == github.TIME_COST_HOURS["project"]


def test_description_includes_language_stars_issues_and_topics():
    with patch.object(github.requests, "get", return_value=_response([_raw_repo()])):
        [candidate] = github.search_projects("q")[0]

    assert "Raft consensus" in candidate.description
    assert "Go" in candidate.description
    assert "1840 stars" in candidate.description
    assert "23 open issues" in candidate.description
    assert "distributed-systems" in candidate.description


def test_description_handles_missing_optional_fields():
    sparse = _raw_repo(description=None, language=None, open_issues_count=0, topics=[])
    with patch.object(github.requests, "get", return_value=_response([sparse])):
        [candidate] = github.search_projects("q")[0]

    assert candidate.description == "1840 stars."


def test_network_failure_retries_then_falls_back_to_fixture():
    with patch.object(
        github.requests, "get", side_effect=requests.ConnectionError("down")
    ) as mock_get:
        candidates, event = github.search_projects("distributed systems")

    assert mock_get.call_count == 1 + github.TOOL_RETRIES
    assert event is not None
    assert "used fixture" in event.message
    assert len(candidates) == 3  # data/fixtures/github_response.json has 3 entries
    assert all(c.source == SourceName.FIXTURE for c in candidates)


def test_empty_items_list_is_treated_as_failure_and_falls_back():
    with patch.object(github.requests, "get", return_value=_response([])):
        candidates, event = github.search_projects("no-matches-query")

    assert event is not None
    assert len(candidates) == 3
    assert all(c.source == SourceName.FIXTURE for c in candidates)


def test_http_error_status_falls_back():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("403 rate limited")
    with patch.object(github.requests, "get", return_value=response):
        candidates, event = github.search_projects("q")

    assert event is not None
    assert len(candidates) == 3


def test_github_token_from_environment_sent_as_bearer_header():
    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
        headers = github._headers()
    assert headers["Authorization"] == "Bearer ghp_test123"


def test_no_authorization_header_when_no_token_set():
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("GITHUB_TOKEN", None)
        headers = github._headers()
    assert "Authorization" not in headers
