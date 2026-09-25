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

### Step 1: create the chapter outline

Create a rough chapter split for the complete story.

The chapter outline is deliberately coarse. Its main purpose is to designate **what happens in each chapter** and preserve the story's order and coverage.

A minimal conceptual shape is:

```json
{
  "chapters": [
    {
      "chapter": 1,
      "outline": "Basic plot responsibility of this chapter."
    }
  ]
}
```

Do not overstuff the chapter object before evidence shows more fields are necessary.

The chapter outline is a working draft, not authority. `story.txt` remains authority.

### Step 2: create beats one chapter at a time

Start with Chapter 1.

The Beat CREATE call for a chapter has **no knowledge of anything outside that chapter**.

It may receive only what is needed to execute that enclosed chapter, such as:

- the current chapter outline;
- the compact opening context for that chapter;
- deterministic renderer/runtime constraints such as available segment count or segment duration.

It must **not** receive:

- the previous chapter outline or prose;
- the next chapter outline or prose;
- future beats;
- a narrative summary of the rest of the book;
- hidden knowledge from adjacent chapters.

The purpose is to stop the local model from solving the whole story while it is supposed to be solving one chapter.

### Step 3: validate/repair the chapter beats against story.txt

The generated beats are judged against **`story.txt`**, not against the rough chapter outline.

The story-facing validator/repairer may use `story.txt` because it is enforcing the source of truth.

If the beats fit the story better than the rough chapter outline, **change the chapter outline**.

Repair until the chapter's beats:

- perform the story events assigned to that part of the story;
- do not invent material events outside the story;
- do not steal events that belong to a later chapter;
- form a usable sequence of H3 segments;
- begin from the supplied chapter opening context.

The rough outline exists to organize the work; it is not a contract that can overrule the story.

### Step 4: treat every next chapter as enclosed

When moving to Chapter N+1, the chapter planner does not receive Chapter N or Chapter N+2.

As far as its creative/beat-generation calls are concerned, Chapter N+1 is an enclosed unit.

It receives:

1. its own chapter outline; and
2. a compact description of **how this chapter starts**.

That opening context should contain only the minimum established facts necessary to continue correctly: location, subject state, held objects, injuries, important environment state, or other continuity that materially affects the first beat.

Do not dump the previous chapter into the prompt.

Opening-context sufficiency is empirical: start minimal, run the chapter, and add only the missing beginning facts demonstrated by failures.

### LLM call decomposition

There is no requirement to preserve the old number or arrangement of LLM calls.

Break the work into as many narrow calls as makes sense for the local model. A likely starting decomposition is:

1. STORY -> CHAPTERS CREATE
2. STORY + CHAPTERS -> CHAPTERS VALIDATE/REPAIR, only as much as needed for coverage/order
3. CURRENT CHAPTER + OPENING CONTEXT -> BEATS CREATE
4. STORY + CURRENT CHAPTER + CANDIDATE BEATS -> BEATS VALIDATE
5. STORY + CURRENT CHAPTER + CANDIDATE BEATS + ISSUE -> BEATS REPAIR
6. accepted beat -> H3 scene/prompt work, split into narrow calls when useful

This is a starting hypothesis, not a locked architecture.

Do not reintroduce old ARC/BEATS machinery simply because it already exists in code.

## Beat budgets and the Amy acceptance chapter boundary

Beat CREATE must not decide how many beats a chapter contains.

Probe 313 demonstrated that when beat count was left open, the local model expanded one simple breakfast chapter into three video beats. Probe 315 showed that an explicit one-beat budget constrained it correctly, although the semantic endpoint still needs stronger completion guidance.

Therefore:

- the total video/segment budget is deterministic runtime input;
- each chapter receives an explicit `beat_count`;
- chapter beat counts must sum to the total segment budget;
- Beat CREATE must return exactly that many beats;
- the mechanism for allocating beat counts across chapters is still under test and is not yet locked.

### Amy benchmark consequence

The locked Amy gold has eight beats and exactly one refresh: Beat 7.

Because this branch defines every later chapter's first beat as a refresh, the gold mode pattern implies exactly two chapters for the Amy acceptance target:

- **Chapter 1: Beats 1-6**
- **Chapter 2: Beats 7-8**

This is an acceptance constraint derived from the locked gold, not a production special case. Production chaptering must reach an equivalent major-story boundary from `story.txt` without being told the gold beat answers.

Probe 314 produced three chapters with beat counts 2/2/4. That is structurally valid as a rough story division but wrong for the Amy gold mode pattern because it would create two refreshes. The chapter splitter therefore needs a stronger generic concept of a chapter as a **large refresh unit**, not merely a cluster of nearby story events.

A promising generic boundary is the transition from the main body/repeated process into an explicit terminal/final-resolution sequence. Test this before encoding it.

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

> Give the new chapter the smallest set of already-established facts needed to render and continue its first beat correctly.

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

The running bridge does not hot-reload changes to its own Python code. If the bridge implementation changes, the user's local checkout must be updated and the bridge restarted.

The current bridge's allowlisted executable test/acceptance worktree still defaults to `gpt-test-branch`. Until that bridge plumbing is updated, use direct `llama_chat` jobs for `gpt-arc-refresh` architecture probes rather than accidentally executing old-branch acceptance code.

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
