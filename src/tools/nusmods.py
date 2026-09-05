"""NUSMods module catalogue — W2.1.

`moduleInformation.json` is NUSMods' single bulk file covering every module in the
academic year (description, credits, prerequisite tree, ~6000 entries, several MB).
PLAN.md section 9 is explicit: "Cache the NUSMods catalogue once. Never fetch it per
run." So this file splits into two paths that are never called from the same place:

  - refresh_cache() — a live network call. Run manually and offline, e.g.
    `python -m src.tools.nusmods`, whenever the cached catalogue needs updating
    (in practice: never during the hackathon). Writes the raw response to
    data/cache/ (gitignored — this file is a multi-MB derived artifact, not
    something to commit). Not reachable from the graph.
  - load_catalogue() — what the Module Agent (W2.5) calls at runtime. Reads
    data/cache/ if refresh_cache() has ever been run locally, otherwise falls back
    to the small trimmed sample committed at data/fixtures/nusmods_module_list.json.
    Pure file I/O, no network, so a run never blocks on or pays for this source.

Per the CLAUDE.md hard rule "tools return small typed objects, never raw API JSON",
load_catalogue() returns NUSModsModule, not the raw dict: only the fields W2.2
(eligibility) and W2.5 (Candidate mapping) actually need. Raw fields like timetable
data, workload arrays and add-on programme info are dropped here so they never reach
the model's context window later.

W2.2 needs to know one thing this file discovered against the live endpoint: neither
NUSMods bulk file (moduleInformation.json here, or the larger moduleInfo.json) carries
a structured prereqTree for any module - live-checked, 0/7138 and 0/20560 respectively.
Only `prerequisite`, a free-text sentence, is present in bulk. The structured tree
NUSModsModule.prereq_tree exposes only exists on the per-module detail endpoint
(`{base}/{year}/modules/{code}.json`, the shape data/fixtures/nusmods_module.json
mirrors), fetched one module at a time. So `load_catalogue()` leaves `prereq_tree`
as None for everything except entries read from the fixture fallback. W2.2 will need
its own lazy, per-candidate detail fetch (small, bounded by the eligible/shortlisted
set, not the full catalogue) rather than assuming this file's bulk cache carries it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from src.config import NUSMODS_ACADEMIC_YEAR, NUSMODS_BASE_URL, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = REPO_ROOT / "data" / "cache" / "nusmods_module_info.json"
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "nusmods_module_list.json"


class NUSModsModule(BaseModel):
    """This tool's own typed shape for one module — not the raw API JSON.

    `prereq_tree` stays as a nested dict/str/None rather than being flattened here:
    NUSMods' prerequisite trees are irregular ({"and": [...]}, {"or": [...]}, nested
    combinations, or a bare module code), and W2.2 owns turning that into
    `is_eligible()`. Parsing it twice would be wasted work and a chance to disagree
    with itself. In practice this is always None from load_catalogue()'s live path -
    see the module docstring; only the fixture fallback and a future per-module
    detail fetch populate it.
    """

    code: str
    title: str
    description: str = ""
    units: float | None = None
    department: str = ""
    prereq_tree: Any | None = None


def _parse(raw_modules: list[dict]) -> list[NUSModsModule]:
    parsed = []
    for module in raw_modules:
        credit = module.get("moduleCredit")
        parsed.append(
            NUSModsModule(
                code=module["moduleCode"],
                title=module.get("title", ""),
                description=module.get("description", ""),
                units=float(credit) if credit not in (None, "") else None,
                department=module.get("department", ""),
                prereq_tree=module.get("prereqTree"),
            )
        )
    return parsed


def fetch_module_catalogue(academic_year: str = NUSMODS_ACADEMIC_YEAR) -> list[dict]:
    """Live GET of the full moduleInformation.json dump. Never called at run time —
    see the module docstring. One retry per config.TOOL_RETRIES, then raises: this is
    an offline maintenance operation with a human watching, not a run-time path that
    needs a silent fallback.
    """
    url = f"{NUSMODS_BASE_URL}/{academic_year}/moduleInformation.json"
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = requests.get(url, timeout=TOOL_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"NUSMods catalogue fetch failed: {url}") from last_error


def refresh_cache(academic_year: str = NUSMODS_ACADEMIC_YEAR) -> Path:
    """Fetch live and write the raw catalogue to data/cache/. Run this by hand
    (`python -m src.tools.nusmods`) when the cache needs updating, not from the graph.
    """
    raw_modules = fetch_module_catalogue(academic_year)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(raw_modules))
    return CACHE_PATH


def load_catalogue() -> list[NUSModsModule]:
    """Runtime read: data/cache/ if refresh_cache() has populated it, else the
    committed fixture. Never touches the network.
    """
    path = CACHE_PATH if CACHE_PATH.exists() else FIXTURE_PATH
    raw_modules = json.loads(path.read_text())
    return _parse(raw_modules)


if __name__ == "__main__":
    path = refresh_cache()
    print(f"Cached NUSMods catalogue to {path}")
