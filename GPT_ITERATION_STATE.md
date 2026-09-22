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

## Exact majority-budget follow-up

Probe `arc-coverage-emphasis-create-probe-017` exposed a separate creator weakness: even when told that an 8-beat story needs at least five emphasized beats, Mistral preserved source coverage but still allocated four non-emphasis setup/preparation beats and only four materially zombie-killing beats (counting the final kill/resolution beat).

Focused response:

- `6f10e94b251e18ebdb416d87023e79e37af73086` — when the source contains explicit `majority`, ARC creation and repair now receive exact Python-computed arithmetic: for 8 beats, reserve at least 5 emphasis beats and allow at most 3 non-emphasis beats. The prompt explicitly says to preserve every source action by adjacent bundling and allows the final emphasized action to share its beat with immediate aftermath/resolution.
- `ca255c9359f05cc48f6ca029196bca2c041e824a` — regression coverage for the exact create/repair majority budget.
- `arc-budget-tests-021` queued on the local bridge.

This remains within the current KISS boundary: Python supplies only deterministic arithmetic; the LLM still decides what source action is emphasized and how adjacent source actions should be semantically bundled.

## Important caution

The evidence LLM can undercount individual matches (one probe returned [4,5,6] instead of [4,5,6,7]), but for the observed bad 4/8 case it still produces evidence below the threshold. Continue evaluating false negatives/false positives through acceptance before generalizing beyond the observed `majority` failure.

Do not build a generalized relative-emphasis subsystem for `most`, `half`, `briefly`, etc. until an actual acceptance failure requires it.

## Superseded long-running acceptance

`run-acceptance-amy-coverage-priority-019` began before the exact majority-budget creator/repair fix was committed. While it remained active, the branch advanced through `6f10e94...` and `ca255c9...`, making the running acceptance stale relative to the code now intended for evaluation.

Mailbox handling:

- queued latest full acceptance: `run-acceptance-amy-majority-budget-022`
- removed the stale `run-acceptance-amy-coverage-priority-019.json` job from `gpt-runtime` so it will not restart after the bridge is restarted
- `arc-budget-tests-021` and `arc-repair-missing-breakfast-probe-020` remain queued ahead of the latest acceptance

Because the already-running local child process cannot be cancelled remotely through the mailbox, the next required local action is to stop the current bridge process with Ctrl+Q (or Ctrl+C) and restart `python tools/chatgpt_llama_bridge.py`. The restarted worker should then consume the latest pending jobs instead of the superseded acceptance.

## Immediate next steps

1. Restart the local bridge so the superseded in-flight `-019` acceptance is cancelled and the latest pending jobs can run.
2. Confirm `arc-budget-tests-021` passes.
3. Inspect `arc-repair-missing-breakfast-probe-020` for whether repair can restore breakfast while retaining the exact majority budget.
4. Inspect `run-acceptance-amy-majority-budget-022`.
5. Verify Segment 1 restores the ordinary breakfast setup and compare final H3 prompts against gold chronologically.
6. Fix the **next earliest observed semantic mismatch only**, then update this file again.

## Recovery instructions for a new chat/context

Read this file first, then inspect:

- latest commit on `gpt-test-branch`;
- newest entries under `bridge/results/` on `gpt-runtime`;
- newest queued jobs under `bridge/jobs/`.

Do not restart architectural brainstorming from scratch. Treat the proven probes, failed approaches, current implementation, and earliest failure above as the working checkpoint unless newer repo evidence supersedes them. Preserve the **input/output product contract**, not the current internal decomposition: if evidence eventually shows ARC -> BEATS -> prompts is the wrong route to gold-quality prompts, architectural replacement is explicitly allowed.

## 2026-09-21 late-session architecture correction: gold is richer than story text

Full acceptance `run-acceptance-amy-majority-budget-022` exposed that the literal majority implementation was optimizing the intermediate ARC away from the actual gold target.

The generated ARC preserved breakfast but packed the zombie break + kids-to-basement + lock + arsenal retrieval/equip into Beat 2, then used Beats 3-7 for literal zombie kills and Beat 8 for reunion.

