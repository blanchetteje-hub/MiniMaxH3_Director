# MiniMax H3 Project Notes

This file is the persistent source of truth for the current MiniMax H3 architecture and acceptance target. Historical iteration details belong in Git history, not here.

## Primary goal

The goal is:

> **story.txt -> gold-standard MiniMax H3 prompts**

The pipeline is disposable. Any intermediate representation, LLM call, validator, state object, or Python layer exists only if it improves that path.

## Rule 0: story.txt is the one narrative source of truth

`story.txt` is authoritative for the story.

- Creativity that fills in unspecified presentation or execution detail **inside the story** is allowed.
- Adding, replacing, contradicting, skipping, or materially changing story events **outside the story** is prohibited.
- Intermediate artifacts do not become competing sources of truth.
- A chapter outline may be rewritten.
- Beats may be rewritten.
- Derived continuity/state may describe what has actually been established, but it may not authorize new plot.
- Renderer constraints and reference images may constrain presentation/identity, but they do not create story events.

When an intermediate artifact disagrees with `story.txt`, change the artifact, not the story.

## Development doctrine

1. Optimize for the gold prompts, not for preserving the current pipeline.
2. Assume the local 20B-class model benefits from short, concrete, low-ambiguity jobs.
3. Prefer narrow LLM calls over one overloaded call.
4. Prefer deleting complexity over teaching the model to manage unnecessary complexity.
5. Use Python for deterministic structure/data integrity; use LLMs for semantic work only where useful.
6. Fix demonstrated failures. Do not build speculative subsystems.
7. Architecture changes are allowed whenever evidence supports them.
8. The new chapter-first design starts from a clean sheet. The old ARC/BEATS call structure is **not** a constraint.

### Probe hygiene

When testing the local model, never embed the expected semantic answer in the required output example.

- For an enum decision, specify the allowed values (for example, `MERGE` or `KEEP`) without pre-filling the desired one.
- For booleans, specify the field type/rule without showing the expected `true` or `false` for that test case.
- For lists/indices, describe the allowed shape without supplying the expected elements.
- Treat any probe that telegraphed the expected answer as prompt-shape evidence only, not independent behavioral evidence.

### 20B operating assumption

Treat the local 20B-class model as capable but instruction-fragile.

- Give each call one primary semantic responsibility whenever practical.
- Keep prompts short, concrete, and procedural.
- Prefer explicit inputs/outputs over prose explanations.
- If the model spends many reasoning tokens circling a simple constraint, split the task or simplify the contract before increasing token limits.
- Do not respond to a miss by stacking more rules into the same prompt.
- Arithmetic/count allocation and semantic boundary selection should be separate calls when evidence shows the combined task causes confusion.
- Validators should make one narrow decision and return a minimal machine-readable result.
- Use the larger GPT-5.6 Sol evaluator for fuzzy gold comparison rather than expecting the local 20B model to judge final artistic equivalence.

## Chapter-first planning architecture

The system is conceptually writing a book from `story.txt`.

The book is divided into **chapters**. Each chapter is divided into **beats**.

A beat is an event or unit of action that must happen in that chapter and will ultimately become one MiniMax H3 video segment/prompt.

### Terminology migration

In `story_arc.json`, the old term `phases` is retired.

Use:

- `chapters`
- chapter number / chapter ID
- chapter outline

Do not preserve `phase` terminology merely for compatibility when implementing this branch.

### Step 1: deterministically expose authoritative source units

Do not ask the local LLM to rewrite `story.txt` into chapter prose before chaptering.

Generated rough outlines were a demonstrated source-drift surface: on neutral probes the 20B model invented events, objects, and micro-scenes while trying to "helpfully" expand the story.

Instead, Python exposes `story.txt` as ordered **authoritative source units** while preserving exact source text.

Start with conservative sentence-sized units. Do not globally explode the story into tiny clause units; probe 379 showed that overly fine units make the chapter planner over-split.

Conceptually:

```json
{
  "source_units": [
    {
      "id": 1,
      "text": "Exact contiguous text from story.txt."
    }
  ]
}
```

