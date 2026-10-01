# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth. This file is intentionally short and should contain only the current implementation state, active constraints, latest findings, and immediate next work. Historical chronology belongs in `docs/HANDOFF_OLD.md`.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active development branch: `gpt-arc-refresh`

Runtime/bridge mailbox branch: `gpt-runtime`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is used for development/evaluation only, not as a production dependency.

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` is the one narrative source of truth. Intermediate artifacts may organize or concretize the story but may not become competing narrative authority.

Fix the earliest demonstrated production/acceptance failure. Do not compensate downstream for an upstream semantic error.

## Current planning architecture

The active planner is source-span / chapter-first.

1. Python exposes exact source units from `story.txt`.
2. Narrow LLM classifiers identify only the semantics Python cannot derive directly:
   - source-unit split gate;
   - TERMINAL;
   - HARD_RESET;
   - visible responsibility;
   - local MERGE vs NEW_TASK relation;
   - typed persistent state effects.
3. Python derives chapter boundaries, source ownership, beat counts, event ordering, and required-event assignments.
4. Beat CREATE expands assigned events into concise executable beats.
5. Beats run through CREATE -> VALIDATE -> REPAIR -> VALIDATE until accepted.
6. Accepted required-event state effects are applied by Python only after validation.

Do not fall back to the old broad ARC semantic architecture when a source-span extractor fails. Repair the source-span path.

## Beat CREATE / REPAIR policy

Beat generation is the current optimization focus.

Beat CREATE receives:
- full `story.txt` under `SOURCE FILM`;
- `KNOWN SUBJECTS`;
- canonical `CHARACTER FACTS`;
- only the chapter/local `ASSIGNED EVENTS`;
- `PREVIOUS BEAT` when one exists.

The full story is context only. `ASSIGNED EVENTS` determine what may happen now.

Beat CREATE and Beat REPAIR use:
- temperature `0`;
- seed `42`;
- repeat penalty `1.15`;
- high reasoning;
- 1024-token reasoning budget.

This is intentional: testing showed GPT-OSS 20B became substantially less reliable on Beat writing at any nonzero temperature.

Beat repair should make the smallest textual change necessary and must re-enter normal validation before acceptance.

## LLM responsibility split

Treat the local 20B as capable but instruction-fragile.

Prefer:
- short prompts;
- one semantic responsibility per call;
- Python-owned truth + narrow extractor + deterministic comparison;
- deterministic arithmetic/bookkeeping/state application.

Avoid:
- broad holistic validators when Python already owns the invariant;
- stacking more prose onto a prompt that is already being ignored;
- combining semantic inference and bookkeeping into the same local-model call.

Sampling:
- ARC create/repair, character canon, and Director RAW remain creative sampling calls.
- Beat CREATE/REPAIR are temperature 0 despite being writing calls.
- Validators/extractors are deterministic: temperature 0, seed 42, low reasoning, 128-token reasoning budget.
- llama-server should run with `--deterministic`; this is a process flag, not a request field.
- target context size is 8192.

## Canonical character data

`canonical_data.txt` is user-authored character information.

For each character, the system establishes:
- age;
- clothing;
- gender.

Explicit file values are copied. Missing required values may be chosen once by the local model. Extra facts are extracted only when explicitly authored.

`character_canon.json` is cached from the canonical-data text and reused deterministically.

`subjects.txt` remains separate and is used for visual subject identity/mapping.

## Current canonical state direction

Python owns canonical state.

Recent direction from the current iteration:
- state capture should remember persistent facts broadly;
- this may include rooms, objects, threat condition/injuries, concrete locations, inventory, barriers/windows, etc.;
- broad capture does **not** mean every stored fact must later be injected into every prompt;
- relevance filtering can be added later, analogous to subject definitions being injected only when relevant;
- an observed `UNSPECIFIED` value must never erase a previously established concrete fact.

The important distinction is:
- **catalog state broadly**;
- **inject state selectively later**.

Do not weaken state capture merely because prompt filtering is not implemented yet.

## Accepted-Beat persistent state capture

After a Beat has passed semantic + coherence validation and required-event effects are staged, a deterministic accepted-Beat extractor observes concrete persistent end-state facts established by the finalized text.

The extractor may concretize source abstractions, for example:
- authored `safe location` -> Beat-established `closet`;
- generic inventory state -> explicit held/stored object placement.

Captured facts are merged into canonical Python state and the persistent-state ledger.

This path intentionally captures incidental but persistent world facts (for example a room or object) so later stages can use them if relevant.

### Latest acceptance finding: 2710

`generate-beats-2710-gpt-accepted-state` showed that accepted-Beat capture is successfully retaining useful continuity:
- concrete kid locations;
- kitchen objects;
- pistol/katana state;
- accumulated threat injuries;
- window/environment changes.

Its first attempt exposed a deterministic schema defect:

`Beat state patch entity threats.zombies must be an object.`

The extractor produced an unambiguous shorthand equivalent to:

`{"threats":{"zombies":"active"}}`

while canonical threat entries require object records.

Fix:
- known scalar threat-state enum values are normalized to `{"status": value}` only on the accepted-Beat state path;
- ambiguous scalar values are still rejected rather than guessed;
- the generic canonical patch contract remains strict.

Relevant commits:
- `f9aa9b60d7646d50db0ade54e9a2ef2e05737383` — normalize accepted Beat threat-status shorthand;
- `2e193e1e4c0078e75d72699abcc327af3933c6f4` — regression coverage;
- `509fd416e52e5a4375125ed906d39cb0896d424a` — align stale source-span regression with full-story Beat context.

## Other recent verified planning fixes

Recent Amy acceptance work established:
- typed state may seed a newly introduced threat namespace before location effects;
- singular/plural aliases may support that typing conservatively;
- required-event state is deterministically preflighted before Beat generation;
- deterministic state-preflight failures preserve the saved arc and fail fast rather than wiping/restarting forever;
- Beat validation now requires assigned final `set_location` values to be visibly true by candidate end;
- the locked test story wording was adjusted where story phrasing itself was unnecessarily hostile to the local 20B, while real state-management failures continue to be fixed in architecture instead of hidden in story edits.

Relevant commits include:
- `28bf277bfb2ee4a766670144115eac88b5f7142a`;
- `61d0325f6a52d751de0c2d70f18451302c782611`;
- `b0dc4bfbc75a693f2697cbb3249d88d6d9c60ea0`;
- `9be30ba0ab1cbc21833bf29d524585f075ab4a43`.

## Boundary policy during Beat optimization

Broad boundary/barrier enforcement remains dormant in the Beat path.

Do not restore the old barrier/state prompt blocks wholesale.

Reintroduce only the smallest specific boundary fact/rule when a concrete Beat failure proves it is necessary.

Underlying boundary helpers may remain in code for later use.

## Director status

Do **not** tune Director prompts while Beat output/state is still the active optimization target.

Director Request 1 is presently a minimal creative staging stage. Older Director-era rules, topology experiments, retry chronology, and barrier-specific acceptance history are archived in `HANDOFF_OLD.md`.

When Beat output is trustworthy enough to become a stable upstream contract, resume Director optimization from fresh acceptance evidence rather than reopening old failures speculatively.

## Runtime / recovery principles

- Infrastructure connection failures are fatal.
- Deterministic programming/state-schema failures should fail fast instead of endlessly replaying the same invalid plan.
- Recoverable generation/model failures may retry from durable checkpoints.
- Explicit force Beat generation must reset Beat validation state so a prior completed checkpoint cannot silently bypass fresh CREATE/VALIDATE calls.
- Creative stages that still sample use randomized request seeds; deterministic stages use seed 42.
- Beat CREATE/REPAIR are the explicit exception: they are writing calls but intentionally deterministic.

## Public repository rule

Committed repository content must remain SFW/generic.

Runtime user-provided stories may contain arbitrary content, but committed tests, examples, prompts, comments, fixtures, and docs should not embed graphic or sexual material.

## Current queued bridge work

Queued after the 2710 finding:

- `tests-2711-accepted-state-shorthand`
- `generate-beats-2712-gpt-accepted-state-shorthand`

When processed:

1. Confirm the focused regression suite is green.
2. Confirm accepted-Beat state capture no longer crashes on scalar threat status.
3. Inspect the new Amy plan from Beat 1 forward.
4. Identify the earliest real semantic/state failure.
5. Explain the failure and proposed fix **before** making repository changes.
6. Fix only that earliest failure, then retest.

Potential later observation from 2710:
- the successful attempt's final Beat retrieved the children but may not have explicitly shown the required `kills the last zombie` portion.
- Do **not** patch this preemptively. Evaluate it only if 2712 reaches that point without an earlier failure.

## Handoff maintenance rule

Keep this file concise.

When a dated issue is resolved or no longer directly relevant to the next developer action:
- move its chronology into `docs/HANDOFF_OLD.md`;
- retain only the resulting architectural rule/current behavior here;
- do not let acceptance-by-acceptance history accumulate again.
