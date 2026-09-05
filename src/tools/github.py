"""GitHub Search tool — W2.4.

Same shape as devpost.py: returns small typed Candidate objects, never raw API
JSON, with timeout + one retry + fixture fallback that writes a TraceEvent. Genuine
per-run live call - the query is gap-driven - so it gets the full hard-rule
treatment.

Unauthenticated GitHub Search is rate-limited to 10 requests/minute, plenty for a
demo. If a GITHUB_TOKEN is present in the environment (config.py already loads
.env, so this picks it up the same way), it's sent as a bearer token for the
higher authenticated rate limit - optional, never required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from src.config import TIME_COST_HOURS, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS
from src.state import Candidate, CandidateKind, SourceName, TraceEvent, TraceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "github_response.json"
SEARCH_URL = "https://api.github.com/search/repositories"

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "pathwise-hackathon-bot",
}


def _headers() -> dict[str, str]:
    headers = dict(_HEADERS)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _build_description(raw: dict) -> str:
    parts = []
    description = raw.get("description")
    if description:
        parts.append(description.strip().rstrip(".") + ".")
    language = raw.get("language")
    if language:
        parts.append(f"Language: {language}.")
    stars = raw.get("stargazers_count")
    if stars is not None:
        parts.append(f"{stars} stars.")
    open_issues = raw.get("open_issues_count")
    if open_issues:
        parts.append(f"{open_issues} open issues.")
    topics = raw.get("topics") or []
    if topics:
        parts.append("Topics: " + ", ".join(topics) + ".")
    return " ".join(parts)


def _to_candidate(raw: dict, source: SourceName) -> Candidate:
    return Candidate(
        id=f"github:{raw['id']}",
        kind=CandidateKind.PROJECT,
        source=source,
        title=raw.get("full_name", ""),
        description=_build_description(raw),
        url=raw.get("html_url"),
        time_cost_hours=TIME_COST_HOURS["project"],
    )


def _load_fixture() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text())
    return payload.get("items") or []


def search_projects(query: str) -> tuple[list[Candidate], TraceEvent | None]:
    """Search GitHub repositories for `query`. Returns (candidates, fallback_event) -
    the event is None on a successful live search, and explains why the fixture was
    used otherwise. Never raises: a dead/rate-limited endpoint degrades to fixture
    data, not a crash.
    """
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = requests.get(
                SEARCH_URL,
                params={"q": query, "sort": "stars", "order": "desc"},
                headers=_headers(),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
            if not items:
                raise ValueError(f"no repositories returned for query {query!r}")
            return [_to_candidate(item, SourceName.GITHUB) for item in items], None
        except (requests.RequestException, ValueError) as exc:
            last_error = exc

    candidates = [_to_candidate(item, SourceName.FIXTURE) for item in _load_fixture()]
    event = TraceEvent(
        kind=TraceKind.OBSERVED,
        agent="Project Agent",
        message="GitHub search failed, used fixture projects instead",
        detail=str(last_error),
    )
    return candidates, event
