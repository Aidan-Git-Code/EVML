#!/usr/bin/env bash
# Preserve go-test-fuzz crasher inputs before the baseline supervisor wipes them.
#
# Problem:
#   Each time a generated input triggers a native-level fault in geth's EVM,
#   `go test --fuzz` persists the bytes to FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/.
#   Our supervisor has to wipe that directory before each relaunch (otherwise
#   go-test-fuzz replays the crasher as "baseline coverage" and bricks the
#   fuzzer). The bytes themselves are potential geth bug reports — we want
#   them saved, not wiped.
#
# Solution:
#   Poll the testdata dir at 1s cadence, move each new file to out/crashers/
#   keyed by its content-hash filename (go-test-fuzz names are already
#   deterministic sha hashes). Append a manifest row with timestamp + size so
#   captures can be correlated with baseline.log supervisor events.
#
# Lifecycle:
#   Self-terminates when the baseline supervisor (out/baseline.pid) is gone,
#   so no manual cleanup is needed after the 16h run ends.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTDATA="$REPO/FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic"
CRASH_DIR="$REPO/out/crashers"
MANIFEST="$CRASH_DIR/manifest.tsv"
SUPERVISOR_PID_FILE="$REPO/out/baseline.pid"

mkdir -p "$CRASH_DIR"
if [[ ! -f "$MANIFEST" ]]; then
	printf 'timestamp\tfilename\tsize_bytes\n' > "$MANIFEST"
fi

echo "[watcher $(date -Is)] starting; supervisor_pid=$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo none)"

shopt -s nullglob

while true; do
	# Self-terminate if the baseline supervisor is gone.
	if [[ -f "$SUPERVISOR_PID_FILE" ]]; then
		SUP="$(cat "$SUPERVISOR_PID_FILE")"
		if ! kill -0 "$SUP" 2>/dev/null; then
			echo "[watcher $(date -Is)] supervisor $SUP gone; exiting"
			exit 0
		fi
	fi

	for f in "$TESTDATA"/*; do
		[[ -f "$f" ]] || continue
		base=$(basename "$f")
		dest="$CRASH_DIR/$base"
		if [[ -e "$dest" ]]; then
			# Same content-hash already captured — drop the duplicate so
			# supervisor doesn't have to wipe it.
			rm -f "$f"
		else
			if mv "$f" "$dest" 2>/dev/null; then
				size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
				printf '%s\t%s\t%d\n' "$(date -Is)" "$base" "$size" >> "$MANIFEST"
			fi
		fi
	done

	sleep 1
done
