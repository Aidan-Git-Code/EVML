#!/usr/bin/env bash
# Stop the active LLM fuzzing loop without touching a running post-hoc
# differential sweep.
#
# The loop and the post-hoc both run goevmlab `runtest --besubatch`, and the
# post-hoc's command line even contains the string "FuzzyVM" (in its glob), so
# pattern-matching on runtest/besu/evm/FuzzyVM would kill the post-hoc too. The
# only safe discriminator is process-tree ancestry: this script kills the loop
# supervisor (out/llm_loop.pid) and its descendant subtree by pid, leaving the
# post-hoc's separate tree alone. Go-fuzz workers are mopped up only via
# fuzz-exclusive tokens the post-hoc never runs.
#
# By default it also stops llama-server (only used for plan generation; the
# post-hoc does not need it, and stopping it frees the GPU). Keep it with
# --keep-llama.
#
#   scripts/stop_fuzzing.sh [--keep-llama]

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

KEEP_LLAMA=0
[[ "${1:-}" == "--keep-llama" ]] && KEEP_LLAMA=1

PID_FILE="out/llm_loop.pid"

descendants() {  # recursively print all descendant pids of $1
	local p
	for p in $(pgrep -P "$1" 2>/dev/null); do
		echo "$p"
		descendants "$p"
	done
}

loop="$(cat "$PID_FILE" 2>/dev/null)"
if [[ -z "$loop" ]] || ! kill -0 "$loop" 2>/dev/null; then
	echo "no live fuzzing loop (pid file: ${loop:-none})"
	rm -f "$PID_FILE"
else
	# Snapshot the whole subtree before signalling so we can finish survivors.
	mapfile -t tree < <(descendants "$loop")
	echo "stopping loop supervisor $loop + ${#tree[@]} descendant(s):"
	for p in "${tree[@]}"; do ps -o pid,comm -p "$p" 2>/dev/null | tail -n +2 | sed 's/^/   /'; done
	# Graceful: the supervisor trap kills run_batch, which killpgs FuzzyVM.
	kill -TERM "$loop" 2>/dev/null
	for _ in 1 2 3 4 5 6 7 8; do kill -0 "$loop" 2>/dev/null || break; sleep 0.5; done
	# Finish off anything from the snapshot still alive, supervisor last.
	for p in "${tree[@]}" "$loop"; do kill -KILL "$p" 2>/dev/null; done
	rm -f "$PID_FILE"
	echo "loop stopped."
fi

# Backstop for orphaned go-fuzz workers. Match ONLY fuzz-exclusive tokens; the
# post-hoc never runs `go test` / FuzzVMBasic, so this cannot hit it.
for p in $(pgrep -f "FuzzVMBasic" 2>/dev/null) $(pgrep -f -- "-test\.fuzz" 2>/dev/null); do
	kill -KILL "$p" 2>/dev/null && echo "killed orphan fuzz worker $p"
done

if [[ "$KEEP_LLAMA" -eq 0 ]]; then
	lp="$(cat out/llama_server.pid 2>/dev/null)"
	if [[ -n "$lp" ]] && kill -0 "$lp" 2>/dev/null; then
		kill -TERM "$lp" 2>/dev/null && echo "stopped llama-server $lp (frees GPU; post-hoc does not use it)"
		rm -f out/llama_server.pid
	fi
fi

echo
if [[ -f out/posthoc_diff.log ]]; then
	bash "$REPO/scripts/posthoc_status.sh"
	echo
	echo "watch it live: scripts/posthoc_status.sh --watch"
else
	echo "no post-hoc sweep detected (no out/posthoc_diff.log)."
fi