The hand-authored gold instead uses the available runtime as a **broad conflict sequence**:
- Beat 1: fully staged ordinary breakfast.
- Beat 2: zombie arrival + escape toward/opening safe-room door.
- Beat 3: finish securing kids + reveal/equip arsenal + turn back toward conflict.
- Beats 4-7: varied zombie fight, including attacks on Amy, reversals, weapon transitions, and continued killing.
- Beat 8: final zombie falls + immediate family resolution.

Therefore the source statement "the majority of the film is Amy killing zombies" must NOT be interpreted as "more than half of required_events must literally contain a kill verb."

### Superseded approach

The earlier `majority_checks` evidence path originally counted only beats whose required_event materially performed/continued the literal emphasized action. That forced five literal kill jobs and compressed setup unnaturally.

### Current corrected approach

Commits:
- `fef71d4843e20444bdbc92788031e1dd8b2aeac0` — reinterpret majority as allocation to the **broad emphasized narrative sequence**.
- `337796b69e33b0f2a2bcb428b9ef86147af59dc6` — update regression expectations.

For an explicit majority:
- Python still supplies/counts the deterministic numeric threshold.
- The LLM supplies semantic sequence membership.
- Sequence membership may include immediate preparation entering the conflict, enemy attacks, reversals, setbacks, weapon transitions, continued action, terminal result, and immediate resolution at the end of that ongoing sequence.
- Ordinary pre-conflict setup does not count.
- Distinct earlier setup stages should not be compressed merely to manufacture literal repetitions.
- For an 8-beat continuous emphasized section, at least 5 beats must belong to that broad section.

Probe `arc-majority-sequence-probe-024` showed Mistral can classify a gold-like broad conflict span rather than only literal kills.
`arc-sequence-tests-030` passed 9/9.

## Director local-staging finding

The gold prompts contain substantial **local cinematic realization** that the short story does not explicitly spell out: breakfast food/plates, children receiving breakfast, short dialogue, weapon handling, enemy reactions, setbacks, etc.

The previous Director contract was too strict: it treated CURRENT BEAT as not only the exclusive story event, but effectively the exclusive list of all micro-actions. This made gold-quality prompt generation impossible from a low-burden story input.

Probes:
- `director-local-staging-probe-023`: proved Request 1 can enrich a broad activity, but over-invented unrelated side business.
- `director-minimal-staging-probe-025` and `director-direct-instantiation-probe-027`: still added unrelated participant behavior.
- `director-beneficiary-completion-probe-031`: succeeded with the tighter rule. It kept Will/Amber present, staged breakfast, turned off the stove, served the food, let both children participate, kept the scene ordinary/safe, and did not begin the zombie beat.

Production response:
- `62814ee4db1354cdebe5b2a15a97b07c1a175754` — Director Request 1 now has controlled **LOCAL STAGING** authority.
- `cc1cb2e29f48c7b5209010581fe59c79b02c6203` — regression test for that contract.

Local staging may add only minimal mundane micro-actions, props, reactions, and short dialogue that directly realize CURRENT BEAT. It may NOT invent unrelated side business or consequential persistent story changes. When an activity is explicitly done FOR named beneficiaries, they should be present and visibly receive/participate when practical.

Important negative result: `beat-local-completion-probe-029` leaked the NEXT EVENT into the current beat when BEAT generation itself was relaxed. Therefore do **not** broadly move this creative authority into BEAT generation yet. Keep BEATS as the story-event execution targets and let Director Request 1 perform controlled local cinematic realization.

## Current queued verification

- `run-acceptance-amy-sequence-032`: evaluates corrected broad-sequence ARC allocation; it started before the Director staging commit and is therefore stale for final prompt quality.
- `director-sequence-tests-033`: focused ARC + Director regressions on current code.
- `run-acceptance-amy-director-staging-034`: current full acceptance; this is the important next result for final gold-prompt comparison.

## 2026-09-21 direct locked-gold contract fixes after staging discovery

The locked benchmark file `tests/acceptance/gold/amy_zombie_house.json` was inspected directly. It explicitly says the short `story_text` is the low-burden input and the hand-authored prompts are fuzzy behavioral targets. This confirms the program itself must create the rich cinematic realization.

### Director timestamp/density contract

Locked gold requires canonical timestamps `At mm:ss.nnn,` with no trailing word `seconds`, one discrete action per timestamp, and **no arbitrary maximum timestamp count**. Gold Beat 3 uses far more than eight timestamps in an eight-second clip.

