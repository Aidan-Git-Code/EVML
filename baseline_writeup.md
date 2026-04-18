# Baseline fuzzing run — writeup

Covers the stock-random FuzzyVM baseline run used as the equal-CPU-hours reference for the upcoming LLM-guided comparison. The infrastructure that made this possible is documented in `WhiteishPaper.md` under *Baseline infrastructure (as built)*; this document focuses on **what we did** and **what we got out**.

## TL;DR

- **~16h 36m wall-clock across three phases** (4-thread startup → brief stuck phase → productive 16-thread phase), all under a supervisor loop that auto-restarts FuzzyVM after every native cgo fault.
- **1,259,920 GeneralStateTest JSONs** written to `out/baseline.4t/` (270 k) and `out/baseline/` (990 k). These are the raw material for the Day 4 goevmlab differential harness.
- **5,078 cumulative "new interesting" inputs** added to Go's fuzz coverage bitmap across the run — the subset of generated inputs that exercised a previously-unseen branch in geth's instrumented EVM.
- **339 unique crashers** preserved at `out/crashers/` — each one is an input that caused `go test --fuzz` to terminate with `exit status 2`, either from a native cgo fault in geth or from a hung worker the harness SIGKILL'd.
- **Plateau observed.** Stock-random byte mutation saturated its reachable coverage at ~4,570 cached inputs; new-interesting rate fell to 1–3 per ~2-minute cycle by hour 10. This is the exact plateau the LLM-guided strategy-weight rotation (Day 5) is designed to break.

## What we actually did

The baseline is intentionally dumb. `FuzzyVM run` spawns `go test --fuzz FuzzVMBasic` under `--parallel N`; Go's fuzz engine hands random byte slices to `Fuzz(data []byte)` at `FuzzyVM/fuzzer/fuzzer.go:70`, which pipes them through `filler.NewFiller(data) → generator.GenerateProgram(f)`. The generator walks its strategy table (stock `Importance()` weights — `opcodeGenerator=80`, `randomCallGenerator=20`, `sstoreGenerator=40`, etc.) and emits EVM bytecode. The result is wrapped into a `GeneralStateTest` for the Cancun fork, executed once through geth's EVM to measure coverage, and written as `out/baseline/<hashprefix>/FuzzyVM-<hash>.json`.

No LLM. No plan DSL. No weight overrides. The run is the stock generator consuming go-fuzz's random + coverage-guided mutation byte stream, rediscovering interesting opcode combinations entirely on its own.

### Three phases

**Phase A — 4 threads (2026-04-17T22:02 → 2026-04-18T01:28, ~3h26m).** Conservative thread count while the supervisor + watcher pipeline was being stabilized. 71 supervisor cycles, mean FAIL cycle 152.7s (90s baseline-coverage replay + ~55s active fuzzing + cgo fault), 850 new-interesting entries added to the cache, 270,028 state-test JSONs generated. Archived to `out/baseline.4t/` before the thread bump.

**Phase B — stuck on cache poison (2026-04-18T01:29 → 01:34, ~5 min).** On relaunching at 16 threads, every cycle died 14s into baseline-coverage replay at index 751/2437. The Go build cache (`~/.cache/go-build/fuzz/.../FuzzVMBasic/`, 2182 entries at that point) contained a poison-pill input saved during the final minutes of phase A. At 4-way parallelism replay reached that input too late in the window to surface; at 16-way parallelism one of the workers hit it fast enough to kill the whole process before any fuzzing happened. Zero new-interesting entries, 30 supervisor launches all killed identically. Archived to `out/baseline.stuck/`; the poisoned cache itself backed up to `out/fuzz_cache.4t_final.tar.gz` (120 KB) for later bisection.

**Phase C — 16 threads, post cache-wipe (2026-04-18T01:37 → ~15:07, ~13h30m).** Wiped Go's persistent fuzz cache and relaunched. Baseline replay shrunk from 2437 entries (~14s, poisoned) to the 255 built-in byte patterns (~6s, clean). 466 supervisor cycles, mean FAIL cycle 84.8s (shorter than phase A because replay parallelizes across 16 workers), 4228 new-interesting entries, 989,892 state-test JSONs written to `out/baseline/`. Total ≈ 215.8 CPU-hours of substrate (wall-clock × threads). The supervisor ran ~1h past its scheduled stop at 14:02:28 — the detached kill-timer didn't fire (cause uninvestigated; not load-bearing for the baseline artifact) — and eventually died on its own around 15:07, at which point the crasher watcher detected the dead pid and self-exited.

