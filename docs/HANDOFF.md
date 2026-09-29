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


## 2026-09-29 — Held-prop sourced-lift reacquisition

- acceptance-2490 confirmed the explicit crossing-route contract: Segment 2 passed on its first Request-1 attempt with no invented stairs/hallways.
- The next continuity hole appeared in Segment 4: RAW reacquired an already-held pistol via "lifts the pistol from a nearby table". The direct-object guard correctly ignored ordinary weapon use but did not yet treat lift/raise-from-source phrasing as acquisition.
- Opening-held reacquisition now also rejects lift/raise of the held prop when followed by from/off/out of a source. Ordinary lift/raise-to-aim/use remains valid.

- `tests-2491` passed 102/102 targeted tests (plus 6 subtests), including the new sourced-lift regression.
- `acceptance-2492` is queued as the next frozen-plan Director-only acceptance using `director_plan_job: "acceptance-2451"`.
- Relevant production fix: `27922a035998c14f6d4826707ad61091f59ab5c6`.


## 2026-09-29 — acceptance 2492 concrete-action fidelity

- `acceptance-2492` completed all 8 frozen-plan Director segments and confirmed the opening-held sourced-lift fix: Segment 4 no longer reacquired the pistol from an invented surface.
- The earliest remaining real production defect moved earlier to Segment 2. Assigned source/beat requires Amy to grab Will and Amber and rush them to the basement, but RAW substituted `Amy lifts Will and Amber` / carries them. This is a material physical-action substitution, not harmless staging.
- The existing Request-1 completion verifier required source actions to occur but did not explicitly forbid replacing one concrete source action/participant interaction with a materially different physical action.
- Commit `fd436b0791c59b01eed69fec95d710d63869a1b8` adds one compact source-fidelity sentence to Request 1 and its existing independent completion verifier. No new LLM call or semantic stage was added.
- `tests-2493` is queued. If green, rerun the frozen-plan Director-only acceptance against `acceptance-2451`. Do not address the later Segment-7 kitchen/living-room teleport until this earlier Segment-2 defect is cleared.


## 2026-09-29 — acceptance 2494 barrier identity

- `acceptance-2494` confirmed the Segment 2 concrete-action substitution fix: Amy now grabs Will and Amber rather than lifting/carrying them.
- The next earliest defect is still Segment 2: RAW conflated the broken kitchen entry door with the basement boundary. It explicitly pushed the children toward/through the broken door, then `slams the kitchen door shut` and locks it even though Python's generic `door` effect is bound to the basement destination.
- The semantic completion verifier had the correct AUTHORITATIVE BARRIER BINDING but accepted the wrong explicitly qualified barrier. This responsibility is deterministic: when Python binds a generic barrier to one destination, an explicit state-changing action on a differently qualified same-type barrier is invalid.
- Commit `abd8db92c351f8b77bbe3bdab15c0a36f6df1076` adds a narrow Python guard for this case. Generic `the door` and the destination-qualified barrier remain valid; actions on a nested window such as `kitchen door window` are not misclassified as door-state changes.
- `tests-2495` is queued. If green, rerun the frozen-plan Director-only acceptance against `acceptance-2451`.


## 2026-09-29 — acceptance 2497 prompt-continuity location drift

- `tests-2496` passed 106/106 targeted tests plus 6 subtests.
- `acceptance-2497` cleared the earlier Segment 2 concrete-action and wrong-bound-barrier defects. Segment 2 RAW now grabs Will and Amber, moves them through the basement door, then closes/locks the basement door.
- The next earliest defect is prompt-derived continuity immediately after Segment 2: the continuity extractor invented `Amy.position = "outside kitchen doorway"` even though RAW never moves Amy outside and no source-owned location/containment effect authorizes that persistent spatial change. That invented position then contaminates Segments 3-6.
- Commit `360990a7248fc7122306d08353a80a7bbf47cfa6` adds a narrow deterministic merge guard: a newly external/`outside` subject position cannot replace a known committed placement unless that subject has a source-owned `set_location` or `set_containment` effect. Ordinary internal room refinement remains allowed.
- `tests-2498` and frozen-plan Director-only `acceptance-2499` are queued together to reduce bridge round-trips.


## 2026-09-29 — acceptance 2499 wrong-bound crossing route

- `tests-2498` passed 109/109 targeted tests plus 6 subtests.
- `acceptance-2499` confirmed the prompt-continuity outside-location corruption is cleared; Amy no longer gets pushed outside the house after Segment 2.
- Earliest remaining defect is still Segment 2: RAW says `They sprint through the broken kitchen doorway directly into the basement`. This incorrectly uses the kitchen entry boundary as the basement crossing route even though the scene separately has a basement door.
- Existing deterministic bound-barrier guard covered wrong qualified barrier state changes, but not wrong qualified barriers used as the crossing route into the bound destination.
- Commit `0a735335cdefb2a65d2b7bb844413912b9d952ea` extends the same narrow Python guard to reject `through/via/across <wrong qualified door/doorway> ... into <destination>` when Python binds the generic barrier to that destination.
- `tests-2500` and frozen-plan Director-only `acceptance-2501` are queued together.


