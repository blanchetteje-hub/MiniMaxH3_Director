# MiniMax H3 — Development Handoff

## 2026-10-06 — object-state-work: canonical spatial location_state

Implemented the location-state split on `object-state-work`.

- Added `SMART_EXTRACTOR_LLM_SETTINGS`: temperature 0, seed 42, context budget 8192,
  medium reasoning, 1024 reasoning tokens.
- The story-grounded compact static-setting extraction remains the first stage. Two SMART passes follow:
  1. plain-text spatial refinement with cardinal directions, anchor-first layout,
     dimensions, accessibility, and non-overlap;
  2. structured spatial extraction in `Location + JSON + text description` format.
- Python parses the second pass: JSON becomes `generation_state["location_state"]`;
  the text description becomes `metadata.setting_description` and is the only location
  description sent to the 3-second ComfyUI reference render.
- `generated_prompts.txt -> config.location_state` preserves the same JSON for split
  LLM/render workflows and resume.
- The location-reference H3 prompt now matches the tested compact form:
  high-angle, empty location, 3-second full 360 orbit, no contradictory static/low-angle
  wording.
- Focused regressions cover the profile, both prompt contracts, parser split,
  checkpoint field, and H3 location prompt.

Next local action: run the tavern case and compare the emitted `location_state` JSON,
its generated text description, and the resulting 3-second location video. Do not change
Beat/RAW spatial rules until this upstream representation is verified.

## 2026-10-06 — extractor naming + single-purpose rule

Renamed the formerly internal `story_setting_seed_extract` stage to the clearer
`static_setting_extract` terminology (`extract_static_setting` and matching
builder/parser helpers). Its job is to decide which static location facts belong to the
location; "seed" was only a refactor label and is no longer used.

PROJECT_NOTES now records the local-LLM design finding: prefer small single-purpose
extractors. The current location chain is the reference example:
`static_setting_extract -> story_setting_spatial_refine -> story_setting_extract`.
Keep the final JSON+render-text extractor combined for now, but consider splitting it
into separate state and serialization calls if future local runs show interference.

## 2026-10-06 — visible wait/progress logging

Added user-visible progress logging so long blocking work no longer looks hung.

- Every `ask_llm()` request logs its `history_metadata.purpose`, attempt number,
  approximate input-token count, and output-token cap immediately before the HTTP call.
- Completed LLM calls log elapsed wall time and the host `finish_reason`.
- `wait_for_completion()` logs when a ComfyUI render wait begins, emits a heartbeat
  every ~15 seconds while the prompt is still pending, and logs total render wait time
  when it completes.
- If the canonical spatial-setting extractor returns malformed JSON,
  `parse_story_setting_description()` prints the complete raw extractor response before
  raising the existing recoverable error. This is diagnostic only; JSON repair behavior
  was intentionally not changed yet.

Commit: `ceac63a2f9ee419e0b488dd5af01df4d397443e1`.

Immediate local action: rerun the same command. If `story_setting_extract` still fails,
capture the newly printed raw response; that will show whether GPT-OSS is emitting
single-quoted/Python-style objects, commentary around JSON, truncation, or another format
error before deciding whether parser/prompt repair is warranted.

## 2026-10-06 — extractor-local retries + mixed spatial-output preservation

The first local run of the new location-state chain exposed two orchestration/parser problems.

- Extractor parse/content failures were escaping to the run-level recoverable restart, causing
  unrelated successful stages (character canon, per-Subject wardrobe, story location, and earlier
  setting passes) to rerun.
- `story_setting_extract` intentionally returns a mixed payload:
  `Location:` line + JSON `location_state` + plain-text render description. Although it passed
  `parse_json_response=False`, `ask_llm()` still opportunistically extracted the first JSON
  object and returned a Python dict, silently discarding the prefix and trailing prose. The later
  parser then stringified that dict into single-quoted Python syntax and falsely reported invalid
  JSON.

Implemented on `object-state-work`:

- `parse_json_response=False` now means exactly raw model text. Mixed-output callers keep the
  complete response; stage-specific parsers remain responsible for extracting JSON when needed.
- The defined-Subject wardrobe extractor, static-setting extractor, spatial-refinement extractor,
  and final mixed spatial extractor now each have their own bounded content/parse retry loop.
  A failure retries only that extractor against its already-computed input.
- Wardrobe output now rejects punctuation-only garbage such as `:[{` before committing canon.
- The final spatial extractor receives both the original compact static-setting facts and the
  spatial-refinement text. This preserves semantic setting facts while still using the refinement
  as its spatial input; the full expanded story is not re-fed unless production evidence shows it
  is needed.
- On retries, the final extractor is reminded to return all three required parts and valid
  double-quoted JSON.

Commit: `23cb452d509ee03cdcf594d2a9becdd9b95a9172`.

Next local action: rerun the tavern case. A malformed final spatial response should produce another
`story_setting_extract` call with attempt 2/3 without rerunning wardrobe/location/upstream setting
extractors. Inspect the preserved full mixed response before deciding whether more context is needed.

## 2026-10-06 — beat-based Subject resolution before Director prompts

Updated the story-start Subject resolver so it runs before Director prompts and supplies
candidate Subjects to the RAW scene request.

- `director_raw_scene_subject_resolution` receives all finalized beats and the existing Subject
  definitions. Its prompt requests Subjects defined in beats with no entry point, excludes names
  already in the definitions, and requires a one-sentence `initial_state` limited to the minimal
  physical location/pose supported by the beats.
- The extractor retains a bounded three-attempt parse/content retry loop and now logs the raw LLM
  result for each attempt.
- Inferred Subjects are seeded into the normal Subject registry with `origin_segment=0`; their
  starting positions are also stored in the Subject-state ledger. Existing Subjects are updated
  rather than duplicated, and inferred Subjects are added to `subject_definitions` before Director
  and H3 work.
- Segment 1's Director request receives a `SUBJECTS INFERRED TO BE PRESENT AT STORY START` block.
  Their states are authoritative, while the Director uses the current beat to decide whether each
  should be visible. Listing a Subject does not require an entrance or an action.
- The post-RAW resolver has the distinct purpose `director_raw_scene_visible_subject_resolution`;
  it handles Subjects that appear in accepted RAW. This avoids conflating it with beat-based
  resolution.
- Dynamic Subjects with humanoid physical form receive canonical, setting-appropriate
  clothing from the visible-Subject resolver. Non-humanoid forms may use N/A wardrobe
  fields when clothing does not apply, unless RAW explicitly gives clothing.

The pre-Director resolver now uses the `director_raw_scene_subject_resolution` purpose for LLM
settings/logging. The visible-Subject resolver uses
`director_raw_scene_visible_subject_resolution`.

## 2026-10-06 — static-setting extractor LLM profile

`static_setting_extract` is routed to `SLIGHTLY_CREATIVE_LLM_SETTINGS` by its
`history_metadata.purpose` in `ask_llm()`. Current settings are temperature 0.1, low reasoning
effort, and a 384-token thinking budget. No seed is configured in this profile, so `ask_llm()`
generates a random seed. The extractor call separately caps output at 512 tokens and uses
`STORY_PIPELINE_CONTEXT_TOKEN_BUDGET` for its context budget.

This is the first setting-specific prompt: it chooses which details from the expanded story count
as static location facts. `story_setting_spatial_refine` and `story_setting_extract` follow it.

## 2026-10-06 — repair story-start Subject handoff after local Codex pass

Reviewed the local Codex implementation against the tavern run logs. The beat-wide Subject
inference itself worked, but Segment 1 was allowed to keep inferred Subjects off-camera; H3
reference binding then filtered the goblin out, and Segment 2's physical validator falsely treated
the durable goblin as a new participant because it saw only PREVIOUS SHOT END.

Changes on `object-state-work`:
- Kept the user-approved character-reference timing at 0.5s with midpoint sample at 0.25s.
- Kept the user-approved medium-shot location-reference wording.
- Reverted only `DETERMINISTIC_ANALYSIS_LLM_SETTINGS.thinking_budget_tokens` from 256 to 128.
- Moved `SLIGHTLY_CREATIVE_LLM_SETTINGS` from `static_setting_extract` to
  `story_setting_spatial_refine`. Static fact selection is deterministic again; slight variation
  is applied only while choosing unspecified spatial layout/dimensions.
- Strengthened pre-Director story-start Subject inference:
  - read all beats for actors whose first state implies prior presence with no entry;
  - preserve explicit proper names;
  - use stable Role1 names for unnamed roles/species (for example Goblin1);
  - deterministically normalize lowercase role outputs such as `goblin` to `Goblin1`;
  - reject/retry initial states that leak held-prop actions such as clutching/holding/carrying.
- Segment 1 now must visually establish every inferred story-start Subject at least once in the
  inferred state. They may stay stationary/background and receive no invented action or entrance.
  This lets the existing RAW -> reference-binding path retain them naturally in H3.
- The RAW physical validator now receives compact durable KNOWN SUBJECT STATE from the existing
  registry. A known Subject may first come into frame through ordinary camera framing/reveal and is
  not treated as a new arrival merely because PREVIOUS SHOT END omitted it.
- The post-RAW visible-Subject resolver can return missing appearance/wardrobe metadata for an
  already-registered visible Subject. Python fills only missing/generic fields and never overwrites
  established canonical metadata.
- Added focused regressions for stable Goblin1 normalization, held-prop rejection, mandatory
  Segment-1 visual establishment, durable known-Subject validator context, existing-Subject
  metadata fill, the medium-shot location reference, and the 128-token deterministic budget.

Commits:
- `689541a24af715892b46e1e6e532483f91510e5e` — implementation
- `79211309cbf111c2491f86ca9176ac1a425b665b` — focused regressions
- `4481ab9324e11b64a6eab0c96ca108ea91e73afa` — update older physical-validator prompt regression

The GitHub connector cannot execute the local Python suite; pushed source and call sites were
re-read after the commits, but the next local acceptance should run the focused tests before the
full render.

Next local acceptance:
- Story-start resolver should return `Goblin1` with a state such as `leaning over the counter`,
  not the chipped mug.
- Segment 1 RAW/H3 should visibly contain Goblin1 without giving him a new action or entrance.
- Segment 1 reference bindings should therefore include Subject 2.
- Segment 2 physical validation must not reject Goblin1 as a new participant.
- When Goblin1 is first visually established, missing canonical appearance/appropriate humanoid
  wardrobe may be filled once and then remain stable.

