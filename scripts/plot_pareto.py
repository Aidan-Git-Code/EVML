#!/usr/bin/env python3
"""Design-tension Pareto chart for slide 19 (portrait).

Two axes that capture the tradeoff:
  X = test throughput (tests / CPU-hour)
  Y = rotation-detector signal quality (0 = none, 1 = full)

Two real points from this project and two projections. The star marks
the Pareto-better point that sparse-inline-diff would unlock.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/pareto_design_tension.png"


def main() -> int:
    fig, ax = plt.subplots(figsize=(7.2, 9.4))

    points = [
        {"label": "Stock-random\nbaseline",          "x": 4587,  "y": 0.00,
         "color": "#6a7a8a", "kind": "real"},
        {"label": "LLM + inline diff\n(projected)",  "x": 12000, "y": 0.95,
         "color": "#8a4fa8", "kind": "projected"},
        {"label": "LLM, --no-diff\n(this paper)",    "x": 54259, "y": 0.00,
         "color": "#c76a3d", "kind": "real"},
        {"label": "Sparse inline diff\n(next step)", "x": 48000, "y": 0.65,
         "color": "#2a8f4f", "kind": "star"},
    ]

    for p in points:
        if p["kind"] == "star":
            ax.scatter(p["x"], p["y"], s=650, marker="*",
                       color=p["color"], edgecolors="white", linewidths=1.8,
                       zorder=5)
        elif p["kind"] == "projected":
            ax.scatter(p["x"], p["y"], s=260, marker="o",
                       color="white", edgecolors=p["color"], linewidths=2.2,
                       zorder=4)
        else:
            ax.scatter(p["x"], p["y"], s=260, marker="o",
                       color=p["color"], edgecolors="white", linewidths=1.5,
                       zorder=4)

    offsets = [
        (-12000, 0.07),
        (-5000, -0.13),
        (-19000, -0.13),
        (-9000, 0.10),
    ]
    for p, (dx, dy) in zip(points, offsets):
        ax.annotate(
            p["label"],
            xy=(p["x"], p["y"]),
            xytext=(p["x"] + dx, p["y"] + dy),
            fontsize=11, color="#222", fontweight="bold",
            ha="left", va="center",
        )

    ax.plot(
        [points[2]["x"], points[3]["x"]],
        [points[2]["y"], points[3]["y"]],
        linestyle="--", color="#2a8f4f", linewidth=1.6, alpha=0.7, zorder=2,
    )
    ax.plot(
        [points[1]["x"], points[3]["x"]],
        [points[1]["y"], points[3]["y"]],
        linestyle="--", color="#2a8f4f", linewidth=1.6, alpha=0.7, zorder=2,
    )

    ax.annotate(
        "better",
        xy=(58000, 0.85), xytext=(58000, 0.85),
        fontsize=10, color="#2a8f4f", fontweight="bold",
        ha="right", va="center",
    )
    ax.annotate(
        "",
        xy=(58000, 0.90), xytext=(50000, 0.40),
        arrowprops=dict(arrowstyle="->", color="#2a8f4f", linewidth=1.6),
    )

    ax.set_xlim(0, 65000)
    ax.set_ylim(-0.18, 1.1)
    ax.set_xlabel("throughput  (tests / CPU-hour)",
                  fontsize=11, color="#333")
    ax.set_ylabel("rotation-detector signal  (0 = none · 1 = full)",
                  fontsize=11, color="#333")
    ax.set_xticks([0, 10000, 20000, 30000, 40000, 50000, 60000])
    ax.set_xticklabels(["0", "10k", "20k", "30k", "40k", "50k", "60k"])
    ax.set_yticks([0.0, 0.5, 1.0])

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#888")
    ax.spines["bottom"].set_color("#888")
    ax.tick_params(colors="#555")
    ax.grid(alpha=0.15, linestyle="--")
    ax.set_axisbelow(True)

    ax.set_title(
        "Design tension:\nthroughput vs rotation signal",
        fontsize=15, pad=16, color="#222", fontweight="bold", loc="left",
    )

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
