# Modifying the FuzzyVM

### Preface

This actually doesn’t have much to do technically with the blockchain, so we don’t need to use tools like foundry or concern ourselves with addresses and RPC calls. 

This entirely focuses on creating test cases for different implementations of the EVM to see if it can cause any discrepancies on how they handle it.

## **What the model should do**

- Pick or propose **strategy sequences** (e.g., more calls + storage + jumps).
- Suggest **targeted scenarios** (e.g., edge gas, precompile boundary sizes, deep call chains).
- React to feedback (“this area found divergences, explore neighbors”).

## **What to train (or condition) on**

Best results come from a **mixture**:

- **Ethereum state tests** (GeneralStateTests): strong examples of structured semantics.
- **Historical client-diff bugs / consensus incidents**: teaches high-value failure patterns.
- **Your own fuzz outputs** (`out/`, crashes, minimized repros): most aligned with your pipeline.
- **EIPs/spec excerpts + opcode docs**: good for semantic grounding (especially fork-specific behavior).
- **goevmlab differential results**: pairs “input pattern -> disagreement/no disagreement”.

NOTE: I’m gonna be searching for some of these to train on

## **Best practical approach**

Start with **RAG + prompt templates** before heavy training:

- Retrieve similar prior tests/bugs by topic (CALL, CREATE2, warm/cold access, precompiles, EOF, etc.).
- Ask the model to output your **structured DSL** (strategy plan), not test JSON/raw bytecode.
- Validate and execute through FuzzyVM/goevmlab.
- Log outcomes to build a dataset for later fine-tuning.

## **If you do train/fine-tune later**

Train for a supervised target like:

- Input: fork + recent coverage gaps + recent divergences + objective
- Output: strategy plan DSL (steps, weights, constraints, seed hints)

Then optionally add ranking/reward:

- Reward higher for plans that produce **new coverage** or **cross-client disagreement**.
- Penalize invalid/unproductive plans.

---

## **Recommendation**

- **Phase 1 (best ROI):**
    - Use a strong existing LLM.
    - Add **RAG** over EVM tests, EIPs, past diffs, and your fuzz outputs.
    - Force output into your **template DSL** (JSON schema + validator).
- **Phase 2:**
    - Add light **fine-tuning** (or preference tuning) only if Phase 1 hits a ceiling.

## **Practical stack**

- **Model:** hosted frontier/open model. (qwen is what we were thinking of
- **RAG index:** EVM tests + EIPs + bug repros + your `out/` + minimized failures.
- **Output contract:** strict JSON template schema.
- **Scoring loop:** reward templates by coverage novelty, differential mismatches, and validity rate.

## Datasets:

- https://github.com/ethereum/tests (The basic EVM test cases repo)
- https://github.com/ziyadedher/evm-bench (Consider this, is more focused on performance and deterministic workloads)
- https://huggingface.co/datasets/andstor/smart_contracts (Legitimate smart contracts, these aren’t test cases themselves, but can help in creating realistic flow to reach other parts that might break)
- WE CAN CREATE A DATASET FROM RUNNING OTHER EVM FUZZERS. Might have to check on this one tho, but if we can find more opensource differential fuzzers, maybe we can use their test cases?) (we could ask Thanos for this)

## Resources:

- Basics we are implementing / modifying
    - https://github.com/MariusVanDerWijden/FuzzyVM (added to repo)
    - https://github.com/holiman/goevmlab (added to repo)
    - https://mariusvanderwijden.github.io/blog/2021/05/02/FuzzyVM/
- Advanced / More reading
    - https://r9295.github.io/posts/differential-fuzzing-accross-languages/
    - https://github.com/R9295/autarkie (The Fuzzer Mentioned in the previous bullet point)
    - https://dl.acm.org/doi/abs/10.1002/smr.2556 (EVMFuzz proposal from some year, its mentioned a bunch in different places)
    - https://github.com/ziyadedher/evm-bench (New possible harness that we can check out in case we are not satisfied with goevmlab)
- Absolutely IMPORTANT
    - https://arxiv.org/pdf/1903.08483 (The paper that explains the entire process super well, we are basically doing all of this except we are making the LLM generate us strategies that choose the seed contract route to go down)
        - Our strategy template approach differs by telling the generator how to string bytecode togethe**r,** which kinds of program-building steps to prefer (opcode vs call vs jump vs storage, etc.) and with what constraints/fork/seed.