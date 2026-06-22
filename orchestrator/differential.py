"""Differential runner: invokes goevmlab runtest across a batch of FuzzyVM
state-test JSONs, parses its log output, and summarizes consensus flaws.

Why not wrap goevmlab's Go API directly: goevmlab's runtest is a CLI, and its
"aborts on first flaw" behavior is driven by an internal atomic flag set in
the consensus handler. Running it as a subprocess is the stable contract;
re-implementing the VM-adapter orchestration in Python would be a losing bet
against a moving upstream.

Parsing contract (from goevmlab/common/utils.go):
- "Consensus flaw" INFO line → one divergence, fields: file, vm, have, ref vm, want
- "Consensus error" multi-line block on flaw → testcase + per-vm output file paths
- "Slow test found" WARN → benign timing outlier; counted but not a divergence
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTEST_BIN = Path(os.environ.get("RUNTEST_BIN", REPO_ROOT / "goevmlab" / "runtest"))
GETH_EVM_BIN = Path(os.environ.get("GETH_EVM_BIN", Path.home() / "go" / "bin" / "evm"))
REVME_BIN = Path(os.environ.get("REVME_BIN", Path.home() / ".cargo" / "bin" / "revme"))
# besu evmtool is optional. Present -> runtest gets a third client and divergences
# carry a 3-way vote. Absent -> stock geth+revme path is unchanged. The default
# points at the JDK-25 wrapper because besu 26.6.1 ships class file v69 and the
# system default Java is 21.
BESU_BIN = Path(os.environ.get("BESU_BIN", Path.home() / "tools" / "besu-26.6.1" / "bin" / "evmtool-jdk25"))

# ANSI-strip + log parsing. goevmlab uses ethereum/go-ethereum's terminal
# handler which always emits SGR sequences even with no TTY attached.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")
_KV_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')


@dataclass
class Divergence:
    file: str
    vm: str
    ref_vm: str
    have: str
    want: str


@dataclass
class DiffReport:
    batch_dir: str
    tests_run: int = 0
    slow_tests: int = 0
    divergences: list[Divergence] = field(default_factory=list)
    duration_s: float = 0.0
    runtest_rc: int = 0
    vms: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2)


def _parse_kv(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _KV_RE.finditer(line):
        k = m.group(1)
        v = m.group(2) if m.group(2) is not None else m.group(3)
        out[k] = v
    return out


def _parse_log(text: str) -> tuple[list[Divergence], int, int]:
    # "tests=N" statistics lines: keep the last one as authoritative count.
    # Consensus flaws: each one line. Slow test: each one line.
    tests_run = 0
    slow = 0
    divs: list[Divergence] = []
    for raw in text.splitlines():
        line = _ANSI_RE.sub("", raw)
        if "Consensus flaw" in line:
            kv = _parse_kv(line)
            divs.append(Divergence(
                file=kv.get("file", ""),
                vm=kv.get("vm", ""),
                ref_vm=kv.get("ref", "") or kv.get("ref vm", ""),
                have=kv.get("have", ""),
                want=kv.get("want", ""),
            ))
        elif "Slow test found" in line:
            slow += 1
        elif "Executing " in line and "tests=" in line:
            kv = _parse_kv(line)
            try:
                tests_run = max(tests_run, int(kv.get("tests", "0")))
            except ValueError:
                pass
    return divs, tests_run, slow


def _preflight() -> list[str]:
    missing = []
    for p in (RUNTEST_BIN, GETH_EVM_BIN, REVME_BIN):
        if not p.exists():
            missing.append(str(p))
    return missing


def run_diff(batch_out_dir: Path, threads: int = 4, glob: str = "*/FuzzyVM-*.json",
             skiptrace: bool = True, diff_dir: Path | None = None) -> DiffReport:
    """Run runtest across every test JSON under batch_out_dir.

    Returns a DiffReport. Even on non-zero runtest rc we still parse what we
    got — goevmlab aborts (rc!=0) *after* logging the flaw we want.

    diff_dir overrides the default diff output location. The default is
    batch_out_dir.parent/diff (matches the per-plan layout). For posthoc
    sharded runs the caller should pass batch_out_dir/diff so each shard
    gets its own report."""
    batch_out_dir = Path(batch_out_dir)
    missing = _preflight()
    if missing:
        raise FileNotFoundError(f"differential preflight missing binaries: {missing}")

    # goevmlab dumps consensus-flaw traces into --outdir; keep those with the batch.
    diff_out = diff_dir if diff_dir is not None else batch_out_dir.parent / "diff"
    diff_out.mkdir(parents=True, exist_ok=True)

    pattern = str(batch_out_dir / glob)
    cmd = [
        str(RUNTEST_BIN),
        "--geth", str(GETH_EVM_BIN),
        "--revme", str(REVME_BIN),
        "--parallel", str(threads),
        "--outdir", str(diff_out),
    ]
    if BESU_BIN.exists():
        # besubatch keeps one evmtool JVM alive and streams tests into it. The
        # per-test --besu adapter cold-starts a JVM each call (~2s/test), which
        # is unusable for a full-corpus sweep. besu still ~10x slower per test
        # than geth/revme even batched, so it gates throughput; size --threads
        # accordingly on the post-hoc pass.
        cmd += ["--besubatch", str(BESU_BIN)]
    if skiptrace:
        cmd.append("--skiptrace")
    cmd.append(pattern)

    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    duration = time.monotonic() - t0

    log = (proc.stderr or "") + (proc.stdout or "")
    divs, tests_run, slow = _parse_log(log)

    vms = ["geth", "revme"]
    if BESU_BIN.exists():
        vms.append("besu")
    report = DiffReport(
        batch_dir=str(batch_out_dir),
        tests_run=tests_run,
        slow_tests=slow,
        divergences=divs,
        duration_s=round(duration, 2),
        runtest_rc=proc.returncode,
        vms=vms,
    )

    # Persist the raw log and report next to the diff outputs.
    (diff_out / "runtest.log").write_text(log)
    (diff_out / "diff_report.json").write_text(report.to_json())

    # If consensus error trace files landed in diff_out (geth-output.jsonl etc.),
    # leave them; they're the crown-jewel artifact for reproducing a divergence.
    return report


def summarize_report(report: DiffReport, max_divs: int = 5) -> str:
    """One-paragraph human summary suitable for logging + feeding back to LLM."""
    if not report.divergences:
        return (f"No divergences found. Ran {report.tests_run} tests across "
                f"{'+'.join(report.vms)} in {report.duration_s}s "
                f"({report.slow_tests} slow).")
    lines = [f"{len(report.divergences)} divergence(s) across {report.tests_run} tests:"]
    for d in report.divergences[:max_divs]:
        lines.append(f"  - {Path(d.file).name}: {d.vm} state_root={d.have[:12]}… ref {d.ref_vm}={d.want[:12]}…")
    if len(report.divergences) > max_divs:
        lines.append(f"  (+{len(report.divergences) - max_divs} more)")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("batch_out_dir", type=Path)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--glob", default="*/FuzzyVM-*.json")
    ap.add_argument("--with-trace", action="store_true")
    ap.add_argument("--diff-dir", type=Path, default=None,
                    help="override diff output directory (default: batch_out_dir/../diff)")
    args = ap.parse_args()
    rep = run_diff(args.batch_out_dir, threads=args.threads, glob=args.glob,
                   skiptrace=not args.with_trace, diff_dir=args.diff_dir)
    print(summarize_report(rep))
