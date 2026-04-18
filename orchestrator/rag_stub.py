"""Day-2 RAG stub. Hardcoded context snippets so the orchestrator pipeline is
end-to-end testable before the FAISS index (Day 3) is built.

Each entry is a short (1-4 sentence) snippet pulled from public sources: EIPs,
geth release notes, historical client-divergence postmortems. Real retrieval
replaces this in orchestrator/rag/ later.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Snippet:
    source: str
    text: str


_STUB_CORPUS: list[Snippet] = [
    Snippet(
        "EIP-2929",
        "Access list (EIP-2929, Berlin): first access to an address or storage slot "
        "costs 2600/2100 gas; subsequent warm accesses cost 100. Divergences between "
        "clients historically cluster around nested CALL/DELEGATECALL where the warm "
        "set is mutated inside a sub-frame.",
    ),
    Snippet(
        "EIP-1153",
        "Transient storage (EIP-1153, Cancun): TSTORE/TLOAD operate on per-transaction "
        "storage that is discarded at tx end. Early implementations disagreed on "
        "visibility across CREATE/CREATE2 frames and on reverts inside nested calls.",
    ),
    Snippet(
        "EIP-4844",
        "Blob transactions + BLOBHASH opcode (EIP-4844, Cancun). The BLOBHASH opcode "
        "returns versioned hashes of transaction blobs; consensus bugs have appeared "
        "when the index is out of range or the transaction has no blobs.",
    ),
    Snippet(
        "EIP-3529",
        "SSTORE gas refund reduction (EIP-3529, London): refund capped at gas_used/5. "
        "Clients have historically differed on whether refund is computed before or "
        "after including the current frame's gas cost.",
    ),
    Snippet(
        "incident:besu-geth-2023-selfdestruct",
        "2023 Shanghai-era divergence: besu and geth disagreed on SELFDESTRUCT semantics "
        "when the beneficiary equals the caller and the balance is zero. Surfaces only "
        "with specific nested CALL + SELFDESTRUCT sequences.",
    ),
    Snippet(
        "incident:revm-modexp",
        "revm/geth historical mismatch on MODEXP precompile (0x05) with zero-length "
        "modulus: revm returned empty, geth returned a single zero byte. Still a good "
        "target for precompile fuzzing.",
    ),
    Snippet(
        "opcode:EXTCODEHASH",
        "EXTCODEHASH returns the Keccak-256 hash of a contract's bytecode. Returns 0 "
        "for non-existent accounts and the empty-hash for existing accounts with no "
        "code. Clients have disagreed on the distinction in post-SELFDESTRUCT states.",
    ),
    Snippet(
        "opcode:JUMPDEST-analysis",
        "Valid JUMPDEST analysis: a JUMPDEST byte (0x5B) only counts if it is not "
        "inside PUSH data. Discrepancies show up with truncated code and with "
        "CREATE-time code ending mid-PUSH.",
    ),
]


def retrieve(objective: str, k: int = 4) -> list[Snippet]:
    """Stub retriever: word-overlap scoring.

    Deterministic by design; real retrieval (FAISS + bge-small) lands on Day 3.
    """
    tokens = {w.lower() for w in objective.split() if len(w) > 2}
    scored: list[tuple[int, Snippet]] = []
    for snip in _STUB_CORPUS:
        body = (snip.source + " " + snip.text).lower()
        overlap = sum(1 for t in tokens if t in body)
        scored.append((overlap, snip))
    scored.sort(key=lambda x: -x[0])
    top = [s for score, s in scored if score > 0][:k]
    if not top:
        # No overlap -> return a fixed safe default so the LLM always has grounding.
        top = _STUB_CORPUS[:k]
    return top


def format_context(snippets: list[Snippet]) -> str:
    return "\n\n".join(f"[{s.source}] {s.text}" for s in snippets)
