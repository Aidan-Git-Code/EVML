#!/usr/bin/env python3
"""Build the FAISS index for RAG.

Corpus sources (all under orchestrator/rag/corpus/):
    EIPs/EIPS/*.md   — one chunk per EIP (title + abstract + motivation window)
    opcodes.md       — one chunk per opcode section (## header delimited)

Writes:
    orchestrator/rag/index/vectors.faiss
    orchestrator/rag/index/chunks.jsonl   — [{"id": i, "source": ..., "text": ...}]

Embedding model: BAAI/bge-small-en-v1.5 (384-dim, cosine via normalized IP).
Run once, then rag_faiss.retrieve() reads the on-disk index.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.expanduser("~/models/sentence-transformers"))

CORPUS_ROOT = Path(__file__).resolve().parent / "corpus"
INDEX_ROOT  = Path(__file__).resolve().parent / "index"
INDEX_ROOT.mkdir(parents=True, exist_ok=True)

# Chunk sizing: bge-small caps at 512 tokens. We target ~300 tokens per chunk
# to leave headroom, using a rough 4-chars-per-token proxy.
CHAR_BUDGET = 1200


def _strip_frontmatter(text: str) -> str:
    """EIPs markdown starts with YAML frontmatter fenced by '---'. Keep it —
    it contains eip number, status, title, type, which are great retrieval fodder."""
    return text


def _eip_chunks() -> list[dict]:
    eips_dir = CORPUS_ROOT / "EIPs" / "EIPS"
    if not eips_dir.exists():
        return []
    out = []
    for path in sorted(eips_dir.glob("eip-*.md")):
        raw = path.read_text(errors="ignore")
        # Extract title + abstract/motivation/spec top — the first ~CHAR_BUDGET
        # chars are overwhelmingly the summary. We skip the long 'Backwards
        # Compatibility' / 'Test Cases' / 'References' sections.
        head = _strip_frontmatter(raw)[:CHAR_BUDGET * 2]
        # Coarse split: if the file has a clear 'Abstract' or 'Motivation'
        # section, keep those two; otherwise take the first CHAR_BUDGET.
        m = re.search(r"##\s*Abstract(.+?)(?=\n##\s|\Z)", head, re.S | re.I)
        n = re.search(r"##\s*Motivation(.+?)(?=\n##\s|\Z)", head, re.S | re.I)
        parts = []
        # Always include the first ~600 chars (title + frontmatter + intro)
        parts.append(head[:600])
        if m: parts.append("## Abstract" + m.group(1)[:CHAR_BUDGET])
        if n: parts.append("## Motivation" + n.group(1)[:CHAR_BUDGET])
        chunk_text = "\n\n".join(parts).strip()
        if len(chunk_text) < 60: continue
        out.append({"source": f"EIP/{path.stem}", "text": chunk_text[:CHAR_BUDGET * 2]})
    return out


def _opcode_chunks() -> list[dict]:
    path = CORPUS_ROOT / "opcodes.md"
    if not path.exists(): return []
    raw = path.read_text()
    # Split on `## ` section headers, keeping headers with bodies.
    sections = re.split(r"\n(?=## )", raw)
    out = []
    for sec in sections:
        sec = sec.strip()
        if not sec.startswith("## "): continue
        header = sec.splitlines()[0][3:].strip()
        # Skip the intro-level `## Precompiles (...)` accumulator; it's a list
        # of nested bullets and we still want to index it as one chunk.
        name = header.split()[0]
        out.append({"source": f"opcode/{name}", "text": sec})
    return out


def _incident_chunks() -> list[dict]:
    """Hand-written historical-divergence notes. Same role as rag_stub's
    `incident:*` entries but now indexed for retrieval. These entries help the
    LLM anchor plans in known-divergence classes rather than invent targets."""
    return [
        {"source": "incident/besu-geth-2023-selfdestruct",
         "text": "2023 Shanghai-era cross-client divergence: besu and geth disagreed on SELFDESTRUCT when beneficiary == caller and balance is 0. Surfaces only with specific nested CALL + SELFDESTRUCT sequences. Pre-EIP-6780 behavior."},
        {"source": "incident/revm-modexp-zero-modulus",
         "text": "revm vs geth on MODEXP precompile (0x05) with zero-length modulus: revm returned empty buffer, geth returned a single zero byte. Still a useful target when plans bias callPrecompileGenerator."},
        {"source": "incident/ecrecover-malformed-v",
         "text": "ECRECOVER (precompile 0x01): clients have historically disagreed on v values outside {27, 28}. Some returned zero address, others reverted/consumed full gas. Good fuzz surface for signature edge cases."},
        {"source": "incident/transient-storage-create",
         "text": "During EIP-1153 rollout, multiple clients disagreed on whether TLOAD in a freshly CREATE2'd frame should see the caller's transient store. Current spec: NO, per-account. Fuzz plans that combine createCallGenerator + tloadGenerator can trip clients that implemented this wrong."},
        {"source": "incident/jumpdest-analysis-push-tail",
         "text": "JUMPDEST analysis must ignore 0x5B bytes inside PUSH immediate data. Bug class: truncated code ending inside a PUSH, or code that looks like PUSH32 followed by a JUMPDEST pattern. Fuzz surface: pushGenerator + jumpGenerator + truncated-code paths."},
        {"source": "incident/mcopy-overlap",
         "text": "MCOPY (EIP-5656, Cancun): spec requires memmove semantics (overlap-safe). Some early clients used memcpy and broke on overlapping regions. Ban MCOPY + high mstoreGenerator weight is a productive target for new implementations."},
    ]


def _run_finds_chunks() -> list[dict]:
    """Baseline-run outcome: give the LLM awareness that stock-random has
    already harvested 339 crashers, so its plans should aim at signals random
    did NOT produce (semantic divergence) rather than re-hitting well-known
    crashers."""
    manifest = Path(__file__).resolve().parents[2] / "out" / "crashers" / "manifest.tsv"
    if not manifest.exists(): return []
    count = sum(1 for _ in manifest.open()) - 1  # minus header
    return [{
        "source": "run/baseline-summary",
        "text": (
            f"The stock-random baseline (FuzzyVM for 16h36m, 1.26M state-tests) "
            f"already produced {count} preserved crasher inputs. Those are "
            "predominantly go-fuzz execution-timeouts or native geth cgo "
            "segfaults — they are process-level crashes, NOT cross-client "
            "consensus divergences. LLM-guided plans should target semantic "
            "divergence (state_root_divergence, gas_divergence, storage_divergence) "
            "rather than re-hitting the crash surface stock random already mined."
        ),
    }]


def build_chunks() -> list[dict]:
    chunks: list[dict] = []
    chunks += _eip_chunks()
    chunks += _opcode_chunks()
    chunks += _incident_chunks()
    chunks += _run_finds_chunks()
    for i, c in enumerate(chunks):
        c["id"] = i
    return chunks


def main() -> int:
    print("[build_index] loading bge-small-en-v1.5 ...", flush=True)
    model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    chunks = build_chunks()
    print(f"[build_index] {len(chunks)} chunks "
          f"(EIPs={sum(1 for c in chunks if c['source'].startswith('EIP/'))}, "
          f"opcodes={sum(1 for c in chunks if c['source'].startswith('opcode/'))}, "
          f"incidents={sum(1 for c in chunks if c['source'].startswith('incident/'))}, "
          f"runs={sum(1 for c in chunks if c['source'].startswith('run/'))})", flush=True)

    texts = [c["text"] for c in chunks]
    print("[build_index] embedding ...", flush=True)
    vecs = model.encode(texts, batch_size=32, show_progress_bar=True,
                        normalize_embeddings=True)  # cosine via IP
    vecs = np.asarray(vecs, dtype=np.float32)

    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)
    faiss.write_index(index, str(INDEX_ROOT / "vectors.faiss"))

    with (INDEX_ROOT / "chunks.jsonl").open("w") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"[build_index] wrote {INDEX_ROOT / 'vectors.faiss'} ({vecs.nbytes/1024:.1f} KiB)", flush=True)
    print(f"[build_index] wrote {INDEX_ROOT / 'chunks.jsonl'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
