# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active development branch: `gpt-arc-refresh`

Historical experiment logs, superseded failures, probe batches, and old acceptance chronology are archived in `docs/HANDOFF_OLD.md`.

## Current architecture

The current path is source-span / chapter-first.

- `story.txt` is authoritative.
- Python owns exact source spans, chapter boundaries, beat arithmetic, typed canonical state, refresh scheduling, and deterministic acceptance rules.
- The local GPT-OSS 20B performs narrow semantic generation/extraction only.
- Prefer deterministic Python whenever the required fact is already represented structurally.
- When fuzzy language must be interpreted, use the smallest possible extractor with a tiny enum/result and let Python make the validity decision.
- Do not add parallel semantic pipelines. Keep repair inside the existing planning / beat / Director loops.
- Repairable source-span/state-extractor failures stay on the source-span path. Do not fall back to the legacy ARC architecture.
- Fix the earliest demonstrated failure from logs/acceptance runs before speculative later problems.

## Model / prompt constraints

The final system must run on local ~20B-class models, not GPT-5.6 Sol.

Treat the local model as comparatively instruction-fragile:

- prompts should be short, concrete, and explicit;
- avoid asking one call to infer several semantic facts at once;
- narrow extraction + Python comparison has been substantially more reliable than broad prose validators;
- do not solve a deterministic state contradiction by stacking more prose into a large validator.

GPT-20B runtime context is now **8192 tokens** in production code.

Commit `819d613b51d0baee773f2246e2c0cf946f068056` changed:
- `LLM_CONTEXT_TOKEN_BUDGET`: 6044 -> 8192
- default `call_llm(... max_tokens=...)`: 8000 -> 8192

The existing safety reserve and input-token subtraction remain, so the actual completion allowance can still be below 8192 when the prompt itself consumes context.

## Repository-content rule

The public repository must remain SFW.

- Runtime user stories may contain arbitrary content.
- Committed source, prompts, tests, fixtures, comments, and documentation must use SFW/generic examples.
- Keep state/extractor rules domain-generic.

## Current continuity/state invariants

These are active architectural behavior, not historical experiments:

- Python-owned typed effects override conflicting prompt-derived continuity.
- Canonical containment/location changes clear stale transient pose/topology/spatial relationships that depended on the old location.
- Clothing must not be duplicated as generic equipped item state.
- Explicit broken/shattered barrier-like entities use `set_barrier_state=broken`, scoped to the specific barrier entity rather than every barrier in the source unit.
- Generic barrier identity may be bound deterministically to an unambiguous containment destination.
- Closed/locked boundaries cannot be crossed unless the active typed effects authorize that transition.
- If a release temporarily opens/unlocks a barrier but no typed barrier effect changes its persistent state, the barrier must end in its canonical opening state.
- Reapplying an irreversible typed end state to a target that already has that state must be rejected.
- Final H3 timestamp validation rejects malformed, out-of-range, and nested/bracketed timestamp wrappers.

## Current generation workflow

Two unattended modes now exist.

### `--generate-prompts N`

Generates the semantic work and final H3 prompts without sending anything to ComfyUI.

It:
- generates arc/source-span planning, beats, Director RAW, continuity, and final H3 prompts;
- writes `generated_prompts.txt` incrementally;
- stores the render metadata required for later rendering;
- reuses already-written prompt prefixes and existing beat plans during ordinary recovery when valid.

### `--generate-from-prompts`

Loads `generated_prompts.txt`, skips all LLM planning/generation, renders the saved prompts through the normal ComfyUI workflow scheduling, and stitches the clips.

Workflow selection must continue to preserve initial vs append vs chapter/numeric refresh behavior.

Relevant implementation commits:
- `0e9399dd32d3858c63fa8190bbe23adb871dd0fc`
- `f452ebd0e9eb14364a0ca0366fb89d22aa6fc0d6`
- `355c2f71568586ba44c9f7c17faa910530cc8f88`
- `c928a912e2a28ecb4fd5d928a88ab3bd5ce0caec`
- `5c66c8efb27223ddd679a323df8ae36faa738315`