The prior Director template contradicted this by requiring `At ... seconds`, capping micro-beats at segment seconds, and forcing the final timestamp at least one second before the endpoint.

Fixed:
- `71a1b8cf8284bcf8e00451f19fb1294ec01ffa4b` — canonical timestamp syntax, unlimited needed timestamps, discrete actions, late valid handoffs, body-disconnection staging.
- `767d04dca03df92be2ab6c210fc5058ec4bb42ab` — regression assertions.

### Named beneficiary loss in BEAT validation

Observed in acceptance: ARC E1 represented breakfast **for the kids**, but generated Beat 1 collapsed to Amy cooking alone; the single-beat validator accepted it. This removed Will/Amber from the Director's actual execution target.

Fixed:
- `36295840e9cc5c0b8d91ff10495feb948f5fc303` — named relational participants (`for/with/to`) are material in CURRENT JOB; reject solo rewrites that drop named beneficiaries/participants.
- `6e06bda1cb118aef3a3b4bc93940f4bc92ba6e23` — regression test.
- Bridge probe `beat-beneficiary-validator-probe-035` queued to confirm local Mistral behavior.

### Soundtrack behavior

Observed generated acceptance prompts used `non_diegetic_music: N/A` because Request 2 explicitly forbade inventing a soundtrack, while locked gold consistently supplies scene-appropriate score and requires append music to begin `continues from <Video 1>.`.

Fixed without a new LLM stage:
- `6f42195594ea355085f129f16cfef84e515be5b0` — Request 2's only creative finishing responsibility may be minimal scene-appropriate non-diegetic music; continuation segments must begin music exactly with `continues from <Video 1>.`.
- `c804abc7324ae802124f5d258c6f8ea35b5138d7` — formatter music-rule regression test.

Visual/action creativity remains owned by Director Request 1; Request 2 remains a strict translator except for this soundtrack finishing choice.

### ARC clip-scale boundaries, not source-sentence packing

Locked gold splits one long source action chain across Beat 2 and Beat 3:
- Beat 2: threat appears + escape toward/open safe-room boundary.
- Beat 3: finish securing kids + arm Amy + turn back toward conflict.

The current planner had overpacked whole source sentences into one required_event. A source sentence is not a video-clip boundary.

Fixed:
- `9f9447d2c9b7b2f0143e651896bb9dd915ccfd12` — when beat budget permits, split long adjacent source chains across consecutive clip-sized jobs at a natural physical/narrative handoff; punctuation is not a mandatory boundary.
- `1ff496f94a690bf8f83a754c7c63c27439d69650` — prompt regression test.

This is generic, not Amy-specific: ARC jobs should be executable clip-sized story progression.

### Current verification status

A long earlier acceptance `run-acceptance-amy-sequence-032` was still occupying the serial bridge when these later fixes were committed, so it may be stale for final prompt quality. Check its `repository_revision` before using it.

Pending/queued behind it at the time of this update:
- `director-sequence-tests-033`
- `run-acceptance-amy-director-staging-034`
- `beat-beneficiary-validator-probe-035`

Because bridge execution resets the exec worktree to latest `origin/gpt-test-branch` when each job begins, jobs that have not started yet will include the latest code regardless of when their JSON was queued. Always verify `repository_revision` for acceptance results.

## 2026-09-21 late checkpoint: beneficiary guard, stable threats, and sparse-setpiece planning

### Beneficiary semantic validator probe FAILED

Bridge probe `beat-beneficiary-validator-probe-035` tested:

- CURRENT JOB: Amy is cooking breakfast for Will and Amber.
- CANDIDATE: Amy cooks breakfast.

Even with an explicit instruction that named relational participants are material, Mistral returned:

`{"valid": true, "issue": ""}`

Conclusion: as with the earlier majority arithmetic failure, do not rely on this Mistral validator to enforce that semantic coverage rule by prose instruction alone.

### Deterministic named-Subject preservation

Observed requirement was narrow enough to move only the structural portion into Python without making Python interpret arbitrary story semantics:

- If CURRENT JOB explicitly contains a known Subject name from `subject_information`,
- the generated candidate beat must also contain that Subject name,
- otherwise structural validation rejects the candidate and regeneration receives the missing names.

