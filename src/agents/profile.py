"""Profile ingestion — W3.1, the transcript parser.

Turns an uploaded NUS transcript (plain text) into a `StudentProfile`. The primary
path is one Bedrock call forced into a structured schema, because real transcripts
vary in layout far more than the committed fixture does. The fallback is a pure
regex parser of the fixed-column format NUS actually emits: it needs no network, so
it doubles as the thing CI exercises and as the fixture fallback the CLAUDE.md hard
rule requires. Either way the extracted fields converge through `_to_profile`, so
there is exactly one place that knows how to build a `StudentProfile`.

`target_role` is not in a transcript — the student picks it in the UI — so it is a
parameter here, validated against config.ROLE_DIMENSION_WEIGHTS. `evidence` stays
empty: it comes from the resume (W3.2), not the transcript.

Failure handling matches planner.py: boto retries disabled, one explicit retry, then
the deterministic parser runs and a TraceEvent records that the fallback fired.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, Field, ValidationError

from src.config import (
    AWS_REGION,
    DEFAULT_ROLE,
    MODEL_HAIKU,
    ROLE_DIMENSION_WEIGHTS,
    TOOL_RETRIES,
    TOOL_TIMEOUT_SECONDS,
)
from src.state import CompletedModule, StudentProfile, TraceEvent, TraceKind

_TOOL_NAME = "record_profile"

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Student full name, normal capitalisation."},
        "year": {
            "type": "integer",
            "description": "Current year of study, 1-6, inferred from the candidature "
            "start year and the most recent semester listed.",
        },
        "major": {"type": "string", "description": "Primary major, e.g. 'Computer Science'."},
        "units_completed": {"type": "number"},
        "units_required": {
            "type": "number",
            "description": "Total units the programme requires. Use 160 if not stated.",
        },
        "completed_modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "e.g. 'CS2106'"},
                    "title": {"type": "string"},
                    "units": {"type": "number"},
                    "grade": {
                        "type": "string",
                        "description": "Letter grade or S/U. Omit if in progress.",
                    },
                },
                "required": ["code", "title", "units"],
            },
        },
    },
    "required": ["name", "year", "major", "units_completed", "completed_modules"],
}

# boto's own retries are off (max_attempts=1); the loop in _call_bedrock is explicit
# so a final failure is observable and can hand control to the deterministic parser.
_BOTO_CONFIG = BotoConfig(
    connect_timeout=TOOL_TIMEOUT_SECONDS,
    read_timeout=TOOL_TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)

_client: Any = None


def _bedrock() -> Any:
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=_BOTO_CONFIG)
    return _client


# ---------------------------------------------------------------------------
# Extracted shape. Both the model path and the regex path produce this, and only
# _to_profile turns it into a StudentProfile, so the two paths cannot drift.
# ---------------------------------------------------------------------------


class _ExtractedModule(BaseModel):
    code: str
    title: str
    units: float
    grade: str | None = None


class _Extracted(BaseModel):
    name: str
    year: int = Field(ge=1, le=6)
    major: str
    units_completed: float = 0.0
    units_required: float = 160.0
    completed_modules: list[_ExtractedModule] = Field(default_factory=list)


def _to_profile(extracted: _Extracted, target_role: str) -> StudentProfile:
    if target_role not in ROLE_DIMENSION_WEIGHTS:
        raise ValueError(
            f"target_role {target_role!r} is not a key in config.ROLE_DIMENSION_WEIGHTS"
        )
    return StudentProfile(
        name=extracted.name,
        year=extracted.year,
        major=extracted.major,
        target_role=target_role,
        completed_modules=[
            CompletedModule(code=m.code, title=m.title, units=m.units, grade=m.grade)
            for m in extracted.completed_modules
        ],
        units_completed=extracted.units_completed,
        units_required=extracted.units_required,
        evidence=[],  # from the resume, not the transcript — W3.2
    )


# ---------------------------------------------------------------------------
# Model path.
# ---------------------------------------------------------------------------


def _call_bedrock(transcript_text: str) -> _Extracted:
    prompt = (
        "Extract the student profile from this NUS transcript. Include every module "
        "that has a final grade; exclude modules still in progress. Infer the year of "
        "study from the candidature start year and the latest semester shown. Call the "
        f"{_TOOL_NAME} tool with the result.\n\n"
        f"TRANSCRIPT:\n{transcript_text}"
    )
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = _bedrock().converse(
                modelId=MODEL_HAIKU,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": _TOOL_NAME,
                                "description": "Record the parsed student profile.",
                                "inputSchema": {"json": _TOOL_SCHEMA},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": _TOOL_NAME}},
                },
                inferenceConfig={"temperature": 0, "maxTokens": 2000},
            )
            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    return _Extracted.model_validate(block["toolUse"]["input"])
            raise ValueError("model did not call the record_profile tool")
        except (ClientError, BotoCoreError, ValidationError, ValueError, KeyError) as exc:
            last_error = exc
    raise RuntimeError(f"transcript Bedrock call failed after retry: {last_error}") from last_error


# ---------------------------------------------------------------------------
# Deterministic path. Parses the fixed-column layout NUS exports. Pure, no I/O.
# ---------------------------------------------------------------------------

_MODULE_CODE = re.compile(r"^[A-Z]{2,4}\d{4}[A-Z]?$")
_GRADE = re.compile(r"^(?:[A-D][+-]?|F|S|U|CS|CU)$")
_AY_HEADER = re.compile(r"^AY(\d{4})/\d{4}\s+(?:SEMESTER|SPECIAL)", re.IGNORECASE)


def _deterministic_extract(transcript_text: str) -> _Extracted:
    lines = [line.rstrip() for line in transcript_text.splitlines()]

    name = "Unknown Student"
    major = "Unknown"
    units_completed = 0.0
    units_required = 160.0
    candidature_start: int | None = None
    latest_semester_year: int | None = None
    modules: list[_ExtractedModule] = []

    for line in lines:
        stripped = line.strip()

        if stripped.lower().startswith("student:"):
            # Transcripts shout the name in caps; title-case it for the UI.
            name = stripped.split(":", 1)[1].strip().title() or name
            continue
        if stripped.lower().startswith("programme:"):
            programme = stripped.split(":", 1)[1].strip()
            # "Bachelor of ... in Computer Science" -> "Computer Science"
            major = programme.split(" in ")[-1].strip() if " in " in programme else programme
            continue
        if stripped.lower().startswith("candidature:"):
            match = re.search(r"AY(\d{4})/\d{4}", stripped)
            if match:
                candidature_start = int(match.group(1))
            continue
        units_match = re.search(r"units completed:\s*([\d.]+)\s+of\s+([\d.]+)", stripped, re.IGNORECASE)
        if units_match:
            units_completed = float(units_match.group(1))
            units_required = float(units_match.group(2))
            continue
        ay_match = _AY_HEADER.match(stripped)
        if ay_match:
            year = int(ay_match.group(1))
            latest_semester_year = max(latest_semester_year or year, year)
            continue

        # Module rows are code / title / units / grade separated by runs of spaces.
        parts = re.split(r"\s{2,}", stripped)
        if len(parts) in (3, 4) and _MODULE_CODE.match(parts[0]):
            try:
                units = float(parts[2])
            except ValueError:
                continue
            grade = parts[3].strip() if len(parts) == 4 else None
            if grade is not None and not _GRADE.match(grade):
                grade = None  # "IP", "W" etc. — treat as no final grade recorded
            modules.append(
                _ExtractedModule(code=parts[0], title=parts[1].strip(), units=units, grade=grade)
            )

    year = _infer_year(candidature_start, latest_semester_year, units_completed)
    return _Extracted(
        name=name,
        year=year,
        major=major,
        units_completed=units_completed,
        units_required=units_required,
        completed_modules=modules,
    )


def _infer_year(start: int | None, latest: int | None, units_completed: float) -> int:
    """Prefer calendar evidence; fall back to ~32 units a year. Clamped to 1..6."""
    if start is not None and latest is not None:
        return max(1, min(6, latest - start + 1))
    return max(1, min(6, int(units_completed // 32) + 1))


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


@dataclass
class TranscriptParse:
    profile: StudentProfile
    trace: list[TraceEvent]
    used_fallback: bool


def parse_transcript(transcript_text: str, target_role: str = DEFAULT_ROLE) -> TranscriptParse:
    """Parse a transcript into a StudentProfile, falling back to the regex parser."""
    if target_role not in ROLE_DIMENSION_WEIGHTS:
        raise ValueError(
            f"target_role {target_role!r} is not a key in config.ROLE_DIMENSION_WEIGHTS"
        )

    used_fallback = False
    fallback_reason: str | None = None
    try:
        extracted = _call_bedrock(transcript_text)
    except RuntimeError as exc:
        extracted = _deterministic_extract(transcript_text)
        used_fallback = True
        fallback_reason = str(exc)

    profile = _to_profile(extracted, target_role)

    trace: list[TraceEvent] = []
    if used_fallback:
        trace.append(
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Profile Agent",
                message="Transcript parsed by the deterministic fallback parser",
                detail=fallback_reason,
            )
        )
    trace.append(
        TraceEvent(
            kind=TraceKind.OBSERVED,
            agent="Profile Agent",
            message=f"Parsed transcript for {profile.name}: {len(profile.completed_modules)} "
            f"modules, {profile.units_completed:.0f}/{profile.units_required:.0f} units, "
            f"year {profile.year}",
        )
    )
    return TranscriptParse(profile=profile, trace=trace, used_fallback=used_fallback)


if __name__ == "__main__":
    # Manual check against the fixture. Not a pytest test — CLAUDE.md bars those from
    # touching Bedrock. Run with credentials to exercise the model path:
    #   python -m src.agents.profile
    from pathlib import Path

    text = (Path(__file__).parents[2] / "data" / "fixtures" / "transcript.txt").read_text()
    result = parse_transcript(text)
    print(f"used_fallback={result.used_fallback}")
    print(json.dumps(result.profile.model_dump(mode="json"), indent=2))
