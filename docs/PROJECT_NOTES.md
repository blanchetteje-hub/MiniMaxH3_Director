# MiniMax H3 Project Notes

This file is the persistent source of truth for current architecture, testing goals, formatting rules, and deferred action items. Update it whenever a project-level decision changes.

## Primary goal

The goal is not to preserve the current architecture for its own sake.

The goal is:

> Given one story, reliably produce the proper MiniMax H3 prompts needed to render that story well.

Anything may change if evidence shows it is necessary, including:

- story format;
- story arc generation;
- whether a story arc exists at all;
- beat generation;
- Director structure;
- continuity handling;
- prompt formatting;
- Python plumbing.

KISS remains the default, but not at the expense of a real architectural correction.

## Working development loop

1. User runs the program locally.
2. User sends logs/artifacts.
3. ChatGPT inspects the current GitHub branch and the observed failure.
4. ChatGPT edits `gpt-test-branch` directly and commits the fix.
5. User pulls and reruns.
6. Repeat until acceptance goals are met.

Do not default to Codex prompts.

## Locked semantic planning architecture

Unless empirical evidence shows this structure itself is the problem:

### ARC
CREATE -> VALIDATE -> REPAIR -> VALIDATE until valid

### BEATS
CREATE -> VALIDATE -> REPAIR -> VALIDATE until valid

Do not add separate semantic state-preparation, enrichment, coverage, claims, proof, review, or effect-validation pipelines.

State is Python-owned canonical data.

`state_effects` live inside story-arc `required_events`.

Python applies required-event state effects only after a beat validates.

The proven beat validator is effectively frozen unless new evidence implicates it:

- Mistral 24B
- temperature 0
- repeat_penalty 1.15
- seed 42
- 400/400 benchmark

## Director architecture

### Request 1
Creative/directorial generation.

Conceptually: imagination.

It expands CURRENT BEAT into a timed RAW SCENE.

It owns beat completion.

It must:

- execute CURRENT BEAT;
- not enter NEXT BEAT;
- emit timestamped micro-beats;
- include one trailing `End continuity state:`.

### Request 2
Strict H3 formatter/translator.

Conceptually: stenographer.

It must preserve:

- Request 1 actions;
- action order;
- timestamps;
- explicitly supplied camera movement;
- dialogue.

It must not invent story events or become a creative rewrite stage.

## Continuity philosophy

Canonical continuity may know more internally than the H3 prompt needs.

Principle:

> Know more internally; expose only current final-frame facts.

Persistent Subject identity belongs to Python.

Continuity LLMs must not create persistent identities.

Generic/transient actors must not collapse into durable Subjects.

Implementation must remain generic and never special-case literal characters, creatures, weapons, rooms, doors, genres, or regression-fixture vocabulary.

## H3 gold-standard acceptance suite

### Locked benchmark artifact

The first complete 8-beat gold benchmark is now locked and version-controlled at:

`tests/acceptance/gold/amy_zombie_house.json`

That file is the authoritative benchmark artifact for the Amy story. Do not duplicate the full gold prompts in this notes file.

The benchmark is consumed by `tests/acceptance/run_acceptance.py` and reviewed fuzzily by GPT-5.6 Sol. Generated prompts are not required to string-match the gold prompt; they must preserve the gold behavior, timing discipline, continuity, scene intent, exclusions, sound/music progression, and expected end state.

The runner executes `minimax.py` in an isolated temporary copy of the repository, injects the locked story/subject inputs, forces a fresh story-arc/beat generation, runs all eight prompt-only segments against the user's local LM Studio model, and writes `acceptance_run.json` plus diagnostic artifacts under `tests/acceptance/results/`. It intentionally performs no local semantic grading.


The project needs a concrete end goal, not endless "looks better" debugging.

The acceptance suite will use human-authored gold-standard H3 prompts.

The local machine runs the real local LLMs. GitHub stores the benchmark definitions, runner, and project logic.

ChatGPT / GPT-5.6 Sol performs the fuzzy comparison between generated output and the gold standard. A local 24B model is not expected to be the final judge of semantic/artistic closeness.

### Story structure for gold tests

Use 8 beats per benchmark story.

Each beat should include:

- Story ID
- Beat number
- Mode: initial / append / refresh
- Length
- Gold prompt
- Must happen
- Must not happen
- Expected end state

Gold prompts are behavioral targets, not string-equality targets.

Generated output should be judged on whether it preserves the same scene intent, required events, continuity, and final state.

### Current benchmark story

Story ID: `amy_zombie_house`

Story text:

A realistic action film about a woman, Amy, protecting her two kids (Will and Amber) from a zombie apocalypse.
Amy is at home on a normal day, wearing a tight, black tank top and denim jeans, cooking breakfast for her young kids.
Suddenly, a zombie breaks the kitchen door window and Amy sees the danger. She rushes her kids to the basement, gets them inside, and then locks the door.
She retrieves her hidden arsenal consisting of a pistol and a katana. She equips the weapons.

