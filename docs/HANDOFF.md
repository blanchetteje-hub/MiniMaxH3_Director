# MiniMax H3 — Development Handoff

Last updated: 2026-09-21

This document is the quick-start handoff for a new ChatGPT conversation. For detailed evolving decisions and heuristics, also read `docs/PROJECT_NOTES.md`.

## Working arrangement

Active development is being handed to ChatGPT in normal chat mode.

Loop:

1. User runs the program locally.
2. User sends logs / acceptance artifacts.
3. ChatGPT inspects the latest `gpt-test-branch` code and the observed failure.
4. ChatGPT makes the smallest generic fix at the actual failing boundary.
5. ChatGPT commits directly to `gpt-test-branch`.
6. User pulls and reruns.

Do not default to Codex prompts. Minimize cognitive load for the user.

### Scheduled H3 iteration

The hourly `H3 Iteration` task should target the currently active GPT-Driven H3 conversation. Each run must read this handoff before acting and update it whenever substantive project state, decisions, or the next acceptance target changes.

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active branch: `gpt-test-branch`

Always read the current GitHub branch head; do not trust a stale SHA in this document.

## Ultimate goal

The goal is not to preserve any current architecture.

The goal is:

> The user supplies one story (plus whatever minimal explicit input format/reference images prove necessary), and the system reliably creates the proper MiniMax H3 prompts to render that story well.

Story format, story arc generation, whether an arc exists at all, beat generation, Director structure, continuity representation, and deterministic plumbing are all changeable if evidence shows a better structure is required.

KISS is the default, not a prohibition against real architectural correction.

## Current semantic architecture

Current source of truth uses two semantic planning loops:

### ARC

CREATE -> VALIDATE -> REPAIR -> VALIDATE until valid

### BEATS

CREATE -> VALIDATE -> REPAIR -> VALIDATE until valid

Do not add independent semantic enrichment/review/coverage/claims/effect-proof/state-preparation pipelines unless empirical evidence shows the two-loop architecture itself is insufficient.

State is Python-owned canonical data.

`state_effects` live in story-arc `required_events` and are committed by Python only after a beat validates.

The proven single-beat validator is frozen in principle unless new evidence implicates it:

- Mistral 24B
- temperature 0
- repeat_penalty 1.15
- seed 42
- 400/400 benchmark

## Director

### Request 1 — imagination

Expands CURRENT BEAT into a timed raw scene.

It owns beat completion.

Required structural output includes timed actions and exactly one trailing `End continuity state:`.

### Request 2 — stenographer

Translates Request 1 into H3 format.

It must preserve actions, action order, timestamps, camera movement, and dialogue. It must not become a creative rewriting stage.

## Gold acceptance target

The first locked end-to-end benchmark is:

`tests/acceptance/gold/amy_zombie_house.json`

It contains the user's hand-authored 8-segment Amy/zombie story with gold H3 prompts, must-happen constraints, must-not-happen constraints, and expected end states.

GPT-5.6 Sol is the fuzzy semantic evaluator. Do not attempt to replace that final judgment with a 24B local grading model.

The benchmark is behavioral. Generated prompts do not need to match gold strings exactly.

### Acceptance runner

Run locally after pulling:

`python tests/acceptance/run_acceptance.py --image1 amy.jpg`

The runner:

- executes in an isolated temporary repo copy;
- writes the locked Amy story and base subject definitions there;
- removes stale arc/beat/runtime state in the isolated copy;
- runs 8 x 8-second prompt-only segments;
- schedules segment 7 as refresh;
- never sends anything to ComfyUI;
- captures final generated H3 prompts and runtime state;
- writes `acceptance_run.json`, `run.log`, and generated artifacts under `tests/acceptance/results/`.

The user should normally upload `acceptance_run.json` first. Ask for `run.log` when diagnosis needs the LLM exchange/trace.

The runner intentionally produces no semantic pass/fail score. It does perform deterministic capture validation: all eight H3 prompts must be present. A structurally incomplete capture exits nonzero even if `minimax.py` returned best-effort success.

