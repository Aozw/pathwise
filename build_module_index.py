"""Offline build for W2.1b's module embedding index. Run once, by hand, whenever
the NUSMods cache is refreshed - never at runtime (CLAUDE.md hard rule: "Never
embed the module catalogue at runtime"). Commits data/index/module_embeddings.npz.

Usage:
    python build_module_index.py

Needs data/cache/ populated first (`python -m src.tools.nusmods`) - it embeds
whatever load_catalogue() returns, so building against the small fixture instead
would commit a near-useless 5-module index.

Resumable: if module_embeddings.npz already exists, only catalogue codes missing
from it are (re-)embedded and the results are merged in. Titan throttles a first
full run at any real concurrency (confirmed: 12 workers, no backoff, dropped
~18% of 7138 calls to ThrottlingException) - rerunning this script afterwards
retries only the gap at lower concurrency with backoff, rather than re-spending
on the ~5800 that already succeeded.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tools.nusmods import CACHE_PATH, load_catalogue  # noqa: E402
from src.tools.retrieval import INDEX_PATH, embed_text  # noqa: E402

_WORKERS = 4  # Titan throttled a first attempt at 12 with no backoff - stay modest
_MAX_ATTEMPTS = 5
_MAX_DESCRIPTION_CHARS = 500


def _embed_text_for(module) -> str:
    text = f"{module.code} {module.title}. {module.description[:_MAX_DESCRIPTION_CHARS]}"
    return text.strip()


def _embed_with_backoff(text: str) -> np.ndarray:
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return embed_text(text)
        except ClientError as exc:
            last_error = exc
            if exc.response.get("Error", {}).get("Code") != "ThrottlingException":
                raise
            time.sleep(2**attempt)  # 1s, 2s, 4s, 8s, 16s
    raise RuntimeError(f"gave up after {_MAX_ATTEMPTS} attempts") from last_error


def _load_existing() -> tuple[dict[str, np.ndarray], int]:
    if not INDEX_PATH.exists():
        return {}, 0
    data = np.load(INDEX_PATH, allow_pickle=False)
    existing = dict(zip(data["ids"], data["vectors"], strict=True))
    return existing, len(existing)


def main() -> None:
    if not CACHE_PATH.exists():
        sys.exit(
            f"{CACHE_PATH} not found - run `python -m src.tools.nusmods` first to "
            "populate the real catalogue. Building against the fixture fallback "
            "would commit a near-useless index."
        )

    catalogue = load_catalogue()
    by_code, already = _load_existing()
    to_embed = [module for module in catalogue if module.code not in by_code]

    print(f"{len(catalogue)} modules in catalogue, {already} already embedded, "
          f"{len(to_embed)} to go, {_WORKERS} workers with backoff on throttling...")

    failures = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        future_to_code = {
            pool.submit(_embed_with_backoff, _embed_text_for(module)): module.code
            for module in to_embed
        }
        done = 0
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            done += 1
            try:
                by_code[code] = future.result()
            except Exception as exc:  # noqa: BLE001 - one bad module must not abort the build
                failures += 1
                print(f"  skipped {code}: {exc}")
            if done % 250 == 0:
                print(f"  {done}/{len(to_embed)}...")

    elapsed = time.time() - start
    codes = list(by_code.keys())
    matrix = np.stack([by_code[c] for c in codes]).astype(np.float32)
    # Plain str dtype (numpy infers a fixed-width '<U...'), not dtype=object - an
    # object array can only round-trip through np.load with allow_pickle=True,
    # which retrieval.py's runtime load deliberately avoids.
    ids = np.array(codes)

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(INDEX_PATH, ids=ids, vectors=matrix)

    print(f"\nEmbedded {len(to_embed) - failures} more this run ({failures} failed) in {elapsed:.0f}s")
    print(f"Index now covers {len(codes)}/{len(catalogue)} modules")
    print(f"Wrote {INDEX_PATH} ({INDEX_PATH.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
