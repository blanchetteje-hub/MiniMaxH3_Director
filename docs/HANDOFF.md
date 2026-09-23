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

## Current architectural conclusions / lessons learned

These are the main conclusions from the acceptance history so far. Read this
section before adding new architecture or new prompt rules.

- **The two-loop KISS architecture still holds.** Nothing in the current gold
  benchmark has demonstrated a need for separate semantic enrichment, coverage,
  claims, effect-proof, or state-preparation pipelines. Keep ARC and BEATS as
  CREATE -> VALIDATE -> REPAIR loops unless end-to-end evidence directly
  implicates the architecture itself.

- **24B prompt overload is the dominant recurring failure mode.** Several real
  failures occurred even when the correct rule was already present in the prompt.
  When the same task was reduced to a few simple rules, Mistral often produced the
  correct result immediately. Do not respond to every model mistake by adding more
  instructions. Prefer deleting, narrowing, and separating responsibilities.

- **Each LLM stage should have one narrow job.**
  - ARC decides story allocation, required clip jobs, and persistent state effects.
  - Beat CREATE turns one assigned ARC event into one executable visual endpoint.
  - Beat VALIDATE judges that beat; the proven single-beat validator remains the
    semantic backstop.
  - Director Request 1 expands the accepted beat into timed physical staging and
    mundane completion details.
  - Director Request 2 is a stenographer/H3 formatter and should not creatively
    repair upstream semantics.
  - Continuity describes current rendered/prompt-derived state; it does not own
    durable Subject identity.

- **Python owns deterministic integrity, not arbitrary story semantics.** Good
  Python checks include schema/range/ID/dependency integrity, typed state
  operations, and narrow lexical ownership constraints that prevent fabricated
  authoritative data. Python should not decide whether a character ought to be
  afraid, whether an action is narratively appropriate, or other free-form English
  semantics.

- **Canonical state is authoritative and therefore must be conservative.** An
  invented state_effect can bias every downstream stage. Only persistent facts
  actually established by the owning required_event should be committed. Temporary
  activities such as cooking, eating, running, or fighting are not persistent
  conditions. Clothing belongs in set_clothing, not free-form set_condition.

- **Director Request 1 / Request 2 separation is currently supported by evidence.**
  Request 1 has successfully supplied mundane local staging such as turning off an
  appliance or setting down a utensil. Request 2 generally preserves Request 1
  faithfully. When the story-level endpoint is missing, fix Beat/ARC upstream
  rather than asking Request 2 to compensate.

- **Sampling transport matters, but sampling was not the root cause of everything.**
  Explicit ARC/Beat sampling was previously overwritten by formatter defaults and
  that plumbing bug was fixed. Later probes showed that even with correct sampling,
  oversized prompts could still make the 24B model ignore important rules.

- **The locked gold benchmark is the authority.** Do not accept "looks pretty good"
  output when the behavioral boundary is wrong. Trace each mismatch back to the
  earliest incorrect stage and fix that stage only.

- **Current direction: simplify before redesigning.** The evidence does not yet
  justify removing ARC, BEATS, or Director. It does justify aggressively reducing
  24B prompt scope, especially ARC create/validate/repair prompts when acceptance
  proves they are overloaded.

Recurring anti-pattern to avoid:

> A local-model mistake leads to another prompt instruction; accumulated
> instructions overload the model; the overloaded model causes a new mistake;
> another instruction gets added.

Prefer instead:

> Give each 24B call the minimum information needed for one job, let the existing
> validator/repair loop handle semantic mistakes, and keep deterministic
> bookkeeping in Python.

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

### Bridge hot-reload caveat

The running `tools/chatgpt_llama_bridge.py` process does **not** hot-reload its
own Python code after ChatGPT commits bridge changes.

- Production/test code under `gpt-test-branch` is refreshed by the bridge's
  detached execution worktree before `run_tests` / `run_acceptance` jobs.
- But a new bridge job kind, new bridge argument handling, timeout behavior, or
  other change inside `tools/chatgpt_llama_bridge.py` itself is not active
  until the user's local checkout is pulled and the bridge process is restarted.

This mattered for the new `planning_only` acceptance flag: an already-running
older bridge ignored the field and launched the old full acceptance command.
Do not diagnose that as planning-mode slowness.


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

## Acceptance 109 follow-up: Beat prompt still too large; exact five-rule prompt succeeds

`run-acceptance-amy-beat-prompt-simple-109` completed against revision
`32012b4970c9092966dcaf56e150026852618c6d`.

The first Beat remained too abstract:

> Amy, wearing a tight black tank top and denim jeans, cooks breakfast for Will
> and Amber in the kitchen.

Director Request 1 did improve mundane shutdown by turning off the stove and
setting down the spatula, but neither child actually received breakfast. The
locked Segment-1 target therefore still failed at Beat creation before Director
formatting.

The accepted 109 ARC also contains a separate later defect: Phase 1's
`required_end_state` claims Amy and the kids are in the basement and that Amy
has retrieved her weapons, even though Phase-1 events do not retrieve the
weapons. This later ARC issue must be addressed after the earlier Segment-1
boundary is cleared.

### Probes 110-111

`beat-phase1-production-simple-probe-110` reproduced the production failure
with the then-current roughly ten-rule prompt: it again returned only that Amy
cooks breakfast.

`beat-phase1-four-rule-exact-probe-111` used the same source story and exact
Phase-1 required events but stripped Beat creation to the essential rules. It
returned:

> Amy serves breakfast to Will and Amber at the kitchen table.

This isolates prompt overload as the cause. The 24B model can infer the correct
finite endpoint from the existing ARC event when the Beat task is kept small.

### Minimal Beat-creation correction

Production commit `427069ed07e75e1d267cd84793e62892a332f429` rewrites
`build_beat_generation_messages()` as a deliberately small 24B prompt.

Beat creation now receives only:

- SOURCE STORY;
- the current phase's numbered required-event text;
- an optional immediately previous Beat for continuity;
- explicit correction/beat-instruction/phrase-exclusion text when present;
- the required JSON shape.

The high-priority behavior is reduced to:
- complete each assigned required event visibly;
- finish finite everyday activities to their natural visible result;
- show named beneficiaries receiving/participating in the result when reasonable;
- do not start the next required event early;
- continue from the previous Beat without repeating it;
- one concise sentence per Beat with exact numbering.

Full CURRENT PHASE JSON, NEXT PHASE prose, phase end-state summaries, recent-beat
blocks, state-effect metadata, and the previous large instruction list are no
longer sent to Beat CREATE. ARC owns allocation; the frozen Beat validator owns
semantic rejection afterward.

Regression commit `d095952f5b3cd3342297cc814d543b7adffcc46e` updates prompt
contract tests so they enforce the minimal prompt rather than rewarding prompt
bulk.

`run-tests-minimal-beat-create-112`: **PASS, 72/72 tests green** across:
- `tests.test_llm_prompt_pipeline`
- `tests.test_forward_beat_validation`
- `tests.test_beat_at_a_time_validator`
- `tests.test_beat_retry_hierarchy`
- `tests.test_beat_plan_localization`
- `tests.test_generate_beats_mode`

### Verification in progress

`run-acceptance-amy-minimal-beat-create-113` is queued against the minimal
Beat CREATE prompt.

Inspect Segment 1 first. If Beat 1 now serves breakfast and Request 1 preserves
that result, move to the next earliest divergence. Acceptance 109 already
suggests the next upstream candidate may be ARC allocation/end-state integrity:
its Phase-1 end state claimed weapon retrieval too early, and its Beat-2/Beat-3
boundary does not match the locked gold's safe-room handoff. Do not patch that
until 113 establishes that Segment 1 has moved.

`arc-end-state-simple-probe-114` is also queued behind 113. It isolates the
Acceptance-109 Phase-1 end-state defect with only three simple validation rules.
Use its result to decide whether ARC validation should receive the same 24B prompt
simplification treatment after Segment 1 is cleared.

## Acceptance 113 timeout follow-up: 6k context and ARC simplification

run-acceptance-amy-minimal-beat-create-113 did not produce a semantic
acceptance result. The bridge killed the command after the 3600-second timeout.

Two concrete issues were found instead of simply increasing the timeout.

### Minimal Beat prompt dropped the Subject block

The first minimal Beat CREATE rewrite removed the compact parsed Subject list.
Production has a deterministic guard that refuses to send Beat-generation
requests when those parsed Subject IDs are absent.

This was fixed in commit 781959d2723fb08c4bb5ee3d893cdeecdbe4c62f by restoring only
the compact Subject IDs to the minimal Beat prompt. The regression test was
corrected to preserve the compact form rather than re-expanding full Subject
descriptions.

