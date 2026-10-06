# MiniMax H3 Project Notes

This file is the persistent source of truth for the current MiniMax H3 architecture and acceptance target. Historical iteration details belong in Git history, not here.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `object-state-work`

## Primary goal

The goal is:

> **story.txt -> gold-standard MiniMax H3 prompts**

The pipeline is disposable. Any intermediate representation, LLM call, validator, state object, or Python layer exists only if it improves that path.

## Project progress checklist

This checklist is the compact current-status view. Historical sections below explain why each decision exists. A checked item means the architecture has been implemented and has enough production evidence to treat it as provisionally complete. Unchecked items are active verification targets or remaining work.

### Story / planning / local-LLM pipeline

- [x] **story.txt remains the sole narrative authority.**
- [x] **Summary -> expanded story** path is established, with filmable/literal prose and a deliberately small prompt.
- [x] **Expanded story -> Beats** is established; SUMMARY is a final guide and Beats preserve required source ordering/content.
- [x] **Beat validation/repair** handles finite endpoints, beneficiary delivery, explicit participant/object enumerations, and source-faithful completion without inventing unnecessary terminal outcomes.
- [x] **20B-class local runtime is the production target.** GPT-5.6 Sol is development/evaluation only.
- [x] **Task-specific LLM sampling/reasoning profiles** are separated by job rather than loaded model.
- [x] **Prompt generation and ComfyUI rendering can be separated** for a one-GPU workflow.
- [x] **Bridge/mailbox workflow retired.** Local runs + uploaded artifacts are the active acceptance/debugging path.

### Director / H3 prompt quality

- [x] **Two-stage Director path:** Request 1 owns creative RAW staging; downstream H3 handling is lossless/translation-oriented.
- [x] **RAW starts at 00:00.000** and continuation frame zero is a Guide-authority anchor rather than a semantic restage.
- [x] **RAW physical/order coherence** rejects teleportation, omitted prerequisite movement, impossible barrier order, stale end state, unexplained prop changes, and similar causal failures.
- [x] **Post-RAW pronoun cleanup** changes only unambiguous person pronouns.
- [x] **Post-RAW dynamic Subject resolution** owns functional naming of newly staged unnamed foreground characters/creatures.
- [x] **Final H3 action preservation** keeps accepted RAW action authoritative instead of allowing formatter drift.
- [x] **Direct speech handling** uses stable H3 dialogue syntax with Subject speaker IDs.
- [x] **Soundscape and music are separate jobs.** Soundscape is extraction-only; music is the narrow creative audio stage.
- [x] **Good camera movement.** Continuous choreography, natural pan/truck/tilt/pedestal/arc/tracking/reframing, and the periodic reframe rule have produced excellent camera work across roughly the last six production videos.
- [x] **Continuous-take default / no gratuitous cuts** is copied into the actual H3 prompt.
- [x] **RAW timing-feasibility validator accepted in production.** The next tavern run eliminated the prior impossible doorway/table/bar spatial jumps and H3 no longer needed to hide compressed travel with cuts. The validator remains qualitative (temperature 0, no hardcoded minimum interval).
- [ ] **Verify RAW temperature 0.2 + economical-staging rule.** Confirm reduced unnecessary reactions/fluid/object embellishment without making staging too sterile.

### Immediate segment-to-segment continuity

- [x] **Native 22-frame MiniMax H3 AddGuide continuation** is the normal seam mechanism.
- [x] **Guide carries aligned video + audio context** while PREVIOUS SHOT END no longer dictates visible frame-zero composition.
- [x] **All literal 22 overlap frames are removed after guided render** and guided clips do not receive another two-frame seam trim.
- [x] **Current wardrobe/pose/held-state can come from immediate visual continuation** rather than being reset by a Picture reference.
- [ ] **Occasional ~0.25-second continuation replay at segment start.** This has appeared more than once even after literal Guide-overlap trimming. Determine whether it is generated temporal echo inside H3 rather than a retained-frame trim error.

### Location / environment continuity

- [x] **Story-level overall + starting-location extraction** exists and Segment 1 gets authoritative starting-location context.
- [x] **Structured spatial `location_state` extraction:** the existing story-grounded static setting extraction is followed by two SMART extractor passes. The first makes the space explicit with cardinal directions, anchors, dimensions, accessibility, and non-overlap; the second emits both canonical JSON and literal prose derived from that JSON. The JSON is stored in `generation_state["location_state"]`; only the prose is sent to the 3-second location-reference render.
- [x] **Persistent location memory:** generate one character-free 3-second 360-orbit location clip before Segment 1 and reuse it throughout the run.
- [x] **Location-reference audio is deterministically removed with ffmpeg** before conditioning reuse.
- [x] **Location-reference authority is limited to static environment/spatial layout**, not characters or current camera composition.
- [x] **Location continuity accepted.** Recent tavern runs preserved covered room geometry with unexpectedly high accuracy across changing viewpoints.
- [x] **Setting extraction avoids over-promoting action-only props** and treats relative labels such as front/back/side as uncertain unless distinct architecture is established.
- [ ] **Production-verify Director static-setting authority.** Request 1 and RAW coherence now receive the compact extracted static setting and must preserve explicitly described fixed fixtures/lighting placement without forcing off-camera elements into frame.
- [x] **Compact static-space existence bookkeeping.** `location_state` now stores structured location/anchor/object facts separately from the rendered orbit. It is the Python-owned spatial record; the matching literal prose is the visual serialization used to create the orbit.
- [ ] **Multi-room / returning-location stress test.** Verify authority when the story moves between several spaces and later returns.

### Subject identity / character consistency

- [x] **Canonical named characters promote deterministically into the Subject registry** when they appear in accepted RAW.
- [x] **Dynamic functional Subject names are stable** and preserve role/species semantics without same-type alias drift.
- [x] **Named dynamic Subjects carry canonical prose** such as age/gender/clothing where available.
- [x] **Full Python Subject continuity state is text-renderable on re-entry:** position, pose/action, wardrobe, topology, physical condition, held/attached props, injuries/substances, spatial relationships, persistent effects, and terminal absence.
- [ ] **Production-verify generated identity Pictures for dynamic Subjects.** Before first H3 story appearance, a no-source dynamic Subject now gets a 1-second portrait reference whose sampled frame owns identity + current appearance. Later intentional wardrobe/condition changes reuse the prior generated Picture as identity conditioning. Verify first appearance and re-entry stay on that identity.
- [ ] **Verify dynamic identity survives wardrobe changes.** A dynamic Subject's generated Picture may depict current clothing, but versioned wardrobe updates must preserve the same face/head, build, species, and distinguishing traits while allowing semantic clothing to change.
- [ ] **DINO recovery path remains fallback only.** Revisit DINO extraction/cropping if deliberate pre-generated character references fail or cannot cover a use case.

### Clothing / wardrobe continuity

- [x] **Source identity Pictures no longer own current clothing.** Source-backed Subjects use their original Picture for persistent identity/body appearance plus a separate generated current-clothing Picture. Dynamic Subjects with no source Picture use a generated identity + current-appearance Picture that is versioned from its prior identity when wardrobe changes.
- [x] **Current wardrobe is stored in Python-owned Subject state and can be rendered back into re-entry Subject prose.**
- [ ] **Intentional wardrobe-change persistence.** Stress test Outfit A -> explicit change to Outfit B -> character leaves for multiple segments -> character returns while permanent identity reference still depicts A. The return must stay in B.
- [ ] **Wardrobe-change bookkeeping/validation.** Ensure changes occur only when source/Beat authorizes them and stale canonical/reference clothing cannot roll them backward.

### Props / physical bookkeeping

