# AIingFuzzyVM

LLM-guided differential fuzzer for Ethereum Virtual Machine implementations. The orchestrator wraps two existing tools (vendored as git submodules) with an AI strategy generator that biases test-case generation toward consensus-sensitive corners of EVM semantics.

The pipeline is: objective + RAG context + recent divergences → local LLM emits a strategy plan (JSON DSL) → FuzzyVM consumes the plan to bias bytecode generation → goevmlab runs the resulting GeneralStateTests across geth and revm → divergences feed back into the next prompt → plateau detector rotates the objective when several batches stall.

This is pure VM-level fuzzing. No RPC, no on-chain interaction, no Foundry.

## Repo layout

```
.
├── CLAUDE.md                  full project context (read this first)
├── WhiteishPaper.md           original methodology / rationale
├── final_report.md            project report (markdown draft)
├── paper.tex                  IEEE conference-format report
├── FuzzyVM/                   submodule: state-test generator (patched in-tree)
├── goevmlab/                  submodule: differential harness (unmodified)
├── orchestrator/
│   ├── plan_schema.json       JSON Schema for the strategy-plan DSL
│   ├── plan.gbnf              GBNF grammar for grammar-constrained decoding
│   ├── rag_faiss.py           FAISS retriever (preferred)
│   ├── rag_stub.py            keyword-overlap fallback
│   ├── differential.py        goevmlab runtest wrapper + diff_report.json
│   ├── rotate.py              plateau detector + LLM objective rotator
│   ├── run_batch.py           one batch: objective → LLM → validate → fuzz → diff
│   ├── rag/build_index.py     embeds corpus into orchestrator/rag/index/
│   └── plans/                 hand-written smoke plans
├── scripts/
│   ├── start_baseline.sh      supervised stock-random baseline runner
│   ├── start_llama_server.sh  idempotent llama-server launcher
│   ├── start_llm_loop.sh      Day-5 LLM-guided loop driver (overnight)
│   └── crasher_watcher.sh     preserves go-fuzz crashers
└── out/
    ├── baseline/              stock random run output (gitignored)
    ├── llm_guided/<plan_id>/  per-plan LLM-guided batches (gitignored)
    └── *.{pid,start,stop,log} session-state files
```

`CLAUDE.md` documents every design decision, every patched bug, and the day-by-day status. Read it before changing anything.

## Reproducing the experiment

The full setup needs a CUDA GPU (we used an RTX 4080, 16 GB VRAM), Linux (we ran WSL2), ~30 GB free disk, geth's `evm`, revm's `revme`, Python 3.11+, Go 1.22+, and Rust 1.91+.

### 1. Clone with submodules

```bash
git clone --recurse-submodules https://github.com/<owner>/AIingFuzzyVM.git
cd AIingFuzzyVM
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

`--no-diff` runs generation only, matching the baseline's behavior so the comparison stays fair. Run differential post-hoc as a single sweep:

```bash
goevmlab/runtest \
  --geth ~/go/bin/evm --revme ~/.cargo/bin/revme \
  --parallel 8 --outdir out/posthoc_diff \
  'out/llm_guided/*/out/*/FuzzyVM-*.json'
```

Same command for the baseline, swapping the glob.

### 9. Stop a running session

```bash
kill $(cat out/llm_loop.pid)        # or out/baseline.pid
```

The supervisor's SIGTERM trap forwards to its children.

## What's in the report

`paper.tex` has the IEEE conference-format writeup with a TikZ architecture diagram. `final_report.md` is the markdown draft that fed into it. `CLAUDE.md` has the engineering log. `WhiteishPaper.md` has the original plan from before any code was written.

## Authors

Aidan Morgan and Odessa Rybski, Department of Computing Security, Rochester Institute of Technology. Course project for CSEC-559/659, Spring 2026.
