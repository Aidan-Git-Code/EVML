# Distributed Fuzzing Design

Status: design, not yet built. This document describes the target architecture for running the
LLM-guided fuzzer across more than one machine. It is meant to be built once, correctly, not
stood up as a quick hack and rewritten later. Read `CLAUDE.md` first for the single-machine
system this extends.

## Why distribute at all

The bottleneck is CPU, not GPU. A single fuzzing batch spends a few seconds generating a plan on
the GPU, then the GPU sits idle for the rest of the batch while 16 CPU threads run FuzzyVM's
go-fuzz loop and goevmlab diffs the output. The plan generation is cheap and infrequent. The
generation and differential passes are where the wall-clock goes.

That shapes everything below. We do not need a GPU per machine. We need many CPU workers pulling
plans from one or a few model servers, all writing findings back to one shared place. The model is
a shared service. The corpus and the findings are shared state. The fuzzing itself is the part
that fans out.

## Goals and non-goals

Goals:

- Near-linear CPU scaling of generation and differential work as machines are added.
- One architecture that runs identically at one machine and at fifty. The single-machine case is
  N=1, not a separate code path.
- Global feedback. A divergence found on any node informs the next plan on every node.
- Correct plateau detection and objective rotation across the whole fleet, not per-node.
- Divergence deduplication, so the same client bug found by ten machines counts once.
- Preserved experiment attribution. The baseline-vs-LLM comparison still holds when both run in
  the same fleet against the same shared store.

Non-goals:

- Multi-datacenter or WAN operation. This targets a LAN or a single cloud subnet. Workers are
  trusted. There is no adversarial-worker threat model.
- Autoscaling or elastic worker pools. Workers are started and stopped by hand or by a simple
  supervisor. The count changes rarely.
- Replacing goevmlab or FuzzyVM internals. We wrap them, same as the single-machine system does.

## Core principle: N=1 is a special case

The single biggest design decision is that there is no "distributed mode." There is one system.
At N=1 it runs a coordinator, one worker, a local store, and a local model server, all on one box.
At N=50 the same coordinator runs on one host, fifty workers run elsewhere, the store is a real
database plus an object store, and the model runs on the GPU hosts. The code is identical. Only
the backend bindings and the host count differ.

This is what "right the first time" means here. If the single-machine path and the distributed
path are different code, the single-machine path will rot and the distributed path will carry bugs
nobody hits until the demo. One path, exercised constantly, configured at the edges.

Concretely: every interaction between a worker and shared state goes through an interface with two
implementations. A local implementation backed by SQLite and the local filesystem. A networked
implementation backed by Postgres and an object store. The worker code does not know which it is
talking to.

## Architecture

```
                         ┌──────────────────┐
                         │  Model server(s) │   llama-server, GPU hosts
                         │  (stateless)     │   plan generation + rotation prompts
                         └─────────▲────────┘
                                   │ HTTP /completion (grammar-constrained)
                                   │
   ┌───────────┐   lease work   ┌──┴───────────┐   read/write   ┌──────────────────┐
   │  Worker 1 │◄──────────────►│ Coordinator  │◄──────────────►│  Findings store  │
   │  Worker 2 │   report       │              │                │  (relational)    │
   │   ...     │   results      │  - objectives│                │                  │
   │  Worker N │                │  - plateau   │                ├──────────────────┤
   └─────┬─────┘                │  - rotation  │                │  Artifact store  │
         │                      │  - dedup     │                │  (object/blob)   │
         │ generate + diff      │  - diff shards│               │  state-tests,    │
         │ locally              └──────────────┘                │  traces, corpus  │
         ▼                                                       └──────────────────┘
   FuzzyVM + goevmlab
```

Four components. The coordinator owns decisions. Workers do work. The model servers answer
prompts. The store holds state and artifacts. Each is described below.

### Coordinator

One process. It is the only component that makes fleet-wide decisions, which is what keeps the
fleet coherent. Responsibilities:

- Hand out work. A worker asks for something to do; the coordinator returns either an objective to
  pursue or, later, a specific differential shard to run.
- Own the active objective set. Workers do not pick objectives. The coordinator does, because
  plateau detection and rotation have to see global state.