### Step 2: refine only source units that contain an internal phase boundary

A sentence-sized source unit can occasionally contain both:

- an ongoing/main narrative phase; and
- a major reset or distinct terminal-resolution phase.

Do **not** ask one LLM call to select all such units. A multi-unit selector produced false positives.

Instead, inspect each source unit independently with one tiny semantic decision:

`SPLIT | KEEP_TOGETHER`

Use a large-refresh bias:

- continuous action in the same phase -> `KEEP_TOGETHER`;
- terminal resolution plus its immediate closure/aftermath -> `KEEP_TOGETHER`;
- major time/location/state reset -> `SPLIT`;
- ongoing/main process followed inside the same unit by a distinct terminal-resolution phase -> `SPLIT`.

If a unit returns `SPLIT`, Python enumerates exact candidate cut points from the original source text. The LLM chooses among those candidates (or `NONE`). The LLM does not rewrite either side.

Candidate cut-point selection must run **only after** the unit-level gate returns `SPLIT`. Otherwise the 20B model may choose a grammatical cut merely because one is available.

### Step 3: classify TERMINAL and HARD_RESET; Python derives boundaries

After source-unit refinement, do **not** ask the local model to choose chapter
indices directly. That judgment remained too subjective even when evaluated one
candidate boundary at a time.

Instead, each refined source unit receives two narrow semantic judgments:

1. **TERMINAL** — does this unit itself decisively end the central
   conflict/process?
2. **HARD_RESET** — does this unit begin after a real narrative discontinuity
   such as a substantial time jump, scene break, or relocation after a completed
   phase?

HARD_RESET explicitly does **not** include an inciting event, immediate
cause-and-effect movement, equipping tools/weapons, danger changes, or
room-to-room movement inside one continuous event.

Python owns the chapter rule:

- split before every HARD_RESET unit;
- when a TERMINAL unit has a later non-reset closure unit, start the
  terminal/closure chapter before that TERMINAL unit;
- a final TERMINAL unit stays in the current chapter;
- a TERMINAL unit immediately followed by HARD_RESET stays with its current
  phase and the split occurs at the reset.

The production HARD_RESET wording passed all tested Amy, technician,
continuous-movement, next-day, relocation, and explicit-time-jump controls.
TERMINAL also passed the focused setup/main/final/closure controls.

Python then builds each chapter from exact contiguous source spans. The LLM
never writes chapter summaries or performs boundary arithmetic.

A chapter therefore needs source ownership, not an LLM-authored plot outline.
A minimal conceptual shape is:

```json
{
  "chapters": [
    {
      "chapter": 1,
      "source_unit_ids": [1, 2, 3],
      "beat_count": 6
    }
  ]
}
```

### Step 4: group visible responsibilities, then allocate beat counts

Raw sentence count is **not** the beat minimum.

After chapter spans are fixed:

1. classify each source unit independently as **visible responsibility YES/NO**;
   premise/genre/summary framing and purely internal thought do not consume a
   mandatory video beat;
2. isolate every explicitly long/repeated source unit such as `majority`,
   `most of`, or `repeatedly`;
3. for adjacent finite visible units only, use the current single binary local
   classifier: `MERGE | NEW_TASK`;
4. `MERGE` only when RIGHT is the same uninterrupted local action, a direct
   immediate response caused by LEFT itself, or immediate mechanical completion
   of the exact object/action LEFT obtained/opened/started; otherwise use
   `NEW_TASK`;
5. every repeatable unit remains its own group;
6. the grouped visible responsibilities form the deterministic minimum beat
   count;
7. any remaining beats are assigned to chapters that contain explicit
   repeatable/emphasized source, then repeated only on those source-authorized
   groups.

Do not ask the local model whether an arbitrary collection of actions "fits in
N seconds." Pairwise 8-second fit probes overthought simple cases and even
accepted an intentionally overfull chain. Likewise, a holistic "are N beats
enough?" call exhausted its reasoning budget on Amy-shaped material.