## 2026-09-29 — acceptance 2501 pull-out reacquisition

- `tests-2500` passed 110/110 targeted tests plus 6 subtests.
- `acceptance-2501` cleared the Segment 2 wrong-bound crossing-route defect.
- Earliest remaining defect moved to Segment 4: Segment 3 leaves Amy holding pistol + katana, but Segment 4 says `Amy pulls out her pistol` before firing. The held-prop deterministic guard already rejected direct reacquisition forms but missed the phrasal verb `pulls out <prop>`.
- Commit `940ed4ccd792ba97d67543ce3e9d15554796460e` extends the existing held-prop guard to cover `pull/pulls/pulled/pulling out <held prop>` without changing Director semantics or adding a new LLM stage.
- `tests-2502` and frozen-plan Director-only `acceptance-2503` are queued together.


## 2026-09-29 — acceptance 2503 unassigned external relocation

- `tests-2502` passed 111/111 targeted tests plus 6 subtests.
- `acceptance-2503` cleared the Segment 4 `pulls out her pistol` reacquisition defect.
- Segments 1-7 are now materially clean enough to advance. Earliest remaining defect is Segment 8: RAW moves Amy outside with Will and Amber and ends with all three on a sunny patio, but only Will and Amber have source-owned movement/containment effects for the escape.
- Existing topology validation only reasoned about the basement boundary, so Amy could remain correctly outside the basement while still being incorrectly relocated outside the house.
- Commit `af12046bca490d1707f5bd2383b11cdc2a647a0c` adds a narrow deterministic end-state guard: if a known subject explicitly ends outside/on a porch/patio/exterior and no source-owned set_location/set_containment effect authorizes that persistent relocation, reject Request 1. Already-external subjects and explicitly authorized moves remain valid.
- `tests-2504` and frozen-plan Director-only `acceptance-2505` are queued together.


## 2026-09-29 — acceptance 2505 preserved containment

- `tests-2504` passed 113/113 targeted tests plus 6 subtests.
- `acceptance-2505` cleared Amy's unauthorized outside relocation in Segment 8.
- Earliest remaining defect is Segment 7: Will and Amber are still canonically contained in the basement, but RAW stages them `through the broken kitchen door window` looking at the fight before their release beat. Prompt-derived continuity then incorrectly moves them out of the basement.
- Existing topology guards only activate around typed destination transitions; they did not protect unchanged containment on a beat with no containment effect.
- Commit `fa2769520c569be680fc880152fb39f00f37a41a` adds a deterministic preserved-containment guard: a subject canonically contained in a location cannot be visually staged elsewhere unless the current beat carries a source-owned set_location/set_containment effect for that subject. Explicitly keeping the subject in the container remains valid.
- `tests-2506` and frozen-plan Director-only `acceptance-2507` are queued together.


## 2026-09-29 — acceptance 2507 pronoun held-prop reacquisition

- `tests-2506` passed 116/116 targeted tests plus 6 subtests.
- `acceptance-2507` cleared the Segment 7 preserved-containment leak; Will and Amber now remain in the basement until their release beat.
- Earliest remaining defect is Segment 4: RAW begins with Amy already holding pistol + katana, then says `She pulls the pistol from her belt` before firing. This is another held-prop reacquisition.
- The held-prop guard was subject-name anchored, so the production pronoun form `She pulls...` bypassed it even though equivalent `Amy pulls...` regressions passed.
- Commit `1aa135386671a4c42764f570b07357ef034ae70d` broadened sourced pull phrasing; commit `9101c02d0fa451b89e327123ab1abd0564dce41f` fixes the actual production hole by allowing an unambiguous pronoun actor only when exactly one opening-state subject holds that prop.
- `tests-2508` and frozen-plan Director-only `acceptance-2509` are queued together.


## 2026-09-29 — tests 2508 pronoun regression correction

- `tests-2508` was red: 116 passed, 1 failed, 6 subtests passed. The failing production-shaped regression was `She pulls the pistol from her belt`.
- Root cause: pronoun matching required gender metadata, but the held-prop guard can receive minimal opening state containing only `held_props`. The production parser therefore still missed the exact pronoun form seen in acceptance 2507.
- Commit `1e5d545a5d797d190e10188323ab68c5667fe39a` makes pronoun resolution depend only on uniqueness of the opening-state prop holder: if exactly one Subject holds that prop, `she/he/they` is accepted as an unambiguous actor; if multiple Subjects hold the same prop, pronouns are not used for deterministic rejection.
- `acceptance-2509` is diagnostic only because the regression suite was red. It suggests the next issue may be Segment 8 failing to actually clear Will and Amber out of the house, but do not fix that until the held-prop regression is green.
- `tests-2510` and frozen-plan Director-only `acceptance-2511` are queued.
## 2026-09-29 — Director RAW timing must use the clip window

