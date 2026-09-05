"""Devpost hackathon tool — W2.3.

Returns small typed Candidate objects, never raw API JSON, per the CLAUDE.md hard
rule. Unlike nusmods.py's catalogue fetch, this is a genuine per-run live call - the
query is gap-driven and changes every run - so it gets the full hard-rule treatment:
timeout, one retry, then a fixture fallback that writes a TraceEvent recording that
the fallback fired.

Field mapping follows W2.0's verify_devpost.py findings: id/title/url map directly,
description is built (no single raw field covers it), and deadline comes from
`submission_period_dates`, a free-text range like "Oct 03 - Oct 05, 2026" - parsed
here as the trailing date, i.e. the submission close.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests

from src.config import TIME_COST_HOURS, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS
from src.state import Candidate, CandidateKind, SourceName, TraceEvent, TraceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "devpost_response.json"
SEARCH_URL = "https://devpost.com/api/hackathons"

_MONTHS = {
    name: i
    for i, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}
# The day+year of the trailing end of a range like "Oct 03 - Oct 05, 2026" - the
# submission close, which is the only date worth surfacing as Candidate.deadline.
_DAY_YEAR_RE = re.compile(r"(\d{1,2}),\s*(\d{4})")
_MONTH_RE = re.compile(r"[A-Za-z]{3}")


def _parse_deadline(text: str) -> date | None:
    """Handles same-month ranges like "Sep 03 - 06, 2026", where Devpost drops the
    second month entirely (live-observed, not in the fixture) - the day/year come
    from the trailing segment, but the month falls back to the first segment's.
    """
    if not text:
        return None
    segments = [segment.strip() for segment in text.split("-")]
    last_segment = segments[-1]

    day_year = _DAY_YEAR_RE.search(last_segment)
    if not day_year:
        return None
    day, year = (int(group) for group in day_year.groups())

    month_match = _MONTH_RE.search(last_segment) or _MONTH_RE.search(segments[0])
    if not month_match:
        return None
    month = _MONTHS.get(month_match.group(0).title())
    if month is None:
        return None

    try:
        return date(year, month, day)
    except ValueError:
        return None


def _build_description(raw: dict) -> str:
    parts = []
    org = raw.get("organization_name")
    if org:
        parts.append(f"Hosted by {org}.")
    themes = [t.get("name") for t in raw.get("themes", []) if t.get("name")]
    if themes:
        parts.append("Themes: " + ", ".join(themes) + ".")
    location = (raw.get("displayed_location") or {}).get("location")
    if location:
        parts.append(f"Location: {location}.")
    prize = raw.get("prize_amount")
    if prize:
        parts.append(f"Prize: {prize}.")
    return " ".join(parts)


def _to_candidate(raw: dict, source: SourceName) -> Candidate:
    return Candidate(
        id=f"devpost:{raw['id']}",
        kind=CandidateKind.HACKATHON,
        source=source,
        title=raw.get("title", ""),
        description=_build_description(raw),
        url=raw.get("url"),
        deadline=_parse_deadline(raw.get("submission_period_dates", "")),
        time_cost_hours=TIME_COST_HOURS["hackathon"],
    )


def _load_fixture() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text())
    return payload.get("hackathons") or []


def search_hackathons(query: str) -> tuple[list[Candidate], TraceEvent | None]:
    """Search Devpost for `query`. Returns (candidates, fallback_event) - the event
    is None on a successful live search, and explains why the fixture was used
    otherwise. Never raises: a dead endpoint degrades to fixture data, not a crash.
    """
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = requests.get(
                SEARCH_URL, params={"search": query}, timeout=TOOL_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            hackathons = response.json().get("hackathons") or []
            if not hackathons:
                raise ValueError(f"no hackathons returned for query {query!r}")
            return [_to_candidate(h, SourceName.DEVPOST) for h in hackathons], None
        except (requests.RequestException, ValueError) as exc:
            last_error = exc

    candidates = [_to_candidate(h, SourceName.FIXTURE) for h in _load_fixture()]
    event = TraceEvent(
        kind=TraceKind.OBSERVED,
        agent="Event Agent",
        message="Devpost search failed, used fixture hackathons instead",
        detail=str(last_error),
    )
    return candidates, event