## 2026-10-06 — restore proven story-start prompt + dedicated wardrobe calls for dynamic Subjects

The tavern acceptance run showed two regressions in the local Codex pass:

- `director_raw_scene_subject_resolution` was given all beats correctly, but its rewritten
  system prompt returned Goblin1, Elf1, and Dragon1 as story-start Subjects even though the
  elf explicitly "steps in" and the dragon explicitly "enters" in later beats.
- `story_subject_wardrobe_extract` ran only for Amy because it was invoked only for
  pre-defined `subjects.txt` Subjects. Inferred/dynamically registered Subjects were created
  later and therefore never received the dedicated per-Subject wardrobe call.

Fixes on `object-state-work`:

- Restored the user-proven story-start system prompt verbatim in substance:
  "Return subjects defined in beats that have no entry point (IE entered, walked in, etc.)"
  with the original Jim/William examples and minimal `initial_state` rule.
- Added a reusable one-Subject `extract_subject_canonical_wardrobe()` path using the same
  `story_subject_wardrobe_extract` prompt/profile/retry behavior.
- Story-start Subjects newly registered before Segment 1 now each receive one independent
  wardrobe extractor call after their dynamic Subject definitions are created.
- Subjects first registered from a later RAW segment now each receive one independent
  wardrobe extractor call immediately after registration and before H3 character-reference
  creation.
- Naturally unclothed Subjects (for example dragons when appropriate) keep all wardrobe slots
  at N/A. Humanoid Subjects use the dedicated appropriate-attire extractor rather than relying
  on the combined visible-Subject resolver as their primary wardrobe source.
- Added focused regressions for the restored prompt, one-call-per-dynamic-Subject wardrobe
  extraction, and N/A wardrobe for a naturally unclothed dragon.

Commits:
- `bee33a7c9d4ce977d31895081cdd2271fed344a5` — implementation
- `2c6cffba9911c34cdcd0f0296e2b9743b4cf7216` — focused regressions

Next local acceptance:
- `director_raw_scene_subject_resolution` should return only Goblin1 for the current tavern
  beats; Elf1 and Dragon1 must remain later arrivals.
- Startup should log one `story_subject_wardrobe_extract` call for Amy and one separate call
  for Goblin1.
- Segment 3 should run a dedicated wardrobe call for Elf1 when she is first registered.
- Segment 4 should run a dedicated wardrobe call for Dragon1 and should return N/A unless the
  expanded story explicitly clothes the dragon.

## 2026-10-06 — Gate C phase 2 corrections, before Gate D

Reworked pre-Request-1 WorldState preparation against the locked benchmark at
`tests/acceptance/gold/amy_medieval_tavern_six.json`. Gate D is not started; accepted Director
actions still do not commit to `generation_state["world_state"]`.

- Added a separate one-call-per-authored-Subject story-start classifier. It seeds `present` only
  with explicit source evidence that the Subject is already in the opening scene, `absent` only
  with explicit later-entry evidence, and otherwise leaves presence `unknown`. The proven
  initial-location Subject extractor was not changed.
- Replaced whole-story persistent-prop prediction with a current-Segment-only extractor. Its
  inputs are the current beat/source, registered Subjects, already registered props, and
  registered location/support vocabulary. It returns only new props needed for persistent state
  actions in that Segment; registration makes their persistence automatic. It does not predict
  future beats or holders and does not harvest nouns.
- Current-beat Subject identity/wardrobe extraction runs before Director Request 1. New arrivals
  receive Python IDs and canonical wardrobes, but remain `unknown` until an explicit `enter` action.
  The dragon-shaped creature remains `physical_form=unknown` because the benchmark does not
  establish humanoid anatomy.
- The real benchmark regression now covers Amy and Goblin1 already present; Goblin1 holding the
  chipped mug; the later Elf1 entrance and chalice service; and the later dragon-shaped creature
  with Amy taking the crystal cup from the shelf, pouring, and handing it over.
- Request 1's Segment vocabulary uses those stable IDs. In the benchmark replay, Segment 1 has
  Amy/Goblin1, mug/barrel, counter/hearth; Segment 3 adds Elf1, crystal chalice, and back table;
  Segment 4 adds Dragon1, crystal cup, shelf, and high bar stool. Presence for newly registered
  Elf1/Dragon1 stays `unknown` until `enter` is accepted.
- Exact modeled initial placements: chipped mug is held by Goblin1; barrel is located in Tavern;
  crystal cup is located in Tavern on the shelf; crystal chalice is located in Tavern with no
  exact starting holder/support established before its Segment-3 service. The source says the
  chalice is set on wood after service. “Beside the hearth” is retained as source meaning but is
  not represented as a support or adjacency relation.
- Updated 14 stale `test_director_retry.py` expectations against current prompt, timestamp,
  identity-labeling, and subject-resolution contracts. No code regression was found in the
  original 14 failures. The two-module suite is now green: `151 passed, 4 subtests passed`.

Validation:
- `pytest -q tests/test_director_retry.py tests/test_world_state_foundation.py` — 151 passed,
  4 subtests passed.
- No full tavern generation was run. Stop here for Gate C review before Gate D.

## 2026-10-08 — WorldState rollback and bridge acceptance

- **Current code branch:** `world-state-rebuild`, created from Gate C checkpoint `33a56bb5a5b8a79c72b8acbeff86268b3709d9eb` rather than continuing the 78 later commits on `object-state-work`.
- **Reason for branch:** subsequent Gate D and follow-up changes accumulated excessive WorldState/legacy reconciliation and architectural complexity. Keep proven authoring, location, Director validation/repair, and Gate C action dry-run; do not restore the downstream transaction machinery by default.
- **Current acceptance path:** ChatGPT writes an allowlisted `run_acceptance` job under `bridge/jobs/` on `gpt-runtime`; local `tools/chatgpt_llama_bridge.py` executes `world-state-rebuild` using the 20B runtime and publishes logs/artifacts under `bridge/results/` on `gpt-runtime`.
- **Benchmark:** `tests/acceptance/gold/amy_medieval_tavern_six.json`; six eight-second prompt-only segments. Evaluate actual H3 prompts, RAW staging, identities, geometry, prop reuse and WorldState dry-run diagnostics, not just unit-test status.
- **KISS is mandatory:** If a fix requires adding another validator, synchronizer, shadow state, or repair subsystem, stop to redesign or simplify. Solve the earliest observed acceptance failure with the minimum change. Gate D remains excluded unless fresh evidence justifies a lean redesign.
- **Bridge startup blocker (2026-10-08):** Job `accept-world-state-rebuild-tavern-20261008-01` was submitted on `gpt-runtime` but the already-running worker rejected it before running the local LLM: `Acceptance jobs must run on 'gpt-arc-refresh'; got 'world-state-rebuild'.` This is a stale **worker process**, not a pipeline failure. The new branch includes the updated acceptance allowlist, explicit tavern benchmark selection, and result-artifact routing (commit `813aa4ad02facf2edb17083c67b25a420929063f`). Restart local bridge from a pulled `world-state-rebuild` checkout, then submit a fresh job ID. Do not repeat the failed ID or interpret it as acceptance evidence.
- **Acceptance #02 (processed):** `accept-world-state-rebuild-tavern-20261008-02` executed the requested branch and benchmark at commit `72802fdb`, but failed before contacting the LLM or emitting any segments. Windows worker has no `H:\\` drive, while `minimax.py` defaults media output to `H:\\images\\output\\video` and calls `clear_state_media_output()` unconditionally. This is a test-runner environment issue, **not** evidence against Gate C or WorldState.
- **Minimal fix:** acceptance-runner subprocess now sets `MINIMAX_VIDEO_OUTPUT` to its own isolated temporary workspace `output/video`; production ComfyUI defaults and WorldState logic remain untouched. Added a focused regression in `tests/test_acceptance_runner.py` (commits `65337c3e` and `2b99f8aa`).
- **Next:** run the focused acceptance-runner regression through the bridge, then rerun the six-segment tavern acceptance as #03 and inspect the earliest actual prompt/state defect. Historical branch and bridge-retirement notes below are superseded by this checkpoint.

## 2026-10-08 — acceptance #03: opening Subject classification

- Bridge preflight accept-world-state-rebuild-00-preflight-20261008-03: 10/10 passed.
- Tavern acceptance #03 at 5b897f2 reached all six accepted Beats but emitted no H3 prompts. It stopped before Director Request 1: authored Amy story-start classification exhausted 3 retries with `Explicit story-start classification requires exact source evidence`.
- The beat-wide extractor incorrectly classified Elf as present despite the explicit Beat-3 entrance.
- KISS-only changes within the existing minimax.py extractors: clarify that performing the initial Beat 1 action establishes presence; request short verbatim evidence; normalize whitespace before exact quote comparison; explicitly exclude later entrants from initial-state inference. No new LLM stage, state subsystem, or validator. Code f239381e; regression 0f2078e4.
- Acceptance #04 attempted focused tests and prompt generation, but both stopped immediately on a prompt string literal typo introduced in `f239381e`. Corrected only the newline syntax in commit `14fe4527` (no semantic changes to the fix). The #04 failures are **not** meaningful LLM/Director evidence.
- Full tavern acceptance #05 is queued on `gpt-runtime` at corrected branch head. The separate #05 focused-test job has not been successfully queued. Examine the #05 result before further code changes. The beat-ledger's hostile goblin and incorrect chalice ownership are later potential issues, not current blockers.

## 2026-10-08 — immutable LLM settings profiles

- Removed per-purpose output-token caps and context-budget overrides. `ask_llm()` now reads both values from the selected immutable profile; remaining output capacity is reduced only when needed to fit the request inside that profile's context budget.
- `director_raw_scene_subject_resolution` now receives the full `SMART_EXTRACTOR_LLM_SETTINGS` output allowance (4096 tokens), instead of the previous 1024 purpose cap.
- Long-input extraction purposes select explicit immutable long-context profiles. All runtime LLM profile mappings are read-only.
- Removed the mutable story-temperature CLI/GUI override. Story expansion now uses its fixed profile value of 0.8.
- The test-only llama client no longer accepts `H3_LLM_TEMPERATURE`; endpoint, model, and request timeout remain configurable.
- Verification: `python -m py_compile minimax.py desktop_app.py tests/LLM/llama_client.py`, frontend production build, and `git diff --check` passed. Focused profile/desktop/story tests passed (50 tests, 22 subtests). A broader mixed run reported stale reasoning-profile and prompt-text assertions; those failures were outside this settings change.