## Gold H3 formatting discoveries

Treat these as tested production heuristics, not arbitrary style preferences:

- Canonical timestamp syntax: `At mm:ss.nnn,`
- Do not append the word `seconds`.
- One discrete action per timestamp.
- No arbitrary timestamp-count limitation.
- `(S#)` is needed only for dialogue speakers.
- Prefer names over pronouns when ambiguity is possible.
- Pronouns are fine within a sentence when the referent is already unmistakable.
- Every append music field should begin `continues from <Video 1>.` before describing a music change.
- Avoid ending an append segment on dialogue when practical; H3 may carry vocal momentum into the next clip.
- If append context does not visibly prove a persistent detail, restate it. This is especially important for full clothing, lower-body clothing, holsters, weapons, injuries, blood, and substances.
- Difficult decapitation/dismemberment works better when staged across separate timed events: strike, separation, detached part movement, reaction/close-up, remaining body collapse.
- For fades, distinguish semantic pre-fade state from the literal black final frame.
- Visually similar characters may require explicit appearance/clothing reinforcement in the opening description.

## Append workflow

Implemented on `gpt-test-branch`:

- only the final 22 frames of the previous video are loaded;
- `skip_first_frames` selects that tail;
- `frame_load_cap = 22` prevents accidental extra context.

Do not revert this to the old 72-frame / 3-second behavior.

## Refresh workflow

The user's tested Extend Backport refresh graph is integrated on `gpt-test-branch`.

Runtime behavior:

- load the previous segment directly;
- calculate its exact H3-aligned frame count from the configured segment length;
- load only the final 22 frames;
- VAE-encode those frames as `context_latent`;
- `context_frames = 7`;
- pass prior video audio as `ref_audio`;
- reverse/select the tail frame using the user's tested first-frame selector path;
- batch active reference images densely and remap render-only `<Picture N>` tags when missing/excluded references require compaction.

For 8-second segments, H3 frame count is 192 and the loader skips 170 frames.

The old `MiniMaxH3HybridRefAndKeyframe` graph is preserved as `Minimax_auto_repair_API.json` and is used only by `--repair`, so the refresh migration does not remove two-keyframe repair behavior.

## Subject input rule

User-defined named Subjects may be declared without a Picture reference, e.g. `<Subject 2> is Will, a 10-year-old boy.`. These are stable Python-owned identities with no initial reference image. Do not force every named character to have `<Picture N>`.

## Continuity philosophy

Principle:

> Know more internally; expose only current final-frame facts.

Persistent Subject identity belongs to Python.

Continuity LLMs cannot create durable Subject identities.

Generic/transient actors cannot collapse into existing named Subjects.

Never special-case literal zombie/weapon/room/character vocabulary in production logic.

## Known environment-continuity action item

Leaving and later re-entering a room can cause H3 to regenerate a different room.

Preferred first attempt later:

- persistent room identity: layout, furniture, doors/windows, colors, major objects;
- mutable room state: damage, broken glass, blood, bodies, moved objects, fire, etc.;
- re-inject that state when the room is revisited.

If descriptive state is insufficient, upgrade to capturing a representative room frame and using it as a reference image on re-entry.

Do not implement this until the gold benchmark exposes it as a priority.

## Significant recent branch work

- Request-1 structural enforcement: timed micro-beat + exactly one non-empty trailing End continuity state.
- Phase-1 final-frame authority separated from full-segment supporting context.
- LLM-emitted Subject identity metadata stripped before mutable continuity validation; Python remains identity authority.
- Append input reduced to final 22 frames and capped at 22.
- Gold 8-beat Amy benchmark locked.
- Acceptance-runner scaffold added.

See Git history for current commit IDs; branch head is authoritative.

## How to work the next failure

When a new acceptance run arrives:

