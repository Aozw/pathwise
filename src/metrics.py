"""Run metrics — W3.4.

Fills `RunState.metrics` (a `RunMetrics`, defined in the frozen state contract) so the
testing slide has real numbers: token spend, how often the model's structured output
validated, how often a tool call fell back to a fixture, and how far the candidate set
was cut before scoring.

Two collection paths, split by what each field can be known from:

  - **Instrumented** at the two model call sites (planner, score node): input/output
    tokens and schema-validation pass/fail. These are counted where the `converse`
    response and the `model_validate` call actually happen - nowhere else can see
    them. `RunState.metrics` is last-write-wins (not a reducer - state.py is frozen),
    which is safe here only because planner and score run strictly in sequence; the
    parallel fan-out nodes are deliberately *not* instrumented.
  - **Derived** at run end by `finalize()` from the trace and the candidate lists:
    refine iterations, candidate counts, and tool-call outcomes. The trace is the
    real execution record (see CLAUDE.md), so reading tool fallbacks back off it
    avoids instrumenting three more of someone else's files.

`write_run_metrics()` writes `data/runs/{run_id}.json` (gitignored) at run end. The
same `RunMetrics` also rides along in the S3 state snapshot `snapshot.py` already
writes - this is the local-dev / no-deploy copy PLAN.md's W3.4 asks for.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.state import RunMetrics, RunState

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "runs"

# Substrings that mark a TraceEvent as "an external call fell back to a fixture or a
# safe default". Kept here, in one place, because they are matched against free-text
# trace messages written in other modules - if one of those messages is reworded this
# list is the single thing to update.
_FALLBACK_MARKERS = ("fell back", "used fixture", "falling back", "failed, used")
# Sub-agent nodes announce a successful source read as "Found N ...".
_TOOL_SUCCESS_PREFIX = "Found "


@dataclass
class ModelCallStats:
    """One model call's contribution to RunMetrics, accumulated across retries."""

    input_tokens: int = 0
    output_tokens: int = 0
    schema_validations_passed: int = 0
    schema_validations_failed: int = 0


def token_usage(response: Mapping) -> tuple[int, int]:
    """(input_tokens, output_tokens) from a Bedrock `converse` response, 0s if absent.

    A fixture-backed or mocked response has no `usage` block, and a partial failure
    can return without one, so this never raises.
    """
    usage = response.get("usage") or {}
    try:
        return int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))
    except (TypeError, ValueError):
        return 0, 0


def apply_model_call(metrics: RunMetrics, stats: ModelCallStats) -> RunMetrics:
    """Return a copy of `metrics` with one model call's stats added in."""
    return metrics.model_copy(
        update={
            "input_tokens": metrics.input_tokens + stats.input_tokens,
            "output_tokens": metrics.output_tokens + stats.output_tokens,
            "schema_validations_passed": metrics.schema_validations_passed
            + stats.schema_validations_passed,
            "schema_validations_failed": metrics.schema_validations_failed
            + stats.schema_validations_failed,
        }
    )


def finalize(state: RunState) -> RunMetrics:
    """Combine the instrumented `state['metrics']` with everything derivable from the
    trace and candidate lists at run end. Pure - no I/O.
    """
    metrics = state.get("metrics") or RunMetrics()
    trace = state.get("trace", [])

    fallbacks = sum(
        1
        for event in trace
        if any(marker in event.message.lower() for marker in _FALLBACK_MARKERS)
    )
    tool_successes = sum(1 for event in trace if event.message.startswith(_TOOL_SUCCESS_PREFIX))
    tool_fallbacks = sum(
        1 for event in trace if "used fixture" in event.message.lower()
    )

    return metrics.model_copy(
        update={
            "refine_iterations": state.get("iteration", metrics.refine_iterations),
            "candidates_before_filter": len(state.get("candidates", [])),
            "candidates_after_filter": len(state.get("ranked", [])),
            "tool_calls_attempted": tool_successes + tool_fallbacks,
            "tool_calls_succeeded": tool_successes,
            "fallbacks_used": fallbacks,
        }
    )


def write_run_metrics(state: RunState, runs_dir: Path = DEFAULT_RUNS_DIR) -> Path | None:
    """Write finalize(state) to `{runs_dir}/{run_id}.json`. Returns the path, or None
    if the write failed - a lost metrics file must never be why a run fails.
    """
    try:
        metrics = finalize(state)
        runs_dir.mkdir(parents=True, exist_ok=True)
        path = runs_dir / f"{state['run_id']}.json"
        path.write_text(json.dumps(metrics.model_dump(), indent=2))
        return path
    except OSError:
        return None