## 2026-10-08 — per-beat Subject presence classification

- `director_raw_scene_subject_resolution` runs once for each nonempty beat, in chronological order. The system prompt distinguishes entering (`present=false`) from acting while already in the scene (`present=true`) and says to omit unreferenced candidates.
- Each user prompt contains only the `character_canon` Subject names as a comma-delimited `POSSIBLE SUBJECTS` list and the current `STORY BEAT`. Python canonicalizes returned names against that allowlist and ignores any name outside it.
- Python keeps the first classification for each normalized Subject identity and ignores later conflicting results. A Subject omitted from a beat is not classified by that beat. Existing authored Subjects are filtered deterministically after the beat passes.
- The extractor continues returning the existing `initial_location_subjects` seed structure, so downstream Subject registration and prompts keep their contract.
- Verification: `python -m py_compile minimax.py`, `python -m pytest -q tests/test_location_state_reference.py` (27 passed), and `git diff --check` passed. A combined run with `tests/test_character_canon.py` had 39 passes and two unrelated stale prompt-text assertions.

## 2026-10-08 — acceptance -12 Subject identity and wardrobe coverage

- Registered every `character_canon` identity in WorldState before canonical wardrobe seeding. This reuses the existing identity-only registration API and leaves presence/location unknown unless a separate authority establishes them.
- Made the existing per-beat `director_raw_scene_subject_resolution` parser reject keys outside the supplied canonical Subject vocabulary. The existing retry path handles invalid keys; the earliest valid classification remains authoritative. Beat text, including descriptive modifiers, is passed through unchanged.
- Expanded `canonicalize_defined_subject_wardrobes()` to run the existing `story_subject_wardrobe_extract` once for every `character_canon` Subject, including Subjects absent from `subjects.txt`. The same prompt/schema/profile are used. The narrow parser retry also rejects clothing that exactly equals the Subject's name; no broader wardrobe validation was added.
- No runtime prompt or LLM-facing schema changed. The fixed humanoid clothing rule remains in the existing wardrobe prompt.
- Verification: WorldState foundation 41 passed (2 pre-existing stale story-start prompt/schema assertions deselected); location reference 28 passed; character canon 14 passed (2 pre-existing stale prompt assertions deselected). New regressions cover identity without presence, wardrobe for later-appearing canon identities, exact-name clothing retry, unknown resolver keys, canonical numbered-role aliases, and unmodified descriptive Beat text.

Fix observed failures in order. Explain the failure and proposed fix before making substantive architecture/prompt changes.

## 2026-10-08 — Subject resolver array response

- Updated the `director_raw_scene_subject_resolution` system prompt to the approved wording: classify each referenced possible Subject as entering (`present=false`) or already present and acting (`present=true`), omit unreferenced Subjects, return Subject names without adjectives, and return a JSON array.
- Updated the existing structured response schema and parser to accept only an array of `{subject, present, reason}` records. Canonical-name enforcement, strict rejection of unregistered names, and earliest-valid-classification behavior remain in place.
- Verification: `python -m pytest -q tests/test_location_state_reference.py` (28 passed), `python -m py_compile minimax.py tests/test_location_state_reference.py`, and `git diff --check` passed.

## 2026-10-08 — canonical descriptive-name aliases in Subject resolver

- Added deterministic Python alias resolution for `director_raw_scene_subject_resolution`: a returned name matching a suffix of a supplied descriptive canonical name resolves to that Subject only when exactly one canonical Subject matches (for example, `Elf` to `Beautiful Female Elf`).
- Exact canonical names take precedence over aliases. Ambiguous aliases and names outside the supplied vocabulary fail closed. Earliest-classification behavior and the current Beat text are unchanged.
- No LLM prompt, response schema, or call path changed.
- Verification: `python -m pytest -q tests/test_location_state_reference.py` (32 passed), `python -m py_compile minimax.py tests/test_location_state_reference.py`, and `git diff --check` passed.

## 2026-10-08 — avoid re-extracting canon-covered dynamic wardrobes

- The initial-location/dynamic Subject compatibility path now receives `character_canon`. For a Subject with canonical clothing, it seeds the legacy continuity wardrobe from that existing record and skips a second `story_subject_wardrobe_extract` call and WorldState wardrobe sink update.
- Non-canon dynamic Subjects still use the existing extractor and compatibility behavior. Dynamic registration and `seed_canonical_wardrobes()` conflict checks are unchanged.
- Verification: WorldState foundation 42 passed (2 documented stale story-start prompt assertions deselected); location-reference 32 passed; syntax and whitespace checks passed.

## 2026-10-09 — current-Segment prop vocabulary uses names

- Removed Python-assigned Subject, location, and prop IDs from the `world_state_current_segment_props` request vocabulary. Existing prop placements are rendered with registered holder, location, and support names as well.
- The extractor's prompt and response schema are unchanged. Python continues to validate exact registered names, resolve them through its name-to-ID maps, and assign stable IDs through the existing persistent-prop registry.
- Added a generic regression for a movable cleaning tool explicitly involved in a handoff: Python registers the initial holder by canonical name, the same deterministic prop ID survives into the following Segment, and the tool can then be placed on a registered support. The next extractor vocabulary includes names and placement but no IDs.
- Scope note: with the current unchanged extractor contract, a prop is registered when the current Beat/assigned source explicitly involves it in a supported persistent action such as placement or transfer. A cloth mentioned only as a wiping instrument is not inferred from future handling.
- Verification: the new focused regression passed. The full `tests/test_world_state_foundation.py` module reported 43 passed and 2 existing stale story-start contract assertions failed; syntax and `git diff --check` passed.

## 2026-10-09 — WorldState extractors use the smart profile

- Routed `world_state_current_segment_props` and `world_state_current_segment_subjects` through immutable `SMART_EXTRACTOR_LLM_SETTINGS`.
- Deleted `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` and its purpose set. The wardrobe, story-location, and static-setting extractors now use the existing `CREATIVE_GENERATION_LLM_SETTINGS` and its standard context budget; prompt text and call counts are unchanged.
- Updated the LLM prompt inventory and profile-routing regressions to match. Long-context deterministic routing remains unchanged.

## 2026-10-09 — centralized WorldState object and action schemas

- Added a canonical Python `WORLD_STATE_PROP_SCHEMA` in `world_state.py` and
  made WorldState prop validation enforce its field set. Shared contents,
  capability, kind, and mobility definitions now supply the current-Segment
  prop extractor schema instead of repeating those values in `minimax.py`.
- Replaced the separately maintained Director action field/schema blocks with
  one declarative `ACTION_CONTRACT`. Reducer shape validation and the dynamic
  Director action schema now derive operation fields and requirements from it;
  request-specific entity enums still use the registered IDs at this stage.
- Kept extractor `reason`/`evidence` in the extraction response and diagnostics.
  Registration no longer copies `reason` into persistent prop provenance.
- Runtime prompt wording and state-writer/commit behavior were not changed. The
  Director ID-to-name boundary and legacy-writer retirement remain later steps.
- Focused follow-up validation: `WorldStateSeedTests`, `WorldStateReducerTests`,
  the four Request-1 state-action regressions, and the Director response-schema
  test passed (40 passed, 2 subtests).
- The broader WorldState foundation + Director retry modules reported 150
  passed and 6 failures. All six are stale story-start prompt/response fixtures:
  two assert the retired `classification/evidence` contract, and four Director
  tests use a shared fixture returning that same retired shape. They do not
  exercise the shared prop/action schema consolidation.

## 2026-10-09 — Director WorldState action contract uses registered names

- Director Request 1 now receives registered Subject, location, prop, and support
  names in its WorldState vocabulary and action-reference enums. Nested prop
  placements also use registered holder/location/support names; Python IDs are
  omitted from the LLM-facing vocabulary.
- The same canonical `ACTION_CONTRACT` still defines action references. A
  request-local name-to-ID map is built from only the vocabulary supplied to
  that Request 1. Python resolves every action reference, including nullable
  support and nested-placement vocabulary references, before passing the
  unchanged ID-based actions to the existing reducer. Unknown or duplicate
  names fail closed; no global registry or alias resolution was added.
- Updated Director system, Request-1 vocabulary, and retry instructions to
  require exact registered names. Canonical WorldState, reducer behavior, and
  diagnostic logging remain unchanged.
- Added regressions for successful resolution, unknown/out-of-request names,
  duplicate-name ambiguity, and nested holder/location/support references.
- Verification: `python -m pytest -q tests/test_world_state_foundation.py::WorldStateSeedTests tests/test_world_state_foundation.py::WorldStateReducerTests tests/test_director_retry.py tests/test_llm_prompt_pipeline.py::DirectorPromptCallContractTests::test_director_response_schema_includes_state_actions` — 151 passed, 4 subtests passed. `py_compile` passed.

## 2026-10-09 — commit accepted Director WorldState actions

- Added a small commit function that reduces the ID-resolved action batch
  against the Segment's captured opening WorldState and assigns the candidate
  only after successful reduction. It verifies that Request 1's dry run passed
  and that canonical WorldState still matches the captured opening. A reducer
  rejection leaves the stored state unchanged.
- Prompt-only generation commits after the final H3 prompt is assembled and
  immediately before its completed-segment checkpoint. Rendered generation
  commits only after a successful render, before the completed-segment record
  and atomic checkpoint save. Each completed record therefore carries the same
  WorldState used as the next Segment's opening; resume restores it from the
  last completed record.
- When vision cadence skips observation, rendering now waits synchronously so
  the next Segment cannot open before the current state commit. The cadence-
  skipped background completion/prefetch path was removed. Vision-enabled
  prefetch still starts only after the previous Segment has committed.
- Legacy continuity and visual-observation state remain separate; neither is
  used to update canonical WorldState. Pre-Director authority seeding and
  identity/prop registration remain unchanged.
- Added regressions for successful multi-Segment handoff/place, rejected-batch
  rollback, prompt-only checkpoint recovery, and ensuring legacy/visual state
  does not overwrite the recorded WorldState. The prompt-generation path also
  verifies commit occurs before checkpoint recording and not after a failed
  render.
- Verification: focused WorldState, Director retry, checkpoint/resume, and
  prompt-generation tests — 157 passed, 4 subtests passed. `py_compile` and
  `git diff --check` passed. A broader foundation run still has two unrelated
  stale story-start prompt/response assertions.

## 2026-10-09 — persistent-prop extractor prompt clarified

