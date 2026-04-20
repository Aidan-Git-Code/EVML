# LLM-Guided Differential Fuzzing of Ethereum Virtual Machine Implementations

**CSEC-559/659 Group Project, Generative AI in Cybersecurity**

Draft v1 (2026-04-20). Experimental results pending completion of the 13h30m fair-comparison run. Sections marked TODO require post-hoc differential analysis before final submission.

---

## 1. Abstract

Consensus bugs between Ethereum Virtual Machine implementations can fork the blockchain, causing financial loss and network instability. Differential fuzzing surfaces such bugs by executing the same bytecode across multiple clients and flagging divergent outputs. Existing fuzzers such as FuzzyVM generate bytecode via random selection from a set of hand-written strategies, with each strategy weighted by a static importance value. Random selection spends most of its budget on broadly convergent behavior and rarely stresses the narrow state spaces around specific Ethereum Improvement Proposals (EIPs).

This work replaces the random strategy selector with a locally-hosted large language model (LLM) conditioned on a retrieval-augmented knowledge base of EIP texts, opcode documentation, and prior divergence incidents. The LLM emits a JSON strategy plan per batch that biases strategy weights, bans risky opcodes, and specifies an objective keyed to a consensus-sensitive aspect of EVM semantics. A plateau detector rotates the objective when several consecutive batches produce no divergences, mirroring the "evolve by generating" pattern from fuzzillai. A patched FuzzyVM consumes the plan; a goevmlab differential harness executes the generated state tests across geth and revm; divergence reports feed back into the next prompt.

The system was evaluated against a 16h36m baseline run of stock random FuzzyVM (1.26M state-tests, 339 preserved crashers). A 13h30m equal-CPU-budget LLM-guided run produced [N] batches across [M] rotated objectives. The comparison is presented across divergences per CPU-hour, unique opcode-sequence coverage, and corpus-dedup rate. Security analysis covers adversarial risks specific to LLM-guided fuzzing, including prompt injection through the retrieval corpus and dual-use concerns around 0-day discovery.

*[TODO: fill in final numbers once post-hoc differential pass completes.]*

---

## 2. Introduction

The Ethereum Virtual Machine is a stack machine specified informally across a yellow paper, hundreds of EIPs, and a reference test suite at `ethereum/tests`. Multiple independent implementations execute the same bytecode to reach consensus on state transitions. When two implementations disagree, the network can fork. Historical examples include the Shanghai fork divergence in 2016, the Constantinople delay over EIP-1283, and the 2020 Geth-OpenEthereum divergence on a malformed SSTORE sequence. Finding such divergences before they reach mainnet is a core defensive task for Ethereum security.

Differential fuzzing treats the problem as a cross-implementation equivalence check. A generator emits candidate bytecode; each client executes it on the same pre-state; any output mismatch (state root, gas consumed, return data) is a candidate bug. FuzzyVM, published by van der Wijden in 2021, is a widely used generator for this workflow. It produces `GeneralStateTest` JSON files consumable by goevmlab, a harness that shells out to geth, revm, besu, erigon, and nethermind binaries and compares their traces.

The generator in FuzzyVM picks among twenty or so strategies (SSTORE-heavy sequences, CREATE/CREATE2, precompile calls, jumptable patching, and so on) weighted by a hardcoded `Importance()` value in the range one to one hundred. Random selection from this weighted distribution is fast and simple, and has historically found real consensus bugs. It also spends the overwhelming majority of its time on broadly-convergent behavior: plain arithmetic, stack pushes, and memory operations that every compliant implementation handles identically. Objectives tied to specific EIPs, such as the warm/cold access accounting introduced by EIP-2929 or the transient storage semantics of EIP-1153, occupy a narrow slice of the strategy space and are rarely stressed in depth.

