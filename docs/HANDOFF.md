# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first for project-wide architectural rules. This file describes the current branch implementation, active experiment, latest evidence, and immediate next work.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `world-state-rebuild`

Runtime/bridge mailbox branch: `gpt-runtime`

Baseline branch this experiment diverged from: `main`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is development/evaluation only and must not become a production dependency.

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

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` remains the sole narrative authority. Expansion may add concrete staging/detail where the source is silent, but it may not add, replace, contradict, skip, reorder, or materially alter source events/outcomes.

### Primary goal achieved

### Next goal

Continuity

Location continuity -> 3-second persistent 360-orbit room reference is accepted; covered geometry stayed ~99% consistent in the latest tavern run
State/subject/action continuity -> active work

## 2026-10-08 — avoid re-extracting canon-covered dynamic wardrobes

- The initial-location/dynamic Subject compatibility path now receives `character_canon`. For a Subject with canonical clothing, it seeds the legacy continuity wardrobe from that existing record and skips a second `story_subject_wardrobe_extract` call and WorldState wardrobe sink update.
- Non-canon dynamic Subjects still use the existing extractor and compatibility behavior. Dynamic registration and `seed_canonical_wardrobes()` conflict checks are unchanged.
- Verification: WorldState foundation 42 passed (2 documented stale story-start prompt assertions deselected); location-reference 32 passed; syntax and whitespace checks passed.

## 2026-10-08 — canonical descriptive-name aliases in Subject resolver

- Added deterministic Python alias resolution for `director_raw_scene_subject_resolution`: a returned name matching a suffix of a supplied descriptive canonical name resolves to that Subject only when exactly one canonical Subject matches (for example, `Elf` to `Beautiful Female Elf`).
- Exact canonical names take precedence over aliases. Ambiguous aliases and names outside the supplied vocabulary fail closed. Earliest-classification behavior and the current Beat text are unchanged.
- No LLM prompt, response schema, or call path changed.
- Verification: `python -m pytest -q tests/test_location_state_reference.py` (32 passed), `python -m py_compile minimax.py tests/test_location_state_reference.py`, and `git diff --check` passed.

## 2026-10-08 — Subject resolver array response

- Updated the `director_raw_scene_subject_resolution` system prompt to the approved wording: classify each referenced possible Subject as entering (`present=false`) or already present and acting (`present=true`), omit unreferenced Subjects, return Subject names without adjectives, and return a JSON array.
- Updated the existing structured response schema and parser to accept only an array of `{subject, present, reason}` records. Canonical-name enforcement, strict rejection of unregistered names, and earliest-valid-classification behavior remain in place.
- Verification: `python -m pytest -q tests/test_location_state_reference.py` (28 passed), `python -m py_compile minimax.py tests/test_location_state_reference.py`, and `git diff --check` passed.

## 2026-10-08 — acceptance -12 Subject identity and wardrobe coverage

- Registered every `character_canon` identity in WorldState before canonical wardrobe seeding. This reuses the existing identity-only registration API and leaves presence/location unknown unless a separate authority establishes them.
- Made the existing per-beat `director_raw_scene_subject_resolution` parser reject keys outside the supplied canonical Subject vocabulary. The existing retry path handles invalid keys; the earliest valid classification remains authoritative. Beat text, including descriptive modifiers, is passed through unchanged.
- Expanded `canonicalize_defined_subject_wardrobes()` to run the existing `story_subject_wardrobe_extract` once for every `character_canon` Subject, including Subjects absent from `subjects.txt`. The same prompt/schema/profile are used. The narrow parser retry also rejects clothing that exactly equals the Subject's name; no broader wardrobe validation was added.
- No runtime prompt or LLM-facing schema changed. The fixed humanoid clothing rule remains in the existing wardrobe prompt.
- Verification: WorldState foundation 41 passed (2 pre-existing stale story-start prompt/schema assertions deselected); location reference 28 passed; character canon 14 passed (2 pre-existing stale prompt assertions deselected). New regressions cover identity without presence, wardrobe for later-appearing canon identities, exact-name clothing retry, unknown resolver keys, canonical numbered-role aliases, and unmodified descriptive Beat text.

Fix observed failures in order. Explain the failure and proposed fix before making substantive architecture/prompt changes.

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

## 2026-10-08 — acceptance #03: opening Subject classification

- Bridge preflight accept-world-state-rebuild-00-preflight-20261008-03: 10/10 passed.
- Tavern acceptance #03 at 5b897f2 reached all six accepted Beats but emitted no H3 prompts. It stopped before Director Request 1: authored Amy story-start classification exhausted 3 retries with `Explicit story-start classification requires exact source evidence`.
- The beat-wide extractor incorrectly classified Elf as present despite the explicit Beat-3 entrance.
- KISS-only changes within the existing minimax.py extractors: clarify that performing the initial Beat 1 action establishes presence; request short verbatim evidence; normalize whitespace before exact quote comparison; explicitly exclude later entrants from initial-state inference. No new LLM stage, state subsystem, or validator. Code f239381e; regression 0f2078e4.
- Acceptance #04 attempted focused tests and prompt generation, but both stopped immediately on a prompt string literal typo introduced in `f239381e`. Corrected only the newline syntax in commit `14fe4527` (no semantic changes to the fix). The #04 failures are **not** meaningful LLM/Director evidence.
- Full tavern acceptance #05 is queued on `gpt-runtime` at corrected branch head. The separate #05 focused-test job has not been successfully queued. Examine the #05 result before further code changes. The beat-ledger's hostile goblin and incorrect chalice ownership are later potential issues, not current blockers.

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

## 2026-10-06 — tavern generation postmortem fixes

Applied to `object-state-work` after reviewing the eight-second, six-segment tavern
generation:

- Fixed wardrobe component parsing so the `lower:` slot label is not mistaken for
  the action verb “lower”; lower garments and later outfit slots now survive
  normalization.
- Made the humanoid clothing requirement a fixed, species-neutral rule in
  defined-Subject wardrobe extraction and character reference rendering.
  Non-humanoid forms may use `N/A` when clothing does not apply.
- Preserved explicit period/culture/genre cues through static-setting extraction,
  spatial refinement, location description, and the final location-reference
  prompt. Medieval-fantasy locations must retain a visibly medieval-fantasy look.
- Strengthened the Director and RAW physical validator against gratuitous climbs
  onto counters, tables, bars, shelves, or stools when the beat and prior state do
  not establish the climb.
- Decoupled persistent Subject definitions from the shorter Picture-reference
  window. Definitions persist until an explicit departure; H3 continuation prose
  falls back to the durable Subject-state ledger when current continuity has no
  usable position.
- Corrected the initial-location held-prop detector's escaped word-boundary
  pattern so it rejects held-prop actions as intended.

The broader Python object-state validators for Amy's cloth and the chalice remain
deferred, as requested. After the next tavern run, inspect the wardrobe for
Goblin1/Elf1, Dragon1's clothing, the location's period styling, furniture use,
and whether Elf1/Dragon1 remain in their established positions through Segment 6.

## 2026-10-06 — WorldState foundation, review gates A and B

Implemented only the first two steps of the WorldState refactor for review. Do
not start Gate C or Gate D until the user approves this checkpoint.

- Gate A: sparse prop and Subject-ledger observations no longer replace
  established scalar or wardrobe facts with omitted, blank, `N/A`, or `unknown`
  defaults. Explicit empty Subject lists remain meaningful clears. A continuity
  wardrobe replacement of an established garment now requires a matching
  explicit put-on/take-off action in the newest scene. Story wardrobe extraction
  fills unknown slots and preserves already-established attire.
- The fixed clothing rule is explicit in wardrobe extraction and dynamic Subject
  resolution: humanoids must remain clothed regardless of species; non-humanoid
  forms may use `N/A` where clothing does not apply unless the source explicitly
  gives clothing. WorldState validation uses the explicit clothing-applicability
  field, not the Subject's name, and rejects `N/A` or `absent` slots when
  clothing is required.
- Gate B's identity-only seed is a temporary migration state. Later
  authority-specific seed functions may initialize story-start presence,
  canonical wardrobe, canonical location, and explicitly established props.
  Legacy continuity, RAW, visual observations, and beat summaries remain
  ineligible as WorldState seed or synchronization sources.
- Current schema: `schema_version`, `revision`, `source_sha256`, `seed_status`,
  `subjects`, `props`, and `locations`. A subject has immutable identity
  metadata (`physical_form` and `clothing_applicability`), unknown-initialized
  physical state, wardrobe slots, and identity provenance. A new run currently
  seeds only identity metadata from the user-authored `subjects.txt` definitions;
  other subject facts stay unknown and props/locations start empty. Old
  checkpoints receive an unknown-only WorldState with no legacy migration.
- There is no legacy-state-to-WorldState synchronization path. The only
  current WorldState construction/write paths are `world_state.new_world_state`,
  `world_state.empty_world_state`, `minimax.new_generation_state`,
  `minimax.load_generation_state` (legacy-key fallback),
  `minimax.save_generation_state` (legacy-key fallback),
  `minimax.record_completed_segment` (snapshot), and
  `minimax.restore_generation_state` (restore of that snapshot).
  `minimax.authoritative_world_state_seed_from_subject_definitions` only
  prepares the narrow authored-input seed; `world_state.copy_world_state`
  returns a validated independent copy. At the Gate A/B checkpoint, no
  Director, reducer, visual observer, beat summary, RAW parser, or legacy writer
  updated WorldState facts. Step 3 below adds a pure reducer core without a
  Director call site or legacy-state synchronization.

Legacy state writers still active and therefore still competing authorities for
their compatibility state:

- `normalize_structured_continuity_state` applies continuity-model values to
  legacy continuity; `request_combined_continuity` orchestrates that path.
- `merge_prompt_and_visual_end_state` still applies visual position, pose,
  camera, and environment observations to legacy continuity. Wardrobe is kept
  diagnostic and no longer promoted from visual observations.
- `apply_state_patch` and `apply_accepted_beat_state_patch` apply accepted-beat
  effects to legacy beat state; `_continuity_apply_authoritative_state_effects`
  applies scripted effects to legacy continuity and prop ledgers.
- `seed_initial_location_subjects`, `apply_visible_subject_bootstrap_metadata`,
  and `apply_authoritative_prop_state_effects` add or update legacy Subject and
  prop facts. `_run_main` orchestrates these paths and additional direct legacy
  assignments during segment processing.
- `merge_prop_ledger`, `merge_subject_state_ledger`,
  `record_completed_segment`, and generation-state load/restore/save still
  canonicalize or merge the legacy ledgers and snapshots.
- Wardrobe compatibility writers include `seed_story_wardrobe`,
  `seed_character_canon_wardrobe`, `seed_canonical_opening_wardrobe`,
  `apply_story_subject_wardrobes`, and `_repair_candidate_wardrobe_extraction`.
  These do not write WorldState.

These writers are intentionally not removed or redirected in this checkpoint.
Gate C must report them again after adding Director `state_actions` and reducer
validation; Gate D is where segment processing becomes transactional and legacy
writers begin to be replaced or disabled.

## 2026-10-06 — Step 3 reducer core

Implemented the pure WorldState reducer and unit tests. This is only the reducer
core: Director `state_actions` emission, prompt vocabulary injection, segment
transactions, and disabling/replacing legacy writers remain out of scope.

Public API in `world_state.py`:

- `reduce_world_state(world_state, state_actions, *, segment_number)` returns a
  `ReductionResult` containing ordered `ActionOutcome` records and a `committed`
  flag. Successful batches return the fully reduced candidate. On the first
  rejected action, processing stops and the result contains a deep copy of the
  original input with `committed=false`; earlier successful actions are rolled
  back and later actions are not evaluated.
- `validate_state_actions(world_state, state_actions, *, segment_number)` dry-
  runs that same engine and returns the same outcomes without exposing the
  candidate.
- `props_held_by(world_state, subject_id)` derives a subject's held-prop IDs
  from each prop's single `placement` field; no subject-held-props list is
  persisted.

Each `StateAction` has `action_id`, `op`, and only the operation-specific
registered fields. Supported operations and effects:

| Operation | State effect |
| --- | --- |
| `pickup` | Changes one movable prop from located to held by the actor. |
| `place` | Changes an actor-held movable prop to a location, optionally on an explicitly registered support. |
| `handoff` | Changes a movable prop's recorded holder from giver to receiver. |
| `pour` | Transfers a registered substance using `all` or `partial` coarse amounts. |
| `consume` | Consumes an explicitly consumable prop or content using `all` or `partial`. |
| `enter` / `exit` | Set presence to present / absent; exit may record a known destination. |
| `move` | Changes a present subject's registered location without changing presence; support clears unless supplied. |
| `set_support` | Sets or clears (`support_id: null`) a subject's explicit support and optionally its posture. |
| `change_clothing` | Puts on, removes, or replaces an exact recorded garment layer, or updates its separate condition. |
| `open` / `close` / `lock` / `unlock` | Changes a registered mechanism state when explicit capabilities and prior states permit it. |

Persistent props now carry one authoritative `placement`, `mobility` (`movable`,
`fixed`, or `unknown`), a kind (including `fixture`, `support`, and
`fixture_support`), coarse contents, explicit capabilities, and mechanism state.
Pickup rejects fixed and unknown-mobility props. Entity references must resolve
to IDs already present in the WorldState; arbitrary field-patch operations and
unknown entity IDs are rejected.

WorldState wardrobe slots (`upper`, `lower`, `footwear`, `other`) each hold
`unknown`, `N/A`, or a list of zero or more `{garment, condition}` records.
Garment identity and condition are separate; for example, a torn shirt remains
`garment: "shirt"` with `condition: "torn"`. `change_clothing` supports a
`set_condition` action for an exact recorded garment. Garments are not global
props. `clothing_applicability: "required"` does not require all four slots to
contain garments: empty lists and an `other: "N/A"` slot are valid when another
garment is recorded. A fully known required wardrobe with no garments is
rejected. The reducer also rejects removing the last recorded garment from a
required-clothing subject; it does not infer garment coverage or appropriateness
from slot names, so semantic clothing validation must check that separately.

The reducer proves only facts encoded in WorldState: registered identity,
presence, location equality, placement, mobility, capability, content, and
mechanism state. It does not infer proximity, reachability, route plausibility,
collision/fit, or whether a support is physically unoccupied. Within-location
movement cannot be represented because the current schema has no position
coordinate, so it is rejected as `movement_not_representable`. Physical staging
remains the semantic validator's responsibility. An `off_camera` action is not
defined; off-camera continuity produces no action.

WorldState mutation and compatibility status at this gate:

- `new_world_state` and `empty_world_state` construct seed states; neither
  imports legacy continuity, RAW, visual observations, or beat summaries.
- `reduce_world_state` and `validate_state_actions` call the shared reducer
  engine. The engine mutates only private deep copies while evaluating actions;
  the caller's input remains unchanged. `copy_world_state` returns a validated
  copy and `props_held_by` is read-only.
- `minimax.new_generation_state` assigns the authoritative identity seed.
  `load_generation_state` creates an unknown-only state for legacy checkpoints;
  `save_generation_state`, `record_completed_segment`, and
  `restore_generation_state` validate or copy WorldState snapshots. None of
  these paths applies legacy state facts to WorldState.
- All legacy continuity, visual, beat, wardrobe, Subject, and prop-ledger
  writers listed in Gate A/B remain active for compatibility state and have not
  been integrated with this reducer. No Director call site invokes the reducer.

Focused validation: `python -m pytest -q tests/test_world_state_foundation.py`.
The reducer tests cover atomic fail-fast rollback, dry-run agreement, fixed and
unknown mobility, placement and derived holders, support clearing, presence
semantics, coarse transfer amounts, layered garments and per-garment condition,
clothing applicability, mechanism prerequisites, and rejection of unregistered
IDs and generic patches. This did not run the full repository suite.

Focused validation: `tests/test_world_state_foundation.py`,
`tests/test_rendered_wardrobe_state.py`, `tests/test_subject_identity_continuity.py`,
`tests/test_location_state_reference.py`, `tests/test_postmortem_regressions.py`,
and the relevant `tests/test_continuity_summary.py` cases had 225 passing tests
and 12 passing subtests. Eleven existing tests were deselected: stale prompt or
retention contracts, unrelated timing/speaker-repair assertions, and a test that
tries to delete a ComfyUI output file outside the writable workspace. The whole
suite was not rerun at this gate.

## 2026-10-06 — Gate C phase 1: authority seeds and Director action contract

Implemented Gate C phase 1 only. This adds explicit one-way WorldState seed
functions, deterministic Python entity IDs, and a dry-run response contract.
The initial seed composition runs before Segment 1. Director `state_actions`
are not connected to the live Director call and are never written back to
`generation_state["world_state"]`. Gate D transactions have not started.

Authority-specific seed APIs in `world_state.py`:

- `seed_predefined_subject_identities(world_state, subject_definitions_seed)`
  accepts only the parsed authored Subject identity seed.
- `seed_story_start_presence(world_state, initial_location_subjects,
  location_id=...)` consumes the Subjects explicitly returned by the dedicated
  story-start extractor. Returned Subjects become present at the registered
  starting location; omitted Subjects are left unchanged, usually `unknown`.
  The extractor intentionally excludes Subjects already in existing
  definitions, so its omissions cannot establish absence. Extractor-discovered
  Subjects receive stable Python IDs and unknown identity fields. Later `enter`
  actions remain the state transition for an arriving Subject.
- `seed_canonical_wardrobes(world_state, wardrobes_by_subject)` consumes only
  dedicated per-Subject wardrobe-extractor output. `minimax.py` adapts the
  canonical text deterministically into slot arrays of `{garment, condition}`
  records. Unstated garment conditions are `unknown`; explicit condition words
  remain separate from garment identity. `N/A` remains `N/A` for non-humanoid
  wardrobes. No additional model call is made for this conversion.
- `seed_canonical_static_location_state(world_state, location_state)` consumes
  the established location-state pipeline. Anchors are registered as fixed
  fixtures by default. Objects enter WorldState only when explicitly marked
  `world_state_role` as `fixture`, `support`, or `fixture_support`; `untracked`
  objects are omitted. The location extractor now labels role and mobility and
  does not supply IDs.
- `register_explicit_persistent_props(world_state, prop_registry)` requires a
  Python-authored entry with `needed_for_state: true`, a reason, mobility,
  kind, and exactly one initial location or Subject holder. It rejects
  caller-supplied IDs and unneeded props. This is an explicit registration API;
  there is no automatic noun/story-prop sweep.

`stable_world_state_id(namespace, label, scope="")` normalizes authoritative
labels and derives IDs from a stable SHA-256 digest. Location IDs derive from
the canonical location name. Fixture/support IDs include location, role, name,
and type. Registered prop IDs include the authoritative prop identity and
initial placement scope. Subject IDs use authored Subject numbers where
available, and extractor-discovered story-start Subjects use a deterministic
normalized-name ID. These IDs are supplied in the Director vocabulary; the
model cannot create IDs.

The proposed Director response uses one response containing both RAW and
actions:

```json
{
  "raw_scene": "...",
  "finite_activity_complete": true,
  "named_beneficiaries_complete": true,
  "activity_tools_settled": true,
  "beat_complete": true,
  "state_actions": []
}
```

`build_director_state_action_contract(world_state)` creates the constrained
JSON schema and the exact registered vocabulary supplied alongside it:

- `subjects`: `{id, name, presence, location_id}`
- `locations`: `{id, name}`
- `props`: `{id, name, kind, mobility, status, placement, contents,
  capabilities, mechanism_state}`
- `supports`: `{id, name, location_id}` for registered `support` and
  `fixture_support` props

Every action ID field is constrained to the matching IDs in that vocabulary.
The available operations follow the existing reducer contract (`pickup`,
`place`, `handoff`, `pour`, `consume`, `enter`, `exit`, `move`, `set_support`,
`change_clothing`, `open`, `close`, `lock`, `unlock`). `parse_and_dry_run_director_state_actions`
parses the same-response envelope and calls `validate_state_actions`, which
dry-runs the shared reducer engine. It returns diagnostics and acceptance only;
it does not expose or persist a candidate state. The live Director response
format and generation call are unchanged.

Gate C phase 1 tests cover story-start Goblin presence without an entrance,
Elf/Dragon unknown until an entrance action, preservation of explicitly seeded
absence on omitted Subjects, canonical layered wardrobe adaptation,
non-humanoid `N/A`, stable fixture/support IDs, one-placement explicit prop
registration, exclusion of legacy/visual/RAW/accepted-beat data, and rejection
of an unregistered Director ID. Focused validation:
`python -m pytest -q tests/test_world_state_foundation.py tests/test_location_state_reference.py` — 65 passed.

WorldState writers now include the explicit seed APIs above, existing
construction/checkpoint APIs (`new_world_state`, `empty_world_state`,
`minimax.new_generation_state`, load/save/restore/snapshot), and the approved
reducer APIs (`reduce_world_state`, `validate_state_actions`). The contract
builder and dry-run parser do not write WorldState. The startup composition
assigns the result of authorized seed functions before Segment 1. No
legacy-state-to-WorldState synchronization exists.

The competing legacy writers remain active and compatibility-only:

- `normalize_structured_continuity_state`, `request_combined_continuity`,
  `merge_prompt_and_visual_end_state`, `apply_state_patch`,
  `apply_accepted_beat_state_patch`, and
  `_continuity_apply_authoritative_state_effects`.
- `seed_initial_location_subjects`, `apply_visible_subject_bootstrap_metadata`,
  `apply_authoritative_prop_state_effects`, `_run_main` legacy assignments,
  `merge_prop_ledger`, `merge_subject_state_ledger`, and
  `record_completed_segment`.
- Wardrobe compatibility writers `seed_story_wardrobe`,
  `seed_character_canon_wardrobe`, `seed_canonical_opening_wardrobe`,
  `apply_story_subject_wardrobes`, and `_repair_candidate_wardrobe_extraction`.

None of these writers updates WorldState. At the Gate C phase 2 checkpoint,
these compatibility writers remain active; connecting the reducer candidate
to canonical segment state and changing legacy writers remains for the next
approved phase.

## 2026-10-06 — Gate C phase 2: Director action contract and dry-run

Director Request 1 now receives a compact registered WorldState vocabulary and
returns `state_actions` in its existing response with `raw_scene` and the four
completion fields. No second LLM call was added. The contract includes only
registered Subjects referenced by the current beat/source, their current
locations/supports and held props, plus registered props and locations
referenced by that Segment. Action operations are limited to those signaled by
the current beat/source. IDs in the strict dynamic response schema are enums
from this Python-built vocabulary.

The exact Request 1 user-message addition is:

```text
REGISTERED WORLDSTATE VOCABULARY — Python-assigned IDs; select only IDs shown here:
{minified JSON vocabulary}

