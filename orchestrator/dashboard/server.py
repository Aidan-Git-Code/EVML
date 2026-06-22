#!/usr/bin/env python3
"""Stats server for the fuzzing dashboard.

Serves the static dashboard and a /api/stats JSON endpoint that scans
out/llm_guided/ (per-plan diff reports + plan files), the loop/llama session
state files, and the crasher manifest. Stdlib only, no framework.

Run:
    python3 orchestrator/dashboard/server.py [--port 8090] [--out-root out]

Then open http://127.0.0.1:8090/ in a browser.
"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Optional HTTP Basic auth. Off unless DASH_AUTH="user:pass" is set in the
# environment (an env var, not a CLI flag, so it does not leak via `ps`).
# Basic auth is plaintext-over-the-wire, so only enable it behind TLS (Caddy).
_AUTH: "tuple[str, str] | None" = None
REPO_ROOT = HERE.parent.parent

# Set by main().
OUT_ROOT = REPO_ROOT / "out"
LLM_GUIDED = OUT_ROOT / "llm_guided"

_BATCH_RE = re.compile(r"=== batch (\d+) ===")


def _pid_alive(pid_file: Path) -> tuple[bool, int | None]:
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return False, None
    try:
        os.kill(pid, 0)
        return True, pid
    except (OSError, ProcessLookupError):
        return False, pid


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text().strip()
    except OSError:
        return None


def _tail(p: Path, n: int = 4000) -> str:
    try:
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _crasher_count() -> int:
    manifest = OUT_ROOT / "crashers" / "manifest.tsv"
    if manifest.exists():
        try:
            # minus header row
            return max(0, sum(1 for _ in manifest.open()) - 1)
        except OSError:
            pass
    crash_dir = OUT_ROOT / "crashers"
    if crash_dir.is_dir():
        return sum(1 for c in crash_dir.iterdir() if c.is_file() and c.name != "manifest.tsv")
    return 0


def _scan() -> dict:
    plan_dirs = sorted(LLM_GUIDED.glob("plan_*"), key=lambda p: p.stat().st_mtime) if LLM_GUIDED.is_dir() else []

    tests_total = 0
    div_total = 0
    slow_total = 0
    batches = 0
    last_vms: list[str] = []
    rows = []
    recent_divs = []

    for d in plan_dirs:
        report = d / "diff" / "diff_report.json"
        if not report.exists():
            continue
        try:
            rep = json.loads(report.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        batches += 1
        t = int(rep.get("tests_run", 0) or 0)
        divs = rep.get("divergences", []) or []
        tests_total += t
        div_total += len(divs)
        slow_total += int(rep.get("slow_tests", 0) or 0)
        vms = rep.get("vms", []) or []
        if vms:
            last_vms = vms

        objective = None
        plan = d / "plan.json"
        if plan.exists():
            try:
                objective = json.loads(plan.read_text()).get("objective")
            except (OSError, json.JSONDecodeError):
                pass

        rows.append({
            "plan_id": d.name,
            "objective": objective or "(unknown)",
            "tests": t,
            "divergences": len(divs),
            "duration_s": round(float(rep.get("duration_s", 0) or 0), 1),
            "vms": vms,
            "rc": int(rep.get("runtest_rc", 0) or 0),
            "mtime": report.stat().st_mtime,
        })
        for dv in divs:
            recent_divs.append({
                "plan_id": d.name,
                "file": Path(dv.get("file", "")).name,
                "vm": dv.get("vm", ""),
                "ref_vm": dv.get("ref_vm", ""),
                "mtime": report.stat().st_mtime,
            })

    rows.sort(key=lambda r: r["mtime"], reverse=True)
    recent_divs.sort(key=lambda r: r["mtime"], reverse=True)

    # Clients reflect the most recently *written* report, not the newest plan
    # dir. A post-hoc re-diff rewrites old reports (adding besu) without bumping
    # the dir mtime, and a fresh batch's dir has no report until its diff lands.
    if rows:
        last_vms = rows[0]["vms"] or last_vms

    # Loop / llama session state.
    loop_running, loop_pid = _pid_alive(OUT_ROOT / "llm_loop.pid")
    llama_running, llama_pid = _pid_alive(OUT_ROOT / "llama_server.pid")

    current_batch = None
    log_tail = _tail(OUT_ROOT / "llm_loop.log")
    matches = _BATCH_RE.findall(log_tail)
    if matches:
        current_batch = int(matches[-1])

    current_objective = rows[0]["objective"] if rows else None

    rate = round(div_total / (tests_total / 1_000_000), 3) if tests_total else 0.0

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "loop": {
            "running": loop_running,
            "pid": loop_pid,
            "started": _read_text(OUT_ROOT / "llm_loop.start"),
            "stop_at": _read_text(OUT_ROOT / "llm_loop.stop"),
            "current_batch": current_batch,
            "current_objective": current_objective,
        },
        "llama": {"running": llama_running, "pid": llama_pid},
        "totals": {
            "plans": len(plan_dirs),
            "batches": batches,
            "tests": tests_total,
            "divergences": div_total,
            "slow_tests": slow_total,
            "crashers": _crasher_count(),
        },
        "rates": {
            "divergences_per_million_tests": rate,
            "tests_per_batch": round(tests_total / batches) if batches else 0,
        },
        "clients": last_vms,
        "recent_batches": rows[:60],
        "recent_divergences": recent_divs[:30],
    }


class _Cache:
    def __init__(self, ttl: float = 2.5):
        self.ttl = ttl
        self._data: dict | None = None
        self._at = 0.0

    def get(self) -> dict:
        now = time.monotonic()
        if self._data is None or now - self._at > self.ttl:
            self._data = _scan()
            self._at = now
        return self._data


_CACHE = _Cache()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        if _AUTH is None:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        # constant-time compares so a wrong username can't be timed apart
        return (hmac.compare_digest(user, _AUTH[0])
                & hmac.compare_digest(pw, _AUTH[1]))

    def _challenge(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="EVML"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._authed():
            self._challenge()
            return
        if self.path.startswith("/api/stats"):
            body = json.dumps(_CACHE.get()).encode()
            self._send(200, body, "application/json")
            return
        if self.path in ("/", "/index.html"):
            try:
                body = (HERE / "index.html").read_bytes()
                self._send(200, body, "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"index.html missing", "text/plain")
            return
        self._send(404, b"not found", "text/plain")


def main():
    global OUT_ROOT, LLM_GUIDED, _AUTH
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    args = ap.parse_args()

    OUT_ROOT = Path(args.out_root).resolve()
    LLM_GUIDED = OUT_ROOT / "llm_guided"

    auth_env = os.environ.get("DASH_AUTH", "")
    if auth_env:
        if ":" not in auth_env:
            raise SystemExit('DASH_AUTH must be "user:password"')
        u, _, p = auth_env.partition(":")
        _AUTH = (u, p)

    exposed = args.host not in ("127.0.0.1", "localhost", "::1")
    if exposed and _AUTH is None:
        print("WARNING: bound to a non-loopback address with no DASH_AUTH set; "
              "anyone who can reach this port can read the stats.")
    if _AUTH is not None:
        print("basic auth: ON (Basic auth is plaintext; serve only behind TLS)")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard on http://{args.host}:{args.port}/  (out-root: {OUT_ROOT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
