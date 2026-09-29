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


## 2026-09-28 — acceptance 2451 formatter follow-up

- `tests-2450` imported successfully after the prior regex syntax fix and ran 54 tests, but the new timestamp-wrapper regression failed because the Python raw regex accidentally contained literal double backslashes, so it did not match real `(At ... )` / `[At ... ]` text.
- `acceptance-2451` completed all 8 segments. Its final prompts used canonical timestamps, but Segment 4's captured `generated_h3_prompt` ended with a literal `Added States:` line. This proves the earlier 2445 observation was not merely console interleaving.
- Both defects are GPT-OSS representation quirks and belong in `gpt_formatter.py`, not shared orchestration.
- Commit `052e11f8e7af37437e95c81ea82f81445af56dbb` fixes the wrapper regex and strips a trailing `Added States:` control label from GPT-rendered fields.
- Commit `7472eec0faf95350560c5acae6f365c65b5e7758` adds regression coverage for the control-label cleanup.
- 2451 also exhausted Director Request-1 retries once at Segment 4 and correctly escalated to replanning, after which the full run completed. Treat that as recovered model variance unless fresh acceptances show a consistent pattern.


## 2026-09-28 — Director-only test path and retry recovery

- Repeated late-segment Request-1 failures were wasting full ARC/BEATS regeneration time because exhausted Director retries triggered the recovery supervisor's plan invalidation path.
- `DIRECTOR_RAW_SCENE_ATTEMPTS` is now 5 (was 3).
- New `--director-only` mode:
  - requires existing valid `story_arc.json` and `beats.txt`;
  - never calls ARC/BEATS generation or repair;
  - implies prompt-generation test mode, so ComfyUI is never called;
  - runs the normal per-segment Director Request 1 -> Request 2 -> formatter/final-H3 validation path;
  - on exhausted Director retries, recovery resumes from the last committed segment and does not invalidate/rebuild the frozen plan.
- Acceptance runner now accepts `--director-plan-dir PATH`, copying a frozen `story_arc.json` + `beats.txt` into its isolated workspace before invoking `minimax.py --director-only`.
- Bridge `run_acceptance` jobs may set `director_plan_job` to a prior acceptance job ID. The bridge reuses saved plan files when available; for older jobs such as `acceptance-2451`, it can materialize the embedded `generated_story_arc` and `generated_beats_text` from `acceptance_run.json` into a local temporary directory. The actual runtime story/plan is not added to the public code branch.
- Full acceptance artifacts now preserve `story_arc.json` and `beats.txt` for later Director-only runs.
- Mailbox queue was purged before this change; no unprocessed bridge jobs remain.
- Relevant commits: `bed344efb92d54ef35b8ffacc77be2519f098a6d`, `f77774decddde57c313ce33b9fb55e0314e65174`, `c8eccde5fbc8a5a1d836cfcbf2b2965e90d895dd`, `c62550df1dfb3cb297e7355f007592bbe5bba074`, `b15bca3e89de32db38c1535ff14150a53bdeeea2`, `d264644d405a8d913b0eab7bdc0978df964a52d7`.
- Next action: pull `gpt-arc-refresh`, restart the bridge, then run targeted tests and a Director-only acceptance using `director_plan_job: "acceptance-2451"` before doing another full ARC/BEATS acceptance.


## 2026-09-28 — Director-only acceptance 2457 findings

- `tests-2456` passed: 54/54 targeted regression tests.
- `acceptance-2457` completed, but exposed a flaw in the frozen-plan harness: `story_arc.json` was copied without a matching `.sha256` sidecar, so normal `load_story_arc()` rejected it as a stale cache. The run therefore did not exercise frozen typed state effects even though `beats.txt` was reused.
- Director-only mode now parses the explicitly supplied frozen `story_arc.json` directly and validates its declared beat count/schema without using the normal story-source cache hash gate. It still fails closed if the supplied frozen arc is invalid.
- Prompt-only checkpoints now persist the exact assembled `h3_prompt` per completed segment. The acceptance runner prefers that exact field over parsing console text, avoiding false prompt contamination from concurrent/asynchronous stdout such as `Added States:`.
- The GPT formatter's trailing `Added States:` cleanup regex also had accidental literal backslashes and is now corrected.
- Stale `tests/test_director_retry.py` helpers were updated to the current five-field Request-1 completion response and current containment prompt wording.
- Relevant commits: `8c494f0e4760f686ffbe468e32408346f1e0d13d`, `3a6d83ba5245ea2a227609bd8582963859244116`, `9f16c086213e0f179d2e718c34b9f4b154739ba2`, `a4d035f09e007c4bdc63d3e5e78f0b46e0d0088c`.


## 2026-09-28 — Director-only acceptance 2459