- [x] **Prop identity and acquisition provenance** are enforced: manipulated props cannot silently become another object and newly acquired props need a visible/stated source.
- [x] **Generic transfer physics:** every transfer requires an explicit, distinct, traceable source and destination, with the transferred object/material established at the source first.
- [x] **Spatial travel is generalized:** interacting with something at another established position requires actual subject movement there first.
- [x] **Final continuity state must match the final timed action**, not an earlier convenient state.
- [x] **Barrier/containment and irreversible-state bookkeeping** has deterministic/narrow semantic support from earlier acceptance work.
- [x] **Persistent movable-prop ledger architecture is implemented.** The existing combined-continuity call now also maintains stable IDs and state for distinct reusable/interactable props (for example mugs, glasses, baskets, tools, weapons, keys, and containers), including kind, owner, holder, location, contents, and present/lost/destroyed status. Unchanged props copy forward even when offscreen, so this adds no new always-on LLM stage. Existing source-authorized item effects (held/equipped/stored/dropped/lost) deterministically override prompt-derived ledger state rather than creating a competing inventory authority.
- [x] **Missing-prop handling is proactive rather than generate/reject/regenerate.** Before RAW, only prop-interaction Beats trigger a tiny temperature-0 micro-call. If a required usable prop is not established, it returns one minimal natural staging instruction for Request 1; otherwise it returns nothing. Existing validators remain backstops rather than the normal repair loop.
- [x] **Basic movable-prop persistence accepted in production.** The latest tavern rerun eliminated the prior appearing/disappearing glasses/basket behavior, and liquid/container behavior was acceptable overall. The remaining demonstrated prop defect was semantic ownership: Segment 3 reused Goblin1's tracked mug as serving inventory for Elf1.
- [x] **Owned/held props are not shared inventory.** The pre-RAW prop-staging micro-call and Director now treat another subject's owned/held prop as unavailable unless CURRENT BEAT explicitly authorizes that use/taking/transfer; missing serving props should be staged as distinct ordinary instances instead of hijacking a tracked patron prop.
- [x] **Deterministic final-participant carry-forward.** After dynamic Subject resolution, Python now compares the final timed micro-action with the End continuity state. A named Subject still present in the final action but omitted by End state is copied into that state from the exact final-action evidence, without another LLM call. Explicit exits/leaving/occlusion are not carried.
- [ ] **Production-verify ownership + final-subject/final-prop carry-forward.** Rerun the tavern case and verify Goblin1 remains semantically located after Segment 2, does not wander into Elf1's seat in Segment 3, and Goblin1's mug is not repurposed to serve Elf1. Also verify Dragon1's handed crystal cup survives Segment 4 End state/ledger and remains the drink source in Segment 5.
- [ ] **End-to-end bookkeeping stress test.** Use a story that stores, drops, retrieves, transfers, equips, loses, and later reuses props while characters leave/re-enter rooms.

### Refresh / long-run quality / runtime robustness

- [x] **Clean-refresh loader ambiguity fixed** after location reference added a second video loader.
- [x] **Routine auto-refresh is intentionally dormant by default (999).** The legacy refresh path remains available, but Guide + location-reference behavior is preferred unless long-run degradation gives evidence to re-enable periodic refresh.
- [x] **Missing required workflow nodes fail loudly/fatally** instead of being retried as transient generation failures.
- [x] **Reference-video experiments were narrowed back from full-clip/56-frame history to native Guide continuation** after runtime/VRAM and composition tradeoffs were measured.
- [ ] **Longer-run degradation test.** Run substantially more than six segments before declaring periodic refresh unnecessary for general use.

### Back-pocket experiments — not active work

- [ ] **RefMod:** potential future experiment for persistent-reference efficiency / reduced VRAM-time cost; do not integrate while current reference architecture is working.
- [ ] **Full spatial JSON/scene graph:** intentionally avoided unless existence-level bookkeeping proves insufficient.
- [ ] **DINO-based character harvesting:** fallback if deliberate generated character-reference creation is not reliable.

### Final completion / release acceptance

The project is close to feature-complete when the remaining bookkeeping/identity tests pass. Before calling the pipeline done, run at least one deliberately hostile acceptance story covering:

- [ ] multiple rooms with later returns;
- [ ] dynamically generated named characters that leave and re-enter;
- [ ] at least one intentional clothing change across an absence;
- [ ] prop storage/retrieval/transfer/loss across multiple segments;
- [ ] enough segments to expose cumulative continuation quality drift;
- [ ] a genre/staging pattern materially different from the current tavern and zombie examples (for example high fantasy with nonhuman characters).

If those pass without exposing a new architectural gap, remaining work should be packaging, documentation, usability, and performance rather than another core continuity subsystem.

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

For Director/H3 quality review, invented staging/detail is acceptable by default. Treat it as a real failure only when it:
- creates physical or spatial incoherence;
- changes, distorts, preempts, or otherwise throws off the overall story/assigned beat trajectory; or
- is completely inconsequential to the story, staging, readability, tone, or continuity and therefore adds pure noise.

A harmless invented motion, route, prop interaction, reaction, or staging choice is not a defect merely because it is absent from the source. Do not over-police useful cinematic elaboration.

The project goal is to expand paragraph-scale through multi-page stories into fully staged films. The LLM therefore must supply missing cinematic detail rather than mechanically paraphrasing the source.


### LLM settings by task

LLM request settings are selected only by **what the model is being asked to do**.
The loaded model/formatter must never select temperature, sampling, reasoning,
prompt transport, or validator settings.

Current task profiles:

- `STORY_EXPANSION_LLM_SETTINGS`: continuous prose expansion from the source
  summary; temperature `0.4`, high reasoning, randomized seed.
- `CREATIVE_GENERATION_LLM_SETTINGS`: open-ended creative staging such as
  character canon and ARC create/repair; temperature `0.8`, high reasoning,
  randomized seed.
- `DIRECTOR_RAW_SCENE_LLM_SETTINGS`: Director RAW scene creation; temperature
  `0.2`, high reasoning, randomized seed. RAW remains creative, but uses lower
  sampling than other creative-generation work to reduce gratuitous staging
  embellishment while preserving useful concrete invention.
- `BEAT_WRITING_LLM_SETTINGS`: Beat CREATE/REPAIR; temperature `0`, high
  reasoning, seed `42`.
- `STORY_TO_BEATS_LLM_SETTINGS`: derive Beats from an expanded story;
  temperature `0`, medium reasoning, seed `42`.
- `MUSIC_GENERATION_LLM_SETTINGS`: short non-diegetic score generation;
  temperature `0.6`, medium/256-token reasoning, randomized seed.
- `SMART_EXTRACTOR_LLM_SETTINGS`: spatially demanding extractors that need more
  reasoning than ordinary deterministic analysis; temperature `0`, context
  budget `8192`, medium/1024-token reasoning, seed `42`. The spatial-refinement
  and JSON+text location extractors use this profile.
- `DETERMINISTIC_ANALYSIS_LLM_SETTINGS`: validators, semantic extractors,
  continuity observers, JSON repair, pronoun cleanup, H3 soundscape
  extraction, and every unclassified LLM purpose; temperature `0`,
  low/128-token reasoning, seed `42`.

All profiles use repeat penalty `1.15`. Creative profiles may sample; the
others are deterministic. `ask_llm()` routes from `history_metadata.purpose`
to one of these task profiles.

Formatter selection (GPT/Qwen/Mistral compatibility code) is output parsing and
cleanup only. Formatter classes no longer own `DEFAULT_LLM_SETTINGS`, and
Beat validation no longer swaps prompt/transport settings by active model.

For llama.cpp's OpenAI-compatible request path, reasoning settings are sent
per request. `--deterministic` remains a server-process flag and should be
enabled independently of the loaded model.

Default principle:

> **The task selects the LLM settings. The model never does.**

### Beat SOURCE FILM authority

Beat CREATE and single-beat repair now receive the full narrative from `story.txt`
under `SOURCE FILM`. The local `ASSIGNED EVENT` remains the authority for what
that beat must execute.

Do not substitute the chapter/source-span fragment into `SOURCE FILM`. The full
story provides context; the assigned event prevents later-story work from being
pulled into the current beat.

### Boundary logic during beat perfection

Boundary/barrier enforcement is intentionally dormant during the current beat
optimization phase.

- Beat CREATE gets no barrier/boundary contract blocks.
- The beat semantic validator does not receive doors/windows/barriers/paths,
  containment/accessibility fields, or `set_barrier_state` /
  `set_containment` effects.
- The deterministic preserved-barrier structural rejection is disabled.
- The post-validator closed-boundary destination-presence gate is disabled.
- Underlying boundary helper code remains available but is not on the active
  beat-generation/validation path.

Reintroduce only the smallest specific boundary contract justified by an observed
beat failure.

### Current optimization focus: Director RAW scenes

Acceptance 2776 completed all 8 Beats successfully with a coherent, source-faithful sequence. Beat planning/generation is therefore provisionally stable enough to serve as the upstream Director contract.

Current focus moves one stage downstream:

- inspect **Beat -> Director Request 1 / RAW scene** behavior;
- fix the earliest real downstream failure in order; Request 2/H3 is now active because 2802 reached a valid RAW scene and then lost a material action during formatting;
- keep existing Python canonical-state machinery in place, but do **not** expand or perfect accepted-Beat bookkeeping speculatively;
- accepted-Beat state is supporting continuity data, not a gate that must be artistically perfect before Director testing;
- malformed accepted-state observations are fail-soft: log and ignore the bad auxiliary patch after Beat acceptance instead of aborting generation;
- revisit state extraction only when a demonstrated Director failure traces back to a missing or incorrect state fact;
- continue to keep broad barrier/state contracts out of Beat CREATE unless fresh Beat evidence requires them.

