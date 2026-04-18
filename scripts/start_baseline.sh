#!/usr/bin/env bash
# Launch the stock-random FuzzyVM baseline run in the background under a
# supervisor loop that restarts FuzzyVM if it crashes.
#
# Why a supervisor:
#   geth's EVM occasionally hits native-level cgo faults that bypass Go's
#   recover(). When that happens, go-test-fuzz persists the offending input
#   to FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/, and replays every file in
#   that dir as "baseline coverage" on the next startup — so a single crash
#   permanently bricks the fuzzer. The supervisor wipes that dir on every
#   (re)launch and relaunches on any non-zero exit.
#
# Usage:
#   scripts/start_baseline.sh                   # 4 threads, default out dir, runs forever
#   scripts/start_baseline.sh --threads 8       # override threads
#   scripts/start_baseline.sh --out-dir /data/b # override output dir
#   scripts/start_baseline.sh --duration 24h    # auto-stop after 24h wall-clock
#     (duration accepts combinations like 90s, 30m, 1h30m, 2d; omit = forever)
#
# Stop:   kill $(cat out/baseline.pid)          # or: scripts/stop_baseline.sh
# Status: tail -f out/baseline.log

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUZZYVM_DIR="$REPO/FuzzyVM"
BIN="$FUZZYVM_DIR/FuzzyVM"
TESTDATA_DIR="$FUZZYVM_DIR/fuzzer/testdata/fuzz/FuzzVMBasic"

THREADS=4
OUT_DIR="$REPO/out/baseline"
DURATION=""

# parse_duration <str> -> seconds; accepts combinations like 90s, 30m, 1h30m, 2d.
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
		--threads) THREADS="$2"; shift 2;;
		--out-dir) OUT_DIR="$2"; shift 2;;
		--duration) DURATION="$2"; shift 2;;
		-h|--help)
			grep '^#' "$0" | sed 's/^# \{0,1\}//'
			exit 0;;
		*) echo "unknown arg: $1" >&2; exit 2;;
	esac
done

DURATION_SECS=0
if [[ -n "$DURATION" ]]; then
	if ! DURATION_SECS=$(parse_duration "$DURATION"); then
		echo "invalid --duration $DURATION (use e.g. 90s, 30m, 1h30m, 2d)" >&2
		exit 2
	fi
	if [[ "$DURATION_SECS" -le 0 ]]; then
		echo "--duration must be > 0" >&2
		exit 2
	fi
fi

PID_FILE="$REPO/out/baseline.pid"
LOG_FILE="$REPO/out/baseline.log"
START_FILE="$REPO/out/baseline.start"
STOP_FILE="$REPO/out/baseline.stop"
rm -f "$STOP_FILE"

mkdir -p "$REPO/out" "$OUT_DIR"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
	echo "baseline already running: pid=$(cat "$PID_FILE") log=$LOG_FILE"
	exit 0
fi

if [[ ! -x "$BIN" ]]; then
	echo "building FuzzyVM..."
	( cd "$FUZZYVM_DIR" && go build -o FuzzyVM ./cmd/fuzzyvm )
fi

# The upstream seed corpus contains at least one input that segfaults geth's
# VM via cgo (bypasses Go recover), crashing go-test-fuzz on startup. Keep
# it parked as corpus_disabled/ so readCorpus() returns empty and fuzzing
# falls back to the 255 byte-pattern seeds.
if [[ -d "$FUZZYVM_DIR/corpus" ]]; then
	echo "renaming FuzzyVM/corpus -> FuzzyVM/corpus_disabled (avoid startup crasher)"
	mv "$FUZZYVM_DIR/corpus" "$FUZZYVM_DIR/corpus_disabled"
fi

START_TS="$(date -Is)"
echo "$START_TS" > "$START_FILE"

# Supervisor body. Runs in background via nohup. On each loop iteration:
#   1. Wipe go-fuzz's persisted crasher dir so startup replay can't re-fault.
#   2. Launch FuzzyVM as a child; record its PID so SIGTERM propagates.
#   3. On any exit, sleep briefly and relaunch.
# PID_FILE holds the supervisor PID; `kill $PID` triggers the trap which
# forwards SIGTERM to the live FuzzyVM child, then the supervisor exits.
SUPERVISOR=$(cat <<SUPEOF
set -u
child_pid=""
trap 'if [[ -n "\$child_pid" ]]; then kill "\$child_pid" 2>/dev/null || true; fi; exit 0' TERM INT
while true; do
	if [[ -d "$TESTDATA_DIR" ]]; then
		rm -f "$TESTDATA_DIR"/* 2>/dev/null || true
	fi
	echo "[supervisor \$(date -Is)] launching FuzzyVM run (threads=$THREADS out=$OUT_DIR)"
	cd "$FUZZYVM_DIR"
	"$BIN" run --threads "$THREADS" --out-dir "$OUT_DIR" &
	child_pid=\$!
	wait "\$child_pid"
	rc=\$?
	child_pid=""
	echo "[supervisor \$(date -Is)] FuzzyVM exited rc=\$rc; restarting in 5s"
	sleep 5
done
SUPEOF
)

nohup bash -c "$SUPERVISOR" > "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
disown "$PID" 2>/dev/null || true

sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
	echo "baseline supervisor died immediately; see $LOG_FILE" >&2
	tail -20 "$LOG_FILE" >&2
	rm -f "$PID_FILE"
	exit 1
fi

# Optional wall-clock deadline. A detached timer sleeps then SIGTERMs the
# supervisor, whose trap forwards the signal to its FuzzyVM child.
STOP_LINE="never (runs until killed)"
if [[ "$DURATION_SECS" -gt 0 ]]; then
	STOP_TS="$(date -Is -d "@$(( $(date +%s) + DURATION_SECS ))")"
	echo "$STOP_TS" > "$STOP_FILE"
	STOP_LINE="$STOP_TS  (after $DURATION)"
	TIMER=$(cat <<TIMEOF
sleep $DURATION_SECS
if kill -0 $PID 2>/dev/null; then
	echo "[timer \$(date -Is)] duration $DURATION elapsed; stopping supervisor pid=$PID" >> "$LOG_FILE"
	kill $PID
fi
TIMEOF
	)
	nohup bash -c "$TIMER" > /dev/null 2>&1 &
	disown $! 2>/dev/null || true
fi

echo "baseline running (supervised):"
echo "  pid     $PID   (supervisor; auto-restarts FuzzyVM on crash)"
echo "  start   $START_TS"
echo "  stop    $STOP_LINE"
echo "  threads $THREADS"
echo "  out     $OUT_DIR"
echo "  log     $LOG_FILE"
echo
echo "stop early: kill $PID   (trap forwards to FuzzyVM child)"
echo "status:     tail -f $LOG_FILE"
