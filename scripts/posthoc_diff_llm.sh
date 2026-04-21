#!/usr/bin/env bash
# Post-hoc differential for the LLM-guided corpus.
#
# The llm_guided tree has 654 plans * ~16 XX shards * ~1000 tests per shard.
# At ~45 s per runtest invocation (dominated by per-invocation VM startup),
# running the stock posthoc_diff.sh on every XX shard projects to 40+ hours.
#
# This script runs ONE runtest per plan with a hash-prefix glob that samples
# 1/16 of each plan's tests (files matching FuzzyVM-0*.json). Because
# FuzzyVM-* filenames embed a content hash prefix, the first-nibble filter is
# a uniform random sample. Output contract matches attribute.py: each plan
# gets <plan>/diff/diff_report.json, and the caller-level divergences.jsonl
# aggregates every divergence with its originating plan path embedded in the
# "file" field.
#
# Usage:
#   scripts/posthoc_diff_llm.sh [--threads N] [--force] [--sample-glob PAT]
#
# Defaults: --threads 16, --sample-glob "*/FuzzyVM-0*.json" (1/16 sample).
# Set --sample-glob "*/FuzzyVM-*.json" for full (no sampling) if time allows.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

ROOT="out/llm_guided"
THREADS=16
FORCE=0
SAMPLE_GLOB="*/FuzzyVM-0*.json"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--threads) THREADS="$2"; shift 2;;
		--force) FORCE=1; shift;;
		--sample-glob) SAMPLE_GLOB="$2"; shift 2;;
		--root) ROOT="$2"; shift 2;;
		*) echo "unknown flag: $1" >&2; exit 2;;
	esac
done

if [[ ! -d "$ROOT" ]]; then
	echo "no such directory: $ROOT" >&2
	exit 2
fi

OUT_DIR="$REPO/out/posthoc_llm_guided"
mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/posthoc.log"
DIVS_JSONL="$OUT_DIR/divergences.jsonl"
: > "$DIVS_JSONL"

PLANS=()
while IFS= read -r -d '' d; do
	PLANS+=("$d")
done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name "plan_*" -print0)

if [[ ${#PLANS[@]} -eq 0 ]]; then
	echo "no plans found under $ROOT" >&2
	exit 2
fi

echo "[posthoc-llm] root=$ROOT plans=${#PLANS[@]} threads=$THREADS sample_glob=$SAMPLE_GLOB out=$OUT_DIR" | tee "$LOG"

PLANS_DONE=0
for plan in "${PLANS[@]}"; do
	if [[ ! -d "$plan/out" ]]; then
		continue
	fi
	report_dir="$plan/diff"
	report="$report_dir/diff_report.json"
	if [[ -f "$report" && "$FORCE" -ne 1 ]]; then
		echo "[posthoc-llm] skip (cached) $plan" | tee -a "$LOG"
	else
		# Quick check: is there at least one file matching the sample glob?
		# If the plan is empty or has too few tests, skip without calling runtest.
		first=$(find "$plan/out" -mindepth 2 -maxdepth 2 -type f -name "FuzzyVM-0*.json" -print -quit 2>/dev/null)
		if [[ -z "$first" ]]; then
			echo "[posthoc-llm] skip (no sample files) $plan" | tee -a "$LOG"
			continue
		fi
		echo "[posthoc-llm] $plan" | tee -a "$LOG"
		python3 orchestrator/differential.py "$plan/out" \
			--threads "$THREADS" \
			--glob "$SAMPLE_GLOB" \
			--diff-dir "$report_dir" >> "$LOG" 2>&1 || true
	fi
	if [[ -f "$report" ]]; then
		python3 - "$report" "$DIVS_JSONL" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    r = json.load(f)
print(json.dumps({
    "plan": r["batch_dir"],
    "tests": r["tests_run"],
    "slow": r["slow_tests"],
    "divergences": len(r["divergences"]),
    "duration_s": r["duration_s"],
}))
with open(sys.argv[2], "a") as out:
    for d in r["divergences"]:
        d["_plan"] = r["batch_dir"]
        out.write(json.dumps(d) + "\n")
PY
		PLANS_DONE=$((PLANS_DONE + 1))
	fi
done | tee -a "$LOG"

# Aggregate summary across all plans.
python3 - "$OUT_DIR" "$ROOT" "$SAMPLE_GLOB" <<'PY'
import json, sys, glob
from pathlib import Path
out_dir = Path(sys.argv[1])
root = sys.argv[2]
sample_glob = sys.argv[3]
reports = []
for p in sorted(glob.glob(f"{root}/plan_*/diff/diff_report.json")):
    with open(p) as f:
        reports.append(json.load(f))

summary = {
    "root": root,
    "sample_glob": sample_glob,
    "plans_with_reports": len(reports),
    "tests_total": sum(r["tests_run"] for r in reports),
    "slow_tests_total": sum(r["slow_tests"] for r in reports),
    "divergences_total": sum(len(r["divergences"]) for r in reports),
    "duration_s_total": round(sum(r["duration_s"] for r in reports), 2),
    "unique_flaw_files": len({d["file"] for r in reports for d in r["divergences"]}),
    "divergences_by_vm_pair": {},
}
for r in reports:
    for d in r["divergences"]:
        key = f"{d['vm']} vs {d['ref_vm']}"
        summary["divergences_by_vm_pair"][key] = summary["divergences_by_vm_pair"].get(key, 0) + 1

(out_dir / "posthoc_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
PY
