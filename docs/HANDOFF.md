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
