"""W3.1 transcript parser and W3.2 resume parser.

The model path cannot run in CI (no credentials, and CLAUDE.md bars Bedrock from
tests), so these exercise the deterministic parsers directly and drive
`parse_transcript` / `parse_resume` by monkeypatching the `_call_*_bedrock`
functions — either raising to force the fallback, or returning a canned extraction
to check the success path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import profile as profile_mod
from src.agents.profile import (
    _deterministic_extract,
    _deterministic_resume,
    _Extracted,
    _ExtractedEvidence,
    _ExtractedModule,
    _infer_year,
    _ResumeExtracted,
    _to_evidence,
    build_profile,
    parse_resume,
    parse_transcript,
)
from src.state import Dimension

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures"
FIXTURE = FIXTURES / "transcript.txt"


@pytest.fixture
def transcript_text() -> str:
    return FIXTURE.read_text()


@pytest.fixture
def resume_text() -> str:
    return (FIXTURES / "resume.txt").read_text()


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


# ---------------------------------------------------------------------------
# W3.2 — resume parser, deterministic path
# ---------------------------------------------------------------------------


def test_deterministic_resume_finds_evidence_across_dimensions(resume_text: str):
    evidence = _to_evidence(_deterministic_resume(resume_text))
    labels = {e.label for e in evidence}
    dimensions = {e.dimension for e in evidence}

    assert "rest api" in labels
    assert "automated testing" in labels
    assert "teaching" in labels
    assert {"relational databases", "sql"} & labels
    # this resume shows no systems work — that is the student's actual gap, so the
    # redundancy penalty must not later see systems evidence
    assert Dimension.SYSTEMS not in dimensions
    assert {Dimension.PROGRAMMING, Dimension.DATA, Dimension.TOOLING, Dimension.COMMUNICATION} <= dimensions


def test_deterministic_resume_does_not_match_keywords_inside_other_words(resume_text: str):
    # "github.com/weilingtan" must not register as "git" -> version control on its own;
    # version control should come only from the real "Tools: Git, ..." line.
    evidence = _to_evidence(_deterministic_resume(resume_text))
    vc = [e for e in evidence if e.label == "version control"]
    assert len(vc) == 1
    assert "Tools:" in vc[0].source_text


def test_deterministic_resume_carries_the_source_line(resume_text: str):
    evidence = _to_evidence(_deterministic_resume(resume_text))
    rest_api = next(e for e in evidence if e.label == "rest api")
    assert rest_api.source_text == "Built a REST API in Flask for the internal reporting dashboard."


def test_to_evidence_deduplicates_and_normalises():
    extracted = _ResumeExtracted(
        evidence=[
            _ExtractedEvidence(label="REST API", dimension=Dimension.PROGRAMMING, source_text="a"),
            _ExtractedEvidence(label="rest api", dimension=Dimension.PROGRAMMING, source_text="b"),
            _ExtractedEvidence(label="  ", dimension=Dimension.DATA, source_text="c"),
        ]
    )
    evidence = _to_evidence(extracted)
    assert [e.label for e in evidence] == ["rest api"]
    assert evidence[0].source_text == "a"  # first wins


# ---------------------------------------------------------------------------
# W3.2 — resume parser, model path and fallback
# ---------------------------------------------------------------------------


def test_parse_resume_falls_back_and_traces_when_bedrock_fails(
    resume_text: str, monkeypatch: pytest.MonkeyPatch
):
    def boom(_text: str):
        raise RuntimeError("resume Bedrock call failed after retry: no credentials")

    monkeypatch.setattr(profile_mod, "_call_resume_bedrock", boom)
    result = parse_resume(resume_text)

    assert result.used_fallback is True
    assert result.evidence
    assert any("fallback" in event.message.lower() for event in result.trace)


def test_parse_resume_uses_model_result_when_bedrock_succeeds(monkeypatch: pytest.MonkeyPatch):
    canned = _ResumeExtracted(
        evidence=[
            _ExtractedEvidence(
                label="kafka streams",
                dimension=Dimension.SYSTEMS,
                source_text="Built an event pipeline on Kafka",
            )
        ]
    )
    monkeypatch.setattr(profile_mod, "_call_resume_bedrock", lambda _text: canned)
    result = parse_resume("irrelevant")

    assert result.used_fallback is False
    assert [(e.label, e.dimension) for e in result.evidence] == [
        ("kafka streams", Dimension.SYSTEMS)
    ]


# ---------------------------------------------------------------------------
# build_profile — both parsers together
# ---------------------------------------------------------------------------


def test_build_profile_attaches_resume_evidence_to_the_transcript_profile(
    transcript_text: str, resume_text: str, monkeypatch: pytest.MonkeyPatch
):
    def unavailable(_text: str):
        raise RuntimeError("Bedrock call failed after retry")

    monkeypatch.setattr(profile_mod, "_call_bedrock", unavailable)
    monkeypatch.setattr(profile_mod, "_call_resume_bedrock", unavailable)

    built = build_profile(transcript_text, resume_text, target_role="backend_infrastructure")

    assert built.used_fallback is True
    assert len(built.profile.completed_modules) == 18  # from the transcript
    assert built.profile.evidence  # from the resume
    assert built.profile.evidence_labels  # the frozen helper still works
    assert all(isinstance(e.dimension, Dimension) for e in built.profile.evidence)
