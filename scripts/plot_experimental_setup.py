#!/usr/bin/env python3
"""Side-by-side run comparison for slide 13.

Two horizontal bars on the same wall-clock x-axis: stock-random baseline
vs LLM-guided --no-diff run. Emphasizes equal CPU budget (~216 CPU-hours)
with a 12x difference in test volume and a 0-0 divergence outcome.
Numbers sourced from CLAUDE.md and the post-hoc summaries.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/experimental_setup.png"


RUNS = [
    {
        "name": "Stock-random baseline",
        "subtitle": "FuzzyVM unmodified",
        "hours": 16.6,
        "cpu_hours": 215.8,
        "tests": 1_260_000,
        "distinct": 989_892,
        "throughput": 4587,
        "extras": "339 crashers preserved",
        "divergences": 0,
        "color": "#6a7a8a",
        "text_color": "white",
    },
    {
        "name": "LLM-guided (--no-diff)",
        "subtitle": "Qwen2.5-Coder-7B + RAG, 654 plans",
        "hours": 13.5,
        "cpu_hours": 216.0,
        "tests": 11_700_000,
        "distinct": 8_563_800,
        "throughput": 54_259,
        "extras": "676 batches · 90s each",
        "divergences": 0,
        "color": "#c76a3d",
        "text_color": "white",
    },
]


def fmt_tests(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return f"{n}"


def main() -> int:
    fig, ax = plt.subplots(figsize=(14, 5.2))

    max_hours = max(r["hours"] for r in RUNS)
    row_y = [2.0, 0.7]
    h = 0.65

    for run, y in zip(RUNS, row_y):
        ax.add_patch(FancyBboxPatch(
            (0.05, y - h / 2), run["hours"] - 0.1, h,
            boxstyle="round,pad=0.0,rounding_size=0.10",
            linewidth=1.2, edgecolor="white", facecolor=run["color"],
        ))
        ax.text(
            0.3, y + 0.10, run["name"],
            ha="left", va="center",
            fontsize=12, color=run["text_color"], fontweight="bold",
        )
        ax.text(
            0.3, y - 0.13, run["subtitle"],
            ha="left", va="center",
            fontsize=9.5, color=run["text_color"], style="italic",
        )

        ax.text(
            run["hours"] - 0.2, y + 0.10, f"{fmt_tests(run['tests'])} tests",
            ha="right", va="center",
            fontsize=13, color=run["text_color"], fontweight="bold",
        )
        ax.text(
            run["hours"] - 0.2, y - 0.15,
            f"{run['throughput']:,} / CPU-hour",
            ha="right", va="center",
            fontsize=10, color=run["text_color"],
        )

    ax.annotate(
        "16h36m wall-clock · 215.8 CPU-hours\n"
        f"{RUNS[0]['distinct']:,} distinct on disk · 339 crashers",
        xy=(RUNS[0]["hours"] / 2, row_y[0] + h / 2),
        xytext=(RUNS[0]["hours"] / 2, row_y[0] + h / 2 + 0.55),
        ha="center", va="bottom", fontsize=9.5, color="#333",
        arrowprops=dict(arrowstyle="-", color="#888", linewidth=0.9),
    )
    ax.annotate(
        "13h30m wall-clock · 216.0 CPU-hours\n"
        f"{RUNS[1]['distinct']:,} distinct · 654 plans · 676 batches",
        xy=(RUNS[1]["hours"] / 2, row_y[1] - h / 2),
        xytext=(RUNS[1]["hours"] / 2, row_y[1] - h / 2 - 0.55),
        ha="center", va="top", fontsize=9.5, color="#333",
        arrowprops=dict(arrowstyle="-", color="#888", linewidth=0.9),
    )

    ax.text(
        max_hours + 0.5, (row_y[0] + row_y[1]) / 2, "12×\nmore\ntests",
        ha="left", va="center",
        fontsize=16, color="#b03030", fontweight="bold",
    )
    ax.annotate(
        "",
        xy=(max_hours + 0.4, row_y[0]),
        xytext=(max_hours + 0.4, row_y[1]),
        arrowprops=dict(
            arrowstyle="<->", color="#b03030", linewidth=1.6,
        ),
    )

    ax.text(
        max_hours / 2, -0.8,
        "Post-hoc differential pass (geth evm vs revm revme, Cancun):  "
        "baseline 0 divergences over 866,813-test shard sweep  ·  "
        "LLM-guided 0 divergences over 472,713-test 1/16 hash-prefix sample",
        ha="center", va="top",
        fontsize=10, color="#333", style="italic",
    )

    ax.set_xlim(-0.3, max_hours + 3.5)
    ax.set_ylim(-1.3, 3.2)
    ax.set_yticks([])
    ax.set_xticks(range(0, int(max_hours) + 2, 2))
    ax.set_xlabel("wall-clock hours", fontsize=10)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#888")
    ax.tick_params(axis="x", colors="#555")

    ax.set_title(
        "Equal CPU budget, different corpus shape  "
        "·  16 threads, Cancun, same FuzzyVM binary",
        fontsize=13, pad=12, loc="left",
    )

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
