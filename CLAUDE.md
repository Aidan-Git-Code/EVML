# AIingFuzzyVM

LLM-guided differential fuzzer for Ethereum Virtual Machine implementations. The project layers an AI strategy generator on top of two existing tools (vendored as git submodules) to produce higher-value test cases for cross-client EVM consensus testing.

## Goal

Find consensus discrepancies between EVM implementations (geth, nethermind, besu, erigon, etc.) by generating GeneralStateTests whose bytecode shape is **chosen by an LLM** instead of being purely random. The LLM emits a structured *strategy plan* (a DSL); FuzzyVM consumes that plan to bias which bytecode-building strategies fire and with what weights; goevmlab runs the resulting tests against multiple clients and reports diffs.

This has nothing to do with on-chain interaction. No RPC, no addresses, no Foundry. Pure VM-level fuzzing.

## Project Rules

### Audience Profile
The indended audience for this project is a group of industry professionals, PHDs, and AI researchers from College age to mid 60s, expecting IEEE levels of professionalism.

### AI Fingerprint Removal

Reference data consolidated from Geostar's AI writing pattern research (186,000+ articles, 5+ models, 2024-2025). Source: https://www.geostar.ai/resources/ai-writing-patterns-research-data/

---

#### Claude-Specific Fingerprint

Claude is classified as "The Measured Hedger." Its sycophancy rate is 57.44%, and its readability registers at a literary level (roughly grade 11.5 Flesch-Kincaid). Claude 1.3 wrongly admitted mistakes on 98% of questions when users pushed back (regressive sycophancy rate: 18.31%).

**Claude signature patterns:**
- "You're absolutely right!" and similar sycophantic openers
- Overuse of the word "quiet" in unusual contexts
- Heavy em dash usage
- XML tag affinity (structural artifact of training/prompting)
- Preference for flowing paragraphs over lists
- Providing context/framing before answering the actual question
- "Concession + Pivot" rhetorical formula: "Yes, X. But also Y."
- "Nuanced Hedge" formula: "That's a fair point. The nuance is Y."
- Qualification/caveat endings instead of courtesy closers
- Clean endings without "I hope this helps!" or "Let me know if you need anything else"

**Words Claude actively avoids** (and therefore their absence is also a tell):
- delve
- tapestry
- landscape
- beacon

---

#### Banned Word List (All Models)

These words surged 200-900% in academic/creative writing after LLM adoption. Their presence is a strong detection signal.

**Highest-surge words:**
- "delve" — +654% (46% of all historical uses occurred in just 15 months, 2023-2025)
- "underscore" — +900%
- "meticulous" — +200%
- "tapestry" — +800%
- "pivotal" — +450%
- "intricate" — +335%

**Co-occurrence signal:** Papers containing "delve" also contain "underscore" at a 98.8% rate. These words cluster together.

**Corporate buzzwords to avoid:**
- synergy, leverage, streamline, optimize, holistic, seamless

**Empowerment verbs to avoid:**
- foster, harness, unlock, empower, catalyze

**Aspirational adjectives to avoid:**
- transformative, seamless, vibrant, revolutionary, unparalleled, groundbreaking

**Grandiosity terms to avoid:**
- paradigm (shift), revolutionary, unprecedented, game-changer

---

#### Setup Phrases to Never Use

These are instant AI tells. Delete them or rewrite around them.

- "Here's why:" / "Here's what:" / "Here's the thing:" — start with the content directly
- "What this means:" — state the implication directly
- "The reality is:" / "The truth is:" — just state it
- "Let's be honest:" — delete, just be honest
- "It's important to note that" / "It's worth noting that" — just state the fact
- "Think about it like..." — state the comparison directly

---

#### Transition Words to Avoid

- "Moreover," / "Furthermore," / "Additionally," — use "also" or just start a new sentence
- "Consequently," — use "so" or "this means"
- "That said," / "That being said," — use "but" or delete entirely
- "At the end of the day," / "The bottom line is," — delete (meaningless filler)
- "On the flip side," — use "but" or "however"
- "With that in mind," — delete

---

#### Rhetorical Formulas to Avoid

These are structural patterns detectors flag. All models share some of them, but Claude leans on the concession/hedge variants.

- **Binary Contrast:** "It's not X. It's Y."
- **Stop/Start Parallel:** "Stop chasing leads. Start building relationships."
- **Rule of Three:** "fast, efficient, and user-friendly"
- **Reframe Formula:** "That's not failure. That's data."
- **Drama Starters:** "This changes everything." / "Nobody's talking about this."
- **Concession + Pivot (Claude):** "Yes, X. But also Y."
- **Nuanced Hedge (Claude):** "That's a fair point. The nuance is Y."
- **Here's Setup (all models):** "Here's why this matters:"
- **Truth Announcement (all models):** "The truth is, customers don't care about features."
- **Escalation:** "X is good. But Y is better."

---

#### Syntactic and Punctuation Tells

