"""Unit tests for W2.3 — src/tools/devpost.py.

requests.get is mocked throughout per the CLAUDE.md hard rule against calling
external APIs from a test.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import requests

import src.tools.devpost as devpost
from src.state import CandidateKind, SourceName


def _raw_hackathon(**overrides) -> dict:
    defaults = dict(
        id="hack-abc",
        title="CloudScale Asia 2026",
        url="https://cloudscale-asia.devpost.com",
        displayed_location={"location": "Singapore"},
        open_state="open",
        submission_period_dates="Oct 03 - Oct 05, 2026",
        themes=[{"name": "Cloud Computing"}, {"name": "DevOps"}],
        organization_name="CloudScale Org",
        prize_amount="SGD 10,000",
    )
    return {**defaults, **overrides}


def _response(hackathons: list[dict]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"hackathons": hackathons}
    return response


def test_search_hackathons_success_returns_typed_candidates_no_event():
    with patch.object(devpost.requests, "get", return_value=_response([_raw_hackathon()])):
        candidates, event = devpost.search_hackathons("singapore")

    assert event is None
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == "devpost:hack-abc"
    assert candidate.kind == CandidateKind.HACKATHON
    assert candidate.source == SourceName.DEVPOST
    assert candidate.title == "CloudScale Asia 2026"
    assert candidate.url == "https://cloudscale-asia.devpost.com"
    assert candidate.deadline == date(2026, 10, 5)
    assert candidate.time_cost_hours == devpost.TIME_COST_HOURS["hackathon"]


def test_description_includes_org_themes_location_and_prize():
    with patch.object(devpost.requests, "get", return_value=_response([_raw_hackathon()])):
        [candidate] = devpost.search_hackathons("singapore")[0]

    assert "CloudScale Org" in candidate.description
    assert "Cloud Computing" in candidate.description
    assert "Singapore" in candidate.description
    assert "SGD 10,000" in candidate.description


def test_deadline_parses_end_of_range_when_year_stated_once():
    with patch.object(
        devpost.requests,
        "get",
        return_value=_response(
            [_raw_hackathon(submission_period_dates="Sep 26 - Oct 12, 2026")]
        ),
    ):
        [candidate] = devpost.search_hackathons("q")[0]
    assert candidate.deadline == date(2026, 10, 12)


def test_deadline_handles_same_month_range_with_dropped_second_month():
    # Live-observed shape: "Sep 03 - 06, 2026" - Devpost drops the repeated month.
    with patch.object(
        devpost.requests,
        "get",
        return_value=_response(
            [_raw_hackathon(submission_period_dates="Sep 03 - 06, 2026")]
        ),
    ):
        [candidate] = devpost.search_hackathons("q")[0]
    assert candidate.deadline == date(2026, 9, 6)


def test_deadline_none_when_unparseable():
    with patch.object(
        devpost.requests,
        "get",
        return_value=_response([_raw_hackathon(submission_period_dates="Rolling")]),
    ):
        [candidate] = devpost.search_hackathons("q")[0]
    assert candidate.deadline is None


def test_network_failure_retries_then_falls_back_to_fixture():
    with patch.object(
        devpost.requests, "get", side_effect=requests.ConnectionError("down")
    ) as mock_get:
        candidates, event = devpost.search_hackathons("singapore")

    assert mock_get.call_count == 1 + devpost.TOOL_RETRIES
    assert event is not None
    assert "used fixture" in event.message
    assert len(candidates) == 3  # data/fixtures/devpost_response.json has 3 entries
    assert all(c.source == SourceName.FIXTURE for c in candidates)


def test_empty_hackathons_list_is_treated_as_failure_and_falls_back():
    with patch.object(devpost.requests, "get", return_value=_response([])):
        candidates, event = devpost.search_hackathons("no-matches-query")

    assert event is not None
    assert len(candidates) == 3
    assert all(c.source == SourceName.FIXTURE for c in candidates)


def test_http_error_status_falls_back():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("500")
    with patch.object(devpost.requests, "get", return_value=response):
        candidates, event = devpost.search_hackathons("q")

    assert event is not None
    assert len(candidates) == 3
