# Modifying the FuzzyVM

### Preface

This actually doesn't have much to do technically with the blockchain, so we don't need to use tools like foundry or concern ourselves with addresses and RPC calls.

This entirely focuses on creating test cases for different implementations of the EVM to see if it can cause any discrepancies on how they handle it.

## **What the model should do**

- Pick or propose **strategy sequences** (e.g., more calls + storage + jumps).
- Suggest **targeted scenarios** (e.g., edge gas, precompile boundary sizes, deep call chains).
- React to feedback ("this area found divergences, explore neighbors").

## **What to train (or condition) on**

Best results come from a **mixture** — but not every candidate dataset earns its slot. Verdicts:

- **Ethereum state tests** (`ethereum/tests` → `GeneralStateTests`) → **YES**. Don't ingest the full JSON; extract per-test summaries (`{folder_name (= objective), opcodes_touched, pre_state_shape, expected_post_shape}`). Thousands of small summaries in FAISS is cheap and retrievable.
- **`goevmlab/trophies/`** → **YES, highest value.** 9 documented historical cross-client bugs already vendored in the repo (besu DoS, nimbus consensus errors, reth consensus issue, EIP-2929, etc.). This *is* "historical client-diff bugs" — we don't have to hunt for them.
- **EIPs** (ethereum/EIPs markdown) → **YES**. Small, authoritative, fork-semantic grounding. Required for fork-specific objectives.
- **Our own fuzz outputs** (`out/`, crashes, minimized repros) → **YES, as a feedback loop.** Append every divergence-producing plan + its outcome to the RAG index and weight retrieval by recency + past success. This is the Phase-1-friendly version of "reward plans that produce new coverage or cross-client disagreement" — no training loop, just scored memory.
- **`evm-bench`** → **skip for v0.** Performance-focused, wrong signal for correctness/divergence.
- **`andstor/smart_contracts`** → **skip for v0.** Production contracts are noisy; they aren't test patterns, and the whitepaper itself hedged on this one.
- **Other open-source differential fuzzers' test cases** → defer. Ask Thanos if an opportunity arises, but don't block on it.

## **Best practical approach**

Start with **RAG + prompt templates** before heavy training:

- Retrieve similar prior tests/bugs by topic (CALL, CREATE2, warm/cold access, precompiles, EOF, etc.).
- Ask the model to output our **structured DSL** (strategy plan), not test JSON/raw bytecode.
- Validate and execute through FuzzyVM/goevmlab.
- Log outcomes to build a dataset for later fine-tuning.

## **Methodology baseline: fuzzillai**