- Run plateau detection and rotation. This is currently in `rotate.py` and runs per-batch on each
  node's local view. In the fleet that logic moves to the coordinator and runs against the global
  findings store. If it stayed on the workers, every node would detect the same plateau
  independently and rotate to a different new objective, and the fleet would scatter across N
  unrelated objectives within one cycle. Rotation must be a single decision.
- Deduplicate divergences. When a worker reports a flaw, the coordinator computes its fingerprint
  (see below), checks whether it has been seen, and records it as new or as another hit on an
  existing bug.
- Assign differential shards. The post-fuzz diff pass is split into file-range shards; the
  coordinator hands them out and tracks completion.

The coordinator is a single point of failure. For a research fleet on a LAN that is acceptable.
It keeps all durable state in the store, so if it dies it restarts and resumes from the store.
Workers retry their reports with backoff while it is down. We do not build coordinator HA.

### Worker

Stateless puller. Runs the loop that `start_llm_loop.sh` runs today, except it gets its objective
from the coordinator instead of a command-line flag, and it writes findings to the store instead
of the local filesystem. Per cycle:

1. Ask the coordinator for work. Get back an objective and a seed-space slice (see below).
2. Pull recent global findings from the store for the prompt's "recent findings" block.
3. Generate a plan against a model server. This is the existing `call_llm` path, unchanged, just
   pointed at a possibly-remote URL.
4. Run FuzzyVM under the plan, locally, for the batch duration. Output stays on local disk.
5. Run the differential locally over the just-generated tests, or defer it to the shard pass.
6. Report results: the plan, the batch stats, and any divergences, to the coordinator. Upload the
   crown-jewel artifacts (the failing state-test plus per-VM traces) to the artifact store.
7. Repeat.

A worker holds no state that matters. If it dies mid-batch, its lease expires and the coordinator
reissues the objective. The half-written local output is discarded. Nothing downstream depended on
it because nothing is reported until the batch completes.

### Model server

llama-server, unchanged. It is already an HTTP service and `run_batch.py` already takes
`--llm-url`, so this part is mostly configuration. Two operational notes. One model server on one
4080 can serve plan generation for many CPU workers, because each worker only asks for a plan once
per batch (roughly once every 90 seconds) and decode takes a few seconds. If the request rate ever
saturates one server, run two or three instances and put a round-robin in front; the workers do not
care how many there are. The rotation prompts in `rotate.py` hit the same server with a
grammar-free call, so the coordinator needs a model URL too.

### Findings store

The relational state. Objectives, plans, batch records, divergences and their fingerprints, node
registrations, corpus generations. At N=1 this is SQLite on local disk. In the fleet it is Postgres.
fuzzillai used Postgres for exactly this and the project skipped it for the six-day build; this is
where we un-skip it. The schema is below.

### Artifact store

The bulky, content-addressed blobs that do not belong in a relational table. Generated state-tests,
per-VM traces from flaws, and merged corpus generations. At N=1 this is a directory tree keyed by
content hash. In the fleet it is an object store (MinIO is enough; a shared NFS mount with a
content-addressed layout also works and is simpler to stand up). We do not put millions of
state-test JSONs into Postgres. We put their hashes and counts there and the bytes in the artifact
store, and most state-tests we never store at all, only the ones tied to a divergence.

## Data model

The relational schema. Types are illustrative; tighten them at implementation.

`node` — a registered worker or the coordinator itself.

| column | type | note |
|---|---|---|
| id | text pk | stable per host+process |
| host | text | hostname or IP |
| role | text | `worker`, `coordinator`, `differ` |
| cpu_threads | int | fuzz parallelism this node runs |
| has_gpu | bool | informational |
| source | text | `llm` or `baseline`, fixes attribution |
| last_heartbeat | timestamp | lease/liveness |

`objective` — a fuzzing target.

| column | type | note |
|---|---|---|
| id | text pk | |
| text | text | the objective string, copied verbatim into plans |
| fork | text | e.g. Cancun |
| status | text | `active`, `plateaued`, `retired` |
| origin | text | `seed`, `rotation` |
| parent_id | text fk null | the objective this was rotated from |
| created_at | timestamp | |

`plan` — one emitted strategy plan.

