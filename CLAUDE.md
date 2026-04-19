# AIingFuzzyVM

LLM-guided differential fuzzer for Ethereum Virtual Machine implementations. The project layers an AI strategy generator on top of two existing tools (vendored as git submodules) to produce higher-value test cases for cross-client EVM consensus testing.

## Goal

Find consensus discrepancies between EVM implementations (geth, nethermind, besu, erigon, etc.) by generating GeneralStateTests whose bytecode shape is **chosen by an LLM** instead of being purely random. The LLM emits a structured *strategy plan* (a DSL); FuzzyVM consumes that plan to bias which bytecode-building strategies fire and with what weights; goevmlab runs the resulting tests against multiple clients and reports diffs.

This has nothing to do with on-chain interaction — no RPC, no addresses, no Foundry. It's pure VM-level fuzzing.

## Architecture (current + planned)

```
[ LLM (RAG-conditioned) ]  --strategy plan DSL-->  [ FuzzyVM generator ]
                                                            |
                                                   GeneralStateTest JSON
                                                            v
                                                   [ goevmlab runner ]
                                                            |
                                                  per-client traces / diffs
                                                            v
                                                  feedback for next plan
```

### Submodules

- `FuzzyVM/` — fork of [MariusVanDerWijden/FuzzyVM](https://github.com/MariusVanDerWijden/FuzzyVM). Generates state tests. The seed bytes drive a `Filler` that picks among `Strategy` implementations (basic ops, call/create variants, jumps, precompiles). Each strategy has an `Importance()` weight (1–100) that determines how often it's picked. Entry points: `fuzzer/fuzzer.go`, `generator/generator.go`, `generator/strategy.go`. Output goes to `$FUZZYDIR/<hashprefix>/FuzzyVM-<hash>.json`.
- `goevmlab/` — [holiman/goevmlab](https://github.com/holiman/goevmlab). Runs generated tests across multiple EVM binaries and surfaces disagreements. Used unmodified as the execution harness.

### Strategy surface (what the LLM is steering)

Defined under `FuzzyVM/generator/`:
- `basic_strategies.go` — opcode emit, MSTORE/SSTORE/TSTORE, MLOAD/SLOAD/TLOAD, RETURN, KECCAK+SSTORE, BLOBHASH, etc.
- `call_strategies.go` — CREATE/CREATE2 + CALL/CALLCODE/DELEGATECALL/STATICCALL, precompile calls.
- `jump_strategies.go` — JUMP/JUMPI patterns + jumptable patching.

Currently `Importance()` is hardcoded. The LLM-guided path will override these (and possibly inject new composite strategies / seed hints / fork constraints) per fuzzing batch.

## Approach (per `WhiteishPaper.md`)

**Phase 1 — RAG + prompt templates** (best ROI, start here):
1. Build a retrieval index over: ethereum/tests, EIPs/opcode docs, historical client-diff incidents, prior `out/` finds and minimized repros, goevmlab differential results.
2. Prompt a hosted/local model (Qwen is the working pick) with: target fork + recent coverage gaps + recent divergences + objective.
3. Force output through a strict **strategy plan JSON schema** (steps, weights, constraints, seed hints) — no raw bytecode, no test JSON.
4. Validate, feed into FuzzyVM, run via goevmlab, log outcomes to grow the dataset.

**Phase 2 — light fine-tuning / preference tuning** only if Phase 1 plateaus. Reward: new coverage + cross-client disagreement. Penalize: invalid/unproductive plans.

## Current status (as of 2026-04-19)

Day 1 + Day 2 + Day 3 complete. Baseline ran 16h36m (1.26M state-tests, 339 crashers preserved, see `baseline_writeup.md`). LLM-guided pipeline is end-to-end operational with real RAG.

**Day 1 (baseline + plumbing):**
- **Plan loader** in `FuzzyVM/generator/plan.go`: reads JSON plan via `--plan path.json` or `FUZZYVM_PLAN=path.json` env var; overrides strategy weights, fork, banned opcodes. Stock behavior is the default when no plan is present.
- **`makeMapNormalized`** in the same file: bypasses a byte-overflow bug in upstream `generator/strategy.go:52 makeMap` that manifests only under plan-driven heavy weights. Stock path untouched.
- **`--out-dir`** flag on `FuzzyVM run` propagates to `FUZZYDIR`. Baseline writes to `out/baseline/`, LLM-guided runs write to `out/llm_guided/<plan_id>/`.
- **`dump` subcommand** (`./FuzzyVM dump --count 50 [--plan plan.json]`) runs the generator in-process and prints per-opcode emission frequency. Used by the orchestrator to verify bias.
- **Supervised baseline runner** at `scripts/start_baseline.sh` + crasher watcher at `scripts/crasher_watcher.sh`.
- **Smoke plan** at `orchestrator/plans/smoke_storage_heavy.json`.

**Day 2 (LLM + orchestrator pipeline):**
- **llama.cpp** built with CUDA at `~/tools/llama.cpp/build/bin/llama-server` (CUDA 13.2, RTX 4080, Ada sm_89).
- **Model** at `~/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf` (~5.1 GB). Loaded with full GPU offload; ~107 tok/s decode.
- **Server launcher** at `scripts/start_llama_server.sh` — idempotent, waits for `/health`, writes pid+log to `out/`.
- **`orchestrator/plan_schema.json`** — JSON Schema (Draft 2020-12) for the Strategy Plan DSL (semantic validation).
- **`orchestrator/plan.gbnf`** — GBNF grammar for llama.cpp grammar-constrained decoding (shape validation). Each rule is single-line / paren-grouped — llama.cpp's GBNF parser breaks rules at bare newlines, so multiline rules must be wrapped in `(...)`.
- **`orchestrator/rag_stub.py`** — hardcoded-snippet retriever (8 EIP / opcode / incident entries, word-overlap scoring). Placeholder; FAISS + bge-small lands Day 3.
- **`orchestrator/run_batch.py`** — objective → LLM (`/completion` with `grammar` field — note `/v1/chat/completions` silently drops grammar, so the native endpoint is mandatory) → `json.loads` → `jsonschema` validate → plan file → `./FuzzyVM run --plan`. Supports `--dry-run`, `--verify-bias`, `--duration`.
- **LLM sampling**: temperature 0.6, top_p 0.9, dry_multiplier 0.8, repeat_penalty 1.1. Prior to dry-sampling, the model looped on repeat keys until max_tokens; dry-sampling + `sw-entry` bounded to 20 in grammar fixed it.

**Day 3 (real RAG):**
- **Embedder**: `BAAI/bge-small-en-v1.5` (384-dim, ~25 MiB, runs on CPU). Cached under `~/models/sentence-transformers/`.
- **Corpus** at `orchestrator/rag/corpus/`: 912 EIPs (shallow clone of `ethereum/EIPs`, gitignored), `opcodes.md` (47 hand-written opcode entries, committed). Six historical-divergence "incident" entries and a baseline-run summary are inlined in `build_index.py`.
- **Index**: `orchestrator/rag/index/vectors.faiss` (FAISS flat IP, cosine via normalized embeddings) + `chunks.jsonl` sidecar, 966 chunks, 1.4 MiB. Gitignored — regenerable from `python3 orchestrator/rag/build_index.py` (~3 sec on CPU).
- **Retriever** at `orchestrator/rag_faiss.py`: lazy-loads the index, queries with bge's instruction-prefix convention. Drop-in for `rag_stub`; `run_batch.py` imports `rag_faiss` first and falls back to `rag_stub` if the index is missing.
- **Plan loader correctness**: removed `validOpcodeGenerator` from schema/grammar/prompt — the type exists in `basic_strategies.go` but is not registered in `basicStrategies`, so the Go loader rejected it.
- **Required field**: `strategy_weights` is now required in both schema and grammar (was optional; the LLM exploited that and emitted plans with no bias).
- **Few-shot example** added to system prompt — keeps the model emitting 5-12 strategies with rationale + bans rather than a one-strategy stub.

End-to-end on the EIP-2929 / SLOAD objective produced a plan with sloadGenerator=80 + nested-call strategies + BLOCKHASH/SELFDESTRUCT bans; `dump` confirms SLOAD: 2093 over 200 programs (vs ~10 for stock random) and zero BLOCKHASH/SELFDESTRUCT.

What's **not yet** built: goevmlab differential harness wiring, divergence summaries fed back into the next prompt, plateau rotation, preference tuning. See `WhiteishPaper.md`.

## Baseline runner

`scripts/start_baseline.sh` launches FuzzyVM under a supervisor loop (auto-restarts on crash; wipes `testdata/fuzz/FuzzVMBasic/` before each relaunch to avoid go-fuzz's crasher-replay trap). Flags: `--threads N`, `--out-dir PATH`, `--duration <N>{s,m,h,d}`. Run it idempotently — it no-ops if the supervisor is already alive.

State files (all under `out/`, one per session):
- `baseline.pid`    — supervisor PID. Kill this to stop everything; the trap forwards SIGTERM to the FuzzyVM child.
- `baseline.start`  — ISO-8601 launch time.
- `baseline.stop`   — scheduled-stop time (present only if `--duration` was used).
- `baseline.log`    — combined stderr/stdout of supervisor + FuzzyVM + child `go test --fuzz`.
- `baseline.watcher.pid`, `baseline.watcher.log` — crasher watcher, if running.

Important operational facts:
- `go test --fuzz` hits native cgo faults in geth's EVM every 2-4 min under current generation. The supervisor handles this; ~37% wall-clock is actual fuzzing, the rest is Go's baseline-coverage replay on each restart. This is substrate-level and affects the LLM-guided path identically, so baseline-vs-LLM fairness is preserved.
- `FuzzyVM/cmd/fuzzyvm/main.go` passes `-fuzzminimizetime=0` to the child `go test --fuzz` to skip Go's (60s, often-hanging) post-crash minimization phase. Unminimized crashers are fine — goevmlab reruns the full saved state test.
- The upstream FuzzyVM seed corpus (`FuzzyVM/corpus/`) contains at least one input that segfaults geth's EVM on startup. Must stay parked as `corpus_disabled/` — do not restore it.
- Go persistently caches "new interesting" inputs at `~/.cache/go-build/fuzz/.../FuzzVMBasic/` across restarts. Coverage is retained across crashes. Don't wipe this cache unless there's a reason.

## Working with the submodules

- Both submodules are Go projects (`go.mod` at their root). Modifications to FuzzyVM (strategy weights, new strategies, external plan ingestion) happen in-tree under `FuzzyVM/`.
- Treat `goevmlab/` as a black box unless something breaks at the harness boundary.
- Build: `cd FuzzyVM && go build -o FuzzyVM ./cmd/fuzzyvm`.
- Run (oneshot, no supervisor): `./FuzzyVM run [--threads N] [--out-dir PATH] [--plan plan.json]`. Output dir defaults to `./out`; also settable via `$FUZZYDIR`.
- Corpus generation: `./FuzzyVM corpus --count N [--plan plan.json]`.
- Plan tuning diagnostic: `./FuzzyVM dump --count 50 [--plan plan.json]` — prints opcode-frequency table.

## Methodology baseline: fuzzillai

Reference implementation to adapt from: [VRIG-RITSEC/fuzzillai](https://github.com/VRIG-RITSEC/fuzzillai) — a fork of Google Project Zero's Fuzzilli (JS-engine fuzzer) with an agentic LLM layer. Their `Sources/Agentic_System/` is the blueprint.

What we're **stealing** from them:
- Three-stage pipeline: *objective/section selection → context analysis → structured program-plan emission*.
- RAG over historical regression tests + traces (they index ~8000 regressions; we'll index EIPs, opcode docs, ethereum/tests metadata, and our own `out/` finds).
- "Evolve by generating" on plateaus: when divergence/coverage rate stalls, re-prompt with a shifted objective (their `EBG_plateau.py`). Cheap, high-ROI.
- Attribution: keep LLM-generated seeds in a **separate queue/folder** so we can measure their contribution vs. baseline random fuzzing.
- Preflight validation of tool paths + model availability before any agent reasoning starts.

What we're **not** copying:
- Their PostgreSQL + distributed fuzzing layer (we're single-machine, 6 days).
- gdb-based crash triage (EVM differential diffs come out of goevmlab as text, not native crashes).
- V8-code-navigation agents (we don't map EVM client internals; we target EVM semantics).
- Hosted LLM APIs — we run **local** on an RTX 4080 (16 GB VRAM).

## Local model stack

- **Server:** `llama.cpp` (llama-server) or Ollama. Either works; llama.cpp gives tighter grammar-constrained decoding via GBNF, which is a big win for schema-valid JSON output.
- **Model (primary candidate):** `Qwen2.5-Coder-7B-Instruct` at Q5_K_M (~5.4 GB VRAM, leaves headroom for embeddings + context). Strong at structured JSON and code reasoning.
- **Fallbacks:** `Qwen2.5-7B-Instruct` (non-coder) or `Llama-3.1-8B-Instruct` if Coder-7B hallucinates opcodes. Consider `Qwen2.5-Coder-14B-Instruct` Q4_K_M (~8.5 GB) only if 7B is the bottleneck.
- **Embeddings:** `bge-small-en-v1.5` or `all-MiniLM-L6-v2` via `sentence-transformers`. Tiny, runs on CPU fine.
- **Vector store:** FAISS flat index (no serving complexity).
- **Orchestrator:** Python. `jsonschema` for plan validation, `requests` for the local LLM HTTP API, `subprocess` to drive FuzzyVM and goevmlab.

## Strategy Plan DSL (v0 — implemented)

The LLM emits one JSON object per fuzzing batch. FuzzyVM reads it via `FuzzyVM/generator/plan.go:LoadPlanFile` and applies the settings before the generator's `init()` finishes building the strategy map. All fields are optional; omitted fields use defaults (including the stock FuzzyVM weights). Only `strategy_weights`, `fork`, and `constraints.banned_opcodes` are wired into generation today — the other fields are accepted by the loader but not yet consumed.

```json
{
  "plan_id": "sha256 of this document, filled in by orchestrator",
  "objective": "EIP-2929 warm/cold access divergence on nested DELEGATECALL",
  "fork": "Cancun",
  "rounds": { "min": 60, "max": 150 },
  "batch": { "num_tests": 50 },
  "strategy_weights": {
    "opcodeGenerator":        10,
    "validOpcodeGenerator":   10,
    "mstoreGenerator":         8,
    "sstoreGenerator":        25,
    "tstoreGenerator":        15,
    "sloadGenerator":         25,
    "tloadGenerator":         15,
    "mloadGenerator":          5,
    "returnGenerator":         2,
    "returnDataGenerator":     2,
    "pushGenerator":           5,
    "hashAndStoreGenerator":   5,
    "blobhashGenerator":       3,
    "memStorageGenerator":     3,
    "createCallRNGGenerator":  8,
    "createCallGenerator":    12,
    "randomCallGenerator":    20,
    "callPrecompileGenerator": 5,
    "jump":                    5
  },
  "parameter_hints": {
    "push_size_bias":     "full32",
    "mem_offset_bias":    "small",
    "sstore_slot_bias":   "low_cluster",
    "max_recursion_level": 5,
    "min_jump_distance":  10
  },
  "constraints": {
    "banned_opcodes":              ["BLOCKHASH", "SELFDESTRUCT"],
    "required_opcodes_any_of":     ["TSTORE", "TLOAD"],
    "allowed_call_ops":            ["CALL", "DELEGATECALL", "STATICCALL"],
    "allowed_precompiles":         ["0x01", "0x02", "0x09"]
  },
  "seed_hint": {
    "hex": null,
    "notes": "null means orchestrator picks a fresh seed"
  },
  "rationale": "Short free-text 'why this plan' — one paragraph. Logged for later analysis of what prompts the LLM to produce productive plans.",
  "expected_signal": ["state_root_divergence", "gas_divergence"]
}
```

Weight semantics: numbers on a 1–100 scale (same as `Strategy.Importance()`). Plan-loaded weights go through `makeMapNormalized` in `plan.go`, which divides each by the total and spreads across 256 buckets — this sidesteps a byte-overflow bug in upstream `makeMap` that chaotically stomps buckets when cumulative weight exceeds 255. Omitting a strategy falls back to the default importance. Use `./FuzzyVM dump --plan plan.json` to verify a plan biases generation the way you expect before kicking off a run.

**Implementation:** `generator/plan.go` holds the `Plan` struct, `LoadPlanFile`, `ApplyPlan`, `makeMapNormalized`, and `IsBanned`. `generator/basic_strategies.go` consults `IsBanned` inside `opcodeGenerator.Execute` and `validOpcodeGenerator.Execute` to skip / substitute banned opcodes. `cmd/fuzzyvm/main.go` accepts `--plan` on `corpus`, `run`, and `dump` subcommands and propagates it to the child `go test --fuzz` process via `FUZZYVM_PLAN=<path>`.

**Validation contract:** plan loader rejects (a) unknown strategy names (error includes the full known-strategy list), and (b) banned opcodes that don't name real EVM opcodes. On rejection the loader returns an error; when reached from the CLI this aborts the run before subprocess launch. The LLM-side JSON-schema validator in the orchestrator is not yet built.

## 6-day build & fuzz plan (deadline 2026-04-23)

**Day 1 — baseline + plumbing. ✅ done.** Plan loader, normalized weight buckets, `--out-dir`/`--plan`/`dump` CLI, supervised baseline runner with `--duration`, crasher preservation watcher, and stock-random 16h baseline run launched.

**Day 2 — local LLM up.** llama.cpp serving Qwen2.5-Coder-7B Q5_K_M with a GBNF grammar for our DSL. Python orchestrator: prompt → LLM → JSON schema validator → plan file → FuzzyVM batch. Prove end-to-end with a trivial RAG stub.

**Day 3 — real RAG.** FAISS index over (a) EIPs markdown, (b) opcode reference, (c) ethereum/tests GeneralStateTests metadata (opcode frequencies + folder-name objectives), (d) any prior `out/` finds. Start feedback: parse goevmlab diffs → recent-divergences summary fed into next prompt.

**Day 4 — differential harness.** Wire goevmlab against 2–3 client binaries (geth + revm minimum; add besu if time allows). Run the first full loop: LLM → plan → FuzzyVM batch → goevmlab → diffs → LLM. Log coverage and divergence counts per batch.

**Day 5 — plateau rotation + long run.** Add plateau detection (if divergence rate < threshold for K batches, rotate objective via a second prompt template). Start the long overnight run.

**Day 6 — compare & write up.** Metrics: unique divergences per CPU-hour, unique opcode sequences, corpus-dedup rate, objective→divergence attribution. Stock-random baseline vs. LLM-guided on equal CPU budget.

## Repo layout

```
.
├── CLAUDE.md                  this file
├── README.md
├── WhiteishPaper.md           project plan / rationale (read first for methodology)
├── FuzzyVM/                   submodule — generator (patched in-tree)
│   ├── cmd/fuzzyvm/           CLI: run, corpus, dump, bench, minCorpus
│   ├── generator/plan.go      plan loader + makeMapNormalized (ours)
│   └── fuzzer/fuzzer.go       go-fuzz entry point (FuzzVMBasic)
├── goevmlab/                  submodule — differential harness (unmodified)
├── orchestrator/
│   ├── plan_schema.json       JSON Schema for the DSL (semantic validation)
│   ├── plan.gbnf              GBNF grammar for llama.cpp (shape validation)
│   ├── rag_stub.py            Day-2 fallback retriever (used if index absent)
│   ├── rag_faiss.py           Day-3 FAISS retriever (preferred)
│   ├── run_batch.py           objective → LLM → validate → FuzzyVM
│   ├── rag/
│   │   ├── build_index.py     embeds corpus into orchestrator/rag/index/
│   │   ├── corpus/
│   │   │   ├── opcodes.md     hand-written opcode reference (committed)
│   │   │   └── EIPs/          shallow clone of ethereum/EIPs (gitignored, 153 MB)
│   │   └── index/             FAISS index + chunks.jsonl (gitignored, 1.4 MiB)
│   └── plans/
│       └── smoke_storage_heavy.json   manual smoke-test plan
├── scripts/
│   ├── start_baseline.sh      supervised baseline runner
│   ├── start_llama_server.sh  idempotent llama-server launcher
│   └── crasher_watcher.sh     preserves testdata crashers to out/crashers/
└── out/
    ├── baseline/              stock FuzzyVM random run (gitignored)
    ├── llm_guided/<plan_id>/  per-plan LLM-guided batches (gitignored)
    ├── crashers/              preserved go-fuzz crashers (+ manifest.tsv)
    ├── baseline.{pid,start,stop,log}          supervisor session state
    ├── baseline.watcher.{pid,log}             crasher-watcher session state
    └── llama_server.{pid,log}                 llama-server session state
```

External (outside repo, not version-controlled):
- `~/tools/llama.cpp/`              CUDA-built llama.cpp
- `~/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf`  local model (~5.1 GB)
- `~/models/sentence-transformers/` bge-small-en-v1.5 cache (~25 MiB)

To rebuild the RAG index from a fresh checkout:
```
cd orchestrator/rag/corpus
git clone --depth 1 --filter=blob:limit=200k https://github.com/ethereum/EIPs.git
cd ../.. && python3 rag/build_index.py
```

**To build in the future:** `orchestrator/plan_schema.json`, `orchestrator/plan.gbnf`, `orchestrator/rag/`, `orchestrator/prompts/`, `out/llm_guided/<plan_id>/`.

## Useful references (from WhiteishPaper.md)

- Marius van der Wijden's FuzzyVM blog: https://mariusvanderwijden.github.io/blog/2021/05/02/FuzzyVM/
- Foundational paper: https://arxiv.org/pdf/1903.08483 (this project follows that pipeline but with LLM-driven strategy selection)
- Differential fuzzing across languages: https://r9295.github.io/posts/differential-fuzzing-accross-languages/
- Candidate training/RAG data: ethereum/tests, andstor/smart_contracts (HF), evm-bench.