STATE ACTION CONTRACT — Return state_actions in this same response as RAW SCENE. Add only explicit persistent changes staged in RAW SCENE; off-camera is not an action. Use [] if no represented state changes. The response schema restricts operations and IDs to the registered vocabulary.
```

The system prompt also states that actions must correspond to explicit changes
staged in RAW SCENE, IDs must come from Python, off-camera is not an action,
and an empty array is correct when no represented persistent state changes.
The same-response object is:

```json
{
  "raw_scene": "...",
  "finite_activity_complete": true,
  "named_beneficiaries_complete": true,
  "activity_tools_settled": true,
  "beat_complete": true,
  "state_actions": []
}
```

`request_segment_llm()` deep-copies the opening WorldState once and parses and
dry-runs each response with `parse_and_dry_run_director_state_actions()` and
`validate_state_actions()`. A rejected batch retries from the same immutable
opening state with only the first concrete reducer diagnostic. This retry is
rebuilt from the base Request 1 messages, so failures from earlier physical,
prop, timing, or reducer attempts do not accumulate. A passing dry-run is
attached to the Request 1 result for downstream inspection; its candidate is
not assigned to `generation_state["world_state"]`. Existing RAW physical,
prop-state, and timing validators still run afterward and retain their
semantic staging role. No legacy writers are disabled or redirected, and Gate
D transactions have not started.

Focused regressions cover a valid Goblin mug transfer, duplicate pickup and
unknown prop IDs, a handoff whose giver is not the holder, and a reducer retry
that includes only the first reducer error without stale prior-attempt text.
The dynamic schema and prompt vocabulary are also checked in the Request 1
path. Legacy compatibility writers listed in the phase 1 report remain active;
they are still the competing state writers to audit before Gate D.

## 2026-10-06 — Gate C phase 2 vocabulary and pre-Director seeding corrections

Corrected three problems before Gate D. No Director candidate is committed to
canonical WorldState, no legacy writer is disabled, and no full tavern render
was run.

- Removed `director_state_action_operations_for_segment()` and its beat/source
  regex gating. `build_director_state_action_contract()` now includes every
  reducer operation for which the registered entity categories can form a
  schema. Verb wording never removes an operation; the reducer decides whether
  an emitted action is legal.
- Added `extract_persistent_prop_registry()` as a small semantic extractor over
  authored story, numbered beats, validated structured event effects, and
  canonical location state. It selects only explicitly placed cross-beat props,
  not every noun and not legacy ledgers, accepted-beat summaries, RAW, or visual
  observations. IDs remain Python-assigned. Prop registration now happens at
  the prop's first relevant beat, after that beat's dynamic Subjects are
  registered. This supports a cup whose explicit pre-handoff holder is Elf1.
- Added `extract_current_segment_subjects()` and
  `prepare_segment_world_state_for_director()`. Before Request 1, the narrow
  current-beat extractor registers new identity-only Subjects, the existing
  per-Subject canonical wardrobe extractor fills their layered wardrobe, and
  eligible persistent props are registered. These functions do not infer
  presence. Elf1 and Dragon1 remain `unknown` until an `enter` action. The
  post-RAW visible-Subject resolver remains a fallback for unanticipated
  foreground identities; those identities cannot join the current action plan
  until they pass the controlled registration path.
- The current-beat extractor uses exact source evidence, explicit `physical_form`
  values, and Python stable IDs. It never infers body type from a name. The prop
  extractor requires at least two relevant beats and an explicit pre-action
  placement; for a handoff, the source names the giver as the prior holder.
- Added tavern-sequence regressions that derive Amy/Goblin1 from authored and
  story-start authorities and derive mug/barrel/chalice/cup from the prop
  extractor response. They do not manually pre-seed Elf1, Dragon1, or the mug.
  Segments 1, 3, and 4 assert the pre-Request-1 vocabulary; Segment 4's cup is
  registered as held by Elf1, and the full 14-operation contract is unchanged
  for “refills,” “handing,” “locking,” “steps outside,” and “slides onto.”

Focused validation: `python -m py_compile minimax.py world_state.py
tests/test_director_retry.py`; the five focused tavern/operation/Request-1
regressions passed, and `tests/test_world_state_foundation.py` passed 40 tests.
The combined `tests/test_director_retry.py tests/test_world_state_foundation.py`
run had 137 passing tests and 14 failures in unchanged prompt-template, timing,
and RAW-resolver assertions outside this change; those failures remain
to be triaged separately. No full render was run.

The active compatibility writers remain the legacy list recorded above. New
WorldState writes are still limited to explicit seed APIs, the pre-Director
identity/wardrobe/prop seed functions, and checkpoint/snapshot plumbing. The
reducer candidate remains dry-run-only at this checkpoint.

### Test-suite maintenance and current status

Use pytest from the repository root; some external-service modules use
pytest-level skips and do not work correctly under `unittest discover`.
Removed the legacy macro-arc mock tests that hang against the current
source-span planner, the full-entrypoint test that does not terminate against
the current generation pipeline, and two prop-staging tests for an API that no
longer exists. Updated stale prompt assertions and the continuity-scheduling
mocks for separate soundscape/music requests. Focused tavern regressions and
the postmortem, location-reference, and macro-state modules pass.

The latest whole-suite pytest run completed in 43.44 seconds: **934 passed,
438 skipped, 88 failed**. Remaining failures span stale prompt/call-contract
expectations and unresolved continuity/state/render scheduling tests. Do not
delete these wholesale: update stale fixtures/assertions against current APIs,
and investigate failures that may expose production defects before claiming a
green suite.

## 2026-10-03 handoff — native Guide overlap replaces append Ref2V

Implemented on `summary-to-story-test`:

- append uses the exact final 22 rendered frames as native
  `MiniMaxH3AddGuide` conditioning at frame 0;
- prior video/audio are disconnected from append Ref2V, which now carries
  persistent Picture references only;
- final H3 continuation text no longer claims a nonexistent preceding
  `<Video 1>` reference;
- raw append duration includes the duplicate guide head, then Python removes 20
  frames and the existing stitch removes the remaining 2;
- Director has a ~0.92-second airlock before CURRENT BEAT begins;
- coherence checks now cover final-frame participant omission and moving an
  occupied chair/stool/seat.

No custom node package is required. Local ComfyUI must include the native
`MiniMaxH3AddGuide` node; otherwise queueing fails with an update-ComfyUI
message.

Next acceptance target: rerun the tavern torture test, especially Segment 2→3
and 4→5, verify Griffin1 survives Segment 4's final-frame state, and compare
camera continuity/runtime against the Ref2V-tail experiments.


## 2026-10-03 handoff — latest native-Guide postmortem

Active branch is `h3-add-guidance-test`. The latest 48-second tavern render showed good
visual continuation into Segments 2 and 3, an audio discontinuity into Segment 2, and hard
visual cuts at the exact Segment 4 and 5 joins. The cuts matched a prompt conflict: the
hidden 22-frame Guide carried the real close composition, while the continuation 00:00
RAW line reconstructed all semantic-state Subjects into a different composition.

Implemented next test:
- Add Guide receives the aligned previous audio tail plus audio VAE as well as the 22 video frames;
- continuation frame 0 is deterministically rewritten to a generic Guide-authority anchor,
  so prompt-derived PREVIOUS SHOT END cannot force off-camera Subjects into the opening frame;
- Guide length remains 22 frames.

Next acceptance: rerun the same tavern torture test and inspect 1→2 audio plus 3→4 and
4→5 visual/camera seams. If hard cuts remain after the prompt conflict is removed, the
next architectural candidate is a preserved/masked AV overlap rather than adding more
Director wording or immediately increasing reference length.


## 2026-10-03 handoff — Director timing regression fixed

The Guide test initially stalled on Segment 2 because Request 1 was being asked to write a
synthetic 8.91667-second timeline. The local 20B model began emitting malformed timestamps
(`01:00.000`, `02:500.000`, etc.) and missing the End continuity state.

Fix: Director is back to a normal delivered-duration timeline. For continuation segments,
Python now shifts every nonzero accepted timestamp by the 22-frame Guide duration and then
replaces frame 0 with the Guide-authority anchor. Hidden Guide timing is no longer exposed
to Request 1. Audio+video Guide conditioning from the prior commit remains enabled.

Next action: rerun the same 48-second tavern test from Segment 1. Acceptance remains 1→2
audio continuity and 3→4 / 4→5 visual seams.

Follow-up: post-shift pronoun/timestamp validation now uses the raw H3 prompt duration (delivered duration + Guide offset), while Request 1 structure validation remains on delivered duration only.


## 2026-10-04 handoff — location-state-test

Created branch `location-state-test` from main commit
`40f4727030507e116c1631367a80ba0711ca000e`.

Goal: test whether one persistent three-second character-free panoramic location reference
prevents H3 from rewriting off-camera environment (for example shelves becoming a torch)
while preserving the validated seamless 22-frame AddGuide seam.

Implementation:
- extract static setting facts from expanded_story.txt with a narrow temperature-0 call;
- fallback to overall_location when the story does not specify detail;
- render one 3-second wide orbital environment clip before Segment 1, with all Picture
  references disconnected;
- save/checkpoint the location-reference path;
- pass it as Ref2V Video 1 to initial and append segments, visual-only/no reference audio;
- keep append AddGuide on its own loader and unchanged;
- clean refresh receives four sampled frames from the same location clip through ref_images;
- final H3 prompt explicitly says the location reference owns static spatial layout only,
  never characters or current camera framing.

Next acceptance should focus only on background geometry/fixtures when the camera reveals an
area that was previously off-screen. Do not evaluate character persistence as part of this
test.

Refinement after diff review: the setting extractor now explicitly excludes furniture/props
that appear only because a later story action uses or introduces them. This keeps the
location reference honest: a vague "medieval tavern" is mostly designed by H3, then the
experiment tests whether that invented room persists off camera instead of pre-seeding
future beat objects into the panorama.


## 2026-10-03 fix — refresh loader ambiguity exposed by location reference

Segment 6 clean refresh failed before queueing with
`WorkflowConfigurationError: ... contains multiple nodes named 'Load Video'`.

Root cause: refresh still used the legacy logical name `"Load Video"`. The exported
refresh workflow's actual previous-segment loader is titled
`Load Video (Path) 🎥🅥🅗🅢`, so node lookup previously succeeded only through the
fallback that selected the sole `VHS_LoadVideoPath` node. The location-state experiment
adds a second `VHS_LoadVideoPath` node for the persistent location clip, making that
fallback ambiguous.

Fix: `REFRESH_LOAD_VIDEO_NODE_NAME` now aliases the workflow's exact
`LOAD_VIDEO_NODE_NAME` title. The persistent location loader keeps its separate
`Location Reference Video` title. Added a regression proving the refresh prior-video
loader remains uniquely resolvable after a location-reference loader is added.

Next acceptance: rerun/resume through the next clean refresh and verify Segment 6 renders;
then evaluate the location-reference experiment on background geometry/fixtures as planned.


## 2026-10-04 handoff — tavern location-reference acceptance and prompt/state fixes

Latest 48-second tavern run established a useful split:

- the persistent 3-second location-reference video is successful for environment
  continuity; Segments 1-5 matched the covered room geometry extremely closely,
  with invention limited mainly to the slice the orbit did not show reliably;
- remaining failures were primarily prompt/state problems: ambiguous physical
  prose, indirect speech conflicting with the no-dialogue constraint, spatially
  impossible staging, dynamic Subject registration lag, and a Segment 6 clean
  refresh discontinuity.

Fixes now on `location-state-test`:

- CLI/default automatic refresh is `999`, matching desktop/web defaults;
- legacy GUI settings are migrated once: an old saved default `refresh: 6` becomes `999` and old default story temperature `0.8` becomes `0.4`; later explicit user choices are preserved;
- an explicit refresh interval is authoritative and no longer loses to
  source-span chapter-boundary refresh scheduling; `None` retains the legacy
  source-span fallback for programmatic callers;
- story-expansion default temperature is 0.4 and its prompt asks for film-ready,
  literal, physically unambiguous prose rather than literary ambiguity;
- an explicit Beat speech act (asks/orders/says/etc.) must become direct
  `<d>...</d>` dialogue in RAW; after same-segment Subject registration the
  final H3 identity repair emits the stable form such as
  `Goblin1 (S3) said <d>Give me a pint.</d>`;
- Director/RAW coherence now explicitly rejects hidden spatial teleportation such
  as serving a distant bar/table while still established at the door;
- post-RAW Subject resolution gets two attempts and is no longer allowed to fail
  open. Every resolved dynamic Subject must be registered before that segment's
  H3 prompt is assembled;
- Subject-resolver responses are now retained in prompt history for diagnosis;
- guided append postprocessing removes all 22 native Guide overlap frames and
  guided clips receive no additional two-frame stitch trim.

Next acceptance: rerun the tavern test as a new run with the revised humanoid-
creature story. Verify Segment 6 stays on normal Guide continuation (not
clean-refresh), new creatures are registered in the segment where they first
appear, explicit speech is tagged, and door/bar movement is physically staged.
Do not change the accepted location-reference architecture before this rerun.


### 2026-10-04 — provenance fixes after second tavern acceptance

The second tavern run kept room/location continuity strong but exposed four
specific upstream failures:

- reference-video audio could still be heard even though Ref2V audio inputs were
  disconnected and the location prompt requested N/A audio;
- a new goblin could "appear" in a chair without a physical entrance/reveal;
- held/container props could silently change identity (bucket -> mug,
  mug -> glass/chalice);
- an established actor could interact with a distant object without explicit
  travel (Amy at barrel -> crystal shelf/bar).

Current fixes:

- every rendered location-reference video is now atomically remuxed with ffmpeg
  using video stream-copy plus `-an`; the file used by all later conditioning
  therefore contains no audio stream regardless of what H3 generated;
- Director generation and RAW coherence validation both require visible
  provenance for a newly introduced foreground Subject: explicit physical entry
  through a route/boundary or explicit continuous camera motion revealing an
  already-present offscreen Subject; "appears" alone is insufficient;
- Director/validator preserve prop identity and acquisition provenance. A prop
  cannot silently become another prop, newly handled props need a stated source
  and acquisition action unless already established, and every transfer keeps
  an explicit, distinct, traceable source and destination;
- spatial travel validation is generalized: interaction with any different
  established position requires explicit actor movement there first. This is no
  longer a door/bar-specific rule.

These are prompt + low-temperature semantic-validator contracts, not
tavern-specific deterministic rewrites. The ffmpeg audio removal is the only
deterministic media transformation in this change.


### 2026-10-04 — setting-label and RAW pacing follow-up

Latest tavern acceptance was substantially improved but exposed two prompt-level
issues plus one renderer/location conflict:

- Segment 3 compressed prop acquisition and use into one late timestamp, making
  the cup visually appear in Amy's hand even though RAW named a shelf origin.
- Segment 4 invented a lid and immediately sealed the cup, again compressing an
  invented prerequisite/action chain.
- The persistent setting text called the only visible entrance a `back door`,
  while the location-reference video established a single door; this may have
  encouraged H3 to reinterpret the doorway geometry when the dragon entered.

Implemented on `location-state-test`:

- setting extraction no longer treats relative action labels
  (front/back/side, left/right) as proof of distinct static architecture; a
  single established instance is described generically;
- RAW Director now explicitly gives physical prerequisites their own earlier
  timed micro-beat instead of combining prerequisite + dependent action at one
  timestamp;
- RAW Director has a dedicated `DIRECTOR_RAW_SCENE_LLM_SETTINGS` profile at
  temperature `0.2` with high reasoning/random seed; other creative generation
  remains at `0.8`;
- focused regressions cover the setting, pacing, transfer, and sampling contracts.

Follow-up after the next tavern run:
- the room geometry remained stable, so the location-reference architecture is
  accepted for this test;
- prompt-only pacing was not enough: Segment 3 compressed doorway-to-back-table
  travel into about 1.5 seconds and H3 hid the missing travel with a cut; Segment
  4 similarly omitted the dragon's route from the doorway to the bar stool;
- a new narrow temperature-0 timing-feasibility validator now checks only whether
  consecutive physical transitions can visibly fit between their timestamps,
  with no hardcoded minimum duration;
- RAW transfer wording is now generic and requires an explicit, distinct source
  and destination plus source provenance for what is transferred;
- RAW invention is now explicitly economical: useful staging is still allowed,
  but optional secondary reactions/consequences and extra object/substance motion
  should not be added once the Beat action is already readable.

Next acceptance: rerun the same tavern story/Beats and inspect Segment 3/4 travel,
Segment 4 transfer behavior, and Segment 5 reaction/fluid choreography.


### 2026-10-04 — spatial acceptance; movable-prop bookkeeping is next

The newest tavern render no longer showed the prior spatial/teleportation failures. Treat
the location-reference + travel/timing architecture as provisionally accepted. The visible
remaining failures were ordinary props: glasses and the basket could still appear or
disappear.

Implemented on `location-state-test`:

- generation state now carries a separate persistent movable-prop ledger with stable IDs;
- the existing combined-continuity call maintains that ledger while H3 renders, so there
  is no additional always-on LLM request;
- ledger records track kind, owner, holder, location, contents, and
  present/lost/destroyed status and copy unchanged props forward while offscreen;
- source-authorized typed item state remains higher authority: held/equipped/stored/
  dropped/lost effects deterministically update the matching ledger record, so the new
  movable-prop ledger does not compete with existing canonical inventory truth;
- Request 1 receives the ledger as authoritative movable-prop state;
- strong prop-interaction Beats may trigger one tiny pre-RAW temperature-0 staging call;
  it returns either nothing or one minimal staging sentence when a required prop is not
  currently available;
- this is proactive repair before RAW generation, not a validator-driven
  generate/reject/regenerate loop;
- checkpoint/resume state and Director prefetch fingerprints include the prop ledger;
- focused regressions cover copy-forward/update, schema acceptance, conditional staging,
  test-mock routing, and resume slicing.

Next acceptance: reuse the tavern story/Beats and inspect mug/glass/basket identity,
location/possession, transfer contents, and whether the pre-RAW staging call fires only when
needed. No spatial/location changes should be made unless that regression reappears.

### 2026-10-04 — prop persistence accepted; Segment 2→3 ownership/state fix

Latest tavern acceptance materially improved movable-object continuity:

- the prior appearing/disappearing glasses and basket were gone;
- fluid/container behavior was acceptable overall;
- location geometry and earlier spatial/travel fixes remained stable.

The remaining Segment 3 failure was not renderer-only. Logs showed two upstream causes:

1. Segment 2's final timed action still had Goblin1 present, putting his mug on the counter
   and stepping back toward the hearth, but the End continuity state omitted Goblin1.
   Combined continuity therefore preserved the Subject identity but lost his position.
2. The prop ledger correctly tracked `mug_1` as owned by Goblin1 and sitting on the
   counter, but Segment 3 Director repurposed that mug as the source for Elf1's drink.

Implemented on `location-state-test`:

- post-RAW Subject resolution is followed by deterministic final-participant carry-forward:
  if a stable named Subject is present in the final timed micro-action but omitted by End
  continuity state, Python copies that exact final-action evidence into End state;
- explicit leave/exit/fully-occluded final actions are excluded from carry-forward;
- this adds no LLM call and does not alter the H3 timed action itself; it repairs semantic
  bookkeeping used by the next segment;
- Director now treats ledger `owner` / `holder` as exclusive continuity facts rather
  than generic inventory;
- the existing conditional prop pre-staging micro-call treats a matching prop owned/held
  by another Subject as unavailable unless CURRENT BEAT explicitly authorizes taking,
  reuse, or transfer, and should stage a distinct ordinary instance instead;
- Request 1 receives the same ownership rule in the injected prop-state block.

Focused regressions were added for omitted final Subjects, explicit exits, newly resolved
Subjects before registry append, and owned-prop prompt policy.

Next acceptance: rerun the same tavern case. Segment 2→3 is the key checkpoint:
Goblin1 should retain his semantic position near the hearth, should not drift into Elf1's
seat, and `mug_1` should remain Goblin1's instead of being reused to serve Elf1.

### 2026-10-04 — generated current-clothing Picture references

The tavern acceptance showed that Amy's correct rendered wardrobe survived only Segment 1;
later segments fell back toward the clothing in her original identity Picture. A separate
current-clothing visual authority is now implemented on `location-state-test`.

Implementation:

- when a visible character has no generated clothing reference yet, or the character's
  canonical current wardrobe changes, Python renders an isolated 1-second H3 character
  reference using the same base render path as the location reference;
- the character is front-facing in a neutral pose with the current outfit visible; there is
  no 360 orbit, camera move, cut, or story action;
- Python samples the 0.5-second frame and places that PNG in the ComfyUI input directory;
- the generated Picture is added to H3 subject definitions as clothing-only authority, e.g.
  `<Picture 2> references only the clothing that Amy is currently wearing.`;
- Picture numbering is dense and positional. Empty template `LoadImage` nodes do not
  reserve Picture numbers: if only Picture 1 is active, the first generated reference is
  Picture 2;
- Pictures 1-6 reuse the existing template LoadImage nodes when available. Once all active
  positions through 6 are occupied, Python dynamically creates `LoadImage` nodes for
  Picture 7, Picture 8, and so on; six is not a hard maximum;
- each character keeps the same generated Picture number after assignment. A later wardrobe
  change creates a versioned replacement PNG for that Picture instead of shifting every
  later Picture number;
- generated reference metadata is checkpointed and stored with each finalized H3 prompt so
  resume and saved-prompt rendering retain the exact image version used by that segment;
- no extra LLM call is added. The trigger/description comes from the existing canonical
  Subject/wardrobe state.

Focused regressions assert the dense Picture-2 case, stable numbering across an outfit
change, dynamic creation above Picture 6, clothing-only definition filtering, and the
front-facing one-second/no-orbit prompt contract.

Next acceptance: rerun the tavern story. Amy should use Picture 1 for identity and the new
generated Picture for her current clothing, so the post-Segment-1 renders should stop
reverting to the outfit in the original identity reference.

### 2026-10-04 — state media directory consolidation

All generated visual-state media now uses one persistent directory:
`<ComfyUI output>/video/state/`.

- location-reference video prefix moved from `video/location_state/location_reference`
  to `video/state/location_reference`;
- character-reference 1-second videos moved from `video/character_state/` to
  `video/state/`;
- sampled character-reference PNGs are now written persistently to the same
  `output/video/state/` directory instead of being authored in ComfyUI/input;
- because ComfyUI `LoadImage` reads from its input directory, Python stages a copy of the
  authoritative state PNG into ComfyUI/input only when preparing a workflow. The persisted
  checkpoint path points to the state-directory original.

The old `location_state` and `character_state` output prefixes are no longer used by new
renders.

### 2026-10-04 — outfit-reference identity conditioning

Production test showed that the generated clothing Picture could bleed its newly invented
face/body back into Amy's appearance. The isolated 1-second clothing render now conditions
on the target character's existing source Picture when available.

- the target Subject's original `picture_id` is resolved to its configured LoadImage;
- that source image is connected as the only Picture in the isolated outfit-reference
  workflow, so it is locally `<Picture 1>`;
- the outfit-reference prompt explicitly states that Picture 1 owns only identity/physical
  appearance (face, hair, age, build, species, body), while current clothing text owns the
  outfit and must not be copied from the identity Picture;
- the resulting sampled Picture remains clothing-only authority in the final story prompt;
- video-only/dynamic Subjects with no source Picture currently fall back to unconditioned
  outfit-reference generation and log a warning.

A possible future alternative—standalone reusable outfit assets that can be applied to
multiple characters—is documented in `docs/FUTURE_NOTES.md`.

### 2026-10-04 — clothing-reference persistence + portrait reference canvas

Two production fixes are now active on `location-state-test`:

- Person/outfit reference renders use a portrait 13:19 canvas. Python computes width/height
  from the requested megapixel budget and writes those dimensions directly into the isolated
  character-reference conditioner. The 3-second location orbit keeps the normal landscape
  workflow unchanged.
- Generated clothing Pictures no longer regenerate because the vision observer describes
  the rendered wardrobe differently. Each clothing Picture persists its intended wardrobe
  and condition. A new version is authorized only when the immediately preceding segment
  explicitly changes/removes/adds clothing or explicitly damages/soils/wets/burns it.
- Authorized changes are applied to the prior intended clothing-reference state, not to
  vision-observed wardrobe, preventing renderer drift from becoming canonical.

### 2026-10-04 — newest tavern postmortem: dynamic identity, transfer semantics, fixed fixtures

Newest production evidence separated four visible symptoms into three upstream causes:

1. Segment 2's extra plate was actually RAW's invented `small wooden tray`; the apparent
   extra cup is consistent with H3 compensating for RAW telling Amy to tilt a barrel as if
   it were a handheld pouring vessel.
2. Segment 4's generated Dragon1 state Picture existed before the render, but final H3
   labeled it clothing-only while the Subject definition said only `Dragon1 is a dragon`.
   H3 therefore had no Picture-owned dragon identity on first appearance. RAW also
   explicitly misdirected the brew onto Dragon1's scales instead of filling the cup.
3. Segment 5 used source-less liquid on Dragon1's tongue because the prior End continuity
   omitted the just-handed crystal cup, so the prop ledger did not carry that drink source
   forward. Segment 6 then conflicted with location authority by moving an established
   hanging lantern onto a table.

Implemented:

- dynamic Subjects with no external Picture now promote their generated state Picture to
  identity + current-appearance authority; source-backed characters retain the separate
  identity-Picture + clothing-Picture model;
- later outfit changes for dynamic Subjects reuse the previous generated Picture as identity
  conditioning;
- first unconditioned dynamic-reference generation no longer mentions nonexistent
  `<Picture 1>`;
- RAW generation/validation preserves the Beat's transfer destination/recipient/container,
  binds drinks/material to a real established source, and rejects final End states that drop
  a just-transferred/materially changed prop;
- RAW avoids unnecessary helper supports/containers/utensils used only to settle props;
- the existing extracted static-setting sentence is now supplied to Request 1 and coherence
  validation, preventing RAW from relocating explicit fixed fixtures before final H3
  location-reference injection.

Next production acceptance: rerun the same tavern case. Check Segment 2 for direct,
provenanced barrel -> Goblin1 mug transfer without a surprise helper prop; Segment 4 must
use the generated Dragon1 identity on its first appearance and fill/hand over the crystal
cup rather than pour onto the dragon; Segment 5 must sip from that carried cup; Segment 6
must preserve the established lantern placement and Elf1's table. Do not chase the apparent
overall quality degradation yet: this analyzed run predates the 13:19 character-reference
and clothing-reference persistence fixes.

### 2026-10-04 — 16GB split-mode reference assets fixed

The 16GB path was audited after noticing that versioned/torn-clothing references cannot be
created during the LLM-only phase. The issue was real: prompt-only mode skipped ComfyUI,
therefore it also skipped location-reference and dynamic character/clothing-reference
creation, while render-only mode assumed those files already existed.

Current behavior:

- `generated_prompts.txt` now contains ordered `reference_jobs` in addition to segment
  prompts;
- location and character reference jobs freeze all generation inputs needed by ComfyUI;
- character outputs are immutable/versioned PNGs, with a run token in prompt-only mode;
- a later dynamic-character clothing state references the prior generated Picture as its
  identity dependency instead of overwriting it;
- each segment retains the exact reference-version metadata that was current when its H3
  prompt was finalized;
- the render-only phase generates all saved references first in dependency order, then
  renders the saved segments in order;
- prompt-only H3 text receives the same persistent-location authority clause as normal mode.

Acceptance target: run the desktop 16GB flow end-to-end with at least one dynamic character
and one explicit clothing-condition change, inspect `generated_prompts.txt` before starting
ComfyUI, then verify v001 and v002 both remain under `output/video/state` and the appropriate
segment uses each version.

### 2026-10-04 — sliding dynamic-Subject references + per-segment Picture map

Implemented the requested conservative dynamic-reference lifecycle:

- persistent Subject/reference records are never deleted or renumbered;
- each segment gets a frozen `reference_bindings` map that records both the persistent
  canonical Picture number and the segment-local Picture number;
- H3 Subject definitions and ComfyUI reference wiring use the same segment-local generated
  reference map;
- a Subject remains retained for `ceil(total_segments / 2)` segments since its last
  explicit visual appearance, so a potentially passive/background Subject is not dropped
  immediately;
- after expiry, its Subject definition and configured/generated reference conditioning are
  removed only for the current segment; a later explicit re-entry restores the same
  persistent identity/reference version;
- `--disable-subject-removal` (also exposed in the desktop UI) keeps every previously seen
  Subject bound indefinitely;
- `generation_state.json` keeps the full tracking/binding history, and each completed
  segment plus `generated_prompts.txt` freezes the exact map/exclusions needed for 16GB
  replay.

Production acceptance: use a run with several dynamic Subjects entering/leaving. Verify an
inactive Subject remains bound through the sliding window, ages out at the threshold, its
configured/generated Picture is disconnected, another generated Subject can pack into the
vacated dynamic slot, and later re-entry restores the original identity asset even if the
H3 Picture number differs from its earlier segment.


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


### 2026-10-05 — RAW validator split

The former combined RAW coherence validator is now split for the local ~20B runtime:

- `director_raw_scene_physical` checks subject movement/spatial continuity, entry/reveal,
  travel between established positions, barriers/seats/supports, fixed architecture, and
  final subject/barrier state.
- `director_raw_scene_prop_state` checks prop identity/provenance, ledger holder/owner/contents,
  source/destination transfers, CURRENT BEAT object/recipient/container/result fidelity,
  material sources, and final prop state.
- `director_raw_scene_timing` remains a third independent check.

Request 1 now evaluates physical/spatial -> prop/state -> timing, with a category-specific
retry message for each failure. Compatibility wrappers remain for old callers, but production
runtime no longer asks one large coherence prompt to reason about every domain at once.
The RAW Director prompt itself was intentionally left alone because it is being revised separately.


### 2026-10-05 — continuation Picture authority fix

Generated character references were being lost at the final H3 render boundary because
blank configured Picture slots were pruned before generated refs were attached. Their slot
numbers were then replaced in prompt text with "the supplied opening guide," even though a
generated character Picture would occupy that same segment-local number.

Current behavior:

- generated segment-local Picture IDs are protected from configured-slot exclusion and
  canonical remapping in append/refresh prompt conditioning;
- explicit generated `<Picture N>` identity/clothing authority survives into the actual H3
  prompt;
- the opening guide anchors only frame-0 pose/position/physical state for visible Subjects;
- Picture-definition lines no longer receive duplicated opening-guide state language.

Focused tests passed for generated-Picture preservation and non-duplication of guide authority.


### 2026-10-05 — dynamic reference identity descriptions + species-neutral reference portraits

The latest tavern acceptance confirmed that generated character Pictures now reach H3
correctly, but exposed an upstream identity-flattening bug for newly resolved dynamic
Subjects. RAW retained useful explicit appearance facts (for example a female silver-haired
elf and a humanoid dragon with obsidian scales/wings/amber eyes), while Python registered
only the functional fallback `Elf1 is an elf.` / `Dragon1 is a dragon.`. The first
generated identity Picture therefore had too little authority and could contradict the Beat.

Current fix on `location-state-test`:

- the existing post-RAW Subject-resolution call now also returns one concise
  `subject_descriptions` entry for each newly named dynamic Subject;
- those descriptions may use only explicit visual identity facts already present in RAW
  (species/type, sex/gender wording, age, hair, skin/scales/fur, build, anatomy/body, and
  distinguishing features), excluding action, pose, location, props, camera, mood, and
  invented details;
- Python persists that description as the dynamic Subject's canonical description during
  registration instead of falling back to species-only text;
- canonical source-character descriptions still override resolver descriptions for planned
  named characters;
- the resolver API remains backward compatible for older tests/callers, while production
  requests the new description map;
- the isolated one-second character-reference prompt is now species-neutral: it asks for a
  single subject's complete physical appearance and species/anatomy traits, and only shows
  clothing/accessories when explicitly described. It no longer assumes every Subject is a
  clothed humanoid.

Focused tests cover returned dynamic identity descriptions and the species-neutral
character-reference prompt contract.

Next acceptance: rerun the same tavern case and inspect the generated PNGs before judging
the final video. Elf1 should preserve the explicit female/silver-haired identity and
Dragon1 should preserve the humanoid-dragon/obsidian-scale/wing/amber-eye identity. After
that, investigate the two remaining spatial failures separately rather than changing the
reference architecture.


### 2026-10-05 — one-source dynamic wardrobe bootstrap

The dynamic-reference identity fix is now consolidated with initial wardrobe assignment so
clothing has one authoritative source before a new dynamic Subject's generated Picture is
rendered.

Current architecture on `location-state-test`:

- the existing post-RAW Subject-resolution call now bootstraps both non-clothing identity
  and initial wardrobe for each newly named foreground dynamic Subject;
- `subject_descriptions` contains only stable non-clothing identity facts already present
  in RAW (species/type, sex/gender wording, age, hair, skin/scales/fur, build, anatomy/body,
  distinguishing features);
- `subject_wardrobes` contains exactly `upper`, `lower`, `footwear`, and `other`;
- explicit RAW clothing is preserved; when a human/normally clothed humanoid has no clothing
  specified, the same LLM call assigns one simple setting-appropriate outfit exactly once;
- animals/creatures that normally do not wear clothing receive N/A wardrobe fields unless
  RAW explicitly provides clothing; explicit garment/footwear absence uses `absent` and
  overrides invention;
- Python stores that wardrobe directly in the new Subject continuity record before any
  character-reference media is generated;
- identity prose is deterministically stripped of any accidental wearing-clause so wardrobe
  is not duplicated in two canonical fields;
- the character-reference renderer is now a consumer only: it visualizes the persisted
  identity + wardrobe and is explicitly forbidden from adding/removing/redesigning clothing;
- later clothing changes continue through the existing persistent wardrobe continuity path;
  there is no second first-appearance clothing decision downstream.

Compatibility: older direct callers/tests of the Subject resolver may still request only
names or names+descriptions; production requests the full bootstrap tuple.

Acceptance target: rerun the tavern. Before video evaluation, inspect Elf1/Dragon1 generated
state metadata and PNGs. Elf1 should have both the RAW-derived female/silver-haired identity
and one persisted setting-appropriate outfit; Dragon1 should retain the RAW-derived dragon
identity and should not acquire humanoid clothing unless RAW explicitly says so. The same
persisted wardrobe must be what the story H3 prompt references.


### 2026-10-05 — expanded-story context for dynamic wardrobe bootstrap

The consolidated dynamic Subject bootstrap now receives the complete
`expanded_story.txt` as read-only wardrobe context.

- The existing post-RAW Subject-resolution call gets a `STORY CONTEXT` block containing
  the expanded story.
- RAW remains authoritative for actions and explicit appearance/clothing.
- STORY CONTEXT is used only when RAW leaves clothing unspecified, so the one-time
  canonical wardrobe can match the established setting, period, culture, and visual world.
- The expanded story is loaded once for the video run and reused both for existing
  story-location extraction and dynamic Subject bootstrap, including resumed runs.
- No extra LLM stage was added; this only enriches the existing identity+wardrobe bootstrap.
- Focused regression coverage confirms the story context reaches that prompt.

Acceptance target remains the tavern run: Goblin1/Elf1 clothing should now reflect the
expanded story's visual world while Dragon1 should stay unclothed unless the story/RAW
establishes clothing.


### 2026-10-05 — cumulative Director Request 1 retry blockers

Observed Segment 3 repeatedly bounced between independent blockers: final timestamp too
early, prop-transfer incoherence, then missing 00:00.000 staging. The retry path was resetting
to the clean base prompt after every failure and passing only the latest issue, so a later
retry could reintroduce a defect already corrected on an earlier attempt.

Fix on `location-state-test`:

- Request 1 now keeps a short unique list of every blocking failure observed during the
  current segment attempt loop.
- Every retry is still rebuilt from the clean base prompt, but appends one compact
  `RETRY REQUIREMENTS` block containing ALL blockers seen so far.
- Structure retries now include the exact structure error returned by Python instead of only
  a generic "begin at 00:00.000" reminder.
- Physical/spatial, prop/state, timing, dialogue, and empty-scene blockers all use the same
  cumulative mechanism.
- This does not add an LLM stage or preserve/re-feed the rejected RAW; it only prevents the
  model from forgetting already-discovered constraints while keeping retry prompts small.
- Regression coverage reproduces a structure failure followed by a prop/state failure and
  verifies the third Request 1 prompt contains both requirements.

Acceptance target: rerun the failed tavern Segment 3. Once a retry learns that the final
micro-beat must be >= 6s and frame zero must be 00:00.000, those constraints should remain
present while it also repairs the mug transfer instead of oscillating between validators.

### 2026-10-05 — Python now owns three Director RAW structure repairs

Request 1 is normalized before semantic validators run. Python now inserts a
missing `00:00.000` anchor, moves only a too-early final timestamp to the 75%
segment boundary, and guarantees exactly one trailing
`End continuity state:` marker. These cases no longer need Director
regeneration. Earlier timestamps are deliberately unchanged, so compressed
travel (for example doorway -> back table in 1.5s) still reaches the existing
timing-feasibility LLM unchanged. Prop/state semantic retries are also
unchanged.

### 2026-10-05 — run-level H3 visual style

- Added `--visual-style "STYLE"` with default `Live-Action cinematic`.
- Python now owns the global visual-style prefix at the final H3 assembly boundary. Every final `detailed_description` begins `[Shot 1] {visual_style}, ...`; Request 2 is told not to invent or repeat a global style phrase.
- The historical `Live-action, cinematic` formatter prefix is stripped if it still appears, then the configured style is inserted once.
- The style is saved in generation-state/run config and `generated_prompts.txt` metadata. Resume/repair reuse the saved style unless `--visual-style` explicitly overrides it.
- The desktop UI exposes Visual style and passes it to `minimax.py` as one subprocess argv element, so spaces require no platform-specific quoting inside the app.

### 2026-10-05 — per-defined-Subject canonical appropriate attire

The Amy reference test exposed a wardrobe-authority loss: the expanded story said
`rough-spun tunic and leather apron`, but the earlier broad character-canon pass
collapsed that to `tunic and apron`, producing an incomplete clothing reference.

Current fix on `location-state-test`:

- after `expanded_story.txt` exists, every pre-defined Subject from `subjects.txt`
  gets its own independent `story_subject_wardrobe_extract` LLM request;
- the call is deterministic/low-budget (temperature 0, low reasoning, 128 thinking
  budget through the normal analysis profile; output capped at 128 tokens);
- each call receives the full expanded story but reasons about exactly one Subject;
- the prompt explicitly asks for the Subject's **appropriate attire**: preserve all
  explicit material/texture/color/wear/layer details, then fill only missing normal
  outfit pieces so a normally clothed Subject has a complete coherent outfit;
- "appropriate attire" is species/body/setting aware. Dragons, animals, and other
  beings that appropriately do not wear clothes return `N/A` unless the story
  explicitly clothes them; a normally clothed modern person may receive ordinary
  attire such as a T-shirt and blue jeans when the story is silent;
- the earlier broad character-canon pass no longer invents clothing when source
  clothing is absent; it returns `N/A` and leaves final wardrobe ownership to this
  expanded-story per-Subject extractor;
- each extracted outfit overwrites that Subject's `character_canon.json`
  `clothing` value and is therefore the canonical defined-Subject outfit used by
  Director/H3/reference generation;
- canonical attire is seeded into structured wardrobe state before fallback story
  parsing, and `apron` is now recognized as an `other` wardrobe component;
- explicit no-clothing values do not generate a bogus `wearing ...` sentence.

Dynamic/video-created Subjects keep the existing one-source post-RAW wardrobe bootstrap;
this new extractor applies only to pre-defined Subjects.

### 2026-10-05 — latest tavern postmortem: Elf promotion, support routes, prop render identity, audio specificity

The 18:16 tavern run showed that the accepted location/Guide architecture remained stable, but
five upstream/render-boundary gaps were still visible:

- Segment 3's Subject resolver correctly returned both `Goblin1` and `Elf1`, including an
  Elf identity description and wardrobe, but its rewritten RAW still said generic `the elf`.
  Python required the literal functional name to appear in RAW and silently filtered `Elf1`,
  so no Elf generated reference was created.
- Segment 1 RAW contained an unsupported support transition (Amy was established on the floor,
  then "steps down from the counter"), and Segment 6 again chose gratuitous tabletop traversal.
- Segment 3's final timed action left Amy at the back table while End continuity state incorrectly
  relocated her near the counter; Segment 4 therefore began with bad semantic position authority.
- H3 visually duplicated/merged distinct drink containers even though the prop ledger itself was
  correct (Goblin mug duplication; Segment 4 glass/cup merging/substitution).
- Segment 2 soundscape reduced the Goblin entry to a generic `footstep`, leaving H3 room to
  exaggerate it into heavy/repeated footsteps.
- Dragon1's generated identity Picture was finally used, but the unclothed nonhuman reference
  acquired inappropriate human sex anatomy. This is not a defined-Subject attire-extractor issue:
  Dragon1 is dynamic and is intentionally allowed to remain unclothed.

Implemented on `location-state-test`:

- dynamic Subject resolution now explicitly requires every returned `subject_names` label to be
  applied in returned RAW; Python also deterministically canonicalizes unambiguous generic
  role/species nouns in timed RAW using the resolved functional name before promotion. A resolved
  name that still cannot be found now raises instead of silently disappearing;
- Director creation and the physical validator now preserve body support/elevation literally:
  no stepping down/off/over or climbing onto counters/tables/bars/etc. without an established or
  Beat-required reason, and ordinary floor routes are preferred;
- the physical validator now explicitly rejects End continuity state that relocates a Subject away
  from its final timed position without a later timed move;
- every final H3 prompt now carries one compact render-boundary prop rule: established handheld/
  movable props remain one distinct physical object and may not duplicate, merge, or substitute;
- soundscape extraction now preserves source/count/duration/intensity when RAW establishes them and
  specifically avoids turning one step into generic/plural or exaggerated footsteps;
- generated nonhuman identity references keep external anatomy species-appropriate and do not
  invent human sex-specific anatomy unless explicitly established; no clothing is added merely to
  cover anatomy.

Focused regressions were added for the exact Elf metadata-with-generic-RAW failure, unsupported
support transitions/stale End position, final H3 prop identity contract, sound source/count
specificity, and unclothed nonhuman reference anatomy.

Commits:
- `8dc31b5efe8fc3f0e4375edfe3cd598b17fa5f7b` — implementation
- `43227243a157e2679695e0c80f7c7095e087c70f` — focused regressions

Next acceptance: rerun the same tavern case from current `location-state-test`. Before judging
video, confirm Segment 3 logs register `Elf1` and create/bind its generated Picture. Then inspect:
Segment 1 stays on an ordinary floor-side wiping route; Segment 2 keeps one Goblin mug and does not
invent heavy/repeated footsteps; Segment 4 starts Amy from the back-table state and keeps the
existing chalice/new Dragon cup distinct; Segment 6 uses a visible ordinary floor route rather than
a tabletop shortcut or teleport.



### 2026-10-05 — resolver restart-loop hotfix
- Fixed a regression from the stricter dynamic Subject resolver enforcement.
- If returned Subject metadata is valid but the resolver fails to rewrite its functional name into RAW, Python first retries the naming deterministically against the already-accepted Director RAW.
- If no safe deterministic mapping exists, that resolver entry is warned/dropped instead of restarting the entire segment.
- Raised the per-defined-Subject wardrobe extractor output cap from 128 to 256 tokens after local GPT-OSS repeatedly truncated the JSON response at 128.
- No LLM prompt wording changed in this hotfix.
- Commit: `5f6668bba909898984b374c14cfae4ed6aef7f7e`.


### 2026-10-05 — prop ledger identity lock + delta-only continuity props
- Fixed deterministic prop-ledger corruption where the combined continuity observer could overwrite an existing prop ID with a different object kind (for example `mug_1` becoming a cloth).
- `merge_prop_ledger()` now treats `prop_id -> kind` as immutable identity. Same-kind observations may update mutable state; a conflicting different-kind observation is assigned a fresh unique prop ID instead of rewriting the existing object.
- Simplified the `COMBINED_CONTINUITY_SYSTEM` prop instructions so the LLM reports only NEW props or CHANGES. Unchanged props are omitted because Python copies the committed ledger forward.
- Removed the redundant instruction telling the LLM to copy unchanged/offscreen props forward.
- Kept the rest of the Combined Continuity wording unchanged because it still defines semantic final-frame facts the LLM must observe.
- Added regressions for a `mug_1 -> cloth` collision and for delta-only prop prompt wording.
- Commits: `79474334b75f3625d3b467f8da1ccd6e19c5b7e7`, `4c8f927c58c28bfbde65e4319cb467db5b63ed1f`.
- Tests were added but not executed through this chat environment.


### 2026-10-05 — tavern regression: simplify validators, retire prop staging, add persistent Subject ledger
Latest rendered tavern run regressed despite character references working. Root causes were primarily upstream scene/continuity handling rather than missing Pictures:
- Segment 2's first RAW used a camera reveal for the goblin, but the prop validator rejected the goblin's chipped mug because it was not already in the ledger even though CURRENT BEAT introduced it. Retry accumulation degraded this into literal `appears` wording.
- Segment 3/4 showed the same over-validation pattern for newly introduced cups/chalices. Segment 3 also accepted impossible cross-room interaction and a malformed `held_props` shape caused a useful continuity response (including the chalice) to be discarded.
- Elf1 lost the explicit female fact because the post-RAW Subject resolver was restricted to appearance facts present in RAW even though CURRENT BEAT said female.
- Goblin1 remained referenced/registered but Segment 4's timed H3 action omitted him while Dragon1 entered the same visual area.

Changes:
- Retired the proactive `director_prop_staging` LLM path completely, including its dead schema/trigger/helpers/purpose entry.
- Simplified `director_raw_scene_prop_state`: a prop explicitly introduced by CURRENT BEAT may first appear in the scene; existing ledger props remain identity/state constrained; source/destination and real source-container checks remain.
- Simplified `director_raw_scene_physical` to only entry/reveal, travel between established positions, support/elevation changes, and final End-position consistency.
- Added deterministic RAW rejection for `appears` / `suddenly appears` / `pops into view` introduction wording before the physical LLM validator.
- Subject resolver now receives CURRENT BEAT and may use explicit non-clothing appearance facts from RAW or CURRENT BEAT. Explicit female/male wording in the resolved canonical description is deterministically copied into Subject registration.
- Combined Continuity sanitizes harmless `held_props:[{"id":"..."}]` variants into string IDs before strict schema validation, preventing an unrelated list-shape error from discarding otherwise useful prop observations.
- Removed implementation-language from modified prompts: no `Python owns...`, `Python copies...`, or prop-ledger copy-forward explanation. Combined Continuity user input now labels the database simply `COMMITTED PROP LEDGER:`.
- Director Request 1 likewise states required timestamp/end-state behavior directly rather than explaining Python normalization.
- Added deterministic final-H3 continuing-Subject state insertion for continuation clips. A known Subject with a concrete opening position that is absent from current timed action gets a concise line such as `Continuing Subjects: Goblin1 remains beside the counter.`
- Added `subject_state_ledger`, a Python-owned durable all-Subjects database parallel to the prop ledger. It is seeded from configured `subjects.txt`, persists dynamic Subjects and last-known state across offscreen segments, is checkpointed run-level and per-segment, and is intentionally not yet used as a new semantic/render authority. `last_updated_segment` means ledger update, not rendered observation.
- Future design note: the Subject ledger currently treats N/A/empty continuity values as unknown and therefore does not clear prior nonempty state from an empty observation. Before it becomes authoritative for every-world-state use, explicit clear/change semantics should be defined rather than inferring clears from absence.

Prompt changes made in this batch:
- `director_raw_scene_prop_state` now begins: `Validate only prop continuity in RAW. A prop introduced by CURRENT BEAT may first appear in this scene.`
- `director_raw_scene_physical` now begins: `Validate only subject movement in RAW.` and enumerates only the four narrow rejection cases above.
- `director_raw_scene_subject_resolution` receives a `CURRENT BEAT` block and the description rule now says appearance facts may come from `RAW or CURRENT BEAT`.
- `COMBINED_CONTINUITY_SYSTEM`: `Omit unchanged props.`; removed architecture explanations about Python.
- Director Request 1: direct behavior only for 00:00.000, final-quarter timing, and exactly one End continuity state.

Implementation commits:
- `90c96a26be5949910759356585b90da3e78276c6` — simplify validators/continuity and add Subject state ledger
- `a28c323e2941a72390cd4c885aa648ce082227a6` — finish stationary Subject carry-forward and state seeding
- `a102960ab54f06c6a45a06262c27a07dae3fb048` — remove retired prop-staging code and clarify Subject ledger timestamp
Regression commits:
- `347fe1efabf4b65e7319728fe2ea314fc693cdf7`
- `cd3bb16e907264d6e4f50dba9e3b6b7dac96dd7b`
- `6cc56dbc4fceece85030858b835a796d1935b0c8`

Regressions cover CURRENT-BEAT prop introduction, deterministic pop-in rejection without an LLM call, CURRENT-BEAT gender/appearance input to Subject resolution, held-prop schema sanitization, offscreen Subject persistence, and deterministic stationary-Subject H3 carry-forward.
Tests were updated but not executed through this chat/GitHub connector environment.

Next local acceptance run:
- Segment 2 should no longer burn retries merely because CURRENT BEAT introduces Goblin1's chipped mug, and accepted RAW must not contain pop-in `appears` wording.
- Segment 3 Elf1 reference/registry should retain explicit female identity; Amy must visibly travel before interacting at the back table; mug/chalice identities should remain separate; a harmless held_props shape slip must not erase the chalice.
- Segment 4 should retain Goblin1 through deterministic continuing-Subject text when he remains in the location, and pouring must have a real source container. Watch specifically for cup floating/duplication even with correct prompt state.
- Inspect `generation_state.json.subject_state_ledger`: configured Subjects should exist from run start, dynamic Subjects should be added, and offscreen Subjects should retain last-known state.


### 2026-10-05 — object-state-work branch

Created branch `object-state-work` from `main` at commit
`8dc5c86e2cc0ae8f3b79aaa8e327b100b5b792ac`.

This branch is the active workspace for the next object-state work. The latest
implementation and acceptance target are the 2026-10-05 Subject/prop ledger
handoff immediately above; no new implementation changes are part of this
branch setup.


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
