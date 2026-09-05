"""Unit tests for W1.6 — src/snapshot.py.

The S3 client is mocked throughout; nothing here touches the network, per the
CLAUDE.md hard rule against calling external APIs from a test.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.snapshot as snap
from src.state import TraceKind, new_run_state


class _FakeNoSuchKey(Exception):
    pass


def _fake_client(no_such_key_cls=_FakeNoSuchKey):
    client = MagicMock()
    client.exceptions.NoSuchKey = no_such_key_cls
    return client


def test_load_snapshot_missing_key_is_not_a_failure():
    client = _fake_client()
    client.get_object.side_effect = client.exceptions.NoSuchKey()
    with patch.object(snap, "_s3", return_value=client):
        state, event = snap.load_snapshot("run-does-not-exist")
    assert state is None
    assert event is None


def test_load_snapshot_round_trips_a_real_state():
    original = new_run_state("run-1")
    tag, payload = snap._SERDE.dumps_typed(original)

    client = _fake_client()
    client.get_object.return_value = {
        "Body": MagicMock(read=lambda: payload),
        "Metadata": {"serde-type": tag},
    }
    with patch.object(snap, "_s3", return_value=client):
        state, event = snap.load_snapshot("run-1")

    assert event is None
    assert state["run_id"] == "run-1"
    assert state["candidates"] == []


def test_load_snapshot_reports_failure_after_retry():
    client = _fake_client()
    client.get_object.side_effect = RuntimeError("boom")
    # RuntimeError is not (ClientError, BotoCoreError), so patch load_snapshot's
    # narrower behaviour by raising a type it actually catches instead.
    from botocore.exceptions import BotoCoreError

    client.get_object.side_effect = BotoCoreError()
    with patch.object(snap, "_s3", return_value=client):
        state, event = snap.load_snapshot("run-broken")

    assert state is None
    assert event is not None
    assert event.kind == TraceKind.OBSERVED
    assert "read failed" in event.message


def test_save_snapshot_success_returns_no_event():
    client = _fake_client()
    with patch.object(snap, "_s3", return_value=client):
        event = snap.save_snapshot(new_run_state("run-2"))
    assert event is None
    assert client.put_object.called


def test_save_snapshot_reports_failure_after_retry():
    from botocore.exceptions import BotoCoreError

    client = _fake_client()
    client.put_object.side_effect = BotoCoreError()
    with patch.object(snap, "_s3", return_value=client):
        event = snap.save_snapshot(new_run_state("run-3"))
    assert event is not None
    assert "write failed" in event.message
    assert client.put_object.call_count == 2  # one retry, per config.TOOL_RETRIES
