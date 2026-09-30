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


### Creativity fills unspecified story space

Creativity is part of the local LLM's job, not a failure mode.

The source story defines what is true and what must happen. It does **not** need to specify every concrete staging, location detail, prop placement, motion, visual choice, or action implementation needed to turn a short story synopsis into a film.

When `story.txt` leaves a detail unspecified, the LLM should invent a plausible, cinematic, story-compatible answer. For example, if the source says a character retrieves a hidden arsenal but does not say where it is hidden, the LLM is expected to choose a concrete hiding place. That invented detail is desirable so long as it does not contradict source facts, canonical facts, established continuity, or a later required event.

The governing distinction is:

- **Creative elaboration:** fills an unspecified blank while preserving the source story. This is encouraged.
- **Story alteration:** contradicts, replaces, skips, preempts, or materially changes an explicit source/canonical fact or required event. This is prohibited.

Do not reject a beat, Director scene, or H3 prompt merely because it contains a detail that was not literally stated in `story.txt`. Ask instead whether the detail is compatible with all established authority and helps concretely realize the film.

The project goal is to expand paragraph-scale through multi-page stories into fully staged films. The LLM therefore must supply missing cinematic detail rather than mechanically paraphrasing the source.


### Sampling policy by responsibility

Sampling is now a hard responsibility split.

**Creative calls**
- character canon establishment when configured facts are missing;
- ARC CREATE and ARC REPAIR;
- BEAT CREATE and BEAT REPAIR;
- Director Request 1 / RAW scene creation.

All creative calls use the same request profile:
- temperature: `0.8`
- top_p: `0.95`
- top_k: `0`
- min_p: `0.05`
- repeat_penalty: `1.15`
- seed: `42`
- reasoning enabled
- reasoning_effort: `high`
- reasoning budget: `1024` tokens

For llama.cpp's OpenAI-compatible request path, Python sends `reasoning_effort="high"`,
`thinking_budget_tokens=1024`, and `chat_template_kwargs.enable_thinking=true`.

**Deterministic calls**
Every LLM call not on the explicit creative allowlist is deterministic by default.
This includes validators, semantic extractors, continuity/state observers, JSON
repair, and the final H3 formatter/translator.

Deterministic calls force:
- temperature: `0`
- seed: `42`

Existing narrow call-specific sampler values may remain for compatibility, but
temperature 0 is authoritative.

**llama-server process requirements**

`--deterministic` is a process-level llama.cpp flag, not a per-request JSON
field. Any llama-server used by this pipeline should therefore be launched with
`--deterministic`. This stabilizes supported numerical kernels but does not
remove creative sampling when a request uses temperature 0.8.

The current target server configuration is:
- `--ctx-size 8192`
- `--deterministic`
- `--repeat-penalty 1.15` as a server fallback
- `--flash-attn on`
- `--jinja`
- `--host 0.0.0.0`
- `--port 1234`
- `--cache-ram 32768`
- `--seed 42`
- `-np 1`
- `--reasoning-budget-message ". Enough thinking, now answer."`

Do not hard-pin `--reasoning-budget 1024` at server launch when per-request
creative/deterministic routing is desired; llama.cpp's request-side
`thinking_budget_tokens` override is used for creative calls. Likewise,
`reasoning_effort` is sent per creative request so deterministic calls are not
forced into the creative reasoning profile.

Default principle:

> **Only explicit creative stages may sample. Everything else is deterministic by default.**

### Current optimization focus: beats only

Beat generation is the sole active optimization target.

- Work in the order: **generate -> analyze -> repair -> validate -> regenerate**.
- Do not tune Director prompts until beat output is trustworthy enough to serve
  as a stable upstream contract.
- Reintroduce barrier/state information into Beat CREATE only when a concrete
  observed beat failure proves that a specific fact is needed.
- Any reintroduced constraint must be surgical: add the minimum information
  required to fix the demonstrated failure, then retest.
- Avoid restoring broad barrier/state prompt blocks wholesale.

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
THE BIGGEST HURDLE YOU HAVE TO OVERCOME IS REFINING THE LOCAL LLM MODEL PROMPTS TO WORK PROPERLY.

When testing the local model, never embed the expected semantic answer in the required output example.

- For an enum decision, specify the allowed values (for example, `MERGE` or `KEEP`) without pre-filling the desired one.
- For booleans, specify the field type/rule without showing the expected `true` or `false` for that test case.
- For lists/indices, describe the allowed shape without supplying the expected elements.
- Treat any probe that telegraphed the expected answer as prompt-shape evidence only, not independent behavioral evidence.

### 20B operating assumption

Treat the local 20B-class model as capable but instruction-fragile.

- Give each call one primary semantic responsibility whenever practical.
- Judge task size by semantic responsibility, not output size: a tiny enum or short JSON response is still a large task if the model must infer multiple hidden facts before answering.
- Prefer supplying Python-owned targets/expected states explicitly so the local model only observes or classifies one fuzzy fact at a time.
- Keep prompts short, concrete, and procedural.
- Prefer explicit inputs/outputs over prose explanations.
- If the model spends many reasoning tokens circling a simple constraint, split the task or simplify the contract before increasing token limits.
- Do not respond to a miss by stacking more rules into the same prompt.
- Arithmetic/count allocation and semantic boundary selection should be separate calls when evidence shows the combined task causes confusion.
- Validators should make one narrow decision and return a minimal machine-readable result.
- Use the larger GPT-5.6 Sol evaluator for fuzzy gold comparison rather than expecting the local 20B model to judge final artistic equivalence.

## Empirical development heuristics

These rules summarize repeated findings from MiniMax H3 acceptance work. Treat them as defaults unless new end-to-end evidence contradicts them.

### Prefer extraction + deterministic decision over holistic LLM judgment

When Python already owns the authoritative rule or expected state, do not ask the local model to decide overall validity.

Prefer:

1. Python supplies canonical truth / the expected invariant.
2. A very small local-LLM call extracts one fuzzy fact from generated text.
3. Python compares the extracted fact to canonical truth and decides validity.

Examples include terminal-target state, finite-vs-ongoing completion, locked-boundary traversal, and observed barrier final state.

> **Canonical Python truth + very small local-LLM extractors + deterministic comparisons.**

The local model should answer the smallest semantic question necessary. It should not decide a deterministic consequence Python can derive.

### LLM understands; Python calculates

Use the local LLM for narrow semantic classification where language understanding is required.

Use Python for:
- counting and arithmetic;
- chapter/beat allocation after semantic classifications are known;
- exact source-span ownership;
- ordering and structural integrity;
- application of typed state effects;
- expected final-state comparisons;
- authorization derived from canonical state;
- deterministic boundary and refresh scheduling.

Repeated testing showed that the 20B model can classify the underlying semantics correctly and still fail when asked to perform the resulting bookkeeping or arithmetic.

### Fix the earliest incorrect stage

For every acceptance failure, trace backward until the first artifact that is wrong. Fix that stage rather than compensating downstream.

Examples:
- wrong Beat -> fix Beat CREATE/VALIDATE, not Director;
- correct Beat but wrong RAW scene -> fix Director Request 1;
- correct RAW scene but incorrect H3 translation -> fix Request 2;
- wrong canonical state -> fix the source/state ownership that created it.