### The code still carried 13B-era context assumptions

The current local 24B runtime operates around a ~6k context window, while the
repository still advertised/used older assumptions such as a 14,000-token input
budget and an 8,000-token default completion request.

README commit 21fbd94ec522d9ddcb37374b1854eb125ae4bafa removes the old
~21k 13B guidance.

Production commit 7cacf52d63cf56f2c1a6add67ae3b8b26fb8a349 adds a generic
context-window guard:

- local context budget: 6044 tokens;
- normal input budget: 4500 estimated tokens;
- 128-token safety margin;
- at least 256 completion tokens must remain;
- ask_llm() clamps requested completion length to the remaining context instead
  of sending impossible 8k completions;
- an input that leaves no usable completion room fails fast with an instruction
  to simplify that stage prompt.

This is deterministic transport protection, not semantic architecture.

### Probe 114: free-text ARC end state is not reliably validated

arc-end-state-simple-probe-114 gave Mistral only three simple rules and an ARC
phase whose end state claimed Amy had retrieved weapons even though no event in
that phase retrieved them. Mistral still returned VALID.

Therefore this defect is not just prompt overload. A free-text
required_end_state is redundant authority that the 24B validator cannot
reliably police.

Following the architectural lessons, no new end-state checker was added.

Instead:

- new ARC output no longer asks the model to author required_end_state;
- old saved arcs containing it remain parse-compatible;
- Python ignores the legacy prose as story authority and derives the internal
  phase handoff deterministically from the phase's final required_event;
- required_events + typed state_effects are now the single ARC story authority.

Production commits:
- cfb76cc3de185f4956d88a7870057e6a61cdb096 — simplify ARC
  create/validate/repair prompts for the 24B model;
- 3b6d45430bb092b36ad075491a7c2b1ff6cc3b22 — remove model-authored
  required_end_state from the strict schema and derive the compatibility handoff
  from the final event.

The ARC prompts were deliberately reduced instead of adding more rules. Tests
that previously asserted verbose prompt wording were updated to assert the
minimal semantic contracts, prompt-size budget, and the new single-authority
handoff behavior.

run-tests-arc-simplify-118: PASS, 91/91 tests green.

### Current verification

arc-create-amy-minimal-probe-119 is queued/running with the locked Amy story
and the new compact ARC CREATE prompt.

Inspect 119 before another full acceptance. If the compact ARC produces a
reasonable 8-beat allocation, queue the next locked acceptance against the
current branch. The first semantic target remains Segment 1: Beat CREATE should
turn the ordinary breakfast event into a completed serving endpoint. After
Segment 1 clears, inspect the Beat-2/Beat-3 safe-room handoff against gold rather
than repairing downstream Director prose.

## ARC majority-allocation follow-up: global reasoning fails; localized REPAIR succeeds

The current Mistral 24B runtime is constrained to about 6k context, but new
probes show that the remaining majority-allocation defect is **not** primarily a
context-overflow problem.

Very small ARC prompts still reproduced it:

- `arc-create-majority-boundary-probe-121`: explicit 5/8 budget and "start by
  Beat 4" correctly compressed the pre-conflict setup, but the model still spent
  Beat 8 on resolution alone and therefore produced only four conflict beats.
- `arc-create-majority-final-beat-probe-123`: even with a ~459-token input and
  an explicit rule that Beats 4-8 must belong to the active zombie-fighting
  sequence, the model moved retrieval/equipping into Beats 4-5 and kept Beat 8
  resolution-only.
- `arc-majority-repair-minimal-probe-124`: a ~380-token global REPAIR prompt
  literally instructed that Beats 4-8 must all be conflict and Beat 8 must
  combine terminal kill + resolution; Mistral still returned a resolution-only
  Beat 8.

This means adding more global prompt wording is the wrong direction.

### Deterministic ARC sampling

Constraint allocation is planning/validation work rather than creative prose.
At temperature 0, `arc-majority-create-temp0-probe-125` improved materially:

- Beat 1 breakfast baseline;
- Beat 2 breach + evacuation + lock;
- Beat 3 retrieve + equip;
- Beats 4-7 conflict;
- Beat 8 resolution-only.

The front allocation therefore fits the three outside-majority beats correctly,
but the model still resisted merging terminal conflict + immediate resolution.
A global temperature-0 REPAIR probe (`126`) showed the same tail failure.

Production commit `91e7c24dad9e398526727b4298d39b1a8df0fb44` therefore
separates stage sampling:

- ARC CREATE / VALIDATE / focused majority validation / REPAIR use a
  deterministic profile: temperature 0, repeat_penalty 1.15, seed 42;
- Beat CREATE keeps its creative 0.65 profile;
- `ask_llm()` now accepts an explicit seed;
- the frozen Beat validator's documented seed 42 is now actually sent instead of
  relying on a random fallback.

### Focused ARC tail REPAIR

`arc-majority-tail-repair-probe-128` tested the same failure with the valid
prefix frozen and only Beats 7-8 editable. It succeeded immediately:

- Beat 7 remains nonterminal zombie combat;
- Beat 8 kills the last zombie, establishes the blood-soaked house, and
  immediately lets the kids out.

That is the strongest current evidence about 24B behavior: **global arc rewrites
lose constraints; smallest-range repair can satisfy them.**

This does **not** add another semantic pipeline. It changes how the existing ARC
REPAIR step operates when ARC VALIDATE has already localized the exact
resolution-tail majority defect.

Production commits:

- `8aeba152eee7a307bee8bba733f49a609782eb1a` — focused two-event
  majority-tail repair helpers;
- `57a5135b41169daa9d9fb09cd3b11ffa49c13e8a` — invoke that focused
  repair inside the existing ARC VALIDATE -> REPAIR loop before falling back to
  whole-arc repair;
- `310a9f10c7d8c4a0907d550b1fc2199ca169f76e` — regressions for exact
  localization, fixed IDs/dependencies, and conservation/movement of existing
  typed state_effects;
- `e5c7f3afa1335ce8104fc7851930134308ab8931` — deterministic ARC and
  validator-sampling regressions.

The focused repair activates only when focused majority evidence shows the exact
case where an otherwise contiguous strict-majority span is one beat short because
the final global beat is resolution-only. Other failures continue through normal
ARC REPAIR.

### Planning-only locked acceptance

Full 8-segment acceptances 113 and 120 each timed out after an hour, obscuring
whether the time was spent in ARC/BEATS or Director/continuity.

A KISS diagnostic path now reuses the existing production
`minimax.py --generate-beats 8` mode inside the same locked Amy acceptance
workspace:

- `213c70989d01879a395381b3d88ecdefbd83b919` — acceptance runner
  `--planning-only`;
- `cefb95454f67daced53dcd9937d8beb971eba56d` — bridge support;
- `c95530e57e36f8deba0f75976055ea22eda98eda` — command regression;
- `run-tests-planning-acceptance-harness-127`: **23/23 passing**.

This captures only `story_arc.json` and `beats.txt`, avoiding eight
Director/continuity segments while ARC+BEATS are still the failing boundary.

### Retry-loop / timeout observability

ARC still has nested retry budgets derived from `BEAT_RETRY_ATTEMPTS = 10`.
At current 24B latency, persistent nonconvergence can therefore consume tens of
minutes. Do not merely increase acceptance timeouts.

Commit `812c0e1a69d91da9b86ebfb6df0e48e132201c38` makes future bridge
timeouts preserve partial process output and the latest acceptance `run.log`
when available, instead of losing all evidence.

### Verification currently queued

The bridge worker is serial. An older planning-only job,
`run-planning-acceptance-amy-129`, was queued before the deterministic
ARC/localized-repair changes and may occupy the worker until its 30-minute
timeout. Treat its semantics as stale unless its reported repository revision
proves otherwise.

Behind it:

- `run-tests-arc-local-repair-129` — focused regressions for current code;
- `run-acceptance-amy-planning-only-130` — the meaningful locked Amy
  ARC+BEATS verification against the latest branch at execution time.

Inspect 130's repository revision before drawing conclusions. If ARC majority
allocation and Beat 1 completion pass, the next likely gold boundary is the
Beat-2/Beat-3 safe-room handoff: gold ends Beat 2 with the steel door open and
moves kids-through + door close/lock + weapon retrieval/equipping into Beat 3.
Do not patch that boundary until current planning output proves it is the
earliest remaining failure.

## Focused ARC verification after localized-repair changes

Current focused verification remains consistent with the architectural lessons:
small editable ranges work much better than global rewrites.

- `run-tests-arc-local-repair-129`: **PASS, 75/75 tests green** across the
  focused ARC/local-repair, prompt, state-effect, and acceptance-runner modules.
