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

The Beat endpoint state-authority correction is regression-clean, and acceptance 086 exposed the next real failure back inside ARC majority repair: it can still destroy an explicitly authored ordinary-baseline / sudden-inciting-event contrast while compressing setup.

### Verification through 085/086

`current-regressions-085`: **PASS, 104/104 tests green** for the corrected Beat endpoint state-authority contract.

`run-acceptance-amy-current-086`: **PASS as a process, return code 0**, against repo revision `3991db995fbb63e1a49c2cee412bb7fd99a54602` (which includes the Beat endpoint authority correction).

However, the accepted 086 ARC was behaviorally wrong at the first gold boundary:

- Beat 1 required event became: “Amy cooks breakfast for Will and Amber; a zombie breaks the kitchen door window, revealing the threat.”
- Therefore Segment 1 contained the zombie breach and suspense instead of remaining an ordinary safe breakfast.
- Request 1 and Request 2 correctly executed/transcribed that bad assigned Beat 1.

The earliest failure is therefore ARC majority repair again, not Director or formatter behavior.

### 086 causal trace

The **initial created ARC was correct**:

- Beat 1: Amy cooks breakfast for Will and Amber.
- Beat 2: zombie breaks the kitchen door window.
- Beat 3: Amy rushes Will and Amber to the basement and locks the door.
- Later setup/retrieval/equip followed.

After unrelated ARC semantic repairs, validation eventually reached the explicit majority issue at attempt 4:
> Explicit source majority sequence is under-allocated ... 3/8 beats; more than half is required.

The majority-allocation repair then produced the final accepted ARC that merged the breakfast baseline with the zombie breach.

So the merge happens specifically inside **ARC majority allocation repair**.

### Focused probes 087/088

`arc-majority-baseline-boundary-probe-087` reproduced the current production failure using the 086-shaped pre-majority ARC and current repair wording:

> Beat 1: Amy cooks breakfast for Will and Amber; a zombie breaks the kitchen door window...

This confirms the current majority repair contract is sufficient to cause the bad merge independently of the full acceptance.

`arc-majority-protected-baseline-probe-088` added a stronger generic contrast rule:

- when source explicitly establishes an ordinary/calm/safe/normal baseline;
- and then explicitly introduces a sudden/inciting threat/change;
- **never merge the inciting threat/change into the baseline beat**;
- let that baseline consume one outside-sequence beat;
- compress later setup/preparation instead;
- the inciting action may still share with its immediate reaction/escape/containment sequence.

Under that contract Mistral preserved:

- Beat 1: ordinary breakfast only.
- Beat 2: zombie breach + immediate evacuation/lock sequence.

The raw probe omitted one later beat, but production's Python structural validation already rejects missing beat assignments. The semantic contrast behavior itself was corrected.

### Production correction

Production commit `c2f2aa9828b1bc017384bfb20e55d1bf634f198a` strengthens the existing ARC majority repair prompt with a **PROTECTED CONTRAST BOUNDARY**:

- explicit ordinary/calm/safe/normal baseline remains its own beat;
- sudden/inciting threat/change cannot be merged into that baseline;
- the protected baseline consumes one outside-sequence beat;
- later setup/preparation should be compressed instead;
- inciting action may still share with immediate reaction/escape/containment.

This remains entirely inside ARC CREATE -> VALIDATE -> REPAIR. No new semantic subsystem was added.

Regression commit `94733acff47e2b280ed17fae0be922e39d66e31d` asserts the new prompt contract.
A case-sensitive assertion typo was fixed in `25d778d2e90cd0680c5d0c75671e465fcaf209d6`.

`current-regressions-090`: **PASS, 104/104 tests green**.

### Beat endpoint correction still in force

Production commit `4cb0d75e19e0c6c3768a2b28a0cce41f5e315b29` remains active:

- Beat generation turns finite assigned story activities into concrete observable execution targets.
- When explicitly done FOR named people, beneficiaries should visibly receive/participate in the completed result when physically reasonable.
- Beat generation does **not** add durable untyped state changes merely to prove completion.
- Mundane local staging such as setting down utensils / turning off an appliance remains Director Request 1 responsibility.

### Current verification

- `run-acceptance-amy-current-091`: next locked acceptance against the protected-baseline majority repair contract.
- First check: Beat 1 must remain pure ordinary breakfast with no zombie/threat content.
- Second check: majority allocation must still reach at least 5/8 materially emphasized beats.
- Third check: with a clean breakfast beat, evaluate whether the concrete Beat endpoint + Request 1 completion now reaches both kids and natural local completion.
- If Segment 1 passes, continue forward to Segment 2 and fix the next earliest behavioral divergence only.

### Current architectural conclusion

KISS still holds:
- ARC = CREATE -> VALIDATE -> REPAIR
- BEATS = CREATE -> VALIDATE -> REPAIR
- Beat generation = concrete story-level execution target within typed-state authority.
- Request 1 = timed mundane/local staging needed to realize the assigned beat.
- Request 2 = stenographer/formatter.
- Python = deterministic structure/counting/state mechanics.

### Other observed but non-current semantic weaknesses

- `arc-optional-state-effect-strong-probe-053`: Mistral accepted unsupported Hungry state inferred from cooking.
- `beat-lock-omission-current-probe-055` / `056`: Mistral accepted rushing children into the basement as completing a job that also required locking the door.

Do not create separate semantic subsystems merely for these probes. Work them only when end-to-end acceptance makes one the earliest real failure.

Always re-read the current `gpt-test-branch` head, this handoff, and newest `gpt-runtime` results before acting.

