#!/usr/bin/env python3
"""Paired-bars scoreboard for slide 16.

Five metrics, baseline vs LLM-guided: throughput (tests/CPU-hour),
distinct tests, dedup rate, per-test 3-gram diversity, divergences.
The diversity bar reads low for the LLM-guided run, because "concentration
on the objective" is exactly the steering effect. The divergence column
sits at 0-0 to make the null result land visually alongside the wins.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/results_scoreboard.png"


METRICS = [
    {
        "name": "Throughput",
        "unit": "tests / CPU-hour",
        "baseline": 4587,
        "llm": 54259,
        "ratio": "12× higher",
        "format": "int",
    },
    {
        "name": "Distinct tests",
        "unit": "unique GeneralStateTests",
        "baseline": 989892,
        "llm": 8_563_800,
        "ratio": "8.6× more",
        "format": "int",
    },
    {
        "name": "Dedup rate",
        "unit": "% raw corpus kept",
        "baseline": 53.4,
        "llm": 26.8,
        "ratio": "half (concentrated)",
        "format": "pct",
    },
    {
        "name": "3-gram diversity",
        "unit": "per-test (lower = concentrated)",
        "baseline": 0.275,
        "llm": 0.032,
        "ratio": "8.6× concentrated",
        "format": "float3",
    },
    {
        "name": "Divergences",
        "unit": "post-hoc, geth vs revm",
        "baseline": 0,
        "llm": 0,
        "ratio": "null = null",
        "format": "int",
    },
]


def fmt(v, kind):
    if kind == "int":
        if v >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v/1_000:.0f}k"
        return f"{v}"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "float3":
        return f"{v:.3f}"
    return str(v)


def main() -> int:
    n = len(METRICS)
    fig, axes = plt.subplots(1, n, figsize=(15, 4.6))

    for ax, m in zip(axes, METRICS):
        vals = [m["baseline"], m["llm"]]
        labels = ["baseline", "LLM"]
        colors = ["#6a7a8a", "#c76a3d"]

        ymax = max(vals) if max(vals) > 0 else 1.0
        if m["name"] == "Divergences":
            ymax = 1.0

        x = np.arange(2)
        bars = ax.bar(x, vals, color=colors, width=0.65,
                      edgecolor="white", linewidth=1.5)

        for i, (b, v) in enumerate(zip(bars, vals)):
            if m["name"] == "Divergences":
                ax.text(b.get_x() + b.get_width() / 2, 0.05, "0",
                        ha="center", va="bottom",
                        fontsize=22, color=colors[i], fontweight="bold")
            else:
                ax.text(b.get_x() + b.get_width() / 2,
                        v + ymax * 0.025,
                        fmt(v, m["format"]),
                        ha="center", va="bottom",
                        fontsize=11, color="#222", fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10, color="#333")
        ax.set_yticks([])
        ax.set_ylim(0, ymax * 1.25 if m["name"] != "Divergences" else 1.0)

        ax.set_title(m["name"], fontsize=12, fontweight="bold",
                     color="#222", pad=8)
        ax.text(0.5, -0.18, m["unit"],
                ha="center", va="top", transform=ax.transAxes,
                fontsize=9, color="#555", style="italic")

        ratio_color = "#b03030" if m["name"] == "Divergences" else "#333"
        ax.text(0.5, -0.30, m["ratio"],
                ha="center", va="top", transform=ax.transAxes,
                fontsize=10, color=ratio_color, fontweight="bold")

        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#888")

    fig.suptitle(
        "LLM-guided vs stock-random  ·  216 CPU-hours each, same hardware",
        fontsize=14, y=0.99,
    )
    fig.text(
        0.5, 0.02,
        "Steering is real and measurable. Divergences remain zero on both arms against Cancun geth+revm.",
        ha="center", va="bottom", fontsize=10.5, color="#333", style="italic",
    )

    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