This project asks whether an LLM can steer strategy selection toward objectives with a known consensus-sensitive structure. The LLM does not produce bytecode. It produces a structured JSON plan that biases the random generator: which strategies to emphasize, which to omit, which opcodes to forbid, and what fork to target. FuzzyVM consumes the plan and generates bytecode under the biased distribution. goevmlab runs the output across two client binaries (geth and revm). The divergence report feeds back into the next LLM prompt alongside a retrieval-augmented context built from the EIP corpus and prior incident summaries. A plateau detector rotates the objective when repeated batches find nothing new.

The contribution is threefold. First, a strategy-plan domain-specific language (DSL) that constrains the LLM output to a validatable JSON schema and a GBNF grammar. Second, an end-to-end pipeline implementing the fuzzillai-style loop on a single machine with a 16 GB-VRAM consumer GPU and no hosted-API dependency. Third, a direct comparison against a stock-random FuzzyVM baseline at equal CPU budget, with metrics chosen to address the null hypothesis that LLM guidance adds overhead without improving divergence discovery.

---

## 3. Related Work

FuzzyVM (van der Wijden, 2021) provides the strategy-based state-test generator that this work extends. The generator composes bytecode from a registry of Go-defined strategies, each emitting a short sequence of opcodes under an importance weight. A separate cumulative-distribution map resolves random byte inputs into strategy choices. The work reported here preserves FuzzyVM's strategy registry unchanged; only the weight map and a banned-opcode filter are overridden at runtime by a loaded plan.

Fuzzilli (Groß, 2018, Google Project Zero) is a coverage-guided mutation fuzzer for JavaScript engines. It introduced FuzzIL, an intermediate language designed to preserve semantic correctness across mutations. fuzzillai (VRIG-RITSEC, 2024) adds an agentic LLM layer to Fuzzilli, using an LLM to propose program plans and an "evolve by generating" plateau-recovery mechanism. The plateau-recovery idea, the retrieval-augmented objective selection, and the structured-plan output format are adapted from fuzzillai. Several components were deliberately not adapted: the PostgreSQL-backed distributed corpus, gdb-based crash triage (EVM differential runs produce text diffs rather than native crashes), and reliance on hosted LLM APIs. The present system runs entirely on-device.

The differential-fuzzing methodology follows the pattern surveyed in Petsios et al. (arXiv:1903.08483) and adapted to cross-language EVM comparison by goevmlab (Holiman, 2019-present). goevmlab's `runtest` tool implements the comparison loop: parse a state-test JSON, run it against each configured client binary, diff the resulting traces, and emit a consensus-flaw line on mismatch. goevmlab is used unmodified; all changes in this project sit upstream of the harness.

Retrieval-augmented generation (RAG) for domain-specific LLM tasks is well established in the broader NLP literature (Lewis et al., 2020). This project applies a minimal flat-index RAG over a corpus of 912 EIPs and a hand-written opcode reference, embedded with `BAAI/bge-small-en-v1.5` (Xiao et al., 2023) and indexed with FAISS (Johnson et al., 2019). The corpus size and embedding dimension are deliberately small so the index fits on CPU memory and rebuilds in under five seconds.

Grammar-constrained decoding via GBNF was introduced in llama.cpp (Gerganov, 2023). The project uses GBNF to enforce shape validity on LLM output, paired with a JSON Schema validator for semantic checks. This two-layer validation is closer to guidance (Microsoft, 2023) and outlines (Willard and Louf, 2023) than to free-form generation with post-hoc parsing.

---

## 4. Methodology

### 4.1 System architecture

The system has five components: a local LLM server, a retrieval index, a Python orchestrator, a patched FuzzyVM generator, and the unmodified goevmlab differential harness. Figure 1 shows the data flow per batch.

```
[ Objective ] ─┐
               │
[ FAISS RAG  ] ─┼─> [ LLM (Qwen2.5-Coder-7B)   ] ─> JSON plan
               │         grammar + schema
[ Feedback   ] ─┘
                             │
                             v
                   [ FuzzyVM --plan ] ─> state tests (.json)
                             │
                             v
                   [ goevmlab runtest ] ─> diff report
                             │
                             v
                      [ feedback loop ]
```

