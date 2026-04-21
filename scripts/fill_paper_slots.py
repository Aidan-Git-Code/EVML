#!/usr/bin/env python3
r"""Read posthoc + attribution outputs and print every \NUM{} value
needed to finish paper.tex. Run this once both posthoc_diff passes
have produced their summary JSON and attribute.py has written
attribution.json.

Usage:
    scripts/fill_paper_slots.py > out/paper_fills.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def load(p: Path) -> dict:
    if not p.exists():
        print(f"WARN: missing {p}", file=sys.stderr)
        return {}
    with open(p) as f:
        return json.load(f)


def main() -> int:
    baseline = load(REPO / "out/posthoc_baseline/posthoc_summary.json")
    llm = load(REPO / "out/posthoc_llm_guided/posthoc_summary.json")
    attrib = load(REPO / "out/attribution.json")

    baseline_cpuh = 215.8
    llm_cpuh = 216.0
    llm_tests_total = 11_719_896

    baseline_div = baseline.get("divergences_total", 0)
    llm_div = llm.get("divergences_total", 0)
    sample_frac = 1 / 16  # posthoc_diff_llm.sh samples 1/16 by hash prefix
    llm_div_extrapolated = round(llm_div / sample_frac)

    baseline_rate = baseline_div / baseline_cpuh
    llm_rate = llm_div_extrapolated / llm_cpuh
    ratio = (llm_rate / baseline_rate) if baseline_rate else float("inf")

    out: dict[str, str] = {}
    out["baseline-div"] = f"{baseline_div}"
    out["baseline-div-per-cpuh"] = f"{baseline_rate:.3f}"
    out["llm-div"] = f"{llm_div_extrapolated} (extrapolated from a 1/16 hash-prefix sample that observed {llm_div} divergences)"
    out["llm-div-per-cpuh"] = f"{llm_rate:.3f}"
    out["div-rate-ratio"] = (f"{ratio:.2f}$\\times$" if baseline_rate else "(undefined; baseline rate zero)")

    if attrib:
        plans_with = attrib.get("plans_with_divergences", 0)
        plans_zero = attrib.get("plans_zero_divergences", 0)
        out["llm-plans-with-div"] = f"{plans_with}"
        out["llm-plans-zero-div"] = f"{plans_zero}"

        # top-N objectives
        objectives = attrib.get("objectives", {})
        # attribute.py sorts by -divergences in its summary
        obj_items = list(objectives.items())[:5]
        for i, (obj, bucket) in enumerate(obj_items, 1):
            out[f"obj-row-{i}"] = f"{obj} & {bucket['tests_run']:,} & {bucket['divergences']}"
            if i == 1:
                out["top-objective-1"] = obj
                out["top-objective-1-count"] = str(bucket["divergences"])
            if i == 2:
                out["top-objective-2"] = obj
                out["top-objective-2-count"] = str(bucket["divergences"])
        # pad unused rows
        for i in range(len(obj_items) + 1, 6):
            out[f"obj-row-{i}"] = "-- & -- & --"

        vm_pair = attrib.get("divergences_by_vm_pair", {})
        parts = [f"{v} {k}" for k, v in sorted(vm_pair.items(), key=lambda kv: -kv[1])]
        out["vm-pair-breakdown"] = ", ".join(parts) or "no divergences"

        # zero-div tests pct of total budget
        plan_rows = attrib.get("plans", {})
        zero_div_tests = sum(r["tests_run"] for r in plan_rows.values() if r["divergences"] == 0)
        all_tests = sum(r["tests_run"] for r in plan_rows.values()) or 1
        pct = 100 * zero_div_tests / all_tests
        out["zero-div-tests-pct"] = f"{pct:.1f}"

    # Discussion
    if baseline_div == 0 and llm_div == 0:
        out["outcome-category"] = "null"
        out["discussion-summary-one-line"] = (
            "Over equal 13h30m CPU budgets, neither arm produced any geth/revm divergences; "
            "the LLM-guided arm generated an order of magnitude more state-tests at a concentrated per-test $n$-gram distribution"
        )
    elif llm_rate > baseline_rate and baseline_div > 0:
        out["outcome-category"] = "expected-useful"
        out["discussion-summary-one-line"] = (
            f"The LLM-guided arm produced a {ratio:.2f}$\\times$ higher divergences-per-CPU-hour rate than the baseline"
        )
    elif llm_rate <= baseline_rate and baseline_div > 0:
        out["outcome-category"] = "null-or-worse"
        out["discussion-summary-one-line"] = (
            "The LLM-guided arm did not exceed the baseline's divergences-per-CPU-hour rate at this CPU budget"
        )
    else:
        out["outcome-category"] = "llm-only-positive"
        out["discussion-summary-one-line"] = (
            f"The LLM-guided arm produced {llm_div_extrapolated} divergences while the baseline produced zero, "
            f"giving an undefined rate ratio but an absolute positive finding for the biased arm"
        )

    for k, v in out.items():
        print(f"{k}\t{v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
