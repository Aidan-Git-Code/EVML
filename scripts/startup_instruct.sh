#!/usr/bin/env bash
# Prints how to start everything for a fuzzing session, plus the live status of
# each piece. Informational only: it does not start or stop anything.
#
#   scripts/startup_instruct.sh

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

LLAMA_PORT="${LLAMA_PORT:-8080}"
DASH_PORT="${DASH_PORT:-8090}"

# colors (skip if not a tty)
if [[ -t 1 ]]; then
	B=$'\e[1m'; DIM=$'\e[2m'; G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; X=$'\e[0m'
else
	B=""; DIM=""; G=""; R=""; Y=""; C=""; X=""
fi

pid_alive() {  # $1 = pid file -> echoes pid if alive, returns 0/1
	local p
	p="$(cat "$1" 2>/dev/null)" || return 1
	[[ -n "$p" ]] && kill -0 "$p" 2>/dev/null && { echo "$p"; return 0; }
	return 1
}
port_open() { curl -sfm 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1 || curl -sfm 2 "http://127.0.0.1:$1/" >/dev/null 2>&1; }

up()   { printf '%s' "${G}● up${X}"; }
down() { printf '%s' "${R}○ down${X}"; }

echo
echo "${B}EVML — startup${X}  ${DIM}($REPO)${X}"
echo "${DIM}────────────────────────────────────────────────────────${X}"

# ---- live status -------------------------------------------------------------
echo "${B}status${X}"

if port_open "$LLAMA_PORT"; then llama_s="$(up)"; else llama_s="$(down)"; fi
lpid="$(pid_alive out/llm_loop.pid)" && loop_s="$(up) ${DIM}pid $lpid${X}" || loop_s="$(down)"
if port_open "$DASH_PORT"; then dash_s="$(up)"; else dash_s="$(down)"; fi

printf '  %-12s %s\n' "llama"     "$llama_s   ${DIM}:$LLAMA_PORT${X}"
printf '  %-12s %s\n' "fuzz loop" "$loop_s"
printf '  %-12s %s\n' "dashboard" "$dash_s   ${DIM}:$DASH_PORT${X}"

if [[ -f out/posthoc_diff.log ]]; then
	if grep -q "POSTHOC DONE" out/posthoc_diff.log 2>/dev/null; then
		ph_s="${G}done${X}"
	elif pgrep -f "POSTHOC" >/dev/null 2>&1; then
		prog=$(grep '^\[' out/posthoc_diff.log | tail -1 | grep -oE '^\[[0-9]+/[0-9]+' | tr -d '[')
		ph_s="$(up)   ${DIM}${prog:-0} dirs${X}"
	else
		ph_s="${R}stopped (unfinished)${X}"
	fi
	printf '  %-12s %s\n' "post-hoc" "$ph_s"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
	read -r used free <<<"$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr ',' ' ')"
	[[ -n "$free" ]] && printf '  %-12s %s\n' "gpu" "${DIM}${used} MiB used / ${free} MiB free${X}"
fi
echo

# ---- quick commands ----------------------------------------------------------
echo "${B}quick${X}  ${DIM}(copy-paste)${X}"
printf '  %-22s %s\n' "dashboard"        "${C}python3 orchestrator/dashboard/server.py${X}"
printf '  %-22s %s\n' "3-way diff loop"  "${C}scripts/start_llm_loop.sh --objective \"...\" --rotate-if-plateau 0${X}"
printf '  %-22s %s\n' "stop fuzzing"     "${C}scripts/stop_fuzzing.sh${X}  ${DIM}(keeps post-hoc running)${X}"
printf '  %-22s %s\n' "post-hoc sweep"   "${C}scripts/posthoc_diff_llm.sh --threads 16${X}"
printf '  %-22s %s\n' "post-hoc status"  "${C}scripts/posthoc_status.sh --watch${X}"
printf '  %-22s %s\n' "watch loop log"   "${C}tail -f out/llm_loop.log${X}"
echo

# ---- instructions ------------------------------------------------------------
echo "${B}1. dashboard${X}  ${DIM}(read-only viewer, safe to leave running)${X}"
echo "   ${C}python3 orchestrator/dashboard/server.py${X}"
echo "   then open ${C}http://127.0.0.1:$DASH_PORT/${X}"
echo

echo "${B}2. fuzzing loop${X}  ${DIM}(starts llama itself if it is down)${X}"
echo "   run now until killed:"
echo "   ${C}scripts/start_llm_loop.sh --objective \"EIP-1153 TSTORE across nested DELEGATECALL\"${X}"
echo
echo "   run for a fixed length:"
echo "   ${C}scripts/start_llm_loop.sh --objective \"...\" --duration 6h${X}"
echo
echo "   run inside an absolute window (waits for start, stops at stop):"
echo "   ${C}scripts/start_llm_loop.sh --objective \"...\" \\${X}"
echo "   ${C}     --start-at \"2026-06-22 02:00\" --stop-at \"2026-06-22 14:00\"${X}"
echo
echo "   ${DIM}fair-comparison run (no inline diff, diff post-hoc): add --no-diff${X}"
echo "   ${DIM}other flags: --threads N  --diff-threads N  --batch-duration 90s${X}"
echo "   ${DIM}             --rotate-if-plateau K  --feedback-n N  --no-llm-autostart${X}"
echo
echo "   ${Y}note:${X} diffing on => the 3-client panel (geth+revme+besu) runs automatically."
echo "   ${Y}note:${X} the objective auto-rotates after K zero-divergence batches (default K=3),"
echo "         so on an all-zero corpus it swaps on batch 1. ${C}--rotate-if-plateau 0${X} pins it."
echo "   ${Y}note:${X} sharing the box with the post-hoc diff? use ${C}--threads 8${X} so they don't thrash."
echo

echo "${B}3. watch / stop${X}"
echo "   live log:   ${C}tail -f out/llm_loop.log${X}"
echo "   stop loop:  ${C}kill \$(cat out/llm_loop.pid)${X}"
echo "   stop llama: ${C}kill \$(cat out/llama_server.pid)${X}"
echo "   stop fuzzing but keep a post-hoc diff running:"
echo "               ${C}scripts/stop_fuzzing.sh${X}  ${DIM}(add --keep-llama to leave the LLM up)${X}"
echo

echo "${B}4. post-hoc 3-client diff${X}  ${DIM}(geth + revme + besu over an existing corpus)${X}"
echo "   ${C}for d in out/llm_guided/plan_*/out; do python3 orchestrator/differential.py \"\$d\" --threads 12; done${X}"
echo

echo "${DIM}llama is only needed for plan generation; the loop auto-starts it. Free the${X}"
echo "${DIM}GPU first if another process holds VRAM (nvidia-smi). Manual llama start:${X}"
echo "${DIM}  scripts/start_llama_server.sh${X}"
echo