| column | type | note |
|---|---|---|
| plan_id | text pk | the existing sha256 canonical id from `canonical_plan_id` |
| objective_id | text fk | |
| node_id | text fk | who generated it |
| json | jsonb | the full plan document |
| created_at | timestamp | |

`batch` — one FuzzyVM run under one plan.

| column | type | note |
|---|---|---|
| id | text pk | |
| plan_id | text fk | |
| node_id | text fk | |
| seed_slice | int | which seed-space partition this node used |
| tests_generated | int | |
| fuzz_seconds | float | actual fuzzing time, not wall-clock |
| started_at | timestamp | |
| ended_at | timestamp | |

`divergence` — a deduplicated consensus flaw, not a raw report.

| column | type | note |
|---|---|---|
| id | text pk | |
| fingerprint | text unique | the canonical bug signature, see below |
| first_batch_id | text fk | who found it first |
| objective_id | text fk | what objective surfaced it first |
| client_pair | text | e.g. `geth:revme`, sorted |
| diverging_opcode | text | opcode at the first diverging trace step |
| diverging_field | text | `state_root`, `gas`, `stack`, `memory`, `storage` |
| example_test_ref | text | artifact-store key for the minimized repro |
| have | text | the divergent value, e.g. one state root |
| want | text | the reference value |
| hit_count | int | how many raw reports mapped to this fingerprint |
| first_seen_at | timestamp | |

`corpus_generation` — a merged go-fuzz coverage corpus snapshot.

| column | type | note |
|---|---|---|
| id | int pk | monotonically increasing generation number |
| artifact_ref | text | object-store key for the merged corpus tarball |
| input_count | int | after `minCorpus` dedup |
| merged_at | timestamp | |
| source_nodes | int | how many node exports fed this merge |

The `have`/`want`/`client_pair` columns map straight onto the existing `Divergence` dataclass in
`differential.py` (`vm`, `ref_vm`, `have`, `want`). The new fields (`diverging_opcode`,
`diverging_field`) come from trace analysis, described next.

## Divergence fingerprinting and dedup

This is the hard part, so it gets its own section. Get it wrong and the headline metric,
divergences per CPU-hour, is meaningless, because ten machines fuzzing similar objectives will
report the same client bug over and over.

The naive fingerprint is `(client_pair, have, want)`. It does not work. The `have` and `want`
fields are post-execution state roots, and a state root encodes the entire post-state of the test.
Two genuinely different test cases that trip the same underlying bug produce different state roots,
so this fingerprint treats one bug as many. It over-counts, which is the failure we are trying to
avoid.

The correct signature is the first point where the clients disagree, not the end state. Two test
cases that diverge for the same reason will diverge at the same opcode on the same kind of field
(gas, or a stack value, or a storage write), even if everything downstream differs. So the
fingerprint is built from the trace, not the result:

1. On a flaw, capture the per-VM execution traces. goevmlab already dumps these into the diff
   output directory as `.jsonl` files when tracing is on.
2. Walk the two traces in lockstep to the first step where they disagree. Record the opcode at
   that step, the program counter, and which field diverged (gas, stack top, memory, storage,
   or the final state root if they agree step-by-step but produce different roots).
3. The fingerprint is a hash of `(sorted client_pair, opcode_at_divergence, diverging_field_kind)`.
   Optionally tighten it with a hash of the minimized bytecode, so distinct bugs that happen to
   diverge at the same opcode stay separate.

There is a cost wrinkle worth designing around now. `differential.py` runs `runtest` with
`--skiptrace` by default, because traces are expensive and most tests do not flaw. Fingerprinting
needs traces. The answer is a two-stage diff, which is also just good engineering:

- Stage one, fast: run the whole batch with `--skiptrace`. This finds which tests flaw and nothing
  else. It is what the system does today.
- Stage two, narrow: re-run only the flawed tests with tracing on, to produce the per-VM traces the
  fingerprint needs. This is a handful of tests, so the trace cost is bounded.

The coordinator does the fingerprinting when it receives a flaw report, or the worker does stage
two locally and reports the finished fingerprint. Either works; doing it on the worker keeps the
trace bytes off the coordinator unless the bug is new. The minimized repro for a new fingerprint
goes to the artifact store and is referenced by `example_test_ref`. Minimization can reuse FuzzyVM
and goevmlab's existing test-rerun path; we do not need gdb-style triage, which the project already
ruled out.