- Updated the `world_state_current_segment_props` system prompt to explicitly
  require only new physical props needed for persistent actions, reuse existing
  prop identity, use registered names for placement and support, quote exact
  evidence, and return the specified JSON fields and capability values.
- The extractor call, LLM-facing schema, validation, and Python ID resolution
  are unchanged.
- Verification: syntax and whitespace checks passed; tests were not run for
  this prompt-only change.

## 2026-10-09 — wardrobe extractor prompt clarified

- Updated the `story_subject_wardrobe_extract` system prompt to preserve all
  explicit clothing details, fill only missing normal outfit pieces, and retain
  the fixed humanoid-clothing rule with the non-humanoid `N/A` allowance.
- The response schema, call routing, input construction, and parsing are
  unchanged.
- Verification: syntax and whitespace checks passed; tests were not run for
  this prompt-only change.

## 2026-10-09 — standardized LLM profiles and request budgets

- Replaced the overlapping text settings profiles and purpose sets with four
  immutable profiles: Creative (0.6, medium/256), Smart Creative (0.6,
  high/1024), Extractor (0, medium/256), and Smart Extractor (0, high/1024).
  Creative profiles retain creative sampling defaults and random seeds;
  extractor profiles retain deterministic sampling defaults and seed 42.
- Routed every text-call purpose through one `LLM_PURPOSE_PROFILES` mapping.
  Applied the requested classifications: character canon and wardrobe use
  Smart Creative; spatial refinement uses Smart Creative; story-location and
  static-setting extraction use Extractor; soundscape uses Creative; and
  source-unit state effects use Smart Extractor. The remaining source-planner
  calls are also explicitly mapped to Smart Extractor.
- Moved context and completion limits out of profile constants into independent
  per-purpose maps. The story expansion, story-to-beats, and registered
  story-start calls retain their 60,000-token context; prior task-specific
  output ceilings are retained. Unknown text purposes use Extractor with the
  standard 8192 context and 1024 output defaults.
- `visual_end_state` remains on its image-capable request path and
  `VISION_LLM_SETTINGS`; it cannot cleanly fit a text-only profile.
- Runtime prompts, schemas, LLM call count, and diagnostic logging are
  unchanged. `docs/LLM_PROMPTS.md` now reflects the actual purpose mapping,
  including the source-planner calls.
- Verification: focused routing/settings, source-planner, and call-integration
  tests passed (98 passed, 1 skipped). The wider WorldState/Director selection
  reported 283 passed, 8 subtests passed, and 2 existing stale story-start
  prompt/response assertions failed. A broader LLM prompt selection reported
  194 passed and 26 existing stale Director/story prompt assertions failed;
  this work did not change runtime prompt text. Syntax and whitespace checks
  passed.

## 2026-10-09 — raise 1024-token output caps to 2048

- Raised every text-purpose completion cap that was 1024 to 2048 tokens, and raised `LLM_DEFAULT_MAX_OUTPUT_TOKENS` from 1024 to 2048. This covers the listed purpose-specific requests and unknown-purpose requests using the default.
- Left profiles, thinking budgets, context budgets, and purpose caps already above or below 1024 unchanged. The context-fit calculation may still lower the effective request cap when necessary. The separate vision request cap was not changed.
- Updated the LLM call catalog and routing/settings regression to assert the new limits.

## 2026-10-09 — split Beat story and state validation

- Replaced the combined `beat_validation` purpose with independent `beat_story_validation` and `beat_state_validation` purposes. Both use the existing Smart Extractor profile and unchanged `{"valid": boolean, "issue": string}` response schema.
- Both validators receive byte-identical user context for previous Beat, current state, current job, reserved later job, state effects, and candidate Beat. Only `CHECKS` differs: Story runs checks 1, 2, 4, and 6; State runs checks 3 and 5.
- The two requests run concurrently for each candidate. Both must return valid before finite-endpoint checks and acceptance continue. Each result and issue is logged under its validator name; failed reasons retain Story/State attribution in the existing retry/regeneration feedback.
- Removed the combined validator purpose and builder. Existing separate finite-endpoint and within-Beat coherence checks remain unchanged.
- Verification: forward-Beat, retry hierarchy, at-a-time validator, source-span, simplified-prompt, and dynamic-profile suites passed (115 passed; 2 unrelated stale assertions deselected; 2 subtests passed). The postmortem regression suite passed (79 passed; one unrelated stale wardrobe-prompt assertion deselected). Split-validator profile/transport tests passed (3 passed). `py_compile` and `git diff --check` passed.

## 2026-10-09 — accept quote-wrapped prop evidence

- Updated `parse_current_segment_persistent_prop_result()` to strip repeated,
  matching straight or curly quotation pairs from a temporary evidence value
  before the existing case-insensitive exact-substring check against the
  current Beat and assigned source.
- The parsed evidence retains its original enclosing and internal quotation
  marks. Evidence still must match a source substring; prop validation,
  extraction prompts, schemas, and logging are unchanged.
- Added regressions for straight/curly and redundant enclosing quotes, unquoted
  exact evidence, preserved internal quotation marks, and incorrect quoted
  evidence.
- Verification: WorldState foundation selection passed (53 passed, 7
  subtests; 2 unrelated stale story-start assertions deselected), Director
  retry tests passed (112 passed, 4 subtests), and `py_compile` plus
  `git diff --check` passed.

## 2026-10-09 — validate complete initial-Subject and static-fixture seeds

- `extract_initial_location_subjects()` now checks that each Beat's explicitly
  referenced canonical Subjects have classifications before accepting that
  attempt. Matching uses exact canonical names and only unambiguous aliases
  already supported by the parser. An incomplete response enters the existing
  three-attempt retry path; after exhaustion it fails closed. The check runs
  before earliest classifications are recorded, so rejected partial attempts
  cannot affect earliest-classification-wins. Prompts, schemas, and diagnostics
  are unchanged.
- `seed_canonical_static_location_state()` now merges duplicate declarations
  with the same stable fixture identity when their physical fields agree. A
  difference in `anchors` versus `objects` provenance alone is ignored, and
  compatible known/unknown capability declarations are combined. Conflicting
  mobility, kind, type, placement, or other physical attributes still fail
  closed; same-name conflicting static declarations cannot silently receive a
  second ID.
- Added the tavern Beat-2 Goblin/Amy incomplete-classification retry and
  three-attempt failure regressions, plus stone-hearth duplicate, idempotence,
  stable-ID, capability-merge, mobility-conflict, and type-conflict coverage.
- Verification: the WorldState foundation and location-reference suites passed
  with 91 tests and 7 subtests; two pre-existing stale registered-story-start
  prompt/response assertions were deselected. Running both files without the
  exclusions reports those same two failures. `py_compile` and
  `git diff --check` passed.

## 2026-10-09 — repair Director RAW physical/spatial validation failures

- Added `director_raw_scene_repair`, routed through
  `SMART_EXTRACTOR_LLM_SETTINGS`. It receives only the current normalized RAW
  prompt and physical/spatial validator issue bullets, requests plain altered
  RAW text, and has an 8192-token output cap for full-scene replacements.
- After `director_raw_scene` produces an otherwise accepted candidate, a
  physical/spatial failure now invokes the repair call up to five times. Each
  non-empty replacement is normalized through the existing RAW structure path
  and returned to the same physical validator. Existing structure and required
  dialogue checks run again on repaired output. If all five repairs fail, the
  current Director retry path goes back one stage and regenerates RAW.
- Prop-state and timing failures retain their existing Director retry path.
  The repaired text replaces only `request1_result.raw_scene`; accepted
  `state_actions` and their reducer dry-run result are preserved. Repair
  responses are recorded in the existing prompt history and bounded run log.
- Added regressions for the exact repair prompt, Smart Extractor routing,
  physical repair acceptance without a second creative RAW call, and five
  failed repairs followed by RAW regeneration. `docs/LLM_PROMPTS.md` lists the
  new call.
- Verification: Director retry and LLM-profile suites plus the RAW retry-budget
  regression passed (174 passed, 4 subtests); Director RAW prompt-contract
  tests passed (12 passed). `py_compile` and `git diff --check` passed. A
  combined run including all prompt-generation
  tests was interrupted at a socket wait; the focused retry-budget test passed.

## 2026-10-10 — publish job diagnostics and reference bindings

- The bridge now copies `expanded_story.txt`, `subjects.txt`, and `story.txt`
  alongside its existing acceptance artifacts when those files are available.
  Result publication force-adds only the current job's result directory so
  ignored `generation_state.json` and `prompt_history.txt` files are committed
  when listed in the artifact manifest. The manifest continues to list only
  files that were actually copied.
- Rejected `world_state_current_segment_subjects` responses now log the raw
  response, exact Python validation error, and attempt number. Retry behavior,
  extraction, and prompts are unchanged.
- Immediately before final H3 assembly, the run now logs each Segment's
  Subject/Picture binding records and the exact Subject definitions passed to
  the formatter.
- Added regressions for copying and publishing ignored/source artifacts,
  rejected Subject response diagnostics, and per-Segment pre-assembly binding
  logs.
- Verification: bridge tests passed (10 passed; one existing stale branch
  assertion deselected); WorldState foundation passed (58 passed, 7 subtests;
  two existing stale story-start prompt/response assertions deselected); the
  focused prompt-generation binding-log test passed (3 parameter cases).
  `py_compile` and `git diff --check` passed. Full-module runs reproduced only
  the three previously documented stale assertions; they were not changed.

## 2026-10-10 — allow auto-pilot acceptance branch

- Added `world-state-rebuild-auto-pilot` to the bridge acceptance experiment
  branch allowlist while retaining `world-state-rebuild` and the existing base
  branch.
- Updated the branch-allowlist regression to execute an acceptance job on the
  auto-pilot branch and verify that an unapproved branch is still rejected.

## 2026-10-10 — normalize persistent-prop evidence matching

- Fixed the source-evidence comparison used by `world_state_current_segment_props`
  after bridge job 30 exposed a U+002D/U+2011 mismatch. The comparison now
  normalizes Unicode hyphen/dash variants and whitespace on temporary copies
  of both strings, then requires the normalized evidence to remain a
  contiguous substring of the normalized current Beat/assigned source.
- Original evidence and source text remain unchanged; quote handling and all
  extraction behavior remain as before. Incorrect evidence still fails closed.
