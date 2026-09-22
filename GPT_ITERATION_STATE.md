# GPT-Driven H3 Iteration State

## END GOAL — DO NOT LOSE THIS

The end goal of this project is:

> **Take a user-authored story input (whether free-flow prose like `story.txt` or a somewhat more structured story format) and automatically produce MiniMax H3-ready prompts that are semantically and structurally equivalent in quality to the hand-authored GOLD prompts in the acceptance suite.**

Everything in the ARC, BEATS, state, continuity, validation, repair, and formatting pipeline exists only to serve that transformation.

The system should therefore be judged by the final generated H3 prompts, not by whether intermediate ARC/beat JSON looks elegant in isolation.

The acceptance/gold prompts are the behavioral target. **No current intermediate representation or pipeline stage is sacred.** ARC, BEATS, canonical state, continuity stages, validators, repair loops, or the entire current decomposition may be changed, collapsed, replaced, or removed if evidence shows a different architecture gets from the user input to gold-quality prompts more reliably.

The only durable product contract is:

`LOW-BURDEN STORY INPUT -> GOLD-QUALITY FINAL H3 PROMPTS`

"Story input" may be free-flow prose such as `story.txt` or a modestly structured format if that materially improves reliability, but the user must **not** be required to manually author pages of planning metadata, arc definitions, beat-by-beat instructions, continuity bookkeeping, state transitions, or prompt engineering.

The current pipeline:

`STORY INPUT -> ARC -> BEATS -> DIRECTOR/CONTINUITY -> FINAL H3 PROMPTS`

is a **working hypothesis**, not the end goal and not an architectural invariant. Keep using and improving it while acceptance evidence says it is productive. If repeated evidence shows that this decomposition cannot reach the gold prompts reliably, redesign it—even radically.

A successful system should let the user describe the story with reasonable author effort, run the program, and receive the equivalent of the hand-authored gold prompt sequence automatically.

This file is the durable handoff/source-of-truth for autonomous GPT iteration on `gpt-test-branch`.

**Update rule:** after every meaningful finding, architectural decision, proven probe, failed approach, focused code change, or new next step, update this file. New chats/automations should read this file before making architectural changes.

## Current working architecture — PROVISIONAL, NOT SACRED

For the **current implementation**, keep the semantic architecture simple unless acceptance evidence justifies changing it:

- **ARC:** create -> validate -> repair -> validate until valid.
- **BEATS:** create -> validate -> repair -> validate until valid.
- Do not casually add separate semantic enrichment, coverage, claim, state-preparation, effect-proof, or audit pipelines when the same responsibility can live inside the current ARC or BEATS loop.
- Python should own deterministic structure/data-integrity checks and deterministic arithmetic rather than pretending to understand arbitrary English semantics.
- In the current design, canonical persistent state is Python-owned; ARC required_events carry typed `state_effects`; Python applies those effects only after a beat validates.
- The proven single-beat validator is a strong known-good component and should not be disturbed without evidence that it is blocking the final goal.
- Fix observed acceptance failures, not hypothetical ones.

**These are not permanent product constraints.** They describe the best current implementation we have. If the ARC/BEATS architecture itself becomes the demonstrated reason the system cannot reproduce the gold prompts, replace it. KISS means choosing the simplest architecture that actually reaches the end goal, not preserving today's architecture forever.

## Bridge workflow

- Code branch: `gpt-test-branch`
- Mailbox/results branch: `gpt-runtime`
- Local bridge: `tools/chatgpt_llama_bridge.py`
- The bridge can run allowlisted local unit tests, acceptance runs, and llama.cpp probes, then publishes results to `gpt-runtime`.
- Do not require the user to shuttle logs when results are available under `bridge/results/`.

## Known-good checkpoints

- `77e94e340889dc69072549da1fb6e6f704833f66` — ARC/beat logic checkpoint before bridge production changes.
- `d606f11a84c6b7498e7733649f9953100c98e9ab` — production bridge checkpoint.
- `38b028281377dfdbb4ed1f741066a52a4f9c8747` — normalized ARC prompt regression assertions.
- `cd3f1c5858b321e0227a8035e38124c5c0afc61f` — added explicit source-emphasis instructions to ARC planning/validation.
- `d88bd0674cbcdab7ef5a22f32ef55e6cb56ec6fc` — deterministic ARC majority evidence enforcement.
- `f853902da5b93b05a6db30f8b4d2e02556132321` — regression tests for deterministic ARC majority enforcement.

## Acceptance progress that is now proven

The Amy zombie-house acceptance story has progressed through several earlier failures:

1. Breakfast/source setup coverage is preserved.
2. Packed Beat 2 correctly contains the zombie window break plus Amy rushing Will/Amber to the basement and locking the door.
3. Retrieval + equipping can be packed into one ARC/beat job when necessary.
4. ARC regression tests were passing before the current majority-evidence work.
5. Full prompt-generation acceptance reached all 8 segments successfully at `cd3f1c...`.

## Current earliest real failure

The deterministic majority-evidence change succeeded at forcing five materially zombie-killing beats in the next Amy acceptance run, but it exposed a more important gold mismatch: **the explicit breakfast setup disappeared entirely.**

