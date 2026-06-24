#!/usr/bin/env bash
# Parallel post-hoc differential sweep over a FuzzyVM state-test corpus.
#
# Each plan dir (<root>/plan_<id>/out) is one unit of work: orchestrator/
# differential.py runs runtest across its */FuzzyVM-*.json with its own besu
# evmtool stream and writes plan_<id>/diff/diff_report.json. besu runs as a
# single ~90 tests/sec stream per runtest, so the throughput gate is besu, not
# CPU. Fanning out JOBS plan dirs at once gives JOBS independent besu streams
# and fills an otherwise ~88%-idle 32-core box. JOBS=8 / THREADS=3 is the
# default (24 runtest slots + 8 besu JVMs).
#
# Resumable: skips any plan dir whose diff_report.json was written after the
# previous session's POSTHOC START. Pass --force to re-run everything.
#
# Progress is logged to out/posthoc_diff.log in the format scripts/
# posthoc_status.sh parses; watch it with `scripts/posthoc_status.sh --watch`.
#
# Usage:
#   scripts/posthoc_diff.sh [<corpus_root>] [-j JOBS] [--threads N] [--force]
#
# <corpus_root> defaults to out/llm_guided. Examples:
#   scripts/posthoc_diff.sh                       # llm_guided, 8 jobs
#   scripts/posthoc_diff.sh out/baseline -j 8     # baseline corpus
#   scripts/posthoc_diff.sh -j 10 --threads 2     # push harder

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

ROOT="out/llm_guided"
JOBS=8
THREADS=3
FORCE=0
SKIP_EXISTING=0        # incremental: diff each immutable batch once; ignore the mtime cutoff
GRACE=120              # defer batches whose out/ was touched within this many seconds
LOG="out/posthoc_diff.log"

while [[ $# -gt 0 ]]; do
	case "$1" in
		-j|--jobs) JOBS="$2"; shift 2;;
		--threads) THREADS="$2"; shift 2;;
		--force) FORCE=1; shift;;
		--skip-existing) SKIP_EXISTING=1; shift;;
		--log) LOG="$2"; shift 2;;
		-*) echo "unknown flag: $1" >&2; exit 2;;
		*) ROOT="$1"; shift;;
	esac
done

if [[ ! -d "$ROOT" ]]; then
	echo "no such directory: $ROOT" >&2
	exit 2
fi

# Resume cutoff: a report newer than the prior session's start counts as done.
# Read this before rotating the log.
CUTOFF=0
if [[ "$FORCE" -eq 0 && -f "$LOG" ]]; then
	ts=$(grep -m1 -oE 'POSTHOC START [^ ]+' "$LOG" 2>/dev/null | awk '{print $3}')
	[[ -n "$ts" ]] && CUTOFF=$(date -d "$ts" +%s 2>/dev/null || echo 0)
fi