- Added regressions for U+002D versus U+2011, whitespace differences, an exact
  match, and incorrect evidence. Focused evidence tests passed (7 passed,
  56 deselected, 7 subtests); `py_compile` and `git diff --check` passed.

## 2026-10-10 — retain authored Subject/Picture bindings

- Acceptance job 31 showed Segment 1 logging no reference bindings or Subject
  definitions despite `subjects.txt` defining Amy as `<Subject 1>` with
  `<Picture 1>`. `build_segment_reference_bindings()` initialized an empty
  tracking map and kept definitions only for IDs detected by matching the RAW
  description. When that text omitted the canonical name/tag, filtering erased
  the authored identity before H3 assembly, leaving the final identity check
  with no Subject 1 contract to validate.
- The binding builder now retains authored Picture-backed Subject mappings on
  Segment 1 directly from the identity registry. Physical presence and
  choreography remain separate; this does not infer scene presence or change
  later-segment visibility/removal behavior. The segment binding snapshot,
  H3 assembly, and identity validation receive the original authored mapping.
- Added a Segment 1 regression where accepted scene prose omits Amy's name but
  the authored mapping is retained, plus Segment 2 checks that the same mapping
  remains available and rejects a mismatched Subject tag.
- Updated the existing reference-window regression to expect authored Picture
  1 in the Segment 1 binding snapshot; its normal later-segment expiration is
  still covered.
- Verification: the Segment 1 binding regression passed (1 passed), the
  existing reference-binding selection passed (2 passed), and the focused H3
  identity mismatch regression and cross-segment identity-lock regression
  passed (1 each). The full
  `test_subject_identity_continuity.py` run had 44 passes and 4 failures in
  canonical-description wardrobe rendering, timed-sentence formatting, and
  speaker-verb wording; those code paths are outside this change and were not
  modified.

## 2026-10-11 — prepare action-only WorldState extraction (not wired)

- Added an action-only contract projection and parser that reuse the current
  request-scoped registered-name vocabulary, resolver, and reducer. Nested
  action references still resolve only through the supplied vocabulary; the
  reducer remains the only action legality check.
- Added a separately callable Smart Extractor path for validated RAW. Its
  repair requests carry the same immutable RAW and opening vocabulary, the
  rejected action response, and only the first concrete reducer diagnostic.
  The repair instruction explicitly requires the entire corrected batch,
  including actions that already passed, rather than only the rejected action.
  It allows five action-only repair calls, logs each raw response, and fails
  closed without mutating opening WorldState. This path is not connected to
  live segment generation.
- Added the two Smart Extractor purpose routes with 4096-token per-purpose
  output caps. The live Director combined response and its existing prompts
  remain active until the user approves the Director prompt/schema separation;
  no incomplete split pipeline is enabled. The raw correction budget and live
  orchestration are therefore not yet migrated.
- Added focused tests for the action-only schema/name resolution, repair with
  unchanged RAW, reducer acceptance, failure after five repairs, and unchanged
  opening state.
- Verification: the new focused tests passed (3 passed). The WorldState
  foundation and Director retry modules together reported 179 passed and 14
  subtests, with two existing stale registered-story-start assertions failing
  (`classification`/`evidence` response shape and old prompt wording). Syntax
  compilation and `git diff --check` passed.

## 2026-10-11 — temporary pre-Director replay fixture

- Added a test-only `--pre-director-replay-fixture PATH` option and reusable
  fixture from bridge job
  `accept-world-state-rebuild-tavern-20261011-33-director-baseline`. It loads
  the saved story/arc/Beats/canon, extracted location data, canonical
  pre-Director WorldState, authored Subject/Picture identity lock, reference
  mappings, and first-Segment Subject vocabulary. Fixture loading rejects any
  snapshot with completed Segments or a WorldState hash that differs from the
  captured first Director opening.
- The replay bypasses the upstream character canon, Beat, wardrobe, location,
  story-start, and current-Segment WorldState extraction calls for Segment 1.
  The normal Director, validators/repairs, H3 assembly, and later Segment path
  remain active. The option forces prompt-only mode and is ignored entirely
  when absent.
- Before Request 1, replay compares its reconstructed messages and opening
  WorldState hash against job 33's captured request. They matched exactly;
  the state hash is
  `d9ba6db94ff5d5a9b4bd62a2742d41bd00013f43cad0c20242be92ced7449de0`.
  The artifact recorded zero completed Segments, so no failed Director/repair
  state is restored. Legacy continuity/prop ledgers are not loaded from the
  artifact.
- Example invocation:
  `python minimax.py 8 6 0.5 --refresh 999999 --vision-continuity 0 --model gpt --image1 amy.jpg --pre-director-replay-fixture tests/acceptance/fixtures/tavern_job33_pre_director/replay.json`
- Added four replay regressions. Replay, prompt-generation, source-mode, and
  Director retry tests passed (156 passed, 7 subtests). WorldState foundation
  had 62 passes, 7 subtests, and the same two stale story-start contract/prompt
  failures documented above. `py_compile` and `git diff --check` passed.

## 2026-10-11 — preserve timestamps during pronoun resolution

- Job 35 exposed a pronoun-resolution response changing a RAW timestamp. The
  resolver previously compared timestamp values only after canonicalization;
  it now compares the literal timestamp values in exact order and count before
  accepting the response, then checks that every returned timestamp is inside
  the Segment duration. A rejected response follows the existing error path,
  leaving the accepted Director RAW in place.
- Added a duration check immediately before visible-Subject resolution. The
  visible-Subject resolver continues to apply its existing RAW structure and
  duration validation after its transformation.
- Added the exact system-prompt rule `- Do not alter timestamps.` and converted
  the existing pronoun-resolution rules to `- ` bullets without changing their
  wording or meaning.
- Verification: all `tests/test_director_retry.py` tests passed (121 passed,
  9 subtests). Focused Director/timestamp tests passed (12 passed, 2 subtests).
  The combined Director retry and prompt-pipeline suite had 210 passes plus
  9 subtests and 24 failures; failures were stale prompt/contract expectations
  in the existing `test_llm_prompt_pipeline.py` suite, outside this change.
  `py_compile` passed.

## 2026-10-11 — quote-wrapped Subject evidence and authored references

- `world_state_current_segment_subjects` now strips one matching enclosing
  straight or curly quotation-mark pair from a returned evidence excerpt for
  the existing source-substring check. The check remains case-insensitive and
  fail-closed; the model's evidence text is not rewritten or used to admit
  invented text.
- Added quoted-valid, unquoted-valid, and quoted-invalid evidence regressions.
- Traced authored Picture preservation from `base_subject_definitions` through
  `world_state_subject_definitions()` and `build_segment_reference_bindings()`.
  The current code preserves `<Subject 1>` / `<Picture 1>` for Segment 1 even
  when RAW does not mention Amy and generated reference images are empty. The
  regression now exercises this complete helper path through final H3 identity
  validation. No production binding change was made because the current code
  already has the preservation behavior.
- The published artifact named r36 available on `gpt-runtime` is from
  `object-state-work`, repository revision `33786849d5f7e2fa4949086b0749ee4e44b238a7`;
  it does not contain the reported empty-binding diagnostic and its Segment 1
  H3 text includes Amy's Subject 1 / Picture 1 definitions. The exact Job 36
  log described in the request was not available in that artifact, so the
  reported empty value could not be traced to its input boundary.
- The StateAction split remains gated. No RAW prompt/schema or Director action
  integration was changed; exact proposed RAW prompt/schema removals are being
  submitted for approval before wiring the existing action-only extraction and
  repair path.
- Verification: focused Subject-evidence and authored-binding regressions
  passed (5 passed, 4 subtests). The combined WorldState foundation and
  postmortem modules had 143 passes, 11 subtests, and 5 failures in unrelated
  stale story-start, wardrobe, legacy-prop, and legacy-H3 expectations.
  Syntax compilation and whitespace checks passed.

## 2026-10-11 — separate Director RAW generation and StateActions

- Removed the StateAction vocabulary and required `state_actions` field from
  Director Request 1. The existing readable WorldState opening block remains
  in that request: it presents known Subject presence, location, support and
  posture, plus each prop's holder/location/support, contents, condition, and
  mechanism state. No action vocabulary or IDs are sent with creative RAW.
- After RAW validators/repairs, visible-Subject resolution, and deterministic
  carry-forward accept the final RAW, the existing Smart Extractor action call
  receives that immutable RAW, the Segment's opening WorldState, and registered
  entity names. The existing reducer validates the full action batch; up to
  five repairs return a complete replacement batch. Exhaustion fails closed
  with a dedicated error and does not enter RAW repair or the general run
  recovery loop.
- Removed the combined Director response parser/contract and its Request-1
  reducer retry path. StateActions are attached to the accepted segment result
  only after dry-run acceptance, so the existing completed-segment commit
  boundary remains in force.
- Added regressions for the action-free RAW schema, retained readable opening
  state, action-only reducer/repair behavior, prompt-only sequential commits,
  and fail-closed exhaustion. The focused Director retry module passed. The
  Director retry module passed (118 tests and 7 subtests), replay tests passed
  (4), and sequential prompt-only generation passed for one and five Segments
  (2). The WorldState foundation module had 65 passes and 11 subtests; two
  existing stale story-start assertions still fail (old `classification` /
  `evidence` response shape and old prompt wording). The new recovery-boundary
  regression passed. The prompt-pipeline module had 97 passes and 18 failures;
  those failures are existing assertions for older Director/beat/H3 prompt
  text and formatter behavior, not the new action-free response contract.
  Syntax compilation and `git diff --check` passed.

## 2026-10-11 — explicit StateAction JSON contracts and replay review

- Added the exact `{"state_actions": []}` return envelope to both the
  `director_state_actions` and `director_state_actions_repair` system prompts.
  Each prompt now says the array may be empty and otherwise contains complete
  StateAction objects matching one permitted operation structure, with no
  extra fields and registered entity names in place of Python IDs. The
  operation object structures are derived from the current per-request action
  schema, so the prompt and structured response schema expose the same allowed
  operations and fields without maintaining a second contract.
- Added regressions asserting both prompt paths include the envelope and
  schema-derived operation shapes, and that the action-only response keeps
  using registered names. The focused extractor/repair and WorldState schema
  tests passed (2 passed); the full Director retry module passed (118 passed,
  7 subtests).
