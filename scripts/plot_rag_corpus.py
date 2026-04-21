#!/usr/bin/env python3
"""Generate two slide-ready visuals for the RAG corpus:
  1. out/rag_embedding_2d.png  : 2D t-SNE projection of the FAISS index,
     colored by corpus category. Shows that embeddings cluster by topic.
  2. out/rag_corpus_donut.png  : donut chart of corpus composition.

Reads orchestrator/rag/index/{vectors.faiss,chunks.jsonl}.
"""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE


REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "orchestrator/rag/index/vectors.faiss"
CHUNKS = REPO / "orchestrator/rag/index/chunks.jsonl"
OUT_2D = REPO / "out/rag_embedding_2d.png"
OUT_DONUT = REPO / "out/rag_corpus_donut.png"

CATEGORIES = [
    ("EIPs", "#3c78b4"),
    ("Opcode reference", "#c76a3d"),
    ("Historical incidents", "#6aa84f"),
    ("Baseline summary", "#8a4fa8"),
]


def categorize(source: str) -> str:
    if source.startswith("EIP/"):
        return "EIPs"
    if source.startswith("opcode") or source == "opcodes.md":
        return "Opcode reference"
    if "incident" in source.lower() or "historical" in source.lower():
        return "Historical incidents"
    if "baseline" in source.lower():
        return "Baseline summary"
    return "EIPs"


def main() -> int:
    index = faiss.read_index(str(INDEX))
    n = index.ntotal
    dim = index.d
    vecs = np.zeros((n, dim), dtype=np.float32)
    index.reconstruct_n(0, n, vecs)

    sources = []
    with open(CHUNKS) as f:
        for line in f:
            sources.append(json.loads(line)["source"])
    assert len(sources) == n, f"chunk/vector mismatch: {len(sources)} vs {n}"

    labels = [categorize(s) for s in sources]

    print(f"projecting {n} vectors of dim {dim} to 2D via PCA(50) + t-SNE(2) ...")
    pca = PCA(n_components=50, random_state=0).fit_transform(vecs)
    coords = TSNE(
        n_components=2,
        perplexity=30,
        init="pca",
        learning_rate="auto",
        random_state=0,
        max_iter=1000,
    ).fit_transform(pca)

    fig, ax = plt.subplots(figsize=(9, 6.5))
    for cat, color in CATEGORIES:
        mask = np.array([lab == cat for lab in labels])
        if not mask.any():
            continue
        ax.scatter(
            coords[mask, 0],
            coords[mask, 1],
            s=18 if cat == "EIPs" else 55,
            alpha=0.55 if cat == "EIPs" else 0.95,
            label=f"{cat} (n={mask.sum()})",
            color=color,
            edgecolors="white" if cat != "EIPs" else "none",
            linewidths=0.5,
        )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title(
        "RAG corpus in 2D (t-SNE of 384-dim BGE embeddings)\n"
        "EIPs cluster by topic; opcode reference and incident notes sit at the edges"
    )
    ax.legend(loc="lower left", framealpha=0.95)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT_2D, dpi=160)
    print(f"wrote {OUT_2D}")

    counts = {cat: sum(1 for lab in labels if lab == cat) for cat, _ in CATEGORIES}
    donut_values = [counts[cat] for cat, _ in CATEGORIES]
    donut_colors = [c for _, c in CATEGORIES]
    total = sum(donut_values)

    fig2, ax2 = plt.subplots(figsize=(8, 6))
    wedges, _ = ax2.pie(
        donut_values,
        colors=donut_colors,
        startangle=90,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
    )
    ax2.text(
        0, 0.08, f"{total}",
        ha="center", va="center", fontsize=34, fontweight="bold", color="#333",
    )
    ax2.text(0, -0.15, "chunks", ha="center", va="center", fontsize=13, color="#555")
    legend_labels = [
        f"{cat}  —  n={counts[cat]}  ({100*counts[cat]/total:.1f}%)"
        for cat, _ in CATEGORIES
    ]
    ax2.legend(
        wedges,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        fontsize=11,
    )
    ax2.set_title("RAG corpus composition", pad=18, fontsize=14)
    fig2.tight_layout()
    fig2.savefig(OUT_DONUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_DONUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
