"""Unit tests for W2.1b — src/tools/retrieval.py.

embed_text (the one real Bedrock call) is mocked throughout, per the CLAUDE.md
hard rule against calling Bedrock or any external API from a test. The index
itself is a real .npz written to tmp_path, not the committed data/index/ one, so
these tests exercise the real np.load/dot-product path without depending on
whatever the committed index happens to contain.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

import src.tools.retrieval as retrieval


def _unit(vector: list[float]) -> np.ndarray:
    arr = np.array(vector, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def _write_index(path, codes: list[str], vectors: list[np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, ids=np.array(codes), vectors=np.stack(vectors).astype(np.float32))


@pytest.fixture(autouse=True)
def _reset_cache():
    retrieval._index_cache = None
    yield
    retrieval._index_cache = None


def test_shortlist_ranks_by_cosine_similarity(tmp_path, monkeypatch):
    index_path = tmp_path / "module_embeddings.npz"
    # CS_SYSTEMS points the same direction as the query; CS_UNRELATED points away.
    _write_index(
        index_path,
        ["CS_SYSTEMS", "CS_UNRELATED", "CS_SOMEWHAT"],
        [_unit([1.0, 0.0]), _unit([0.0, 1.0]), _unit([0.7, 0.3])],
    )
    monkeypatch.setattr(retrieval, "INDEX_PATH", index_path)
    monkeypatch.setattr(retrieval, "_embed_query", lambda text: _unit([1.0, 0.0]))

    codes, used_fallback = retrieval.shortlist(
        "distributed systems", ["CS_SYSTEMS", "CS_UNRELATED", "CS_SOMEWHAT"], k=2
    )

    assert used_fallback is False
    assert codes == ["CS_SYSTEMS", "CS_SOMEWHAT"]


def test_shortlist_restricts_to_eligible_ids_only(tmp_path, monkeypatch):
    index_path = tmp_path / "module_embeddings.npz"
    _write_index(
        index_path,
        ["A", "B", "C"],
        [_unit([1.0, 0.0]), _unit([1.0, 0.0]), _unit([1.0, 0.0])],
    )
    monkeypatch.setattr(retrieval, "INDEX_PATH", index_path)
    monkeypatch.setattr(retrieval, "_embed_query", lambda text: _unit([1.0, 0.0]))

    codes, used_fallback = retrieval.shortlist("gap", ["B"], k=5)

    assert used_fallback is False
    assert codes == ["B"]


def test_shortlist_falls_back_when_index_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "INDEX_PATH", tmp_path / "does_not_exist.npz")

    codes, used_fallback = retrieval.shortlist("gap", ["A", "B", "C"], k=2)

    assert used_fallback is True
    assert codes == ["A", "B"]


def test_shortlist_falls_back_when_embedding_call_fails(tmp_path, monkeypatch):
    index_path = tmp_path / "module_embeddings.npz"
    _write_index(index_path, ["A", "B"], [_unit([1.0, 0.0]), _unit([0.0, 1.0])])
    monkeypatch.setattr(retrieval, "INDEX_PATH", index_path)
    monkeypatch.setattr(retrieval, "_embed_query", lambda text: None)

    codes, used_fallback = retrieval.shortlist("gap", ["A", "B"], k=1)

    assert used_fallback is True
    assert codes == ["A"]


def test_shortlist_falls_back_when_no_eligible_id_is_in_the_index(tmp_path, monkeypatch):
    index_path = tmp_path / "module_embeddings.npz"
    _write_index(index_path, ["A"], [_unit([1.0, 0.0])])
    monkeypatch.setattr(retrieval, "INDEX_PATH", index_path)
    monkeypatch.setattr(retrieval, "_embed_query", lambda text: _unit([1.0, 0.0]))

    codes, used_fallback = retrieval.shortlist("gap", ["ZZZ_NOT_IN_INDEX"], k=5)

    assert used_fallback is True
    assert codes == ["ZZZ_NOT_IN_INDEX"]


def test_shortlist_of_no_eligible_ids_is_empty_without_touching_the_index():
    with patch.object(retrieval, "_load_index") as mock_load:
        codes, used_fallback = retrieval.shortlist("gap", [], k=5)

    mock_load.assert_not_called()
    assert codes == []
    assert used_fallback is False


def test_embed_query_retries_once_then_gives_up(monkeypatch):
    calls = []

    def _boom(text):
        calls.append(text)
        raise ValueError("boom")

    monkeypatch.setattr(retrieval, "embed_text", _boom)

    assert retrieval._embed_query("gap") is None
    assert len(calls) == 2  # one retry, per config.TOOL_RETRIES