- `acceptance-2459` is the first clean frozen-plan Director-only acceptance using the saved arc's typed state effects.
- Segment 2 containment now behaves correctly: Will/Amber end inside the basement while Amy remains outside in the kitchen.
- Exact checkpointed H3 prompts contain no `Added States:` contamination; prior appearances inside acceptance reports were caused by stdout scraping/interleaving.
- Earliest remaining real prompt defect: Segment 5 authorizes only a non-terminal arm sever + limb disposal, but Request 1 added `zombie remains motionless on floor`, inventing a terminal/incapacitated outcome not assigned by source.
- Rather than add another semantic pipeline/call, the existing independent Request-1 completion validator now explicitly rejects stronger terminal outcomes when SOURCE authorizes only non-terminal injury/damage/change.
- `tests/test_director_retry.py` fixtures were also updated to emit structurally valid timed RAW SCENEs with a trailing `End continuity state:`, matching the current production Request-1 contract instead of failing for obsolete fixture shape.
- Relevant commits: `fcf95ee5116ae698735f0c214b9d8cdf14565a21`, `f7f0ad4a8dd5bbd1e17cc955d7d0e6cbe534a653`.

## 2026-09-28 — acceptance 2461 + regression cleanup

- `tests-2460` exposed 13 failures (79 passed). Most Director failures were not independent production defects: legacy unit-test bundles supplied derived beat text but no authoritative `assigned_source`, while the newer independent completion verifier still made an extra semantic LLM call. That exhausted mocked response queues and obscured the formatter failures.
- Commit `2e08b3acb708cf0af85a94ab4a32f1978b7e3bf4` fixes the GPT-only wrapped-local-timestamp regex. The previous raw regex still contained literal double escapes and failed to unwrap `(At ... )` / `[At ... ]` reliably.
- Commit `2545ab269bd4df67aa928b95e1dd029a44660542` makes the independent Request-1 semantic completion verifier explicitly source-authority based: it runs only when both CURRENT BEAT and authoritative `assigned_source` are present. Legacy/unit callers without source retain structural + self-reported completion checks; production Director bundles continue through the independent verifier.
- `acceptance-2461` completed all 8 frozen-plan Director segments. The Segment-5 unassigned terminal outcome from 2459 did not recur, confirming the terminal-scope prompt fix moved the failure downstream.
- Do not treat later prompt-quality observations from 2461 as the next production target until the targeted regression suite is green again.
- Next checkpoint: run the same targeted Director/formatter/prompt-generation tests. If green, run another Director-only acceptance against the frozen `acceptance-2451` plan and identify the earliest remaining real prompt defect.

## 2026-09-28 — targeted baseline green; Segment 2 crossing ambiguity

- `tests-2469` is green: 90/90 targeted tests passed (8 subtests passed).
- Re-review of `acceptance-2465` found the earliest remaining production prompt defect in Segment 2. RAW used `They descend the kitchen stairs` after Amy grabbed Will and Amber, which can visually include Amy crossing into the basement even though the authoritative typed end state moves only Will and Amber there and leaves Amy outside to lock the door.
- The independent completion verifier received the correct typed end state and participant-scope rule, but GPT-OSS 20B rationalized `They` as only Will and Amber and returned valid.
- Commit `0f33cd7c7d02ffc2dd305adb618056b2dd1f3ef7` tightens only the existing participant-scope rule: collective crossing language such as `they`, `we`, `all`, or `the group` is invalid when it could include an unauthorized mover/helper; RAW must explicitly name authorized crossers.
- Commit `1c8344e36f727a668a4660a891926ed5eb4debad` adds a regression assertion for that prompt rule.
- Next checkpoint: rerun the targeted tests, then rerun Director-only acceptance against the frozen `acceptance-2451` plan. The expected Segment-2 repair is explicit wording such as `Will and Amber descend/enter the basement` while Amy remains outside.

## 2026-09-28 — Director structural-geography tightening

- The Segment-2 `They descend the kitchen stairs` wording in `acceptance-2465` was not present in the frozen beat plan; Request 1 invented `kitchen stairs` as local staging.
- Commit `e92e4d8d51910a3a25cdb828ec933853165957a1` tightens the existing RAW Director prompt: do not invent structural geography/travel routes (stairs, hallways, corridors, extra doors, ladders, elevators, rooms, floors, tunnels, gates, passages). If a route is unspecified, move named subjects directly toward/through the established destination boundary without defining how the building connects.
- The same commit tightens the existing Request-1 completion verifier to reject invented route-defining structures. This stays within the existing Director generate/verify retry loop; no new semantic stage was added.
- Commit `c1c07ca7ee8338737de13e8e024c476551ad99a0` adds regression coverage for both prompt constraints.

## 2026-09-28 — deterministic Director route/crossing guards

- `acceptance-2473` proved the 20B model can ignore explicit semantic rules: it generated `Amy, Will, and Amber rush down the kitchen stairs into the basement`, then the independent verifier incorrectly rationalized that only Will and Amber crossed.
- Root cause included a contradictory Python-added final-side note allowing temporary unauthorized crossing if the subject returned before the end. That loophole was removed.
- Commit `67b07da70d7ac6e89ac076ab8892212703b15b6d` adds deterministic Request-1 guards inside the existing acceptance gate:
  - reject route-defining structures that appear in RAW but are absent from source/beat/opening continuity;
  - reject an explicitly named subject with NOT_AT_DESTINATION topology when RAW states that subject moves into/through/to the typed destination.