Observed accepted-state oddities such as hand-holding being classified as inventory/equipment or defeated threats receiving noisy status labels are not, by themselves, reasons to delay Director work when the finalized Beat text is correct.

After Request 1 RAW passes structure/coherence, run one tiny deterministic pronoun-resolution pass before H3 formatting. Its only job is to replace unambiguous person pronouns (especially they/them/their and she/her/he/him/his) with explicit names. RAW action/timestamps/order remain authoritative; if the cleanup changes timestamps/structure or is unusable, ignore it and keep the original RAW.

Request 1 RAW acceptance includes one narrow semantic physical/action-order coherence check when a current Beat is available. It reads timed actions literally in order, allows harmless creative staging, and retries only concrete impossibilities or material prerequisite/order contradictions. This is deliberately semantic rather than an expanding pile of Python regex rules.

Request 2 is a lossless formatter, not a narrative authority. If its final H3 output fails the semantic RAW-action preservation check, Python may deterministically substitute the already-valid timed RAW action text as detailed_description and rebuild the H3 prompt. This is preferred over adding more formatter prose or regenerating Request 1.
Once Python deterministically substitutes canonical timed RAW actions into the final H3 detailed_description, action preservation is true by construction; do not ask an LLM to re-judge that same copied text.

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

### LLM result logging

Every production LLM stage, validator, extractor, and cleanup call should print a concise human-readable result to stdout so acceptance/bridge run logs show what the model decided. Prefer compact stage-specific messages such as `Checking pronouns segment: replaced ...`, `...: no replacements`, or validator `VALID/INVALID: issue` messages. Do not make important LLM decisions visible only in hidden request history or metadata.

### Post-RAW H3 boundary

After Request 1 RAW is accepted:
1. a tiny deterministic LLM cleanup may replace only unambiguous person pronouns with explicit names;
2. a narrow post-RAW Subject resolver names distinct unnamed foreground animate participants, reusing an established dynamic Subject only when continuity clearly requires it;
3. Python registers those resolved names in the existing Subject registry before H3 assembly;
4. a tiny deterministic soundscape extractor returns only `overall_soundscape`;
5. a separate narrow creative music call receives the previous segment's music
   when continuing and returns only `non_diegetic_music`;
6. Python copies canonical cleaned RAW directly into `detailed_description` and assembles the final H3 prompt from the Subject registry plus audio fields.

Soundscape extraction and music generation must remain separate responsibilities because
they require different sampling/reasoning behavior. Soundscape output is microphone-audible
only: visual facts such as lighting, expressions, stillness, positions, silent gestures,
persistent state wording, and merely visible motion must not be converted into sound.
Explicit RAW audio cues such as footsteps, laughter, groans, echoes, impacts, or gunshots
must not collapse to N/A; that omission is rejected and retried once. Punctuation-only or
otherwise non-language soundscape results are also rejected and retried once. Music should describe one
short underscore cue, continue the previous musical state, and avoid character/action
narration; overlong music results are rejected and retried once.

After the 2847 frozen-plan acceptance, treat the H3 audio path as locked unless a
future story exposes a concrete regression. Do not continue tuning audio against the
zombie benchmark.

Story-to-beats does **not** own dynamic Subject identity. Beats should describe
unnamed participants naturally and should not create `@Guard1`/`Zombie1`-style
identity handles merely for H3.

Dynamic Subject determination begins only after Request 1 has produced an accepted,
fully staged RAW scene. A narrow deterministic-analysis call may replace distinct
unnamed foreground animate references with stable functional names such as
`Guard1` or `Creature1`. It receives the existing Subject definitions so a known
dynamic identity can be reused when the RAW clearly continues the same individual.
Python then registers those names through the existing Subject registry, which owns
numeric Subject IDs, speaker IDs, persistence, and prompt rendering.

If the post-RAW Subject resolver changes timestamps/shot-script structure or otherwise
fails, keep the accepted RAW unchanged rather than blocking the scene.

Per-call sampler overrides are not used; `ask_llm()` task routing is the sole settings authority.

There is no narrative H3 formatter rewrite after RAW and no semantic LLM preservation
check after Python copies RAW. RAW action preservation remains deterministic by construction.

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

For a normal append beat, the preceding rendered video is **not** a Ref2V source.
Ref2V is reserved for persistent reference media such as character Pictures.

Load the exact final **22 frames** of the preceding rendered clip and connect that
IMAGE batch to ComfyUI core's native `MiniMaxH3AddGuide` at `frame_idx = 0`.
Those frames are a protected overlap on the target timeline. They carry local
composition and motion into the new generation instead of asking H3 to interpret
the previous clip as a separate semantic video reference.

The append render budget includes the duplicated overlap. For a normal 8-second
delivery, render 226 raw H3 frames, remove 20 guide frames immediately after
render, then let the existing two-frame stitch trim remove the remaining overlap.
The delivered clip is still 8 seconds and begins immediately after all 22 guide
frames.

Repair remains on its isolated legacy hybrid workflow and may use a 56-frame
previous-video reference. Clean refresh remains separate and continues using its
22-frame latent context path so refresh still acts as a quality reset.

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

Support a two-phase unattended workflow for long runs and single-GPU systems where the LLM and ComfyUI cannot occupy VRAM at the same time.

Preferred interface:

- `minimax.py <segment_length> <segment_count> [<megapixels>] --generate-prompts COUNT` runs the complete normal LLM pipeline (story expansion/planning, Beats, Director Request 1, Request 2, final H3 validation), saves finalized render-ready prompts to `generated_prompts.txt`, and never contacts ComfyUI.
- `minimax.py --use-prompts PATH` loads that exact saved prompt package, performs no LLM/planning work, renders all saved prompts through ComfyUI, and stitches the result.
- This permits a one-video-card workflow: run `--generate-prompts COUNT` with the local LLM loaded, unload the LLM/start ComfyUI, then run `--use-prompts`.
- The prompt package is the complete render handoff contract. It stores timing, workflow mode, continuity metadata, per-segment LoRAs, and reference-image overrides required to reproduce the generated run. Explicit render-time `--imageN` flags may override saved image paths.

Legacy compatibility:

- `--generate-prompts N` remains supported for count-driven prompt generation.
- `--generate-from-prompts` remains supported as the legacy default-path render command using `generated_prompts.txt`.

Save prompt records incrementally so a long LLM phase can recover without losing already-finalized work. On recovery, do not regenerate the beat plan if the existing prompt prefix and generation checkpoint are reusable.

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
- Request 1 structured output is now creation-only: `{"raw_scene":"..."}`.
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

Beat CREATE is a semantic expansion call with temperature-0 generation. Its normal prompt contains:
- `SOURCE FILM`: authoritative source span for the current chapter;
- `KNOWN SUBJECTS`: known character names;
- `CHARACTER FACTS`: persisted configured canon;
- `ASSIGNED EVENTS`: the exact event(s) owned by each requested beat;
- `PREVIOUS BEAT` only when an actual previous beat exists;
- repair/user-specific sections only when actually applicable.

Do not emit empty/N/A barrier sections merely because deterministic state machinery exists elsewhere. The normal Beat CREATE prompt deliberately stays small.

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



## 2026-10-01 — accepted Beat state capture: threat shorthand crash

Acceptance `generate-beats-2710-gpt-accepted-state` demonstrated that broad post-acceptance
state capture is retaining useful concrete continuity (closets, objects, carried/stored items,
threat injuries, and environmental changes), but its first attempt failed after Beat 4 with:
`Beat state patch entity threats.zombies must be an object.`

Root cause:
- the accepted-Beat extractor may use an unambiguous scalar shorthand such as
  `{"threats":{"zombies":"active"}}`;
- canonical threat entries require object records such as
  `{"threats":{"zombies":{"status":"active"}}}`;
- parsing validated the generic canonical patch shape before the accepted-state path had a
  chance to normalize this harmless shorthand.

Fix:
- accepted-Beat state capture now converts only scalar values in the existing canonical
  threat-state enum (`active`, `incapacitated`, `dead`, `removed`, `cleared`) into
  `{"status": value}` before generic state-patch validation;
- ambiguous scalar threat values remain errors rather than being guessed;
- the normalization is accepted-state-specific and does not loosen the generic canonical
  patch contract.

