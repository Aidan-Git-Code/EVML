#!/usr/bin/env bash
# Launch (or check) llama-server with Qwen2.5-Coder-7B-Instruct Q5_K_M.
# Idempotent: no-ops if an instance is already listening on $PORT.

set -euo pipefail

MODEL="${MODEL:-$HOME/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf}"
BIN="${BIN:-$HOME/tools/llama.cpp/build/bin/llama-server}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX="${CTX:-8192}"
NGL="${NGL:-999}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$REPO_ROOT/out/llama_server.pid"
LOG_FILE="$REPO_ROOT/out/llama_server.log"

mkdir -p "$REPO_ROOT/out"

if curl -sfm 2 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "llama-server already healthy on $HOST:$PORT"
    exit 0
fi

if [[ ! -x "$BIN" ]]; then echo "missing $BIN — build llama.cpp first"; exit 1; fi
if [[ ! -f "$MODEL" ]]; then echo "missing $MODEL — download GGUF first"; exit 1; fi

nohup "$BIN" -m "$MODEL" --host "$HOST" --port "$PORT" \
    --n-gpu-layers "$NGL" --ctx-size "$CTX" \
    > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "started pid $(cat "$PID_FILE"), waiting for health..."

for i in $(seq 1 60); do
    if curl -sfm 2 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
        echo "llama-server healthy on $HOST:$PORT (pid $(cat "$PID_FILE"))"
        exit 0
    fi
    sleep 1
done

echo "llama-server did not come up; last log lines:"
tail -20 "$LOG_FILE" >&2
exit 1