**Sentence length uniformity:** AI averages 25-27 words per sentence with low variance. Human writing varies widely (5-40+ words). Fix: vary sentence length deliberately. Mix short fragments with longer compound sentences.

**Burstiness:** AI text scores below 30 on burstiness (B = (σ / μ) × 100). Human text scores above 50. Fix: alternate between short punchy sentences and longer ones. Don't let rhythm flatten out.

**Present participles:** AI uses -ing verb forms at 2-5x the human rate. Fix: prefer finite verbs.

**Nominalizations:** AI uses noun forms ("implementation," "utilization") at 1.5-2x human frequency. Fix: use the verb form ("implement," "use").

**Passive voice:** GPT-4o uses passive at half the human rate, which is itself a tell in technical writing where passive is normal. Fix: match the passive/active ratio to the genre.

**Em dashes:** GPT-4o increased em dash usage 10x over GPT-3.5. Claude also overuses them. Fix: replace with commas, periods, colons, or parentheses. Use em dashes sparingly if at all.

**Oxford comma:** AI almost never omits it (100% usage). Humans are inconsistent. Fix: occasional omission is fine if style guide permits.

**Colon-reveal pattern:** AI uses "Result: 80% fewer" style constructions heavily. Fix: write two sentences instead.

---

#### Readability Gap

All major AI models write at college level (grade 10-12 Flesch-Kincaid). Average human writing registers at grade 8. This complexity gap is a reliable detection signal.

| Model     | Grade Level |
|-----------|-------------|
| ChatGPT   | 12          |
| DeepSeek  | 11.8        |
| Claude    | 11.5        |
| Gemini    | 10.8        |
| Grok      | 9.2         |
| Human avg | 8.5         |

Fix: write at grade 8-9. Use shorter words. Prefer one-syllable verbs. Cut subordinate clauses.

---

#### Purple Prose Patterns (Creative Writing)

AI defaults to ornate, melodramatic prose because RLHF evaluators rewarded "literary" language during training. This creates a feedback loop where elaborate vocabulary gets amplified over plain writing.

**Specific tells:**
- Stacked adjectives before every noun ("the ethereal moonlight," "the tumultuous emotions")
- Metaphor clusters ("a tapestry of memories woven through the fabric of time")
- Emotional amplification ("her heart shattered into a million pieces")
- Generic metaphors: "tapestry" and "symphony" appear in ~8% of creative outputs
- Generic character names: Emily, Sarah, James, Michael (60-70% frequency)

**Fix:** Replace adjective clusters with a single concrete detail. Cut metaphors by 80%. Use one-syllable verbs. Delete emotional amplifiers. Name specific emotions instead of using metaphorical stand-ins.

---

#### Register Leveling

All AI models converge fiction, blog posts, emails, and technical writing toward the same dense, formal, noun-heavy academic prose. This is called register leveling. A blog post and a research abstract should not sound the same, but AI makes them sound identical.

Fix: match register to genre. Blog posts should be conversational. Emails should be brief. Technical docs should be precise but not ornate. Fiction should vary by voice and character.

---

#### RLHF Root Cause Summary

All of these patterns trace back to Reinforcement Learning from Human Feedback (RLHF):
- Fancy vocabulary preference: evaluators rewarded elaborate words, system amplified them
- Formal register everywhere: mid-formal tone got positive feedback regardless of genre
- Structured output bias: lists, bullets, predictable organization got rewarded
- Hedging and qualification: uncertainty got penalized less than being wrong
- Sycophancy: user satisfaction optimization led to agreement regardless of correctness
- 28 of 32 overrepresented AI words appear only after instruction tuning, not in base models (COLING 2025)

---

#### Quick Reference: What to Do

1. Never use words from the banned list. Replace with plain equivalents.
2. Vary sentence length. Mix 4-word sentences with 30-word ones.
3. Delete all setup phrases ("Here's why:", "It's worth noting").
4. Delete filler transitions ("Moreover", "Furthermore", "That said").
5. Avoid rhetorical formulas, especially concession+pivot and binary contrast.
6. Write at grade 8-9 reading level. Shorter words, fewer clauses.
7. Use em dashes rarely or not at all.
8. Match register to genre. Don't write a blog post like a research paper.
9. Prefer verbs over nominalizations ("use" not "utilization").
10. In creative writing: cut adjective stacks, kill generic metaphors, name emotions directly.

### Voice DNA

This section defines my writing voice. Use it to match my tone, structure, and word choice when writing on my behalf or assisting with any written output.

---

#### Two Registers

I write in two distinct registers depending on context. Do not blend them.

**Casual register** (Discord, READMEs, personal docs, messages to peers):
- First person ("I found," "I tested," "I set up")
- Contractions are fine
- Swearing is fine when it fits
- Humor ranges from dry/deadpan to sarcastic to absurdist depending on mood
- Sentence fragments are fine
- Tone is direct and conversational

