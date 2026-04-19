# EVM opcode reference (divergence-prone subset)

Each section is a single opcode, focused on facts the LLM needs to pick plan
weights/bans: semantics, fork introduced, gas model, and known cross-client
disagreement surfaces.

## STOP (0x00)
Halts execution with success, returning no data. Introduced: Frontier.
Divergence surface: minimal. Mostly a "no reason to ban" reference point.

## ADD (0x01)
Integer add mod 2^256. Frontier. Divergence: none known.

## MUL (0x02)
Integer multiply mod 2^256. Frontier. Divergence: none known.

## EXP (0x0A)
Integer exponentiation. Dynamic gas depends on exponent byte length: 10 +
50*byte_len (post-Spurious Dragon). Historical divergences on extreme
exponents and gas-exhaustion paths.

## SIGNEXTEND (0x0B)
Sign-extend a 2s-complement integer of byte_count bytes. Frontier. Rare
divergence target.

## LT / GT / SLT / SGT / EQ / ISZERO (0x10-0x15)
Comparison ops. Frontier. Minimal divergence surface.

## AND / OR / XOR / NOT / BYTE (0x16-0x1A)
Bitwise ops. Frontier. Minimal divergence surface.

## SHL / SHR / SAR (0x1B-0x1D)
Bit shifts. Constantinople (EIP-145). Occasional divergence on large shift
amounts (shift >= 256 → result should be 0 or sign-filled).

## KECCAK256 (0x20)
Keccak-256 hash over memory region. Frontier. Divergence: hash implementation
bugs in early clients; gas on memory expansion is the trickier path.

## ADDRESS / BALANCE / ORIGIN / CALLER / CALLVALUE (0x30-0x34)
Frame identity ops. BALANCE's gas changed across forks (EIP-1884 → 700, EIP-2929
warm/cold). Divergence on BALANCE often appears in warm/cold access edge cases.

## CALLDATALOAD / CALLDATASIZE / CALLDATACOPY (0x35-0x37)
Read tx input data. CALLDATACOPY costs O(size). Rare divergence.

## CODESIZE / CODECOPY (0x38-0x39)
Self-code inspection. Rare divergence.

## GASPRICE (0x3A)
Returns effective gas price. EIP-1559 changes semantics (max-fee vs. priority).
Divergence rare but possible in legacy-vs-1559 corner cases.

## EXTCODESIZE / EXTCODECOPY / EXTCODEHASH (0x3B, 0x3C, 0x3F)
Inspect other accounts' code. EXTCODEHASH (EIP-1052, Constantinople) returns
keccak(code) for existing accounts, 0 for non-existent. Divergence history:
post-SELFDESTRUCT states, empty-vs-nonexistent distinction, and after EIP-2929
the warm/cold cost split is a divergence hotspot.

## RETURNDATASIZE / RETURNDATACOPY (0x3D, 0x3E)
Byzantium (EIP-211). RETURNDATACOPY reverts if src+size > return data size.
Divergence on out-of-bounds: clients have differed on whether it consumes gas
before reverting.

## BLOCKHASH (0x40)
Returns hash of blocks 1..256 back, 0 otherwise. Frontier. In fuzz contexts,
this reads uninitialized harness state — often banned from plans because the
signal it produces is environmental, not about bytecode behavior.

## COINBASE / TIMESTAMP / NUMBER / DIFFICULTY (0x41-0x44)
Block environment reads. PREVRANDAO (0x44) semantics changed at The Merge
(was DIFFICULTY). Divergence possible at fork-boundary tests.

## PREVRANDAO (0x44, Merge+)
Returns the previous block's RANDAO mix. Before Merge, 0x44 was DIFFICULTY.
Divergence target when fork selection is wrong or transition-block behavior.

## GASLIMIT (0x45)
Returns block gas limit. Rare divergence.

## CHAINID (0x46)
Istanbul (EIP-1344). Usually not a divergence source.

## SELFBALANCE (0x47)
Istanbul (EIP-1884). Read own balance cheaply (5 gas vs BALANCE 700). Minor
divergence surface; gas accounting edge cases.

## BASEFEE (0x48)
London (EIP-3198). Returns block base fee. Divergence on pre-London execution
is a fork-selection bug not semantic.

## BLOBHASH (0x49)
Cancun (EIP-4844). Returns versioned hash of blob at index; 0 if out of range
or no blobs. Divergence history: out-of-range indexing, empty blob tx
handling, and interaction with blob gas metering.

## BLOBBASEFEE (0x4A)
Cancun (EIP-7516). Cheap blob-basefee read. Minor divergence surface.

## POP (0x50)
Discard top of stack. Frontier. Zero divergence.

## MLOAD / MSTORE / MSTORE8 (0x51-0x53)
Memory reads/writes. Memory expansion gas is quadratic past 32*724 words.
Divergence: memory-expansion gas accounting in corner-case offsets (near
2^32, negative in signed arithmetic).

## SLOAD (0x54)
Persistent storage read. EIP-2200 (Istanbul) and EIP-2929 (Berlin) reshaped
gas: warm access = 100, cold = 2100. Primary EIP-2929 divergence target.