- Re-ran `tests/test_llm_prompt_pipeline.py`: 97 passed, 18 failed. Fifteen
  failures are stale assertions for prior beat-validator, Director, camera,
  dialogue, music, and H3 prompt wording/formatting; one also formats the
  current Director template without required fields. Two failures expose
  independent behavior mismatches worth separate review: recent spoken
  dialogue exclusions are discarded by `build_generation_messages()`, and
  continuation H3 assembly duplicates “seamless continuation.” A third test
  expects Request 1 to include the current assigned source; the builder
  currently omits it. That source-context mismatch could affect how faithfully
  RAW represents assigned work and should be resolved as a separate design
  decision. No failing prompt-pipeline tests were edited in this change.
- Ran the six-Segment pre-Director replay fixture with its captured settings.
  Segment 1's request matched the fixture opening hash and dynamic inputs,
  passed RAW checks, extracted two reducer-valid support actions, and committed
  revision 7. Segment 2 then produced a RAW timestamp at 00:08.817, outside
  its 8-second duration, so the segment was rejected. Recovery restarted from
  Segment 2; the replay fixture correctly rejected this restart because it is
  restricted to captured Segment-1 settings. The retry loop was stopped. This
  replay confirms the first-segment action-only path and commit, but it does
  not establish six-Segment completion or action-extraction completeness.

## 2026-10-12 — use the continuation timeline for timestamp checks and replay resume

- Segment 2's `00:08.817` was not invented by a later LLM transformation.
  Director Request 1 supplied `00:07.900`; Python shifted nonzero continuation
  timestamps by the 22-frame pinned-guide offset (`22 / 24 = 0.9167s`) before
  pronoun resolution, producing `00:08.817`. This is within the extended H3
  prompt timeline of about `8.9167s`; removing the pinned guide returns it to
  local `00:07.900` in the delivered eight-second Segment.
- The confirmed defect was the pre-visible-Subject check using the delivered
  eight-second duration for already-shifted RAW. It now uses the same effective
  timeline duration as pronoun resolution and visible-Subject resolution. The
  Python guide shift also checks the shifted RAW against that duration. Existing
  Request-1 and repair checks remain on the unshifted Segment timeline; the
  pronoun and visible-Subject transformations retain deterministic timestamp
  range/structure checks. The identity carry-forward after Subject resolution
  changes names/end-state text only and does not alter timestamps.
- Pre-Director replay now accepts `--resume N` for later Segments. It reuses the
  fixture's captured upstream inputs but restores the completed-Segment
  checkpoint; only a Segment-1 start loads and seeds the fixture WorldState.
  Internal recovery follows the same path, so Segment 1's opening fixture is
  not reapplied over its committed ending.
- Segment 1's extracted support actions were, in order, Amy setting support to
  the polished table, then clearing support (`support_id=null`) when she steps
  down. Both transitions are explicitly staged in finalized RAW. The committed
  ending has Amy standing on the tavern floor with no support, matching the
  second action. The table climb is unusual and unnecessary for the assigned
  wiping beat, but it is present in RAW; the StateAction batch accurately
  records it rather than introducing the choreography. This does not establish
  action-extraction completeness beyond this Segment.
- Added regressions for the shifted `00:08.817` timestamp/effective duration,
  out-of-range timestamps at visible-Subject resolution, and replay resume from
  a checkpoint whose WorldState differs from the fixture opening. Verification:
  `pytest -q tests/test_continuation_frame_anchor.py
  tests/test_pre_director_replay.py tests/test_director_retry.py` — 136 passed,
  7 subtests; `py_compile` and `git diff --check` passed. No runtime prompts,
  response schemas, validator rules, or WorldState operations changed.

## 2026-10-12 — concise Director Request 1 state context

- Reworked the deterministic `director_raw_scene` user-message context. The
  Subject list now keeps authored `<Subject N>` numbering and available
  `<Picture N>` bindings while dropping verbose identity descriptions, unknown
  placeholders, and redundant default speaker IDs. Subject locations and
  posture are rendered from explicit WorldState facts only. Current wardrobe
  is omitted when an active clothing reference matches its recorded wardrobe;
  otherwise WorldState clothing remains visible and takes precedence over a
  stale reference. Static fixture positions come from canonical location state,
  while dynamic positions and prop placement come from WorldState. Props are a
  concise name-first list; unknown placements remain unstated.
- Passed canonical location state and character-reference metadata into the
  existing prompt builder. Updated the saved pre-Director replay's Request 1
  message to the newly formatted deterministic context, retaining its captured
  WorldState and other replay inputs.
- Added regressions for canonical Subject/Picture numbering, explicit posture,
  concise static positions versus dynamic support/holder state, unknown
  locations, matching/stale wardrobe references, and the action-free Request 1
  path. `pytest -q tests/test_director_request1_context.py
  tests/test_director_retry.py tests/test_pre_director_replay.py` passed (130
  passed, 7 subtests). Syntax compilation and `git diff --check` passed.

## 2026-10-12 — share concise WorldState context with RAW validators

- The physical RAW validator previously received the verbose generic
  `format_world_state_prompt_context()` output under KNOWN SUBJECT STATE. It now
  uses the same deterministic Subject/Picture, location, wardrobe/reference,
  and prop sections as `director_raw_scene`. The full STATIC SETTING AUTHORITY,
  current Beat, previous shot end, RAW scene, system prompt, and response
  contract remain in place.
- The prop/state validator previously received canonical WorldState as compact
  raw JSON with internal IDs. It now receives those same readable context
  sections under its existing PROP LEDGER heading. The timing validator takes
  RAW only and has no WorldState context, so it was not changed. No validator
  rules, retries, or system prompts changed.
- Added a regression comparing all shared context sections across Director
  generation, physical validation, and prop-state validation, while checking
  that both validator requests retain their Beat, previous-shot, RAW, and full
  static-setting inputs. `pytest -q tests/test_director_request1_context.py
  tests/test_director_retry.py tests/test_pre_director_replay.py
  tests/test_location_state_reference.py` passed (165 passed, 7 subtests).
  Syntax compilation and `git diff --check` passed.

## 2026-10-12 — split creative and timed Director RAW stages

- Director RAW now starts with a free-text, untimed creative call using the
  approved creative prompt and Smart Creative profile. It receives the
  existing deterministic Subject/Picture, WorldState, static-setting, Beat,
  and previous-shot context, without a JSON-only suffix.
- Before timing, the movement validator now uses the approved subject-motion
  prompt. Its exact first physical issue is repaired through the existing
  `director_raw_scene_repair` call. The existing Director prompt and response
  contract then format the accepted creative scene into timed RAW. The final
  formatted candidate still passes shot structure, dialogue, physical,
  prop/state, and timing checks; any downstream physical issue uses the same
  bounded repair budget and is revalidated before continuing.
- Creative, formatter, repair, and validator calls retain separate prompt
  history/log records. RAW repair attempts are shared across pre-format and
  post-format corrections within a Director attempt. WorldState, StateAction
  extraction, segment acceptance, and commit timing were not changed.
- Added split-pipeline regressions for the untimed creative contract, the
  west-wall barrel route, preserving cloth/ladle identity, removing an
  unnecessary stool climb, and repairing a physical error reintroduced by
  timed formatting. `pytest -q tests/test_split_raw_pipeline.py` passed (6).
  `py_compile` and `git diff --check` passed. A broader run of
  `tests/test_director_retry.py` and `tests/test_llm_prompt_pipeline.py` had
  45 failures, 200 passes, and 2 passing subtests. Most failures are old
  single-call mocks/assertions that assume one structured RAW call or the
  previous physical prompt; those expectations need migration before that
  combined suite can serve as a gate. `tests/test_world_state_foundation.py`
  had 66 passes, 2 unrelated stale story-start extractor expectations, and 11
  passing subtests.

## 2026-10-14 — split location description and JSON extraction

- `story_setting_extract` now returns only spatial prose. Its existing bounded repair call addresses rejected text; explicit contradictory placements are checked before JSON creation. `story_setting_spatial_refine` independently retries explicit inconsistent upstream geometry instead of passing that issue to the downstream repair.
- The new `story_setting_json_extract` receives only accepted physical text and a canonical location name. It retries malformed, schema-invalid, or geometry-conflicting JSON from the same unchanged input; it never repairs JSON or regenerates already accepted prose. Exhaustion raises `StorySettingJSONExtractionError` without backstepping the initial location pipeline.
- Narrowed text-derived fixture claims so a building's distinct north/south walls are not interpreted as contradictory positions of that building. Both initial and dynamically registered locations use the split via `extract_story_setting_description`.
- Updated purpose profiles, prompt inventory, and location-reference regressions. Verification: GitHub changes reviewed; repository tests and local LLM generation must still be run.

## 2026-10-15 — Alice Segment-1 endless restart and fixed-fixture regressions

- Local console logs show Segment 1 reaches final H3 assembly and raises `NameError: name 'transitioning' is not defined`. The transition flag lived only inside `build_segment_bundle`, while H3 assembly referenced it in another scope. Added a pure origin-start resolver using the bundle's actual `location_transition` metadata; Segment 1 transitions now use their origin name and later segments do not emit a new starting-location instruction.
- The recovery supervisor previously caught any programming `NameError` as recoverable and restarted expensive pre-Director setup from Segment 1. NameError now terminates with a clear fatal diagnostic; three identical failures on the same incomplete segment also stop automatic restarts rather than spin indefinitely.
- The per-Segment prop extractor previously retried three times when it returned an already registered fixed fixture as a new movable prop. Already registered exact-name candidates are now deterministically skipped while genuinely invalid new entries still fail validation. The prompt also distinguishes bracing/gripping fixtures from acquiring props.
- The RAW visible-Subject filter incorrectly rejected registered Alice because her name also appeared inside `front step of Alice's house`. Exact registered Subject identities now win over non-Subject-label collisions.
- The WorldState event translator now ignores spurious `take` / fixture-actor `move` interpretations of registered fixed geometry instead of discarding otherwise valid event batches. A fixture-contact clarification was added to its extraction prompt. Other unresolvable/reducer-rejected batches retain existing all-or-nothing rollback.
- Regression tests added for H3 location origin, registered-Subject collision, registered fixture skipping, and fixed-fixture events. **Tests have not been run in the local repository or against the local 20B.** Next action: run focused pytest and an end-to-end Alice generation, confirm Segment 1 completes, then inspect origin/destination location geometry and the resulting WorldState movement. Two independently generated location descriptions in the provided checkpoint still disagree on front-step/post geometry; these edits do not purport to solve that broader cross-location continuity issue.

