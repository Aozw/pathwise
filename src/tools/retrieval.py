"""Semantic shortlist over the precomputed module embedding index — W2.1b.

`build_module_index.py` (repo root) embeds every module in the NUSMods catalogue
once, offline, with Titan (config.MODEL_EMBEDDING), and commits the result to
data/index/module_embeddings.npz - a module code array plus an L2-normalised
float32 matrix, so cosine similarity is a plain dot product. Never embed the
catalogue at runtime (CLAUDE.md hard rule).

shortlist() embeds the gap text once - the one runtime embedding call the hard
rule allows - then ranks eligible_ids by dot product against that query vector.
At ~7000 rows brute force is sub-millisecond; no FAISS, no Chroma, no vector
database (PLAN.md W2.1b).

Deviates from PLAN.md's literal `shortlist(...) -> list[str]` signature by
returning `(codes, used_fallback)`: the embedding call is an external API call,
and the CLAUDE.md hard rule on external calls requires the caller be able to
write a TraceEvent recording when the fallback fired, which a bare list can't
signal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, MODEL_EMBEDDING, TOOL_RETRIES, TOOL_TIMEOUT_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = REPO_ROOT / "data" / "index" / "module_embeddings.npz"

_EMBED_BOTO_CONFIG = BotoConfig(
    connect_timeout=TOOL_TIMEOUT_SECONDS,
    read_timeout=TOOL_TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)

_embed_client: Any = None
_index_cache: tuple[np.ndarray, np.ndarray] | None = None  # (ids, unit vectors)


def _embed_bedrock() -> Any:
    global _embed_client
    if _embed_client is None:
        _embed_client = boto3.client(
            "bedrock-runtime", region_name=AWS_REGION, config=_EMBED_BOTO_CONFIG
        )
    return _embed_client


def embed_text(text: str) -> np.ndarray:
    """One Titan embedding call, L2-normalised so dot product is cosine similarity.
    Raises on failure - callers needing the timeout/retry/fallback pattern use
    _embed_query below, not this directly.
    """
    response = _embed_bedrock().invoke_model(
        modelId=MODEL_EMBEDDING,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(response["body"].read())
    vector = np.array(body["embedding"], dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def _embed_query(text: str) -> np.ndarray | None:
    """Timeout + one retry, per the CLAUDE.md hard rule on external calls. Returns
    None (never raises) so shortlist() can fall back to unranked order.
    """
    for _ in range(1 + TOOL_RETRIES):
        try:
            return embed_text(text)
        except (ClientError, BotoCoreError, KeyError, ValueError):
            continue
    return None


def _load_index() -> tuple[np.ndarray, np.ndarray] | None:
    global _index_cache
    if _index_cache is None:
        if not INDEX_PATH.exists():
            return None
        data = np.load(INDEX_PATH, allow_pickle=False)
        _index_cache = (data["ids"], data["vectors"])
    return _index_cache


def shortlist(gap_text: str, eligible_ids: list[str], k: int) -> tuple[list[str], bool]:
    """Rank `eligible_ids` (bare NUSMods module codes) by cosine similarity to
    `gap_text`, restricted to codes present in the committed index, and return the
    top k. Returns (eligible_ids[:k], True) - the fallback, catalogue order as-is -
    if the index isn't built yet or the one runtime embedding call fails after
    retry; the caller writes a TraceEvent when the second element is True.
    """
    if not eligible_ids:
        return [], False

    index = _load_index()
    if index is None:
        return eligible_ids[:k], True

    query_vector = _embed_query(gap_text)
    if query_vector is None:
        return eligible_ids[:k], True

    ids, vectors = index
    row_by_code = {code: i for i, code in enumerate(ids)}
    candidate_rows = [(code, row_by_code[code]) for code in eligible_ids if code in row_by_code]
    if not candidate_rows:
        return eligible_ids[:k], True

    codes, rows = zip(*candidate_rows, strict=True)
    similarities = vectors[list(rows)] @ query_vector
    order = np.argsort(-similarities)[:k]
    return [codes[i] for i in order], False
