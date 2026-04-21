#!/usr/bin/env python3
"""Generate two slide-ready visuals for the plateau-rotation mechanism:
  1. out/rotation_timeline.png   : batch-by-batch timeline showing a
     plateau, a rotation, and the rotated objective yielding divergences.
  2. out/rotation_prompt_io.png  : side-by-side prompt I/O for the
     grammar-free rotation call.

Both images use illustrative data built from the real ROTATE_SYSTEM
prompt in orchestrator/rotate.py. The objectives are drawn from the
EIP candidate list in that system prompt so they read as plausible real
output of the pipeline.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


REPO = Path(__file__).resolve().parent.parent
OUT_TL = REPO / "out/rotation_timeline.png"
OUT_IO = REPO / "out/rotation_prompt_io.png"


BATCHES = [
    ("Batch 1", "EIP-1153 TSTORE visibility across DELEGATECALL", 0, False),
    ("Batch 2", "EIP-1153 TSTORE visibility in nested CALL chains", 0, True),
    ("Batch 3", "EIP-2929 warm/cold access accounting on SSTORE refunds", 1, False),
    ("Batch 4", "EIP-2929 cold-access after CREATE2 address collision", 0, False),
    ("Batch 5", "EIP-2929 SLOAD within STATICCALL after warm access", 2, False),
]


def wrap(text: str, width: int = 34) -> str:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def make_timeline() -> None:
    fig, ax = plt.subplots(figsize=(13, 4.2))
    ax.set_xlim(0, len(BATCHES) * 2.4 + 0.3)
    ax.set_ylim(0, 3.0)
    ax.axis("off")

    box_w, box_h = 2.05, 1.7
    x_step = 2.4
    y_box = 0.7

    for i, (label, obj, divs, plateau_fires) in enumerate(BATCHES):
        x = 0.3 + i * x_step
        if divs == 0:
            fc, ec = "#eaeef2", "#6a7a8a"
        else:
            fc, ec = "#fde6d4", "#c76a3d"
        box = FancyBboxPatch(
            (x, y_box), box_w, box_h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=1.4, edgecolor=ec, facecolor=fc,
        )
        ax.add_patch(box)
        ax.text(x + box_w / 2, y_box + box_h - 0.22, label,
                ha="center", va="top", fontsize=11, fontweight="bold", color="#333")
        ax.text(x + box_w / 2, y_box + box_h - 0.55, wrap(obj, 26),
                ha="center", va="top", fontsize=8, color="#222")
        div_label = f"{divs} div" + ("s" if divs != 1 else "")
        ax.text(x + box_w / 2, y_box + 0.18, div_label,
                ha="center", va="bottom", fontsize=10,
                color=("#6a7a8a" if divs == 0 else "#c76a3d"), fontweight="bold")

        if i < len(BATCHES) - 1:
            arrow = FancyArrowPatch(
                (x + box_w + 0.02, y_box + box_h / 2),
                (x + x_step + 0.02, y_box + box_h / 2),
                arrowstyle="->", mutation_scale=14, color="#888", linewidth=1.2,
            )
            ax.add_patch(arrow)

        if plateau_fires:
            ax.annotate(
                "PLATEAU DETECTED (K=2)\nrotate.py proposes new objective",
                xy=(x + box_w + 0.02, y_box + box_h / 2),
                xytext=(x + box_w + x_step / 2, y_box + box_h + 0.45),
                ha="center", va="bottom", fontsize=9, color="#b03030",
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#b03030", linewidth=1.3),
            )

    ax.text(
        0.3, 0.3,
        "Illustrative sequence. Grey = zero divergences, orange = divergences found. "
        "Arrow labeled 'PLATEAU DETECTED' marks where rotate.py fires at K=2.",
        fontsize=8, color="#555", style="italic",
    )
    fig.tight_layout()
    fig.savefig(OUT_TL, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_TL}")


SYSTEM_PROMPT_LINES = [
    "You are an EVM differential-fuzzing research planner.",
    "The user has tried objectives that produced zero divergences.",
    "Propose ONE new objective targeting a DIFFERENT consensus-",
    "sensitive aspect (EIP-2929, EIP-1153, EIP-4844, EOF, precompile",
    "boundaries, CREATE2 collision, ...).",
    "Output ONE LINE, 10-20 words. No prose, no preamble, no quotes.",
]

USER_PROMPT_LINES = [
    "Fork: Cancun",
    "Objectives already tried (0 divergences each):",
    "  - EIP-1153 TSTORE visibility across DELEGATECALL",
    "  - EIP-1153 TSTORE visibility in nested CALL chains",
    "",
    "Propose ONE new objective targeting a distinctly-different aspect.",
]

ASSISTANT_OUTPUT_LINES = [
    "EIP-2929 warm/cold access accounting",
    "on SSTORE refunds under nested DELEGATECALL",
]


def render_block(ax, x, y_top, lines, fontsize, color, line_step=0.043, **kwargs):
    for i, line in enumerate(lines):
        ax.text(x, y_top - i * line_step, line,
                fontsize=fontsize, color=color, family="monospace",
                va="top", **kwargs)
    return y_top - len(lines) * line_step


def make_prompt_io() -> None:
    fig = plt.figure(figsize=(14, 7.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1], height_ratios=[1, 0.18],
                          wspace=0.10, hspace=0.10)

    ax_l = fig.add_subplot(gs[0, 0])
    ax_l.axis("off")
    ax_l.set_xlim(0, 1); ax_l.set_ylim(0, 1)
    ax_l.add_patch(FancyBboxPatch(
        (0.015, 0.03), 0.97, 0.94,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.2, edgecolor="#3c78b4", facecolor="#eef4fb",
    ))
    ax_l.text(0.04, 0.93, "LLM input (grammar-free rotation call)",
              fontsize=13, fontweight="bold", color="#1e4e79")

    ax_l.text(0.04, 0.85, "system", fontsize=10, color="#3c78b4",
              fontweight="bold", family="monospace")
    y_after_system = render_block(
        ax_l, 0.04, 0.81, SYSTEM_PROMPT_LINES, fontsize=9, color="#222",
    )

    ax_l.text(0.04, y_after_system - 0.035, "user", fontsize=10, color="#3c78b4",
              fontweight="bold", family="monospace")
    render_block(
        ax_l, 0.04, y_after_system - 0.075, USER_PROMPT_LINES,
        fontsize=9, color="#222",
    )

    ax_r = fig.add_subplot(gs[0, 1])
    ax_r.axis("off")
    ax_r.set_xlim(0, 1); ax_r.set_ylim(0, 1)
    ax_r.add_patch(FancyBboxPatch(
        (0.015, 0.03), 0.97, 0.94,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.2, edgecolor="#c76a3d", facecolor="#fdeee1",
    ))
    ax_r.text(0.04, 0.93, "LLM output (one line, no grammar)",
              fontsize=13, fontweight="bold", color="#8a4216")
    ax_r.text(0.04, 0.85, "assistant", fontsize=10, color="#c76a3d",
              fontweight="bold", family="monospace")
    render_block(
        ax_r, 0.04, 0.78, ASSISTANT_OUTPUT_LINES,
        fontsize=13, color="#222", line_step=0.055, fontweight="bold",
    )
    ax_r.text(0.04, 0.55, "Used verbatim as the next objective,",
              fontsize=10, color="#555", family="monospace", va="top", style="italic")
    ax_r.text(0.04, 0.50, "feeding back into the RAG + plan",
              fontsize=10, color="#555", family="monospace", va="top", style="italic")
    ax_r.text(0.04, 0.45, "pipeline until plateau detector fires again.",
              fontsize=10, color="#555", family="monospace", va="top", style="italic")

    ax_cap = fig.add_subplot(gs[1, :])
    ax_cap.axis("off")
    ax_cap.text(0.02, 0.55,
                "Prompt text condensed from orchestrator/rotate.py:ROTATE_SYSTEM. "
                "Sampling: temperature 0.8, no JSON grammar, no RAG retrieval.",
                fontsize=9.5, color="#555", style="italic")

    fig.suptitle("Grammar-free rotation call: plateau triggers a fresh objective",
                 fontsize=14, y=0.98)
    fig.savefig(OUT_IO, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_IO}")


def main() -> int:
    OUT_TL.parent.mkdir(parents=True, exist_ok=True)
    make_timeline()
    make_prompt_io()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