## Latest verified acceptance state

Acceptance `2440` verified that:
- authoritative containment no longer carries stale cross-location physical relationships forward;
- the final release can temporarily open/unlock the basement boundary and correctly restores its locked final state.

It then exposed malformed/nested Request-2 timestamp wrappers. Those were fixed by:
- `5d4f5c37e1f54b925c568db6e919e69113ca0233` — reject bracketed/nested timestamp wrappers;
- `70846f73e9b904544861bb66ed121de7e325c834` — regression coverage.

`tests-2441` showed the new split-generation regressions passing; its only failure was a stale test fixture, corrected by:
- `72796c243afaf6a300e82d766fbc87ef6204c93a`.

## Current active failure / latest fix

A user run became trapped on Segment 4.

Observed behavior:
- Director Request 1 repeatedly failed the closed-boundary traversal check.
- After exhausting the local 3-attempt Director retry budget, application recovery resumed from the same Segment-4 planning checkpoint.
- Because the Beat/typed-state contract itself could be incompatible with Director validation, replaying the same checkpoint could loop indefinitely.
- One retry also showed RAW creating a durable terminal target-state change while the assigned typed end state was empty, confirming this can be a planning-contract problem rather than merely a bad Director sample.

Latest production fix:

`fe4254683e3ce1507ebf2117505bd425e490800e`

When Director Request 1 exhausts its local retry budget:
- recovery escalates back to planning instead of replaying the same later-segment checkpoint forever;
- in `--generate-prompts` mode, Segment-1 recovery forces a fresh beat plan so a poisoned Beat/typed-state contract can be regenerated;
- the application's recover-forever policy remains, but it can now change the plan rather than repeat an impossible segment indefinitely.

## Next checkpoint

Run the focused regression suite and then a fresh end-to-end `--generate-prompts` / acceptance run on the current branch.

Verify, in this order:

1. The GPT-20B call path is using the 8192-token software context budget rather than the obsolete 6044 cap.
2. Director retry exhaustion no longer loops forever on the same Segment-N checkpoint.
3. Exhaustion escalates to planning and produces a fresh beat/typed-state plan.
4. Previously verified continuity/barrier/timestamp fixes still hold.
5. Identify the **earliest new real failure** from that run and fix only that failure.

Do not reopen already-verified historical failures unless a fresh run actually reproduces them.


## 2026-09-28 — acceptance 2445 + GPT formatter timestamp wrappers

- `tests-2444` passed 51/51 (1 skipped) across prompt-generation mode, requested prompt regressions, and minimax integration coverage.
- `acceptance-2445` completed all 8 segments with canonical timestamp syntax throughout, so the parenthesized timestamp failure from `acceptance-2443` did not reproduce on the next stochastic run.
- Nevertheless, `acceptance-2443` demonstrated a real GPT-OSS formatter quirk: Request 2 could emit wrappers such as `(At 00:01.500, )` around otherwise valid timestamps, and the shared timestamp checker could see the valid inner token.
- Architectural rule: model-specific representation cleanup belongs in the model formatter. Shared orchestration should enforce the final H3 contract, not accumulate GPT-specific punctuation repair.
- Commit `b9b5297509bc25f5cc2f30846e65eddcaef58e4a` adds GPT-only deterministic unwrapping for parenthesized or bracketed local timestamps before canonical normalization.
- Commit `b6b0ee96a254460277bb6fb11d470369bf3f9c1c` adds formatter regression coverage for both wrapper forms.
- `acceptance-2445` also showed one `Added States:` string visually interleaved inside the printed Segment-6 H3 block. This has not yet been proven to be part of the actual prompt object rather than concurrent console-output/capture interleaving, so do not patch it until a direct prompt-object or repeated acceptance result proves the defect.
- Next checkpoint: run formatter/regression tests, then fresh full acceptance. Confirm wrapped timestamps are normalized by `gpt_formatter.py`; if `Added States:` appears again, trace its origin before changing production behavior.