1. Compare each generated H3 prompt to its gold beat behaviorally.
2. Identify the earliest meaningful divergence.
3. Trace the divergence backward:
   - source story / required input format;
   - story arc;
   - beat generation;
   - Request 1;
   - Request 2;
   - continuity Phase 1;
   - Phase 2 projection/opening;
   - identity registry;
   - deterministic Python plumbing.
4. Fix the earliest incorrect boundary rather than patching downstream prose.
5. Add a targeted regression test when deterministic behavior is involved.
6. Commit to `gpt-test-branch`.
7. User pulls and reruns the same locked benchmark.

The benchmark is the finish line. Do not move the gold target simply because production output misses it unless the gold itself is demonstrably wrong.

## Local llama.cpp access

Use tools/chatgpt_llama_bridge.py rather than exposing llama.cpp to the public Internet.

Mailbox branch: gpt-runtime.

The local worker polls ChatGPT-authored JSON jobs, calls the configured local llama.cpp OpenAI-compatible API, then commits responses and requested artifacts back to the mailbox branch.

Normal command:

    python tools/chatgpt_llama_bridge.py

Default endpoint is http://127.0.0.1:8080; override with --endpoint.

This is intentionally not a remote-shell bridge. Supported job kinds are constrained to model chat calls and file collection.

## Current acceptance finding

Acceptance 091 completed successfully and finally preserved the ARC baseline boundary. The earliest remaining failure is now Beat generation / Request 1 completion for Segment 1.

### Acceptance 091: ARC boundary passes; Beat 1 still too abstract

`run-acceptance-amy-current-091` completed with return code 0 against repo revision `39898bd2abce7b978be272b35fc4d4a908d5101e`.

Accepted ARC:
- Beat 1: ordinary breakfast only.
- Beat 2: zombie breach + Amy sees danger + rush kids to basement + lock door.
- Beat 3: retrieve/equip weapons.
- Beats 4-8: majority zombie conflict and resolution.

So the protected ordinary-baseline / sudden-inciting-event rule held, and the majority allocation remained acceptable.

Generated Beat 1 was still:
> Amy cooks breakfast for Will and Amber at the kitchen stove.

Request 1 then produced:
- Amy stirring/flipping eggs;
- Will and Amber seated watching;
- Amy takes the pan off the stove;
- but breakfast is still visibly underway;
- neither child receives the finished food;
- stove/tool shutdown is not completed.

Request 2 faithfully preserved that incomplete Request 1 scene.

The earliest failure is therefore Beat creation failing to turn the finite required event into the concrete executable endpoint requested by its prompt.

### Sampling probes 092-095

`beat-phase1-endpoint-repro-092` used the same endpoint contract with deterministic sampling:
- temperature 0
- top_p 0.95
- min_p 0.05
- seed 42
- repeat_penalty 1.15

It produced:
> Amy cooks breakfast in the kitchen, placing food on plates for Will and Amber.

`beat-phase1-formatter-sampling-probe-093` used the H3 formatter sampling profile with seed 42 and also produced a concrete completed breakfast endpoint.

`beat-phase1-declared-sampling-probe-094` used the declared `BEAT_LLM_SAMPLING_PARAMETERS`:
- temperature 0.65
- top_p 0.90
- presence_penalty 0.15
- frequency_penalty 0.15
- repeat_penalty 1.05
- seed 42

It produced:
> Amy cooks breakfast for Will and Amber in the kitchen, and the food is ready on the table when the shot ends.

`beat-phase1-declared-plus-inherited-probe-095` added formatter-default top_k=20/min_p=0 and still preserved the correct endpoint.

The endpoint prompt is therefore viable. The discrepancy was in sampling transport.

### Production sampling-routing bug

ARC create/validate/repair and Beat generation explicitly call `ask_llm(..., **BEAT_LLM_SAMPLING_PARAMETERS)`.

However, `ask_llm()` previously replaced those caller values with `_active_formatter_llm_settings()` for every non-Beat-validator request. Under the Mistral formatter this silently changed Beat/ARC sampling to roughly:
- temperature 0.7
- top_p 0.8
- top_k 20
- min_p 0
- presence_penalty 1.5
- repeat_penalty 1.0

