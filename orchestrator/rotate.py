"""Plateau detection + objective rotation.

If the last K LLM-guided batches under out/llm_guided/ all produced zero
divergences, we're plateaued on the current objective space. Ask the LLM
to propose a NEW objective that targets a distinctly-different consensus-
sensitive aspect, and feed that back into the pipeline.

Modeled after fuzzillai's EBG_plateau.py: "evolve by generating" when the
current trajectory stalls. Cheap insurance against spending a long run on
an objective the current client pair can't distinguish.

Standalone CLI:
    python3 orchestrator/rotate.py \\
        --out-root out/llm_guided --k 3 --current "EIP-1153 TSTORE visibility"
The script prints the objective to use (rotated, or --current if no plateau).
Used by run_batch.py and by a future loop driver.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests


ROTATE_SYSTEM = """You are an EVM differential-fuzzing research planner.

The user is looking for consensus bugs between EVM client implementations. They've tried several objectives in a row that produced zero divergences. Your job: propose ONE new objective that targets a DIFFERENT consensus-sensitive aspect of EVM semantics.

Pick from (but not limited to): memory-expansion edge cases, precompile boundary inputs (MODEXP, BN256, RIPEMD160), CREATE2 address collision, gas-refund edges (SSTORE, SELFDESTRUCT), static-context violations, blob-tx/EIP-4844 gas accounting, EOF (EIP-3540/3670) validation mismatches, jumpdest-analysis edge cases, return-data truncation across nested calls, warm/cold access accounting (EIP-2929), transient storage scoping (EIP-1153).

Output ONE LINE: a short objective (10-20 words) mentioning a specific EIP or opcode. No prose, no preamble, no quotes, no markdown."""


def detect_plateau(out_root: Path, k: int = 3) -> list[str]:
    """Return the last k objectives if they all had 0 divergences, else []."""
    if k <= 0 or not out_root.exists():
        return []
    candidates = [p for p in out_root.iterdir() if p.is_dir() and p.name.startswith("plan_")]
    # Only count batches that actually ran differential (have diff_report.json).
    with_reports: list[tuple[float, Path]] = []
    for d in candidates:
        rpt_path = d / "diff" / "diff_report.json"
        plan_path = d / "plan.json"
        if rpt_path.exists() and plan_path.exists():
            with_reports.append((rpt_path.stat().st_mtime, d))
    with_reports.sort(key=lambda t: t[0], reverse=True)
    recent = with_reports[:k]
    if len(recent) < k:
        return []  # Not enough completed batches yet.

    objectives: list[str] = []
    for _, d in recent:
        try:
            rpt = json.loads((d / "diff" / "diff_report.json").read_text())
            plan = json.loads((d / "plan.json").read_text())
        except (OSError, json.JSONDecodeError):
            return []
        if len(rpt.get("divergences", [])) > 0:
            return []  # Not a plateau: at least one batch found something.
        objectives.append(plan.get("objective", ""))
    return objectives


def propose_objective(llm_url: str, plateaued: list[str], fork: str,
                      temperature: float = 0.8, max_tokens: int = 80) -> str:
    """Ask the LLM for a new objective distinct from the plateaued ones."""
    body = "\n".join(f"- {o}" for o in plateaued)
    user = (f"Fork: {fork}\n"
            f"Objectives already tried that produced zero divergences:\n{body}\n\n"
            f"Propose ONE new objective targeting a distinctly-different aspect.")
    # ChatML template (matches run_batch.call_llm), no grammar.
    prompt = (
        f"<|im_start|>system\n{ROTATE_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    payload = {
        "prompt": prompt,
        "temperature": temperature,
        "top_p": 0.95,
        "n_predict": max_tokens,
        "stop": ["<|im_end|>", "<|endoftext|>", "\n"],
        "cache_prompt": False,  # different prompt each rotation
        "repeat_penalty": 1.1,
    }
    r = requests.post(llm_url.rstrip("/") + "/completion", json=payload, timeout=120)
    r.raise_for_status()
    text = r.json().get("content", "").strip()
    # Strip leading list markers and surrounding quotes the model sometimes adds.
    text = text.lstrip("-*> ").strip().strip('"').strip("'")
    # Collapse whitespace, keep single line.
    text = " ".join(text.split())
    return text


def resolve(out_root: Path, current: str, k: int, llm_url: str, fork: str) -> tuple[str, bool]:
    """Return (objective_to_use, rotated?). If plateau detected, rotate; else keep current."""
    plateaued = detect_plateau(out_root, k)
    if not plateaued:
        return current, False
    new_obj = propose_objective(llm_url, plateaued, fork)
    if not new_obj or new_obj == current:
        return current, False
    return new_obj, True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True, type=Path)
    ap.add_argument("--current", required=True, help="Current (proposed) objective")
    ap.add_argument("--k", type=int, default=3, help="Plateau window")
    ap.add_argument("--fork", default="Cancun")
    ap.add_argument("--llm-url", default="http://127.0.0.1:8080")
    ap.add_argument("--quiet", action="store_true", help="Print only the resolved objective")
    args = ap.parse_args()

    obj, rotated = resolve(args.out_root, args.current, args.k, args.llm_url, args.fork)
    if not args.quiet:
        if rotated:
            print(f"[rotate] plateau detected; rotated objective", file=sys.stderr)
        else:
            print(f"[rotate] no plateau; keeping current objective", file=sys.stderr)
    print(obj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
