"""Module Agent node.

STUB for W1.2 (graph skeleton): reads the committed NUSMods fixture directly and maps
it straight onto Candidate, no eligibility filter and no semantic shortlist. The real
NUSMods fetch/cache (W2.1), prerequisite eligibility filter (W2.2) and the shortlist
call before returning (W2.5) all replace this.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.state import Candidate, CandidateKind, RunState, SourceName, TraceEvent, TraceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "nusmods_module_list.json"


def module_node(state: RunState) -> dict:
    modules = json.loads(FIXTURE_PATH.read_text())
    candidates = [
        Candidate(
            id=f"nusmods:{module['moduleCode']}",
            kind=CandidateKind.MODULE,
            source=SourceName.FIXTURE,
            title=f"{module['moduleCode']} {module['title']}",
            description=module.get("description", ""),
            units=float(module["moduleCredit"]) if module.get("moduleCredit") else None,
        )
        for module in modules
    ]
    return {
        "candidates": candidates,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Module Agent",
                message=f"Found {len(candidates)} modules from fixture data",
                detail="Stub: reads data/fixtures/nusmods_module_list.json directly, no "
                "eligibility filter or shortlist yet. Real tool call lands in W2.1-W2.5.",
            )
        ],
    }