- `arc-front-handoff-temp0-probe-131`: with only the first three jobs editable,
  deterministic Mistral produced the locked-gold handoff cleanly:
  - Beat 1 ordinary breakfast baseline;
  - Beat 2 zombie breach + Amy rushes Will/Amber to the protective door and
    **opens it**, without putting the kids through, locking it, or retrieving
    weapons;
  - Beat 3 kids go through + Amy closes/locks the door + retrieves/equips pistol
    and katana.
- `arc-tail-state-effects-probe-132`: with only Beats 7-8 editable, Mistral
  correctly moved the terminal threat, blood-soaked-house, and child-release
  typed state effects to Beat 8 while leaving Beat 7 as nonterminal fighting.

These probes are evidence that both known Amy boundary corrections are solvable
by the 24B model when the repair scope is localized. They are **not** justification
for adding literal basement/zombie special cases.

Do not implement a new front-handoff repair path yet. First obtain the current
production ARC+BEATS output and confirm that this is the earliest remaining
failure after Beat 1 completion and majority-tail repair.

## Planning-only acceptance 133: phase arithmetic was the earliest failure

After the bridge restart, `run-acceptance-amy-planning-only-133` finally ran
the intended ARC+BEATS-only command. It failed before semantic ARC validation:
ARC CREATE repeatedly emitted impossible or overlapping LLM-authored phase
ranges (for example 8-10 in an 8-beat story, or a new phase starting at Beat 7
after Beat 7 was already consumed). The deterministic structural validator was
correct to reject them.

This is bookkeeping failure, not story semantics. Do not weaken the structural
validator and do not add more phase-arithmetic instructions to the 24B prompt.

`arc-create-flat-events-probe-134` removed phase authoring and asked Mistral
only for eight chronological required clip jobs. It returned a structurally
clean E1-E8 chain immediately. Its semantic majority allocation was still wrong
(weapons remained outside the three-beat setup budget and the last beat was
resolution-only), which is useful separation: flat ARC output fixes the
bookkeeping failure but does not hide the remaining semantic ARC work.

Production direction is therefore:

- ARC CREATE still owns semantic required-event allocation.
- ARC VALIDATE still owns semantic judgment, including the focused majority
  evidence check.
- ARC REPAIR still owns semantic correction.
- Python now owns phase_number/beat_start/beat_end bookkeeping only, wrapping
  each accepted flat required event in a deterministic one-beat phase for the
  existing downstream machinery.
- This is not a new semantic pipeline and does not change the two-loop KISS
  architecture.

Production commits:

- `4ea1f9200a3c8520b3be3dc941fa500b916a01ad` — ARC CREATE and whole-ARC
  REPAIR now use a flat events schema/parser and deterministic Python phase
  wrappers.
- `a2969c20a271c2dd4c660481bc0334d9c3571f98` — regressions for flat ARC
  parsing and Python-owned phase bookkeeping.
- `1b18c6165bf7b3749f8bccb4581b13f868ed3db8` — preserve the explicit
  required_end_state ownership contract in the simplified ARC prompt.
- `run-tests-flat-arc-bookkeeping-136`: **PASS, 78/78 tests green**.

The bridge is current and healthy; no restart is required.

Next verification: run a fresh planning-only locked Amy acceptance against the
flat ARC production path. The first result to inspect is whether ARC CREATE now
reaches semantic validation reliably. If it does, fix the earliest semantic
defect reported by that run rather than adding more global prompt rules.

The old adjacent-beat/global fidelity audit helpers still exist in `minimax.py`,
but they are not the active path that would solve the current ARC allocation
boundary. Do not revive them merely to catch the Amy safe-room split; that would
reintroduce semantic layers contrary to the current KISS conclusions.



## Planning-only acceptance 137: ARC validation subject-guard mismatch

`run-acceptance-amy-flat-arc-planning-137` proved the flat ARC CREATE path
itself is now structurally usable: the first model response returned a clean
eight-event E1-E8 chain with deterministic Python phase wrappers.

The run then failed before semantic ARC validation. The validation prompt
correctly included the compact subject identifiers produced by
`_format_beat_arc_subject_names()`, but the deterministic
`verify_subjects_in_beat_messages()` call compared that prompt against the
full raw `subjects.txt` lines. Because the raw descriptive lines are
intentionally not present in the compact ARC validator prompt, every validation
attempt was falsely rejected with:

`Parsed subjects.txt information was not included in the beat generation prompt`

That deterministic mismatch caused repeated ARC REPAIR/VALIDATE cycling until
the planning acceptance timed out. It was not a semantic ARC failure.

Production commits:

- `6ade7c7ed20cf2f7e117eb6e78ee7cca970ec0ef` — ARC validation now verifies
  the same compact subject representation that its prompt actually contains.
- `4c5a145b49da09262606d9981238dad526269c22` — regression for compact ARC
  validation subject guarding.
- `run-tests-arc-subject-guard-139`: **PASS, 79/79 tests green**.

A separate unconstrained probe,
`arc-flat-majority-repair-probe-138`, showed that a whole-list majority repair
can still lose the required eight-event count when no JSON schema is enforcing
it; it returned only six events. Do not treat that as the current production
failure because production ARC REPAIR uses a strict eight-event response
schema. The next evidence boundary is a fresh planning-only Amy acceptance after
the subject-guard fix.



## Planning-only acceptance 140: timeout output buffering hid the failing stage

`run-acceptance-amy-flat-arc-planning-140` timed out after 1800 seconds but
published an empty `run.log` and empty captured stdout/stderr. This does **not**
establish an ARC or BEATS semantic failure.

The acceptance runner launches `minimax.py` with stdout piped through Python.
Without an unbuffered child environment, MiniMax output can remain in the
child's userspace buffer. The runner also wrote each received line to
`run.log` without explicitly flushing the file. When the bridge timeout kills
the process tree, both buffers can disappear, leaving no evidence.

This was fixed only in the diagnostic harness:

- `ac100e0074aa38d3fe923b7924a983d8d7212714` — acceptance child processes
  receive `PYTHONUNBUFFERED=1`; each mirrored log line is printed/flushed and
  flushed to `run.log` immediately.
- `e1ef8c9c37375c2fb875bce849d68dff1ec8fac6` — regression for the
  unbuffered child environment.
- `run-tests-acceptance-live-output-141`: **PASS, 80/80 tests green**.

No production ARC/BEATS semantics changed in this fix.

`run-acceptance-amy-flat-arc-planning-142` is the next evidence boundary. It
runs the same planning-only locked Amy path after the subject-guard fix, but
with timeout-safe live logging. If it times out, inspect its preserved
`run.log` and fix the earliest observed production failure rather than
increasing the timeout or guessing from elapsed time.



## Acceptance 142 follow-up: broad ARC validator semantic input fixed

The preserved log from `run-acceptance-amy-flat-arc-planning-142` identified the
first real production failure after flat ARC CREATE and the subject-guard fix:
broad ARC VALIDATE was rejecting structurally valid Amy event plans for semantic
reasons caused by its own input representation.

Three focused bridge probes isolated the causes:

- `arc-flat-validation-events-only-probe-143`: removing Python phase-wrapper
  metadata stopped phase-bookkeeping complaints, but the validator still
  rejected relational wording because DEFINED SUBJECTS exposed only
  `<Subject N>` IDs without names.
- `arc-flat-validation-named-subjects-probe-144`: supplying aliases
  (`<Subject 1> = Amy`, etc.) fixed the identity problem; the next false
  rejection was treating repeated zombie-combat continuation beats as invented
  events even though the source explicitly says that process occupies the
  majority of the film.
- `arc-flat-validation-sparse-sequence-probe-145`: with flat event input,
  named Subject aliases, and one explicit rule that an extended/repeated source
  process may span multiple beats, the same candidate validated cleanly.

Production changes:

- `4ada6f02db2c296066a253752ee5007e3604f51e` — broad ARC VALIDATE now sees
  only authoritative flat required_events/state_effects, compact Subject aliases
  retain names, and source-authorized extended/repeated processes are explicitly
  valid across multiple beats.
- `7a952041c207ee6b360e377987074f640d974a9a` — subject-alias regression.
- `a3243fb4621690b83b2b6bbd2c42d3671c7be588` — flat semantic-input and
  repeated-process validator regression.
- `run-tests-arc-semantic-input-146`: **PASS, 81/81 tests green**.

This does not add a semantic layer. ARC remains CREATE -> VALIDATE -> REPAIR;
the change only removes Python bookkeeping from the semantic validator's input
and restores information the validator actually needs.

Next evidence boundary: a fresh planning-only locked Amy acceptance. Do not add
the previously probed safe-room/front-handoff repair unless that acceptance
proves it is the earliest remaining failure.



