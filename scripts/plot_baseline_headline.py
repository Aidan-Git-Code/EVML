#!/usr/bin/env python3
"""Headline stats block for slide 15 (Baseline Results).

Six big-number tiles arranged in a 2x3 grid. Plain register, no chart
decoration — the numbers carry the slide.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/baseline_headline.png"


TILES = [
    ("1.26M",    "state-tests generated",      "#3c78b4"),
    ("16h36m",   "wall-clock  ·  215.8 CPU-h", "#3c78b4"),
    ("989,892",  "distinct on disk",           "#3c78b4"),
    ("53.4%",    "dedup rate",                 "#6a7a8a"),
    ("339",      "crashers preserved",         "#6a7a8a"),
    ("0",        "consensus divergences",      "#b03030"),
]


def main() -> int:
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.4))

    for ax, (value, label, color) in zip(axes.flat, TILES):
        ax.axis("off")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.add_patch(FancyBboxPatch(
            (0.04, 0.08), 0.92, 0.84,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            linewidth=1.2, edgecolor="#d0d6dc", facecolor="#f5f7fa",
        ))
        ax.text(0.5, 0.62, value,
                ha="center", va="center",
                fontsize=38, color=color, fontweight="bold")
        ax.text(0.5, 0.30, label,
                ha="center", va="center",
                fontsize=12, color="#444")

    fig.suptitle(
        "Stock-random baseline  ·  16 threads, Cancun, goevmlab post-hoc vs geth+revm",
        fontsize=13, y=0.97,
    )
    fig.text(
        0.5, 0.015,
        "The budget was large. Zero divergences against a mature client pair is the informative part.",
        ha="center", va="bottom", fontsize=10, color="#555", style="italic",
    )

    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