- These are deterministic lexical/state checks, not a new semantic pipeline. The existing local-LLM completion verifier remains for broader source completion.
- Commit `ab8418996d8b887bc4f56b9a814a272f4d613d3a` adds focused regression tests and fixes the geography test to use `DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE`.

## 2026-09-28 — Segment 2 cleared; Segment 4 opening-held prop contradiction

- `tests-2476` is green: 94/94 targeted tests passed.
- `acceptance-2477` finally clears Segment 2: no invented route geometry; Amy steps back, Will/Amber enter the basement, Amy remains on the kitchen side, and the basement door ends locked.
- Segment 3 is acceptable.
- Earliest remaining production defect is Segment 4: RAW begins with Amy already holding pistol + katana, then later says she `pulls pistol from holster`, inventing a holster and reacquiring an item already held in canonical opening continuity.
- Commit `57e4e078d88171f22e4f90fdbf2468f26bf478a5` extends the existing deterministic object-state gate to compare RAW against structured `registry_state.held_props`; an opening-held item cannot be reacquired unless RAW explicitly releases/stows it first.
- Commit `7a7a4414158efcf1727279cfec4352b4d8a5bdfe` adds regression coverage for reject/allow cases.

## 2026-09-29 — Segment 4 infinite restart root cause fixed

- User supplied a live run showing Segment 4 repeatedly restarting with `global flags not at the start of the expression at position 38`; this was a Python regex exception, not an LLM stall.
- `tests-2478` reproduced the same exception in `test_opening_held_prop_cannot_be_reacquired_without_release`.
- Pending `acceptance-2479` was removed from the runtime queue; no new acceptance is queued until the regression suite is green.
- Root cause: `_director_opening_held_reacquire_errors` embedded `_DIRECTOR_HELD_REACQUIRE_RE.pattern`, which contained an inline `(?i)` flag, inside a larger regex that already had preceding tokens. Python rejects nested global flags away from pattern start.
- Commits `9aa323f46297def8bacfb8c98bda41b460da7b1a` and `603b0e9d78c3c08316f2e3c1b679cde59b381661` split the reusable reacquire fragment into a flag-free string pattern and compile the standalone regex with `re.IGNORECASE`.
- Commit `559cc68e686272eb6b3931cb6c3ebb43321490c3` makes `re.error` non-recoverable in the outer generation loop. Regex/programming defects now fail fast instead of restarting the same checkpoint forever.


## 2026-09-29 — Request-1 KISS + preserved-state semantics

- Preserved canonical state now follows the core state rule: if a barrier state is already established in the opening state and no typed effect changes it, a RAW-scene extractor result of `UNSPECIFIED` means "not restated" and does **not** override the canonical state. Explicitly assigned barrier transitions still require an observed matching result; `UNSPECIFIED` remains invalid for those.
- Director Request 1 was reduced to a compact creative-director contract: ASSIGNED SOURCE -> CURRENT BEAT -> OPENING STATE -> Python-owned FINAL STATE CONTRACT -> NEXT BEAT boundary.
- Python now appends one concise `AUTHORITATIVE FINAL STATE CONTRACT` covering final-side topology, barrier end states, barrier binding, and closed-boundary traversal constraints rather than several verbose prose blocks.
- No Director 1B/state-repair stage was added. First evaluate the simpler creative call plus corrected deterministic state semantics.


## 2026-09-29 — Held-prop use vs reacquisition

- acceptance-2484 completed all 8 Director-only segments; preserved BROKEN/LOCKED barriers no longer fail when RAW omits them.
- acceptance-2485 exposed the next earliest deterministic false positive: _director_opening_held_reacquire_errors treated phrases such as "pulls the trigger on her pistol" as reacquiring an already-held pistol because the regex allowed the prop to appear far after the reacquire verb.
- The guard now requires the canonical held prop to be the direct object of pull/draw/retrieve/take/grab/pick-up. Ordinary use such as pulling a trigger, shooting with, or raising an already-held pistol is allowed.
- Keep the KISS Request-1 prompt unchanged while measuring this deterministic fix.


## 2026-09-29 — Crossing-route contract tightened

- acceptance-2487 confirmed Segment 4 no longer exhausts retries after the held-prop fix; it cleared on attempt 2.
- The earliest recurring failure moved to Segment 2: GPT-OSS 20B repeatedly invented basement stairs/hallways even though the compact Director prompt forbids unestablished route geometry.
- Keep Request 1 compact. When Python has both a destination topology contract and a bound destination barrier, append one explicit route line: move authorized subjects directly through that destination boundary and do not invent stairs, hallways, corridors, or intermediate route geometry.