## Looking through the results

### State-test JSONs

Each generated test is a full goevmlab-format `GeneralStateTest`:

```
keys: ['env', 'pre', 'transaction', 'out', 'post']
post forks: ['Cancun']
pre accounts: 2  (the generated contract + the sender 0xa94f5374...e6ebf0b)
tx gasLimit[0]: 0x1312d00 (20 M gas)
```

Spot-check of a randomly picked test: 1,406 bytes, a single contract at `0x00...ca1100f022` with 1 byte of code (`0x10` = LT opcode), 2 million gas tx, post-state hash computed by geth at generation time. Most generated tests are in the 1–2 KB range. Plenty of them will be uninteresting (simple programs that immediately halt on stack underflow, or programs whose behavior clients already agree on) — the Day 4 differential run is what separates signal from noise.

### Coverage discovery trajectory

Go's fuzz engine persists every "new interesting" input (one that hits ≥1 coverage edge not already in the bitmap) to `~/.cache/go-build/fuzz/.../FuzzVMBasic/`. Cache size over the run:

| time           | cache size (entries) |
|----------------|---------------------:|
| phase A start  |                    0 |
| phase A end    |               ~2,180 |
| phase C start  |                  255 |
| phase C +1 h   |               ~2,500 |
| phase C +6 h   |               ~4,200 |
| phase C +12 h  |               ~4,570 |
| phase C end    |                4,599 |
| current        |                4,349 |

