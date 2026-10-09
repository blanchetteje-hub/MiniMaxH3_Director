# MiniMax H3 — Development Handoff

## 2026-10-09 — use WorldState for Director and final H3 continuity

- Bridge job 26 showed physical facts duplicated across the generated
  `subject_definitions`, legacy `generated_continuity_state`, and final H3
  inputs. The run's legacy summary described Subject positions, wardrobe, and
  a held prop independently of the reducer state.
- Director Request 1 continuity now formats established Subject, wardrobe,
  location, support, condition, and prop facts from the immutable WorldState
  opening. Legacy continuity summaries, prop ledgers, and initial-location
  summaries no longer feed that request. The previous Director end frame is
  carried separately as choreography context.
- Final H3 assembly now places WorldState physical facts in the existing
  Subject-definition content while retaining identity and Picture references,
  location Video references, soundscape, music, and visual style. Canonical
  identity descriptions remain; their wardrobe clauses and the redundant raw
  `canonical_data.txt` insertion are omitted when WorldState is present.
- Removed the live combined-continuity extraction/Phase-2 update and the
  visual-observation-to-continuity merge. Rendered observations remain saved
  as separate diagnostics/media evidence and do not write WorldState. Dynamic
  Subject identity fallback remains identity-only; deterministic WorldState
  display references are stable even for string stable IDs.
- The accepted Director action batch still commits through the existing
  reducer only after segment acceptance. Checkpoint/resume keeps the canonical
  WorldState; old continuity and prop fields are read only while normalizing
  prior checkpoint formats and are reset before prompt construction.
- No runtime system/user prompt templates or retry suffixes were edited; only
  their assembled physical-state inputs now come from WorldState.
- Verification: prompt-authority plus canonical-insertion tests passed (8
  passed, 2 subtests); prompt-generation mode passed (10); WorldState foundation
  passed (57 passed, 2 stale story-start response-contract tests deselected,
  7 subtests); focused Director state-action regressions passed (3 passed, 112
  deselected, 2 subtests). `py_compile` and `git diff --check` passed. Bridge
  job 26 was used for diagnosis; no acceptance job was queued.

## 2026-10-09 — route all Director RAW validators through repair

- Every Director RAW-scene validator now sends its first concrete failure to
  `director_raw_scene_repair`: shot-script structure, required dialogue,
  physical/spatial movement, prop/state consistency, and timing feasibility.
  The repaired RAW is normalized and the full validator sequence reruns. Five
  unsuccessful repairs still step back to a new `director_raw_scene` attempt.
  The separate `state_actions` contract/reducer retry remains separate because
  the RAW-only repair cannot change the action response.
- The repair request labels its errors generically as `VALIDATOR ERRORS`. Each
  verdict and repair dispatch logs the Segment, Director attempt, repair
  attempt, validator, and concrete issue. Raw physical, prop/state, and timing
  responses are retained in prompt history.
- `docs/LLM_PROMPTS.md` now records the broader repair scope. Verification:
  `tests/test_director_retry.py` and `tests/test_dynamic_temperature.py` passed
  (174 passed, 7 subtests); `py_compile` and `git diff --check` passed. The
  broader combined run including `tests/test_llm_prompt_pipeline.py` had 24
  failures among 288 cases, from stale prompt assertions and pre-WorldState
  Director response fixtures; those were not changed in this scoped update.

## 2026-10-09 — bridge accepts fixture Director plans

- `run_acceptance` jobs may provide `director_plan_dir`; the bridge resolves it
  inside the execution worktree, restricts it to `tests/acceptance/fixtures/`,
  verifies `story_arc.json`, `beats.txt`, and `expanded_story.txt`, and forwards
  the resolved path to the existing `--director-plan-dir` runner option.
- The established plan is
  `tests/acceptance/fixtures/tavern_run21_plan`. Existing `director_plan_job`
  materialization remains unchanged; a job cannot specify both plan sources.
- Verification: bridge tests passed (9 passed; one unrelated stale branch-error
  assertion deselected), acceptance-runner tests passed (10 passed), and syntax
  and whitespace checks passed.

## 2026-10-09 — include expanded story in Director-only plans

- Recovered the saved expanded tavern story from the run artifacts and added
  it to `tests/acceptance/fixtures/tavern_run21_plan/expanded_story.txt`.
- Director-only acceptance now requires and stages `story_arc.json`,
  `beats.txt`, and `expanded_story.txt`, and captures the expanded story in the
  acceptance artifacts. The existing Director-only path continues to load the
  saved Beats and skip story expansion, Beat generation, and Beat validation.
- Added a regression proving the saved expanded story reaches location
  extraction and that its resulting location/fixture state seeds canonical
  WorldState. Story and Beat stages remain uncalled; existing WorldState
  validation remains active.
- Verification: acceptance-runner tests passed (11 passed), bridge tests passed
  (9 passed; one unrelated stale branch-error assertion deselected),
  prompt-generation-mode tests passed (10 passed), and syntax/whitespace checks
  passed.

## 2026-10-09 — reusable six-Beat tavern Director plan

- Preserved the **six accepted Beats** from acceptance 21 and paired them with the supplied one-phase `story_arc.json` and recovered `expanded_story.txt` at `tests/acceptance/fixtures/tavern_run21_plan/`. The arc retains E1–E6, their original source-event wording (including Amy's explicit wardrobe in E1), ordering/dependencies, and empty source state effects; accepted Beat text is copied verbatim from the run log.
- **Future tavern WorldState/Director/H3 tests:** use the existing `tests/acceptance/run_acceptance.py --director-plan-dir tests/acceptance/fixtures/tavern_run21_plan` mode with the tavern gold benchmark and normal image/model options. This reuses the fixed planning outputs and skips story expansion/Beat generation/Beat validation; do not quietly substitute a fresh plan.
- The separate `tests/acceptance/fixtures/tavern_run21_accepted_beats.txt` remains as a source record. No production prompt, reducer, or acceptance runner code changed. Re-enable fresh full-pipeline acceptance when testing planning itself.

Read `docs/PROJECT_NOTES.md` first for project-wide architectural rules. This file describes the current branch implementation, active experiment, latest evidence, and immediate next work.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `world-state-rebuild`

Runtime/bridge mailbox branch: `gpt-runtime`

Baseline branch this experiment diverged from: `main`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is development/evaluation only and must not become a production dependency.

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` remains the sole narrative authority. Expansion may add concrete staging/detail where the source is silent, but it may not add, replace, contradict, skip, reorder, or materially alter source events/outcomes.

### Primary goal achieved

### Next goal

Continuity

Location continuity -> 3-second persistent 360-orbit room reference is accepted; covered geometry stayed ~99% consistent in the latest tavern run
State/subject/action continuity -> active work

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