The current binary local-relationship classifier is locked for the production
path after the exact Amy pairs passed:
- calm baseline -> inciting change = `NEW_TASK`;
- inciting danger -> immediate protective reaction = `MERGE`;
- completed protection -> retrieve gear = `NEW_TASK`;
- retrieve gear -> equip that gear = `MERGE`;
- completed local task -> unrelated next tool/task = `NEW_TASK`.

Earlier synthetic experiments with multi-label classifiers and two-call semantic
decomposition were not stable enough for the 20B model and are not the active
architecture.

For the exact Amy acceptance story, this produces:

- Chapter 1 finite groups:
  1. breakfast;
  2. breach + immediate child-protection/escape;
  3. retrieve + equip weapons;
- Chapter 1 repeated group:
  4. the explicit majority zombie-fighting process;
- Chapter 2 groups:
  1. last-zombie resolution + blood aftermath;
  2. release the children.

The grouped minimum is therefore 6 beats total. The two surplus beats both go
to Chapter 1's explicit majority process, producing **6/2** chapter allocation
and Chapter 1 ownership of three repeated fighting beats.

Python owns all counting, grouping assembly, repetition placement, and chapter
allocation. The LLM supplies only the narrow semantic classifications above.

### Step 5: create beats one chapter at a time from exact source

Beat CREATE receives:

1. the exact authoritative source span for the current chapter;
2. the compact opening context for that chapter;
3. its exact beat budget;
4. deterministic renderer/runtime constraints.

It has **no knowledge of source material outside that chapter**.

It must not receive:

- the previous chapter prose;
- the next chapter prose;
- future beats;
- a summary of the rest of the story;
- an LLM-generated chapter outline that can compete with `story.txt`.

The assigned beats must explicitly perform the concrete source actions owned by the chapter. A later state does not prove an omitted action occurred.

Creative presentation detail is allowed inside unspecified story space, but Beat CREATE remains subject to story-facing validation.

### Step 6: validate/repair chapter beats against authoritative source

The validator receives the authoritative current chapter source and may also receive explicit later-chapter responsibility when needed to enforce scope.

A compact combined validator is currently preferred over several overlapping semantic subsystems. Its demonstrated responsibilities are:

1. **required action coverage** — every concrete assigned source action must actually happen;
2. **material source fidelity** — harmless presentation detail is allowed, but material changes to events, plot-relevant objects, relationships, protected/danger state, location significance, or outcome are not;
3. **chapter ownership** — later-chapter responsibility may not happen early.

Return the first issue with a small machine-readable category such as:

- `MISSING_ACTION`
- `MATERIAL_DEVIATION`
- `CHAPTER_SCOPE`

Repair only the demonstrated issue, then validate again.

### Step 7: build later-chapter opening context from canonical state

Do not ask the local LLM to decide which historical facts are relevant.

That approach repeatedly hallucinated relevance for unrelated history such as a discarded tool or an earlier broken window.

Instead, canonical state records must distinguish at least:

- **CURRENT** — true now;
- **HISTORY** — happened earlier but is no longer current state.

The chapter-context builder is deterministic Python:

1. include authoritative CURRENT state needed to represent the refresh boundary;
2. include current protected/location/containment facts for subjects that the enclosed chapter will act on later;
3. include persistent/current visible continuity from Python-owned Subject/environment state;
4. exclude HISTORY records by default;
5. do not ask the 20B model to rewrite or semantically filter the included facts.

Evidence:
- current-state-only context was judged sufficient when the needed current location/containment fact was present;
- omitting the waiting people's current location made the context insufficient;
- extra currently-visible environment facts were acceptable and did not confuse the chapter;
- semantic relevance probes incorrectly marked unrelated historical facts as needed.

Therefore prefer a small amount of harmless extra **current** state over giving the 20B model access to historical facts and asking it to decide relevance.

The LLM receives authoritative fact text, not rewritten continuity prose.

The design target remains:

> Know more internally; expose current truth, not historical narrative.

### Current LLM call decomposition

The current evidence-supported decomposition is:

1. Python: `story.txt -> authoritative sentence-sized source units`
2. each splittable source unit -> internal `SPLIT | KEEP_TOGETHER`
3. only for `SPLIT` units: exact candidate cut points -> choose cut
4. refined source units -> TERMINAL and HARD_RESET binary flags; Python derives chapter boundaries
5. each refined source unit -> visible responsibility `YES | NO`
6. Python isolates explicit repeatable/emphasized units
7. adjacent finite visible units -> one binary `MERGE | NEW_TASK` local-relation call
8. Python applies that decision, then groups visible responsibilities,
   computes chapter minimums, allocates
   surplus beats only to source-authorized repeatable groups, and creates exact
   beat/source ownership
9. current exact chapter source + grouped beat jobs + opening context -> BEATS CREATE
10. authoritative assigned source + candidate beat -> BEATS VALIDATE
11. authoritative assigned source + candidate beat + issue -> BEATS REPAIR
12. Python canonical CURRENT state -> deterministic refresh-context composition
13. accepted beats -> downstream H3 scene/prompt work

Each LLM call remains narrow. In particular, do not combine local semantic
classification with beat arithmetic, duration fitting, or final artistic
judgment.

## Beat budgets and the Amy acceptance chapter boundary

Beat CREATE must not decide how many beats a chapter contains.

Probe 313 demonstrated that when beat count was left open, the local model expanded one simple breakfast chapter into three video beats. Probe 315 showed that an explicit one-beat budget constrained it correctly, although the semantic endpoint still needs stronger completion guidance.

Therefore:

- the total video/segment budget is deterministic runtime input;
- raw sentence/source-unit count is not the beat minimum;
- visible finite source units are grouped by narrow local relationship before
  allocation;
- explicit repeated/emphasized source units stay isolated and may receive
  surplus beats;
- each chapter receives an explicit `beat_count`;
- chapter beat counts must sum to the total segment budget;
- Beat CREATE must return exactly that many beats.

### Amy benchmark consequence

The locked Amy gold has eight beats and exactly one refresh: Beat 7.

Because this branch defines every later chapter's first beat as a refresh, the gold mode pattern implies exactly two chapters for the Amy acceptance target:

- **Chapter 1: Beats 1-6**
- **Chapter 2: Beats 7-8**

This is an acceptance constraint derived from the locked gold, not a production special case. Production chaptering must reach an equivalent major-story boundary from `story.txt` without being told the gold beat answers.

The chaptering work is now locked around large refresh units rather than
event-by-event clusters: TERMINAL and HARD_RESET semantics produce the exact Amy
two-chapter boundary, and grouped visible-responsibility allocation produces the
required **6/2** beat split without teaching the planner the gold beat answers.

## Chapter opening context

Chapter opening context is continuity, not plot authority.

It is derived from facts actually established by prior rendered/accepted work and should be as small as possible.

A later chapter may know, for example, that a character begins in the kitchen holding a katana with a locked basement door behind her. It does not need the prose or reasoning that produced those facts.

Persistent subject identity remains Python-owned.

Do not let an LLM create durable named identities merely because they appear in continuity prose.

## Empirical chapter-opening baseline from the locked gold refresh

The locked Amy benchmark contains exactly one explicit refresh segment: **Beat 7**.

Use that gold refresh as the current empirical model for what a later chapter needs to know when it starts.

The Beat 7 opening setup re-establishes only the facts needed to resume the scene correctly:

- current location: Amy is in the kitchen;
- active subjects: Amy and Zombie4;
- current spatial relationship: Amy is in front of Zombie4;
- current pose/action readiness: Amy is holding the katana above her head;
- persistent visual identity/clothing: black tank top and denim jeans;
- persistent visible condition: Amy's front is covered in green vomit;
- relevant environment aftermath: two earlier zombie corpses remain on the kitchen floor even though they are not currently in view.

What it notably does **not** need:

- the previous chapter outline;
- a recap of the prior fight;
- why Amy is covered in vomit;
- every earlier zombie;
- prior dialogue;
- the discarded pistol;
- unrelated character state that does not affect the opening shot.

This is the baseline rule for later chapters:

> Give the new chapter the smallest authoritative current-state context needed to execute the whole enclosed chapter correctly, while Python separately preserves visible continuity required by the refresh.