## Planning-only acceptance 147: broad ARC validator still over-judges source fidelity

`run-acceptance-amy-flat-arc-planning-147` reached broad ARC VALIDATE with a
structurally clean flat eight-event plan, but validation rejected facts that
were already present or were never required by the source. The earliest false
rejection demanded clothing for Will/Amber even though the source never
specifies it. Later retries falsely claimed the kids' identities or breakfast
action were absent despite relational wording and the explicit Beat-1 event.

Targeted probes isolated the contract:

- `arc-validation-source-clothing-probe-148`: removing the unsupported
  clothing requirement exposed another false "missing equip" rejection.
- `arc-validation-minimal-coverage-probe-149`: a smaller coverage/order task
  still criticized legal bundling of adjacent sequential source actions.
- `arc-validation-minimal-bundling-probe-150`: limiting broad validation to
  missing explicit source actions/states, source-order contradiction, or an
  unsupported major plot addition validated the same candidate cleanly.

Production correction applied:

- broad ARC VALIDATE is explicitly a narrow source-fidelity check;
- it must not invent clothing/appearance/name requirements absent from source;
- order-preserving adjacent source actions may legally share one required_event;
- pacing, detail level, style, bundling policy, and majority allocation are not
  broad-validator judgments;
- the existing focused majority check remains the owner of majority allocation;
- a regression locks this narrow contract.

This preserves ARC CREATE -> VALIDATE -> REPAIR and adds no semantic layer.

Verification:
- `run-tests-arc-source-fidelity-152`: **PASS, 82/82 tests green**.

Current evidence boundary:
- `run-acceptance-amy-flat-arc-planning-153` is queued behind the passing
  regressions.
- Inspect ARC VALIDATE first. If the broad source-fidelity check passes, follow
  the production path forward and fix only the next earliest demonstrated
  failure.
- Do not implement the safe-room/front-handoff repair unless acceptance 153
  proves it is the earliest remaining failure.


## Planning-only acceptance 153 clears ARC + BEATS; do not overfit the safe-room handoff

`run-acceptance-amy-flat-arc-planning-153` completed successfully end-to-end in
planning-only mode:

- broad ARC source-fidelity validation eventually passed;
- focused majority validation/repair produced a true 5/8 conflict allocation;
- ARC was saved successfully;
- all eight Beat CREATE jobs were generated;
- the frozen single-beat validator accepted Beats 1-8 on their first attempts;
- planning exited 0 with a complete `story_arc.json` and `beats.txt`.

The final planning allocation still differs from the locked gold around the first
escape handoff:

- Beat 2 is only the window breach/reaction;
- Beat 3 contains evacuation + containment/locking + weapon retrieval/equipping;
- gold carries meaningful evacuation progress through Beat 2 and leaves
  containment/locking/arming for Beat 3.

Targeted probes 154-166 tested whether this should become another production ARC
validator/repair rule. The answer is currently **no**:

- 154 correctly detects the original trigger-only / overloaded-next-beat shape.
- 155 whole-ARC repair moves evacuation progress into Beat 2, but 156 still
  falsely rejects that improved allocation.
- a second whole-ARC repair (160) overshoots by moving the children fully inside
  during Beat 2, which violates the locked boundary.
- focused/localization probes 157-159 cannot infer the intended threshold
  reliably without being told the benchmark-specific door-opening answer.
- 163/164 show a supposedly narrow handoff validator still returns the same
  rejection after meaningful movement has already been shifted into Beat 2.
- 165 demonstrates a generic threshold instruction can attach the opening action
  to the wrong entrance.
- 166 demonstrates another CREATE prompt rule is ignored and can regress the
  majority allocation by spending Beat 4 on weapon preparation.

Do not add a separate handoff semantic pipeline, deterministic English heuristic,
or more global ARC prompt wording from these probes. The local 24B evidence is
not reliable enough to support it.

The exact physical act of opening an entrance is also finer-grained than the
source story explicitly states. Beat CREATE / Director may legally supply such a
necessary physical prerequisite when expanding an assigned movement job. The
planning-only harness therefore should not be treated as final proof that the H3
gold boundary fails.

Next evidence boundary: run the **full locked Amy acceptance** against the
current code. Compare Segment 1 first, then Segment 2. If Segment 2 actually
omits the evacuation-to-threshold behavior in final H3 output, trace that concrete
failure back to the earliest responsible stage. Do not preemptively add another
ARC sub-validator.



## Full acceptance 167: earliest real failure is Beat 1 action collapse

`run-acceptance-amy-full-167` completed planning successfully and entered the
Director pipeline, but capture stopped after Segment 1 because Segment 2 Request 1
could not confirm Beat-2 completion after three attempts.

The **earliest** behavioral failure is already Segment 1, before that Segment-2
failure:

- ARC E1 correctly says Amy is cooking breakfast for her kids.
- Beat CREATE rewrote that as a static after-state:
  `Amy stands in the kitchen with a finished breakfast on the table...`
- Director Request 1 therefore never had the cooking/serving transition left to
  stage. It began from finished breakfast and only placed a final item on the
  table.
- The locked gold requires the activity plus completion: cook/serve both
  children, settle utensils, and shut off the stove.

This is a Beat CREATE contract defect, not Director formatting.

Targeted probes:
- 168 added “show the assigned action itself” but produced only activity
  underway and lost the completion endpoint.
- 169 reframed the rule as a **visible transition: show the activity, then show
  it finishing** and produced
  `Amy ... cooks breakfast and serves it to Will and Amber...`.
- 170 repeated the same successful prompt using the exact current production
  Beat CREATE sampling
  (`temperature=.65, top_p=.90, presence=.15, frequency=.15,
  repeat_penalty=1.05`) and also succeeded.

Therefore no Beat sampling change is justified yet. Production Beat sampling is
unchanged.

Production changes:
- `65680b1bc6479cef3f9cb7c67c3cb99d416c2207` — replace the old finite
  activity rule with a transition contract: include the assigned activity, then
  show it finishing; never output only activity-underway or only after-state.
- `343c67966e6df723f213406fc12a6b7eaba17b5a` — prompt regression updated to
  lock that contract.
- `884ac671b3c89e4f0826cbd508d7bdc71e28a75d` — PROJECT_NOTES now explicitly
  records LLM sampling as an evidence-driven tuning lever and current baselines.

Future iterations may tune temperature/top-p/min-p/repeat/presence/frequency
penalties when targeted probes show a real gain. Record every production sampling
change and the exact successful/failed probes here or in PROJECT_NOTES. The
frozen single-beat validator remains unchanged unless evidence directly
implicates it.

Verification:
- `run-tests-beat-transition-contract-171`: **PASS, 82/82 tests green**.
- `run-acceptance-amy-full-172` is the active full locked acceptance against
  the Beat transition-contract change.

Inspect Segment 1 first when 172 publishes. Only after Segment 1 clears should
Segment 2's Request-1 completion failure become the active target.



## Acceptance 172: Beat CREATE sampling and capture parser

Full acceptance 172 generated all eight H3 prompts. Segment 1 improved after the
finite-transition prompt change: Amy visibly cooks and serves both children.
However the production Beat-1 job itself still remained activity-only under the
old Beat CREATE sampling, so Director had to infer completion and did not fully
settle the activity.

Sampling probes on the production-shaped Beat-1 prompt:
- 173 changed only repeat_penalty 1.05 -> 1.15 and produced activity + completion.
- 174 kept RP 1.15 but raised top_p 0.90 -> 0.95 and regressed to activity-only.

Production change:
- `d471209a86609abb94aa9059b7e828cdeda3d738` — Beat CREATE
  repeat_penalty is now 1.15; all other Beat sampling values remain unchanged.
- `648662688254957a9ddfd90029f8dab0c4e55384` — sampling regression.

Acceptance 172 also exposed a harness-only capture bug: Segment 2's H3 end marker
was immediately followed by `Added States:` on the same line, so the parser
incorrectly marked Segment 2 missing even though the prompt was generated.
- `ff547b98e8eed3ad001d15ec6f330e577eae8c3e` and
  `682ab9befd154e6abb4b1ff99294c59d58f9a4ca` make the parser tolerate
  concatenated trailing text while still terminating on the segment number.
- `269fefbcd20ab51000ea55987b1ea22486ff3dc3` adds the regression.

Verification:
- `run-tests-capture-and-beat-rp115-176`: **PASS, 83/83 tests green**.
- `run-acceptance-amy-planning-rp115-177` is the active cheaper production
  check for the RP 1.15 Beat CREATE change.

Inspect Beat 1 as soon as 177 publishes. If it now contains activity + completion,
queue the full locked acceptance immediately. If it does not, do not stack more
prompt wording; continue one-dial sampling probes from the documented baseline.