**Formal register** (lab reports, research papers, presentations, professional docs):
- Impersonal or third person ("the scan revealed," "results indicate," "the system was configured")
- No first person unless unavoidable
- No contractions
- No humor
- Tighter claims, more careful language
- Still sounds like flat direct prose, not like a textbook or an AI

Both registers share the same core voice described below. The formal register is not a different person, just a different mode.

---

#### Sentence Structure

Mixed length. I alternate between short blunt sentences and longer compound ones. A 5-word sentence followed by a 35-word sentence is normal for me. Do not flatten this into uniform 20-25 word sentences. Rhythm matters.

Do not pad sentences to fill space. If the thought is short, the sentence is short.

---

#### Vocabulary

I use precise and sometimes uncommon words when they are the correct word for the concept. I do not use fancy words for decoration. If "exfiltrate" is the right word, use it. If "send" is the right word, use that instead. Technical jargon is fine when writing for a technical audience. Plain language everywhere else.

Never use words from the AI Fingerprint Removal banned list. Never use corporate buzzwords, empowerment verbs, or aspirational adjectives.

---

#### Explaining Things

When I explain something, I do not dump the full answer immediately. My default pattern:
1. Give a few sentences of context so the reader knows where we are
2. Gauge what the audience already knows (or assume a reasonable baseline for the format)
3. Explain the gaps, not the whole thing from scratch

Do not over-explain. Do not repeat concepts the audience already understands. Do not provide unsolicited background unless the reader would be lost without it.

---

#### Uncertainty

I do not bluff. If I do not know something well enough to write about it confidently, I either research it first or explicitly flag that my knowledge is limited. I do not hedge with soft language like "perhaps" or "it could be argued" — I either know it or I say I don't.

Do not write vague hedged statements on my behalf. If the information is uncertain, say so plainly: "I'm not sure about X" or "my knowledge here is limited."

---

#### Disagreement

My tone when disagreeing depends on the person and the context. With people I respect, I explain my reasoning before stating my position. With people I don't, I'm blunt. Do not soften disagreement into diplomatic mush. Do not add "I see your point, but..." or "That's a great question, however..." — those are AI patterns.

---

#### Formatting Preferences

For personal docs, READMEs, and notes:
- Headers to organize sections
- Bullet points and tables when they earn their place
- Minimal use of bold and italics — structure comes from headers and layout, not inline emphasis
- Code blocks for code, commands, and paths

For academic/professional writing:
- Prose paragraphs, not bullet lists
- Formatting follows the assignment or publication requirements
- Still no decorative bold/italics

---

#### Things to Never Do

- No em dashes. Use commas, periods, colons, or parentheses instead.
- No filler transitions ("Moreover," "Furthermore," "That said," "Additionally")
- No setup phrases ("Here's why:", "It's worth noting that", "Let's be honest:")
- No sycophantic openers ("Great question!", "You're absolutely right!")
- No AI rhetorical formulas (binary contrast, concession+pivot, rule of three)
- No emotional amplification or purple prose
- No "I hope this helps" or "Let me know if you need anything else"
- No metaphors used as filler ("tapestry," "symphony," "landscape," "beacon")
- No nominalizations when the verb works ("use" not "utilization," "implement" not "implementation")
- No generic softening ("arguably," "it could be said," "one might suggest")
- Do not begin responses with "I" unless it is the natural start of the sentence
- Do not begin paragraphs the same way twice in a row

---

#### What My Writing Sounds Like

Flat. Direct. Technical when the subject demands it, casual when it doesn't. I say what I mean without decoration. I'd rather be clear than impressive. My humor shows up unexpectedly and without signposting. I do not explain my jokes. I do not soften my opinions to make them palatable. I write like someone who knows what they're talking about and doesn't need to prove it with vocabulary.

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