Treat those categories as empirical guidance, not as a rigid schema. Add another opening-context fact only when a real failure shows the chapter needed it.

Do not hard-code Amy, Zombie4, Beat 7, kitchens, vomit, or any other benchmark-specific vocabulary into production logic.

## H3 mode is controlled only by chapter boundaries

Refresh cadence is no longer user-controlled.

The chapter split is the sole normal source of initial/append/refresh mode:

- **First beat of Chapter 1:** normal initial generation using `Minimax_auto_API.json`.
- **Later beats in the same chapter:** append; pass the previous video.
- **First beat of every later chapter:** refresh.
- **Later beats in that refreshed chapter:** append.

A user-facing "refresh every N segments" concept is no longer part of the intended architecture.

Any old runtime/CLI/acceptance logic that arbitrarily schedules refresh by segment number must be removed or converted to derive mode from chapter membership.

Repair rendering remains a separate concern and is not a user-selectable refresh cadence.

## Append video context

For an append beat, pass only the final 22 frames of the previous video into the H3 reference-video path.

Use the same exact H3-aligned frame-count calculation as the render workflow, then:

- skip to the final 22 frames;
- set `frame_load_cap = 22`.

For an 8-second segment this is 192 frames total and `skip_first_frames = 170`.

Do not revert to the old long-tail append context.

## Refresh video context

The tested quality-refresh baseline uses the Extend Backport path with context latents from the prior video:

- final 22 decoded frames;
- VAE-encoded context latents;
- `context_frames = 7`;
- prior audio as reference audio;
- the tested first-frame selector path.

A chapter refresh is therefore still visually continuous with the preceding rendered video while giving MiniMax H3 a fresh generation boundary.

## Gold-standard acceptance target

The primary locked benchmark remains:

`tests/acceptance/gold/amy_zombie_house.json`

The benchmark is authoritative for the desired H3 behavior of that test story. Generated prompts do not need string equality; they must preserve the same events, timing discipline, scene intent, exclusions, continuity, audio/music progression, and expected end states.

The new architecture must still reach the gold prompts from the benchmark's `story.txt` content. Do not teach the planner the gold answers.

The current Amy benchmark contains eight output beats/segments. The chapter planner may group those beats into chapters; chapter boundaries determine which segments are refresh versus append.

GPT-5.6 Sol is the fuzzy final evaluator of generated output against the gold target. The local 20B-class model is not the final semantic judge of artistic closeness.

## Global H3 prompt rules

### Timestamp/action rule

Canonical timestamp syntax:

`At mm:ss.nnn,`

Do not append the word `seconds`.

Use one timestamp per discrete action. Do not bundle unrelated sequential actions merely to reduce timestamp count.

Dialogue is its own timed action when spoken.

Camera movement may share a timestamp only when inseparable from the action; otherwise give it its own timestamp.

### Names and dialogue IDs

Prefer names over ambiguous pronouns.

Use `(S1)`, `(S2)`, etc. only when a subject is speaking.

Do not use Subject IDs as ordinary action prose when the name is sufficient.

### Visual subject disambiguation

When visually similar named subjects are present, restate the minimum useful appearance/clothing discriminator already established by the story/reference inputs.

Do not invent new traits just to disambiguate.

### Sound and music

Append segments must explicitly inherit the prior video's music state before describing a change:

`continues from <Video 1>.`

Use simple concrete ambience, object sounds, dialogue, combat sounds, and music-state transitions.

### Additional production heuristics

- Avoid ending append segments on dialogue when practical because H3 may carry vocal momentum forward.
- Re-state important visual details not actually proven by the incoming video tail.
- Difficult dismemberment/decapitation may need separate timed stages: strike, detachment, detached-part movement, reaction, collapse.
- For fades, judge story/continuity from the semantic scene state immediately before the literal black frame.
- Persistent room continuity may eventually require durable room identity/state or a representative image, but implement it only when acceptance demonstrates the need.

## Continuity philosophy

> Know more internally; expose only the facts needed now.

Canonical continuity may know more than the H3 prompt needs.

Persistent named Subject identity belongs to Python.

Generic/transient actors must not silently collapse into durable Subjects.