Commits:
- `132d53f6af353e601611991a9460c5f2d37844b2` — `_missing_named_job_subjects(...)` and structural check before semantic beat validation.
- `043aeda57fb0e5f636e099f1200a3761045a0163` — deterministic coverage tests.

This remains KISS-compliant: Python compares known explicit names; it does not decide the meaning of the action.

A separate generator probe `beat-beneficiary-generation-probe-036` was queued to determine whether generation already usually preserves the names even without the guard.

### Stable functional labels for recurring unnamed individuals

Old acceptance left the first attacker anonymous, preventing stable Subject continuity.

Commits:
- `4b89a2f86371eb47f053b840f1b3231390a6cbbb`
- `a8598deb675973ea8fa5d61575a8a9d425937332`

Director Request 1 may assign a simple stable functional label such as `Zombie1`, `Guard1`, or `Creature1` to an unnamed visually significant individual that may persist, act again, speak, or matter to continuity. Do not label crowds/scenery/incidental background figures.

The existing Request2 `subject_genders` + dynamic Subject registry can register such names before final H3 prompt assembly.

### Sparse repeated conflict must become a coherent multi-beat setpiece

Locked gold Beats 4-8 demonstrate cross-beat stateful escalation rather than generic repeated kills:
- pistol becomes empty/discarded;
- katana is drawn later;
- threats persist between beats;
- Amy is contaminated with bile and remains contaminated;
- katana becomes stuck then is freed;
- final threat remains unresolved until the next beat;
- Beat 8 resolves threat + family reunion.

This kind of cross-beat creative state cannot safely be invented independently by each Director call. It must be planned upstream inside the existing ARC create/validate/repair loop.

Commits:
- `8f55465b69c4d0ca88fee49d5daad3fde88168ae` — ARC creation/validation/repair explicitly allows and encourages coherent local setpiece developments inside a source-authorized long conflict.
- `8e34bdcb5ff0790186fb0dc2e96e57b5048a92ce` — contract tests.

Allowed execution-level developments within an already authorized conflict include:
- attack/counterattack;
- weapon empty/drop/stuck/recovered/switch;
- enemy survives across beats;
- temporary contamination/mess;
- setback then recovery;
- delayed terminal result.

They are NOT permission to invent a new plot, major character, location, mythology, mission, outcome-changing injury, or alternate ending.

Persistent modeled facts authored by ARC still require typed `state_effects`.

### Current test/acceptance queue

Because the bridge sorts job filenames alphabetically and processes them serially:
- `aaa-current-regressions-037` was queued before the long acceptance.
- `arc-setpiece-create-probe-038` was queued to verify Mistral actually produces stateful escalation.
- `beat-beneficiary-generation-probe-036` was queued to measure generation behavior.
- `run-acceptance-amy-director-staging-034` is the next full behavioral run after those jobs.

The earlier `director-sequence-tests-033` had three failures, all test-contract/staleness issues rather than discovered production regressions:
1. stale continuity prompt wording assertion;
2. stale expectation that music must be N/A;
3. unnormalized wrapped string assertion in the new beneficiary test.

Fixed by:
- `81ac3b7a8a80dc767e7d6d687733d37e0b45f6c5`
- `fe7f9c92319e62cc5a32c4830a399292de885c3c`

Do not treat the old `-033` failure count as evidence that the current production code is broken; use `current-regressions-037`.



## 2026-09-21 late-session: baseline/inciting contrast is a real clip boundary

Fresh review of stale acceptance `run-acceptance-amy-director-staging-034` plus the current setpiece probe showed the ARC planner still merged the ordinary breakfast baseline with the zombie window break into Beat 1. That directly violates the locked gold, which keeps Beat 1 completely ordinary/safe and begins the disruption in Beat 2.

Observed failure:
- E1: breakfast + zombie window break in the same beat.
- This forced suspense/music/danger into Segment 1 and destroyed the intended ordinary-to-danger contrast.

Generic production fix:
- `5a126afa922feff97c93160f6f558a566941001d` — ARC create/validate now explicitly preserves an ordinary/baseline activity -> sudden disruptive/inciting change as a beat boundary when the requested beat budget can support it.
- When allocation is tight, prefer sharing the final emphasized action with its immediate resolution rather than leaking the inciting threat into the baseline beat.
- `fe137851a61a889584f398ea392d3ac4dc90273c` — regression contract for this rule.

