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

Acceptance 078 completed successfully and moved the earliest failure fully into Beat -> Director behavior.

### Acceptance 078: ARC boundary is now good enough; Beat 1 remains too abstract

`run-acceptance-amy-current-078` completed with return code 0.

The accepted ARC preserved the ordinary baseline separately from the inciting zombie event:
- Beat 1: Amy is cooking breakfast for the kids.
- Beat 2: zombie breach + kids to basement + lock + retrieve/equip.
- Beats 3-7: active zombie conflict.
- Beat 8: release kids.

The majority allocation still satisfied the strict-majority requirement, and the prior repair-scope fix held.

So the earliest real failure is no longer ARC.

### Segment 1 failure in 078

Generated Beat 1:
> Amy cooks breakfast for her kids in the kitchen.

Director Request 1 then produced:
- Amy cooking at the stove;
- Will and Amber watching;
- Amy flips a pancake;
- Amy turns toward the kids holding a plate.

It still ended before:
- the completed breakfast visibly reached both kids;
- the stove/tool state was visibly settled.

Request 2 faithfully transcribed Request 1, so the H3 formatter was not the loss point.

### Focused completion-check probe 079 failed

`director-completion-validator-probe-079` tested a tiny separate semantic judge on the exact bad 078 RAW SCENE.

Despite explicit rules saying:
- finite activity underway != complete;
- named beneficiaries must visibly receive the result;
- tools/appliances should be settled at natural completion;

Mistral returned:
`{"valid":true,"issue":""}`

Therefore adding a separate Director completion-validator call would only duplicate the same semantic weakness and add latency/complexity. Do not add that extra semantic stage.

### Earlier-boundary probe 080 succeeded

`beat-executable-endpoint-probe-080` reframed the same requirement one stage earlier:

Required event:
> Amy is cooking breakfast for her kids in the kitchen.

Contract:
- convert it into one executable 8-second video beat job;
- preserve story meaning;
- give finite activities a concrete observable endpoint;
- when done for named people, visibly reach those beneficiaries;
- settle tools/appliances at the natural endpoint;
- do not include NEXT EVENT.

Mistral returned:
> Amy places three plates of scrambled eggs and toast on the kitchen table for Will and Amber.

This is the right kind of executable beat job and does not leak into the zombie event.

### Production correction

Production commit `905d54635d262c1f60f8b8a2c958b1a7bee5d96f` strengthens `build_beat_generation_messages()`:

- finite assigned activities must become EXECUTABLE CLIP JOBS with concrete observable endpoints;
- if the job is explicitly ongoing/interrupted/unresolved, it may remain incomplete;
- finite activities done FOR named people should end with those beneficiaries visibly receiving/participating in the completed result when physically reasonable;
- ordinary tool/appliance shutdown/settling belongs in the beat endpoint when it naturally completes the authorized activity and does not conflict with the next job.

Regression commit `03ec1b4c5d66c6c8405935f4b431dee9133e3d54` adds prompt coverage.
A whitespace-only assertion issue in the new test was fixed in `f296d140aca3b06ee61c563ad606cc144df91912`.

`current-regressions-082`: **PASS, 104/104 tests green**.

### Current verification

- `run-acceptance-amy-current-083`: queued/running.
- First check: generated Beat 1 itself should now be a concrete executable endpoint rather than the abstract phrase “cooks breakfast.”
- Second check: Director Request 1 should then visibly realize that endpoint.
- Request 2 should preserve it.
- If Segment 1 passes, continue to Segment 2 and fix the next earliest real divergence only.

### Current architectural conclusion

The KISS architecture still holds:
- ARC = CREATE -> VALIDATE -> REPAIR
- BEATS = CREATE -> VALIDATE -> REPAIR
- Beat generation owns turning macro required-events into concrete clip execution targets.
- Request 1 owns timed realization of the assigned beat.
- Request 2 is a stenographer/formatter.
- Python owns deterministic structure/counting/state mechanics.

Important lesson from 079/080:
> When Mistral cannot reliably judge semantic completion after the fact, prefer giving it a clearer executable target earlier rather than adding another validator stage.

### Other observed but non-current semantic weaknesses

- `arc-optional-state-effect-strong-probe-053`: Mistral accepted unsupported Hungry state inferred from cooking.
- `beat-lock-omission-current-probe-055` / `056`: Mistral accepted rushing children into the basement as completing a job that also required locking the door.

Do not create separate semantic subsystems merely for these probes. Work them only when end-to-end acceptance makes one the earliest real failure.

Always re-read the current `gpt-test-branch` head, this handoff, and newest `gpt-runtime` results before acting.

