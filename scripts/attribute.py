#!/usr/bin/env python3
"""Plan-to-divergence attribution for the LLM-guided corpus.

Takes the divergences.jsonl produced by scripts/posthoc_diff.sh and walks
each flaw back to the plan.json that caused it. Buckets results by plan and
by objective so we can answer:

    - Which objectives produced divergences at all?
    - Are the productive objectives the ones the plateau rotator picked,
      or the ones we seeded the loop with?
    - What strategy weights and banned-opcode sets co-occur with flaws?
    - How many plans produced zero divergences (plateau plans)?

Path contract: divergences reference files under
    out/llm_guided/<plan_id>/out/<XX>/FuzzyVM-<hash>.json
so the plan id is the second-to-last-but-two path component. Each plan
directory also contains plan.json written by orchestrator/run_batch.py.

Usage:
    scripts/attribute.py <llm_guided_root> [--divergences path/to/divergences.jsonl]
                                            [--out path/to/attribution.json]

If --divergences is omitted, scripts/attribute.py looks for
out/posthoc_llm_guided/divergences.jsonl.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


PLAN_ID_RE = re.compile(r"(plan_[0-9a-f]+)")


def extract_plan_id(path: str) -> str | None:
    """Find the plan_<hex> component in a state-test file path."""
    parts = Path(path).parts
    for p in parts:
        m = PLAN_ID_RE.fullmatch(p)
        if m:
            return m.group(1)
    m = PLAN_ID_RE.search(path)
    return m.group(1) if m else None


def load_plan(plan_dir: Path) -> dict:
    """Read plan.json from a plan directory, return a compact summary."""
    plan_file = plan_dir / "plan.json"
    if not plan_file.exists():
        return {"plan_id": plan_dir.name, "objective": "<missing plan.json>",
                "fork": None, "banned_opcodes": [], "top_weights": {}}
    try:
        with open(plan_file) as f:
            p = json.load(f)
    except (OSError, ValueError):
        return {"plan_id": plan_dir.name, "objective": "<unreadable>",
                "fork": None, "banned_opcodes": [], "top_weights": {}}
    weights = p.get("strategy_weights", {}) or {}
    top = sorted(weights.items(), key=lambda kv: -(kv[1] or 0))[:5]
    return {
        "plan_id": p.get("plan_id", plan_dir.name),
        "objective": p.get("objective", ""),
        "fork": p.get("fork"),
        "banned_opcodes": p.get("constraints", {}).get("banned_opcodes", []),
        "top_weights": dict(top),
    }


def diff_report_tests(plan_dir: Path) -> int:
    """Read tests_run count from a plan's diff_report.json if present."""
    f = plan_dir / "diff" / "diff_report.json"
    if not f.exists():
        return 0
    try:
        with open(f) as fh:
            return int(json.load(fh).get("tests_run", 0))
    except (OSError, ValueError, TypeError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="llm_guided root, e.g. out/llm_guided")
    ap.add_argument("--divergences", default=None,
                    help="path to divergences.jsonl (default: out/posthoc_llm_guided/divergences.jsonl)")
    ap.add_argument("--out", default=None,
                    help="path to write attribution.json (default: stdout only)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"no such directory: {root}", file=sys.stderr)
        return 2

    div_path = Path(args.divergences) if args.divergences else \
        root.parent / "posthoc_llm_guided" / "divergences.jsonl"

    # Gather every plan directory under the root, even the ones that produced
    # no divergences. That's how we count zero-div plans for the rotation
    # analysis.
    plan_dirs = sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith("plan_")])
    all_plans = {p.name: load_plan(p) for p in plan_dirs}
    tests_by_plan = {p.name: diff_report_tests(p) for p in plan_dirs}

    # Read divergences if the jsonl exists. Missing file is a warning, not
    # fatal: fuzz may still be running.
    divergences: list[dict] = []
    if div_path.exists():
        with open(div_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    divergences.append(json.loads(line))
                except ValueError:
                    pass
    else:
        print(f"warning: no divergences.jsonl at {div_path}", file=sys.stderr)

    # Attribute each divergence to a plan id.
    by_plan: dict[str, list[dict]] = defaultdict(list)
    unattributed: list[dict] = []
    for d in divergences:
        pid = extract_plan_id(d.get("file", ""))
        if pid and pid in all_plans:
            by_plan[pid].append(d)
        else:
            unattributed.append(d)

    # Build per-plan and per-objective summaries.
    plan_rows = {}
    for pid, meta in all_plans.items():
        divs = by_plan.get(pid, [])
        plan_rows[pid] = {
            "objective": meta["objective"],
            "fork": meta["fork"],
            "banned_opcodes": meta["banned_opcodes"],
            "top_weights": meta["top_weights"],
            "tests_run": tests_by_plan.get(pid, 0),
            "divergences": len(divs),
            "divergent_files": [Path(d["file"]).name for d in divs],
        }

    obj_rows: dict[str, dict] = defaultdict(lambda: {
        "plans": [], "plan_count": 0, "divergences": 0, "tests_run": 0,
    })
    for pid, row in plan_rows.items():
        obj = row["objective"]
        bucket = obj_rows[obj]
        bucket["plans"].append(pid)
        bucket["plan_count"] += 1
        bucket["divergences"] += row["divergences"]
        bucket["tests_run"] += row["tests_run"]

    for obj, bucket in obj_rows.items():
        t = bucket["tests_run"]
        bucket["divergences_per_test"] = round(bucket["divergences"] / t, 8) if t else 0.0

    vm_pair = Counter(f"{d.get('vm','?')} vs {d.get('ref_vm','?')}" for d in divergences)

    zero_div_plans = sum(1 for r in plan_rows.values() if r["divergences"] == 0)
    summary = {
        "root": str(root),
        "divergences_file": str(div_path),
        "plans_total": len(plan_rows),
        "plans_with_divergences": len(plan_rows) - zero_div_plans,
        "plans_zero_divergences": zero_div_plans,
        "divergences_total": len(divergences),
        "divergences_unattributed": len(unattributed),
        "divergences_by_vm_pair": dict(vm_pair),
        "objectives": dict(sorted(obj_rows.items(), key=lambda kv: -kv[1]["divergences"])),
        "plans": plan_rows,
    }

    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}", file=sys.stderr)
    # short digest to stdout; full doc only if --out not given
    print(f"plans_total={summary['plans_total']}  "
          f"with_divergences={summary['plans_with_divergences']}  "
          f"zero_div={summary['plans_zero_divergences']}  "
          f"divergences_total={summary['divergences_total']}  "
          f"unattributed={summary['divergences_unattributed']}",
          file=sys.stderr)
    if not args.out:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