# Enumerate plan dirs. LLM-guided: <root>/plan_<id>/out. Baseline: <root>
# itself holds the XX/ subdirs, so treat the root as the single unit.
mapfile -t CANDIDATES < <(ls -d "$ROOT"/plan_*/out 2>/dev/null | sort)
if [[ ${#CANDIDATES[@]} -eq 0 ]]; then
	CANDIDATES=("$ROOT")
fi

TODO=()
skipped=0
now=$(date +%s)
for d in "${CANDIDATES[@]}"; do
	rep="$(dirname "$d")/diff/diff_report.json"
	if [[ "$FORCE" -eq 0 && "$SKIP_EXISTING" -eq 1 ]]; then
		# Incremental mode (repeating-wrapper friendly): a FuzzyVM batch is
		# write-once, so diff each exactly once and never re-diff. Defer dirs
		# still being written so a partial batch is not marked done.
		[[ -f "$rep" ]] && { skipped=$((skipped + 1)); continue; }
		dm=$(stat -c %Y "$d" 2>/dev/null || echo 0)
		if [[ $((now - dm)) -lt "$GRACE" ]]; then
			skipped=$((skipped + 1)); continue
		fi
		TODO+=("$d"); continue
	fi
	if [[ "$FORCE" -eq 0 && "$CUTOFF" -gt 0 && -f "$rep" ]]; then
		m=$(stat -c %Y "$rep" 2>/dev/null || echo 0)
		if [[ "$m" -gt "$CUTOFF" ]]; then
			skipped=$((skipped + 1)); continue
		fi
	fi
	TODO+=("$d")
done

TOTAL=${#TODO[@]}
if [[ "$TOTAL" -eq 0 ]]; then
	echo "nothing to do (skipped=$skipped already done since last start). use --force to redo all." >&2
	exit 0
fi

# Rotate prior log, open fresh session.
[[ -f "$LOG" ]] && mv -f "$LOG" "$LOG.prev"
mkdir -p "$(dirname "$LOG")"
COUNTER_FILE="$(mktemp)"; echo 0 > "$COUNTER_FILE"
LOCK="$LOG.lock"; : > "$LOCK"

echo "POSTHOC START $(date -Is)  dirs=$TOTAL clients=geth+revme+besu jobs=$JOBS threads=$THREADS skipped=$skipped" >> "$LOG"
echo "[posthoc] root=$ROOT dirs=$TOTAL jobs=$JOBS threads=$THREADS skipped=$skipped (log: $LOG)"

worker() {
	local d="$1" name rc st rep vms divs
	name=$(basename "$(dirname "$d")")
	[[ "$name" == "$(basename "$ROOT")" ]] && name=$(basename "$d")
	if python3 orchestrator/differential.py "$d" --threads "$THREADS" >/dev/null 2>&1; then
		st=ok
	else
		rc=$?; st="rc=$rc"
	fi
	rep="$(dirname "$d")/diff/diff_report.json"
	vms=$(python3 -c "import json;print(','.join(json.load(open('$rep'))['vms']))" 2>/dev/null)
	divs=$(python3 -c "import json;print(len(json.load(open('$rep'))['divergences']))" 2>/dev/null)
	(
		flock 9
		local i; i=$(( $(cat "$COUNTER_FILE") + 1 )); echo "$i" > "$COUNTER_FILE"
		echo "[$i/$TOTAL] $(date -Is) $name vms=${vms:-?} divs=${divs:-?} $st" >> "$LOG"
	) 9>"$LOCK"
}
export -f worker
export ROOT THREADS TOTAL LOG COUNTER_FILE LOCK

printf '%s\n' "${TODO[@]}" | xargs -P "$JOBS" -I{} bash -c 'worker "$@"' _ {}

echo "POSTHOC DONE $(date -Is)" >> "$LOG"
rm -f "$COUNTER_FILE" "$LOCK"

# Aggregate every report under the corpus into one summary.
python3 - "$ROOT" <<'PY'
import json, sys, glob
from pathlib import Path
root = sys.argv[1]
reports = []
for p in glob.glob(f"{root}/**/diff/diff_report.json", recursive=True):
    try:
        with open(p) as f:
            reports.append(json.load(f))
    except Exception:
        pass
summary = {
    "root": root,
    "dirs_with_reports": len(reports),
    "tests_total": sum(r.get("tests_run", 0) for r in reports),
    "slow_tests_total": sum(r.get("slow_tests", 0) for r in reports),
    "divergences_total": sum(len(r.get("divergences", [])) for r in reports),
    "duration_s_total": round(sum(r.get("duration_s", 0) for r in reports), 2),
    "unique_flaw_files": len({d["file"] for r in reports for d in r.get("divergences", [])}),
    "divergences_by_vm_pair": {},
}
for r in reports:
    for d in r.get("divergences", []):
        key = f"{d.get('vm','?')} vs {d.get('ref_vm','?')}"
        summary["divergences_by_vm_pair"][key] = summary["divergences_by_vm_pair"].get(key, 0) + 1
out = Path("out") / f"posthoc_summary_{Path(root).name}.json"
out.write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
PY