Regression cleanup:
- the broad-capture prompt assertion now matches its actual capitalization;
- the source-span generation regression now reflects the current documented contract that
  Beat CREATE receives the full story under SOURCE FILM while ASSIGNED EVENTS remain the
  chapter-local execution authority.

Commits:
- `f9aa9b60d7646d50db0ade54e9a2ef2e05737383` — normalize accepted Beat threat status shorthand;
- `2e193e1e4c0078e75d72699abcc327af3933c6f4` — accepted-state shorthand regression;
- `509fd416e52e5a4375125ed906d39cb0896d424a` — align source-span regression with full-story Beat context.


### Functional Subject labeling refinement (2851–2853)

Fresh planning runs proved the Python marker path works, but model compliance was
incomplete. Run 2851 produced Zombie1-Zombie4 and Python carried all four into
`characters_introduced`; runs 2852/2853 marked only Zombie1 and left later distinct
attackers as generic prose.

The beat-writing rule now requires every distinct unnamed animate foreground participant
who acts or is acted on to receive a stable marked handle, even for a one-beat appearance.
Only truly interchangeable collective groups may remain unlabeled.


### 2026-10-02 — Dynamic Subject determination locked
- Dynamic Subject identity is owned post-RAW, not by Beats.
- The resolver operates on finalized timed RAW, preserves the exact `End continuity state:` via Python, and may add only functional identities for unnamed foreground animate participants.
- Identifiers already present in accepted RAW are immutable across Subject resolution; deterministic alias drift such as `Will1`, `Amber1`, or `Zombie2_1` is restored/rejected.
- Python remains authoritative for Subject IDs, speaker IDs, persistence, registration, and scene-scoped H3 filtering.
- Acceptance 2868 verified clean dynamic registration (`Zombie1`, then `Zombie2`/`Zombie3`) with no identifier-alias corruption. Treat this area as locked unless new evidence shows a regression.
- Next major gold-gap target: camera choreography.


## 2026-10-02 update — generated-video postmortem hardening

A 50-second fantasy-tavern production render exposed six concrete upstream failures.
The fixes are intentionally narrow and preserve the current post-RAW architecture:

1. Director RAW coherence now explicitly verifies that the trailing
   `End continuity state` matches the state produced by the final timed action.
   It must reject stale earlier-frame positions/props/barrier state.
2. Post-RAW Subject resolution now uses the most specific explicit role/species
   for functional names (`Dragon1`, `Griffin1`, etc.); `CreatureN` is reserved
   for genuinely unknown types. Numbered dynamic Subjects also carry deterministic
   semantic prose such as `Griffin1 is a griffin.`
3. A deterministic Subject backstop collapses an accidental same-type alias such
   as `Griffin` or `Griffin2` to the one established `Griffin1` unless RAW
   explicitly introduces another/new/second individual.
4. Beat validation no longer treats an ordinary story/staging prop as unavailable
   merely because canonical state does not list it. Missing state is unknown;
   only explicitly absent/destroyed/inaccessible props are unavailable.
5. Finite-endpoint checks no longer invent terminal outcomes for story events whose
   required event is the visible activity itself (for example reading, inspecting,
   polishing, watching, walking, or working). Explicit arrivals, retrievals,
   handoffs, destruction, capture, completion, and stated final conditions still
   require observable endpoints.
6. The Director's one-continuous-take rule is now copied deterministically into the
   actual H3 detailed-description prompt: no cuts/cutaways, continuous camera
   movement only for reframing.

Focused regression coverage lives in `tests/test_postmortem_regressions.py`.
No bridge job is queued; the next acceptance step is the user's fresh local run.


## 2026-10-03 update — 8x6 render boundary hardening

Postmortem of the 48-second, six-segment render produced four focused follow-ups:

1. Director RAW now must begin at `00:00.000`. The system prompt states the
   frame-0 requirement and deterministic RAW structure validation rejects any
   first timed micro-beat later than zero.
2. The existing RAW physical/coherence validator now receives
   `PREVIOUS SHOT END` and checks that the first timed action is physically
   reachable from it without omitted subject travel, teleportation, hidden
   location changes, or unexplained prop/state changes.
3. H3 Subject filtering now preserves a dynamic video-only Subject definition
   whenever that Subject's canonical name appears in non-tagged-dialogue scene
   prose. This protects identities such as `Creature1` from being dropped when
   malformed quotation punctuation confuses the stricter visual-identity mask.
4. The H3 no-dialogue constraint is now natural prose
   (`No intelligible speech or singing is heard in this segment.`) rather than
   a metadata-looking `SPOKEN DIALOGUE:` label. Continuity Phase 2 also returns
   immediately without an LLM call when placeholder pruning leaves no facts
   beyond `version`.

Regression coverage was added to `tests/test_postmortem_regressions.py`.
Bridge job `tests-20261003-boundary-v1` targets
`summary-to-story-test` and the postmortem/requested-prompt regression suites.
At documentation time the bridge result had not yet been published; do not mark
this checkpoint test-green until that result exists.


## 2026-10-03 update — local-only acceptance workflow

The GitHub mailbox bridge is retired from the active development loop unless the
user explicitly decides to resurrect it. Do not queue bridge jobs or wait for
`gpt-runtime` results during normal iteration.

Current acceptance loop:

1. ChatGPT edits and commits focused changes to `summary-to-story-test`.
2. The user pulls/runs the program locally.
3. The user uploads the resulting video/log/state/prompt files directly into chat.
4. ChatGPT analyzes those local-run artifacts and makes the next focused changes.

Historical bridge code/results remain repository history/evidence only and are
not the default execution path.


## 2026-10-03 workflow update — bridge retired

The GitHub mailbox/bridge is no longer part of the active development or
acceptance workflow unless explicitly resurrected later.

Current workflow:
- ChatGPT edits and commits the active repository branch.
- The user pulls/runs the program locally.
- The user uploads generated prompts, state/history artifacts, videos, and other
  local results directly into chat.
- Those uploaded local-run artifacts are the acceptance/debugging source of
  truth.

Do not queue new `gpt-runtime` bridge jobs or wait for bridge results unless the
user explicitly asks to restore the bridge workflow.


## 2026-10-03 update — six continuity fixes from 8x6 acceptance render

The 48-second / six-segment local acceptance render established that clean refresh is
architecturally justified and should remain. The continuation chain showed the visible
identity/seam accumulation; the Segment 5 -> 6 clean-refresh boundary was one of the
cleanest transitions in the run. Refresh exists to reset generation quality rather than
repeatedly conditioning on decoded/generated video indefinitely.

Implemented six generic fixes:

1. **Dynamic Subject Video-1 origin is now based on actual previous visibility.**
   Final H3 subject definitions strip historical Video-1 markers first, then add exactly
   one continuation marker only for Subjects visible in the immediately preceding video.
   A Subject introduced in the current segment therefore does not claim to be continued
   from <Video 1>. Dynamic Subject definitions without a Video-1 clause are now valid
   registry syntax.
2. **Continuation frame 0 is an inherited anchor.** When PREVIOUS SHOT END exists,
   Request 1 must use 00:00.000 only to preserve the inherited subjects, positions,
   props, and opening composition. CURRENT BEAT action and newly introduced Subjects
   begin immediately after frame 0 rather than restaging the shot at the seam.
3. **The RAW coherence validator no longer rejects legitimate new participants.**
   A participant introduced by CURRENT BEAT need not exist in PREVIOUS SHOT END; only
   already-established subjects/state must be physically reachable from the inherited
   frame.
4. **Functional Subject names propagate into End continuity state.** When a species/
   role has one unambiguous canonical functional Subject (for example Centaur1), generic
   end-state references are deterministically canonicalized. This prevents the continuity
   guard from discarding correctly extracted dynamic Subject state merely because the
   Director end-state reverted to an anonymous species noun.
5. **Explicit source enumerations must survive Beat conversion/repair/validation.**
   Story-to-Beats and Beat repair now explicitly preserve listed participants,
   recipients, targets, or objects instead of collapsing a meaningful list into a generic
   group label.
6. **No-dialogue wording now forbids spoken dialogue only.** The final H3 fallback is
   `No intelligible spoken dialogue is heard in this segment.`, so story-required
   singing/chanting/background song is not contradicted.

Focused regressions were added to `tests/test_postmortem_regressions.py`. Tests are
committed but are not considered accepted until the user runs them locally.

### Active development responsibility

For overall continuity architecture, accumulated project rationale, cross-run postmortems,
and continuity/state changes, this ChatGPT thread is the source-of-truth maintainer.
Local Codex may be used for isolated feature additions (for example CLI flags), after
which the latest merged branch must be re-read before continuity changes are made.