## Planning 177 and exact Beat sampling isolation

`run-acceptance-amy-planning-rp115-177` completed successfully, but Beat 1
still ended as activity-only:
`Amy ... cooks breakfast for Will and Amber.`
So RP 1.15 alone did not generalize.

The discrepancy was traced to hidden Beat CREATE sampling:
- Beat CREATE had no explicit seed, so each production request used a random seed.
- `top_k=20` and `min_p=0.0` were inherited from the Mistral formatter rather
  than owned by the Beat stage.

Exact-profile probes:
- 178: seed 42, top_k=20, min_p=0, RP 1.15 -> activity-only.
- 179: same but RP 1.05 -> activity-only.
- 180: top_k 20 -> 0 with RP 1.15 -> still activity-only.
- 181: min_p 0 -> 0.05 with RP 1.15 -> activity + explicit completion.
- 182: min_p 0.05 with RP 1.05 -> activity-only.

Production conclusion:
- the useful combination is RP 1.15 + min_p 0.05;
- Beat CREATE should own a complete explicit profile so formatter defaults do not
  silently affect it;
- Beat CREATE is now deterministic at seed 42.

Production commits:
- `b2835cccbd3f501d908ae486d7da47d540c2bb75` — explicit Beat CREATE profile:
  temperature .65, top_p .90, top_k 20, min_p .05, presence .15,
  frequency .15, RP 1.15, seed 42.
- `a105f523aeff737c74644ef9b1fb0f4a146ed57a` — regression locks that profile.

Next: focused regressions, then planning-only Amy. If Beat 1 includes activity +
completion there, queue the full locked acceptance immediately.


### Verification after explicit Beat CREATE profile

- `run-tests-explicit-beat-sampling-183` failed only because an old regression
  still asserted that Beat `min_p` must equal the formatter default. That
  expectation was obsolete once Beat CREATE began owning its complete profile.
- `3cc990c5792228b7108ecb66d3298df2765da5a6` updates the regression to
  assert Beat settings are independent of formatter defaults and that the
  explicit seed avoids random-seed generation.
- `run-tests-explicit-beat-sampling-184`: **PASS, 83/83 tests green**.
- `run-acceptance-amy-planning-explicit-beat-185` is the active production-path
  verification. Inspect generated Beat 1 first. If it includes both the cooking
  action and a visible completion, immediately queue the full locked acceptance.
  If it remains activity-only, do not revert to hidden formatter defaults; use
  the explicit deterministic profile as the new baseline for one-dial tuning.



## Planning 185: explicit Beat sampling still activity-only; schema contract is next boundary

`run-acceptance-amy-planning-explicit-beat-185` completed successfully under
the fully explicit deterministic Beat CREATE profile
(`temperature=.65, top_p=.90, top_k=20, min_p=.05, presence=.15,
frequency=.15, repeat_penalty=1.15, seed=42`).

Beat 1 nevertheless remained activity-only:
`Amy ... cooking breakfast for her young kids Will and Amber.`
It still omitted a visible completion endpoint, even though the user prompt says
finite activities must show both the action and its completion.

This means the sampling profile is no longer the unexplained difference between
successful direct probes and the production path. The remaining production-only
difference is the strict JSON `response_format`. Its `beat_text` schema
description previously asked only for a "concise, complete sentence" and did not
carry the finite-action transition requirement.

Focused production change:
- `1ce50459b4a847cf73d911b464615a8064a8fd24` — align the structured
  `beat_text` schema description with the existing Beat CREATE contract:
  finite assigned activities must include the activity itself and its visible
  completion endpoint in the same sentence; activity-only and after-state-only
  outputs are explicitly disallowed.
- `3876447b6789835f28cf53690aee1ad3dd27a3d7` — regression locks the schema
  description to the same finite-action contract.

No new validator or repair stage was added. BEATS remains CREATE -> VALIDATE ->
REPAIR; this only removes contradictory instructions between Beat CREATE's user
prompt and structured-output schema.

Current verification:
- `run-tests-beat-schema-contract-186` is queued/pending.
- If 186 passes, queue a fresh planning-only Amy acceptance and inspect Beat 1
  first. Do not tune another sampling dial until the schema-aligned production
  request is observed.



## Acceptance 187 follow-up: finite clip completion belongs in ARC jobs, not the frozen Beat validator

`run-tests-beat-schema-contract-186`: **PASS, 83/83 tests green**.

`zzz-run-acceptance-amy-planning-schema-contract-187` still produced an
activity-only Beat 1 even after the Beat CREATE prompt, structured schema, and
explicit deterministic sampling profile all required a finite activity endpoint:

`Amy ... cooking breakfast for her young kids Will and Amber.`

The frozen Beat validator also accepted that candidate. Targeted probes showed
that simply strengthening the Beat VALIDATE wording is not a reliable fix:

- 188 reproduced the current validator result: activity-only Amy -> VALID.
- 189 added a finite-activity completion rule in CHECKS -> still VALID.
- 190 made the rule explicit that gerund/in-progress wording does not imply
  completion -> still VALID.
- 191 moved that rule into the system prompt -> still VALID.
- 192 supplied a contrastive generic invalid/valid example -> activity-only Amy
  still VALID.
- 193 verified the completed control remains VALID.

Do **not** modify the frozen 400/400 Beat validator for this boundary. The local
24B repeatedly refuses to infer an endpoint that is absent from CURRENT JOB.

The earliest semantic defect is therefore upstream: ARC says each required_event
is an executable clip job, but E1 copied the source's progressive wording
(`cooking breakfast`) instead of assigning a complete clip job.

Targeted ARC probes:
- 194 added one finite-activity clip-job rule to ARC CREATE and Mistral rewrote
  E1 as `finishes cooking breakfast...`, proving the planner can express the
  endpoint. This unconstrained diagnostic had unrelated shape/allocation errors,
  so only the E1 semantic behavior is evidence.
- 195 gave ARC REPAIR the same boundary and it cleanly changed only E1 to
  `cooking breakfast ... and serving it to them` while preserving the other
  seven events and existing clothing state effects.

Production change:
- `17354e780055bee07415a3691d68336c1f9604f8` — ARC CREATE and whole ARC
  REPAIR now share the rule: a finite source activity assigned wholly to one
  beat must be a complete clip job that reaches a natural visible endpoint;
  merely progressive/in-progress wording is insufficient. The endpoint may state
  only the ordinary result directly implied by completing the activity and may
  not add a new plot event/outcome.
- `6dbe8c4526524705f374da306708ee84d0680ca0` — regression locks the same
  contract in ARC CREATE and REPAIR prompts.

This preserves KISS:
ARC CREATE -> VALIDATE -> REPAIR remains the only ARC semantic loop, and
BEATS CREATE -> VALIDATE -> REPAIR remains unchanged. No semantic Python
heuristic and no additional validator layer were introduced.

Verification:
- `run-tests-arc-finite-clip-contract-196`: **PASS, 83/83 tests green**.
- `zzz-run-acceptance-amy-planning-finite-arc-197` is the active planning
  acceptance against the upstream ARC finite-clip-job contract.

Inspect ARC E1 and generated Beat 1 first in 197. If E1 is now a complete clip
job and Beat 1 preserves its endpoint, immediately queue the full locked
acceptance. If ARC REPAIR later removes the endpoint, fix only that observed
repair path.



## Planning 187 follow-up: finite completion belongs in the ARC clip job

`run-tests-beat-schema-contract-186`: **PASS, 83/83 tests green**.

`zzz-run-acceptance-amy-planning-schema-contract-187` completed successfully
against revision `0592caac5a09ea3a922dc215062d567979be3665`, but Beat 1 still
collapsed to activity-only wording:

> Amy ... cooking breakfast for her young kids Will and Amber.

The schema-aligned Beat CREATE contract therefore did not clear the production
boundary. More importantly, the frozen Beat validator accepted that incomplete
finite-action Beat as VALID.

Targeted validator probes 188-193 made the same boundary explicit. The 24B Beat
validator returned VALID for the activity-only breakfast candidate even when the
prompt directly emphasized the missing visible endpoint and even in contrastive
invalid/valid probes. Do not expand the frozen Beat validator around this case;
its proven job remains judging a Beat against the assigned clip job, not repairing
a clip job whose ARC wording is itself only an in-progress activity.

The earlier authoritative defect is ARC E1 itself:

> Amy ... cooking breakfast for her young kids.

That is not a complete executable clip job. If a finite source activity is wholly
assigned to one beat, ARC must describe the activity reaching its natural visible
endpoint rather than handing BEATS an in-progress state and asking downstream
stages to infer how it finishes.

