# GPT-Driven H3 Iteration State

This file is the durable handoff/source-of-truth for autonomous GPT iteration on `gpt-test-branch`.

**Update rule:** after every meaningful finding, architectural decision, proven probe, failed approach, focused code change, or new next step, update this file. New chats/automations should read this file before making architectural changes.

## Architectural invariants

Keep the semantic architecture simple:

- **ARC:** create -> validate -> repair -> validate until valid.
- **BEATS:** create -> validate -> repair -> validate until valid.
- Do not add separate semantic enrichment, coverage, claim, state-preparation, effect-proof, or audit pipelines when the responsibility belongs inside ARC or BEATS.
- Python owns deterministic structure/data-integrity checks and deterministic arithmetic. It should not independently interpret arbitrary English semantics.
- Canonical persistent state is Python-owned. ARC required_events carry typed `state_effects`; Python applies those effects only after a beat validates.
- The proven single-beat validator remains conceptually frozen: one beat at a time, validity-first, with story/phase/previous beat/canonical state/current job/next job/candidate beat context.
- Fix observed acceptance failures, not hypothetical ones.

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

Source requirement:

> The majority of the film is Amy killing zombies as they try and attack her.

A finalized 8-beat acceptance ARC allocated actual zombie-killing jobs only to Beats 4-7: **4/8**, which is not a majority.

The original ARC validator incorrectly accepted that allocation.

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

1. Let the currently queued local regression/acceptance jobs finish.
2. Confirm the deterministic majority-evidence tests pass locally.
3. Run Amy acceptance again on the latest `gpt-test-branch`.
4. Verify the accepted ARC contains at least 5/8 actual zombie-killing required_event jobs.
5. If it does, inspect the resulting beats/prompts and fix the **next earliest real acceptance failure only**.
6. Update this file with the result before moving on.

## Recovery instructions for a new chat/context

Read this file first, then inspect:

- latest commit on `gpt-test-branch`;
- newest entries under `bridge/results/` on `gpt-runtime`;
- newest queued jobs under `bridge/jobs/`.

Do not restart architectural brainstorming from scratch. Treat the invariants, proven probes, failed approaches, and current earliest failure above as the working checkpoint unless newer repo evidence supersedes them.