### 2026-10-03 follow-up — frame-zero structural compatibility

The timed-state padding guard now explicitly exempts only `00:00.000`, so an
inherited frame-zero line may truthfully say a subject remains/stays beside an
already-open/closed object without being rejected as padding. Every later timed
micro-beat still must advance visible action. This completes the inherited-frame
anchor contract without weakening later-shot pacing validation.


## 2026-10-03 update — full previous-video reference for append/repair

The 8x6 fantasy-tavern acceptance showed two remaining continuation failures when
important information had moved off camera near the preceding segment boundary:
Amy's current wardrobe reverted to her Picture reference when Segment 2 ended on
the goblin, and the room's subject placement reset when Segment 4 ended on a
close-up before Segment 5 widened again.

Append and repair reference-video conditioning now use the complete previous clip
when it is 15 seconds or shorter, and the most recent 15 seconds for longer clips.
For the normal 8-second case, the loader now passes all 192 aligned frames instead
of only the final 22. Clean refresh intentionally retains its 22-frame latent
context path.

Picture-backed continuation Subjects now state that their beginning-of-target-video
`wardrobe` comes from `<Video 1>`, replacing the weaker phrase `clothing
condition`, which could be interpreted as damage/cleanliness rather than the
underlying outfit.


## 2026-10-03 update — continuation reference reduced to 56 frames

The full-previous-clip experiment improved some off-camera continuity but roughly
doubled runtime and saturated GPU VRAM, while visual improvement was mixed. Append
and repair therefore use the most recent 56 frames (~2.33 seconds at 24 fps).
For an 8-second/192-frame segment this is `skip_first_frames = 136` and
`frame_load_cap = 56`. Refresh remains 22 frames.

The same acceptance exposed malformed Request-1 RAW of the form
`Frame 0 (At 00:00.000, ):` with actions moved into following bullets. Timestamp
parsing previously saw the embedded timestamp and accepted the structure. Request-1
structure validation now requires every timed micro-beat to begin directly with
its timestamp on a new line and to contain action text on that same line. This is
an upstream RAW validator fix; no formatter rule was added.


## 2026-10-03 update — native 22-frame Guide continuation

Normal append continuation no longer passes the previous clip through
`MiniMaxH3ReferenceToVideo`. Ref2V remains responsible for persistent Picture
references only. Python now takes the exact final 22 decoded frames of the
previous rendered clip and adds them at frame 0 through ComfyUI core's native
`MiniMaxH3AddGuide` node.

The 22-frame guide is a protected opening overlap, not a semantic `<Video 1>`
reference. Continuation H3 prompts therefore no longer emit `<Video 1>`
authority clauses for the preceding clip. Picture-backed identity remains on
Picture references; current opening pose/wardrobe/position are physically
anchored by the Guide; semantic changed state remains Python/continuity owned.

For an 8-second delivery, append renders to 226 raw frames. Python removes 20
of the 22 overlap frames immediately and retains the existing two-frame stitch
trim, so the delivered clip begins exactly after the Guide while preserving the
requested duration.

Director continuation now has an explicit ~0.92-second airlock and deterministic
validation rejects a second timed micro-beat before it ends. Coherence validation
also rejects silently dropping a foreground participant still visible in the
final timed action and rejects moving an occupied chair/stool/seat without
stated occupant movement.

Dependency: no new custom node. ComfyUI core must include native
`MiniMaxH3AddGuide` ("Add Guide for MiniMax H3"). A missing node is treated as
a fatal configuration error instead of a recoverable render retry.


## 2026-10-03 update — Guide audio + frame-zero authority fix

The first native-Guide acceptance improved visual continuity substantially, but the
stitched render still had hard boundary cuts at the starts of Segments 4 and 5 and an
audible score discontinuity entering Segment 2.

Postmortem found two separate causes:

1. The native Add Guide node was receiving the 22-frame video tail but not the matching
   audio tail. Append now sends both the aligned video frames and their soundtrack to
   MiniMaxH3AddGuide, with both video and audio VAEs connected. This follows the native
   H3 continuation contract and gives generated audio an actual preceding waveform rather
   than only a text instruction to continue the score.
2. Request 1 was reconstructing frame 0 from prompt-derived PREVIOUS SHOT END. Once the
   tavern accumulated several Subjects, that semantic state listed off-camera characters;
   the final H3 prompt therefore competed with the real Guide image and encouraged a new
   wide composition exactly when the hidden Guide overlap ended. For continuation only,
   Python now replaces the 00:00.000 line with a generic Guide-authority anchor. PREVIOUS
   SHOT END remains semantic physical context but no longer claims which Subjects are
   visible or how the camera is framed at the seam.

The 22-frame Guide length is unchanged for this test. Do not widen it yet; first determine
whether removing the text/Guide conflict plus carrying audio resolves the remaining seams.
Active branch: h3-add-guidance-test.


## 2026-10-03 update — hide native-Guide timing from Director

The first rerun after the Guide-authority change exposed a local-LLM regression before
Segment 2 could render: Request 1 repeatedly malformed timestamps and sometimes omitted the
required trailing End continuity state. The failure coincided with asking the 20B Director
to reason about an 8.91667-second synthetic clip and a 0.92-second continuation airlock.

Architecture is simplified again:
- Director always writes and validates the ordinary delivered segment timeline (for the
  current test, exactly 8 seconds).
- The prompt no longer asks the LLM to reason about 22 hidden Guide frames or a 0.917s
  airlock.