Reference implementation to adapt from: [VRIG-RITSEC/fuzzillai](https://github.com/VRIG-RITSEC/fuzzillai) — a fork of Google Project Zero's Fuzzilli (JS-engine fuzzer) with an agentic LLM layer. Their `Sources/Agentic_System/` is the blueprint.

**Stealing:**

- Three-stage pipeline: *objective/section selection → context analysis → structured program-plan emission*.
- RAG over historical regression tests + traces (they index ~8000 regressions; we index EIPs, `ethereum/tests` metadata, `goevmlab/trophies/`, and our own `out/`).
- "Evolve by generating" on plateaus: when divergence/coverage rate stalls, re-prompt with a shifted objective (their `EBG_plateau.py`). Cheap, high-ROI.
- **Attribution isolation**: keep LLM-generated seeds in a separate folder (`out/llm_guided/`), so we can measure their contribution vs. baseline random fuzzing.
- Preflight validation of tool paths + model availability before any agent reasoning.

**Not copying:**

- PostgreSQL + distributed fuzzing (single machine).
- gdb-based crash triage (EVM diffs come out of goevmlab as text; no native crashes to inspect).
- V8-code-navigation agents (we target EVM semantics, not client internals).
- Hosted LLM APIs — local only.

## **If we do train/fine-tune later**

Train for a supervised target like:

- Input: fork + recent coverage gaps + recent divergences + objective
- Output: strategy plan DSL (steps, weights, constraints, seed hints)

Then optionally add ranking/reward:

- Reward higher for plans that produce **new coverage** or **cross-client disagreement**.
- Penalize invalid/unproductive plans.

---

## **Recommendation**

- **Phase 1 (best ROI):**
    - Use a strong existing LLM, locally hosted.
    - Add **RAG** over EVM tests, EIPs, `goevmlab/trophies/`, and our own `out/`.
    - Force output into our **template DSL** (JSON schema + validator + grammar-constrained decoding).
- **Phase 2:**
    - Add light **fine-tuning** (or preference tuning) only if Phase 1 hits a ceiling.

## **Practical stack**

### Local model

- **Server:** `llama.cpp` (llama-server). Reason: supports **GBNF grammars** that constrain decoding to our DSL schema at the token level, which drives invalid-output rate to zero and saves retry loops. Ollama is the fallback.
- **Primary model:** `Qwen2.5-Coder-7B-Instruct` at Q5_K_M (~5.4 GB VRAM on the target 4080, leaves headroom for embeddings + context). Coder variant because we're emitting structured JSON that parameterizes code generation.
- **Fallbacks:** `Qwen2.5-7B-Instruct` (non-coder) or `Llama-3.1-8B-Instruct` if the Coder variant hallucinates opcodes. `Qwen2.5-Coder-14B-Instruct` Q4_K_M (~8.5 GB) only if 7B is clearly the bottleneck.
- **Embeddings:** `bge-small-en-v1.5` or `all-MiniLM-L6-v2` via `sentence-transformers`. Runs on CPU; no VRAM cost.
- **Vector store:** FAISS flat index. No serving complexity.
- **Orchestrator:** Python. `jsonschema` for plan validation, local HTTP for LLM calls, `subprocess` to drive FuzzyVM and goevmlab.

### Target EVM clients (differential set)

Only pick from what `goevmlab/evms/` already has adapters for: **besu, eels, erigon, evmone, geth, nethermind, nimbus, revm**.

- **`geth`** — the de-facto reference implementation. Required.
- **`revm`** — Rust, fast, trivial to build. High test throughput. Required.
- **`nethermind`** — historically the most divergent client vs. geth in this codebase. Evidence: `FuzzyVM/generator/basic_strategies.go:48` already special-cases BLOCKHASH because Nethermind diverges there. Include if it builds cleanly on WSL2.
- Skip `besu / erigon / nimbus / evmone / eels` for v0 — diminishing returns per setup-hour.

### Plan granularity

**Per-batch, ~50 tests per plan.** One LLM plan drives 50 FuzzyVM test generations. Per-test inference would cost ~50× more LLM time for marginal targeting gain. Per-batch matches the DSL shape ("steps, weights, constraints, seed hints") and is cheaper.

### Strategy Plan DSL (v0 draft)

The LLM emits one JSON object per fuzzing batch. FuzzyVM reads it and applies the settings to its existing strategy table. All fields optional; omitted fields fall back to defaults.

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
  "rationale": "Short free-text 'why this plan' — one paragraph. Logged for later analysis.",
  "expected_signal": ["state_root_divergence", "gas_divergence"]
}
```

**Weight semantics:** numbers on a 1–100 scale, same as `Strategy.Importance()` today. The `Probability` function in `FuzzyVM/generator/strategy.go` normalizes them across 255 buckets. Omitting a strategy name means "use the default importance."

**Why this shape:** maps 1:1 onto the existing `strategies` map in `FuzzyVM/generator/generator.go:42` with minimum code change — we add an exported `SetStrategyWeights(map[string]int)` and `SetConstraints(...)` and rebuild the strategy map. Parameter hints feed into the `Filler` so `MemInt()` / `Byte()` can be biased. Anything more expressive (explicit sequences, brand-new composite strategies) is **v1 territory** and deliberately out of scope for v0.

**Validation contract:** orchestrator rejects plans that (a) fail JSON schema, (b) name unknown strategies, or (c) declare banned opcodes that aren't real EVM opcodes. On rejection, re-prompt with the validator error. GBNF grammar at the decoder level should make rejections rare.

### Baseline comparison

- **Fairness metric:** **equal CPU-hours**, with test counts reported alongside. "LLM-guided produced X tests in N hours; stock random produced ~50X tests in N hours; LLM-guided found Y unique divergences, stock found Z."
- **Baseline run:** stock FuzzyVM with random strategy selection, same client set (geth + revm [+ nethermind]), running in the background from the earliest possible moment. Accumulating CPU-hours while the LLM pipeline is still being built costs nothing and protects the comparison if the pipeline slips.
- **Output isolation:** `out/baseline/` vs `out/llm_guided/` (keyed by `plan_id`), so attribution is unambiguous.

### Repo layout (target)

```
.
├── CLAUDE.md
├── README.md
├── WhiteishPaper.md
├── FuzzyVM/                submodule — generator (we patch here)
├── goevmlab/               submodule — harness (unmodified)
├── orchestrator/           (to be built) python: prompt, RAG, validator, runner
│   ├── plan_schema.json
│   ├── plan.gbnf           llama.cpp grammar for DSL-constrained decoding
│   ├── rag/                ingestion scripts + FAISS index
│   └── prompts/            objective templates
└── out/
    ├── baseline/           stock FuzzyVM random run
    └── llm_guided/         LLM-driven run, keyed by plan_id
```

## Datasets

Verdicts consolidated from **What to train (or condition) on** above.

- `https://github.com/ethereum/tests` → **YES** (GeneralStateTests, summaries only).
- `goevmlab/trophies/` (vendored in this repo) → **YES, highest value.**
- `https://github.com/ethereum/EIPs` → **YES** (fork-semantic grounding).
- Our own `out/` finds → **YES** (scored feedback loop).
- `https://github.com/ziyadedher/evm-bench` → **skip v0** (performance, not correctness).
- `https://huggingface.co/datasets/andstor/smart_contracts` → **skip v0** (real contracts, not test patterns).
- Other open-source differential fuzzers → defer; maybe ask Thanos if easy.

## Resources

- Basics we are implementing / modifying
    - https://github.com/MariusVanDerWijden/FuzzyVM (added to repo)
    - https://github.com/holiman/goevmlab (added to repo)
    - https://mariusvanderwijden.github.io/blog/2021/05/02/FuzzyVM/
- Methodology baseline for the AI layer
    - https://github.com/VRIG-RITSEC/fuzzillai (blueprint for the agentic system — adapt `Sources/Agentic_System/`)
- Advanced / More reading
    - https://r9295.github.io/posts/differential-fuzzing-accross-languages/
    - https://github.com/R9295/autarkie
    - https://dl.acm.org/doi/abs/10.1002/smr.2556 (EVMFuzz proposal)
    - https://github.com/ziyadedher/evm-bench (candidate alternate harness if goevmlab disappoints)
- Absolutely IMPORTANT
    - https://arxiv.org/pdf/1903.08483 (foundational paper — we basically do this pipeline, except the LLM generates our strategy plans that choose the seed contract route to go down)
        - Our strategy template approach differs by telling the generator how to string bytecode together, which kinds of program-building steps to prefer (opcode vs call vs jump vs storage, etc.) and with what constraints/fork/seed.