A downstream stage must not repair an upstream semantic error merely because it has enough context to notice it.

### Prompt failure usually means reduce responsibility before adding rules

The local 20B is capable but instruction-fragile.

When an important rule already exists and is still ignored, do not automatically add another paragraph of instructions. First consider:
- shortening the prompt;
- removing unrelated context;
- splitting out one narrow extraction;
- moving deterministic consequences into Python;
- removing duplicated authority.

When a local-model failure recurs despite explicit prompt instructions, treat that as evidence that the responsibility may be in the wrong place.

### Do not create competing narrative authority

`story.txt` is the one narrative source of truth.

Do not ask an LLM to rewrite authoritative source into an intermediate narrative artifact when exact source spans or IDs can serve the same purpose.

Generated summaries, outlines, continuity prose, and beats are derived artifacts. They may help execution but may never become independent permission to invent, omit, replace, or reinterpret story events.

### Synthetic probes diagnose; acceptance decides

Synthetic probes are useful for isolating suspected weaknesses, comparing prompt contracts, checking generic behavior, and exposing instruction instability.

They are not, by themselves, a reason to redesign a production path that is working.

Prefer the smallest change supported by:
1. a demonstrated production/acceptance failure;
2. focused generic probes;
3. a fresh end-to-end acceptance showing the failure moved downstream.

Do not chase every synthetic edge case at the cost of a stable real path.

### Preserve stable architecture until evidence reopens it

Once an architectural responsibility has repeatedly passed production acceptance, treat it as provisionally closed.

Do not reopen chaptering, allocation, beat ownership, state architecture, or another stable layer merely because a later stage fails. Reopen it only when fresh evidence traces the earliest incorrect artifact back to that layer.

### Narrow extractors are not new semantic pipelines

A narrow extractor does not constitute a new CREATE/VALIDATE/REPAIR subsystem.

It is an implementation mechanism inside an existing acceptance loop when:
- Python owns the invariant;
- generated natural language must be observed semantically;
- deterministic parsing alone cannot recover the fact reliably.

Keep extractors independent, tiny, and purpose-specific rather than combining them into another general validator.

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

The current binary local-relationship classifier remains the production path.
Acceptance 1211 demonstrated fresh-run instability: completed protection ->
retrieve gear was falsely merged, producing a 7+1 beat allocation. A paired
20-probe comparison (1215-1234) showed the shorter replacement wording was worse
overall (about 6/10 semantic controls versus about 8/10 for the then-current
wording), so that replacement was rejected.

A later 20-probe duplicated matrix (1255-1274) against the actual current prompt
scored 18/20 parsed semantic decisions. The only misses were one of two duplicate
protection->equipment cases and one of two duplicate finished-assembly->calibration
cases. This indicates residual instruction-order instability, not a need for
another semantic stage. The classifier prompt now applies STOPPING POINT before
same-object/new-problem merge exceptions, while keeping the same single binary
LLM call.

Acceptance 1276 confirmed the grouping-priority fix end-to-end: the source-span
planner again produced exactly **2 chapters / 6+2 beats**, with refresh at
Segment 7. The next earliest failure moved downstream to source/beat fidelity:
Beat 1 rewrote "cooking breakfast for her young kids" into staging where Will
drinks milk and Amber watches. The existing validator preserves named participant
presence but can still accept a beneficiary becoming a spectator. Treat this as
the current beat-validation target; do not reopen chapter allocation unless a
fresh acceptance regresses it.

The intended relations remain:
- calm baseline -> inciting change = `NEW_TASK`;
- inciting danger -> immediate protective reaction = `MERGE`;
- completed protection -> retrieve gear = `NEW_TASK`;
- retrieve gear -> immediate use/equip/consume of that exact obtained item may `MERGE`;
- completed victory/resolution -> release/aftermath task = `NEW_TASK`;
- completed local task -> unrelated next tool/test/task = `NEW_TASK`.

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
- relevant environment aftermath: two earlier terminal target remnants remain in the kitchen even though they are not currently in view.

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

The benchmark is authoritative for the desired H3 **prompt contract and quality bar** of that test story.

Generated prompts do **not** need string equality with the gold prompt, and they do not need to reproduce the gold prompt's exact timestamp-by-timestamp choreography. The required acceptance target is:

- the same overall H3 prompt structure/schema and mode-specific contract;
- semantically valid execution of the assigned story beat/source responsibility;
- valid timestamp syntax and a physically/coherently ordered sequence of visible actions; timestamp count does not need to match gold, and being modestly shorter or longer (for example by one or two timestamps) is acceptable when the beat remains complete and coherent;
- required story events, exclusions, continuity constraints, subject identity, and material end-state facts preserved;
- scene-appropriate sound/music behavior consistent with the prompt mode.

Different wording, different harmless staging, different concrete props inside unspecified story space, and a different valid sequence/timing of micro-actions are acceptable. Treat the gold prompt as an exemplar, not a screenplay that must be reconstructed.

The new architecture must still produce gold-standard H3 prompts from the benchmark's `story.txt` content. Do not teach the planner the gold beat answers or timestamp choreography.

The current Amy benchmark contains eight output beats/segments. The chapter planner may group those beats into chapters; chapter boundaries determine which segments are refresh versus append.

GPT-5.6 Sol is the fuzzy final evaluator of generated output against the gold target. The local 20B-class model is not the final semantic judge of artistic closeness.

## Global H3 prompt rules

The locked gold prompts are exemplars of **H3 prompt-writing discipline**, not scripts that production must reconstruct. Four hard rules define that discipline:

1. **To the point.** Use short, concrete visual/action wording. No literary fluff, atmosphere prose, ornamental description, or unnecessary explanation.
2. **Depictable information only.** Describe only things a video can show or audio can present. Do not write feelings, internal thoughts, intentions that are not externally visible, smell/taste/touch as subjective sensation, or other non-portrayable information. Visible physical reactions are allowed when explicitly described as actions/expressions rather than inferred emotions.
3. **Actions are explicit.** State each materially important physical action directly: who acts, what object is used, how the object moves/changes hands/changes state, and the visible result when relevant. Avoid vague compression such as "gets ready," "handles the weapon," or "deals with the door" when the physical steps matter to H3.
4. **Use camera movement liberally; cuts rarely.** Pan, orbit, track, tilt, push/pull, follow, reframe, and similar continuous camera movement are encouraged when they improve spatial clarity or reveal the next action. Prefer these over cuts. Cuts should be rare and used only when continuous movement would be impractical or confusing.

These rules are stricter than fuzzy comparison against the exact gold choreography. Timestamp count, exact wording, and harmless staging may differ from gold while these rules and all continuity/source constraints remain satisfied.

### Timestamp/action rule

Canonical timestamp syntax:

`At mm:ss.nnn,`

Do not append the word `seconds`.

Use one timestamp per discrete action. Do not bundle unrelated sequential actions merely to reduce timestamp count.

Dialogue is its own timed action when spoken.

Camera movement may share a timestamp only when inseparable from the action; otherwise give it its own timestamp. Use camera movement freely when it makes spatial progression clearer; do not add cuts merely for variety.