- A fresh Director RAW scene for an 8-second Segment 2 completed all timed action by 00:01.300. The existing contract only required the final timestamp to be before the segment endpoint, so this was structurally accepted.
- Fix: Request 1 now explicitly paces timed action across the full clip, and Python deterministically rejects RAW scenes whose final timed micro-beat occurs before the final quarter of the segment. For an 8-second clip, the last timed action must be at or after 6.0 seconds and still before 8.0 seconds.
- This remains inside the existing Director Request-1 structure gate; no new LLM stage or semantic pipeline was added.
- Added focused regressions for rejecting a 1.3-second ending in an 8-second clip and accepting a 6.2-second ending.
- Next checkpoint: run the focused Director regression suite, then a fresh Director-only acceptance using the frozen plan and verify Segment 2 uses the full 8-second timing window.

## 2026-09-29 — direct endpoint continuation and frozen-plan checks

- `gpt-arc-refresh` was pulled at `5a44e3e9`. The local GPT-OSS endpoint at `http://192.168.0.203:1234` is directly reachable, so no bridge program is needed for this session. The endpoint briefly timed out, then recovered.
- The new final-quarter timing gate exposed stale mocked Director fixtures. Their RAW and formatter examples now extend to 00:04.500 in the tests' six-second segment. The focused Director/formatter/prompt-generation suite is green: **136 passed, 8 subtests passed**. Production timing behavior is unchanged from `5a44e3e9`.
- The frozen `acceptance-2451` arc and beats were materialized from its saved `acceptance_run.json` on `gpt-runtime`. The direct runner uses `tests/acceptance/run_acceptance.py --director-plan-dir /tmp/amy-frozen-2451 --image1 Amy.jpg`. All acceptance outputs are in `/tmp`; none are committed. An initial diagnostic used the repository image because `Amy.jpg` was not present, but `Amy.jpg` later appeared in the workspace and is used for subsequent checks.
- A completed direct frozen-plan run is at `/tmp/amy-director-20260929-r4/acceptance_run.json` (8/8 segments, refresh at Segment 7). Every segment's last RAW timestamp was in the final quarter, so the timing rule passed live. This run exposed the earliest persistent-state defect at Segment 4: Amy began holding pistol + katana but ended with the katana on her belt. Prompt-derived continuity then carried that unauthorized belt state into Segment 5.
- Earlier diagnostic runs also exposed deterministic Segment-2 false positives and missed crossings. The external-location guard treated `Amy outside the basement` as outdoors; it now distinguishes an interior containment boundary from outside the house. The crossing guard now recognizes `while Amy follows behind`, exit-from-destination evidence, and `dash`; bound-door routing rejects a window route into the basement. These are all Python checks inside the existing Request-1 gate, with no new LLM calls or longer model prompts.
- A later direct run with `Amy.jpg` showed a Segment-2 RAW scene that moved the children only to the basement door, closed it, and claimed they were inside in the final-state sentence. The new deterministic containment-crossing check requires each newly contained subject to visibly cross in a timed action; final-state assertion or approach alone is insufficient. A fresh run then passed Segment 2 with `Amy pushes Will and Amber through the kitchen side of the basement door into the basement` before she shut and locked it.
- The held-prop gate now also rejects an opening-held prop ending on a belt/holster/sheath unless authoritative source explicitly assigns that stow. The focused regression uses the production Segment-4 katana case and an authorized-stow control.
- Direct frozen-plan run `/tmp/amy-director-20260929-r6`, using `Amy.jpg`, cleared Segment 2 with an explicit door crossing and Segment 4 with both weapons still held. It was stopped at the earliest new clear defect in Segment 5: RAW began with pistol and katana occupying both hands, then said Amy lifted a severed arm `with both hands` without releasing either weapon. The end state still claimed both were held. The existing Request-1 structure gate now rejects this exact occupied-hands contradiction unless one opening-held prop is visibly released first. No LLM prompt or call was added. Evidence is preserved under `/tmp/amy-director-seg5-evidence-r6/`.
- Next checkpoint: rerun the frozen-plan Director acceptance with `Amy.jpg` and review the earliest new real defect. Keep GPT-OSS 20B jobs narrow and use Python for typed-state and crossing invariants. Commit and push this handoff with the code changes to `gpt-arc-refresh`; do not add the untracked runtime `Amy.jpg`.

## 2026-09-29 — Director Request 1 wording simplified for local gpt-oss 20B

- Target runtime model remains `GPT-OSS-20B-Uncensored-HauhauCS-MXFP4-Balanced.gguf`.
- The exact model card adds no special prompt syntax beyond being a gpt-oss 20B derivative. Keep using the runtime's gpt-oss/Harmony chat template.
- Director Request 1 now uses short, literal, ordered rules: SOURCE -> CURRENT BEAT -> OPENING STATE -> END STATE RULES -> NEXT BEAT.
- Removed abstract wording such as "authoritative final state contract", "persistent changes", and the blanket ban on invented structural geography from the creative call.
- Harmless route details (for example, a short hall or stairs) are now allowed. The real invariants remain enforced: required destination, correct bound door/gate, which people cross, and required end state.
- Removed the deterministic unestablished-route rejection and the matching completion-verifier rule so harmless route detail is not accepted by the prompt and then rejected later.
- Timing is now stated with a concrete number for each clip: the last timed action must be at or after 75% of the clip length and before the exact endpoint.