Focused local-model evidence supports that ownership:

- `arc-create-finite-clip-job-probe-194` produced an E1 that **finishes cooking
  breakfast** under a small flat-ARC contract.
- `arc-repair-finite-clip-job-probe-195` repaired the exact current E1 to
  **cooking breakfast and serving it to the kids**, without disturbing unrelated
  events.

Production commits:

- `17354e780055bee07415a3691d68336c1f9604f8` — ARC CREATE and ARC REPAIR
  now require a finite activity assigned wholly to one beat to reach a natural
  visible endpoint in that required_event; the endpoint may expose the ordinary
  result implied by completion but may not add a new plot event/outcome.
- `6dbe8c4526524705f374da306708ee84d0680ca0` — regression coverage for the
  finite clip-job ARC contract.

Verification:

- `run-tests-arc-finite-clip-contract-196`: **PASS, 83/83 tests green**.
- `zzz-run-acceptance-amy-planning-finite-arc-197` is queued as the next locked
  planning-only production-path check.

Inspect 197's generated ARC E1 first. If ARC now authors a complete breakfast
clip job, inspect Beat 1 next. Only after both carry activity + completion should
a full locked acceptance be queued. If 197 still emits an in-progress ARC E1,
probe the existing ARC VALIDATE/REPAIR loop on that exact candidate before adding
any new rule elsewhere.

KISS remains unchanged: ARC CREATE -> VALIDATE -> REPAIR and BEATS CREATE ->
VALIDATE -> REPAIR. This correction moves responsibility upstream to the stage
that owns the required clip job; it does not add a semantic pipeline.


## Planning 197: ARC CREATE still compresses explicit majority sequence

`zzz-run-acceptance-amy-planning-finite-arc-197` timed out inside ARC planning after repeated validation/repair cycles. The earliest defect is now creation, before Beat generation: ARC CREATE repeatedly authored only 2/8 zombie-fighting beats even though its own majority budget required at least 5/8. ARC VALIDATE correctly rejected that allocation. Repair sometimes reached 4/8 but did not converge reliably, so downstream repair should not be asked to recover the same deterministic allocation mistake on every fresh ARC.

Production change:
- `4b45ef526299d66e0e86c854361158307788f946` — ARC CREATE now states the missing semantic consequence of its existing numeric majority budget: when the source says a process occupies the majority, allocate that process across the required numeric majority of beat jobs rather than compressing repeated activity into one or two summary events. Sparse source-authorized conflict may be expressed as distinct moments of the same process; no new major plot/character/location/outcome is allowed.

This is a prompt-only correction inside existing ARC CREATE. KISS remains ARC CREATE -> VALIDATE -> REPAIR and BEATS CREATE -> VALIDATE -> REPAIR; no new stage or Python semantic heuristic was added.

Next: run focused regressions, then a planning-only Amy acceptance. Inspect the first freshly-created ARC before repair: the zombie-fighting process should occupy at least 5/8 beats while preserving the calm baseline, inciting break-in, kids-to-basement/arsenal setup, and final release through adjacent bundling where required. If creation clears that boundary, continue to the earliest later failure rather than tuning hypothetical cases.


## Majority-create verification queued after Planning 197

The ARC CREATE majority-allocation correction from `4b45ef526299d66e0e86c854361158307788f946` is now protected by prompt-contract regression coverage:

- `fe81b3d115f0dc3c22191508a1209095c632088a` — locks the numeric-majority, anti-compression, and source-authorized-moment wording in ARC CREATE.
- Initial bridge regression `yyy-01-run-tests-arc-majority-create-contract-198` found only one obsolete test phrase (`coherent source-authorized escalation`) from the previous wording; production behavior was not implicated.
- `feba7e16b92ef5784fcdc4e44c78a52a525426cd` updates that old assertion to the current `distinct coherent source-authorized moments` contract.

Queued verification order:
1. `yyy-02-arc-create-majority-current-probe-199` — current full ARC CREATE prompt at production ARC sampling, checking whether first creation allocates the explicit majority process across at least 5/8 beats while retaining the finite breakfast endpoint and source order.
2. `yyy-03-run-tests-arc-majority-create-contract-201` — rerun focused regressions after the stale assertion fix.
3. `zzz-run-acceptance-amy-planning-majority-create-200` — fresh locked planning-only Amy acceptance against the current branch.

Do not make another production semantic change until those results publish. Inspect the first newly created ARC before repair; if creation now satisfies the majority allocation, continue to the next earliest observed failure. If it still compresses the majority process, revise only ARC CREATE/its sampling based on that exact evidence rather than expanding downstream repair architecture.


### Probe 199 result

`yyy-02-arc-create-majority-current-probe-199` completed with the current full ARC CREATE wording and production ARC sampling. Even with the explicit numeric-majority rule, unconstrained Mistral still compressed the zombie-fighting process to only a few beats and lost structural discipline (duplicate/missing beat assignments and malformed state-effect shapes). This is consistent with the earlier global-planning probes: prompt wording alone may still be insufficient for reliable global allocation.

Do not treat 199 alone as the production verdict because `llama_chat` does not apply production's strict structured response schema. The decisive current evidence remains `zzz-run-acceptance-amy-planning-majority-create-200`, which is queued behind the corrected regression rerun `yyy-03-run-tests-arc-majority-create-contract-201`.


## Planning 200: majority repair converges; accepted E1 is still not a complete clip job

`zzz-run-acceptance-amy-planning-majority-create-200` completed successfully against revision `feba7e16b92ef5784fcdc4e44c78a52a525426cd`.

What moved:
- ARC CREATE still initially compressed the explicit majority process, but the existing ARC VALIDATE -> REPAIR loop eventually converged to a valid 5/8 zombie-conflict allocation.
- All eight Beats were generated and the frozen Beat validator accepted them.
- Therefore the majority-create problem is currently an efficiency/nonconvergence risk, not the earliest defect in the final accepted plan from this run.

Earliest accepted-output defect:
- Final ARC E1 remained: `Amy ... cooking breakfast for her young kids.`
- That is still progressive/in-progress wording, despite ARC CREATE/REPAIR's finite-activity clip-job rule.
- Beat 1 consequently remained activity-only as well.
- This is earlier than the later Beat-3 omission/packing issues and remains the current semantic target.

### Do not add finite-activity judgment to broad ARC VALIDATE

Targeted validation probes showed that Mistral cannot apply that rule reliably in the broad validator:
- `arc-validate-finite-clip-exact-202` failed to identify E1 and instead falsely rejected the already-complete evacuation/arming event.
- `arc-validate-finite-clip-control-203` falsely rejected a valid middle beat of the explicitly extended zombie-fighting process as unfinished.

So broad ARC VALIDATE remains the narrow source-fidelity check; no new finite-activity validator/sub-validator was added.

### Structured ARC schema mismatch

The production-only discrepancy is that `build_flat_arc_response_format()` described `event` as only a non-empty string, while the ARC prompt requires each finite one-beat activity to reach a natural visible endpoint. This mirrors the earlier Beat CREATE structured-schema mismatch.

Production work:
- `8186e200962d59e1309fbd985bcda4b89361e773` attempted to align the ARC event schema, but initially landed the description on the wrong event schema because the same one-line field shape exists in multiple response formats.
- `18c982384da73c966882c042014121f528b9c9fa` added the regression that exposed that placement mistake.
- `59e4f31abc2922036b0284676eda31b9f0ee771f` moved the description to the correct `build_flat_arc_response_format()` event field and removed it from the unrelated focused majority-tail schema.

The correct flat-ARC event schema now says:
- one executable clip job per beat;
- if a finite source activity is wholly assigned to the beat, include its natural visible endpoint rather than only in-progress wording;
- an explicitly extended/repeated process should describe that beat's concrete portion without prematurely ending the whole process.

Bridge queue cleanup:
- stale, superseded unprocessed `aaa-*` jobs and an obsolete old planning-153 job were removed from `gpt-runtime` because their filenames sorted ahead of current verification and blocked the worker.
- stale acceptance 205 was also canceled after the first schema patch was proven misplaced.

Current verification queue:
1. `yyy-05-run-tests-arc-finite-schema-206` — corrected focused regression suite.
2. `zzz-run-acceptance-amy-planning-arc-finite-schema-207` — fresh production planning check using the corrected flat-ARC structured schema.

Inspect ARC E1 first in 207. If E1 includes both breakfast activity and its ordinary visible completion and Beat 1 preserves it, immediately return to the full locked acceptance. If E1 remains progressive-only, the structured-schema hypothesis is disproven and the next fix should remain inside ARC CREATE/REPAIR rather than broadening ARC VALIDATE.