## Plateau detection and rotation

Today `rotate.detect_plateau` scans the last K local `diff_report.json` files and
`rotate.propose_objective` asks the model for a fresh objective. In the fleet this logic is
unchanged in spirit and moves to the coordinator, with two differences.

It reads from the global findings store, so K is a window over the whole fleet's recent batches,
not one node's. A plateau means the fleet collectively found nothing across the last K batches,
which is the signal we actually want.

It runs once and updates the shared objective set. When the coordinator rotates, it marks the old
objective `plateaued`, inserts the new one as `active` with `origin=rotation` and a `parent_id`,
and every worker picks it up on its next work request. No worker rotates on its own. This is the
correctness fix that makes rotation safe at scale.

One subtlety: rotation should debounce. With many workers reporting concurrently, the coordinator
should rotate at most once per cooldown window, so a burst of zero-divergence reports arriving
together does not trigger several rotations in a row. A simple timestamp on the last rotation
covers it.

## Coverage corpus sync

This is optional and should be measured before it is built. It is described here so that if we do
build it, we build it right.

What go-fuzz's coverage corpus actually contains is worth stating plainly, because it changes the
value calculation. go-fuzz instruments FuzzyVM's own generator code, the `FuzzVMBasic` function,
not the EVM clients. Its "interesting" inputs are seeds that drive the generator down new code
paths, which is a proxy for diverse bytecode shapes. It is not EVM coverage. Sharing it helps each
node avoid re-exploring generator-input regions its peers already covered. That is real but it is
second-order next to sharing findings.

If we build it, the protocol is a coordinator-mediated merge:

1. Each worker periodically exports its local `~/.cache/go-build/fuzz/.../FuzzVMBasic/` interesting
   inputs and uploads them to the artifact store.
2. The coordinator merges the exports and prunes them with FuzzyVM's existing `minCorpus`
   subcommand, which already does coverage-preserving corpus minimization. The result is a new
   `corpus_generation` row plus a tarball in the artifact store.
3. Workers pull the latest generation and merge it into their local cache before the next batch.

The merge is periodic and coarse, not per-batch. Corpus generations are versioned so a slow worker
can skip generations and just take the newest. This is the most code and the least certain payoff
of anything in this document. Build phases one and two, measure whether coverage is plateauing
because nodes keep rediscovering the same generator paths, and only then decide.

## Seed-space partitioning

FuzzyVM derives bytecode from seed bytes, and go-fuzz mutates a shared seed corpus. If every node
starts from the same seeds and the same corpus, their exploration overlaps and the marginal node
adds less than it should. Each worker should get a disjoint slice of seed space.

The mechanism is small: salt the seed with the node's slice index, handed out by the coordinator at
work-lease time and recorded in `batch.seed_slice`. This needs a minor FuzzyVM change to accept a
seed salt, in the same spot the plan is read. With distinct salts, nodes explore different regions
and the corpus merge (if built) recombines what they find. Without it, distribution still works,
it is just less efficient per node.

## Experiment attribution

The whole point of the project is comparing LLM-guided fuzzing against stock random on an equal CPU
budget. Distribution must not blur that. The `node.source` column (`llm` or `baseline`) tags every
batch and every divergence by which methodology produced it. Baseline nodes run stock FuzzyVM with
no plan; LLM nodes run plans. They can share the same fleet, the same coordinator, and the same
findings store, as long as every metric query can filter on `source`. Keeping LLM-generated work in
a separate, attributable lane is the same discipline the single-machine system already follows with
its separate output folders; here it is a column instead of a directory, and it must be set at node
registration and never inferred.

## Consistency and failure model

The findings store is the source of truth. Everything durable lives there or in the artifact store.

The feedback loop tolerates staleness. The "recent findings" block in a prompt is a heuristic
input, so a worker reading a slightly stale view of global findings is fine. Eventual consistency is
acceptable for reads that feed prompts.

Plateau and rotation do not tolerate staleness, which is exactly why they are centralized on the
coordinator against the authoritative store rather than computed from any worker's local view.