*Figure 1. Per-batch dataflow. Dashed lines indicate feedback from prior batches.*

### 4.2 Strategy Plan DSL

Each batch is driven by one JSON plan. The required fields are `objective` (a short free-text description of the target EIP or opcode behavior), `fork` (one of the named EVM forks, defaulting to Cancun), and `strategy_weights` (a mapping from strategy name to integer in the range one to one hundred). Optional fields include `constraints.banned_opcodes`, `constraints.required_opcodes_any_of`, `parameter_hints`, `seed_hint`, `rationale`, and `expected_signal`. Only `strategy_weights`, `fork`, and `banned_opcodes` are consumed by the current FuzzyVM plan loader; the other fields are accepted for forward compatibility and logged for analysis.

Two layers of validation apply to LLM output. The llama.cpp server is loaded with a GBNF grammar that forces the output token stream into valid JSON matching the expected shape. After decoding, a JSON Schema validator (Draft 2020-12) checks semantic constraints: strategy names must exist in the FuzzyVM registry, banned-opcode names must be real EVM opcodes, and the weight range is bounded. A plan that fails either layer aborts the batch before any FuzzyVM invocation.

### 4.3 FuzzyVM patches

The upstream FuzzyVM is modified in three places. First, a plan loader in `generator/plan.go` reads the JSON plan via `--plan path.json` or the `FUZZYVM_PLAN=path.json` environment variable. Second, a replacement weight-normalization function, `makeMapNormalized`, avoids a byte-overflow bug in the upstream `makeMap` function that manifests when plan-driven weights exceed a cumulative value of 255. Third, the `opcodeGenerator` and `validOpcodeGenerator` Execute methods consult an `IsBanned` check before emitting an opcode, substituting a no-op when a banned opcode would be chosen. Stock FuzzyVM behavior is the default when no plan is supplied; the patches touch only the plan-driven path.

A `dump` subcommand (`./FuzzyVM dump --count N --plan plan.json`) runs the generator in-process and prints per-opcode emission frequency. The orchestrator uses this to verify a plan biases generation as expected before committing to a long fuzz run.

### 4.4 Local LLM stack

The LLM is Qwen2.5-Coder-7B-Instruct at Q5_K_M quantization (approximately 5.1 GB on disk, 5.4 GB VRAM with headroom for the 8k context). It runs under llama.cpp compiled with CUDA 13.2 on an RTX 4080 (Ada Lovelace, sm_89). Full GPU offload is enabled (`--n-gpu-layers 999`). Observed decode throughput is approximately 107 tokens per second for constrained JSON output, which is sufficient for a five-to-ten-second plan generation per batch.

Sampling parameters are temperature 0.6, top-p 0.9, repeat-penalty 1.1, and DRY sampling with multiplier 0.8 and a sequence-breaker set for JSON structural tokens. Before DRY sampling was enabled, the model occasionally looped on a repeated strategy-weight key until the maximum-token budget expired. Adding DRY plus a bounded repetition on the grammar's `sw-entry` rule eliminated this failure mode.

### 4.5 Retrieval-augmented generation

The retrieval corpus combines three sources: 912 Ethereum Improvement Proposals (shallow clone of `ethereum/EIPs` at blob-limit 200 KB), a hand-written opcode reference (`opcodes.md`, 47 entries), and six divergence-incident summaries inlined in the build script. The total chunk count is 966. Embeddings are produced by `BAAI/bge-small-en-v1.5` (384 dimensions) with the library-standard instruction prefix for asymmetric retrieval. The index is FAISS flat inner-product over L2-normalized vectors, giving cosine similarity. Index rebuild takes approximately three seconds on CPU.

At query time, the orchestrator retrieves the top-k chunks for the current objective and injects them into the LLM prompt under a "Relevant reference material" section. Empirically, k=4 balances context window usage against coverage of multi-EIP topics.