- After Request 1 passes normal 8-second structure/coherence validation, Python shifts every
  nonzero continuation timestamp by the exact Guide duration (22/24s, rounded to 917ms for
  H3's millisecond prompt syntax).
- Python then replaces only the 00:00.000 line with the generic Guide-authority anchor.
- The ComfyUI render still allocates the longer raw duration and still removes the Guide
  overlap before delivery, so delivered story timing remains aligned with the original
  8-second Director plan.

This keeps hidden render mechanics deterministic and outside the local model's job.


## 2026-10-04 experiment — persistent location-state reference

Historical experiment branch (merged to `main`): `location-state-test`.

The seamless 22-frame native AddGuide continuation is frozen. This experiment targets only
off-camera spatial persistence.

At run start, the expanded story is used to establish the broad location as before. A second
small deterministic-temperature LLM extraction now returns only static setting facts actually
supported by the expanded story (architecture, layout, fixtures, entrances, surfaces,
persistent furniture, landmarks, lighting sources). When the story is vague, the extractor
falls back to the broad location and H3 is allowed to design unspecified details.

Before Segment 1, Python renders one character-free 2-second panoramic H3 location video.
Configured Picture references are deliberately disconnected for this render. The resulting
video is saved separately and is never stitched into the story.

For normal initial/append segments, the same clip is supplied as Ref2V `<Video 1>` and the
prompt states that it owns only static environment/spatial layout. Append's existing 22-frame
native AddGuide remains a separate loader and continues to own exact seam composition and
temporal continuation. Location-reference audio is never supplied.

The clean-refresh conditioner has no Ref2V video input, so refresh samples four frames from
the same location clip into its existing reference-image batch. This avoids replacing the
proven refresh architecture while keeping static environment evidence available.

Characters/dynamic subject state are explicitly out of scope for this experiment.


## Current continuity decisions — 2026-10-04

These decisions supersede older refresh/location notes above where they conflict:

- Persistent location memory is a single character-free 3-second 360-orbit
  reference video rendered before Segment 1 and reused for the run. The latest
  tavern acceptance showed near-complete consistency for geometry visible in
  that reference.
- Routine clean refresh is disabled in practice by the default
  `DEFAULT_REFRESH_INTERVAL = 999`. An explicitly supplied numeric refresh
  interval is authoritative; source-span chapter refreshes are only a legacy
  fallback when no interval is supplied.
- Native AddGuide continuation owns ordinary segment-to-segment visual
  continuity. Its full 22-frame overlap is removed once during guided-append
  postprocessing; stitching must not trim another two frames from guided clips.
- Summary-to-story expansion should remain creative enough to stage the source,
  but its physical prose must be literal and filmable. Attachment, movement,
  action targets, containers, and destinations may not depend on figurative
  wording. Default story temperature is 0.4.
- Explicit speech in a Beat is explicit speech in RAW/H3. Indirect actions such
  as "asks for a pint" or "orders a pint" must be rendered as short direct
  `<d>...</d>` dialogue; once the speaker's dynamic Subject is registered,
  Python supplies the stable speaker ID, e.g.
  `Goblin1 (S3) said <d>Give me a pint.</d>`.
- Post-RAW dynamic Subject resolution is a required pre-H3 identity stage, not a
  best-effort decoration. A resolved foreground Subject must be registered in
  the same segment in which it first appears or generation stops before render.
- Continuous-take staging must preserve physical travel. A subject established
  at one location cannot interact with a distant location without explicit
  timed movement there.


## 2026-10-04 update — location wording, action pacing, RAW sampling

The latest tavern acceptance confirmed that the persistent location-reference
video is working well for room geometry, while several remaining failures were
caused by RAW staging/timing:

- Static setting extraction must not treat relative action wording as proof of
  separate architecture. Labels such as front/back/side door or left/right table
  are preserved only when the story establishes multiple distinct instances or
  the relative identity is itself a persistent architectural fact. With one
  established instance, use a generic static description such as `entrance door`.
- Director RAW must budget visible time for every physical prerequisite it
  invents. Movement, acquisition, positioning, opening, or another prerequisite
  that must precede a dependent action gets its own earlier timed micro-beat
  instead of being compressed into the same timestamp.
- A separate temperature-0 timing-feasibility validator now checks consecutive
  RAW timestamps and rejects only obvious compression that would force a hidden
  cut, teleport, skipped prerequisite, or instantaneous relocation/manipulation.
  It deliberately uses no fixed minimum interval.
- Transfer physics are generic: every transfer must have an explicit, distinct,
  traceable source and destination, and the transferred material/object must be
  established at the source before reaching the destination.
- RAW invention remains allowed, but optional secondary reactions, extra
  consequences, and extra object/substance motion should not be added once the
  required action is already readable.
- Director RAW now uses its own task profile at temperature `0.2`; other
  open-ended creative generation remains at `0.8`.

A structured static-space catalog remains a future experiment, not current
architecture.


## Continuity authority model — target architecture

The continuity system should use different evidence for different kinds of
state instead of asking one representation to solve every continuity problem:

- **Location not externally referenced:** generate one short character-free
  3-second 360-orbit location video before Segment 1 and reuse it as the
  persistent location reference. This video is the visual authority for the
  location's appearance, geometry, layout, fixtures, entrances, furniture, and
  other static spatial relationships. Text/JSON should not attempt to reproduce
  its geometry when the visual reference already carries that information.
- **Current character clothing:** implemented as a parallel generated
  Picture reference. When a visible character first needs a generated visual
  reference, or the canonical current wardrobe changes, render a 1-second
  front-facing neutral character clip from the existing character description
  and current wardrobe, sample the 0.5-second frame, and register that Picture
  as clothing-only authority. External/original Pictures continue to own
  identity; the generated Picture exists specifically so old reference-image
  clothing cannot override current wardrobe.
- **Immediate visual state:** native AddGuide continuation frames own the exact
  state at ordinary segment seams: current composition, pose, visible clothing,
  held objects, nearby subjects, and other details H3 can directly continue
  from the preceding frames.
- **Semantic state:** Python/LLM bookkeeping owns facts that cannot safely be
  inferred from a visual reference alone: subject presence and identity,
  current wardrobe, prop possession/provenance/transfers, intentional state
  changes, and which architectural/interaction elements have actually been
  established. A future compact static-space catalog may therefore be useful as
  an *existence validator* (for example, rejecting "Amy grabs the broom from the
  closet" when no closet has been established), rather than as a textual map of
  coordinates already represented by the location-reference video.

In short, the intended authority split is:

- unreferenced location -> generated 3-second orbit -> persistent location ref
- current character wardrobe -> generated 1-second front-facing clip -> 0.5-second clothing-only Picture
- immediate seam state -> AddGuide overlap frames
- nonvisual/history-dependent facts -> semantic bookkeeping

This division is intentional. Persistent visual references should establish
what things look like; semantic bookkeeping should establish what exists, what
changed, who owns or wears what, and whether a requested action is physically
and causally legal. Avoid duplicating visual geometry in text/JSON unless a
validator specifically needs an existence-level fact.


## 2026-10-04 update — persistent movable-prop ledger and proactive staging

The latest tavern run closed the remaining obvious spatial/travel failure: the prior
doorway/table/bar jumps were gone. The remaining visible continuity failures were ordinary
movable props—especially glasses and the basket—appearing or disappearing across actions
and segment boundaries.

The prop solution deliberately avoids another generate -> validate -> reject -> regenerate
cycle:

1. The existing combined-continuity call, which already runs while H3 renders, now also
   maintains a separate persistent movable-prop ledger. This adds no new always-on LLM call.
2. Distinct reusable/interactable props receive stable IDs such as `mug_1` and carry
   `kind`, `owner`, `holder`, `location`, `contents`, and `status`
   (`present`, `lost`, or `destroyed`). Unchanged props copy forward even when
   offscreen. Existing source-owned `set_item_state` effects remain higher authority:
   held/equipped/stored/dropped/lost state is deterministically overlaid onto the ledger.
   A source-owned destroyed object also marks a uniquely matching tracked prop destroyed.
3. Architecture, fixed fixtures, furniture, clothing, and ambient clutter are excluded
   from this ledger. Static architectural existence remains a separate future bookkeeping
   concern.
4. Before Director RAW, Python cheaply screens for strong prop-interaction verbs. Only
   those Beats may run a tiny deterministic-analysis micro-call. The call compares CURRENT
   BEAT, PREVIOUS SHOT END, and the prop ledger. If the Beat assumes a missing usable prop,
   it returns one short natural staging sentence to make that prop available before the
   dependent action. If the prop is already available—or the Beat itself acquires it—the
   result is empty.
5. The micro-call may not rewrite the Beat, change its outcome, add dialogue/characters,
   replace an established prop, or invent unsupported architecture/storage. When no
   established storage source exists, it may place the needed prop directly at a natural
   interaction point.
6. Request 1 receives the persistent prop ledger plus any one-line availability staging
   before generating RAW. The existing physical/coherence validator remains a backstop,
   not the primary prop-repair mechanism.

Next acceptance should focus on mug/glass/basket persistence and transfer/container state.
Do not reopen the location-reference or spatial-timing architecture unless that run shows
a regression.

## 2026-10-04 update — prop persistence accepted; ownership and final-subject carry-forward

The next tavern acceptance showed that the persistent movable-prop ledger solved the main
visible object-continuity problem: glasses/basket no longer appeared and disappeared, and
fluid/container behavior was acceptable overall.

One Segment 3 failure exposed two narrower bookkeeping defects:

1. Segment 2's final timed action still had Goblin1 present and stepping back toward the
   hearth, but Request 1's End continuity state omitted Goblin1 entirely. Combined
   continuity therefore knew Goblin1 existed but lost his current position, leaving H3's
   22-frame Guide to visually continue a subject whose semantic state was effectively
   locationless.
2. The prop ledger correctly preserved `mug_1` as Goblin1's owned mug on the counter,
   but Director treated that tracked mug as generic serving inventory and used it as the
   source for Elf1's drink.

Implemented response:

- After post-RAW Subject resolution gives every dynamic participant a stable name, Python
  deterministically inspects the final timed micro-action. If a named Subject is still
  present there but the End continuity state omits that Subject, the exact final-action
  evidence is appended to End state. This is bookkeeping repair, not another semantic
  validator or generate/reject/regenerate cycle. Explicit leave/exit/fully-occluded final
  actions are not carried.
- Prop ownership/holding is now an availability boundary. A ledger prop owned or held by
  another Subject does not count as shared inventory unless CURRENT BEAT explicitly
  authorizes reuse, taking, or transfer.
- The existing conditional prop-staging micro-call is instructed to prefer a distinct
  ordinary instance when the only matching tracked prop belongs to somebody else, and
  Request 1 receives the same ownership rule in both its Director contract and injected
  prop-state block.
- No new always-on LLM call was added.

Next acceptance: rerun the same tavern case and specifically verify Segment 2 -> 3:
Goblin1 should retain his final location/state, should not drift into Elf1's seat, and his
tracked mug should remain his rather than becoming Elf1's serving source.

## 2026-10-04 update — one-second character clip -> current-clothing Picture

The planned character-reference experiment has been replaced by a narrower implementation
driven by the observed Amy wardrobe regression.

- Trigger: a visible character has no generated clothing Picture yet, or the character's
  canonical current wardrobe has changed since the last generated Picture.
- Render: an isolated 1-second H3 clip using the same base workflow strategy as the
  location-reference render, but with a static front-facing character instead of a 360
  environment orbit.
- Sample: frame at 0.5 seconds becomes the generated reference PNG.
- Semantics: the added prompt line is clothing-only, e.g.
  `<Picture 2> references only the clothing that Amy is currently wearing.` Identity
  remains owned by the normal Subject/original Picture/video-continuation system.
- Ordering: H3 Pictures are treated as dense positional inputs. Six template LoadImage
  nodes do not reserve six positions. With only Picture 1 active, the first generated
  clothing reference is Picture 2.
- Capacity: existing LoadImage nodes are reused through active Picture 6; Picture 7+ causes
  Python to create additional LoadImage nodes and autogrow reference inputs dynamically.
- Stability: once a character receives a generated Picture number, later wardrobe changes
  replace that Picture's versioned PNG instead of allocating a new number.
- Persistence: generated reference metadata is kept in generation_state.json and copied
  into each saved finalized prompt record.

This adds ComfyUI work only when a character reference is first created or its current
wardrobe changes. It adds no LLM request.

## 2026-10-04 update — unified visual-state media storage

Persistent generated state media is consolidated under `VIDEO_OUTPUT/state`
(normally `<ComfyUI output>/video/state/`):

- `location_reference*.mp4`
- `character_reference*.mp4`
- `minimax_character_ref_*.png`

The state-directory PNG is authoritative and its absolute path is stored in character
reference metadata/checkpoints. ComfyUI's LoadImage restriction is handled by staging a
copy into `COMFY_INPUT` when the workflow is built; the input copy is not the persistent
state source. New renders no longer write to the former `video/location_state` or
`video/character_state` prefixes.

## 2026-10-04 update — identity-conditioned clothing-reference generation

The first generated clothing-reference test exposed cross-authority bleed: because the
1-second outfit clip was rendered from text alone, it could invent a different face/body,
and that invented appearance then influenced later story renders.

Current fix:
- use the Subject's original source Picture as the sole image reference while rendering the
  1-second clothing clip;
- inside that isolated render, source Picture 1 is identity-only authority and text is
  clothing authority;
- final story use remains unchanged: the sampled generated Picture is described as
  clothing-only authority, so it should not redefine the character's identity;
- dynamic/video-only Subjects without an original Picture remain a fallback case.

This preserves the intended authority split:
original Picture -> identity/body; generated current-clothing Picture -> wardrobe.

## 2026-10-04 update — portrait person refs and source-authorized wardrobe regeneration

Person/outfit reference clips are now rendered on a portrait 13:19 canvas. This is isolated
to the one-second character/clothing reference path; the location-reference orbit remains
on the existing landscape canvas.

Clothing-reference versioning is also now event-authorized. Once a character has a clothing
Picture, vision-observed outfit differences do not create a new version. Regeneration occurs
only when the immediately preceding generated segment explicitly changes/removes/adds a
garment or explicitly changes garment condition (for example torn, ripped, stained, muddy,
soaked, singed, or burned). The previous intended clothing-reference state is the base for
that update, rather than the rendered/vision wardrobe.

### 2026-10-04 — dynamic identity Picture authority + transfer/static-setting fixes

The latest tavern render exposed three distinct upstream failures rather than one general
continuity regression:

- generated Pictures for dynamic Subjects (Goblin1/Elf1/Dragon1) existed before their
  story render but were labeled clothing-only, leaving H3 free to invent a different
  creature identity on first appearance;
- Director RAW could preserve transfer provenance while still redirecting the Beat's
  semantic destination (for example, pouring a drink onto a recipient instead of into
  the cup the Beat says is filled), and final End continuity could omit a just-transferred
  prop;
- Request 1 did not receive the already-extracted static setting facts, so RAW could
  relocate a fixed fixture such as a hanging lantern onto a tabletop and then conflict
  with the persistent location reference injected only at final H3 assembly.

Current implementation on `location-state-test`:

- a source-backed Subject keeps its generated current-clothing Picture as clothing-only
  authority;
- a dynamic Subject with no source identity Picture now uses its first generated Picture
  as full identity + current-appearance authority and is explicitly bound to that Picture
  in H3 subject definitions;
- later intentional wardrobe/condition changes for such a dynamic Subject condition the
  replacement render on its prior generated identity Picture rather than inventing a new
  identity;
- an unconditioned first character-reference render no longer refers to a nonexistent
  `<Picture 1>`;
- RAW rules and coherence validation now preserve CURRENT BEAT transfer roles/results,
  reject source-less material motion or substitute spill/drool behavior for an assigned
  drink/transfer, and require a materially changed/transferred final prop to survive into
  End continuity state;
- RAW staging now discourages disposable helper supports/containers/utensils that are
  invented only to settle a prop after the required action;
- Request 1 and the coherence validator now receive the compact extracted static-setting
  description and treat explicitly described fixed fixtures/lighting placement as
  authoritative without forcing off-camera elements into frame.

Production verification is still required. Re-run the tavern case and inspect Segment 2
direct barrel-to-mug staging, Dragon1's first appearance in Segment 4, cup/ale continuity
through Segment 5, and lantern/Elf/table geometry in Segment 6. The broader per-segment
quality-degradation question remains intentionally back-pocketed because this run predates
the exact 13:19 person-reference and no-spurious-regeneration fixes.

### 2026-10-04 — 16GB prompt-package reference planning

A review of the one-GPU / 16GB path found that the split workflow had become
incomplete after dynamic character and location references were added. Prompt-only
generation skipped ComfyUI entirely, but dynamic reference creation and location-reference
creation still happened only inside the live-render path. As a result, a saved
`generated_prompts.txt` could describe story segments without containing enough information
to recreate the reference assets those segments expected.

The package is now a self-contained render plan:

- `reference_jobs` records every ComfyUI-only reference generation step required by the
  saved prompts;
- the persistent location reference is planned during the LLM phase with its setting,
  LoRAs, steps, megapixels, and frozen noise seed;
- each dynamic/source-backed character reference is planned with its exact description,
  Picture slot, immutable version, output PNG path, LoRAs, frozen noise seed, and identity
  dependency;
- later clothing/condition versions never replace the previous PNG. A dynamic Subject's
  v002 job explicitly depends on/stages its v001 generated identity Picture;
- every segment stores its own exact `character_reference_images` snapshot, so Segment N
  cannot accidentally pick up a later clothing version planned for Segment N+K;
- prompt-only H3 assembly now includes the location-reference authority clause even though
  the location video does not exist yet;
- render-only mode executes all saved reference jobs in package order before rendering the
  saved story segments, then uses the per-segment frozen reference snapshots.

This restores the intended 16GB contract: run all LLM work first, unload the LLM, start
ComfyUI, and render the complete saved package without any LLM calls or mutable
"current reference" assumptions.

### 2026-10-04 — per-segment Subject/Picture bindings and sliding retention

Dynamic Subject identity/reference assets are now separated from the Picture numbers exposed
to any one H3 segment.

- The persistent generated-reference registry remains keyed by Subject and keeps the actual
  asset path, reference version, authority, and canonical creation slot. Removing a Subject
  from a segment never deletes its Subject registry entry or reference media.
- Every segment deterministically builds a frozen `reference_bindings` snapshot. Generated
  references are densely assigned after the configured base Picture range, so a Subject can
  legitimately be `<Picture 4>` in one segment and `<Picture 3>` later after another
  generated Subject ages out.
- The same segment-local character-reference map is used to generate H3 Subject/Picture text
  and to wire ComfyUI, preventing prompt/workflow slot drift.
- Configured/base Pictures belonging only to inactive Subjects are recorded as
  `excluded_configured_picture_ids` and disconnected from that segment's workflow as well
  as omitted from its H3 conditioning. Their files/registry identity remain available.
- `generation_state.json` now contains a rich `reference_binding_state`: current bindings,
  explicit/active/removed Subject IDs, configured Picture exclusions, removal policy, and
  per-Subject first appearance, last explicit appearance, inactivity age, threshold,
  binding reason, last bound segment, and full binding history.
- Each completed segment also freezes its exact Subject definitions, segment-local character
  references, and `reference_bindings`. `generated_prompts.txt` stores the same segment
  snapshot plus Picture exclusions, so 16GB render-only replay uses exactly the mapping
  chosen during the LLM phase.

Default removal is deliberately conservative. After a Subject has explicitly appeared
visually, it stays bound until it has gone `ceil(total_segments / 2)` segments without
another explicit visual appearance. This protects passive/background continuity. Expiry is
segment-local only; a later explicit re-entry immediately reuses the persistent identity
asset and creates a new segment binding.

`--disable-subject-removal` disables aging entirely. Once a Subject has appeared, it
continues to remain bound in subsequent segments. The desktop UI exposes the same setting.


### 2026-10-04 — 8/6 acceptance follow-up: transfer semantics, compressed travel, retained background Subjects

The next 8-second / 6-segment tavern render exposed three upstream issues despite strong
location continuity:

- Segment 2 RAW was accepted with the impossible phrase that ale was poured "from" a
  barrel lid. The Director and coherence validator now explicitly distinguish a fixed
  container from its lid/cap/handle/rim/latch; contents must come from the actual container
  or an established dispensing opening/tap.
- Segment 4 again allowed Amy to interact with a shelf/bar-area prop without explicit travel
  from her prior table position. Coherence validation now treats distinct named
  fixture/interaction areas from STATIC SETTING AUTHORITY as established positions and
  requires explicit movement between them.
- The final closing Beat compressed unlatching, crossing the doorway, closing, and locking
  into one timestamp. Timing validation now explicitly rejects sequential dependency chains
  hidden inside a single timestamp when they cannot execute visibly as one continuous take.
- Sliding Subject retention now derives explicit visual evidence from the complete accepted
  RAW scene, including its End continuity state, instead of only the stripped timed
  description. A patron that the accepted final frame says remains present therefore refreshes
  its retention age rather than being dropped merely because it performs no new Beat action.

The uploaded acceptance artifacts predate the new per-segment `reference_bindings` package:
they contain generated character-reference records but no frozen binding snapshots. The next
run must be made from current `location-state-test` and should show `reference_bindings` plus
`excluded_picture_ids` in each generated prompt record before reference-slot behavior is
judged.

Next acceptance: rerun the same tavern case from current branch head. Verify Segment 2 uses
the barrel/container as the ale source; Segment 4 visibly moves Amy to the shelf/bar and the
Dragon reference is both generated and bound; the closing sequence visibly traverses the
door before exterior framing; and background Goblin/Elf identity references remain bound
when the RAW End state keeps them present.


### 2026-10-05 — generated Picture authority preserved in continuation prompts

A continuation-conditioning bug was replacing generated character Picture tags with
"the supplied opening guide" before render. The append/refresh workflows prune blank
configured reference slots before generated character references are attached, so those
blank template slot numbers were incorrectly treated as removed Pictures even when a
generated character reference was about to occupy that same segment-local Picture number.

Fix:

- segment-local generated character Picture numbers are now protected from configured-slot
  exclusion/replacement and canonical Picture remapping at the H3 render boundary;
- generated identity/clothing references therefore remain explicit `<Picture N>` references
  in the actual H3 prompt;
- the opening guide now anchors only a visible Subject's opening pose, position, and physical
  state; it no longer claims wardrobe authority when a Picture reference owns clothing;
- Picture-definition lines are no longer given duplicated opening-guide pose/state suffixes.

Focused regression tests verify that a generated Picture survives blank template-slot
conditioning and that Picture authority lines remain separate from opening-guide continuity.

### 2026-10-05 — deterministic Director RAW structure normalization

Three Request-1 formatting/timing failures are now Python-owned before semantic
validation:

- if RAW has no frame-zero micro-beat, Python inserts the canonical
  `00:00.000` opening-state anchor;
- if the final authored timestamp lands before 75% of the segment, Python moves
  only that final timestamp to the 75% boundary, leaving earlier intervals
  untouched so the semantic timing-feasibility validator still sees compressed
  travel/action exactly as authored;
- Python guarantees exactly one trailing `End continuity state:` marker,
  collapsing duplicates and deriving a missing marker's state text from the
  final timed action.

The Director prompt no longer asks the local LLM to satisfy those exact
structural constraints. The existing structure validator remains as a backstop.
Physical/spatial timing feasibility and prop/state legality are unchanged and
still use their existing semantic validation/retry behavior.

### 2026-10-05 — deterministic run-level H3 visual style

- Added the run-level CLI option `--visual-style "STYLE"`; default is `Live-Action cinematic`.
- This is render/prompt metadata, not story semantics. It is deliberately excluded from the story/source fingerprint.
- Final H3 assembly, not the formatter LLM, owns style placement. Python normalizes every final `detailed_description` to `[Shot 1] {visual_style}, ...`.
- Legacy formatter output beginning `Live-action, cinematic` is removed at the final assembly boundary before the configured style is inserted, preventing duplicate style phrases.
- `visual_style` is persisted in run config/generation state and generated-prompt package metadata. Resume and repair inherit the saved style when no explicit CLI override is supplied.
- `normalize_command_line` preserves the value following `--visual-style` as one argument, including embedded commas. The desktop bridge already launches `minimax.py` with an argv list and now emits `["--visual-style", value]`, so Windows/Linux quoting differences do not leak into the app.
- The desktop Generation settings UI exposes a Visual style text field; no additional text file is required.

### 2026-10-05 — defined-Subject wardrobe authority now comes from expanded story

Pre-defined Subjects now get canonical wardrobe in a dedicated pass after
`expanded_story.txt` is available. Python iterates `subjects.txt` and makes one
small deterministic LLM request per Subject rather than asking one call to classify
multiple characters.

The extractor's key phrase is **appropriate attire**. It preserves explicit outfit
detail from the expanded story and fills only missing normal pieces according to the
Subject's species/body, period, setting, culture, and occupation. It must not dress
dragons/animals/other naturally unclothed beings merely to satisfy a clothing schema;
those return `N/A` unless explicitly clothed. Conversely, an unstated modern human
outfit can be completed with ordinary modern attire such as a T-shirt and blue jeans.

The resulting natural-language outfit replaces `character_canon.json -> clothing`
for that defined Subject and feeds canonical Subject prose plus structured wardrobe
state used by character-reference generation. The original broad character-canon call
is now prohibited from inventing missing clothing; it only copies explicit source
clothing provisionally until this expanded-story extractor runs.

This is intentionally separate from dynamic Subject wardrobe bootstrap. Dynamic
Subjects still receive their one-time outfit from the existing post-RAW resolver.


### 2026-10-06 — structured spatial location-state extraction

Location creation now separates semantic spatial state from the H3 visual reference.

- The existing static-setting extractor still produces the compact source
  description and filters out plot-only props.
- A new SMART spatial-refinement pass rewrites that description with cardinal directions,
  anchor-first layout, overall/object sizes, clear access paths, and non-overlap.
- The altered second SMART extractor converts that refined location into the required
  `Location: ...` + JSON + literal text format. Python parses the JSON into
  `generation_state["location_state"]` and sends only the text description to ComfyUI.
- `SMART_EXTRACTOR_LLM_SETTINGS` is deterministic: seed 42, 8192-token context budget,
  medium reasoning effort, 1024-token reasoning budget.
- The 3-second location-reference prompt now uses the tested compact high-angle,
  character-free 360-orbit wording and no longer includes the contradictory
  `high, low-angle` / `static orbital` language.
- `generated_prompts.txt` also carries the frozen `location_state` in config so the
  prompt-only/render-only package retains the same canonical spatial record.

The next acceptance should inspect the emitted `location_state`, its text serialization,
and the resulting 3-second reference together before changing Beat/RAW spatial logic.


### 2026-10-06 — prefer single-purpose local-LLM extractors

Observed design rule for the local ~20B runtime: prefer small, single-purpose extractor calls over one extractor that must identify, transform, structure, and serialize several kinds of information at once. The extra calls are cheap compared with asking the smaller model to keep multiple semantic jobs straight, and each stage is easier to inspect and tune independently.

Current location pipeline is the concrete example:

1. `static_setting_extract`: decide which static location facts from the expanded story actually belong to the location.
2. `story_setting_spatial_refine`: make those facts spatially coherent using anchors, cardinal directions, dimensions, accessibility, and non-overlap.
3. `story_setting_extract`: convert that spatial description into canonical `location_state` JSON plus the literal text description used for the H3 location-reference prompt.

This separation is intentional. If a bad object is promoted from story action into the room, fix the static-setting extractor; if the right objects are arranged badly, fix spatial refinement; if the spatial facts are correct but JSON/text serialization is wrong, fix the final extractor. Do not push corrective rules downstream when the failure belongs to an earlier stage.

The final extractor still performs two closely related outputs (canonical JSON and text derived from that JSON). Keep it combined for now because the text is intended to be a direct serialization of the same state. If future runs show that the local model compromises either output while doing both, test splitting JSON-state creation and render-text serialization into separate single-purpose calls.


### Extractor retry ownership

Each small extractor owns its own bounded parse/content retry loop. A malformed result from one
extractor must retry only that extractor using its already-computed input; it must not restart
unrelated successful extraction stages. Mixed-output extractors must preserve raw model text until
their stage-specific parser splits structured state from prose.
