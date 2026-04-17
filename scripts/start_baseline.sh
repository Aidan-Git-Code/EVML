#!/usr/bin/env bash
# Launch the stock-random FuzzyVM baseline run in the background.
# Writes PID + start timestamp so start/stop/status commands can find it.
#
# Usage:
#   scripts/start_baseline.sh                   # 4 threads, default out dir
#   scripts/start_baseline.sh --threads 8       # override threads
#   scripts/start_baseline.sh --out-dir /data/b # override output dir
#
# Stop:   kill $(cat out/baseline.pid)          # or: scripts/stop_baseline.sh
# Status: tail -f out/baseline.log

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUZZYVM_DIR="$REPO/FuzzyVM"
BIN="$FUZZYVM_DIR/FuzzyVM"

THREADS=4
OUT_DIR="$REPO/out/baseline"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--threads) THREADS="$2"; shift 2;;
		--out-dir) OUT_DIR="$2"; shift 2;;
		-h|--help)
			grep '^#' "$0" | sed 's/^# \{0,1\}//'
			exit 0;;
		*) echo "unknown arg: $1" >&2; exit 2;;
	esac
done

PID_FILE="$REPO/out/baseline.pid"
LOG_FILE="$REPO/out/baseline.log"
START_FILE="$REPO/out/baseline.start"

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
# VM via cgo (bypasses Go recover), crashing go-test-fuzz on startup. We keep
# it on disk as corpus_disabled/ so the test package's readCorpus() sees an
# empty seed set and fuzzing falls back to the 255 byte-pattern seeds.
if [[ -d "$FUZZYVM_DIR/corpus" ]]; then
	echo "renaming FuzzyVM/corpus -> FuzzyVM/corpus_disabled (avoid startup crasher)"
	mv "$FUZZYVM_DIR/corpus" "$FUZZYVM_DIR/corpus_disabled"
fi

START_TS="$(date -Is)"
echo "$START_TS" > "$START_FILE"

cd "$FUZZYVM_DIR"
nohup "$BIN" run --threads "$THREADS" --out-dir "$OUT_DIR" \
	> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
disown "$PID" 2>/dev/null || true

sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
	echo "baseline died immediately; see $LOG_FILE" >&2
	tail -20 "$LOG_FILE" >&2
	rm -f "$PID_FILE"
	exit 1
fi

echo "baseline running:"
echo "  pid     $PID"
echo "  start   $START_TS"
echo "  threads $THREADS"
echo "  out     $OUT_DIR"
echo "  log     $LOG_FILE"
echo
echo "stop:   kill $PID  (or scripts/stop_baseline.sh)"
echo "status: tail -f $LOG_FILE"