### 4.6 Differential harness

goevmlab's `runtest` is invoked with the geth `evm` binary and the revm `revme` binary as the two clients. Typical invocation is:

```
runtest --geth ~/go/bin/evm --revme ~/.cargo/bin/revme \
        --parallel N --outdir <batch>/diff \
        '<batch>/out/*/FuzzyVM-*.json'
```

FuzzyVM uses a two-level output layout (`<hashprefix>/FuzzyVM-<hash>.json`) because Go's `filepath.Glob` does not support `**`. The pattern `*/FuzzyVM-*.json` matches it exactly. On a consensus flaw, `runtest` logs a `Consensus flaw` line with file, per-client result, and reference-client result, dumps per-VM JSONL traces into the output directory, and exits. A single invocation handles one flaw; exhaustive coverage of a large corpus requires re-invocation in a loop or a post-hoc pass.

The orchestrator wraps `runtest` in `orchestrator/differential.py`, which strips ANSI codes from the log, parses the divergence lines, and writes a `diff_report.json` file per batch containing `{tests_run, slow_tests, divergences[], duration_s, runtest_rc, vms}`. Tests exceeding 100 ms per client are logged as slow but not counted as divergent.

### 4.7 Plateau detection and objective rotation

The plateau detector in `orchestrator/rotate.py` scans the last K `diff_report.json` files by modification time. If every one of them contains zero divergences, the detector treats the current objective space as plateaued and asks the LLM for a new objective distinct from the recent list. The rotation prompt uses a grammar-free temperature-0.8 call to encourage exploration. The returned single-line objective replaces the user-supplied one for the next batch.

K=3 is the default. K=0 disables rotation. The pattern adapts fuzzillai's `EBG_plateau.py` to the single-machine EVM case.

### 4.8 Loop driver

The overnight run is supervised by `scripts/start_llm_loop.sh`. The driver pins a PID file under `out/`, launches a bash loop that shells out to `orchestrator/run_batch.py` per batch, waits for completion, and sleeps briefly before the next iteration. Signal handling is explicit: the driver traps SIGTERM and forwards it to the current batch's child process. An optional detached timer kills the driver after a wall-clock budget, serving as the 13h30m upper bound for the fair-comparison run.

Two robustness patches were required before the driver could run unattended. Both are described in the `Experimental Results` section as they emerged from debugging the first failed run.

### 4.9 Baseline runner

The stock-random baseline uses `scripts/start_baseline.sh`, a separate supervisor with a matching interface (PID file, start file, stop file, wall-clock timer). The baseline supervisor wipes `FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/` between supervisor restarts to avoid a Go fuzz crasher-replay trap. It also passes `-fuzzminimizetime=0` to the underlying `go test --fuzz` child to skip Go's expensive post-crash minimization phase.

---

## 5. Experimental Results

### 5.1 Baseline characterization

The stock-random FuzzyVM baseline ran for 16 hours and 36 minutes on a single workstation, producing 1,260,741 `GeneralStateTest` JSON files across a two-phase schedule: a four-thread warm-up followed by a sixteen-thread production phase. The sixteen-thread phase contributed 215.8 CPU-hours over 13 hours 30 minutes wall-clock, which defines the equal-CPU-budget target for the LLM-guided comparison. Across the full run, 339 unique crashers were preserved to `out/crashers/` with a watcher script.

Throughput metrics observed during the sixteen-thread phase: approximately 26 state-tests per CPU-second net of Go fuzz startup overhead, with approximately 37 percent of wall-clock spent in active fuzzing and the remainder in Go's baseline-coverage-replay phase after supervisor restarts. The 37 percent figure is substrate-level (go-fuzz's crasher-replay behavior on every restart) and applies identically to the LLM-guided path.

### 5.2 LLM-guided run

*[TODO: fill in once post-hoc diff pass completes. Target fields:]*

