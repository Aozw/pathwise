"""Project Agent node.

STUB for W1.2 (graph skeleton): reads the committed GitHub Search fixture directly and
maps it straight onto Candidate. The real GitHub Search tool call, with its
timeout/retry/fixture fallback, lands in W2.4; wiring it into this node is W2.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.state import Candidate, CandidateKind, RunState, SourceName, TraceEvent, TraceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "github_response.json"


def project_node(state: RunState) -> dict:
    payload = json.loads(FIXTURE_PATH.read_text())
    items = payload.get("items", [])
    candidates = [
        Candidate(
            id=f"github:{item['id']}",
            kind=CandidateKind.PROJECT,
            source=SourceName.FIXTURE,
            title=item["full_name"],
            description=item.get("description") or "",
            url=item.get("html_url"),
        )
        for item in items
    ]
    return {
        "candidates": candidates,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Project Agent",
                message=f"Found {len(candidates)} repos from fixture data",
                detail="Stub: reads data/fixtures/github_response.json directly. Real "
                "GitHub Search tool call lands in W2.4, wired in here by W2.5.",
            )
        ],
    }
