"""Profile ingestion — W3.1 transcript parser and W3.2 resume parser.

`parse_transcript` turns an NUS transcript into a `StudentProfile` (name, year,
major, completed modules, units). `parse_resume` turns a resume into a list of
`Evidence` - things the student has demonstrably done, each tagged with the
readiness `Dimension` it demonstrates. `build_profile` runs both and returns one
`StudentProfile` with the evidence attached.

Every parser has the same shape: one Bedrock call forced into a structured schema
as the primary path, and a pure deterministic parser as the fallback - no network,
so it doubles as the thing CI exercises and the fixture fallback the CLAUDE.md hard
rule requires. Each pair converges through one builder (`_to_profile`,
`_to_evidence`) so there is exactly one place that knows the target shape.

`target_role` is not in a transcript - the student picks it in the UI - so it is a
parameter, validated against config.ROLE_DIMENSION_WEIGHTS.

`Evidence.dimension` is what `scoring.redundancy_penalty` matches on (a candidate
that closes gaps in a dimension the student already has evidence in scores lower);
`Evidence.label` is a short readable skill phrase for the UI and the planner prompt.

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
from src.state import (
    CompletedModule,
    Dimension,
    Evidence,
    StudentProfile,
    TraceEvent,
    TraceKind,
)

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


# ---------------------------------------------------------------------------
# W3.2 - resume parser. Produces Evidence, tagged by readiness Dimension.
# ---------------------------------------------------------------------------

_RESUME_TOOL_NAME = "record_evidence"

_DIMENSION_VALUES = [dimension.value for dimension in Dimension]

_RESUME_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": {
            "type": "array",
            "description": "One entry per distinct, concrete thing the student has "
            "demonstrably done. Skip aspirational or coursework-only lines unless the "
            "resume shows the skill was actually applied.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Short lowercase skill phrase, e.g. 'rest api', "
                        "'relational databases', 'teaching'. Two or three words.",
                    },
                    "dimension": {
                        "type": "string",
                        "enum": _DIMENSION_VALUES,
                        "description": "programming = writing application code and APIs; "
                        "systems = OS, networks, concurrency, distributed systems; "
                        "data = databases, pipelines, ML, analytics; "
                        "tooling = git, containers, CI/CD, testing, cloud infra; "
                        "communication = teaching, writing, presenting, leading.",
                    },
                    "source_text": {
                        "type": "string",
                        "description": "The resume line this came from, copied verbatim.",
                    },
                },
                "required": ["label", "dimension", "source_text"],
            },
        }
    },
    "required": ["evidence"],
}


class _ExtractedEvidence(BaseModel):
    label: str
    dimension: Dimension
    source_text: str


class _ResumeExtracted(BaseModel):
    evidence: list[_ExtractedEvidence] = Field(default_factory=list)


def _to_evidence(extracted: _ResumeExtracted) -> list[Evidence]:
    """Normalise and de-duplicate. `redundancy_penalty` works on the set of
    dimensions, so a repeated (label, dimension) pair only adds noise to the UI.
    """
    seen: set[tuple[str, Dimension]] = set()
    evidence: list[Evidence] = []
    for item in extracted.evidence:
        label = item.label.strip().lower()
        key = (label, item.dimension)
        if not label or key in seen:
            continue
        seen.add(key)
        evidence.append(
            Evidence(label=label, dimension=item.dimension, source_text=item.source_text.strip())
        )
    return evidence


def _call_resume_bedrock(resume_text: str) -> _ResumeExtracted:
    prompt = (
        "Extract the skills this student has demonstrably applied from the resume "
        "below. One evidence entry per distinct skill, each tagged with the readiness "
        f"dimension it demonstrates. Call the {_RESUME_TOOL_NAME} tool with the result.\n\n"
        f"RESUME:\n{resume_text}"
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
                                "name": _RESUME_TOOL_NAME,
                                "description": "Record the evidence extracted from a resume.",
                                "inputSchema": {"json": _RESUME_TOOL_SCHEMA},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": _RESUME_TOOL_NAME}},
                },
                inferenceConfig={"temperature": 0, "maxTokens": 2000},
            )
            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    return _ResumeExtracted.model_validate(block["toolUse"]["input"])
            raise ValueError("model did not call the record_evidence tool")
        except (ClientError, BotoCoreError, ValidationError, ValueError, KeyError) as exc:
            last_error = exc
    raise RuntimeError(f"resume Bedrock call failed after retry: {last_error}") from last_error


# Word-boundary keyword -> (label, dimension). Ordered roughly specific-first; every
# match on a line is emitted, then _to_evidence de-duplicates. This is the fixture
# fallback and the CI-testable path, not a claim to parse arbitrary prose well.
_RESUME_KEYWORDS: list[tuple[str, str, Dimension]] = [
    ("rest api", "rest api", Dimension.PROGRAMMING),
    ("flask", "web backend", Dimension.PROGRAMMING),
    ("spring boot", "web backend", Dimension.PROGRAMMING),
    ("django", "web backend", Dimension.PROGRAMMING),
    ("react", "frontend development", Dimension.PROGRAMMING),
    ("flutter", "mobile development", Dimension.PROGRAMMING),
    ("postgresql", "relational databases", Dimension.DATA),
    ("mysql", "relational databases", Dimension.DATA),
    ("sql", "sql", Dimension.DATA),
    ("firebase", "cloud data stores", Dimension.DATA),
    ("machine learning", "machine learning", Dimension.DATA),
    ("data pipeline", "data pipelines", Dimension.DATA),
    ("pytest", "automated testing", Dimension.TOOLING),
    ("unit test", "automated testing", Dimension.TOOLING),
    ("test coverage", "automated testing", Dimension.TOOLING),
    ("docker", "containers", Dimension.TOOLING),
    ("kubernetes", "container orchestration", Dimension.TOOLING),
    ("git", "version control", Dimension.TOOLING),
    ("ci/cd", "ci/cd", Dimension.TOOLING),
    ("github actions", "ci/cd", Dimension.TOOLING),
    ("postman", "api tooling", Dimension.TOOLING),
    ("aws", "cloud infrastructure", Dimension.TOOLING),
    ("distributed", "distributed systems", Dimension.SYSTEMS),
    ("microservice", "distributed systems", Dimension.SYSTEMS),
    ("concurren", "concurrency", Dimension.SYSTEMS),
    ("operating system", "operating systems", Dimension.SYSTEMS),
    ("networks", "networking", Dimension.SYSTEMS),
    ("load balanc", "scalability", Dimension.SYSTEMS),
    ("teaching assistant", "teaching", Dimension.COMMUNICATION),
    ("lab session", "teaching", Dimension.COMMUNICATION),
    ("graded assignments", "teaching", Dimension.COMMUNICATION),
    ("mentor", "mentoring", Dimension.COMMUNICATION),
    ("presented", "presenting", Dimension.COMMUNICATION),
    ("led the", "leadership", Dimension.COMMUNICATION),
    ("wrote feedback", "written communication", Dimension.COMMUNICATION),
]


def _deterministic_resume(resume_text: str) -> _ResumeExtracted:
    items: list[_ExtractedEvidence] = []
    for raw_line in resume_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        for keyword, label, dimension in _RESUME_KEYWORDS:
            if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", lowered):
                items.append(
                    _ExtractedEvidence(label=label, dimension=dimension, source_text=line)
                )
    return _ResumeExtracted(evidence=items)


@dataclass
class ResumeParse:
    evidence: list[Evidence]
    trace: list[TraceEvent]
    used_fallback: bool


def parse_resume(resume_text: str) -> ResumeParse:
    """Parse a resume into Evidence, falling back to the keyword parser."""
    used_fallback = False
    fallback_reason: str | None = None
    try:
        extracted = _call_resume_bedrock(resume_text)
    except RuntimeError as exc:
        extracted = _deterministic_resume(resume_text)
        used_fallback = True
        fallback_reason = str(exc)

    evidence = _to_evidence(extracted)

    trace: list[TraceEvent] = []
    if used_fallback:
        trace.append(
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Profile Agent",
                message="Resume parsed by the deterministic fallback parser",
                detail=fallback_reason,
            )
        )
    by_dimension = ", ".join(sorted({item.dimension.value for item in evidence})) or "none"
    trace.append(
        TraceEvent(
            kind=TraceKind.OBSERVED,
            agent="Profile Agent",
            message=f"Extracted {len(evidence)} pieces of evidence from the resume "
            f"(dimensions: {by_dimension})",
        )
    )
    return ResumeParse(evidence=evidence, trace=trace, used_fallback=used_fallback)


@dataclass
class ProfileBuild:
    profile: StudentProfile
    trace: list[TraceEvent]
    used_fallback: bool  # True if either parser fell back


def build_profile(
    transcript_text: str, resume_text: str, target_role: str = DEFAULT_ROLE
) -> ProfileBuild:
    """Run both parsers and return one StudentProfile with the evidence attached."""
    transcript = parse_transcript(transcript_text, target_role)
    resume = parse_resume(resume_text)
    profile = transcript.profile.model_copy(update={"evidence": resume.evidence})
    return ProfileBuild(
        profile=profile,
        trace=transcript.trace + resume.trace,
        used_fallback=transcript.used_fallback or resume.used_fallback,
    )


if __name__ == "__main__":
    # Manual check against the fixtures. Not a pytest test — CLAUDE.md bars those from
    # touching Bedrock. Run with credentials to exercise the model path:
    #   python -m src.agents.profile
    from pathlib import Path

    fixtures = Path(__file__).parents[2] / "data" / "fixtures"
    built = build_profile(
        (fixtures / "transcript.txt").read_text(), (fixtures / "resume.txt").read_text()
    )
    print(f"used_fallback={built.used_fallback}")
    print(json.dumps(built.profile.model_dump(mode="json"), indent=2))
