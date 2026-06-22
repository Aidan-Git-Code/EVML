# AIingFuzzyVM

LLM-guided differential fuzzer for Ethereum Virtual Machine implementations. The orchestrator wraps two existing tools (vendored as git submodules) with an AI strategy generator that biases test-case generation toward consensus-sensitive corners of EVM semantics.

The pipeline is: objective + RAG context + recent divergences -> local LLM emits a strategy plan (JSON DSL) -> FuzzyVM consumes the plan to bias bytecode generation -> goevmlab runs the resulting GeneralStateTests across geth, revm, and besu -> divergences feed back into the next prompt -> plateau detector rotates the objective when several batches stall.

Note on scope: the published experiment (see `paper.tex` / `final_report.md`) used two clients, geth and revm. besu was added afterward as a third differential client, so the current harness runs a 3-way panel. The report's null result is stated against the geth+revm pair it was measured on.

This is pure VM-level fuzzing. No RPC, no on-chain interaction, no Foundry.

## Repo layout

```
.
├── WhiteishPaper.md           original methodology / rationale
├── final_report.md            project report (markdown draft)
├── paper.tex                  IEEE conference-format report
├── docs/
│   ├── distributed-fuzzing.md  design for scaling the fuzzer across machines
│   └── dockerization.md        design for packaging fleet nodes as containers
├── FuzzyVM/                   submodule: state-test generator (patched in-tree)
├── goevmlab/                  submodule: differential harness (unmodified)
├── orchestrator/
│   ├── plan_schema.json       JSON Schema for the strategy-plan DSL
│   ├── plan.gbnf              GBNF grammar for grammar-constrained decoding
│   ├── rag_faiss.py           FAISS retriever (preferred)
│   ├── rag_stub.py            keyword-overlap fallback
│   ├── differential.py        goevmlab runtest wrapper + diff_report.json
│   ├── rotate.py              plateau detector + LLM objective rotator
│   ├── run_batch.py           one batch: objective -> LLM -> validate -> fuzz -> diff
│   ├── rag/build_index.py     embeds corpus into orchestrator/rag/index/
│   ├── dashboard/             stats web server + frontend (server.py, index.html)
│   └── plans/                 hand-written smoke plans
├── scripts/
│   ├── start_baseline.sh      supervised stock-random baseline runner
│   ├── start_llama_server.sh  idempotent llama-server launcher
│   ├── start_llm_loop.sh      LLM-guided loop driver (scheduling + llama autostart)
│   ├── startup_instruct.sh    prints how to start everything + live status
│   ├── stop_fuzzing.sh        stops the loop, leaves a post-hoc diff running
│   └── crasher_watcher.sh     preserves go-fuzz crashers
└── out/
    ├── baseline/              stock random run output (gitignored)
    ├── llm_guided/<plan_id>/  per-plan LLM-guided batches (gitignored)
    └── *.{pid,start,stop,log} session-state files
```

## Reproducing the experiment

The full setup needs a CUDA GPU (we used an RTX 4080, 16 GB VRAM), Linux (we ran WSL2), ~30 GB free disk, geth's `evm`, revm's `revme`, Python 3.11+, Go 1.22+, and Rust 1.91+. The optional third client, besu's `evmtool`, additionally needs a JRE (besu 26.6.1 requires JDK 25).

### 1. Clone with submodules

```bash
git clone --recurse-submodules https://github.com/Aidan-Git-Code/EVML.git
cd EVML
```

If you cloned without `--recurse-submodules`, run `git submodule update --init --recursive`.

### 2. Build FuzzyVM and goevmlab

```bash
cd FuzzyVM && go build -o FuzzyVM ./cmd/fuzzyvm && cd ..
cd goevmlab && go build -o runtest ./cmd/runtest && cd ..
```

### 3. Install the differential clients

```bash
# geth's evm binary
GOBIN=~/go/bin go install github.com/ethereum/go-ethereum/cmd/evm@v1.15.11

# revm's revme binary (needs Rust 1.91+ from rustup, not Debian's 1.75)
cargo install revme
```

Optional third client, besu's `evmtool`. besu 26.6.1 ships Java 25 class files, so it needs a JDK 25 even though the rest of the project runs on whatever Java you have. A small wrapper pins besu to JDK 25 without touching the system default:

```bash
# JDK 25 (Debian/Ubuntu)
sudo apt-get install -y openjdk-25-jre-headless

# besu distribution (contains bin/evmtool)
cd ~/tools && VER=26.6.1
curl -sL -O https://github.com/besu-eth/besu/releases/download/$VER/besu-$VER.tar.gz
curl -sL -O https://github.com/besu-eth/besu/releases/download/$VER/besu-$VER.tar.gz.sha256
sha256sum -c besu-$VER.tar.gz.sha256 && tar xzf besu-$VER.tar.gz

# wrapper: run evmtool under JDK 25 only
cat > ~/tools/besu-$VER/bin/evmtool-jdk25 <<'EOF'
#!/usr/bin/env bash
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64
exec "$(dirname "$0")/evmtool" "$@"
EOF
chmod +x ~/tools/besu-$VER/bin/evmtool-jdk25
```

`orchestrator/differential.py` auto-detects the wrapper at `~/tools/besu-26.6.1/bin/evmtool-jdk25` (override with the `BESU_BIN` env var) and adds besu to the panel via goevmlab's `--besubatch` flag. If besu is absent, the harness runs geth + revm only, unchanged.

