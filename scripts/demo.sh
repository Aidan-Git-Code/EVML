#!/usr/bin/env bash
# Presentation demo walkthrough. Maps to slide 14 of presentation.md.
# Seven interactive steps with pause-after-each so the presenter can narrate.
#
# Assumes a quiet host: stop the overnight loop first if it's running.
# Writes to out/demo/ so it never touches out/llm_guided/ or out/baseline/.
#
# Usage:
#   scripts/demo.sh            # interactive, pause-after-each-step
#   scripts/demo.sh --fast     # no pauses (good for asciinema recording)
#
# Total run-time: about 3-4 minutes interactive, about 2 minutes --fast.

set -uo pipefail
# Note: -e omitted so a downstream `head` closing a pipe (SIGPIPE/EPIPE)
# does not abort the demo. Each step handles its own failures explicitly.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

FAST=0
if [[ "${1:-}" == "--fast" ]]; then FAST=1; fi

OUT_ROOT="$REPO/out/demo"
OBJECTIVE="EIP-2929 warm/cold access divergence on nested DELEGATECALL"
FORK="Cancun"
LLM_URL="http://127.0.0.1:8080"

pause() {
	if [[ "$FAST" -eq 1 ]]; then
		sleep 2
	else
		echo
		read -rp "--- press enter for next step ---" _
		echo
	fi
}

banner() {
	echo
	echo "================================================================"
	echo " $1"
	echo "================================================================"
}

# ---- Step 1: preflight --------------------------------------------------
banner "1. preflight: llama-server, fuzzer binary, clients"
if ! curl -sf "$LLM_URL/health" > /dev/null; then
	echo "llama-server not responding at $LLM_URL"
	echo "start it first: scripts/start_llama_server.sh"
	exit 1
fi
echo "llama-server responding at $LLM_URL"
ls -1 "$REPO/FuzzyVM/FuzzyVM" "$HOME/go/bin/evm" "$HOME/.cargo/bin/revme" 2>&1
pause

# ---- Step 2: ask the LLM for one plan -----------------------------------
banner "2. ask the LLM for one strategy plan on the demo objective"
mkdir -p "$OUT_ROOT"
python3 orchestrator/run_batch.py \
	--objective "$OBJECTIVE" \
	--fork "$FORK" \
	--llm-url "$LLM_URL" \
	--out-root "$OUT_ROOT" \
	--dry-run
pause

# ---- Step 3: show the emitted plan --------------------------------------
banner "3. show the plan the LLM emitted"
PLAN_DIR="$(ls -td "$OUT_ROOT"/plan_* 2>/dev/null | head -1)"
if [[ -z "$PLAN_DIR" ]]; then
	echo "no plan directory found under $OUT_ROOT"
	exit 1
fi
echo "plan_dir: $PLAN_DIR"
echo
python3 -m json.tool "$PLAN_DIR/plan.json"
pause

# ---- Step 4: verify the plan biases generation --------------------------
banner "4. FuzzyVM dump: verify the plan biases opcode emission"
cd "$REPO/FuzzyVM"
./FuzzyVM dump --count 50 --plan "$PLAN_DIR/plan.json" | head -40
cd "$REPO"
pause

# ---- Step 5: generate a small batch with the plan -----------------------
banner "5. run FuzzyVM with the plan for 20 seconds on 4 threads"
python3 orchestrator/run_batch.py \
	--objective "$OBJECTIVE" \
	--fork "$FORK" \
	--llm-url "$LLM_URL" \
	--threads 4 \
	--duration 20s \
	--out-root "$OUT_ROOT"

LATEST="$(ls -td "$OUT_ROOT"/plan_* | head -1)"
ONE_TEST="$(find "$LATEST/out" -name "FuzzyVM-*.json" -print -quit)"
if [[ -n "$ONE_TEST" ]]; then
	echo
	echo "example state-test ($ONE_TEST):"
	python3 -m json.tool "$ONE_TEST" | head -30
fi
pause

# ---- Step 6: differential pass with goevmlab runtest --------------------
banner "6. run goevmlab runtest: geth vs revm on the generated batch"
python3 orchestrator/differential.py "$LATEST/out" --threads 4 || true
echo
echo "diff_report.json:"
cat "$LATEST/diff/diff_report.json" 2>/dev/null | python3 -m json.tool | head -30 || \
	echo "(no diff report written)"
pause

# ---- Step 7: demonstrate plateau rotation -------------------------------
banner "7. plateau detector: ask for a new objective after a dry batch"
python3 orchestrator/rotate.py \
	--out-root "$OUT_ROOT" \
	--llm-url "$LLM_URL" \
	--fork "$FORK" \
	--k 1 \
	--current "$OBJECTIVE" || true

banner "demo complete"
echo "output under: $OUT_ROOT"
