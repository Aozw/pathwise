"""Event Agent node.

STUB for W1.2 (graph skeleton): reads the committed Devpost fixture directly and maps
it straight onto Candidate. The real Devpost tool call, with its timeout/retry/fixture
fallback, lands in W2.3; wiring it into this node is W2.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.state import Candidate, CandidateKind, RunState, SourceName, TraceEvent, TraceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "devpost_response.json"


def event_node(state: RunState) -> dict:
    payload = json.loads(FIXTURE_PATH.read_text())
    hackathons = payload.get("hackathons", [])
    candidates = [
        Candidate(
            id=f"devpost:{hackathon['id']}",
            kind=CandidateKind.HACKATHON,
            source=SourceName.FIXTURE,
            title=hackathon["title"],
            description=", ".join(theme["name"] for theme in hackathon.get("themes", [])),
            url=hackathon.get("url"),
        )
        for hackathon in hackathons
    ]
    return {
        "candidates": candidates,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Event Agent",
                message=f"Found {len(candidates)} hackathons from fixture data",
                detail="Stub: reads data/fixtures/devpost_response.json directly. Real "
                "Devpost tool call lands in W2.3, wired in here by W2.5.",
            )
        ],
    }