and generated a random seed.

That meant the named Beat sampling profile was effectively ignored. An existing integration test already stated that explicit caller sampling should be forwarded, but that pytest-based module is not runnable in the current bridge worker environment because pytest is not installed.

### Production correction

Production commit `4ad97cbf79050cb76a49945bc0890fa0612ae631` changes `ask_llm()` routing:

- **Beat validation remains frozen** to `MISTRAL_24B_SETTINGS`, overriding caller values exactly as before.
- For all other calls, explicit per-call sampling values are authoritative.
- Active formatter defaults only fill sampling/template fields that the caller did not supply.
- Existing formatter thinking/chat-template/jinja defaults still fill missing values.

This restores the intended meaning of `BEAT_LLM_SAMPLING_PARAMETERS` without changing the frozen 400/400 Beat validator.

Regression work:
- an initial test was placed in `tests/test_minimax_integration.py`, but that module cannot import on the bridge worker because pytest is absent; that test-only change was reverted in `dc3aa04741d731cd8d52e0f19d614c9805b6140e`.
- active unittest coverage was added in `fa24e6809eabb59bc85fc70f8b0b2854f3beb5c0`:
  - Beat-generation explicit sampling beats formatter defaults;
  - Beat validation remains pinned to benchmark settings.

`current-regressions-097`: **PASS, 106/106 tests green**.

### Current verification

- Next locked acceptance: `run-acceptance-amy-current-098`.
- First check: ARC Beat 1 must remain pure ordinary breakfast.
- Second check: generated Beat 1 should now be a concrete executable endpoint, ideally visibly delivering breakfast to Will and Amber or otherwise clearly completing the finite activity.
- Third check: Request 1 should realize that concrete endpoint and add only mundane local completion staging (for example utensil/stove settling) without entering Beat 2.
- Request 2 should preserve the completed scene.
- If Segment 1 passes, continue to Segment 2 and identify the next earliest divergence.

### Current architectural conclusion

KISS still holds:
- ARC = CREATE -> VALIDATE -> REPAIR
- BEATS = CREATE -> VALIDATE -> REPAIR
- Beat generation = concrete story-level execution target.
- Request 1 = timed mundane/local staging.
- Request 2 = stenographer/formatter.
- Python = deterministic structure/state mechanics.
- Sampling profiles are now routed according to the calling stage rather than silently replaced by formatter defaults.

### Other observed but non-current semantic weaknesses

- `arc-optional-state-effect-strong-probe-053`: Mistral accepted unsupported Hungry state inferred from cooking.
- `beat-lock-omission-current-probe-055` / `056`: Mistral accepted rushing children into the basement as completing a job that also required locking the door.

Do not create separate semantic subsystems merely for these probes. Work them only when end-to-end acceptance makes one the earliest real failure.

## Acceptance 098 follow-up: ARC state-effect contamination is now the earliest observed failure

`run-acceptance-amy-current-098` completed successfully against repo revision
`8485d3e6b224675906ce18e3774db3a8e9719470`.

The sampling-routing correction was active, but the accepted repaired ARC itself
introduced an earlier defect before Beat generation:

- E1 remained the ordinary breakfast event: Amy is cooking breakfast for the kids.
- E1 also acquired `set_condition` effects claiming Amy=`cooking`,
  Will=`eating`, and Amber=`eating`.
- The source/event never states that Will or Amber are eating.
- Beat generation receives the ARC's full required_events including state_effects,
  so those invented authoritative facts directly bias Beat 1 toward the kids
  already eating instead of the finite breakfast endpoint.
- Segment 1 consequently still failed the locked gold behavior: breakfast remained
  underway instead of being served and settled.

The same model weakness had previously appeared in
`arc-optional-state-effect-strong-probe-053`, where Mistral accepted an inferred
`Hungry` condition from cooking. A new exact-current probe,
`arc-state-effect-persistence-probe-099`, added even stronger semantic wording
and Mistral still returned VALID. Prompt emphasis alone is therefore not a
reliable guard for this class.

