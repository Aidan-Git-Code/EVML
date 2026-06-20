# Dockerization Design

Status: design, not built yet. This covers how the fuzzer's nodes get packaged as containers so any machine can join the fleet without matching a long list of host packages. It references the distributed design (`distributed-fuzzing.md`) for the full topology but does not depend on it. The single-machine system these nodes are built from is described in the README. The roles it needs are restated below, so this doc reads cold.

## The roles, briefly

The fleet has three kinds of node. A coordinator owns every fleet-wide decision, holds the corpus, and serves a dashboard. GPU nodes run the LLM and emit fuzzing plans. CPU nodes take a plan, run FuzzyVM to generate tests, run goevmlab to diff them across EVM clients, and report findings back. The planner and the worker are separate modules: a GPU box can run both, or run the planner alone when its CPU is needed elsewhere. That is the whole picture this doc needs. See `distributed-fuzzing.md` for how work and findings actually flow between them.

![Per-host container layout: a registry serves the worker and planner images; the coordinator host holds the corpus volume, the GPU host runs the planner and worker containers with model and fuzz-cache volumes, the CPU host runs a worker container with its own fuzz-cache volume, and all hosts sit on the VPN.](dockerization-architecture.png)

## Why containers here

Three reasons, ordered by how much they matter to this project specifically.

Pinned client versions come first. A divergence only means something if every worker ran identical client builds. Today that is `evm@v1.15.11` and `revme` 15.0.0, installed by hand on each machine. Across a mixed local-and-cloud fleet that drift is a real hazard: a "divergence" that is really two different geth patch levels is a false positive, and it poisons the corpus every other node learns from. Baking the client binaries into the worker image makes the version a property of the image tag instead of whatever each host happened to install. That alone justifies the work.

The module decoupling becomes literal. The distributed design requires the planner and worker to be independently stoppable on a GPU box. Two containers is exactly that. Run the planner container always, start and stop the worker container on its own, and `docker stop` on the worker hands the machine's cores back without touching the planner. The decoupling stops being something we engineer and becomes something the container runtime gives us.

Host package mess goes away, which was the original reason to ask. The Go toolchain for go-fuzz, Rust 1.91+ for revme (Debian ships 1.75), CUDA for llama.cpp, the Python embedding stack: standing all of that up consistently on heterogeneous hosts is the slow part of adding a machine. The image carries the environment instead.

And the join is one command, which is the plug-and-play goal stated plainly.

## What gets an image, what does not

Two role images on a shared base: a worker image and a planner image. The coordinator stays host-optional. It is the stateful node with the big disk and the dashboard, a single long-lived process, so containerize it with the drive bind-mounted if you want one-command bring-up, or run it on bare host. Not worth blocking on. The two decisions worth calling out: two images rather than one image with a runtime role flag (cleaner separation, and it maps to the two-container decoupling), and coordinator left host-optional rather than committed to a container.

### Base image

The common layer: the Python orchestrator client, the registration and heartbeat logic, and the join entrypoint. Thin. Both role images build on it.

### Worker image

Base plus the Go runtime for go-fuzz, the FuzzyVM binary, the goevmlab runtest binary, and the pinned differential clients (geth's `evm`, revm's `revme`). This is the image whose tag pins the client versions across the fleet.

### Planner image

Base plus llama.cpp built against CUDA and the plan-generation client. It does not carry the embedder or the FAISS index. The coordinator owns the RAG corpus and does the query embedding, so the planner sends objective text and gets context back. That keeps the planner image to llama.cpp plus a thin client, and it keeps one place in charge of the index.

## What stays outside the image

Three things must be persistent bind-mounts, or the design breaks. The go-fuzz coverage cache (`~/.cache/go-build/fuzz/.../FuzzVMBasic/`) carries coverage across restarts, and since go-fuzz crashes on cgo faults every few minutes, an ephemeral container would wipe that coverage on every restart; mount it. The model file is about 5 GB and does not belong baked into the planner image; mount it. The coordinator corpus lives on the 4 TB drive and is bind-mounted there.

Images hold the code and the pinned tools. Volumes hold the data and the model.

## The entrypoint does the supervisor's job

The single-machine system runs a bash supervisor that wipes `testdata/fuzz/FuzzVMBasic/` between restarts to dodge the crasher-replay trap, then relaunches after go-fuzz hits its cgo fault. In containers that logic moves into the worker entrypoint. Docker's restart policy can handle the restart itself, but only if the entrypoint wipes the testdata seed directory before each `go test --fuzz` run. Skip that and one cached crasher bricks every restart, the same trap the project already hit once. The entrypoint also owns the join: detect whether a usable GPU is present, present the token, register with the coordinator, then start pulling work.

## GPU hosts still need two things

A planner host is not fully package-free. It needs the NVIDIA driver and the NVIDIA Container Toolkit so the container can see the GPU (`docker run --gpus all`). That is a small, standard install next to building a CUDA llama.cpp by hand. Everything above the driver lives in the image.

## Networking

Nodes reach the coordinator over the VPN, and the VPN client runs on the host, so containers ride it with host networking (`--network host`). The coordinator API and the model endpoints stay bound to the VPN interface, same as the distributed design states. Containers add no security here. The only gate is the join token.

## Plugging in a node

A worker, anywhere with Docker:

```bash
docker run -d --restart unless-stopped --network host \
  -e COORDINATOR=10.0.0.5:PORT -e JOIN_TOKEN=... \
  -v fuzzcache:/root/.cache/go-build/fuzz \
  registry.example/evml-worker:<tag>
```

A planner, on a GPU host with the driver and container toolkit:

```bash
docker run -d --restart unless-stopped --network host --gpus all \
  -e COORDINATOR=10.0.0.5:PORT -e JOIN_TOKEN=... \
  -v /models:/models \
  registry.example/evml-planner:<tag>
```

On a GPU box you run both containers. Stop the worker when you want the cores back; the planner keeps going. Pull a machine entirely and the coordinator notices the dropped heartbeat and frees its work.

## Open questions

- Where the images live: a public registry, or a small local registry on the coordinator so the fleet pulls over the VPN.
- Whether the coordinator ships as an image too, so the whole stack comes up with one compose file, or stays host-managed.
- How the fleet picks up a new image tag when client versions bump: a rolling stop-pull-start per node, or something the coordinator drives so the fleet does not run mixed client versions mid-experiment.