- Wall-clock duration
- Batches completed
- Plans rotated (count and distinct objectives)
- Total state-tests generated
- Tests per CPU-second
- Divergences found (count, categorized by objective)
- Slow-test count

The active run was launched on 2026-04-20 at 00:53:26 Eastern Time with a 13h30m wall-clock budget. Batch-level parameters: sixteen fuzz threads, ninety-second per-batch fuzz budget, no inline differential (differential runs as a single post-hoc pass over the accumulated corpus). The `--no-diff` mode is necessary for fair comparison against the baseline, which did not run differential during its 13h30m generation phase.

### 5.3 Two robustness issues observed in preliminary runs

Two issues surfaced during a 5-minute smoke test and a subsequent 90-second-batch trial; both required patches before the full run could proceed.

**Go-fuzz crasher-replay trap.** The first preliminary run showed each batch exiting at approximately 12 seconds of active fuzzing, against a 90-second budget. The root cause was a cached crasher in `FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/`, which go-fuzz replays during its baseline-coverage phase on every restart. Once any batch finds a crashing input and go-fuzz adds it to the seed corpus, every subsequent batch trips the same crash. The patch wipes the testdata directory before each FuzzyVM spawn, matching the approach used by the baseline supervisor. The persistent fuzz cache under `~/.cache/go-build/fuzz/` is intentionally left alone so coverage carries across batches.

**Orphaned fuzz workers on SIGTERM.** The second preliminary run produced 89,787 state-tests in a single 90-second batch. The per-batch differential pass, at approximately 100 tests per second, required approximately fifteen minutes, which pushed the LLM-guided path well below the baseline's wall-clock efficiency. Worse, when the orchestrator sent SIGTERM to the FuzzyVM wrapper at the 90-second mark, the `go test --fuzz` grandchild was reparented to /init instead of exiting, and its sixteen fuzz workers kept writing state-tests into the batch's output directory while `runtest` was diffing it. A race condition plus unbounded CPU. The patch spawns FuzzyVM with `start_new_session=True` and kills the whole process group with `os.killpg` on timeout, with a belt-and-braces SIGKILL to the group after normal exit. The second failure mode informed the decision to run the production loop in `--no-diff` mode: decoupling differential from the fuzz loop cleanly separates generation throughput from the diff bottleneck.

### 5.4 Comparison metrics

*[TODO: complete once post-hoc diff finishes on both corpora.]*

The comparison is structured across three axes:

1. **Divergences per CPU-hour.** Direct productivity metric. Baseline: [N] divergences / 215.8 CPU-hours. LLM-guided: [M] divergences / [CPU-hours].
2. **Unique opcode-sequence coverage.** Extracted via a post-hoc pass over each state-test JSON that tokenizes the bytecode and hashes n-grams (n=3, n=5). The LLM-guided path is predicted to have higher diversity in narrow EIP-keyed regions and lower diversity in broadly-convergent regions.
3. **Corpus-dedup rate.** After canonicalization (strip addresses, normalize gas fields), the fraction of unique tests per generated test. Baseline expected to have high dedup due to random overlap; LLM-guided expected to have moderate dedup, biased toward the objective's region.

Objective-to-divergence attribution requires that each divergence be traced back to the plan that produced it. Because FuzzyVM writes outputs keyed on a content hash, the attribution is exact: the divergence's filename indexes into the `plan_<id>/out/` directory, and the sibling `plan.json` records the objective at the time.

---

## 6. Security and Ethical Analysis

### 6.1 Dual-use concerns

A tool that finds consensus bugs in EVM implementations is dual-use by design. The same divergence that allows a defensive engineer to patch a client before mainnet deployment also allows an attacker to craft a chain-forking transaction. The standard responsible-disclosure pathway for Ethereum clients is the Ethereum Foundation's bounty program at `bounty.ethereum.org` and per-client programs at Immunefi. Any divergence produced by this system that affects a production client will be disclosed through those channels with an embargo of at least ninety days, consistent with the industry norm for consensus-affecting bugs.