Acceptance `run-acceptance-amy-majority-016` produced an ARC beginning with the zombie breaking the kitchen window; the source's explicit ordinary action "Amy ... cooking breakfast for her young kids" was absent. Segment 1 therefore began with the zombie attack instead of the locked gold's ordinary breakfast scene.

The gold benchmark also clarified the correct compression direction: the gold keeps breakfast/setup early and lets Beat 8 begin with the final zombie falling before transitioning into the family reunion. Therefore, when emphasis and beat budget conflict, the system should preserve early explicit source stages and bundle the final emphasized action with its immediate aftermath/resolution when appropriate, rather than delete setup.

## Latest coverage-priority finding

Targeted probes after `run-acceptance-amy-majority-016`:

- `arc-coverage-emphasis-validator-probe-018`: when explicitly told to validate source coverage before other concerns, Mistral correctly rejected the bad ARC and identified **"Amy is cooking breakfast for her young kids"** as the first missing source action.
- `arc-coverage-emphasis-create-probe-017`: creation preserved breakfast when explicitly told never to sacrifice source coverage, but still did not reliably satisfy the majority arithmetic on its own. This reinforces the current split: semantic matching by the LLM, deterministic threshold counting by Python.

Focused production changes:

- `38b147790c99fbfabe0d4c7629476d5441eaa157` — make source coverage the first ARC semantic check and instruct planning to preserve all explicit source stages before satisfying emphasis through adjacent bundling.
- `428a843b4d6cc7f6e47643d16690756bc363926e` — regression-test that source coverage appears before source emphasis in the ARC validator prompt.
- `run-tests-arc-coverage-priority-019` passed **8/8** ARC structural/semantic prompt regressions.
- Full Amy acceptance `run-acceptance-amy-coverage-priority-019` is queued/running. Its result determines the next real failure.

## What did NOT work

### Stronger natural-language arithmetic inside the ARC validator

Probe: `arc-emphasis-count-probe-011`

Even with the rule explicitly stating that majority requires `K * 2 > N`, and that 4/8 is invalid, Mistral returned the bad 4/8 arc as valid.

### Forced silent per-beat classification plus arithmetic

Probe: `arc-emphasis-classify-probe-012`

Even when instructed to classify every event X/NOT-X and require at least 5/8, Mistral still returned valid.

**Conclusion:** do not rely on this model to perform the final majority arithmetic/validity decision reliably.

## What DID work

### Semantic beat matching

Probe: `arc-emphasis-beatlist-probe-013`

For the bad ARC, Mistral correctly returned:

`matching_beats: [4, 5, 6, 7]`

### Valid-majority semantic evidence

Probe: `arc-majority-valid-evidence-probe-015`

For a valid allocation, Mistral correctly returned five matching kill beats:

`[3, 4, 5, 6, 7]`

### Architecture decision from those probes

Keep semantic interpretation inside the existing single ARC validator, but have it return **evidence**:

`majority_checks: [{ source_requirement, matching_beats }]`

Then Python performs only deterministic validation/counting:

- validate beat numbers are integers, unique, and in range;
- if source explicitly contains `majority`, require evidence;
- reject when `len(matching_beats) * 2 <= total_segments`.

This respects KISS: it is still one ARC validation pass, not a new semantic subsystem. The LLM decides which beats semantically match; Python only does arithmetic.

## Current implementation state

At `d88bd067...`:

- ARC validation response schema gained `majority_checks`.
- ARC validator prompt requests one evidence entry per explicit source sentence using `majority`.
- `parse_macro_arc_validation_result(...)` validates the evidence structurally and deterministically enforces the majority threshold.
- `request_macro_arc_validation` requires majority evidence when the source contains the word `majority`.

At `f853902...`:

- tests cover bad 4/8 -> invalid;
- good 5/8 -> valid;
- missing majority evidence -> parser rejection;
- validator prompt -> requests matching beats from actual required_events.

## Important caution

The evidence LLM can undercount individual matches (one probe returned [4,5,6] instead of [4,5,6,7]), but for the observed bad 4/8 case it still produces evidence below the threshold. Continue evaluating false negatives/false positives through acceptance before generalizing beyond the observed `majority` failure.

Do not build a generalized relative-emphasis subsystem for `most`, `half`, `briefly`, etc. until an actual acceptance failure requires it.

## Immediate next steps

1. Read `run-acceptance-amy-coverage-priority-019` when it lands.
2. Verify Beat/Segment 1 restores the explicit ordinary breakfast setup while the accepted ARC still satisfies the current majority evidence check.
3. Compare generated prompts against the locked gold in chronological order and identify the **earliest semantic mismatch**.
4. Fix that observed mismatch only; do not optimize later beats first.
5. Update this file again with the acceptance outcome and next blocker.

## Recovery instructions for a new chat/context

Read this file first, then inspect:

- latest commit on `gpt-test-branch`;
- newest entries under `bridge/results/` on `gpt-runtime`;
- newest queued jobs under `bridge/jobs/`.

Do not restart architectural brainstorming from scratch. Treat the proven probes, failed approaches, current implementation, and earliest failure above as the working checkpoint unless newer repo evidence supersedes them. Preserve the **input/output product contract**, not the current internal decomposition: if evidence eventually shows ARC -> BEATS -> prompts is the wrong route to gold-quality prompts, architectural replacement is explicitly allowed.