### Focused correction

Production commit `629e9d01225f6fcaa1843889d5a35e7e77c08b18` adds a
small deterministic data-integrity rule for free-form `set_condition` values:

- Python does **not** decide whether a condition is narratively true.
- Every meaningful word in a `set_condition.value` must occur in the same
  required-event text that owns the effect.
- This rejects invented values such as `eating` or `Hungry` when the event only
  says Amy cooks breakfast.
- Source/event-grounded values remain legal; for example `blood_soaked` is
  accepted for an event saying the house becomes soaked in blood.
- ARC create/validate/repair prompts now state the same lexical ownership
  contract and explicitly say that temporary activities such as cooking/eating/
  running/fighting are not persistent `set_condition` facts.

Regression commit `851dbfd9fe1a5825fa1ff0a1f35993cafac26bab` adds parser
coverage for rejected ungrounded and accepted grounded free-form conditions.

`run-tests-arc-condition-grounding-101`: **PASS, 28/28 tests green** across:
- `tests.test_state_effect_canonicalization`
- `tests.test_story_arc_structural_guarantees`
- `tests.test_macro_state_enrichment`

This remains within KISS: the rule is deterministic state-data integrity inside
the existing ARC loop, not a new semantic validator or enrichment subsystem.

### Verification in progress

`run-acceptance-amy-condition-grounding-102` is queued against the new code.
Inspect its earliest divergence before making any further change.

Acceptance 098 also produced a later ARC-allocation regression:
- Beat 2 became only the window breach;
- Beat 3 packed kid evacuation/locking plus arsenal retrieval/equipping.

Do **not** repair that allocation preemptively. First determine whether 102 moves
the Segment-1 boundary; then fix the earliest remaining observed failure only.

Always re-read the current `gpt-test-branch` head, this handoff, and newest `gpt-runtime` results before acting.

## Acceptance 102 follow-up: typed clothing effect is the next ARC defect

`run-acceptance-amy-condition-grounding-102` completed against revision
`851dbfd9fe1a5825fa1ff0a1f35993cafac26bab`.

The lexical `set_condition` grounding fix removed the earlier invented
Will/Amber eating effects. Segment 1 improved materially: Request 1 plated
breakfast for both children and ended the cooking action rather than leaving it
underway.

The accepted ARC still contained an earlier architecture defect before Beat
generation:

- E1 correctly described Amy cooking breakfast while wearing the source-defined
  black tank top and denim jeans.
- E1 encoded that clothing with
  `{"op":"set_condition","entity":"Amy","value":"wearing ..."}`.
- Clothing has a dedicated typed operation, `set_clothing`; using
  `set_condition` for wardrobe makes the typed state contract semantically
  inconsistent.
- The same accepted ARC also had later allocation/end-state problems, but they
  remain downstream of this malformed E1 state effect and are not the current
  fix target.

### Targeted probes 103-104

`arc-clothing-op-validation-probe-103` gave Mistral one short rule:
clothing must use `set_clothing`, never `set_condition`. The 24B model
correctly returned INVALID and named the operation mismatch. This shows the
existing ARC VALIDATE/REPAIR loop can own the fix without a new subsystem.

`beat-phase1-simple-prompt-probe-104` used the exact Acceptance-102 Phase-1
events with a much shorter Beat-generation prompt. It produced a concrete
completed breakfast endpoint instead of simply restating that Amy was cooking.
This is evidence that Beat prompting is currently too instruction-heavy for the
24B model, consistent with `docs/PROJECT_NOTES.md`: keep 24B instructions
simple. Do not apply that Beat change until the earlier ARC defect is verified
fixed.

### ARC clothing-operation correction

Production commit `dc083ab4d0277dbb53cf1f45b71211c09999ce13` adds one
direct rule to ARC create/validate/repair:

> Clothing must use set_clothing; never use set_condition for clothing or what
> someone is wearing.