The project uses only public EVM binaries (geth, revm) and operates offline on generated synthetic state-tests. No production traffic or private keys are involved. The fuzzer cannot be trivially repurposed to attack a live network because the state-tests it produces are self-contained and do not reference mainnet accounts.

### 6.2 Adversarial risks specific to LLM-guided fuzzing

Three attack surfaces are introduced by the LLM layer that do not exist in stock-random fuzzing.

**Prompt injection through the retrieval corpus.** The RAG index is built from public EIP text. An attacker who contributes a crafted EIP (or edits an existing one in the upstream `ethereum/EIPs` repository) could embed a hidden instruction that steers the LLM's plans away from a specific opcode or EIP they wish to keep unchecked. A defense applied here is to cap retrieval at the top-four chunks and present them with explicit role framing ("reference material, not instructions"). A stronger defense, not yet implemented, would strip any text matching known prompt-injection patterns at indexing time.

**Training-data contamination.** Qwen2.5-Coder was trained on public code and text. If its training set included biased narratives about EVM bug classes (for instance, an overrepresentation of SSTORE-refund issues and underrepresentation of precompile boundary issues), its plans will inherit that bias. The mitigation is the plateau detector, which rotates away from objectives that fail to produce divergences regardless of the model's prior. A secondary mitigation is human review of the distribution of rotated objectives, performed post-hoc.

**Feedback-loop amplification of spurious signals.** The feedback mechanism summarizes recent diff reports into the next prompt. A parse error in `orchestrator/differential.py` could inject phantom divergences, steering the model toward a false region of the search space. The parser is deliberately narrow (it matches only the literal "Consensus flaw" line emitted by `runtest`) and is unit-tested against captured logs.

### 6.3 LLM hallucination in security-critical output

The LLM occasionally produces plans referencing opcodes that do not exist on the target fork (for example, emitting `EOFCREATE` under Cancun, which does not include EIP-7692). Two guards handle this: the JSON Schema rejects unknown strategy names, and the FuzzyVM plan loader rejects banned-opcode names that do not resolve to real opcodes. Both errors abort the batch before any fuzzing begins, so a hallucinated plan wastes at most one LLM call plus the orchestrator's validation step. The conservative failure mode is preferred over silent substitution.

A harder class of hallucination is subtle: plans with valid opcodes but incorrect reasoning about why they trigger a divergence (for example, claiming that TLOAD reads persist across transaction boundaries when they do not). Such plans still generate valid bytecode, but the bytecode targets a non-existent failure mode. These plans are visible only through poor divergence yield and are rotated away by the plateau detector.

### 6.4 Energy and cost

The system runs on a single workstation with an RTX 4080 and a modern AMD CPU. Measured power draw during the full-throughput LLM-guided run is approximately 280 W at the wall for the GPU plus approximately 180 W for the CPU under sixteen-thread fuzz load. Over a 13h30m run, total energy is approximately 6.2 kWh, roughly equivalent to running an average US household's refrigerator for three days. No hosted-API inference is used; the project has zero per-call cloud cost.

For comparison, an equivalent run against GPT-4 at public API pricing (approximately one plan per ninety seconds at roughly 1500 input tokens and 300 output tokens) would cost on the order of $50-100 for a 13h30m run. The local stack is justified both on cost and on supply-chain grounds: no third party sees the generated bytecode or the objectives.

### 6.5 Accessibility and responsible release

The source code is released under the same license as upstream FuzzyVM (LGPL-3.0). The RAG corpus build script pulls only from `ethereum/EIPs`, a public repository. The local model weights (Qwen2.5-Coder-7B-Instruct) are available under the Qwen Research License. No part of the system depends on proprietary data or closed client binaries.

Release artifacts include the patched FuzzyVM, the orchestrator, the plan schema, the GBNF grammar, and reproduction scripts. The generated state-test corpora (approximately 5 GB per 13h30m run) are not included in the release; they are regenerable from the provided scripts and a re-run of the fuzz pipeline.