## Director completion reset after Planning 207

Planning acceptance `zzz-run-acceptance-amy-planning-arc-finite-schema-207` passed the focused regressions but disproved the flat-ARC response-schema hint as a solution for E1: ARC/Beat 1 still said Amy was cooking breakfast without encoding a visible endpoint. Additional probes 208-212 showed that neither a shorter ARC CREATE prompt, a contrastive finite-activity example, broad ARC REPAIR enforcement, nor a focused finite-activity ARC validator reliably identified/fixed that defect without false positives. Do not add another ARC validation subsystem for this issue.

Re-reading the prior full acceptance evidence showed the more useful boundary: Director Request 1 in full run 172 already inferred the missing serving actions from the activity-only Beat 1, but returned `beat_complete=true` while leaving its own completion contract partially unsatisfied (the end state still reported cooking / active kitchen work). Request 1 already owns local completion, beneficiaries, and settling activity-only tools/appliances.

Sampling/prompt probes 213-221 showed that Request 1 can often realize the correct endpoint, but no tested temperature/presence/repeat/min-p tweak or duplicated local checklist was reliably better across the exact current Beat-1 wording. Do not make a sampling change from those probes.

Concrete implementation mismatch found:
- `DIRECTOR_RAW_SCENE_RESPONSE_FORMAT` described `raw_scene` only as a string and `beat_complete` only as a bare boolean, even though the Request-1 prompt gives `beat_complete` strict semantic completion meaning.
- `7b27c164fbed132fee55dc5dbb17896b21384414` aligns the strict response-schema descriptions with the existing Request-1 completion contract; this does not add a validator or stage.
- `7b51850688127cdbcb1d641d266911694c6d7ea6` locks that response-schema contract in tests.
- Bridge regression `yyy-06-run-tests-director-completion-schema-222` passed 85/85 tests.
- Full locked acceptance `zzz-run-acceptance-amy-full-director-completion-schema-223` is the only remaining queued/live verification. Do not stack further changes while it runs.

For 223, inspect Segment 1 first. The required behavioral evidence is: both Will and Amber receive/participate in the completed breakfast; cooking is no longer ongoing at the handoff; and any active cooking tool/appliance used only for that activity is visibly settled when reasonable. If Segment 1 clears, continue to the earliest later acceptance failure. If it does not, this schema-description fix is disproven and should not be expanded into new ARC machinery.


## Acceptance 223: Request 1 trusts one false completion boolean

Full locked acceptance `zzz-run-acceptance-amy-full-director-completion-schema-223` completed successfully, but Segment 1 still failed the gold completion boundary. Request 1 returned `beat_complete=true` while only Amber received the cooked eggs; Will did not receive breakfast, and the cooking tool/appliance state was not visibly settled before the handoff. Therefore the prior schema-description-only change did not solve the behavior.

The earliest responsible runtime boundary is now explicit: `request_segment_llm()` retries Request 1 only when the model's single `beat_complete` boolean is false (plus deterministic structure/name checks). It has no independent completion evidence inside the same response.

Focused KISS change:
- `6f433c1da41f711870a29b38b9efd1776f27b98c` expands the existing Request-1 structured response with three required boolean completion claims: `finite_activity_complete`, `named_beneficiaries_complete`, and `activity_tools_settled`. The existing Request-1 retry loop now requires all three plus `beat_complete` to be true. A false claim feeds a precise completion reason back into the same retry; no extra LLM call, semantic Python heuristic, ARC validator, Beat validator, or new pipeline stage was added.
- Legacy/mock callers that predate the expanded response schema remain compatible in the parser, while production strict structured output requires all new fields.
- `d1afe6c23a2beca3c239b10c32c142b7d0a0d830` locks the expanded response contract and proves a false beneficiary/tool completion claim causes Request 1 to retry and accept only the corrected second response.

Verification:
- `yyy-07-run-tests-director-explicit-completion-224`: **PASS, 86/86 tests green**.
- `zzz-run-acceptance-amy-full-director-explicit-completion-225` is the only live verification. Inspect Segment 1 first. Do not stack another prompt/sampling/ARC change while 225 runs.


## Qwen 27B differential: planning improves sharply; finite-breakfast blind spot remains

After switching the local runtime to `qwen3.8-27b-obliterated`, targeted comparison jobs were run before changing production model routing.

- `aaa-qwen-director-seg1-completion-226`: direct Request-1-shaped probe. Qwen still treated the breakfast beat as an in-progress establishing activity and ended with Amy still cooking. Because `llama_chat` does not apply production strict `response_format`, this is supporting evidence only, not the production verdict.
- `aab-qwen-amy-planning-227`: production planning-only acceptance with `--model qwen`. Qwen's first ARC CREATE attempt immediately satisfied the explicit zombie-majority allocation and passed ARC validation on attempt 1. This is materially better than the repeated Mistral repair churn seen in prior Amy runs. However ARC/Beat 1 still preserved the activity-only breakfast wording.

Interpretation: Qwen appears substantially better for global ARC allocation, but it does not automatically solve the finite-breakfast endpoint. Do not replace the frozen 400/400 Mistral Beat validator solely from this result. Stage-specific model routing is now a plausible direction if full Qwen Director evidence supports it.

A concrete Request-1 contradiction was also found before the production Qwen comparison: the expanded structured schema required `raw_scene`, `finite_activity_complete`, `named_beneficiaries_complete`, `activity_tools_settled`, and `beat_complete`, while the prose OUTPUT CONTRACT still told the model to return exactly `raw_scene` and `beat_complete`. `dd7c1f1d8acd934a38230afeb21d5143fdf44d71` aligns the prose contract with the five-field schema; `35f79517919496d7fc11b42344b6e7b93affe38e` adds regression coverage. Regression job 228 then exposed only one stale assertion string, removed in `631ee3b514900d71b38a01d1c200458b6c6ea269`.

`aab-run-acceptance-amy-full-qwen-229` is the active clean full-production comparison. Inspect Segment 1 first, then compare later ARC/Director behavior. Do not make a production model-routing change until 229 provides the structured Request-1 evidence.


## Primary model direction: Qwen 27B

As of 2026-09-23, the active local model has been switched from Mistral 24B to `qwen3.8-27b-obliterated` for ongoing MiniMax H3 iteration.

Current optimization policy:
- Treat **Qwen 27B as the primary model target** for the overall pipeline.
- Optimize for a **single-model architecture first** across ARC -> BEATS -> Director -> formatting/continuity.
- Do not prematurely split the pipeline across multiple models just because one isolated stage currently favors Mistral.
- Mixed-model routing remains a fallback only if a clear, repeatable model-specific limitation survives reasonable prompt/schema/formatter integration work.
- Keep in mind that `qwen_formatter.py` is much less battle-tested and less utilized than `mistral_formatter.py`; failures in Qwen full-pipeline runs must be separated into **model capability** vs **formatter/integration maturity** before drawing conclusions.

Evidence so far:
- Qwen planning-only acceptance 227 produced a valid ARC on the **first ARC CREATE attempt**, including the required majority zombie sequence, which is materially better than the repeated Mistral ARC repair churn seen in prior Amy runs.
- Qwen still preserved the activity-only breakfast wording in ARC/Beat 1, so the finite-breakfast endpoint remains an active semantic boundary rather than a solved issue.
- The prior Mistral 24B Beat validator benchmark remains an important reference point (400/400), but the current engineering direction is to see how far the Qwen model can be made to carry the whole system before accepting hybrid routing complexity.


## Qwen full run 229: model-profile mismatch found in Beat validation

Full Qwen acceptance `aab-run-acceptance-amy-full-qwen-229` reached Segment 4 before Request 1 exhausted its retry budget. Segment 1 still ended with breakfast ongoing despite two Request-1 retries, so the finite-activity handoff remains unresolved. More importantly, the generated Beat sequence exposed an earlier Qwen integration defect: Beat 4 said Amy kills attacking zombies **until the last zombie falls dead**, while Beats 5-7 still contained additional zombies. Equivalent premature terminal wording appeared in later repeated fight beats. The single-beat validator incorrectly accepted those candidates.

The cause was not a new validator-rule gap. Production already contained both benchmark profiles, but `_active_beat_validation_settings()` always returned `MISTRAL_24B_SETTINGS`. The locally benchmarked Qwen profile differs materially in prompt packaging: `QWEN38_27B_SETTINGS` uses `user_prompt_only=True`. The Qwen validator benchmark that previously scored 399/400 was therefore not the prompt shape being used in production.