## 2026-10-15 — Remaining issues: connected-location geometry and physical validator truncation

- The rabbit-hole location was generated independently of the earlier accepted front-step geometry, allowing the second location to move/resize/recreate shared landmarks. For a newly registered **transition** destination, the already accepted origin setting is now provided as immutable neighboring context to spatial refinement and physical description. Only those two text stages get this context; `story_setting_json_extract` still receives only the accepted destination prose and canonical location name, and never repairs JSON or reinterprets the neighbor.
- The JSON extraction system prompt now excludes existing neighboring/exterior fixtures when they are described only to orient the new location. Other new locations and initial location extraction retain their earlier prompt shapes. This is prompt-level grounding, **not yet proven deterministic cross-location reconciliation**.
- The physical validator's 9 consecutive `finish_reason=length` retries ran on a 3072-token output cap and 1024-token high-reasoning profile. Only `director_raw_scene_physical` was changed to the existing `EXTRACTOR_LLM_SETTINGS` (medium/256 reasoning) and a 4096-token output cap; its validation contract is unchanged.
- `_fixed_prop_motion_issue` now also rejects attempts to pull a fixed fixture *from / into / onto* another location while allowing simple contact such as pulling on a post to steady oneself. The prop-state validator system prompt clarifies this distinction.
- Regression tests in `tests/test_location_state_reference.py` cover immutable neighboring input, unchanged JSON isolation, runtime transition wiring, output profile, and fixed-fixture contact vs displacement.
- Commits: `a158f607` (context and validator tuning), `aea103bc` (transition wiring and fixed-pull guard), `cc181257` (focused regressions). **GitHub changes reviewed; pytest and local GPT-OSS 20B/ComfyUI runs have not been executed**. Existing `generation_state.json` was created with inconsistent prior geometry and cannot demonstrate the new behavior without regenerating location descriptions.

## 2026-10-16 — WorldState events, canonical destinations, and transition endpoints

Implemented on `multi-location-support`, starting from remote/local head
`89b621298e24189f1a4f753a80cb51104d996db3`.

- Found an additional cause of zero-action commits: successful event translation
  did not return the immutable RAW echo required by `_assert_event_raw_unchanged`.
  The wrapper consequently discarded otherwise accepted actions. Translation now
  returns that echo and retains the integrity check.
- Independent events are validated and reduced in order. An invalid entry no
  longer erases unrelated valid events, including mixed malformed extraction
  entries. Each event's reducer-operation expansion remains atomic. Reducer
  preconditions still protect dependent operations; an unresolved earlier move
  also blocks implicit placement at an assumed new location. Every event logs
  acceptance, omission, or rejection with its reason and original index.
- RAW grounding rejects unsupported actor/action, destination, ownership endpoint,
  mechanism, and clothing interpretations. Fixed-fixture contacts remain
  nonpersistent. Extractor claims of consuming/transferring "all" cannot override
  RAW's stated amount. No actions are invented to make state advance.
- Movement destinations resolve existing names and fixed surfaces/entrances to
  their canonical owning locations. The scene-location selector also reuses
  fixed-surface owners instead of registering those surfaces as new locations;
  selection itself still does not move a Subject. Regressions commit Alice from
  her house's front step to the rabbit-hole interior and then the meadow, using
  each committed state as the next segment's opening.
- Accepted destination prose rejects local redeclarations or detailed measured
  reconstructions of known neighboring fixtures through the existing bounded
  prose repair. JSON extraction still receives only accepted prose and the
  canonical name. Python then reconciles fixed fixtures against existing names,
  types, and owners before registration. Known neighboring fixtures keep their
  original ID/owner; ambiguous identities fail rather than acquire another copy.
  Same-owner fixtures and distinct names are preserved. An extraction-to-seeding
  regression verifies one canonical fixture and one H3 WorldState fixture entry.
- Passage geometry is checked before JSON extraction/reference rendering using
  authored story/Subject information and the current traversal. Explicit body or
  shoulder widths work across anatomies; explicitly identified adult humans without
  authored body widths get a conservative 35-cm width screen. Explicit sizes in
  fictional settings take precedence over that fallback. Explicit subject height is checked for
  upright walking, allowing crouching/crawling. Dimension parsing separates length
  from width/height and handles decimal/unit forms. Authored passage conflicts
  are reported before an LLM call and cannot be cleared by omitting their
  measurement in prose repair. Unrelated measured openings do not automatically
  constrain another traversal. Spatial refinement now preserves source sizes and
  uses relative scale instead of requiring invented numeric dimensions.
- Transition-only creative/repair context now establishes opening WorldState and
  the source-owned destination outcome. It leaves incidental travel choreography
  to H3 while preserving explicit actions, prop changes, dialogue, injuries, and
  required movement manner. Final H3 retains `<Video 1>` as origin and `<Video 2>`
  as destination with separate temporal roles. The timestamp assembler preserves
  accepted action text; accepted RAW is not stripped afterward. Same-location
  prompting and the completed-segment WorldState commit boundary remain intact.

Verification performed locally:

- `pytest -q tests/test_world_state_event_extraction.py tests/test_location_fixture_geometry_repairs.py tests/test_location_surface_aliases.py tests/test_transition_policy.py tests/test_split_raw_pipeline.py tests/test_continuation_frame_anchor.py`
  — **86 passed, 3 subtests passed**.
- `pytest -q tests/test_world_state_foundation.py -k 'StateActionSupportEvidenceTests or WorldStateTransactionTests or WorldStateReducerTests'`
  — **40 passed, 66 deselected, 6 subtests passed**.
- Broader location-reference, WorldState prompt-authority, and pre-Director replay
  modules — **76 passed, 6 failed**. All six failures were independently reproduced
  in an archived clean copy of the starting commit: old static-setting/period,
  physical-validator and wardrobe expectations, old readable-WorldState wording,
  and replay assuming the creative request precedes scene-location selection.
  The changed spatial-size and transition assertions were updated to the requested
  contracts. The full repository suite is not claimed healthy.
- `python -m py_compile minimax.py world_state.py story_planner.py` and
  `git diff --check` passed. Inspected assembled H3 output preserving a weapon
  drop and spoken dialogue with ordered origin/destination references.
- Runtime files are overwritten into `/mnt/h/StableDiffusion/automation` and
  compared byte-for-byte before delivery.

Known limits and next acceptance: lexical event grounding deliberately skips
ambiguous/pronoun-only or unusual paraphrases instead of inventing state. Fixture
identity matching is conservative; unsupported aliases fail or require clearer
ownership rather than semantic guessing. Geometry checks cover explicit numeric
clearances and known body sizes, not a general anatomy/spatial reasoner; unknown
forms, complex shape changes, and ambiguous source-to-passage relationships still
need semantic validation and real acceptance. No new LLM calls, cloud dependencies,
or alternative state authorities were added. **No local GPT-OSS 20B generation or
ComfyUI render was run for this change.** Run a fresh Alice generation from authored
inputs with regenerated location descriptions and reference videos, inspect event
diagnostics and committed locations for all six segments, then verify the visual
transitions. Old generated location/reference artifacts do not verify these fixes.

## 2026-10-17 — stop Segment-1 replay and recover within the failed stage

Implemented on `multi-location-support`, starting from `b2691097`. Read the
operating contract, prior handoff, and that commit before editing. Investigated
the supplied automation `console_logs.txt`, `generation_state.json`, and
`prompt_history.txt`: 11 supervisor restarts, zero completed segments, repeatedly
regenerated canon/wardrobe/start state, selector-to-origin collisions, semantic
fixture errors retried as identical JSON extractions, and a missing required
`/home/j/AI/ComfyUI/input/amy.jpg`. That file is still absent; it was not replaced.

- Required configured image assets now fail preflight before canon, wardrobe,
  LLM requests, or render dispatch. Authored Picture dependencies are also checked
  when their LoadImage slots are disconnected. Saved prompt/reference-job assets
  are validated before saved rendering. `ReferenceAssetError` gives the expected
  path and a repair/override action.
- Optionality is explicit: `_meta.reference_optional: true` on a LoadImage node;
  saved-job configured-picture sources may explicitly set `optional: true`.
  Unavailable optional Pictures are disconnected and removed from runtime Subject
  and H3 bindings, including workflow reload and checkpoint-derived binding paths.
  A required use of the same Picture in another workflow prevents optional
  removal. Original authored files, canonical identity provenance, and source
  fingerprints remain unchanged; tests cover bindings not returning on resume.
- Removed the entry point's blanket `_run_main` replay. Escaped failures stop
  with a diagnostic and preserve accepted outputs/completed checkpoints. Recoverable
  output errors remain inside their existing owning-stage budgets. The shared
  backstep helper now allows at most one explicitly declared predecessor
  correction by default; root-stage or exhausted recovery raises
  `PipelineStageExhaustedError`. Programming/infrastructure errors do not request
  narrative regeneration. No new persistent intermediate-state cache was added.
- Semantic fixture ambiguity/type conflicts now raise a distinct error carrying
  the fixture, canonical owner/type, and exact uncertainty. JSON syntax/schema
  errors retain unchanged-input extraction retries; fixture identity failures
  return immediately to the existing bounded physical-description repair. The
  repaired prose is validated before new JSON extraction and deterministic
  reconciliation. Exhaustion is terminal at the location stage. Explicitly
  distinct local fixtures are preserved; unrelated owner mentions do not silently
  merge them. A spatial suffix such as "garden south of wooden post" identifies
  a garden relative to a post; it no longer makes the garden match the post's
  identity/type, reproducing and correcting another error in the supplied log.
- Canonical location names resolve before connection fixtures. Entrance/portal
  fixtures no longer alias a destination interior to their near-side owner.
  Known fixed floors/surfaces still resolve their owning place. Supported missing
  interiors can use the existing registration flow. Selector inconsistencies get
  bounded local corrections carrying their precise diagnostic. Successful stage
  preparation records canonical `{origin_location_id, entrance_fixture_id,
  destination_location_id}` connections in checkpoint metadata; this does not
  move a Subject or add a second WorldState authority.
- Destination preparation uses detached metadata and candidate WorldState, then
  publishes only after reference preparation succeeds. A regression executes the
  actual nested stage and verifies that reference failure preserves canon,
  wardrobe, initial location, WorldState, nested metadata, and checkpoint writes.
