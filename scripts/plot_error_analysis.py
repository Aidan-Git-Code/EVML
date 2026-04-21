#!/usr/bin/env python3
"""2x2 grid of failure modes observed during development (slide 17).

Rows: LLM-side vs Pipeline-side.
Columns: the two representative failures in each category.
Each card shows a one-line symptom, a concrete detail, and the fix.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/error_analysis.png"


CARDS = [
    {
        "row": "LLM-side",
        "title": "Optional field exploited",
        "symptom": "Schema-valid plans with no steering at all.",
        "detail": "`strategy_weights` was optional. Model emitted minimal "
                  "plans satisfying the schema without biasing generation.",
        "fix": "Marked required in plan_schema.json and plan.gbnf.\n"
               "Added a few-shot example showing 5-12 weighted strategies.",
        "color": "#3c78b4",
    },
    {
        "row": "LLM-side",
        "title": "Repeat-key decode loop",
        "symptom": "Generation filled to max_tokens on repeated keys.",
        "detail": "Grammar-constrained decode re-entered the same "
                  "strategy_weights entry until context ran out.",
        "fix": "Enabled dry-sampling (dry_multiplier 0.8) and\n"
               "bounded `sw-entry` to 20 repetitions in the GBNF.",
        "color": "#3c78b4",
    },
    {
        "row": "Pipeline-side",
        "title": "Go-fuzz crasher replay",
        "symptom": "Every batch aborted at ~12s of fuzzing.",
        "detail": "go-fuzz retains every crasher under testdata/ and replays "
                  "it on baseline-coverage phase of the next run.",
        "fix": "Wipe FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/\n"
               "before each batch spawn. Cache at ~/.cache left alone.",
        "color": "#c76a3d",
    },
    {
        "row": "Pipeline-side",
        "title": "Orphaned fuzz workers",
        "symptom": "runtest diffed a directory still being written to.",
        "detail": "SIGTERM to FuzzyVM left its `go test --fuzz` grandchild "
                  "and 16 workers orphaned under /init, still emitting tests.",
        "fix": "start_new_session=True on spawn;\n"
               "os.killpg(pgid, SIGTERM) on timeout and normal exit.",
        "color": "#c76a3d",
    },
]


def main() -> int:
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.4))

    for ax, card in zip(axes.flat, CARDS):
        ax.axis("off")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)

        light = "#eef4fb" if card["color"] == "#3c78b4" else "#fdeee1"
        ax.add_patch(FancyBboxPatch(
            (0.02, 0.04), 0.96, 0.92,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            linewidth=1.3, edgecolor=card["color"], facecolor=light,
        ))

        ax.text(0.05, 0.90, card["row"],
                fontsize=10, color=card["color"],
                fontweight="bold", family="monospace")
        ax.text(0.05, 0.83, card["title"],
                fontsize=14, color="#222", fontweight="bold")

        ax.text(0.05, 0.72, "Symptom",
                fontsize=9, color="#666", fontweight="bold",
                family="monospace")
        ax.text(0.05, 0.66, card["symptom"],
                fontsize=10.5, color="#222", va="top")

        ax.text(0.05, 0.55, "Root cause",
                fontsize=9, color="#666", fontweight="bold",
                family="monospace")
        detail_lines = _wrap(card["detail"], 52)
        for i, line in enumerate(detail_lines):
            ax.text(0.05, 0.49 - i * 0.055, line,
                    fontsize=10, color="#222", va="top")

        y_fix_label = 0.49 - len(detail_lines) * 0.055 - 0.04
        ax.text(0.05, y_fix_label, "Fix",
                fontsize=9, color="#666", fontweight="bold",
                family="monospace")
        for i, line in enumerate(card["fix"].split("\n")):
            ax.text(0.05, y_fix_label - 0.06 - i * 0.055, line,
                    fontsize=10, color="#222", va="top",
                    family="monospace")

    fig.suptitle(
        "Failure modes observed during development  ·  LLM-side (top) vs Pipeline-side (bottom)",
        fontsize=14, y=0.99,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT}")
    return 0


def _wrap(text: str, width: int) -> list[str]:
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
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