Production fix:
- `6166779a959e6c5ba0d7de527c06f0585a2984bb` — select `QWEN38_27B_SETTINGS` when the active formatter/model is Qwen; keep the Mistral profile for Mistral.
- `bceba74afdfb79a008acb718f9bc444454f4b59a` and `5c4a9a1936f71d0495c9699db194d7ab8a58eca3` — regression coverage verifies Qwen uses the benchmarked user-only validator prompt shape and restores formatter state cleanly.
- `aaa-run-tests-qwen-validator-profile-231`: **PASS, 87/87 tests green**.

`aab-run-acceptance-amy-planning-qwen-validator-232` is the active verification. Inspect Beats 4-7 specifically for premature terminal/exhaustive wording and whether the corrected Qwen validator rejects/regenerates those candidates. Do not add a new validator rule before this run resolves the benchmark-profile mismatch.


## Qwen planning 232: validator profile fixed, repeated-process Beat CREATE churn exposed

`aab-run-acceptance-amy-planning-qwen-validator-232` confirmed that production now uses the Qwen validator profile, but exposed two separate observed issues:

1. **Beat CREATE duplicate churn:** When ARC intentionally assigned the same repeated zombie-killing process to Beats 4-7, Qwen often copied the required-event sentence verbatim. The deterministic duplicate-beat guard rejected Phase 6 ten times and restarted the entire beat process. This happened across multiple full-process retries before a later ARC happened to vary the repeated event wording enough for Beat CREATE to proceed. The correction string was technically being passed, but it did not clearly distinguish “same story-level process” from “same clip wording.”
2. **Validator semantic exhaustion miss remains:** The final successful plan avoided literal “last/final zombie” wording in intermediate beats, but Beat 6 still said Amy “finishes them off” while Beat 7 contained more zombies. Qwen’s single-beat validator accepted this. This is a narrower semantic NEXT JOB miss and should be addressed separately from Beat CREATE duplication.

Focused Beat CREATE fix:
- `1c0d56a7a87900c50a25a4436604a38db41aef96` tells Beat CREATE that an ARC-authorized repeated/ongoing process must become a distinct concrete clip instance, must not copy the prior beat/required-event sentence verbatim, and must not use terminal/exhaustive wording unless the assigned event is the terminal instance. Duplicate retry feedback now includes the prior beat and tells the model to regenerate a distinct clip instance without changing the story-level job.
- `707044f0cf878e44b6c1ee78a9967c3143feadbe` locks the repeated-process prompt contract.
- `aaa-run-tests-qwen-repeated-process-233`: **PASS, 87/87 tests green**.

`aab-run-acceptance-amy-planning-qwen-repeated-process-234` is the active verification. Inspect whether Beats 4-7 are generated without the prior ten-attempt duplicate churn. After that, independently address the observed validator miss for wording such as “finishes them off” when NEXT JOB continues the same repeated process.


## Qwen planning 234 and validator benchmark-parity fixes

`aab-run-acceptance-amy-planning-qwen-repeated-process-234` confirmed the repeated-process Beat CREATE fix. The ARC, all eight Beat CREATE calls, and all eight validations completed on first attempts; the prior Phase-6 duplicate-beat churn disappeared. The final fight beats were distinct concrete instances without premature `last/final` wording. However, Beat 8 still omitted the explicit assigned action “Amy kills the last zombie” and jumped directly to the blood-soaked aftermath + opening the basement. The single-beat validator incorrectly accepted it.

Direct Qwen probes 236/237 exposed the reason: Qwen explicitly reasoned that the last-zombie kill had already happened in PREVIOUS FINAL BEAT, even though CURRENT JOB assigned that action to the current beat. This is a validator ownership error, not a general inability to compare multi-part jobs.

Focused validator ownership fix:
- `f31d86a75e85b3f1af4f007388c6caad663676c0` — production validator now states that PREVIOUS FINAL BEAT is history only: it constrains possibility but cannot satisfy, replace, or excuse any action/result explicitly assigned to CURRENT JOB. Every such requirement must be visibly accomplished by CANDIDATE BEAT.
- `8b577eb06b1583062f043186a1968158a2c9c72d` — the benchmark prompt is kept aligned with production for the same rule.
- `7ccd1c1476b5896a5165919b9d611180070b99c1` — regression coverage.
- `aae-run-tests-current-job-ownership-240`: **PASS, 103/103 tests green**.

The same probe set showed that “finishes them off” in an intermediate fight beat is reasonably interpretable as finishing the current batch rather than the whole later sequence. Do not add a phrase-specific validator ban for that wording absent stronger evidence.

A second benchmark mismatch was then found: Qwen’s 399/400 validator benchmark disables thinking using llama.cpp `chat_template_kwargs={"enable_thinking": false}`, while production validator requests were sending generic `thinking="off"` plus per-request `chat_template`/`jinja`. The benchmark harness does not send those generic fields.

Benchmark-transport alignment:
- `db91ab8fc0a27a38149290b65e229023c299c5c9` — production beat validation now matches the benchmark transport: Qwen receives `chat_template_kwargs.enable_thinking=false`; validator requests no longer send per-request `thinking`, `chat_template`, or `jinja` fields.
- `8f75f42a99f51dfd09eb774229645fe8f95a56cf` — transport regression coverage.
- `aag-run-tests-qwen-benchmark-transport-242`: **PASS, 104/104 tests green**.

Independent transport hardening from run 229:
- `6e5b04ceb005cf46299a09a68f51cea2dd859f7d` — only remove structured `response_format` on a schema-specific HTTP 400; unrelated 400s such as “No models loaded” retain schema enforcement on subsequent attempts.
- `efff4875d541010b7752d3d816283dfd35b5a994` — fallback classification regression coverage.
- `aac-run-tests-response-format-fallback-235`: **PASS, 89/89 tests green**.

`aah-run-acceptance-amy-planning-qwen-benchmark-transport-243` is the active verification and is the first production Qwen planning run with both explicit CURRENT JOB ownership and benchmark-matched validator transport. Inspect Beat 8 first; if it now rejects/regenerates the omitted last-zombie action, planning can move forward to a fresh full Director acceptance.


## Qwen planning 243: CURRENT JOB ownership fixed; ARC state-effect regression exposed

`aah-run-acceptance-amy-planning-qwen-benchmark-transport-243` completed successfully with the Qwen validator using benchmark-matched user-only/thinking-disabled transport. The prior Beat-8 omission was fixed: the finalized Beat 8 explicitly kills the remaining zombies, leaves the house blood-soaked, and gets Will/Amber out.

The next earlier planning defects were:
- Beat 1 still remained an activity-only breakfast target (`preparing breakfast`) rather than a visible finite endpoint.
- Beat 2 changed the assigned `locks the door` action into merely `slams the door shut`, yet the validator accepted it.

Inspection of the accepted ARC revealed the more fundamental architecture regression: **none of the required_events carried state_effects at all**. In particular, the event that explicitly locks the basement door had no `set_barrier_state=locked`, and the event that equips the pistol/katana had no equipment state effects. This contradicts the locked architecture in this handoff: persistent state is authored in ARC required_event.state_effects, semantically checked/repaired in the ARC loop, and committed by Python only after Beat validation.

Historical regression coverage already existed in `tests/LLM/test_story_arc_state_effect_regression.py` for exactly this contract (missing barrier/location/equipment/threat/clothing effects), but those pytest/live tests are not part of the normal unittest bridge suite. The current simplified production ARC prompt had also lost the explicit persistent-state-coverage rule.

Restoration, still inside the existing ARC CREATE -> VALIDATE -> REPAIR loop:
- `48bae8275ca0e0c2717c10cabb921cfeee47d8ae` — fresh flat ARC events must explicitly include a `state_effects` array; CREATE says [] is only for events with no supported persistent fact; VALIDATE rejects missing supported persistent facts; REPAIR owns adding/preserving them. Legacy nested/saved arcs remain load-compatible through the older parser path.
- `afe550c95a09f8e025998733f2d8365d1e208877` — restores the generic `CHECK PERSISTENT STATE COVERAGE` semantic rule across location, containment/release, held/equipped objects, barriers, persistent objects, terminal threats, clothing, and persistent environment conditions while explicitly excluding temporary actions/reactions.
- `5df6f942bcf34e0bd34a33eb7f22eb32f80000c4` — structural/prompt regression coverage requires state_effects in fresh flat ARC output and locks the persistent-state-coverage wording.
- `aai-run-tests-arc-state-effects-required-244`: **PASS, 105/105 tests green**.

`aaj-run-acceptance-amy-planning-qwen-state-effects-245` is the active verification. Inspect the accepted ARC first: Beat 2 must carry locked barrier state, Beat 3 must carry equipped weapon state, and terminal/persistent final outcomes should be represented without invented temporary conditions. Then inspect finalized Beats 1-8 for the earliest semantic mismatch.