It also shortens the nearby lexical-grounding wording rather than piling on more
instructions.

Regression commit `1065b54cd55c61713f4375e94f1befa97e12bd3a` adds prompt
contract coverage.

`run-tests-arc-clothing-op-106`: **PASS, 29/29 tests green** across:
- `tests.test_story_arc_structural_guarantees`
- `tests.test_state_effect_canonicalization`
- `tests.test_macro_state_enrichment`

### Verification in progress

`run-acceptance-amy-arc-clothing-107` is queued/running against the ARC-only
change. Inspect its accepted ARC before any further production edit.

If 107 removes the clothing/`set_condition` mismatch, then evaluate the
earliest remaining behavior. The already-observed next candidate is Beat 1
completion: Acceptance 102 still omitted some gold completion staging (notably
stove/tool shutdown), and probe 104 shows that concise high-priority Beat rules
may solve the overabstract Beat target. Keep any next prompt change short and
24B-friendly rather than adding more bullets.

## Acceptance 107 follow-up: ARC clothing fixed; Beat 1 completion is now earliest

`run-acceptance-amy-arc-clothing-107` completed successfully against revision
`1065b54cd55c61713f4375e94f1befa97e12bd3a`.

The ARC clothing-operation correction worked:

- E1 now uses two typed `set_clothing` effects for Amy's black tank top and
  denim jeans.
- The previous clothing-as-`set_condition` defect is gone.
- ARC Beat 1 remains the ordinary breakfast baseline and Beat 2 remains the
  inciting zombie/evacuation event.

The earliest remaining acceptance failure moved to Beat generation:

- Required E1 says Amy is cooking breakfast for Will and Amber.
- Generated Beat 1 was still only: “Amy cooks breakfast for Will and Amber while
  wearing a tight black tank top and denim jeans.”
- Director Request 1 therefore left breakfast visibly underway: Amy was still at
  the stove flipping a pancake at the end of Segment 1.
- The locked gold requires a completed domestic beat: the children receive food
  and cooking is finished before the zombie event begins.

This confirms the finding from `beat-phase1-simple-prompt-probe-104`: the
production Beat prompt had the correct endpoint rule buried inside too many
instructions for the 24B model.

### Beat prompt simplification

Production commit `32012b4970c9092966dcaf56e150026852618c6d` replaces the
large Beat-writing instruction block with a compact HIGH-PRIORITY RULES section.

The simplified contract keeps only the important behavior:

- one same-numbered required event per beat;
- complete all material clauses of that event;
- finite activities need a concrete observable endpoint;
- named beneficiaries visibly receive/participate in the result when reasonable;
- do not start the next event/phase early;
- source/required event remain authority; do not invent a new plot;
- preserve prior lasting state/continuity;
- mundane local staging remains Director Request 1 responsibility;
- no camera/sound/dialogue embellishment unless required;
- exact numbering and JSON output.

No semantic architecture changed. ARC and BEATS remain CREATE -> VALIDATE ->
REPAIR loops.

`run-tests-beat-prompt-simplify-108`: **PASS, 74/74 tests green** across:
- `tests.test_llm_prompt_pipeline`
- `tests.test_forward_beat_validation`
- `tests.test_beat_at_a_time_validator`
- `tests.test_beat_retry_hierarchy`
- `tests.test_story_arc_structural_guarantees`

### Verification in progress

`run-acceptance-amy-beat-prompt-simple-109` is queued/running against
`32012b4970c9092966dcaf56e150026852618c6d`.

A production-style Phase-1 probe,
`beat-phase1-production-simple-probe-110`, is also queued behind the full
acceptance. The bridge worker is serial, so 110 may not publish until 109
finishes.

Inspect Acceptance 109 first. If Beat 1 becomes a completed breakfast endpoint,
the next boundary is likely Director Request 1's mundane completion staging
(e.g. stove/tool shutdown) or Segment 2 allocation/ordering; diagnose the actual
first divergence rather than preemptively changing either.