### 4. Build llama.cpp with CUDA and download the model

```bash
git clone https://github.com/ggerganov/llama.cpp.git ~/tools/llama.cpp
cd ~/tools/llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build -j

mkdir -p ~/models
wget -O ~/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf \
  https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q5_k_m.gguf
```

### 5. Build the RAG index

```bash
cd orchestrator/rag/corpus
git clone --depth 1 --filter=blob:limit=200k https://github.com/ethereum/EIPs.git
cd ../..
pip install sentence-transformers faiss-cpu jsonschema requests
python3 rag/build_index.py
```

The index lands at `orchestrator/rag/index/` (about 1.4 MiB).

### 6. Start the local LLM server

```bash
./scripts/start_llama_server.sh
```

Idempotent. Writes pid+log to `out/`. Waits for `/health` before returning.

### 7. Run a single batch (smoke test)

```bash
python3 orchestrator/run_batch.py \
  --objective "EIP-2929 warm/cold access divergence" \
  --fork Cancun \
  --threads 4 \
  --duration 60s \
  --diff
```

You should see a plan get generated, FuzzyVM bias toward warm/cold-access strategies, and goevmlab produce a `diff_report.json` under `out/llm_guided/plan_<id>/diff/`.

### 8. Reproduce the long runs

Stock random baseline (matches our 16h36m run):

```bash
./scripts/start_baseline.sh --threads 16 --duration 16h
```

LLM-guided run (matches our 13h30m run):

```bash
./scripts/start_llm_loop.sh \
  --objective "EIP-1153 TSTORE visibility across nested DELEGATECALL" \
  --threads 16 \
  --duration 13h30m \
  --batch-duration 90s \
  --feedback-n 3 --rotate-if-plateau 3 \
  --no-diff
```

`--no-diff` runs generation only, matching the baseline's behavior so the comparison stays fair. Run differential post-hoc through the orchestrator wrapper, one report per plan dir (it adds besu automatically when the wrapper is present):

```bash
for d in out/llm_guided/plan_*/out; do
  python3 orchestrator/differential.py "$d" --threads 12
done
```

The published comparison used geth + revm only; running the sweep with besu present gives the 3-way panel and rewrites each `diff_report.json` with besu's vote. besu cold-starts a JVM per invocation, so the sweep is much slower than the geth+revm pair; budget accordingly (CPU is free once fuzzing stops).

### 9. Stop a running session

```bash
kill $(cat out/llm_loop.pid)        # or out/baseline.pid
```

The supervisor's SIGTERM trap forwards to its children.

## Operating the fuzzer

`scripts/startup_instruct.sh` prints how to start each piece plus the live status of llama, the loop, the dashboard, and the GPU. It reads state only and starts nothing.

`scripts/stop_fuzzing.sh` stops the fuzzing loop (supervisor, `run_batch`, FuzzyVM workers, llama) but leaves a running post-hoc differential sweep alone. It targets the loop's process subtree by pid rather than by pattern, because the loop and a post-hoc sweep both run `runtest --besubatch` and pattern-matching would kill both. Pass `--keep-llama` to leave the LLM server up.

The loop driver (`start_llm_loop.sh`) has a few conveniences beyond the reproduction commands above:

- It ensures llama-server is healthy before each batch, starting it via `start_llama_server.sh` if down (local URLs only). Disable with `--no-llm-autostart`.
- Scheduling: `--duration 6h` (relative), `--stop-at "2026-06-22 14:00"` (absolute end), `--start-at "2026-06-22 02:00"` (wait until an absolute time before batch 1). `--start-at` and `--stop-at` combine to fuzz inside a window; both accept anything `date -d` parses.
- With diffing on (the default), besu joins automatically, so a normal run already uses the 3-client panel.
- The objective auto-rotates after `--rotate-if-plateau K` zero-divergence batches (default 3). On a corpus that is already all-zero-divergence it rotates on batch 1, so pass `--rotate-if-plateau 0` to pin a fixed objective.

### Dashboard

```bash
python3 orchestrator/dashboard/server.py    # then open http://127.0.0.1:8090/
```

Read-only viewer. The `/api/stats` endpoint scans `out/llm_guided/` diff reports plus session state and returns totals (tests, divergences, batches, plans, crashers), a divergence rate, loop/llama status, the current objective, and recent batches/divergences. The clients shown reflect the most recently written diff report.

## Design docs

This README and [`paper.tex`](paper.tex) describe the system as it runs today: one machine, one GPU, the single-machine pipeline above. Two design docs live under `docs/`, both not built yet.

- [`docs/distributed-fuzzing.md`](docs/distributed-fuzzing.md) plans scaling the pipeline across many machines: a GPU mesh of planners, a central coordinator, and a CPU mesh that generates and diffs, all sharing one corpus. Start here.
- [`docs/dockerization.md`](docs/dockerization.md) plans packaging the fleet's nodes as containers so any machine can join without matching host packages, and so the differential client versions stay pinned fleet-wide. It builds on the distributed design but reads on its own.

## What's in the report

[`paper.tex`](paper.tex) has the IEEE conference-format writeup with a TikZ architecture diagram. [`final_report.md`](final_report.md) is the markdown draft that fed into it. [`WhiteishPaper.md`](WhiteishPaper.md) has the original plan from before any code was written.

## Authors

Aidan Morgan and Odessa Rybski, Department of Computing Security, Rochester Institute of Technology. Course project for CSEC-559/659, Spring 2026.
