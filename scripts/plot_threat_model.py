#!/usr/bin/env python3
"""Threat model grid for slide 18.

Five columns, one per threat category. Two rows: threat (what could go wrong)
and mitigation (what this pipeline does about it). Reads like a compliance
table — matches the IEEE register for a security/ethics slide.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out/threat_model.png"


THREATS = [
    {
        "name": "Dual-use disclosure",
        "threat": "Consensus divergences are exploitable before "
                  "patches ship.",
        "mitigation": "Disclose to client teams via the Ethereum "
                      "Foundation security channel; honor embargoes "
                      "before publication.",
    },
    {
        "name": "Prompt injection via RAG",
        "threat": "An attacker-crafted EIP could steer objective "
                  "generation toward benign targets.",
        "mitigation": "RAG corpus pinned to a known-good commit of "
                      "ethereum/EIPs; no live fetch at inference time.",
    },
    {
        "name": "Hallucinated plans",
        "threat": "Model invents strategy names or opcodes that "
                  "don't exist.",
        "mitigation": "Plan loader rejects unknown strategies and "
                      "invalid opcodes. Hallucinated plans fail "
                      "closed before generation starts.",
    },
    {
        "name": "Energy and resource cost",
        "threat": "Inference at scale has climate impact.",
        "mitigation": "Local Q5_K_M model on a single RTX 4080. "
                      "No hosted API calls. Orders of magnitude below "
                      "frontier-model API usage.",
    },
    {
        "name": "Attribution and abuse",
        "threat": "Same pipeline could be used offensively against "
                  "unpatched clients.",
        "mitigation": "Model is open-weight (Qwen2.5-Coder-7B); "
                      "threat model assumes attackers already have "
                      "equivalent access. Value lives in the "
                      "plumbing, not the model.",
    },
]


def main() -> int:
    n = len(THREATS)
    fig, axes = plt.subplots(n, 2, figsize=(9.5, 12.5),
                              gridspec_kw={"width_ratios": [1, 1.25]})

    for i, t in enumerate(THREATS):
        ax_t = axes[i, 0]
        ax_t.axis("off")
        ax_t.set_xlim(0, 1); ax_t.set_ylim(0, 1)
        ax_t.add_patch(FancyBboxPatch(
            (0.03, 0.06), 0.94, 0.88,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            linewidth=1.3, edgecolor="#8a4216", facecolor="#fdeee1",
        ))
        ax_t.text(0.06, 0.84, "THREAT",
                  fontsize=9, color="#8a4216", fontweight="bold",
                  family="monospace")
        ax_t.text(0.06, 0.70, t["name"],
                  fontsize=13, color="#222", fontweight="bold")
        for j, line in enumerate(_wrap(t["threat"], 38)):
            ax_t.text(0.06, 0.52 - j * 0.13, line,
                      fontsize=10.5, color="#333", va="top")

        ax_m = axes[i, 1]
        ax_m.axis("off")
        ax_m.set_xlim(0, 1); ax_m.set_ylim(0, 1)
        ax_m.add_patch(FancyBboxPatch(
            (0.03, 0.06), 0.94, 0.88,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            linewidth=1.3, edgecolor="#3c78b4", facecolor="#eef4fb",
        ))
        ax_m.text(0.05, 0.84, "MITIGATION",
                  fontsize=9, color="#1e4e79", fontweight="bold",
                  family="monospace")
        for j, line in enumerate(_wrap(t["mitigation"], 48)):
            ax_m.text(0.05, 0.70 - j * 0.11, line,
                      fontsize=10.5, color="#222", va="top")

    fig.suptitle(
        "Security and ethical analysis  ·  threat → mitigation",
        fontsize=14, y=0.995,
    )
    fig.text(
        0.5, 0.012,
        "Responsible disclosure, pinned corpus, fail-closed validation,\n"
        "local-only inference, and an open-weight threat model.",
        ha="center", va="bottom", fontsize=9.5, color="#555", style="italic",
    )

    fig.tight_layout(rect=(0, 0.05, 1, 0.975))
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
