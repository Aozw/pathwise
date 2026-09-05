"""S3 state snapshot — W1.6. Read at run start, write at run end.

Replaces AgentCore Memory/Gateway with one S3 object per run, keyed by run_id under
config.S3_RUNS_PREFIX. See PLAN.md section 9: "Do not use AgentCore Memory or
Gateway. Your own S3 object does the same job for free."

This is a coarse RunState snapshot, not a LangGraph checkpointer. It does not capture
enough to resume mid-interrupt across processes - that would need a full
BaseCheckpointSaver backed by S3, a materially bigger task than "read at run start,
write at run end". What this gives: a run's state survives past a single process's
memory, so a run can be reloaded (e.g. a retried request for the same run_id, or an
audit/debug lookup) even after the process that ran it is gone. Within one process's
lifetime, the in-process InMemorySaver checkpointer in graph.py is still what makes
interrupt()/resume actually work - see graph.py's module docstring for the gap this
leaves for W4.4's approve endpoint.

Usage (for whoever wires src/entrypoint.py — W4.1/W4.4, not built here):
    from src.snapshot import load_snapshot, save_snapshot
    from src.state import new_run_state

    state = load_snapshot(run_id) or new_run_state(run_id)
    result = graph.invoke(state, config={"configurable": {"thread_id": run_id}})
    save_snapshot(result)

Every call gets a timeout, one retry, and a graceful fallback per the CLAUDE.md hard
rule: a failed read falls back to "no snapshot" (caller starts fresh) and a failed
write is reported back rather than raised - losing persistence should never be why a
demo run fails outright. A missing object (first-ever run for this run_id) is normal,
not a failure, and is not reported as one.
"""

from __future__ import annotations

import inspect
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src import state as _state_module
from src.config import S3_BUCKET, S3_RUNS_PREFIX, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS
from src.state import RunState, TraceEvent, TraceKind

_BOTO_CONFIG = BotoConfig(
    connect_timeout=TOOL_TIMEOUT_SECONDS,
    read_timeout=TOOL_TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)

# Same approach as graph.py's checkpointer allowlist: built by introspecting state.py
# rather than hand-listed, so it can't go stale as the frozen contract is amended.
_MSGPACK_ALLOWLIST = [
    obj
    for _, obj in inspect.getmembers(_state_module, inspect.isclass)
    if obj.__module__ == _state_module.__name__
]
_SERDE = JsonPlusSerializer(allowed_msgpack_modules=_MSGPACK_ALLOWLIST)

_client: Any = None


def _s3() -> Any:
    global _client
    if _client is None:
        _client = boto3.client("s3", config=_BOTO_CONFIG)
    return _client


def _key(run_id: str) -> str:
    return f"{S3_RUNS_PREFIX}{run_id}.msgpack"


def load_snapshot(run_id: str) -> tuple[RunState | None, TraceEvent | None]:
    """Returns (state, fallback_event). state is None if there is no snapshot yet for
    this run_id (the normal case for a first-ever run) or if the read failed after a
    retry (fallback_event explains why - the caller should start fresh either way).
    """
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            response = _s3().get_object(Bucket=S3_BUCKET, Key=_key(run_id))
            payload = response["Body"].read()
            tag = response.get("Metadata", {}).get("serde-type", "msgpack")
            return _SERDE.loads_typed((tag, payload)), None
        except _s3().exceptions.NoSuchKey:
            return None, None  # normal: no prior snapshot for this run_id
        except (ClientError, BotoCoreError) as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") in (
                "NoSuchKey",
                "404",
            ):
                return None, None
            last_error = exc

    return None, TraceEvent(
        kind=TraceKind.OBSERVED,
        agent="Career Agent",
        message="S3 snapshot read failed, starting fresh",
        detail=str(last_error),
    )


def save_snapshot(state: RunState) -> TraceEvent | None:
    """Returns None on success, or a TraceEvent explaining why the write failed after
    a retry. Never raises - a failed snapshot write should not fail the run itself.
    """
    tag, payload = _SERDE.dumps_typed(state)
    last_error: Exception | None = None
    for _ in range(1 + TOOL_RETRIES):
        try:
            _s3().put_object(
                Bucket=S3_BUCKET,
                Key=_key(state["run_id"]),
                Body=payload,
                Metadata={"serde-type": tag},
            )
            return None
        except (ClientError, BotoCoreError) as exc:
            last_error = exc

    return TraceEvent(
        kind=TraceKind.OBSERVED,
        agent="Career Agent",
        message="S3 snapshot write failed",
        detail=str(last_error),
    )