The majority of the film is Amy killing (dismembering, decapitating, etc.) zombies as they try and attack her.
Amy kills the last of the zombies, her house now soaked in blood. She lets her kids out of the basement.

The AR-15 is not part of this story and must not be reintroduced.

## Timestamp/action rule

MiniMax H3 responds best when each timestamp describes one specific action.

Canonical timestamp syntax:

`At mm:ss.nnn,`

Do not append the word `seconds` after the timestamp.

Rules:

- do not impose an arbitrary maximum number of timestamps;
- use one timestamp per discrete action;
- if multiple distinct actions occur in sequence, give each action its own timestamp;
- do not bundle unrelated actions into one timestamp merely to reduce timestamp count;
- dialogue is its own timed action when spoken;
- camera movement may share a timestamp only when it is inseparable from the single action being described; otherwise give the camera change its own timestamp.

This is a gold-standard and generation target. Beat 3 is expected to provide a concrete example of the preferred structure.

## Gold-prompt formatting rules

### Names vs pronouns

Use names instead of pronouns whenever practical, especially instead of ambiguous `they`.

This is a clarity preference, not a blanket ban on pronouns. A pronoun is fine within a sentence when the subject has already been explicitly established and the referent is unambiguous. Prefer repeating the name when multiple subjects are present or a pronoun could attach to the wrong person.

### Visual subject disambiguation

H3 can visually confuse similar human subjects even when subject IDs and names are correct.

When a segment contains visually confusable named subjects, restate the minimum useful visual discriminator in the opening `detailed_description` setup. Prefer concrete appearance/clothing cues already established by the story or reference image rather than inventing new traits.

Current Amy benchmark example:

`Amy, still wearing her black tank top and denim jeans, ...`

This is intentional identity reinforcement, not redundant prose. Do not strip it merely because the reference image or previous video already defines Amy.

For H3 dialogue speaker IDs:

- use `(S1)`, `(S2)`, etc. only when the subject is speaking;
- do not use `(S1)` style IDs for ordinary non-dialogue actions;
- do not use `<Subject 1>` style references inside ordinary action prose when the character name is sufficient.

Example:

Correct:
`Amy takes Will's hand and leads Will toward the basement door.`

Dialogue:
`Amy (S1) says <d>Come on!</d>`

### Sound and music

Gold prompts should intentionally test both ambient sound and music-state transitions.

Keep them simple.

For every append segment, `non_diegetic_music` must explicitly begin from the prior segment's musical state using `continues from <Video 1>` before describing any change in cue, intensity, or style. The new segment may then transition the music as needed.

Example:

`non_diegetic_music: continues from <Video 1>. The tense suspense cue builds into a restrained action pulse.`

Examples of useful categories:

- domestic room tone;
- object sounds;
- glass breaking;
- footsteps;
- combat sounds;
- fading or continuing sounds;
- warm domestic underscore;
- suspense transition;
- action music;
- post-combat quiet.

Music continuity matters. A later beat should transition appropriately from the prior beat's musical state rather than treating each segment as unrelated.

## Expected end-state fields

Expected end state should be concrete enough to judge continuity without overconstraining harmless visual variation.

Include, when relevant:

- environment / current location;
- persistent environmental changes;
- important object states;
- Amy position;
- Amy final pose/action;
- Amy physical condition;
- Amy held props/weapons;
- Will position/action/condition;
- Amber position/action/condition;
- threat state;
- active/neutralized zombies when relevant;
- important spatial relationships;
- ongoing action;
- ongoing audio;
- musical state.

Do not require an exact frozen pose unless the pose is story-critical.

## Current gold beats

### Beat 1
Mode: initial
Length: 8 seconds

Purpose: calm domestic control case.

Must establish:

- Amy cooking and serving eggs;
- Will and Amber sitting at the table;
- complete normalcy;
- both children receive plates;
- Amy turns off the stove;
- no zombies, danger, weapons, or ominous cues.

End-state essentials:

- intact ordinary kitchen;
- stove off;
- frying pan and spatula set down;
- Amy hands free;
- Will and Amber seated with one egg plate each;
- no threat;
- no significant ongoing action;
- quiet kitchen ambience;
- calm domestic musical state.

### Beat 2
Mode: append
Length: 8 seconds

Purpose: first threat and domestic-to-suspense transition.

Must establish:

- Zombie1 breaks the kitchen door window;
- glass shatters and debris falls;
- Amber screams;
- Amy gathers Will and Amber;
- Amy, Will, and Amber run down the corridor;
- Amy opens the heavy steel door.

Must not include:

- combat;
- Zombie1 fully entering the house;
- Zombie1 reaching the corridor or steel door;
- weapon retrieval.

End-state essentials:

- kitchen door window remains shattered;
- steel door open;
- Amy, Will, and Amber grouped at the steel door;
- Zombie1 remains behind at the kitchen entry area and is not in the final frame;
- escape remains in progress;
- no combat audio;
- suspense music has replaced the warm domestic baseline.

## Append reference-video context

The append workflow should pass only the final 22 frames of the previous video into the H3 reference-video node.

Current implementation:

- compute the previous segment's exact H3-aligned frame count using the same `17n+5` length rule as the workflow;
- skip to the final 22 frames;
- set `frame_load_cap = 22`.

The shared calculation is used by both append and refresh. For an 8-second segment it yields 192 total frames and `skip_first_frames = 170`; for a 6-second segment it yields 158 total frames and `skip_first_frames = 136`.

Reason: the H3 node internally only needs the relevant tail and should not receive the full prior clip.

## Additional H3 production heuristics

### Avoid ending append segments on dialogue when practical

If the preceding video ends with dialogue, H3 may carry that vocal momentum into the next append and make it difficult to begin silently.

Prefer ending a segment on a visual/action beat rather than spoken dialogue when the story allows it.

### Stage difficult body-disconnection effects

H3 may resist or incompletely render decapitation/dismemberment when all consequences are requested at once.

For difficult body-disconnection actions, stage the event across separate timestamps when useful:

- strike;
- detachment;
- separated part falling;
- reaction / close-up;
- remaining body collapse.

The Beat 5 gold prompt is a concrete example.

### Re-establish visual details not proven by append context

If the incoming reference video/start context does not visibly show a persistent detail, H3 may invent a replacement.

Re-state important details when the current context does not clearly prove them, especially:

- full outfit;
- lower-body clothing;
- belt/holster details;
- carried or attached weapons;
- injuries;
- blood/substance coverage;
- other visually persistent body details.

Example: if only Amy's upper body is visible in the prior context, explicitly restate `black tank top and denim jeans` rather than assuming the jeans remain preserved.

### Refresh using context latents

The tested quality-refresh approach uses the Extend Backport node with decoded `context_latents` from the prior video.

Tested settings:

- pass the final 22 decoded frames;
- set `context_frames = 7`.

This tested as effectively as a quality refresh and is the desired refresh baseline.

**Repository integration status:** implemented on `gpt-test-branch`. The checked-in refresh graph uses `MiniMaxH3VideoExtendPatched`, VAE-encoded context latents from the final 22 frames of the prior video, `context_frames = 7`, the prior audio, and the user's tested first-frame selector path. The old hybrid keyframe graph is preserved separately as `Minimax_auto_repair_API.json` for `--repair`.

### Fade-to-black end states

For a segment ending in a fade to black, distinguish:

- semantic scene end state immediately before the fade;
- literal final rendered frame, which may be black.

Acceptance review should judge story/continuity state from the pre-fade scene, not interpret the black final frame as loss of subjects/environment.

## Deferred action item: environment / room continuity

Problem:

When a room or area is exited and later re-entered, H3 may regenerate the room with a different visual identity.

Two candidate approaches:

### Option A: persistent room description/state
Store a durable room identity and re-inject it when the location is revisited.

Separate:

- persistent room identity: layout, furniture, doors/windows, colors, major objects;
- mutable room state: broken glass, blood, bodies, overturned furniture, fire, damage, etc.

This is the preferred KISS starting point.

### Option B: room screenshot/reference image
Capture a representative frame of the room and pass it back as a reference image when the room is re-entered.

This should provide better visual fidelity but is more complicated.

Do not implement yet. First complete the 8-beat gold-standard pass, then test whether descriptive room continuity is sufficient before adding screenshot/reference-image restoration.

## Current branch

Active development branch:

`gpt-test-branch`

Use the current GitHub branch head as authoritative. Do not rely on stale SHA values from handoff documents.

## Local llama.cpp bridge

A GitHub-backed mailbox bridge is implemented in tools/chatgpt_llama_bridge.py.

Reason: the ChatGPT runtime can write/read GitHub but does not expose a general arbitrary HTTP POST client. A Cloudflare tunnel alone therefore does not provide reliable direct access to /v1/chat/completions.

The bridge uses the dedicated gpt-runtime branch. ChatGPT commits JSON jobs under bridge/jobs; the user's local worker polls that branch, sends only allowlisted requests to the locally configured llama.cpp endpoint, and commits responses/requested artifacts under bridge/results. No inbound port or Cloudflare tunnel is required.

### First Amy gold acceptance baseline

The first complete 8-segment acceptance capture completed successfully at the harness level. The earliest semantic divergence is the ARC stage: the generated story arc omitted the ordinary breakfast setup from required events and assigned the zombie-window break-in to Beat 1. The generated Beat 1 therefore depicts the threat immediately, while gold Beat 1 is the calm breakfast scene. Downstream Director/H3 mismatches should not be repaired before this upstream arc/beat planning loss is corrected.
