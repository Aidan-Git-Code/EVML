#!/usr/bin/env bash
# Run differential.py against a single LLM-guided plan with the 1/16
# hash-prefix sample, write the per-plan summary line to a shared log,
# and append divergences to a shared JSONL. Safe for concurrent use
# under xargs/parallel: each plan's diff dir is disjoint, and the
# shared log/jsonl are appended line-by-line (short writes on Linux
# are atomic up to PIPE_BUF, which comfortably covers our lines).
#
# Usage: diff_one_plan.sh <plan_dir>

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

plan="$1"
if [[ ! -d "$plan/out" ]]; then
	exit 0
fi

THREADS="${DIFF_THREADS:-4}"
OUT_DIR="$REPO/out/posthoc_llm_guided"
mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/posthoc.log"
DIVS_JSONL="$OUT_DIR/divergences.jsonl"
SAMPLE_GLOB="*/FuzzyVM-0*.json"

report_dir="$plan/diff"
report="$report_dir/diff_report.json"
if [[ -f "$report" ]]; then
	echo "[llm-diff] skip (cached) $plan" >> "$LOG"
else
	first=$(find "$plan/out" -mindepth 2 -maxdepth 2 -type f -name "FuzzyVM-0*.json" -print -quit 2>/dev/null)
	if [[ -z "$first" ]]; then
		echo "[llm-diff] skip (no sample files) $plan" >> "$LOG"
		exit 0
	fi
	echo "[llm-diff] start $plan" >> "$LOG"
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
fi