- Movement paraphrases and unambiguous pronouns can use the current Beat/assigned
  source plus an accepted connection. RAW must independently perform the traversal
  through that entrance or a supported deictic reference. Selection alone is
  insufficient; another doorway, unregistered endpoint, conflicting actor, or
  unsupported prop event is rejected. Logs include the actual RAW evidence and
  connection basis. Independent invalid events still preserve valid actions.
  No additional LLM calls or broad creative Director prompt rewrites were added.

Verification:

- `pytest -q tests/test_stage_local_recovery.py tests/test_reference_asset_preflight.py tests/test_destination_stage_recovery.py tests/test_world_state_event_extraction.py tests/test_location_fixture_geometry_repairs.py tests/test_location_surface_aliases.py tests/test_transition_policy.py tests/test_split_raw_pipeline.py tests/test_oct15_loop_regressions.py tests/test_reference_pruning.py`
  — **137 passed, 26 subtests passed**. Tests prove the automatic Segment-1 replay
  loop is eliminated: escaped downstream errors call `_run_main` once, missing
  required images make no expensive calls, and local exhaustion terminates.
- Existing `RuntimeRecoverySupervisorTests` selection — **7 passed**; affected
  assertions now require terminal propagation instead of upstream replay.
- Existing WorldState support/transaction/reducer selection — **40 passed,
  66 deselected, 6 subtests passed**.
- Broader resume/workflow/location suites — **137 passed, 9 failed,
  17 subtests passed**. All nine failures reproduce on a clean archived
  `b2691097`: four old print/logging mock expectations, four existing location
  prompt/wardrobe expectations, and the existing fallback wardrobe-seeding
  failure. The changed missing-image expectation and selector cache-order
  regression were migrated to the new contracts. Full suite health is not claimed.
- An additional older prompt-mode integration selection was interrupted in an
  unmocked LLM connection-retry wait; it has no passing result. No actual local
  GPT-OSS generation or ComfyUI render was performed for acceptance.
- `py_compile`, `git diff --check`, and byte comparisons of changed Python files
  against their overwritten automation counterparts passed before delivery.

Remaining acceptance: restore the missing required identity image or provide a
valid override (or explicitly mark all its uses optional), then run the fresh
local Alice generation. Verify local ownership repair, entrance/interior geometry,
connection-grounded movement commits, and visual transitions. Paraphrases without
an accepted connection, ambiguous actor/endpoint references, and unsupported new
location names intentionally remain conservative; older checkpoints without
connection metadata may need location preparation regenerated. Automated tests
establish recovery boundaries, not six-segment film quality or rendered validation.

## 2026-10-17 — normalize location proposals and preserve connected movement

Read the current `PROJECT_NOTES.md` and this handoff before editing. The supplied
automation `console_logs.txt` is from the latest run that hit the `new_location`
failure. It shows the selector returning `new_location` / `the forest clearing`
three times even though that alias resolves to the active Forest Clearing ID.
The resolver then rejected the proposal and repeated the same LLM call until
local recovery was exhausted. The same log also shows Segment 2's invalid event
interpretations being discarded as an empty batch; it does **not** contain the
rabbit-hole movement example, which is covered with explicit replay-style tests.

- When `new_location` resolves uniquely to the active canonical location and the
  Beat establishes no departure to another registered place, Python now
  normalizes it to `same_location`. It reuses the existing ID/reference without
  another selector call or location registration. The original selector result
  and the deterministic reason are retained in the resolution metadata/log.
  Registered destinations, connected entrances, and ambiguous aliases still
  follow their existing resolution or bounded-recovery paths.
- Connected movement grounding no longer requires the event's destination label
  to lexically match the canonical destination when the source, accepted RAW,
  and registered entrance connection establish a unique traversal. An
  unambiguous pronoun/body-part actor reference resolves to the one registered
  Subject named in the RAW context; ambiguous antecedents remain rejected.
  Before returning an event batch, Python now detects a registered Subject's
  source- and RAW-grounded connected traversal if no accepted move/enter action
  records its destination. That condition raises an explicit continuity error
  instead of being swallowed by optional event-extraction fail-open. Rejected
  event batches remain uncommitted; unrelated unsupported event interpretations
  can still be discarded while supported independent actions survive.
- Current-segment Subject candidates require positive identity evidence beyond a
  pronoun/action-only excerpt. A weak candidate is omitted without discarding
  other valid candidates, preventing a pronoun continuation from creating a
  placeholder Subject. An explicitly described unnamed person/creature remains
  eligible. The existing registered-prop/location filter still blocks ordinary
  inanimate candidates; animated entities remain allowed when the source
  explicitly establishes animation.
- Pronoun resolution now accepts only exact replacements of pronoun spans with
  canonical registered Subject names, including grammatical possessives and
  unambiguous plural name lists. It preserves all other RAW text, timestamps,
  annotations, line structure, and end continuity. A response that changes any
  of these is rejected and the accepted input RAW is retained. No runtime LLM
  prompt, schema, retry, geometry, or fixed-fixture contact rule was changed.
- The existing tunnel/fixture geometry rules remain in place: north/south
  position, orientation, travel/extension, and elevation are distinct claims;
  neighboring fixtures remain references rather than being copied into the new
  location. Fixed-fixture contact remains non-acquisition.

Verification:

- Full focused modules — **388 passed, 12 failed, 30 subtests passed** across
  `test_location_state_reference.py`, `test_world_state_event_extraction.py`,
  `test_world_state_foundation.py`, `test_director_retry.py`, and
  `test_location_fixture_geometry_repairs.py`. All 12 failures were reproduced
  unchanged at starting commit `55c7c42d`: existing wardrobe/subject-start
  expectations, older prompt-string assertions, stale retry-count assertions,
  and an existing event-output expectation. No new regression test failed.
- Targeted selections: WorldState event extraction **42 passed**; fixture
  geometry **20 passed**; pronoun-resolution regressions **16 passed**;
  location-selection regressions **7 passed**; additional geometry/neighbor
  checks **6 passed**; Subject identity/phantom-candidate checks **7 passed**.
- `py_compile` and `git diff --check` passed. These tests establish deterministic
  alias resolution, event grounding, Subject filtering, and RAW preservation;
  they do not establish end-to-end local GPT-OSS 20B behavior or rendered video
  quality.

Next local acceptance: run the same-location multi-segment story and the Alice
front-step → connected interior traversal through local GPT-OSS 20B and ComfyUI.
Verify the selector makes one call for the same canonical location, each accepted
connected traversal commits before the following Segment opens, and an
unreconciled required traversal stops with its explicit continuity diagnostic.
Also inspect local Subject registration and final renders; automated tests do
not certify the complete film pipeline.

## 2026-10-17 — overlap Director preparation with serialized renders

Restored asynchronous next-Segment Director preparation for rendered runs when
visual continuity is not due. Once Segment N has an accepted StateAction batch,
Python reduces it against N's immutable opening state and prepares Segment N+1
from that projected result while N's ComfyUI render is in flight. Pre-Director
location selection and WorldState seeding run as part of that preparation, so
the Director request sees the correct next-Segment inputs without waiting for
the current video.

The projection and pre-Director seeds remain detached from the durable
checkpoint until Segment N's render succeeds. A render failure cancels and
discards its speculative Director request and clears the persisted prefetch;
the current segment is not marked complete and the opening WorldState remains
canonical. After a successful render, the existing reducer commit and completed
segment record are checkpointed, then the prepared next-Segment context is
published only if its projected opening hash still matches. Segment N+1's
render is still submitted only after Segment N has produced its video, keeping
AddGuide/previous-video dependencies and ComfyUI rendering ordered. Visual
continuity continues to complete before next-Segment preparation when its
cadence requires it. Prompt-only generation is unchanged.

Verification:

- New deterministic two-Segment scheduling regressions — **3 passed**. They
  prove Director prompt overlap with Segment 1 rendering, projected WorldState
  use, no durable completion/state before render success, speculative rollback
  after render failure, visual-continuity gating, Segment 2 render waiting for
  Segment 1's video, and final stitching waiting for the last render.
- `python -m py_compile minimax.py tests/test_continuity_scheduling.py` and
  `git diff --check` passed.
- A broader legacy selection across continuity scheduling, stitch barriers,
  prompt-generation mode, and resume reported **71 passed, 8 failed, 9
  subtests passed** after replacing the obsolete continuity-opening harness.
  Failures were in older continuity harnesses/contracts, outdated
  prompt-generation call-count expectations, a stitch test whose legacy
  harness did not reach rendering, and a pre-existing wardrobe fallback resume
  assertion. The new scheduling regressions passed; those broader failures
  remain unmodified and are not claimed as passing.

No runtime prompts, reducer semantics, visual observations, checkpoint schema,
or render workflow were changed. No live ComfyUI acceptance render was run.

## 2026-10-17 — make speculative prefetch failures recoverable across phases

Corrected the non-visual asynchronous scheduling path. Failures while projecting
or preparing Segment N+1 are now discarded as speculative work: Segment N can
finish rendering, commit its accepted WorldState, and checkpoint normally. The
next Segment then runs its ordinary authoritative preparation; failures in that
path still propagate, including infrastructure failures. Failures from a
speculative Director future likewise fall back to a normal Director request,
while errors from that authoritative request remain fatal.

When visual continuity is disabled, projected Director preparation can now
overlap the current render even if the next Segment begins a new phase. Phase
initialization runs against the projected context before location and
WorldState preparation, and its initialized marker is published with that
context after the preceding render succeeds. Visual-continuity gating is
unchanged. Render failure still cancels speculative work and retains the last
valid checkpoint; later rendering and stitching remain serialized behind the
preceding video.

Verification:

- Focused event-controlled scheduling regressions — **6 passed**. They cover
  speculative setup failure and normal-path fallback, authoritative preparation
  failure propagation, cross-phase prefetch with projected WorldState and one
  phase initialization, visual-continuity gating, and render-failure rollback.
- `tests/test_stitching.py` — **10 passed**.
- Combined `tests/test_continuity_scheduling.py tests/test_stitching.py` — **17
  passed, 3 failed**. The three failures are existing legacy harness/contracts:
  the old background-render test does not reach Segment 2 with its no-prefetch
  executor setup, and two direct `request_segment_llm` tests assume the previous
  combined RAW response contract / omit the required Director user context.
  All six new scheduling regressions passed.
- `python -m py_compile minimax.py tests/test_continuity_scheduling.py` and
  `git diff --check` passed.

No runtime prompts, WorldState reducer semantics, location resolution, scene
generation, checkpoint format, or render workflow changed. No live ComfyUI
acceptance render was run.
