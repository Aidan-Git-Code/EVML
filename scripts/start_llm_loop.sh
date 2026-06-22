#!/usr/bin/env bash
# Loop driver. Repeatedly invoke orchestrator/run_batch.py with
# differential + feedback + plateau-rotation enabled, until a wall-clock
# budget expires. Each batch:
#   1. Pulls the last --feedback-n diff_reports into the LLM prompt.
#   2. Optionally rotates objective if the last --rotate-if-plateau batches
#      all produced 0 divergences.
#   3. Generates state-tests with FuzzyVM under the LLM-emitted plan.
#   4. Runs goevmlab differential (geth + revme + besu) over them.
#   5. Writes plan.json + diff/diff_report.json to out/llm_guided/<plan_id>/.
#
# Idempotent: refuses to start if a previous loop is still alive (pid file).
# Stop early: kill $(cat out/llm_loop.pid)
#
# Wall-clock budget, three ways (mutually exclusive):
#   --duration 6h            run for 6h from launch
#   --stop-at  <timestamp>   run until an absolute time
#   --start-at <timestamp>   wait until an absolute time before batch 1
# --start-at and --stop-at can be combined to fuzz between two timestamps.
# Timestamps are anything `date -d` accepts: "2026-06-22T03:00",
# "2026-06-22 03:00", "tomorrow 4am", "+90 min".
#
# Usage:
#   scripts/start_llm_loop.sh \
#       --objective "EIP-1153 TSTORE visibility" \
#       --batch-duration 90s \
#       --start-at "2026-06-22 02:00" --stop-at "2026-06-22 14:00" \
#       --threads 16 --diff-threads 4 \
#       --feedback-n 3 --rotate-if-plateau 3
#
# Defaults: 90s per batch, no total cap, 16 fuzz threads, 4 diff threads,
# feedback over last 3 batches, rotate after 3 zero-div batches.
#
# llama autostart: before each batch the loop ensures llama-server is healthy
# at --llm-url (local only), starting it via scripts/start_llama_server.sh if
# down. Disable with --no-llm-autostart (e.g. when you manage the server
# yourself or point --llm-url at a remote host).
#
# Stop:   kill $(cat out/llm_loop.pid)
# Status: tail -f out/llm_loop.log

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OBJECTIVE=""
FORK="Cancun"
LLM_URL="http://127.0.0.1:8080"
THREADS=16
DIFF_THREADS=4
FEEDBACK_N=3
ROTATE_K=3
BATCH_DURATION="90s"
DURATION=""
START_AT=""
STOP_AT=""
OUT_ROOT="$REPO/out/llm_guided"
INTER_BATCH_SLEEP=2
RUN_DIFF=1
LLM_AUTOSTART=1

parse_duration() {
	local d="${1// /}"
	local total=0 n u
	while [[ -n "$d" ]]; do
		if [[ "$d" =~ ^([0-9]+)([smhd])(.*)$ ]]; then
			n="${BASH_REMATCH[1]}"
			u="${BASH_REMATCH[2]}"
			d="${BASH_REMATCH[3]}"
			case "$u" in
				s) total=$((total + n));;
				m) total=$((total + n * 60));;
				h) total=$((total + n * 3600));;
				d) total=$((total + n * 86400));;
			esac
		else
			return 1
		fi
	done
	echo "$total"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--objective) OBJECTIVE="$2"; shift 2;;
		--fork) FORK="$2"; shift 2;;
		--llm-url) LLM_URL="$2"; shift 2;;
		--threads) THREADS="$2"; shift 2;;
		--diff-threads) DIFF_THREADS="$2"; shift 2;;
		--feedback-n) FEEDBACK_N="$2"; shift 2;;
		--rotate-if-plateau) ROTATE_K="$2"; shift 2;;
		--batch-duration) BATCH_DURATION="$2"; shift 2;;
		--duration) DURATION="$2"; shift 2;;
		--start-at) START_AT="$2"; shift 2;;
		--stop-at) STOP_AT="$2"; shift 2;;
		--out-root) OUT_ROOT="$2"; shift 2;;
		--no-diff) RUN_DIFF=0; shift 1;;
		--no-llm-autostart) LLM_AUTOSTART=0; shift 1;;
		-h|--help)
			grep '^#' "$0" | sed 's/^# \{0,1\}//'
			exit 0;;
		*) echo "unknown arg: $1" >&2; exit 2;;
	esac