### Names and dialogue IDs

Prefer names over pronouns. Within one timestamp, use a pronoun only when exactly one person could reasonably be its referent. If two or more people are present or mentioned and the pronoun could be ambiguous, repeat the person's name.

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
- Difficult multi-stage physical transitions may need separate timed stages: initiating action, state change, resulting movement, reaction, settling.
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
2. Use small direct local-endpoint probes to test the chapter-first contracts.
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

## Historical acceptance gate — job 935 review

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

The user resumed autonomous iteration on 2026-09-25. Direct local access at
`http://127.0.0.1:1234` replaces the mailbox bridge for current development.
Use `MINIMAX_LM_STUDIO_URL` for local production runs and explicitly select the
advertised GPT 20B model for probes. Historical bridge results remain evidence.
The first resumed experiment holds compact-v2 rules constant while testing
explicit input roles; both arms use production event-record wrappers for effects.
No production validator change is adopted without reviewed evidence and fresh
planning acceptance.

Repair assignment scope: when a rejected beat or subrange is regenerated, only
that requested range belongs in the required-event assignment list. Full chapter
source may remain context, but other numbered chapter jobs must not be presented
as additional required outputs for a one-beat repair. The former unfiltered list
was an observed contradictory prompt contract; it is now filtered in Python.

## Role-layout validator experiment — probes 996–1015

The explicit BEFORE / NOW / LATER / AFTER input-role experiment is complete.
Reviewed result: **15/20 reference-label matches, 14/20 supported by the actual
reasoning**. Do **not** adopt this prompt layout as the production validator.

Useful signal:
- double-removal/restoration controls remained correct;
- the ordinary final-resolution control was accepted, removing one prior false
  rejection;
- but the important failures remained: locked-barrier traversal, unavailable
  object use, held-vs-equipped typed state, and unsupported ordinary material
  transformation;
- probe 998 still rejected the transformation case for the wrong reason by
  inventing a prior terminal state.

Production stays unchanged. The next evidence-gathering step is narrower rather
than longer: test current-state precondition compatibility separately from exact
typed-effect support (about 10 controls each). Do not add a new subsystem unless
those narrow contracts demonstrate materially better reliability across neutral,
science-fiction, fantasy, and action-shaped controls.

Reviewed results: `tests/LLM/probes/role_layout_996_1015_results.json`.

## Narrow post-validation coherence gate

The combined forward validator remains the production semantic authority for
CURRENT JOB coverage, continuity/preconditions, NEXT-job ownership, typed state
effects, and material fidelity. Do not replace it with the failed role-layout
variant or split all of its responsibilities into tiny calls.

One demonstrated failure class is now handled by one additional narrow call
*only after* the main validator returns VALID: within-beat physical/causal
coherence.

Evidence:
- decomposition probes showed coverage and LATER ownership can become
  over-literal or unstable when isolated;
- barrier and typed-effect isolation looked promising, but they are not adopted
  as separate production validators;
- the within-beat coherence contract generalized across neutral action,
  machinery, fantasy restoration/regeneration, explicit technology/magic, and
  ordinary-physics controls;
- across probes 1041–1063, every request that reached the model returned the
  intended verdict: **19/19 semantic controls correct**; the remaining control
  repeatedly failed at the local HTTP transport layer rather than producing a
  semantic verdict.

The coherence gate owns only:
- repeated irreversible removal/destruction of the same specific target/part
  without restoration/regeneration/reinstallation; and
- unsupported whole-object/body material transformation or disappearance when
  no capability or plausible physical cause is established.

It must not judge source coverage, NEXT-job ownership, or typed state effects.
A semantic coherence failure regenerates the current beat. A transport/parser
failure consumes the existing validation retry budget without changing the
candidate.

Implementation commit: `0f554b0`.

Acceptance requirement: keep the gate only if focused orchestration tests pass
and a fresh planning-only Amy capture removes job 935's accepted double-removal
and unsupported-physics failures without introducing a rejection loop. Do not
advance to H3 rendering before that check.


## Current acceptance target — 2026-09-26

Planning captures have passed the 2-chapter / 6+2 structure and the earlier
coherence/ownership checks sufficiently to resume full H3 prompt generation.
Captures 1125 and 1190 generated all eight prompts; neither establishes gold
quality. Earlier instructions to stop before H3 generation describe historical
checkpoints, not the current next action.

Capture 1190 demonstrates a source-authority loss: a source activity **for**
beneficiaries became an activity they merely **watch** in the derived beat.
The Director completion checker sees only that derived beat. Presence is not
preservation of a source-assigned participant role.

The existing Director creation and completion calls now receive the exact
source-span required event text assigned to the current beat, alongside the
derived beat. Python selects by explicit beat_number; it does not rewrite text
or infer semantic requirements. The source governs actions, results, and
participant roles; the derived beat supplies compatible staging. This changes
inputs to the existing calls, not the number of semantic stages. Non-source-span
legacy callers retain their prior contract.

Paired probes 1191–1210 support this correction: the source-aware variant matched
10/10 intended completion outcomes, including spectators and interrupted work.
One repaired positive omitted appearance details, limiting appearance-fidelity
claims; one baseline request failed with HTTP 400. Full H3 acceptance 1211 must
confirm the fix end to end before advancing past the breakfast mismatch.

### Acceptance 1211: reopen demonstrated grouping instability

Acceptance 1211 generated all 8 prompts, but allocation regressed to 7+1.
The existing local-relation classifier incorrectly merged completed protection
with gear retrieval and terminal resolution with releasing protected people.
These are observed exceptions to the earlier "locked grouping" checkpoint;
those historical passes do not establish stability across fresh runs.

Keep Python grouping/allocation unchanged. Probe a shorter single binary
classifier that distinguishes a new danger/problem's immediate protective
response from a new task merely enabled by completed protection or victory.
Batch 1215–1234 compares that wording with production on exact failed pairs
and generic controls. Do not adopt the experimental wording before review.

Source-aware Director completion remains implemented but is not gold-accepted:
1211's breakfast does not clearly show serving both recipients and settling the
stove. Later capture failures remain documented in HANDOFF; the earliest current
semantic target is grouping. The missing Segment 5 report was a logging/parser
artifact, now reproducibly repaired without rerunning generation.


## Current Director context-budget checkpoint — 2026-09-26

The current demonstrated H3-generation blocker is local context headroom, not chapter planning. A Segment-6 Request 1 entered at roughly 4395 / 4500 estimated input tokens. Under the local 6044-token total context with a 128-token reserve, that left only about 1521 completion tokens, and GPT-OSS 20B repeatedly truncated before completing its structured response.

Current rule:
- reduce redundant Request-1 input before increasing model/context limits;
- Request 1 must remain scene-local and generic;
- full `story.txt` and full chapter/phase JSON are not required once the current beat assignment has already been derived;
- keep only authority needed to execute the current segment and stop before the reserved next beat.

The active generation message now omits `STORY:` and `PHASE:`. Regression job `director-context-tests-1454` passed 61/61. The next acceptance is `gold-prompt-context-1455`; use its real per-segment token measurements to decide whether another context block should be removed or compacted. Do not optimize only for the zombie benchmark: the same contract must support arbitrary genres and action types.


