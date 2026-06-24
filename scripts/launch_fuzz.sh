#!/usr/bin/env bash
# launch_fuzz.sh — start a divergence-hunting fuzz session.
#
# Brings up two cooperating jobs:
#   1. the LLM-guided generation loop in --no-diff mode (full-tilt generation,
#      never blocks on besu), and
#   2. an out-of-band post-hoc differential sweep that diffs finished batches
#      across geth+revme+besu in parallel.
#
# The sweep shadows the loop's PID: while the loop is alive it re-sweeps every
# 60s (resumable, so each pass only picks up batches finished since the last),
# and when the loop stops it runs one final catch-up pass and exits. That makes
# the time bound a property of the loop alone — duration or end-time, set below.
#
# Interactive: asks whether to bound the run by time, and if so by a duration
# or an absolute end-time.

set -uo pipefail

# --- locate the repo regardless of where this is invoked from ---------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO" || { echo "cannot cd to repo root $REPO" >&2; exit 1; }

# --- knobs (generation/diff sizing; edit here, not prompted) ----------------
OUT_ROOT="$REPO/out/llm_guided"   # absolute: FuzzyVM's go-test child has CWD inside FuzzyVM/,
                                  # so a relative out-root resolves to FuzzyVM/out/... and breaks.
OBJECTIVE_DEFAULT="Blob-Tx/EIP-4864 Gas Accounting Precision"  # fallback for the very first run
LAST_OBJECTIVE_FILE="$REPO/out/last_objective.txt"             # remembers the last launched objective
FORK="Cancun"
GEN_THREADS=16        # go-fuzz workers; leaves cores for the parallel sweep
BATCH_DURATION="90s"  # per-batch active-fuzz window
DIFF_JOBS=4           # concurrent runtest+besu streams (RAM-bound; 6 is the solo ceiling)
DIFF_THREADS=3        # geth/revme parallelism per stream
LLM_URL="http://127.0.0.1:8080"

# --- stop any prior session so a relaunch is clean --------------------------
stop_existing() {
	local lp
	if [[ -f out/llm_loop.pid ]]; then
		lp="$(cat out/llm_loop.pid 2>/dev/null)"
		if [[ -n "$lp" ]] && kill -0 "$lp" 2>/dev/null; then
			echo "stopping existing loop (pid $lp)..."
			kill "$lp" 2>/dev/null
		fi
	fi
	# Tear down any running post-hoc sweep: wrapper, xargs pool, workers, clients.
	# Loop a few times because xargs respawns workers until the controller dies.
	local r
	for r in 1 2 3; do
		pkill -f 'posthoc_diff.sh'              2>/dev/null  # wrapper body + controller
		pkill -f 'xargs -P .* bash -c worker'   2>/dev/null  # job pool
		pkill -f 'bash -c worker'               2>/dev/null  # pool workers
		pkill -f 'orchestrator/differential.py' 2>/dev/null
		pkill -x runtest                        2>/dev/null
		pkill -f 'evmtool-jdk25'                2>/dev/null
		sleep 2
	done
}

# --- objective --------------------------------------------------------------
# Default to the last objective actually launched; fall back to OBJECTIVE_DEFAULT
# on the first ever run. Override by typing a new one at the prompt.
DEFAULT_OBJECTIVE="$OBJECTIVE_DEFAULT"
if [[ -s "$LAST_OBJECTIVE_FILE" ]]; then
	DEFAULT_OBJECTIVE="$(< "$LAST_OBJECTIVE_FILE")"
fi
read -rp "Objective [$DEFAULT_OBJECTIVE]: " OBJECTIVE
OBJECTIVE="${OBJECTIVE:-$DEFAULT_OBJECTIVE}"

