"""W3.1 — transcript parser.

The model path cannot run in CI (no credentials, and CLAUDE.md bars Bedrock from
tests), so these exercise the deterministic parser directly and drive
`parse_transcript` by monkeypatching `_call_bedrock` — either raising to force the
fallback, or returning a canned extraction to check the success path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import profile as profile_mod
from src.agents.profile import (
    _deterministic_extract,
    _Extracted,
    _ExtractedModule,
    _infer_year,
    parse_transcript,
)

FIXTURE = Path(__file__).parent.parent / "data" / "fixtures" / "transcript.txt"


@pytest.fixture
def transcript_text() -> str:
    return FIXTURE.read_text()


# ---------------------------------------------------------------------------
# Deterministic parser
# ---------------------------------------------------------------------------


def test_deterministic_extract_reads_header_fields(transcript_text: str):
    extracted = _deterministic_extract(transcript_text)
    assert extracted.name == "Tan Wei Ling"  # title-cased from the shouting transcript
    assert extracted.major == "Computer Science"
    assert extracted.units_completed == 72.0
    assert extracted.units_required == 160.0


def test_deterministic_extract_finds_every_graded_module(transcript_text: str):
    extracted = _deterministic_extract(transcript_text)
    assert len(extracted.completed_modules) == 18
    by_code = {m.code: m for m in extracted.completed_modules}
    # letter-suffixed code, normal grade
    assert by_code["CS2030S"].title == "Programming Methodology II"
    assert by_code["CS2030S"].units == 4.0
    assert by_code["CS2030S"].grade == "A-"
    # multi-word title with internal single spaces stays intact
    assert by_code["CS2109S"].title == "Introduction to AI and Machine Learning"
    # S/U grade is a valid grade, not dropped
    assert by_code["CFG1002"].grade == "S"


def test_deterministic_extract_infers_second_year_from_candidature(transcript_text: str):
    # Candidature starts AY2024/2025, latest semester header is AY2025/2026 -> year 2.
    assert _deterministic_extract(transcript_text).year == 2


def test_infer_year_falls_back_to_unit_count_without_calendar_evidence():
    assert _infer_year(None, None, 0) == 1
    assert _infer_year(None, None, 72) == 3
    assert _infer_year(None, None, 999) == 6  # clamped


def test_infer_year_prefers_calendar_evidence_over_units():
    assert _infer_year(2024, 2026, 0) == 3


def test_module_rows_without_a_recognised_grade_are_kept_without_one():
    text = "AY2025/2026 SEMESTER 1\nCS3210    Parallel Computing    4   IP\n"
    extracted = _deterministic_extract(text)
    assert len(extracted.completed_modules) == 1
    assert extracted.completed_modules[0].grade is None


# ---------------------------------------------------------------------------
# parse_transcript — fallback path
# ---------------------------------------------------------------------------


def test_parse_transcript_falls_back_and_traces_when_bedrock_fails(
    transcript_text: str, monkeypatch: pytest.MonkeyPatch
):
    def boom(_text: str):
        raise RuntimeError("transcript Bedrock call failed after retry: no credentials")

    monkeypatch.setattr(profile_mod, "_call_bedrock", boom)

    result = parse_transcript(transcript_text, target_role="backend_infrastructure")

    assert result.used_fallback is True
    assert result.profile.name == "Tan Wei Ling"
    assert result.profile.target_role == "backend_infrastructure"
    assert len(result.profile.completed_modules) == 18
    assert result.profile.evidence == []
    # the fallback must announce itself in the trace, per the CLAUDE.md hard rule
    assert any("fallback" in event.message.lower() for event in result.trace)


# ---------------------------------------------------------------------------
# parse_transcript — model path
# ---------------------------------------------------------------------------


def test_parse_transcript_uses_model_result_when_bedrock_succeeds(
    monkeypatch: pytest.MonkeyPatch,
):
    canned = _Extracted(
        name="Jane Doe",
        year=3,
        major="Information Systems",
        units_completed=100,
        units_required=160,
        completed_modules=[_ExtractedModule(code="IS1103", title="Ethics", units=4, grade="A")],
    )
    monkeypatch.setattr(profile_mod, "_call_bedrock", lambda _text: canned)

    result = parse_transcript("irrelevant", target_role="data_engineering")

    assert result.used_fallback is False
    assert result.profile.name == "Jane Doe"
    assert result.profile.year == 3
    assert result.profile.completed_modules[0].code == "IS1103"
    assert not any("fallback" in event.message.lower() for event in result.trace)


def test_parse_transcript_rejects_unknown_target_role(transcript_text: str):
    with pytest.raises(ValueError, match="ROLE_DIMENSION_WEIGHTS"):
        parse_transcript(transcript_text, target_role="astronaut")
