#!/usr/bin/env python3
"""Stacked horizontal bar: anatomy of one LLM-guided batch.

Shows where the ~90-100s per batch goes under --no-diff, 16 threads.
Motivates the 12x throughput claim on slide 16 by making visible that
the LLM overhead is a small slice of the batch, not a bottleneck.
Numbers are the canonical per-batch phase timings from CLAUDE.md
(Day-5-step-2 observed shape).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/batch_anatomy.png"


PHASES = [
    ("Plateau check + RAG",                1.0, "#3c78b4"),
    ("LLM plan (grammar-constrained)",     4.0, "#5a9bd8"),
    ("Validate + launch",                  1.0, "#3c78b4"),
    ("go-fuzz baseline coverage replay",  28.0, "#9aa6b2"),
    ("Active fuzzing (16 workers)",       60.0, "#c76a3d"),
    ("Pgroup kill + testdata wipe",        2.0, "#6a7a8a"),
    ("Inter-batch sleep",                  2.0, "#b5bec8"),
]

INSIDE_IDX = {3, 4}

ABOVE_OFFSETS = {
    0: (-4.0, 1.30),
    1: ( 3.0, 1.65),
    2: (10.0, 1.30),
}
BELOW_OFFSETS = {
    5: (-6.0, -0.50),
    6: ( 8.0, -0.50),
}


def main() -> int:
    total = sum(p[1] for p in PHASES)
    fig, ax = plt.subplots(figsize=(14, 5.0))

    y = 0.5
    h = 0.55
    x_cursor = 0.0
    segments = []
    for i, (name, dur, color) in enumerate(PHASES):
        segments.append((i, x_cursor, dur, name, color))
        x_cursor += dur

    for i, x, dur, name, color in segments:
        ax.add_patch(FancyBboxPatch(
            (x + 0.05, y - h / 2), max(dur - 0.1, 0.4), h,
            boxstyle="round,pad=0.0,rounding_size=0.08",
            linewidth=1.0, edgecolor="white", facecolor=color,
        ))
        center_x = x + dur / 2
        if i in INSIDE_IDX:
            ax.text(center_x, y + 0.05, name,
                    ha="center", va="center",
                    fontsize=11, color="white", fontweight="bold")
            ax.text(center_x, y - 0.13, f"~{dur:g}s",
                    ha="center", va="center",
                    fontsize=10, color="white")
        elif i in ABOVE_OFFSETS:
            dx, ty = ABOVE_OFFSETS[i]
            ax.annotate(
                f"{name}\n~{dur:g}s",
                xy=(center_x, y + h / 2),
                xytext=(center_x + dx, ty),
                ha="center", va="bottom", fontsize=9, color="#222",
                arrowprops=dict(
                    arrowstyle="-", color="#888", linewidth=0.9,
                    connectionstyle="arc3,rad=0.0",
                ),
            )
        elif i in BELOW_OFFSETS:
            dx, ty = BELOW_OFFSETS[i]
            ax.annotate(
                f"{name}\n~{dur:g}s",
                xy=(center_x, y - h / 2),
                xytext=(center_x + dx, ty),
                ha="center", va="top", fontsize=9, color="#222",
                arrowprops=dict(
                    arrowstyle="-", color="#888", linewidth=0.9,
                    connectionstyle="arc3,rad=0.0",
                ),
            )

    ax.annotate(
        f"one batch ≈ {total:.0f}s\n~90k state-tests",
        xy=(total, y), xytext=(total + 4, y),
        ha="left", va="center",
        fontsize=11, color="#222", fontweight="bold",
    )

    ax.set_xlim(-12, total + 22)
    ax.set_ylim(-0.9, 2.0)
    ax.set_yticks([])
    ax.set_xticks(range(0, int(total) + 1, 10))
    ax.set_xlabel("wall-clock seconds", fontsize=10)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#888")
    ax.tick_params(axis="x", colors="#555")

    legend_specs = [
        ("Orchestration  (Python, RAG, LLM)", "#3c78b4"),
        ("Generation  (FuzzyVM + 16 fuzz workers)", "#c76a3d"),
        ("Substrate  (go-fuzz, cleanup, sleep)", "#9aa6b2"),
    ]
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in legend_specs]
    ax.legend(
        handles, [l for l, _ in legend_specs],
        loc="lower left", bbox_to_anchor=(0.0, -0.30),
        ncol=3, frameon=False, fontsize=9.5,
    )

    ax.set_title(
        "Anatomy of one LLM-guided batch  ·  --no-diff mode, 16 threads",
        fontsize=13, pad=12, loc="left",
    )

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
