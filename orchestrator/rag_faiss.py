"""FAISS-backed retriever. Drop-in replacement for rag_stub.

Loads the persisted index produced by orchestrator/rag/build_index.py lazily
(first call) so importing this module is cheap.

Public API mirrors rag_stub: retrieve(objective, k) -> list[Snippet];
format_context(snippets) -> str. run_batch.py can swap imports with no other
changes.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.expanduser("~/models/sentence-transformers"))

INDEX_ROOT = Path(__file__).resolve().parent / "rag" / "index"
VECTORS_PATH = INDEX_ROOT / "vectors.faiss"
CHUNKS_PATH = INDEX_ROOT / "chunks.jsonl"

_lock = threading.Lock()
_model = None
_index = None
_chunks: list[dict] | None = None


@dataclass(frozen=True)
class Snippet:
    source: str
    text: str


def _ensure_loaded() -> None:
    global _model, _index, _chunks
    if _model is not None and _index is not None and _chunks is not None:
        return
    with _lock:
        if _model is not None: return
        if not VECTORS_PATH.exists() or not CHUNKS_PATH.exists():
            raise FileNotFoundError(
                f"FAISS index not built. Run `python3 orchestrator/rag/build_index.py` first. "
                f"Expected: {VECTORS_PATH}"
            )
        import faiss
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        _index = faiss.read_index(str(VECTORS_PATH))
        with CHUNKS_PATH.open() as f:
            _chunks = [json.loads(line) for line in f if line.strip()]


def retrieve(objective: str, k: int = 6) -> list[Snippet]:
    _ensure_loaded()
    # bge-small retrieval convention: query prefix for instruction tuning.
    query = "Represent this sentence for searching relevant passages: " + objective
    import numpy as np
    q = _model.encode([query], normalize_embeddings=True)
    q = np.asarray(q, dtype="float32")
    D, I = _index.search(q, k)
    out: list[Snippet] = []
    for idx in I[0]:
        if idx < 0: continue
        c = _chunks[idx]
        # Clip per-chunk for prompt budget — the builder chunks to ~CHAR_BUDGET*2
        # (2400 chars); retrieval keeps the first 1200 to stay tight in prompt.
        out.append(Snippet(source=c["source"], text=c["text"][:1200]))
    return out


def format_context(snippets: list[Snippet]) -> str:
    return "\n\n".join(f"[{s.source}] {s.text}" for s in snippets)