done

if [[ -z "$OBJECTIVE" ]]; then
	echo "--objective is required" >&2
	exit 2
fi

# Derive host/port from --llm-url for autostart. Only autostart a local server;
# a remote --llm-url is the operator's responsibility.
LLM_HOST="$(printf '%s' "$LLM_URL" | sed -E 's#^https?://##; s#[:/].*$##')"
LLM_PORT="$(printf '%s' "$LLM_URL" | sed -E 's#^https?://[^:/]+:?##; s#/.*$##')"
LLM_PORT="${LLM_PORT:-8080}"
if [[ "$LLM_AUTOSTART" -eq 1 && "$LLM_HOST" != "127.0.0.1" && "$LLM_HOST" != "localhost" ]]; then
	echo "note: --llm-url host '$LLM_HOST' is not local; disabling llama autostart" >&2
	LLM_AUTOSTART=0
fi

if [[ -n "$DURATION" && -n "$STOP_AT" ]]; then
	echo "--duration and --stop-at are mutually exclusive" >&2
	exit 2
fi

NOW_EPOCH=$(date +%s)

# --start-at: absolute time to begin batch 1. In the past => start immediately.
START_DELAY_SECS=0
if [[ -n "$START_AT" ]]; then
	if ! START_EPOCH=$(date -d "$START_AT" +%s 2>/dev/null); then
		echo "invalid --start-at '$START_AT' (use anything 'date -d' accepts)" >&2
		exit 2
	fi
	if (( START_EPOCH > NOW_EPOCH )); then
		START_DELAY_SECS=$(( START_EPOCH - NOW_EPOCH ))
	fi
fi

# Total wall-clock budget, measured from launch (now). --stop-at is converted
# to a from-now delay so the existing kill-timer mechanism applies unchanged;
# this counts the start-delay too, so the loop still stops at the absolute
# --stop-at instant regardless of when batch 1 begins.
DURATION_SECS=0
if [[ -n "$DURATION" ]]; then
	if ! DURATION_SECS=$(parse_duration "$DURATION"); then
		echo "invalid --duration $DURATION (use e.g. 90s, 30m, 1h30m, 2d)" >&2
		exit 2
	fi
elif [[ -n "$STOP_AT" ]]; then
	if ! STOP_EPOCH=$(date -d "$STOP_AT" +%s 2>/dev/null); then
		echo "invalid --stop-at '$STOP_AT' (use anything 'date -d' accepts)" >&2
		exit 2
	fi
	if (( STOP_EPOCH <= NOW_EPOCH )); then
		echo "--stop-at '$STOP_AT' is in the past" >&2
		exit 2
	fi
	if [[ -n "$START_AT" ]] && (( STOP_EPOCH <= START_EPOCH )); then
		echo "--stop-at must be after --start-at" >&2
		exit 2
	fi
	DURATION_SECS=$(( STOP_EPOCH - NOW_EPOCH ))
fi

if (( START_DELAY_SECS > 0 && DURATION_SECS > 0 && DURATION_SECS <= START_DELAY_SECS )); then
	echo "budget ends before --start-at fires; nothing would run" >&2
	exit 2
fi

PID_FILE="$REPO/out/llm_loop.pid"
LOG_FILE="$REPO/out/llm_loop.log"
START_FILE="$REPO/out/llm_loop.start"
STOP_FILE="$REPO/out/llm_loop.stop"
rm -f "$STOP_FILE"

mkdir -p "$REPO/out" "$OUT_ROOT"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
	echo "llm loop already running: pid=$(cat "$PID_FILE") log=$LOG_FILE"
	exit 0
fi

# Rotate prior log so each session starts fresh and the previous one is kept
# for diffing.
if [[ -f "$LOG_FILE" ]]; then
	mv "$LOG_FILE" "$LOG_FILE.prev"
fi

START_TS="$(date -Is)"
echo "$START_TS" > "$START_FILE"

# Loop body. Each iteration shells out to run_batch.py and waits for it.
# run_batch.py itself manages the FuzzyVM child + goevmlab subprocess; we
# just supervise the wall-clock budget at this level.
if [[ "$RUN_DIFF" -eq 1 ]]; then
	DIFF_ARGS="--diff --diff-threads $DIFF_THREADS --feedback-n $FEEDBACK_N --rotate-if-plateau $ROTATE_K"