## Finite beat endpoint checkpoint — 2026-09-26

After Director context compaction, full acceptance 1455 captured all 8 segments. The current earliest gold mismatch is now upstream of Director: Beat CREATE/VALIDATE allowed a finite source activity to remain visibly underway at the end of its assigned beat.

Current rule:
- if one beat owns a finite activity/task, the finalized beat must include its natural observable completion endpoint;
- progressive source grammar such as "is cooking" or "is repairing" does not by itself authorize ending the assigned beat mid-task when that whole finite activity belongs to the beat;
- explicitly long/repeated/ongoing source processes remain non-terminal and must **not** be forced to end;
- do not infer mandatory physical handoff merely because work is described as being "for" an owner/client/beneficiary. Preserve beneficiary semantics, but distinguish task completion from transfer/delivery.

This rule belongs in the existing Beat validator before broader checks; do not create a new semantic stage unless the combined validator still misses it after the priority change. Generic probes 1456-1475 produced 18/19 intended parsed judgments plus one 512-token truncation, with the only semantic miss caused by over-strict beneficiary transfer. Therefore only finite-endpoint priority is adopted.


## Beneficiary completion distinction — 2026-09-26

Finite-task completion is verified end-to-end. For a finite consumable or explicit immediate hand-off to a named person, the result must visibly reach/be served to that recipient. Merely labeling it for them or leaving it elsewhere is insufficient. By contrast, fabrication, repair, customization, or creative work merely made FOR someone is complete when the work itself is complete unless source explicitly requires delivery. Explicit later pickup/storage may make storage sufficient. Keep this distinction inside the existing Beat validator and source-aware Director completion gate; do not add a separate beneficiary subsystem.


### 2026-09-26 — timestamp fix exposed Director typed-end-state regression

- Acceptance `acceptance-1538` confirmed the malformed/out-of-range timestamp fix: Director Request 1 no longer emitted the previously observed invalid timestamp forms.
- The earliest real failure moved backward to Segment 2 under fresh-run variance: Amy ended inside the basement with Will and Amber even though the authoritative typed effects relocate/contain only Will and Amber. This is a regression of the previously acceptable Segment-2 boundary, not a reason to reopen chapter/beat allocation.
- The source-only Request-1 completion wording is not stable enough by itself for mover/helper barrier scope. The local 20B model can read verbs such as “guide/escort” as permission for the helper to follow.
- Production change: Director completion validation now also receives the exact typed persistent effects assigned to the active beat. For already-known named subjects/barriers/items, those effects are authoritative for new persistent location, containment, barrier, item, damage, and similar end-state changes. A helper/mover may not inherit another subject’s location/containment effect unless it has its own matching effect. Temporary motion that returns to the opening state remains allowed.
- Commits: `344f68f06549efc7c4d48589beb2308c40923fc8` (production) and `8cc20483ff95a7488d0afcf62206d5469d7053b6` (regressions).
- Queued generic typed-end-state probes `1540-1559` plus focused regression job `tests-1560`. Grade the probes before another full Amy acceptance. Keep the rule generic across domestic, technical, fantasy, sci-fi, containment, barrier, and item-state cases; do not special-case the zombie fixture.


### 2026-09-26 — barrier topology should be state + Python + narrow LLM extraction

Barrier-side continuity is a special high-value case and should not depend on one broad semantic validity judgment.

