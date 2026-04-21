#!/usr/bin/env bash
# Post-hoc differential sweep over a FuzzyVM state-test corpus.
#
# goevmlab's runtest aborts on the first consensus flaw it sees, so a single
# invocation over 1M tests is not useful. This script shards the corpus by
# its 2-level subdirectory layout (XX/YY/FuzzyVM-*.json), calls
# orchestrator/differential.py per shard, and aggregates the results into
# one summary JSON. Re-runtable: a shard already holding a diff_report.json
# is skipped unless --force is passed.
#
# Usage:
#   scripts/posthoc_diff.sh <corpus_root> [--threads N] [--force]
#
# Example:
#   scripts/posthoc_diff.sh out/baseline --threads 8
#   scripts/posthoc_diff.sh out/llm_guided --threads 8
#
# The LLM-guided corpus is nested one level deeper (plan_<id>/out/XX/),
# so the script detects that shape and iterates plans × subdirs.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if [[ $# -lt 1 ]]; then
	echo "usage: $0 <corpus_root> [--threads N] [--force]" >&2
	exit 2
fi

ROOT="$1"
shift

THREADS=4
FORCE=0
while [[ $# -gt 0 ]]; do
	case "$1" in
		--threads) THREADS="$2"; shift 2;;
		--force) FORCE=1; shift;;
		*) echo "unknown flag: $1" >&2; exit 2;;
	esac
done

if [[ ! -d "$ROOT" ]]; then
	echo "no such directory: $ROOT" >&2
	exit 2
fi

OUT_DIR="$REPO/out/posthoc_$(basename "$ROOT")"
mkdir -p "$OUT_DIR"
AGG="$OUT_DIR/posthoc_summary.json"
LOG="$OUT_DIR/posthoc.log"

# Enumerate shards. Baseline layout: <root>/XX/FuzzyVM-*.json.
# LLM-guided:     <root>/plan_<id>/out/XX/FuzzyVM-*.json.
SHARDS=()
if ls "$ROOT"/plan_* >/dev/null 2>&1; then
	# LLM-guided tree
	while IFS= read -r -d '' d; do
		SHARDS+=("$d")
	done < <(find "$ROOT" -mindepth 3 -maxdepth 3 -type d -print0)
else
	# Baseline tree
	while IFS= read -r -d '' d; do
		SHARDS+=("$d")
	done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -print0)
fi

if [[ ${#SHARDS[@]} -eq 0 ]]; then
	echo "no shards found under $ROOT" >&2
	exit 2
fi

echo "[posthoc] root=$ROOT shards=${#SHARDS[@]} threads=$THREADS out=$OUT_DIR" | tee "$LOG"

TOTAL_TESTS=0
TOTAL_SLOW=0
TOTAL_DIVS=0
TOTAL_DURATION=0
SHARDS_DONE=0
DIVS_JSONL="$OUT_DIR/divergences.jsonl"
: > "$DIVS_JSONL"

for shard in "${SHARDS[@]}"; do
	# Per-shard diff directory so each shard gets its own report and runtest traces.
	# Without --diff-dir, differential.py defaults to <shard>/../diff, which means
	# every shard overwrites the same file at the corpus root.
	report_dir="$shard/diff"
	report="$report_dir/diff_report.json"
	if [[ -f "$report" && "$FORCE" -ne 1 ]]; then
		echo "[posthoc] skip (cached) $shard" | tee -a "$LOG"
	else
		echo "[posthoc] $shard" | tee -a "$LOG"
		python3 orchestrator/differential.py "$shard" \
			--threads "$THREADS" \
			--glob "FuzzyVM-*.json" \
			--diff-dir "$report_dir" >> "$LOG" 2>&1 || true
	fi
	if [[ -f "$report" ]]; then
		python3 - "$report" "$DIVS_JSONL" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    r = json.load(f)
print(json.dumps({
    "shard": r["batch_dir"],
    "tests": r["tests_run"],
    "slow": r["slow_tests"],
    "divergences": len(r["divergences"]),
    "duration_s": r["duration_s"],
}))
with open(sys.argv[2], "a") as out:
    for d in r["divergences"]:
        d["_shard"] = r["batch_dir"]
        out.write(json.dumps(d) + "\n")
PY
		SHARDS_DONE=$((SHARDS_DONE + 1))
	fi
done | tee -a "$LOG"

# Aggregate.
python3 - "$OUT_DIR" "$ROOT" <<'PY'
import json, sys, glob
from pathlib import Path
out_dir = Path(sys.argv[1])
root = sys.argv[2]
reports = []
for p in glob.glob(f"{root}/**/diff/diff_report.json", recursive=True):
    with open(p) as f:
        reports.append(json.load(f))

summary = {
    "root": root,
    "shards_with_reports": len(reports),
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
