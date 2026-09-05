"""W3.4 — src/metrics.py.

Pure functions and a single file write. No network: the model call sites that feed
`ModelCallStats` are tested where they live (test_score_node.py); here we test the
helpers and the run-end derivation in isolation.
"""

from __future__ import annotations

import json

from src.metrics import (
    ModelCallStats,
    apply_model_call,
    finalize,
    token_usage,
    write_run_metrics,
)
from src.state import RunMetrics, TraceEvent, TraceKind, new_run_state


def _trace(*messages: str) -> list[TraceEvent]:
    return [
        TraceEvent(kind=TraceKind.OBSERVED, agent="Test", message=m) for m in messages
    ]


# --- token_usage ----------------------------------------------------------------


def test_token_usage_reads_the_usage_block():
    assert token_usage({"usage": {"inputTokens": 111, "outputTokens": 22}}) == (111, 22)


def test_token_usage_is_zero_when_usage_is_absent_or_malformed():
    assert token_usage({}) == (0, 0)
    assert token_usage({"usage": None}) == (0, 0)
    assert token_usage({"usage": {"inputTokens": "oops"}}) == (0, 0)


# --- apply_model_call ----------------------------------------------------------


def test_apply_model_call_adds_into_the_running_totals():
    start = RunMetrics(input_tokens=100, schema_validations_passed=1)
    stats = ModelCallStats(
        input_tokens=50, output_tokens=10, schema_validations_passed=1, schema_validations_failed=2
    )
    out = apply_model_call(start, stats)

    assert out.input_tokens == 150
    assert out.output_tokens == 10
    assert out.schema_validations_passed == 2
    assert out.schema_validations_failed == 2
    # original untouched
    assert start.input_tokens == 100


# --- finalize ----------------------------------------------------------------


def test_finalize_derives_counts_from_state_and_trace():
    state = new_run_state("run-xyz")
    state["iteration"] = 2
    state["candidates"] = ["c"] * 40  # only the length is read
    state["ranked"] = ["c"] * 7
    state["trace"] = _trace(
        "Found 12 hackathons for query 'ml'",
        "Found 30 modules, live-checked prerequisites for 3",
        "GitHub search failed, used fixture projects instead",
        "Planner fell back to dispatching every agent",
    )

    m = finalize(state)

    assert m.refine_iterations == 2
    assert m.candidates_before_filter == 40
    assert m.candidates_after_filter == 7
    assert m.tool_calls_attempted == 3  # two "Found ..." + one "used fixture"
    assert m.tool_calls_succeeded == 2
    assert m.fallbacks_used == 2  # "used fixture" + "fell back"


def test_finalize_keeps_instrumented_token_and_schema_counts():
    state = new_run_state("run-xyz")
    state["metrics"] = RunMetrics(
        input_tokens=900, output_tokens=120, schema_validations_passed=2, schema_validations_failed=1
    )

    m = finalize(state)

    assert (m.input_tokens, m.output_tokens) == (900, 120)
    assert (m.schema_validations_passed, m.schema_validations_failed) == (2, 1)


# --- write_run_metrics -------------------------------------------------------


def test_write_run_metrics_writes_a_json_file(tmp_path):
    state = new_run_state("run-42")
    state["ranked"] = ["c", "c"]
    state["metrics"] = RunMetrics(input_tokens=500)

    path = write_run_metrics(state, runs_dir=tmp_path)

    assert path == tmp_path / "run-42.json"
    data = json.loads(path.read_text())
    assert data["input_tokens"] == 500
    assert data["candidates_after_filter"] == 2


def test_write_run_metrics_returns_none_when_the_directory_cannot_be_used(tmp_path):
    blocker = tmp_path / "runs"
    blocker.write_text("i am a file, not a directory")

    assert write_run_metrics(new_run_state("run-1"), runs_dir=blocker / "nested") is None