- `FuzzyVM/`: fork of [MariusVanDerWijden/FuzzyVM](https://github.com/MariusVanDerWijden/FuzzyVM). Generates state tests. The seed bytes drive a `Filler` that picks among `Strategy` implementations (basic ops, call/create variants, jumps, precompiles). Each strategy has an `Importance()` weight (1-100) that sets how often it fires. Entry points: `fuzzer/fuzzer.go`, `generator/generator.go`, `generator/strategy.go`. Output goes to `$FUZZYDIR/<hashprefix>/FuzzyVM-<hash>.json`.
- `goevmlab/`: [holiman/goevmlab](https://github.com/holiman/goevmlab). Runs generated tests across multiple EVM binaries and surfaces disagreements. Used unmodified as the execution harness.

### Strategy surface (what the LLM is steering)

Defined under `FuzzyVM/generator/`:
- `basic_strategies.go`: opcode emit, MSTORE/SSTORE/TSTORE, MLOAD/SLOAD/TLOAD, RETURN, KECCAK+SSTORE, BLOBHASH, etc.
- `call_strategies.go`: CREATE/CREATE2 + CALL/CALLCODE/DELEGATECALL/STATICCALL, precompile calls.
- `jump_strategies.go`: JUMP/JUMPI patterns + jumptable patching.

`Importance()` is currently hardcoded. The LLM-guided path overrides these per fuzzing batch and may also inject new composite strategies, seed hints, or fork constraints.

## Approach (per `WhiteishPaper.md`)

**Phase 1: RAG + prompt templates** (best ROI, start here):
1. Build a retrieval index over: ethereum/tests, EIPs/opcode docs, historical client-diff incidents, prior `out/` finds and minimized repros, goevmlab differential results.
2. Prompt a hosted/local model (Qwen is the working pick) with: target fork + recent coverage gaps + recent divergences + objective.
3. Force output through a strict **strategy plan JSON schema** (steps, weights, constraints, seed hints). No raw bytecode, no test JSON.
4. Validate, feed into FuzzyVM, run via goevmlab, log outcomes to grow the dataset.

**Phase 2: light fine-tuning / preference tuning** only if Phase 1 plateaus. Reward: new coverage + cross-client disagreement. Penalize: invalid/unproductive plans.

## Current status (as of 2026-04-20)

Day 1 through Day 5 step 2 are complete. Preference tuning (Phase 2) is out of scope for the 6-day build. Baseline ran 16h36m (1.26M state-tests, 339 crashers preserved, see `baseline_writeup.md`). The LLM-guided pipeline runs end-to-end and has a supervised overnight loop driver. A 13h30m equal-CPU-budget LLM-guided fuzz run is active on the 16-thread baseline comparison target. Post-hoc differential pass planned over the final corpus.

**Day 1 (baseline + plumbing):**
- **Plan loader** in `FuzzyVM/generator/plan.go`: reads a JSON plan via `--plan path.json` or the `FUZZYVM_PLAN=path.json` env var. Overrides strategy weights, fork, and banned opcodes. Stock behavior is the default when no plan is present.
- **`makeMapNormalized`** in the same file. Bypasses a byte-overflow bug in upstream `generator/strategy.go:52 makeMap` that only manifests under plan-driven heavy weights. Stock path stays untouched.
- **`--out-dir`** flag on `FuzzyVM run` propagates to `FUZZYDIR`. Baseline writes to `out/baseline/`, LLM-guided runs write to `out/llm_guided/<plan_id>/`.
- **`dump` subcommand** (`./FuzzyVM dump --count 50 [--plan plan.json]`) runs the generator in-process and prints per-opcode emission frequency. The orchestrator uses it to verify bias.
- **Supervised baseline runner** at `scripts/start_baseline.sh`. Crasher watcher at `scripts/crasher_watcher.sh`.
- **Smoke plan** at `orchestrator/plans/smoke_storage_heavy.json`.

**Day 2 (LLM + orchestrator pipeline):**
- **llama.cpp** built with CUDA at `~/tools/llama.cpp/build/bin/llama-server` (CUDA 13.2, RTX 4080, Ada sm_89).
- **Model** at `~/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf` (~5.1 GB). Loaded with full GPU offload. Decode runs at ~107 tok/s.
- **Server launcher** at `scripts/start_llama_server.sh`. Idempotent, waits for `/health`, writes pid+log to `out/`.
- **`orchestrator/plan_schema.json`**: JSON Schema (Draft 2020-12) for the Strategy Plan DSL. Covers semantic validation.
- **`orchestrator/plan.gbnf`**: GBNF grammar for llama.cpp grammar-constrained decoding. Shape validation. Each rule is single-line or paren-grouped, because llama.cpp's GBNF parser breaks rules at bare newlines, so multiline rules must wrap in `(...)`.
- **`orchestrator/rag_stub.py`**: hardcoded-snippet retriever (8 EIP / opcode / incident entries, word-overlap scoring). Placeholder. FAISS + bge-small replaced it on Day 3.
- **`orchestrator/run_batch.py`**: objective → LLM (`/completion` with `grammar` field; `/v1/chat/completions` silently drops grammar, so the native endpoint is mandatory) → `json.loads` → `jsonschema` validate → plan file → `./FuzzyVM run --plan`. Supports `--dry-run`, `--verify-bias`, `--duration`.
- **LLM sampling**: temperature 0.6, top_p 0.9, dry_multiplier 0.8, repeat_penalty 1.1. Before dry-sampling, the model looped on repeat keys until max_tokens. Dry-sampling plus `sw-entry` bounded to 20 in grammar fixed it.

**Day 3 (real RAG):**
- **Embedder**: `BAAI/bge-small-en-v1.5` (384-dim, ~25 MiB, runs on CPU). Cached under `~/models/sentence-transformers/`.
- **Corpus** at `orchestrator/rag/corpus/`: 912 EIPs (shallow clone of `ethereum/EIPs`, gitignored), `opcodes.md` (47 hand-written opcode entries, committed). Six historical-divergence "incident" entries and a baseline-run summary are inlined in `build_index.py`.
- **Index**: `orchestrator/rag/index/vectors.faiss` (FAISS flat IP, cosine via normalized embeddings) plus `chunks.jsonl` sidecar. 966 chunks, 1.4 MiB. Gitignored. Regenerable from `python3 orchestrator/rag/build_index.py` (~3 sec on CPU).
- **Retriever** at `orchestrator/rag_faiss.py`: lazy-loads the index, queries with bge's instruction-prefix convention. Drop-in for `rag_stub`. `run_batch.py` imports `rag_faiss` first and falls back to `rag_stub` if the index is missing.
- **Plan loader correctness**: removed `validOpcodeGenerator` from schema, grammar, and prompt. The type exists in `basic_strategies.go` but never registers in `basicStrategies`, so the Go loader rejected it.
- **Required field**: `strategy_weights` is now required in both schema and grammar. Previously optional, and the LLM exploited that by emitting plans with no bias.
- **Few-shot example** added to system prompt. Keeps the model emitting 5-12 strategies with rationale and bans instead of a one-strategy stub.

End-to-end on the EIP-2929 / SLOAD objective produced a plan with sloadGenerator=80 plus nested-call strategies and BLOCKHASH/SELFDESTRUCT bans. `dump` confirms SLOAD: 2093 over 200 programs (vs ~10 for stock random) and zero BLOCKHASH/SELFDESTRUCT.

**Day 4 (differential harness + feedback loop):**
- **geth `evm`** installed via `GOBIN=~/go/bin go install github.com/ethereum/go-ethereum/cmd/evm@v1.15.11`.
- **revm `revme`** installed via `cargo install revme`. Needed a modern Rust toolchain. Debian ships 1.75 but revme 15.0.0 requires 1.91+, so `rustup` stable (1.95) lives at `~/.cargo/bin/`.
- **goevmlab `runtest`** built in-tree (`goevmlab/runtest`). Invoked with `--geth ~/go/bin/evm --revme ~/.cargo/bin/revme --parallel N --outdir <dir> '<pattern>'`. Note: Go's `filepath.Glob` does NOT support `**`. FuzzyVM's 2-level output layout is matched with `*/FuzzyVM-*.json`. On consensus flaw, runtest logs `Consensus flaw file=… vm=… have=… ref vm=… want=…`, dumps per-VM `.jsonl` traces into `--outdir`, then aborts. Single-flaw-per-invocation works for small batches but requires re-invocation for exhaustive coverage of a corpus.
- **Orchestrator diff module** at `orchestrator/differential.py`: wraps runtest, parses its (ANSI-stripped) log, writes `<batch>/diff/diff_report.json` with `{tests_run, slow_tests, divergences[], duration_s, runtest_rc, vms}`. Standalone CLI: `python3 orchestrator/differential.py <batch_out_dir>`.
- **Feedback loop in `run_batch.py`**: `--diff` runs differential after the FuzzyVM batch. `--feedback-n N` (default 3) reads the most recent N `plan_*/diff/diff_report.json` under `--out-root` and injects a "Recent findings" block (one line per batch: objective + divergence count + tests run) into the next LLM prompt.
- **Smoke verified**: 3881 baseline state-tests across geth + revme at ~100 tests/s. Zero divergences, as expected when baseline bytecode is broadly convergent. Slow-test warnings (>100ms per test) counted as benign.

**Day 5 step 1 (plateau rotation):**
- **`orchestrator/rotate.py`**: `detect_plateau(out_root, k)` scans the last K `plan_*/diff/diff_report.json` by mtime and returns the objectives if every one has zero divergences, else `[]`. `propose_objective(llm_url, plateaued, fork)` is a grammar-free LLM call (temp 0.8) that returns one new short objective distinct from the plateaued list. Standalone CLI prints the resolved objective to stdout and status to stderr. Composable for the Day-5-step-2 loop driver.
- **`run_batch.py --rotate-if-plateau K`**: when set, calls `rotate.resolve()` before the RAG+LLM pipeline. If a plateau is detected, the user-supplied `--objective` is swapped for the LLM's proposal. Logged as `plateau on last K batch(es); rotated objective → ...`. K=0 disables.
- **Verified**: with one zero-div batch on disk, `--rotate-if-plateau 1` fires and rotates EIP-1153 TSTORE into EIP-2929 warm/cold accounting (distinct angle). `--rotate-if-plateau 2` correctly declines because only one diff report exists yet.

**Day 5 step 2 (loop driver + long run):**
- **`scripts/start_llm_loop.sh`**: supervised loop driver for overnight LLM-guided runs. Mirrors `start_baseline.sh` conventions: pid/start/stop/log files under `out/`, `nohup + disown`, trap forwards SIGTERM to the child, optional detached wall-clock timer. Idempotent: no-ops if a previous loop is alive. Log rotates to `.log.prev` on each session start. Flags: `--objective` (required), `--fork`, `--llm-url`, `--threads`, `--diff-threads`, `--feedback-n`, `--rotate-if-plateau`, `--batch-duration`, `--duration`, `--out-root`, `--no-diff`.
- **`--no-diff`**: skips per-batch differential. Required for fair comparison with the baseline methodology, which generated tests without diffing during the 13.5h run. The LLM plan pipeline and FuzzyVM batch still run; rotation + feedback no-op since neither can read diff reports. Differential runs as a single post-hoc pass.
- **run_batch.py hardening**:
  - Wipes `FuzzyVM/fuzzer/testdata/fuzz/FuzzVMBasic/` before each FuzzyVM spawn. Go-fuzz retains every crasher under that directory and replays it on the next baseline-coverage phase. Without the wipe, one early crasher causes every subsequent batch to abort at ~12s of fuzzing. Same mechanism `scripts/start_baseline.sh` uses between supervisor restarts. The persistent `~/.cache/go-build/fuzz/.../FuzzVMBasic/` cache is deliberately left alone so coverage carries across batches.
  - Spawns FuzzyVM with `start_new_session=True` and kills the whole process group with `os.killpg` on timeout. Without this, SIGTERM to the FuzzyVM wrapper leaves its `go test --fuzz` grandchild (and 16 fuzz workers) orphaned under /init, where it kept writing state-tests into the batch's `out/` directory while `runtest` was diffing it. Race condition + runaway CPU. The pgroup kill also runs belt-and-braces after normal exit, in case any straggler remained.
- **Observed batch shape (no-diff mode)**: baseline-coverage replay ~25-30s on 16 threads, then ~60s of active fuzzing at ~1500 execs/sec per worker. One batch yields ~90k state-tests. LLM plan generation and grammar-constrained decode add ~3-5s of overhead between batches. Inter-batch sleep is 2s.
- **Active run (launched 2026-04-20T00:53:26)**: `--objective "EIP-1153 TSTORE visibility across nested DELEGATECALL" --duration 13h30m --threads 16 --batch-duration 90s --no-diff`. Runs until 2026-04-20T14:23:29. Output under `out/llm_guided/plan_*/out/`.

Post-run plan: single `orchestrator/differential.py` pass over the entire `out/llm_guided/` tree, using a higher `--diff-threads` budget than the per-batch config (CPU is free after fuzzing stops). Metrics: divergences per CPU-hour, plan-attribution per divergence, unique-opcode-sequence novelty vs baseline.

Out of scope for the 6-day build: preference tuning (Phase 2). See `WhiteishPaper.md`.

## Baseline runner

`scripts/start_baseline.sh` launches FuzzyVM under a supervisor loop. The supervisor auto-restarts on crash and wipes `testdata/fuzz/FuzzVMBasic/` before each relaunch to dodge go-fuzz's crasher-replay trap. Flags: `--threads N`, `--out-dir PATH`, `--duration <N>{s,m,h,d}`. Idempotent: it no-ops if the supervisor is already alive.

State files (all under `out/`, one per session):
- `baseline.pid`: supervisor PID. Kill this to stop everything; the trap forwards SIGTERM to the FuzzyVM child.
- `baseline.start`: ISO-8601 launch time.
- `baseline.stop`: scheduled-stop time (present only if `--duration` was used).
- `baseline.log`: combined stderr/stdout of supervisor, FuzzyVM, and child `go test --fuzz`.
- `baseline.watcher.pid`, `baseline.watcher.log`: crasher watcher, if running.

Important operational facts:
- `go test --fuzz` hits native cgo faults in geth's EVM every 2-4 min under current generation. The supervisor handles this. About 37% of wall-clock is actual fuzzing; the rest is Go's baseline-coverage replay on each restart. This is substrate-level and affects the LLM-guided path identically, so baseline-vs-LLM fairness is preserved.
- `FuzzyVM/cmd/fuzzyvm/main.go` passes `-fuzzminimizetime=0` to the child `go test --fuzz` to skip Go's (60s, often-hanging) post-crash minimization phase. Unminimized crashers are fine because goevmlab reruns the full saved state test.
- The upstream FuzzyVM seed corpus (`FuzzyVM/corpus/`) contains at least one input that segfaults geth's EVM on startup. Leave it parked as `corpus_disabled/`. Do not restore it.
- Go persistently caches "new interesting" inputs at `~/.cache/go-build/fuzz/.../FuzzVMBasic/` across restarts. Coverage is retained across crashes. Don't wipe this cache without a reason.

## Working with the submodules

- Both submodules are Go projects (`go.mod` at their root). Changes to FuzzyVM (strategy weights, new strategies, external plan ingestion) happen in-tree under `FuzzyVM/`.
- Treat `goevmlab/` as a black box unless something breaks at the harness boundary.
- Build: `cd FuzzyVM && go build -o FuzzyVM ./cmd/fuzzyvm`.
- Run (oneshot, no supervisor): `./FuzzyVM run [--threads N] [--out-dir PATH] [--plan plan.json]`. Output dir defaults to `./out` and can also be set via `$FUZZYDIR`.
- Corpus generation: `./FuzzyVM corpus --count N [--plan plan.json]`.
- Plan tuning diagnostic: `./FuzzyVM dump --count 50 [--plan plan.json]`. Prints an opcode-frequency table.

## Methodology baseline: fuzzillai

Reference implementation to adapt from: [VRIG-RITSEC/fuzzillai](https://github.com/VRIG-RITSEC/fuzzillai). A fork of Google Project Zero's Fuzzilli (JS-engine fuzzer) with an agentic LLM layer. Their `Sources/Agentic_System/` is the blueprint.

Adapted from fuzzillai:
- Three-stage pipeline: *objective/section selection → context analysis → structured program-plan emission*.
- RAG over historical regression tests and traces. They index ~8000 regressions; this project indexes EIPs, opcode docs, ethereum/tests metadata, and our own `out/` finds.
- "Evolve by generating" on plateaus: when divergence or coverage rate stalls, re-prompt with a shifted objective (their `EBG_plateau.py`). Cheap, high-ROI.
- Attribution: keep LLM-generated seeds in a **separate queue/folder** so their contribution can be measured against baseline random fuzzing.
- Preflight validation of tool paths and model availability before any agent reasoning starts.

Skipped from fuzzillai:
- PostgreSQL + distributed fuzzing layer (this project is single-machine, 6 days).
- gdb-based crash triage. EVM differential diffs come out of goevmlab as text, not native crashes.
- V8-code-navigation agents. This project does not map EVM client internals; it targets EVM semantics.
- Hosted LLM APIs. Everything runs **local** on an RTX 4080 (16 GB VRAM).

## Local model stack

- **Server:** `llama.cpp` (llama-server) or Ollama. Both work. llama.cpp gives tighter grammar-constrained decoding via GBNF, which matters for schema-valid JSON output.
- **Model (primary candidate):** `Qwen2.5-Coder-7B-Instruct` at Q5_K_M (~5.4 GB VRAM, leaves headroom for embeddings and context). Strong at structured JSON and code reasoning.
- **Fallbacks:** `Qwen2.5-7B-Instruct` (non-coder) or `Llama-3.1-8B-Instruct` if Coder-7B hallucinates opcodes. Consider `Qwen2.5-Coder-14B-Instruct` Q4_K_M (~8.5 GB) only if 7B is the bottleneck.
- **Embeddings:** `bge-small-en-v1.5` or `all-MiniLM-L6-v2` via `sentence-transformers`. Tiny, runs on CPU fine.
- **Vector store:** FAISS flat index. No serving complexity.
- **Orchestrator:** Python. `jsonschema` for plan validation, `requests` for the local LLM HTTP API, `subprocess` to drive FuzzyVM and goevmlab.

## Strategy Plan DSL (v0, implemented)

The LLM emits one JSON object per fuzzing batch. FuzzyVM reads it via `FuzzyVM/generator/plan.go:LoadPlanFile` and applies the settings before the generator's `init()` finishes building the strategy map. All fields are optional; omitted fields use defaults (including the stock FuzzyVM weights). Only `strategy_weights`, `fork`, and `constraints.banned_opcodes` are wired into generation today. The other fields are accepted by the loader but not yet consumed.

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
  "rationale": "Short free-text 'why this plan'. One paragraph. Logged for later analysis of what prompts the LLM to produce productive plans.",
  "expected_signal": ["state_root_divergence", "gas_divergence"]
}
```

Weight semantics: numbers on a 1-100 scale (same as `Strategy.Importance()`). Plan-loaded weights go through `makeMapNormalized` in `plan.go`, which divides each by the total and spreads across 256 buckets. This sidesteps a byte-overflow bug in upstream `makeMap` that chaotically stomps buckets when cumulative weight exceeds 255. Omitting a strategy falls back to the default importance. Use `./FuzzyVM dump --plan plan.json` to verify a plan biases generation the way you expect before kicking off a run.

**Implementation:** `generator/plan.go` holds the `Plan` struct, `LoadPlanFile`, `ApplyPlan`, `makeMapNormalized`, and `IsBanned`. `generator/basic_strategies.go` consults `IsBanned` inside `opcodeGenerator.Execute` and `validOpcodeGenerator.Execute` to skip or substitute banned opcodes. `cmd/fuzzyvm/main.go` accepts `--plan` on `corpus`, `run`, and `dump` subcommands and propagates it to the child `go test --fuzz` process via `FUZZYVM_PLAN=<path>`.

**Validation contract:** the plan loader rejects (a) unknown strategy names (error includes the full known-strategy list), and (b) banned opcodes that don't name real EVM opcodes. On rejection the loader returns an error; when reached from the CLI this aborts the run before subprocess launch. The LLM-side JSON-schema validator in the orchestrator is not yet built.

## 6-day build & fuzz plan (deadline 2026-04-23)

**Day 1, baseline + plumbing. ✅ done.** Plan loader, normalized weight buckets, `--out-dir`/`--plan`/`dump` CLI, supervised baseline runner with `--duration`, crasher preservation watcher, and stock-random 16h baseline run launched.

**Day 2, local LLM up.** llama.cpp serving Qwen2.5-Coder-7B Q5_K_M with a GBNF grammar for the DSL. Python orchestrator: prompt → LLM → JSON schema validator → plan file → FuzzyVM batch. Prove end-to-end with a trivial RAG stub.

**Day 3, real RAG.** FAISS index over (a) EIPs markdown, (b) opcode reference, (c) ethereum/tests GeneralStateTests metadata (opcode frequencies + folder-name objectives), (d) any prior `out/` finds. Start feedback: parse goevmlab diffs into a recent-divergences summary fed into the next prompt.

**Day 4, differential harness.** Wire goevmlab against 2-3 client binaries (geth + revm minimum; add besu if time allows). Run the first full loop: LLM → plan → FuzzyVM batch → goevmlab → diffs → LLM. Log coverage and divergence counts per batch.

**Day 5, plateau rotation + long run. ✅ done.** Plateau detection in `orchestrator/rotate.py`. Supervised loop driver at `scripts/start_llm_loop.sh` with a `--no-diff` mode for fair-comparison runs. The 13h30m equal-CPU-budget run is active and produces post-hoc-diffable state-test corpora.

**Day 6, compare & write up.** Metrics: unique divergences per CPU-hour, unique opcode sequences, corpus-dedup rate, objective→divergence attribution. Stock-random baseline vs. LLM-guided on equal CPU budget.

## Repo layout

```
.
├── CLAUDE.md                  this file
├── README.md
├── WhiteishPaper.md           project plan / rationale (read first for methodology)
├── FuzzyVM/                   submodule: generator (patched in-tree)
│   ├── cmd/fuzzyvm/           CLI: run, corpus, dump, bench, minCorpus
│   ├── generator/plan.go      plan loader + makeMapNormalized (ours)
│   └── fuzzer/fuzzer.go       go-fuzz entry point (FuzzVMBasic)
├── goevmlab/                  submodule: differential harness (unmodified)
├── orchestrator/
│   ├── plan_schema.json       JSON Schema for the DSL (semantic validation)
│   ├── plan.gbnf              GBNF grammar for llama.cpp (shape validation)
│   ├── rag_stub.py            Day-2 fallback retriever (used if index absent)
│   ├── rag_faiss.py           Day-3 FAISS retriever (preferred)
│   ├── differential.py        Day-4 goevmlab runtest wrapper + diff report
│   ├── rotate.py              Day-5 plateau detector + LLM objective rotator
│   ├── run_batch.py           objective → LLM → validate → FuzzyVM → diff
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
│   ├── start_llm_loop.sh      Day-5 LLM-guided loop driver (overnight)
│   ├── start_llama_server.sh  idempotent llama-server launcher
│   └── crasher_watcher.sh     preserves testdata crashers to out/crashers/
└── out/
    ├── baseline/              stock FuzzyVM random run (gitignored)
    ├── llm_guided/<plan_id>/  per-plan LLM-guided batches (gitignored)
    ├── crashers/              preserved go-fuzz crashers (+ manifest.tsv)
    ├── baseline.{pid,start,stop,log}          supervisor session state
    ├── baseline.watcher.{pid,log}             crasher-watcher session state
    ├── llm_loop.{pid,start,stop,log,log.prev} loop-driver session state
    └── llama_server.{pid,log}                 llama-server session state
```

External (outside repo, not version-controlled):
- `~/tools/llama.cpp/`: CUDA-built llama.cpp
- `~/models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf`: local model (~5.1 GB)
- `~/models/sentence-transformers/`: bge-small-en-v1.5 cache (~25 MiB)
- `~/go/bin/evm`: geth's `evm` (Day 4 differential client)
- `~/.cargo/bin/revme`: revm's `revme` (Day 4 differential client)

To rebuild the RAG index from a fresh checkout:
```
cd orchestrator/rag/corpus
git clone --depth 1 --filter=blob:limit=200k https://github.com/ethereum/EIPs.git
cd ../.. && python3 rag/build_index.py
```

**To build in the future:** `orchestrator/plan_schema.json`, `orchestrator/plan.gbnf`, `orchestrator/rag/`, `orchestrator/prompts/`, `out/llm_guided/<plan_id>/`.

## Useful references (from WhiteishPaper.md)

- Marius van der Wijden's FuzzyVM blog: https://mariusvanderwijden.github.io/blog/2021/05/02/FuzzyVM/
- Foundational paper: https://arxiv.org/pdf/1903.08483. This project follows that pipeline but swaps random strategy selection for an LLM.
- Differential fuzzing across languages: https://r9295.github.io/posts/differential-fuzzing-accross-languages/
- Candidate training/RAG data: ethereum/tests, andstor/smart_contracts (HF), evm-bench.