Implementation must stay generic. Do not special-case fixture vocabulary such as zombies, weapons, rooms, or character names.

## Sampling

Sampling is an evidence-driven tuning lever, not a sacred default.

When probing a demonstrated failure:

- change one small sampling dimension at a time when practical;
- compare against the exact prompt contract being tested;
- distinguish reasoning/token truncation from semantic misunderstanding;
- do not randomly sweep settings.

Historical settings from the old architecture are evidence, not requirements for the new architecture.

## Local llama.cpp bridge

The GitHub-backed mailbox bridge lives at:

`tools/chatgpt_llama_bridge.py`

Mailbox branch:

`gpt-runtime`

ChatGPT writes JSON jobs under `bridge/jobs/`. The local worker calls the configured local OpenAI-compatible llama.cpp/LM Studio endpoint and commits results under `bridge/results/`.

Normal worker command:

`python tools/chatgpt_llama_bridge.py`

No inbound port or public tunnel is required.

The current bridge detects changes to its own script during mailbox sync and restarts automatically. An older running bridge without that support requires a manual update/restart.

Bridge test jobs default to the active `gpt-arc-refresh` code branch.
Acceptance jobs are hard-locked to `gpt-arc-refresh` + model `gpt`; the bridge
rejects a different branch or model instead of silently running a non-baseline
acceptance. The local bridge process must be restarted after bridge-code changes.

## Active development branch

Active architecture-reset branch:

`gpt-arc-refresh`

It was branched from `gpt-test-branch` on 2026-09-24.

This branch intentionally abandons the old locked ARC/BEATS planning architecture as a design constraint.

Use the current branch head as authoritative; do not rely on stale SHA values in handoff/history documents.

## Current development loop

1. Read `docs/PROJECT_NOTES.md` and the current branch head.
2. Use small direct bridge probes to test the chapter-first contracts.
3. Implement only the minimum architecture needed by the demonstrated behavior.
4. Commit focused changes to `gpt-arc-refresh`.
5. Run targeted tests/probes.
6. Progress toward the locked gold benchmark.


## Implemented source-span planner contract

The production planner implementation now follows the empirically proven ownership split:

LLM semantic calls:
1. per sentence-sized source unit: SPLIT or KEEP_TOGETHER;
2. only after SPLIT: choose one Python-enumerated exact cut point or NONE;
3. per refined source unit: TERMINAL YES/NO;
4. per refined source unit after unit 1: HARD_RESET YES/NO.

Python structural work:
1. preserve exact offsets/text from story.txt;
2. renumber refined source units deterministically;
3. create a boundary before HARD_RESET units;
4. create a terminal/closure chapter only when a terminal unit has a later non-reset closure unit;
5. keep a final terminal unit in its current chapter;
6. keep a terminal unit with its phase when the next unit is a hard reset, splitting only at the reset;
7. build chapter text by slicing the original story, never by LLM rewriting;
8. group finite visible responsibilities, allocate one minimum beat per group, then allocate surplus capacity to explicitly repeatable groups;
9. assign source units monotonically to beats; only explicitly repeatable source units may repeat.

Do not ask the LLM to execute these deterministic rules. Probe 565 demonstrated that even with correct flags it could invent a third chapter and produce 6/1/1 instead of the deterministic Amy 6/2 result.


## Locked chapter semantic contracts

The chapter semantic calls are now considered locked unless a concrete
implementation run exposes a new failure.

### Internal source-unit split

Python first enumerates whether an exact legal cut point exists. If none exists,
KEEP_TOGETHER is deterministic and no LLM call is made.

When an exact cut is possible, SPLIT is allowed only for:
- an explicit substantial time jump/scene break inside the unit; or
- source-explicit long/repeated main process wording followed by its explicit
  terminal resolution.

A one-time finite action chain is KEEP_TOGETHER even when its final action
finishes that local task.

### TERMINAL

FULL STORY may identify the central conflict/process, but only TARGET UNIT may
supply the evidence that the process ends. Later story events cannot be credited
backward.

### HARD_RESET