# --- time bound -------------------------------------------------------------
STOP_FLAG=""
read -rp "Bound the run by time? [y/N]: " yn
if [[ "$yn" =~ ^[Yy] ]]; then
	echo "  1) duration   (e.g. 3h, 90m, 1h30m)"
	echo "  2) end time   (e.g. 17:00, 'tomorrow 02:00', '2026-06-22 17:00')"
	read -rp "Choose 1 or 2: " mode
	case "$mode" in
		1)
			read -rp "Duration: " DUR
			DUR="${DUR// /}"
			if [[ ! "$DUR" =~ ^([0-9]+[smhd])+$ ]]; then
				echo "invalid duration '$DUR' (use e.g. 90s, 30m, 1h30m, 2d)" >&2
				exit 1
			fi
			STOP_FLAG="--duration $DUR"
			echo "run bounded to $DUR from launch."
			;;
		2)
			read -rp "End time: " ENDT
			if ! end_epoch=$(date -d "$ENDT" +%s 2>/dev/null); then
				echo "invalid end time '$ENDT' (anything 'date -d' accepts)" >&2
				exit 1
			fi
			if [[ "$end_epoch" -le "$(date +%s)" ]]; then
				echo "end time '$ENDT' is in the past" >&2
				exit 1
			fi
			STOP_FLAG="--stop-at $ENDT"
			echo "run bounded until $(date -d "@$end_epoch" '+%Y-%m-%d %H:%M:%S')."
			;;
		*)
			echo "unrecognized choice '$mode'" >&2
			exit 1
			;;
	esac
else
	echo "no time bound — runs until you stop it (kill the loop pid in out/llm_loop.pid)."
fi

# --- launch -----------------------------------------------------------------
stop_existing

# Remember this objective so the next launch defaults to it.
mkdir -p "$(dirname "$LAST_OBJECTIVE_FILE")"
printf '%s\n' "$OBJECTIVE" > "$LAST_OBJECTIVE_FILE"

echo
echo "starting generation loop (--no-diff)..."
# shellcheck disable=SC2086  # STOP_FLAG is intentionally word-split (flag + value)
scripts/start_llm_loop.sh \
	--objective "$OBJECTIVE" \
	--fork "$FORK" \
	--threads "$GEN_THREADS" \
	--batch-duration "$BATCH_DURATION" \
	--out-root "$OUT_ROOT" \
	--llm-url "$LLM_URL" \
	--no-diff \
	$STOP_FLAG

# Capture the loop's supervisor PID so the sweep can shadow it.
sleep 2
LOOP_PID="$(cat out/llm_loop.pid 2>/dev/null)"
if [[ -z "$LOOP_PID" ]] || ! kill -0 "$LOOP_PID" 2>/dev/null; then
	echo "loop failed to start (no live pid in out/llm_loop.pid); see out/llm_loop.log" >&2
	exit 1
fi
echo "loop up, pid $LOOP_PID."

echo "starting post-hoc diff sweep (j=$DIFF_JOBS, shadowing loop pid $LOOP_PID)..."
nohup bash -c '
	cd '"$(printf %q "$REPO")"' || exit 1
	loop_pid='"$LOOP_PID"'
	while kill -0 "$loop_pid" 2>/dev/null; do
		scripts/posthoc_diff.sh '"$OUT_ROOT"' -j '"$DIFF_JOBS"' --threads '"$DIFF_THREADS"' --skip-existing
		sleep 60
	done
	# loop ended — one final catch-up pass over batches it finished last
	scripts/posthoc_diff.sh '"$OUT_ROOT"' -j '"$DIFF_JOBS"' --threads '"$DIFF_THREADS"'
' >/dev/null 2>&1 &
echo "sweep wrapper pid $!."

# --- summary ----------------------------------------------------------------
cat <<EOF

launched.
  objective : $OBJECTIVE
  fork      : $FORK
  bound     : ${STOP_FLAG:-none (until stopped)}
  gen       : $GEN_THREADS threads, $BATCH_DURATION batches, no in-loop diff
  diff      : $DIFF_JOBS jobs x $DIFF_THREADS threads, geth+revme+besu

monitor:
  tail -f out/llm_loop.log
  scripts/posthoc_status.sh --watch
  python3 orchestrator/dashboard/server.py    # http://127.0.0.1:8090/

stop early:
  kill \$(cat out/llm_loop.pid)               # loop; sweep finishes its last pass then exits
EOF
