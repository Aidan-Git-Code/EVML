#!/usr/bin/env python3
"""Grouped bar chart: opcode emission frequency, stock FuzzyVM vs plan-driven.

Reads dump output from `./FuzzyVM dump --count N` (stock) and
`./FuzzyVM dump --count N --plan plan.json` (plan-driven), plots a
grouped bar chart for a curated set of opcodes, and writes a PNG.

Usage:
    FuzzyVM/FuzzyVM dump --count 100 > /tmp/dump_stock.txt
    FuzzyVM/FuzzyVM dump --count 100 --plan PLAN > /tmp/dump_plan.txt
    scripts/plot_opcode_bias.py /tmp/dump_stock.txt /tmp/dump_plan.txt out/opcode_bias.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_dump(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, num = parts
        if not num.isdigit():
            continue
        if name == "COUNT":
            continue
        counts[name] = int(num)
    return counts


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2

    stock = parse_dump(Path(sys.argv[1]))
    plan = parse_dump(Path(sys.argv[2]))
    out_png = Path(sys.argv[3])

    opcodes = [
        "TSTORE",
        "TLOAD",
        "DELEGATECALL",
        "CALL",
        "MSTORE",
        "SSTORE",
        "SELFDESTRUCT",
        "BLOCKHASH",
    ]
    stock_vals = [stock.get(op, 0) for op in opcodes]
    plan_vals = [plan.get(op, 0) for op in opcodes]

    x = np.arange(len(opcodes))
    w = 0.38

    fig, ax = plt.subplots(figsize=(10, 5.5))
    b1 = ax.bar(x - w / 2, stock_vals, w, label="Stock FuzzyVM", color="#6a7a8a")
    b2 = ax.bar(x + w / 2, plan_vals, w, label="Plan-driven (EIP-1153 TSTORE)", color="#c76a3d")

    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylabel("Emission count per 100 programs (symlog)")
    ax.set_xticks(x)
    ax.set_xticklabels(opcodes, rotation=20, ha="right")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.25, which="both")
    ax.set_axisbelow(True)

    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            label = f"{int(h):,}" if h > 0 else "0"
            ax.annotate(
                label,
                xy=(rect.get_x() + rect.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_title("Plan-driven generation biases strategy output\n(300 programs each, symlog y-axis)")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    print(f"wrote {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