Dedup must be atomic. Two workers reporting the same new fingerprint at the same instant must result
in one `divergence` row with `hit_count` two, not two rows. A unique constraint on `fingerprint`
plus an upsert handles it.

Worker death is handled by leases. A work assignment carries an expiry. If the worker does not
report or renew before expiry, the coordinator considers the objective free again. Because workers
report nothing until a batch completes, a dead worker loses only its in-flight batch, and nothing
downstream consumed it.

Coordinator death loses no durable state. It restarts, reads the store, and resumes. Workers retry
with backoff meanwhile. In-flight leases expire and are reissued. We accept a stall, not data loss.

## Trust and security boundary

Workers are trusted. This runs on a LAN or one cloud subnet, and a worker can already run arbitrary
bytecode through real EVM clients by design, so there is no point pretending the worker boundary is
a security boundary. The model endpoint and the coordinator API should still bind to the private
network, not a public interface, because neither is built to face the open internet. The artifact
store holds nothing sensitive, just test cases and traces. No auth beyond network reachability is in
scope. If this ever leaves a trusted network, that is a new design, not a tweak to this one.

## Mapping to the existing code

Nothing here is throwaway because the existing modules already factor along the right seams. The
work is to introduce interfaces, not rewrite logic.

- `differential.py` already separates "run the diff" from "where the output goes" via the
  `diff_dir` argument and the sharding-friendly glob. It becomes the body of a differential worker.
  The `Divergence` dataclass is the raw input to fingerprinting; add the trace-analysis step beside
  it.
- `rotate.py`'s `detect_plateau` and `propose_objective` are already pure functions over a
  directory of reports and a model URL. Repoint them from a local directory to the store interface
  and call them from the coordinator instead of from `run_batch.py`.
- `run_batch.py`'s `gather_recent_findings` is the read side of the feedback loop. It becomes a
  store query. `canonical_plan_id` stays exactly as is; that hash is the `plan.plan_id` primary key.
- `start_llm_loop.sh`'s loop becomes the worker agent's loop, with the objective coming from a work
  lease instead of `--objective` and results going to the store instead of `out/`.

The new code is three things: the store interface with a local and a networked backend, the
coordinator service, and the worker agent that wraps the existing batch logic. Define the store
interface first, because both the single-machine and fleet paths run through it, and it is what
keeps the two from diverging.

## Build phases

Each phase is additive. No phase throws away the previous one.

Phase 0: introduce the store interface. Move `gather_recent_findings`, the plateau read, and the
findings write behind a `Store` interface with a local SQLite-plus-filesystem backend. The
single-machine system now runs through the interface and behaves identically. Nothing distributed
yet. This is the phase that makes everything after it cheap.

Phase 1: the differential fleet. Stand up the artifact store and a trivial coordinator that only
hands out diff shards. Run the post-fuzz differential pass across machines. This needs no shared
go-fuzz corpus and no plan coordination, so it is the lowest-risk way to prove the coordinator,
the store, and the worker registration all work. It also delivers the biggest immediate throughput
win, since the diff pass is embarrassingly parallel by file.

Phase 2: the generation fleet. Add objective assignment, the networked store backend (Postgres),
global recent-findings reads, and centralized plateau and rotation. Workers now generate as well as
diff. Add seed-space partitioning. This is the full LLM-guided fleet.

Phase 3: divergence fingerprinting and dedup. Add the two-stage trace diff and the fingerprint
upsert. Until this lands, treat raw divergence counts as upper bounds, not deduplicated truth.

Phase 4: coverage corpus sync, only if phase-2 measurements show nodes redundantly re-exploring
generator paths. Build the merge protocol around `minCorpus` and corpus generations. Skip it
otherwise.

## What to measure before and during

- Plan-request rate against one model server, to know when a second server is needed.
- Differential throughput in tests per second per machine, to confirm the diff fleet scales near
  linearly.
- Raw versus deduplicated divergence counts, to quantify how badly the fleet would over-count
  without fingerprinting. This number justifies phase 3.
- Coverage growth per node over time. Flat growth with many nodes is the signal that corpus sync
  (phase 4) might pay off. Healthy growth means skip it.
- Divergences per CPU-hour, split by `source`, which is the headline comparison the whole project
  exists to produce. Distribution must not change how this is computed, only how fast the data
  arrives.