Current design direction:
- canonical typed state/effects define the authorized persistent transition (for example which subjects end in a destination/container and the barrier's final state);
- Python deterministically derives the allowed transition contract from those effects and opening state;
- a narrow local-LLM call only extracts each named subject's observed final relation to the destination from RAW SCENE using `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`;
- Python compares extracted observations with the authorized contract and decides pass/fail;
- the LLM does not decide whether following another subject was permitted, and helper verbs such as guide/escort/push/lead never grant a crossing by themselves.

This is intentionally more specific than ordinary continuity because the Amy basement boundary has repeatedly demonstrated instruction-fragile failure. It must remain generic for doors, gates, portals, airlocks, shelters, rooms, vehicles, containment areas, and similar barriers.

The existing typed-effect Director change passes focused deterministic tests: `tests-1560` = 79/79. Direct validity probes showed the remaining weakness: GPT-OSS can still reinterpret helper grammar or over-reason missing effects. Therefore do not rely on direct LLM validity for barrier topology. Probe batch `probe-barrier-extract-1561` through `1580` tests the narrower extraction-only contract before production wiring.


### 2026-09-26 — barrier topology extractor accepted; Python now owns validity

- Barrier extraction probes `1561-1580` completed. The 10 RAW-scene cases all produced the intended semantic final-side placement. One RAW case emitted the right meaning with a malformed enum token (`ATDESTINATION`), which the production strict response schema prevents.
- Source-text cases still showed helper-verb ambiguity (for example guide/get/escort can make the 20B model infer the helper followed). Therefore source prose is never passed to the topology extractor. It reads only the generated RAW SCENE.
- Production commit `fdcd79da53e55ed54b871d88e29c96aa73dffc6d` adds the barrier-topology path inside the existing Director Request-1 retry loop:
  - Python derives destination-side expectations from source-owned typed state effects plus canonical opening state;
  - already-known subjects with an authorized location/containment effect must end at the destination;
  - an unassigned subject is forbidden from ending there only when canonical opening state establishes that subject started elsewhere;
  - a narrow LLM call extracts only `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED` from RAW SCENE;
  - Python performs the deterministic pass/fail comparison.
- Commit `b8e5bb2501d581cdfab4e2873dff1b8486db8bb4` routes the extractor through the existing frozen validator-settings mechanism instead of passing internal validator settings directly to `ask_llm`.
- This specifically avoids treating helper verbs as crossing authority while remaining generic for rooms, doors, gates, portals, shelters, airlocks, vehicles, and containment areas.
- Focused mailbox regression/acceptance still needs a real local run before this checkpoint is considered accepted. Do not claim the Amy basement regression closed until that run proves Segment 2 leaves Amy on the authorized side while Will/Amber reach the basement.


### 2026-09-26 — topology validator works; Director generation needed the contract up front

- Fresh full acceptance `acceptance-1582` proved the new barrier-topology validator is catching the Amy basement error rather than accepting it. Segment 2 failed three Request-1 attempts: attempts 1 and 3 were rejected by the deterministic topology comparison because Amy ended in the basement; attempt 2 was rejected by the existing typed-effect completion verifier for the same unauthorized crossing.
- This is a successful detection result but not yet an accepted end-to-end fix: repeated regeneration exhausted the 3-attempt Request-1 budget, so the Director generation prompt itself lacked enough explicit topology guidance.
- The accepted Beat 2 wording included the ambiguous phrase that Amy “secures the door behind her.” Do not deterministically rewrite narrative prose to repair this. Canonical state/effects remain the authority.
- Production commit `580f2d888925b91eb20ecf9c95df26f736339db4` now injects the Python-derived final-side contract into Director Request 1 before generation. Example shape: named subjects with authorized effects MUST end at the destination; a known unassigned subject proven by opening state to start elsewhere MUST NOT end there. Helper/mover verbs cannot override the contract, though temporary crossing is allowed if final placement matches.
- The later topology extractor and Python comparison remain as enforcement. This gives three layers: state-derived generation constraint, narrow RAW-scene extraction, deterministic Python validation.
- Next checkpoint: regression suite, then fresh full Amy acceptance. Success requires Segment 2 to generate a valid scene with Will/Amber in the basement and Amy on the non-basement side without exhausting retries.


### 2026-09-26 — Segment 1 verifier overreach narrowed back to source authority

- Regression suite `tests-1583` passed 79/79.
- Fresh acceptance `acceptance-1584` did not reach Segment 2 because Segment 1 exhausted its three Request-1 attempts. The accepted Beat 1 had strengthened source wording into a specific action: Amy “hands the steaming pancakes” to Will and Amber. RAW scenes where she finished breakfast, placed it in front of them, and they picked it up were rejected because the completion verifier treated the derived beat’s hand-to-hand gesture as a source requirement.
- The verifier also over-policed the children briefly holding ordinary breakfast props as persistent typed inventory changes even though plates/food were newly introduced incidental scene props.
- Production commit `dc3dca728c3baab6ee506a2d90cfa79ad4a4e2c0` restores the intended authority boundary:
  - SOURCE alone defines required actions/results/participant roles;
  - DERIVED BEAT may stage SOURCE but may not strengthen it with a stricter transfer method, prop, destination, or gesture;
  - visible receipt/service/practical access is enough for consumables unless SOURCE itself requires a particular hand-off;
  - ordinary newly introduced serving/consumable props are not treated as persistent inventory merely because a known subject holds them at segment end;
  - durable tracked inventory/readiness/location/containment/barrier/etc. remain governed by opening state and typed effects.
- Generic source-authority probes `1585-1604` are queued, followed by `tests-1605` and fresh full acceptance `acceptance-1606`.
- If 1606 clears Segment 1, immediately inspect Segment 2 to verify the new state-derived barrier contract now generates and validates Will/Amber inside the basement while Amy ends outside.


### 2026-09-26 — Segment 2 topology passes, but barrier identity and location granularity required tightening

- `acceptance-1606` successfully generated through Segment 3 and proved the side-of-barrier fix: Segment 2 ends with Amy in the kitchen while Will and Amber are in the basement. This closes the original “Amy followed the kids into the basement” failure.
- However, Segment 2 still exposed a barrier-identity error: the Director locked a “kitchen door” instead of the barrier securing the basement children. The source-owned typed effect was too generic (`set_barrier_state(entity="door", value="locked")`). Barrier identity is therefore not considered fully solved yet.
- Segment 4 then failed because the completion verifier treated Amy moving from kitchen to hallway as an unauthorized durable location change even though canonical `set_location(Amy, home)` is coarse story geography and both spaces are subareas inside the same home.
- Production commit `7e0ec590d33a90b48cefc3a85528810cbd8df0ff` addresses both demonstrated failures:
  - canonical `set_location` is explicitly coarse story geography/container state; room/hallway/subarea movement inside that location is local staging and does not require a new location effect;
  - when one event has exactly one containment destination and exactly one generic barrier noun (`door|gate|hatch|barrier`), Python deterministically binds that barrier to the destination boundary (for example generic `door` + contained-in `basement` => basement boundary); ambiguous multi-destination cases are left unbound rather than guessed;
  - Director generation receives this barrier binding up front, and the completion verifier rejects satisfying it with an unrelated same-type barrier.
- Regression commit `a88538c6960b08d36888edb2ed4b8e5ca11b4121` refreshes three stale prompt-wording assertions and adds coverage for local movement plus unambiguous/ambiguous barrier binding.
- Source-authority probes `1585-1604` were mixed: several reasoning traces still over-weighted derived staging despite the explicit authority rule. Production should therefore continue relying on source authority + deterministic state checks rather than trusting those direct probes as holistic validity judges.
- Next checkpoint: run focused regressions, then fresh full acceptance. Inspect Segment 2 for **basement-door identity**, not only Amy/children sides, and Segment 4 for allowed kitchen→hallway staging.


### 2026-09-26 — first complete 8-segment acceptance; next hard failure is terminal-action ownership

- `tests-1607` passed 82/82.
- `acceptance-1608` is the first structurally complete 8-segment prompt-generation acceptance after the recent fixes.
- Segment 2 now satisfies both barrier requirements: Amy ends outside the basement, Will and Amber end inside, and the locked barrier is explicitly the basement door. This closes the original basement-side and wrong-door regressions.
- Segment 4 no longer fails on kitchen/hallway-scale movement, confirming canonical `set_location` is now correctly treated as coarse story geography rather than room-level staging.
- The next hard semantic failure is Segment 7. Source assigns a new terminal result, but RAW begins with the already-terminal target from Segment 6 and reuses it. The completion gate incorrectly accepted interaction with an already-terminal target as evidence of the newly assigned transition.
- Production commit `df49c6aeb5455bf7e2d66a9f0d780b797485efd3` adds a generic terminal-action invariant to beat generation, Director generation, and Director completion: an irreversible terminal result must begin from a target or process that has not already reached that result and must visibly cause the transition in the current beat. An already-satisfied terminal state cannot satisfy the same newly assigned action again.
- Regression commit `7899fd73337b0f7e379122cc6ef3fa3b52775e3a` covers the new terminal-target rule.
- Segment 1 still has softer gold-quality distance (children reach for breakfast rather than a stronger fully served/stove-settled endpoint), and Segment 8 has over-elaborated release staging. Do not prioritize those artistic/quality differences ahead of the demonstrated Segment-7 source violation.
- Next checkpoint: regression suite, then fresh full acceptance. Verify Segment 7 uses an unresolved final target rather than reusing an already-terminal target; after that, reassess the earliest remaining gold-quality mismatch.


### 2026-09-26 — terminal-action prompt rule was insufficient; moved to narrow extraction + Python decision

- `tests-1609` passed the prompt-contract regression, but `acceptance-1610` still repeated the Segment-7 failure: RAW begins with the already-terminal target from Segment 6 and reuses it for another terminal action.
- This proves broad generation/completion wording is still too instruction-fragile for the local 20B. Do not keep stacking prose rules for this case.
- Production commit `2675c3958abb9aa78c35fbe2f1eaee9ba4fdaee6` adds a narrow terminal-target extraction path inside the existing Request-1 acceptance loop:
  - it runs only when SOURCE explicitly contains a terminal action (kill/destroy/defeat/eliminate/finish/resolve);
  - the LLM answers only the target/process status immediately before that terminal action: `ACTIVE_OR_UNRESOLVED | ALREADY_TERMINAL | UNSPECIFIED`;
  - the extractor does not decide scene validity;
  - Python rejects `ALREADY_TERMINAL` deterministically and feeds that exact failure back into the existing Request-1 retry loop;
  - `UNSPECIFIED` is not automatically rejected, leaving ordinary ambiguity to the existing completion verifier.
- Regression commit `f38802ba98a2f6779a24dd8c7fbc68656f5983d7` covers terminal-action detection, strict enum parsing, and extraction-only prompt scope.
- Generic terminal-target probes `1611-1630` are queued across living/dead creatures, intact/destroyed machinery, active/resolved processes, wounded/unconscious targets, and already-finished tasks. `tests-1631` and full acceptance `acceptance-1632` are queued behind them.
- This follows the same proven architecture as barrier topology: narrow fuzzy extraction by the local model, deterministic Python acceptance, no new semantic pipeline stage.


### 2026-09-27 — terminal-target extraction accepted; earliest remaining gap moved to Beat 1 finite completion

- `tests-1631` passed 87/87.
- Terminal-target probes `1611-1630`: 16/20 strict successes. Three cases reasoned to the expected answer but exhausted the small 300-token probe budget before emitting final JSON; one real miss treated an already unconscious/restrained guard as still unresolved for a `defeat` action.
- `acceptance-1632` fixed the demonstrated Segment-7 failure: the final target is visibly unresolved before Amy performs the assigned terminal action, so the action causes a real unresolved→terminal transition rather than reusing the prior target.
- Commit `a4de6aa4f00d056cf4d35f51fe4afc3d376fb584` makes terminal extraction action-relative: terminal means already dead for `kill`, already destroyed for `destroy`, already neutralized/incapacitated for `defeat/eliminate`, already complete for `finish/complete`, and already resolved for `resolve`.
- The earliest remaining gold-quality failure is now Segment 1. In `acceptance-1632`, Beat 1 was accepted on the first try as “Amy is cooking breakfast...” even though the finite activity had no completion endpoint; Director then ended the segment with Amy still cooking. This is an upstream beat-validation miss, not an H3 formatter problem.
- Production commit `9f188533c8b698de3c5f11c9a4f366c39f03575f` adds a narrow post-VALID finite-endpoint extractor inside the existing beat validation loop. It returns only `COMPLETE | ONGOING | NOT_APPLICABLE`; Python rejects `ONGOING`. Explicit repeated/ongoing assignments (majority/most/repeatedly/throughout/continuing/etc.) return NOT_APPLICABLE and remain non-terminal by design.
- Regression commit `dd81535d44feb2a0e953d51374d2f1ae3644e81f` covers the finite-endpoint extraction contract.
- Generic endpoint probes `1633-1642` are queued. A second 10-case synthetic batch was attempted twice but blocked by connector safety checks; do not treat that as a model result.
- Next checkpoint: regression suite + fresh full acceptance. Beat 1 should be regenerated until breakfast reaches a natural visible endpoint instead of ending while cooking is still underway.


### 2026-09-27 — Beat 1 finite endpoint fixed; terminal extractor needed opening-state authority

- Finite-endpoint probes `1633-1642`: 8/10 strict final JSON successes. The two missing finals (`1633`, `1638`) reasoned to the expected ONGOING classification but exhausted the small probe token budget before emitting JSON. No semantic misclassification was observed in the 10-case batch.
- `acceptance-1644` proves the Beat-1 finite endpoint issue is fixed in production. The first Beat-1 candidate (“still cooking”) was rejected; the accepted candidate explicitly finishes frying pancakes and serves Will and Amber. Segment 1 now ends with both children holding plated breakfast rather than Amy still cooking.
- `tests-1643` exposed only test-harness integration breakage: two mocked beat-validator tests did not know about the new finite-endpoint extraction call and therefore returned the old validity schema. Production acceptance itself completed all eight segments.
- `acceptance-1644` also exposed why Segment 7 can still regress despite terminal-target extraction: the extractor saw only SOURCE + RAW SCENE. Segment 6 continuity knew the zombie was headless/dead, but Segment 7 RAW compressed that to “zombie body lying on the floor,” and the local model reasonably classified that as potentially unresolved.
- Production commit `4b8fabe39c50e1fcbc7a74ae5d923155e9f736f3` now passes AUTHORITATIVE OPENING STATE into terminal-target extraction. Opening state is explicitly already true at 00:00.000 unless RAW visibly changes it, so a terminal state from the prior segment cannot disappear through RAW compression.
- Test-harness commit `8ef7ba4545be2108d379b30385f50e17a1ae230a` updates the two forward-validation mocks to return `COMPLETE` for the new narrow endpoint call. Regression commit `2f451120318c5bb212a2710b747c35d7b829dbaf` asserts the terminal extractor receives and treats opening state as authoritative.
- Next checkpoint: regression suite + full acceptance. Segment 1 should remain complete/served; Segment 7 should reject any RAW that targets a zombie already established terminal by opening continuity.


### 2026-09-27 — acceptance 1770 exposed wrapped-effect plumbing bug in Beat boundary validation

- `acceptance-1770` completed 8/8 but still allowed the old topology failure:
  - Beat 6 explicitly placed Amy fighting zombies **inside the locked basement** while Will/Amber remained contained there.
  - Segment 7 then continued with Amy in the basement although the basement boundary was still canonically locked.
- The newly added Beat destination-presence extractor itself was not the problem. The 1770 developer log contained **no `beat_destination_presence_extract` calls** for the accepted combat beats.
- Root cause: Beat VALIDATE passed assigned effects as event wrappers:
  `[{"id":"E6","state_effects":[]}]`
  while the shared Python boundary derivation expects the flat typed-effect list. `_validate_state_effects` rejected that wrapper shape, so closed-boundary derivation silently returned no contracts. Beat CREATE used flat effects and therefore did receive the boundary contract, explaining the asymmetry.
- Production commit `9ac76adcc7cc81136fe61d899440bd94d2807e09`:
  - adds one deterministic normalizer for Beat assigned effects;
  - flattens event wrappers before Python barrier-binding / closed-boundary derivation;
  - leaves the validator-facing wrapped event structure intact for traceability.
- Regression commit `1b69bdacc52c24bf197f827b197b137efe8790a7` proves the real production shape (wrapped event with empty `state_effects`) still yields the basement closed-boundary contract and destination-presence candidate for Amy.
- Queued `tests-1771` and full `acceptance-1772`.
- Acceptance checkpoint: after Beat 2 locks Will/Amber in the basement with Amy outside, the destination-presence extractor must now actually run on later candidate beats mentioning Amy and deterministically reject any candidate that places her inside the basement before an authorized opening/release.


### 2026-09-27 — acceptance 1772 fixed Beat boundary plumbing; terminal target still ignored supplemental opening fact

- `tests-1771`: 112/113 passed. The sole failure was test-only: an assertion searched the raw multi-line prompt for a sentence that is split by a newline. Commit `00d2b78ec55d037a4dc9830905fc8b7e3f8118ad` checks the normalized prompt instead.
- `acceptance-1772` completed all 8 segments. The wrapped-effect boundary fix worked:
  - Beat VALIDATE now receives `PYTHON-OWNED CLOSED BOUNDARIES` after Beat 2.
  - Accepted Beats 3-7 keep Amy outside the locked basement; no later beat places her inside before Beat 8 release.
  - Beat 8 explicitly unlocks/opens the basement door and releases Will/Amber.
- The earliest important regression is again Segment 7's terminal action. Segment 6 continuity says Amy is near **the dead zombie on the kitchen floor**, but Segment 7 RAW begins with a generic `zombie on the floor` and attacks that same body again.
- The terminal-target extractor did run, but returned `ACTIVE_OR_UNRESOLVED`. Root cause is authority wording:
  - canonical SOURCE-AUTHORIZED CURRENT STATE does not track the incidental per-segment terminal target;
  - RENDERED CONTINUITY does track it as dead;
  - the extractor prompt called the whole bundle AUTHORITATIVE OPENING STATE but only explicitly said to treat AUTHORITATIVE OPENING STATE as already true, while also labeling rendered continuity supplemental;
  - the 20B therefore treated RAW's vaguer `zombie on the floor` wording as alive and ignored the prior rendered dead-state fact.
- Production commit `dd9b185477684286e2a06de3a7dfecf38d3e2068` makes the narrow terminal extractor's authority rule explicit:
  - canonical state wins only on conflict;
  - rendered continuity is still true for opening facts canonical state does not address;
  - RAW omission or a vaguer noun cannot erase an opening fact;
  - an opening dead/destroyed/resolved target remains terminal unless RAW visibly establishes revival/restoration.
- Regression commit `922de00ce1d90ec04e408aa93b250d2d7483f743` locks that prompt contract.
- Queued `tests-1773` and full `acceptance-1774`.
- Acceptance checkpoint: Segment 7 must reject any RAW that attacks the dead Segment-6 zombie as the newly assigned “last zombie” kill; it must introduce/show an actually unresolved final zombie before the terminal action.


### 2026-09-27 — runtime termination policy: only infrastructure outages are automatically fatal

- User-defined runtime invariant: automatic process termination is allowed only when the required LLM runtime cannot be reached, or when ComfyUI cannot be reached during a render-enabled run. Prompt-generation mode intentionally bypasses ComfyUI. Explicit user cancellation/help remain user-controlled exits, not failures.
- All other failures must recover indefinitely. Local stages may use bounded retry cycles (normally 10 attempts), but exhausting a local budget must move control back to an earlier durable stage/checkpoint instead of ending the Python process.
- Audit found the previous application boundary violated this rule: uncaught `BeatGenerationError`, `ValueError`, `RuntimeError`, workflow/render errors, etc. were printed as “best effort” and then the process ended.
- Production commits:
  - `d53ebabbd5864939a478da1f07159f3fc0842707`: adds a persistent application recovery supervisor; recoverable exceptions restart from the durable generation checkpoint; final render-barrier failures escalate to recovery; stitching now retries forever in 10-attempt cycles instead of giving up.
  - `668aa27a46753eb153ad376d1caf195329ee2d6e`: preserves `LLMConnectionError` through ARC/source-span broad retry handlers so an actual LLM outage cannot be accidentally swallowed; incomplete render sets no longer fall through to best-effort stitching.
  - `c028ecae83e745e9e52378bf549ce6a5362cbece`: recovery resumes only from a checkpoint written/changed by the failed attempt, preventing stale `generation_state.json` from an older run from being consumed.
  - `d7fbe7f38c2fd956dee7d292a92108b05a0215c2`: preserves LLM outage propagation through the remaining ARC create/validate retry scopes.
- Recovery behavior:
  - a recoverable failure after committed segments restarts from the next uncommitted segment;
  - a failure before a trustworthy current-run checkpoint restarts from the beginning/earlier stage;
  - if all segments were committed and a later non-connection failure occurs, recovery deliberately backs up to the final segment rather than terminating;
  - FFmpeg stitch failures retry the same completed set indefinitely;
  - ComfyUI execution/render failures remain recoverable; only inability to connect to ComfyUI is fatal.
- Regression commit `b425eb86c1c491dda3ce92f1a1aa4e56c258ad10` covers supervisor retry and fatal propagation for LLM/ComfyUI connection errors.
- Queued `tests-1775` and full `acceptance-1776`.


### 2026-09-27 — final H3 validation now follows Python-owned truth + tiny extractor architecture

- New direction: do not trust Request 2 / formatter output merely because its JSON parsed and timestamps matched. The actual final H3 string assembled by Python is the render boundary and must be validated there.
- Acceptance 1774 exposed the need: Request 2 still contained `Amy ... flips eggs`, but later deterministic wardrobe reconciliation accidentally consumed the action and the final H3 string contained only `Amy, wearing black tank top and denim jeans.` The pre-assembly formatter checks could not see this loss.
- Final-H3 validation architecture:
  1. Python deterministically pairs RAW SCENE and final-H3 micro-actions by canonical timestamp.
  2. A tiny local extractor sees exactly one RAW micro-action and one final-H3 micro-action.
  3. Extractor returns only `PRESERVED | OMITTED | CHANGED`.
  4. Python owns acceptance: any non-PRESERVED required RAW action rejects the final prompt.
  5. Additional final-H3 invariants should follow the same pattern: deterministic Python contracts plus narrow observation extractors, not one holistic “is this prompt good?” judge.
- Commit `291028805a719b6c45211e6589281db419399091` independently fixes the demonstrated wardrobe-regex bug so canonical wardrobe replacement no longer swallows a following physical action.
- Commit `a92225e1e87357159795634b8341f96bf0c8f1c3` adds the first final-H3 action-preservation extractor and replayable post-Director fixture API.
- Commit `a3786944f47dfb9eb6f7127e5bdac4781e3ab132` adds `tools/run_h3_prompt_fixtures.py`, which runs only final-H3 extractors against saved fixtures.
- Commit `1ca78bf998d716a6c8c6687f49b02a28087d2228` adds the allowlisted bridge job kind `run_h3_prompt_fixtures` for fast local fixture replay after the bridge worker is updated/restarted.
- Commit `ae4c8583a681bf6cfa6049b6fc12d20c67d9e8b7` adds prompt-generation capture flags:
  - `--capture-h3-validation-segment N`
  - `--capture-h3-validation-fixture PATH`
  These save accepted RAW + fully assembled final H3 + minimal authority metadata before ComfyUI and also work in `--test-prompt-generation` mode.
- Seed fixtures:
  - `tests/fixtures/h3_prompt_validation/amy_segment1_preserved.json`
  - `tests/fixtures/h3_prompt_validation/amy_segment1_action_omitted.json`
  Both reuse the accepted Segment-1 RAW from acceptance 1774; only the final H3 candidate differs.
- Queued 20 narrow action-preservation probes `h3-action-1777` through `h3-action-1796` across domestic, fantasy, sci-fi, transfer, repair, travel, and magical cases. Expected labels cover preserved, omitted, and materially changed actions.
- Do not wire this extractor as a production rejection gate until the 20B probe matrix is graded. Once stable, production should reject/regenerate at the final H3 boundary before continuity extraction or ComfyUI.


## Public repository content rule

- The public repository must remain SFW.
- Runtime/user-provided source material may contain arbitrary content, but committed code, tests, fixtures, examples, comments, and documentation must not embed graphic or sexual examples.
- When a semantic distinction depends on such source material, use neutral abstract states/enums plus a tiny extractor that maps the runtime observation to the closest Python-owned state. Python owns the acceptance decision.


### Terminal duplicate-result validation

For Director Request 1 duplicate-result checks, follow the standard project rule: Python owns the state target and required value; the local LLM only observes whether the opening/RAW facts already match it.

- Do not ask the local model to infer a terminal outcome from narrative prose when a typed state effect already supplies the target and value.
- Current production scope is intentionally narrow: `set_barrier_state`, `set_threat_state`, and `set_object_state`.
- Comparator output is `MATCH | NOT_MATCH | UNKNOWN`.
- Python rejects only `MATCH`; both non-match states are allowed to continue.
- Expand the checked state families only when acceptance demonstrates a real duplicate-result failure outside this scope.


### Temporary barrier transitions

Containment/location effects can authorize a temporary crossing without changing a barrier's persistent final state.

- If canonical opening state says a barrier is locked/closed/etc. and the active beat has no `set_barrier_state` effect for that barrier, the barrier must end in its opening state.
- A `set_containment=free` or other authorized crossing can temporarily open/unlock the barrier to make the movement physically possible.
- BEAT CREATE/VALIDATE should stage restoration by beat end.
- Director Request 1 verifies the final barrier state with the existing narrow barrier-state extractor.
- Do not invent an ARC barrier-state effect solely because a temporary transition is necessary for an action.


### Containment overlay invalidates transient spatial frame

A canonical `set_containment` effect changes the subject's spatial frame.

- On any containment transition, clear prompt-derived `pose_action`, `topology`, and `spatial_relationships`.
- For `contained`, set the canonical position to the container and re-add only `inside <container>`.
- For `free`, remove the container-bound position/relationship and let later continuity establish new local staging.
- Do this even when the prompt-derived `position` string already equals the canonical container; matching position does not make other spatial relationships trustworthy.


### Split prompt generation / ComfyUI rendering

Support a two-phase unattended workflow for long runs:

- `--generate-prompts N` performs all LLM-dependent work and saves finalized H3 prompts to `generated_prompts.txt` without contacting ComfyUI.
- `--generate-from-prompts` performs only saved-prompt ComfyUI rendering + stitching and must not contact the LLM.
- `generated_prompts.txt` is the render handoff contract. It must contain enough per-segment/run metadata to preserve the same initial/append/refresh workflow selection and reference/continuity behavior as a normal run.
- Save prompt records incrementally so a long LLM phase can recover without losing already-finalized work.
- On recovery, do not regenerate the beat plan if the existing prompt prefix and generation checkpoint are reusable.

## 2026-09-30 — Director baseline reset: generate first, promote rules from evidence

This section supersedes older Director-specific guidance that treated typed state,
barrier topology, terminal-target state, item carry mode, or completion extractors
as blocking acceptance gates.

- ARC and BEATS are unchanged. Their CREATE -> VALIDATE -> REPAIR -> VALIDATE loops
  remain the semantic planning authority.
- Director Request 1 is now a minimal creative stage:
  - ASSIGNED SOURCE is story authority;
  - CURRENT BEAT is the scene to stage now;
  - OPENING CONTINUITY is advisory frame-0 context;
  - a broad/generic continuity summary may not override a concrete CURRENT BEAT;
  - NEXT BEAT is only the boundary.
- Request 1 no longer receives Python-generated final-state contracts, barrier
  contracts, or HELD/EQUIPPED/STORED item instructions.
- Request 1 structured output is now creation-only: \`{"raw_scene":"..."}\`.
  Model-owned completion booleans were removed from the production schema.
- Existing deterministic Director checks are retained as diagnostics only.
  Hand conflicts, item-state contradictions, missing subjects, topology/crossing,
  barrier binding, containment, early timing, and End-continuity structure may emit
  warnings but do not trigger regeneration.
- Independent completion, terminal-target, barrier-side, barrier-traversal, and
  barrier-state LLM checks are no longer called from the Director generation path.
  Keep the helper code for experiments/regressions until evidence shows whether any
  narrow check deserves promotion back to a blocker.
- Request 2 remains a formatter/translator. Malformed formatter responses may retry
  up to three times; timestamp correspondence/syntax problems are diagnostic only
  after deterministic normalization and do not block the run.
- Director content failures must not invalidate a valid ARC/beat plan. Recovery
  resumes from the last committed segment/checkpoint and retains planning.
- Development method from this checkpoint:
  1. generate the complete prompt set whenever transport/parser output is usable;
  2. compare all prompts to gold;
  3. collect concrete recurring failures;
  4. add the smallest generic rule only when full-run evidence shows it is needed;
  5. never add a rule merely to make internal state more formally complete.
- Gold-prompt principle: optimize for story-visible continuity needed by the next
  clip, not a perfectly normalized world-state ontology. Refresh segments may
  restate important visible state more strongly; append segments should lean on
  video continuity and only concise relevant state.



## Configurable canonical character facts (2026-09-30)

Before ARC/BEAT planning, establish user-selected stable character facts once.

Configuration:
- `canonical_data.txt` is user-editable and defines which character facts are canonicalized.
- Initial contents: `age, clothing, gender`.
- Field parsing is generic. Comma- or newline-separated labels are normalized to machine keys, so adding a later field such as `hair color` becomes `hair_color` without a code change.
- `name` is reserved because it is always the character identifier.

Canonicalization rules:
- Explicit `story.txt` facts win.
- Explicit `subjects.txt` facts win over inference.
- Missing configured values are chosen once by the local LLM, then frozen in `character_canon.json`.
- `character_canon.json` stores the configured field list plus the resulting values.
- The canon hash includes story text, `subjects.txt`, and the configured canonical field list. Changing any of them invalidates and regenerates the canon.
- Canonical clothing is the baseline outfit; later dirt/damage/substances/wetness are continuity state rather than a new baseline.
- Python owns and reuses the resulting canonical values deterministically. Later calls receive those exact facts rather than independently re-inventing them.
- ARC planning/validation may receive canonical facts as context.
- BEAT CREATE receives them under `CHARACTER FACTS`.
- Director Request 1 receives the canonical starting facts on Segment 1. It establishes applicable identity/appearance facts for characters already present in that segment; it must not introduce a future character merely to display canon.

### Beat CREATE prompt contract

Beat CREATE is a creative expansion call. Its normal prompt contains:
- `SOURCE FILM`: authoritative source span for the current chapter;
- `KNOWN SUBJECTS`: known character names;
- `CHARACTER FACTS`: persisted configured canon;
- `ASSIGNED EVENTS`: the exact event(s) owned by each requested beat;
- `PREVIOUS BEAT` only when an actual previous beat exists;
- repair/user-specific sections only when actually applicable.

Do not emit empty/N/A barrier sections merely because deterministic state machinery exists elsewhere. The normal creative prompt deliberately stays small.

Core Beat CREATE rules:
- one beat per assigned event;
- source gives context; assigned event says what happens now;
- canonical character facts are context and should not be restated unless they change;
- no later story action may be pulled forward;
- preserve the assigned physical action and participant roles;
- finite work must visibly happen and finish within the beat;
- repeated/ongoing processes become different story-compatible instances;
- creativity is expected where source detail is unspecified, but major plot events/outcomes may not be invented;
- one to two concise sentences per beat;
- maintain spatial awareness;
- prefer names over pronouns to reduce participant ambiguity.

This prompt supersedes the older Beat CREATE contract that injected barrier-name, closed-boundary, preserved-barrier, and beneficiary-specific prose into every generation request.