This is not Amy-specific. It is a generic cinematic segmentation rule: an explicitly established safe/ordinary baseline should remain intact long enough to create the source-specified contrast with the inciting disruption.

### Current verification queue after this change

Queue a clean regression run and full Amy acceptance on/after `fe137851...`. Ignore older acceptance results for final-prompt quality when their `repository_revision` predates this checkpoint.


## 2026-09-21 late-session: sparse conflict needs unresolved cross-beat handoffs

Probe `arc-setpiece-create-probe-038` showed the ARC creator could invent varied conflict actions, but it still resolved each complication inside the same beat and ended the conflict before a resolution-only final beat. That remained too episodic compared with the locked gold's stateful multi-beat setpiece.

Focused production changes:
- `b20ae8ce72751f83abf81cad429d23a133c2bdbb` — strengthen sparse repeated-conflict planning:
  - when several conflict beats are available, prefer at least one meaningful complication/threat/weapon problem/contamination state that remains unresolved across an adjacent beat boundary;
  - when a source's terminal emphasized action is immediately followed by resolution, put terminal result + immediate resolution in the same final sequence beat whenever a resolution-only beat would otherwise shorten the emphasized majority sequence.
- `5b802656f350d5c2acb1aa5d9f28ad65ff085d7c` — regression assertions for those contracts.

This is still inside ARC create/validate/repair. No new semantic stage was added.


## 2026-09-21 late-session: regression cleanup and H3 continuation dedup

Current-head regression bundle `current-regressions-039` still reported four non-production failures:
- two Windows-only temp-file replacement errors caused by tests keeping `NamedTemporaryFile` handles open while `save_generation_state` uses atomic `os.replace`;
- two stale continuity assertions expecting legacy `retention_analysis`/hard-cut wardrobe text in the final H3 prompt even though clean-refresh now relies on the supplied first frame and intentionally keeps internal continuity text out of final H3 output.

Test-only fix:
- `218da775ca2d83e4fdbdea3340063a20d0ff1043` — use closed temp paths on Windows and align stale expectations with the current final-H3 contract.

A separate observed formatter defect from acceptance `-034` was still possible on current code: Request 2 could return
`[Shot 1] Live-action, cinematic, continues from <Video 1>...`
and Python would prepend its own canonical continuation opener, producing duplicate `continues from <Video 1>.`.

Production/test fixes:
- `3fdfb0ae7ffc7a92765e91d1517f82b46f991ffd` — strip Request 2's duplicate leading Video 1 continuation clause before Python prepends the canonical opener.
- `6c29c79a70a9ddf0650107a8af238b8df01f2cc5` — regression coverage.

No production behavior was changed merely to satisfy the obsolete continuity tests.


## 2026-09-21 late-session: Director cannot claim completion while dropping named Subjects

Acceptance `run-acceptance-amy-director-staging-034` exposed a Request 1 completion defect independent of its stale ARC: the final CURRENT BEAT explicitly required Amy to let **Will and Amber** out, but RAW SCENE stopped after Amy opened the basement door and still returned `beat_complete: true`.

The Director previously trusted its own `beat_complete` flag plus timestamp/end-state structure. It had no deterministic check that registered Subjects explicitly named in CURRENT BEAT actually appeared in RAW SCENE.

Focused fix:
- `e52be531e07c6215ced7dbe6683fc87c1cda7299` — add deterministic `_missing_named_director_subjects(...)` helper.
- `45ddc48e75021227d91e003d8b9a832c4ce257f8` — Request 1 completion now rejects/retries when RAW SCENE omits a registered Subject explicitly named in CURRENT BEAT.
- `604b9e13d95beeb1b4d445df41a42761dffad49f` — thread the exact current beat text into normal and repair Director bundles.
- `efa5192492cc7cfb95213a22f76726ecdfaf3175` — integration regression: a `beat_complete:true` scene that opens the door but omits Will/Amber must retry; the corrected scene includes them exiting.

This remains a narrow deterministic identity/coverage guard. Python is not interpreting whether the action itself is semantically complete; Director Request 1 still owns that.