else
	DIFF_ARGS=""
fi

LOOP=$(cat <<LOOPEOF
set -u
child_pid=""
trap 'if [[ -n "\$child_pid" ]]; then kill "\$child_pid" 2>/dev/null || true; fi; echo "[loop \$(date -Is)] received signal, exiting"; exit 0' TERM INT

if [[ $START_DELAY_SECS -gt 0 ]]; then
	echo "[loop \$(date -Is)] waiting ${START_DELAY_SECS}s for scheduled start..."
	sleep $START_DELAY_SECS &
	wait \$! || true
fi

i=0
while true; do
	i=\$((i + 1))
	echo "[loop \$(date -Is)] === batch \$i ==="
	cd "$REPO"
	if [[ $LLM_AUTOSTART -eq 1 ]]; then
		HOST=$LLM_HOST PORT=$LLM_PORT bash "$REPO/scripts/start_llama_server.sh" \
			|| echo "[loop \$(date -Is)] WARN: llama autostart failed; this batch will likely fail"
	fi
	python3 -u orchestrator/run_batch.py \\
		--objective "$OBJECTIVE" \\
		--fork "$FORK" \\
		--llm-url "$LLM_URL" \\
		--threads $THREADS \\
		--duration "$BATCH_DURATION" \\
		--out-root "$OUT_ROOT" \\
		$DIFF_ARGS &
	child_pid=\$!
	wait "\$child_pid" || rc=\$?
	rc=\${rc:-0}
	child_pid=""
	echo "[loop \$(date -Is)] batch \$i finished rc=\$rc"
	sleep $INTER_BATCH_SLEEP
done
LOOPEOF
)

nohup bash -c "$LOOP" > "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
disown "$PID" 2>/dev/null || true

sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
	echo "llm loop died immediately; see $LOG_FILE" >&2
	tail -20 "$LOG_FILE" >&2
	rm -f "$PID_FILE"
	exit 1
fi

STOP_LINE="never (runs until killed)"
if [[ "$DURATION_SECS" -gt 0 ]]; then
	STOP_TS="$(date -Is -d "@$(( NOW_EPOCH + DURATION_SECS ))")"
	echo "$STOP_TS" > "$STOP_FILE"
	if [[ -n "$DURATION" ]]; then
		STOP_LINE="$STOP_TS  (after $DURATION)"
	else
		STOP_LINE="$STOP_TS  (--stop-at)"
	fi
	TIMER=$(cat <<TIMEOF
sleep $DURATION_SECS
if kill -0 $PID 2>/dev/null; then
	echo "[timer \$(date -Is)] duration $DURATION elapsed; stopping loop pid=$PID" >> "$LOG_FILE"
	kill $PID
fi
TIMEOF
	)
	nohup bash -c "$TIMER" > /dev/null 2>&1 &
	disown $! 2>/dev/null || true
fi

SCHED_START_LINE="$START_TS  (now)"
if [[ "$START_DELAY_SECS" -gt 0 ]]; then
	SCHED_START_LINE="$(date -Is -d "@$(( NOW_EPOCH + START_DELAY_SECS ))")  (waits ${START_DELAY_SECS}s)"
fi

echo "llm loop running:"
echo "  pid          $PID"
echo "  launched     $START_TS"
echo "  first batch  $SCHED_START_LINE"
echo "  stop         $STOP_LINE"
echo "  objective    $OBJECTIVE"
echo "  fork         $FORK"
echo "  threads      $THREADS  (fuzz)   diff $DIFF_THREADS"
echo "  diff         $([[ $RUN_DIFF -eq 1 ]] && echo enabled || echo DISABLED)"
echo "  llm autostart $([[ $LLM_AUTOSTART -eq 1 ]] && echo "on ($LLM_HOST:$LLM_PORT)" || echo off)"
echo "  feedback-n   $FEEDBACK_N"
echo "  rotate-if-K  $ROTATE_K"
echo "  batch-dur    $BATCH_DURATION"
echo "  out-root     $OUT_ROOT"
echo "  log          $LOG_FILE"
echo
echo "stop early: kill $PID"
echo "status:     tail -f $LOG_FILE"