---

## 7. Limitations and Future Work

The single-flaw-per-invocation behavior of goevmlab's `runtest` means that a post-hoc differential over a large corpus either stops at the first divergence or requires an outer retry loop that skips previously-flagged files. The current pipeline uses the retry approach for exhaustive coverage, at a wall-clock cost proportional to the number of divergences found.

The comparison uses two clients (geth and revm). Adding a third (besu, nethermind, or erigon) would increase the probability of catching divergences where one client matches the reference and one does not. Besu and nethermind are on the list for future work; they were deferred because of Rust and JVM toolchain-version constraints that would have cost build time during the six-day schedule.

Qwen2.5-Coder-7B is a general-purpose code model without EVM-specific training. A Phase-2 preference-tuning pass (DPO or KTO) on pairs of (plan, divergence count) from this run's output would bias the model toward objectives that historically produce divergences on the deployed client pair. This is explicitly out of scope for the six-day build; the infrastructure to collect the preference pairs is in place.

The plateau detector rotates one objective at a time. More sophisticated exploration policies (Thompson sampling over a bank of objectives, or a structured crossover between successful plans) remain future work.

The comparison is a single paired run rather than a cross-validated experiment. Stochastic variance in both the random-baseline and the LLM-sampled plans means that run-to-run differences in divergence count could be noise-level. A rigorous evaluation would require at least five paired runs with different random seeds; each such run consumes 27 hours of workstation time, which exceeds the six-day project schedule.

Finally, the LLM-guided path does not yet cover EIP-7692 (EOF) semantics because Cancun is the target fork. Extending to Prague (which adds EOF) requires updating both the FuzzyVM strategy set and the grammar. This is a straightforward extension for future work.

---

## 8. References

1. Ethereum Foundation. *General State Tests*. https://github.com/ethereum/tests
2. M. van der Wijden. *Introducing FuzzyVM*. https://mariusvanderwijden.github.io/blog/2021/05/02/FuzzyVM/, 2021.
3. S. Groß. *Fuzzilli: Coverage-Guided Fuzzing for JavaScript Engines*. Saarland University, 2018.
4. VRIG-RITSEC. *fuzzillai: Agentic LLM layer over Fuzzilli*. https://github.com/VRIG-RITSEC/fuzzillai, 2024.
5. T. Petsios et al. *Differential Testing for Software*. arXiv:1903.08483, 2019.
6. M. Holiman. *goevmlab*. https://github.com/holiman/goevmlab
7. P. Lewis et al. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
8. S. Xiao et al. *C-Pack: Packaged Resources to Advance General Chinese Embedding*. arXiv:2309.07597, 2023.
9. J. Johnson, M. Douze, H. Jégou. *Billion-Scale Similarity Search with GPUs*. IEEE Transactions on Big Data, 2019.
10. G. Gerganov et al. *llama.cpp*. https://github.com/ggerganov/llama.cpp
11. Qwen Team. *Qwen2.5-Coder Technical Report*. arXiv:2409.12186, 2024.
12. B. T. Willard and R. Louf. *Efficient Guided Generation for Large Language Models*. arXiv:2307.09702, 2023.
13. Ethereum Foundation. *EIP-1153: Transient Storage Opcodes*. https://eips.ethereum.org/EIPS/eip-1153
14. Ethereum Foundation. *EIP-2929: Gas Cost Increases for State Access Opcodes*. https://eips.ethereum.org/EIPS/eip-2929
15. Ethereum Foundation. *EIP-4844: Shard Blob Transactions*. https://eips.ethereum.org/EIPS/eip-4844
16. R. Aydinyan. *Differential Fuzzing Across Languages*. https://r9295.github.io/posts/differential-fuzzing-accross-languages/
17. Ethereum Foundation Bug Bounty Program. https://bounty.ethereum.org/