HARD_RESET remains a true narrative discontinuity only: substantial time jump,
scene break, relocation after a completed phase, or equivalent restart.
Immediate cause/effect, alarms, danger changes, equipment changes, and continuous
movement are not resets.

## Source-authorized CURRENT state at refresh

Source-unit persistent state extraction is a separate narrow semantic call.
Python owns when effects become authoritative.

Rules:
- temporary activity creates no persistent state;
- explicit movement into an enclosed place produces location + containment;
- explicit release from that place produces containment=free without inventing
  a destination;
- explicit equipment/drop/barrier/clothing/lifecycle/visible-condition results
  may produce typed effects;
- generic testing/using/replacing/fighting does not imply object/threat state;
- a source unit's effects commit only on its final assigned beat.

At a source-span chapter refresh, Python replays all source effects from prior
beats, compacts the resulting current state, and prepends it to the refresh
opening context as authoritative. Rendered continuity is supplemental and must
not override source-authorized facts.

Source-span chapter starts are the refresh schedule. Legacy refresh_interval is
used only when the loaded arc is not a source-span planner arc.


## Locked source-unit semantic contracts

The source-span planner now uses only these narrow semantic calls:

1. SPLIT/KEEP_TOGETHER, and only when Python has at least one exact candidate
   cut point. SPLIT is allowed only for:
   - an explicit substantial time/scene discontinuity inside the unit; or
   - source wording that explicitly describes a long/repeated process
     (majority, most, repeatedly, throughout, equivalent) followed by its
     terminal resolution.
   One-time finite action chains stay together.
2. TERMINAL YES/NO. FULL STORY may identify the central process, but the target
   unit receives no credit for later events. Ongoing/repeated main-process
   wording is NO unless that unit itself explicitly resolves the process.
3. HARD_RESET YES/NO. Immediate cause/effect, danger changes, equipment changes,
   and room-to-room movement remain NO; substantial explicit phase restarts are
   YES.
4. source_unit_state_effects: extract only explicit persistent post-unit facts.
   Never promote activity alone into state.

Python remains authoritative for cut enumeration, chapter boundaries, chapter
spans, beat budgets, beat/source ownership, refresh scheduling, and when
persistent state effects are committed.


### Historical grouping experiment — superseded

Probes 698–777 exposed over-merging on synthetic controls. A two-call
continuation/reaction decomposition was explored but not adopted. The active
contract is the single binary `MERGE | NEW_TASK` classifier documented above;
exact production pairs 838–842 passed. Do not reintroduce the abandoned
multi-call grouping experiment from historical notes.

## Current acceptance gate — job 935 review

A structurally complete planning capture is not semantic acceptance. Job 935
produced the correct 6/2 allocation but accepted a beat that performed the same
irreversible removal twice on one target, and a realistic body transformation
unsupported by the source.

Test fixes inside the existing validator before advancing to H3 generation.
Batch 936–955 completed with 6/10 reference-label matches for both the full
current validator and its shorter sequential-possibility variant. Neither caught
the actual double-removal error; the proposed replacement is not adopted.
Batch 956–975 completed at 7/10 for both compact full validation and isolated
coherence diagnosis. Only the compact full validator caught the actual double
removal. Both invented a previous death and accepted an unsupported physical
transformation; compact validation also demanded unassigned state effects.
No variant is adopted and no new subsystem is justified.

Batch 976–995 completed with 16/20 reference-label matches, but only 15/20
supported by reviewed explanations. One invalid verdict relied on invented prior
death rather than the intended physical-transformation error. The prompt caught
the actual double removal but still invented a prior terminal state, regressed
locked-door traversal, confused NEXT JOB with CURRENT JOB, and conflated held with
equipped in the bare-operation effect control. All calls completed normally.

Do not adopt compact v2. Keep the current production validator while these
observed failures remain unresolved. These findings do not justify another
production subsystem. Distinguish wrong-reason rejections from genuine fixes;
small probe-set scores do not establish overall acceptance. Future typed-effect
experiments should use the production event-record wrapper.

Testing is paused at the user's explicit request after batch 976–995. No new
probes or acceptance jobs should be queued until the user authorizes resumption.