## SSTORE (0x55)
Persistent storage write. Most-changed opcode in EVM history: EIP-1283
(Constantinople, later disabled), EIP-2200 (Istanbul), EIP-2929 (Berlin),
EIP-3529 (London — refund cap = gas_used/5). Divergences cluster on
refund math and original-value tracking.

## JUMP / JUMPI (0x56, 0x57)
Unconditional/conditional jump to a JUMPDEST. JUMPDEST validity must be
computed via JUMPDEST analysis (ignore JUMPDEST bytes inside PUSH data).
Divergence history: truncated-code paths, CREATE-time code ending mid-PUSH.

## PC / MSIZE / GAS (0x58-0x5A)
Frame metadata reads. GAS in particular is a common divergence source — off-by-one
on when gas is charged vs returned.

## JUMPDEST (0x5B)
Valid jump target marker. Divergence-sensitive only through analysis bugs.

## TLOAD / TSTORE (0x5C, 0x5D)
Cancun (EIP-1153). Transient storage: per-transaction, per-account, cleared at
tx end. Divergence history: visibility across CREATE/CREATE2 frames, retention
after REVERT, DELEGATECALL inheriting caller's transient store.

## MCOPY (0x5E)
Cancun (EIP-5656). Memory-to-memory copy. Divergence: overlap handling
(forward vs reverse copy), zero-length semantics, memory expansion at dest.

## PUSH0 (0x5F)
Shanghai (EIP-3855). Push zero to stack, 2 gas. Replacement for PUSH1 0.
Divergence: pre-Shanghai execution should treat 0x5F as invalid opcode.

## PUSH1..PUSH32 (0x60-0x7F)
Push N-byte immediate. Frontier (except PUSH0 above). Divergence: truncated
code (immediate ends after code boundary) — clients must pad with zeros.

## DUP1..DUP16 (0x80-0x8F), SWAP1..SWAP16 (0x90-0x9F)
Stack manipulation. Frontier. Zero divergence surface.

## LOG0..LOG4 (0xA0-0xA4)
Emit log with 0-4 topics. Frontier. Divergence rare.

## CREATE (0xF0)
Create contract. Address = keccak(rlp([sender, nonce]))[12:]. Divergence:
init-code revert handling, nonce increment ordering, collision with existing
account, and post-EIP-3541 reject-code-starting-with-0xEF.

## CALL / CALLCODE (0xF1, 0xF2)
External call. EIP-2929 warm/cold access split applies to target address.
Divergence: stipend (2300 gas if transferring value), value transfer failure
behavior, gas-forwarding (63/64 rule, EIP-150).

## RETURN (0xF3)
Halt with return data. Frontier. Rare divergence.

## DELEGATECALL (0xF4)
Homestead (EIP-7). Runs callee code in caller's storage context. Divergence
history: transient-storage inheritance (EIP-1153), balance-in-context bugs,
and when banned opcodes differ per fork.

## CREATE2 (0xF5)
Constantinople (EIP-1014). Deterministic address = keccak(0xFF ++ sender ++
salt ++ keccak(init_code))[12:]. Divergence: salt encoding, init_code hash
when init_code reverts mid-way, and EOF-era rejection of 0xEF prefix.

## STATICCALL (0xFA)
Byzantium (EIP-214). Like CALL but forbids state-changing ops inside (SSTORE,
LOG*, CREATE*, SELFDESTRUCT, CALL with value). Divergence: which ops count as
"state-changing" across forks.

## REVERT (0xFD)
Byzantium (EIP-140). Halt, refund remaining gas, return data. Divergence:
revert-in-create, revert-after-value-transfer (value should roll back).

## INVALID (0xFE)
Consumes all remaining gas, reverts state. Frontier (by convention — no gas
refunded). Divergence: treatment of unallocated opcodes (each client's
"undefined-opcode" handling should match INVALID semantics).

## SELFDESTRUCT (0xFF)
Historically transferred balance to beneficiary and deleted account.
EIP-6780 (Cancun): only destroys if called in same tx as CREATE. Divergence
hot-spot: pre/post EIP-6780 semantics, beneficiary == self, zero-balance
case, SELFDESTRUCT inside STATICCALL (should revert).

## Precompiles (addresses 0x01-0x0A...)

- 0x01 ECRECOVER: signature recovery. Divergence on malformed inputs (v not
  in {27, 28}, high-s malleability, empty input).
- 0x02 SHA2-256: standard hash.
- 0x03 RIPEMD-160: padded to 32 bytes. Padding direction divergence historically.
- 0x04 IDENTITY: echo input. No divergence.
- 0x05 MODEXP: arbitrary-precision modular exponentiation. EIP-2565 reshaped
  gas. Divergence: zero-length modulus (revm returned empty, geth returned
  0x00), huge inputs, and gas-charging edge cases.
- 0x06 BN_ADD, 0x07 BN_MUL, 0x08 BN_PAIRING: alt_bn128 curve ops (EIP-196,
  EIP-197). Divergence on malformed points and pairing with empty input.
- 0x09 BLAKE2F: (EIP-152). Rounds parameter must fit in uint32.
- 0x0A POINT_EVALUATION: (EIP-4844, Cancun). KZG proof verification.
  Divergence on malformed KZG inputs.