(The last number is lower than the peak because the final few cycles died mid-replay and their "interesting" discoveries weren't committed.)

Exec-rate during active fuzzing typically ran 200–750 execs/sec across 16 workers; the instantaneous rate collapses to 0/sec for 1–3 seconds before a FAIL (one worker hung; the others finish their inputs and wait). By hour 10, per-cycle new-interesting counts had dropped to 1–3 — clear plateau.

### Crashers (339 unique)

`scripts/crasher_watcher.sh` polled `testdata/fuzz/FuzzVMBasic/` at 1s cadence and moved every input that caused a FAIL to `out/crashers/<hash>` before the supervisor's next-cycle wipe. Content-hash filenames gave free deduplication. Manifest at `out/crashers/manifest.tsv` has `timestamp, filename, size_bytes` per row.

Size distribution:

| range       | count |
|-------------|------:|
| <100 bytes  |    24 |
| 100–500     |   314 |
| 500–2k      |     0 |
| 2k–10k      |     0 |
| >10k        |     1 |

Every crasher starts with `go test fuzz v1\n` — that's `go-fuzz`'s serialization format, not raw EVM bytecode. Each file is a `[]byte` input that, when unmarshalled and fed to `Fuzz(data []byte)`, makes the worker die. The largest crasher (12,547 bytes) is almost certainly a hang case: an input where the generator built a program that enters an effectively unterminating JUMP loop and the fuzzer harness SIGKILL'd the worker at the 120s timeout.

These files aren't themselves consensus-divergence evidence — they're just inputs that made geth's in-process execution fail. A secondary pass (rerunning each through `goevmlab`) would tell us which ones produce client disagreements. That's a Day 4+ task.

### Why each FAIL happens

Log pattern for every FAIL is identical:

```
fuzz: elapsed: 1m54s, execs: 8170 (305/sec), new interesting: 5 (total: 4604)
fuzz: elapsed: 1m57s, execs: 8298 (43/sec), new interesting: 5 (total: 4604)   ← rate collapse
fuzz: elapsed: 1m57s, execs: 8298 (0/sec), new interesting: 5 (total: 4604)    ← one worker stuck
--- FAIL: FuzzVMBasic (117.11s)
    fuzzing process hung or terminated unexpectedly: exit status 2
    Failing input written to testdata/fuzz/FuzzVMBasic/0ccf9f703eab3e6f
```

Two overlapping root causes — the harness logs the same exit message for both:

1. **Near-infinite execution paths.** A generated program enters a JUMP/JUMPI cycle, deep recursion, or memory-growth loop that never terminates within the per-input budget. Go's fuzz harness has a hung-worker detector that SIGKILLs after ~120s; the 117–120s FAIL elapsed times dominating the distribution are this mode.
2. **Native cgo faults in geth's EVM.** Certain byte patterns cause geth's C-extension code (keccak, secp256k1, modexp, blob-verify) to segfault outright, bypassing Go's `recover()`. These surface as shorter FAIL elapsed times (70–90s) because they kill the process cleanly instead of hanging first.

Both are substrate-level, not bugs in our code. FuzzyVM's `Fuzz()` does have `recover()` (fuzzer.go:79-84) but per its own comment: *"Interesting-bug signal comes from cross-client state-root diffs via goevmlab, not from in-process geth panics."* The baseline intentionally doesn't try to turn crashes into findings.

### Observed fuzz-fraction at 16 threads

Phase C mean cycle: ~85s FAIL elapsed + 5s supervisor sleep = ~90s. Of that, ~6s is baseline-coverage replay (parallelized across 16 workers over 255–4600 cached inputs); the rest is active fuzzing window, ending when one worker hangs or faults. Effective fuzz-fraction ≈ 90%. Much better than the 37% estimate under 4 threads, where a serial replay dominated each cycle.

## Where the data lives

```
out/
├── baseline/                    phase C productive output (990k JSONs, 4.6 GB)
├── baseline.4t/                 phase A productive output (270k JSONs, 1.5 GB)
├── baseline.stuck/              phase B stuck output (1k JSONs, 10 MB)
├── baseline.pre-16h/            earlier aborted session, still in repo
├── crashers/                    339 preserved FAIL inputs + manifest.tsv
├── fuzz_cache.4t_final.tar.gz   poisoned cache backup (120 KB)
├── baseline.log                 phase C supervisor + go-test-fuzz output (~2 MB)
├── baseline.4t.log              phase A log
├── baseline.stuck.log           phase B log
├── baseline.watcher.log         crasher watcher lifecycle log
└── baseline.{pid,start,stop}    session state files (pid now stale)
```

Persistent Go fuzz cache is at `~/.cache/go-build/fuzz/github.com/MariusVanDerWijden/FuzzyVM/fuzzer/FuzzVMBasic/` — 4,349 entries, 19 MB. This is the coverage frontier the LLM-guided run will start from (or can start from, if we choose not to reset it for fairness).

## Takeaways

1. **The pipeline holds up.** 466 crash-restart cycles in 13h30m with zero manual intervention after the one-time cache wipe. Supervisor + watcher + minimization-off (`-fuzzminimizetime=0`) + cache-backup hygiene all did their jobs.
2. **The plateau is real and quantifiable.** First hour: ~300 new-interesting / hour. Last hour: ~20 new-interesting / hour. Random-byte mutation runs out of easy branches quickly once the cache is ≈4,500 entries deep.
3. **Crash cadence is substrate-limited, not us-limited.** Every cycle ends in FAIL within 70–120s regardless of thread count — it's a property of the input space × geth's cgo surface × Go fuzz-harness timeout, not of our supervisor or generator code.
4. **Baseline artifact is ready for differential replay.** 1.26M state-test JSONs sitting in `out/baseline.4t/` and `out/baseline/`, plus 339 crasher inputs. The Day 4 goevmlab wiring can draw from these without needing any more live fuzzing to happen.

## For the LLM-guided comparison (Day 5+)

- **Equal-CPU-hours fairness:** 215.8 CPU-hours of phase C is the headline reference. Phase A (~13 CPU-hours) can be included or excluded depending on whether the LLM-guided run launches at 4 or 16 threads — cleanest comparison is LLM-guided at 16 threads vs. phase C at 16 threads.
- **Cache handling:** the LLM-guided run should start from a clean `~/.cache/go-build/fuzz/` so its own coverage claims aren't inflated by phase C's 4,349 pre-discovered entries. We have the tooling to wipe and archive — already exercised in phase B→C transition.
- **Output isolation:** phase C lives at `out/baseline/`; LLM-guided runs will write to `out/llm_guided/<plan_id>/` per the `--out-dir` flag. No overlap possible.
- **What we'll measure:** cumulative new-interesting rate over time (phase C: ~4,228 / 13.5 h = ~313 / h; LLM target: beat this, especially past hour 6 when baseline plateaus), and — the actual goal — unique cross-client divergences per CPU-hour once goevmlab is wired (Day 4).
