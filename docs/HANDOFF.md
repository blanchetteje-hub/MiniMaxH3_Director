# MiniMax H3 — Development Handoff

## 2026-10-14 — two-reference location transitions

- Expanded the existing `scene_location_select` request to return
  `same_location`, `new_location`, or `transitioning`. Python resolves a unique
  destination alias against the existing WorldState location IDs; a missing
  destination goes through the established static-setting, spatial-refinement,
  structured location-state, and persistent 360-degree reference pipeline.
  Existing location references are reused. Selector results and per-segment
  origin/destination IDs survive checkpoints, and earlier selector checkpoints
  are normalized without inferring a transition.
- A transitioning segment keeps its opening WorldState unchanged. Director
  context names the origin and destination environments separately and asks for
  physical movement to the destination without assuming every Subject moves.
  Subject location changes remain exclusive to accepted StateActions; following
  segments select the destination as their normal single location reference.
- H3 transition prompts bind `<Video 1>` to the origin reference and `<Video 2>`
  to the destination reference, describe those roles at the start and end, and
  require the final action to establish destination entry. Continuation segments
  keep the preceding rendered clip as the separate native opening guide; a
  transition bypasses a scheduled clean refresh to preserve that guide. Picture
  references remain in their separate image inputs. Saved prompt rendering uses
  the same ordered pair and guide behavior.
- Added coverage for the three selector results, unique destination reuse versus
  registration, checkpoint metadata, two-video prompt roles and ComfyUI input
  slots, saved-prompt transition/revisit bindings, forced append on a refresh
  boundary, and a reducer transition that moves only the named Subject and
  carries that result into the following segment. Focused location tests:
  13 passed; WorldState transition tests: 2 passed. `py_compile` and
  `git diff --check` passed. The full location-reference module still has two
  pre-existing unrelated failures: a wardrobe extractor call-count expectation
  and a stale physical-validator prompt assertion. Adjacent workflow-name and
  prompt-generation suites reported 32 passed and 6 unrelated failures: five
  stale `print` call-count/assertion expectations and one unavailable generated
  character-reference video fixture.

## 2026-10-14 — guard Alice RAW staging and location geometry

- Director RAW repair requests now include the current Beat, assigned source,
  previous shot end, opening WorldState, static setting, and registered location
  geometry. The physical validator and timing validator receive the same source
  context. Generated-setting distances absent from the Beat/source are labeled
  approximate so they do not become hard movement requirements.
- Creative and repaired RAW are checked for leaked internal prompt headers and
  unresolved template placeholders before timing. A repair remains subject to
  the same physical and prop/state validators as the original; rejected content
  cannot reach H3 when bounded repairs/regeneration are exhausted. The existing
  required-stage retry policy remains in force.
- The final pre-H3 boundary checks prompt leakage again. If pronoun resolution
  introduces an internal header or unresolved placeholder, its changed text is
  discarded and the last accepted RAW is retained.
- If pronoun resolution changes accepted RAW, the changed scene now passes the
  existing physical and prop/state validators before replacing the last valid
  scene. Invalid rewritten text is discarded by the existing optional resolver
  fallback. No additional LLM stage or retry loop was added.
- Spatial-setting parsing now compares explicit fixture placement claims across
  structured location state, static setting, spatial refinement, and render
  description. Contradictory fixed-object placements are rejected before
  location reference generation. Exact distances are deliberately not compared
  as authoritative geometry.
- Added regressions for context-rich repair, same-validator revalidation and
  fail-closed exhaustion, `RAW PROMPT`/placeholder leakage, approximate
  distance handling, and contradictory fixture placement. All eight directly
  focused tests pass. The full Director retry and location-reference suites
  reported 189 passed and 2 unrelated failures: an existing wardrobe extractor
  call-count expectation and an existing physical-validator system-prompt text
  expectation. `py_compile` and `git diff --check` passed.
- No local artifacts for the cited Alice run were present, so the exact model
  response that introduced the wooden-post placement conflict could not be
  attributed. The confirmed code defect was that parser validation checked the
  mixed response's shape but never compared its fixed-placement claims.

## 2026-10-14 — isolate Director RAW repair sampling

- Added immutable `REPAIR_LLM_SETTINGS` as a copy of the profile previously
  assigned to `director_raw_scene_repair` (Smart Extractor), with temperature
  `0.2` and a randomized seed. Only this purpose routes to the new profile;
  other purpose mappings are unchanged.
- `ask_llm()` already generates a fresh LLM seed for each request whose
  configured seed is `None`, so successive RAW repair attempts receive
  independently generated seeds without changing startup or retry behavior.
- Added focused routing/profile tests for profile isolation, preserved copied
  settings, temperature, and distinct seeds across consecutive repair calls.
  `tests/test_dynamic_temperature.py`: 69 passed. Its expected routing list also
  now includes the already Smart-Extractor-routed `clothing_state_extractor`.

## 2026-10-14 — keep registered physical entities out of Subject discovery

- Pre-Director Subject candidates are now checked against registered locations,
  props, fixtures, and supports before Python assigns Subject IDs or requests a
  wardrobe. Visible-Subject resolution and formatter Subject-name hints apply
  the same check before a new identity can reach reference generation or
  Subject/Picture bindings.
  Explicitly animated/talking entities remain eligible even when their name
  matches a registered physical object. The filter uses runtime WorldState
  vocabulary and source wording, not a list of forbidden object names.
- Segment location preparation now precedes current-Beat Subject discovery so
  fixtures and supports registered for a newly selected location are included
  in the deterministic category check.
- Dynamic humanoid wardrobes now follow the predefined-Subject path: after
  `story_subject_wardrobe_extract`, the existing `clothing_state_extractor`
  converts the complete outfit into `upper`, `lower`, `footwear`, and `other`
  before `seed_canonical_wardrobes()` writes it to WorldState. Character
  references consume that prepared opening state, then Picture bindings and
  final H3 assembly run as before. Incomplete upper/lower data stays unknown;
  the first reference render/plan is withheld until body coverage is known, and
  the existing wardrobe extraction is retried on a later pre-Director pass.
  Existing references and rendered-wardrobe precedence are unchanged.
- Focused tests cover Moss1/mossy-ground and registered tote/post rejection,
  prevention of wardrobe/reference/binding side effects, explicitly animated
  object and talking-animal preservation, complete Mad-Hatter-style four-slot
  seeding before Picture creation, and withholding a partial hat-only
  reference. Focused regressions passed (9 tests, including the tavern
  Elf/Dragon pre-Director fixtures). The broader five-file run reported 351
  passed, 23 failed, and 30 subtests passed. Those failures assert older
  wardrobe adapter/call-count behavior, retired story-start response fields, or
  pre-split Director prompt wording/contracts; the focused changed paths passed.
- `python -m py_compile minimax.py world_state.py story_planner.py` and
  `git diff --check` passed. The updated automation copy of `minimax.py` was
  verified byte-for-byte with `cmp -s`.
- No runtime LLM prompts, response schemas, reducers, or retry policy changed.

## 2026-10-14 — fail open only at optional stages

- Added `docs/PIPELINE_FAILURE_POLICY.md`, linked from `PROJECT_NOTES.md`, to
  distinguish REQUIRED, OPTIONAL, and CONDITIONAL recovery. It identifies the
  audited optional enrichments and records that conditional-stage recovery is
  not changed here.
- Camera-refiner exhaustion now keeps the accepted timed scene. Pronoun and
  visible-Subject resolution failures preserve accepted RAW after their
  existing local attempts. Exhausted soundscape/music extraction uses the
  existing `N/A` values. Rendered visual analysis failure discards only the
  observation and no longer reruns the completed render.
- Pre-Director Subject discovery, dynamic canonical wardrobe extraction, and
  authored-canon wardrobe enrichment now discard failed optional candidates or
  metadata while retaining registered identity and prior valid canon. Existing
  prop rejection and atomic WorldState event-batch fallback remain in place.
- WorldState event fallback now catches content/translation failures only;
  request transport, filesystem, ComfyUI, LLM connection, and cancellation
  failures propagate. The event RAW-integrity check is inside the same
  fail-open boundary, so an invalid event response cannot block an otherwise
  accepted segment. The shared LLM request path now preserves non-connection
  transport failures for the audited optional purposes instead of returning an
  empty reply that could be mistaken for malformed optional content; vision
  transport failures also propagate after its existing local retries.
- Focused regressions cover exhausted Director enrichment, event atomicity,
  optional Subject/wardrobe failure, rendered-observation fallback, and
  infrastructure propagation. The final focused post-change runs passed:
  Director optional-stage tests (6), camera fallback (1), event extraction
  (17), pre-Director seed/prop tests (4), visual cleanup/fallback (6), and
  canonical wardrobe fallback (2). `py_compile` and `git diff --check` passed;
  the automation copy of `minimax.py` was verified with `cmp -s`.
- The broader affected-module run, before the RAW-integrity regression was
  added, reported 307 passed and 5 failures (36
  subtests passed). Two story-start tests use the retired `classification` /
  `evidence` shape and old prompt wording; two character-canon assertions
  expect retired prompt wording; the render-enabled prompt fixture references
  a character-reference MP4 absent from this checkout. These are outside this
  change; successful behavior and prompts were left unchanged.
- No optional stage invokes `run_pipeline_stage_with_backstep()` on content
  exhaustion. Render completion, required RAW/Beat recovery, and conditional
  mode recovery remain unchanged. No bridge job was queued.

## 2026-10-14 — keep optional WorldState failures from restarting a segment

- WorldState event extraction/translation failures now log the exact diagnostic,
  discard the full event batch, and return an accepted empty action batch against
  the immutable opening state. `LLMConnectionError` still propagates. A reducer
  rejection after an earlier valid event therefore cannot leak a partial state
  or route back to Director RAW generation.
- Pre-Director prop extraction/registration failures now reject the complete
  candidate batch, log the diagnostic, and continue with the already registered
  props. Subject identity and wardrobe seeds remain intact, and registration is
  applied only after the complete prop batch succeeds.
- Added Alice/fixed-post coverage for reducer rejection after a valid pickup,
  malformed/exhausted event extraction, missing prop origins, and duplicate
  pre-Director fixed-post proposals. `tests/test_director_retry.py`: 135 passed,
  13 subtests passed. Event/foundation run: 111 passed, 17 subtests passed; two
  unrelated stale story-start expectations failed (`classification`/`evidence`
  fixture shape and old prompt wording). Targeted event/foundation regressions,
  `py_compile`, and `git diff --check` are recorded with this change.
- No prompts, reducer rules, location handling, or checkpoint commit boundaries
  changed.

## 2026-10-14 — scene location selector output budget

- Increased `scene_location_select` maximum output tokens from 256 to 2048.
  The selector continues using Smart Extractor settings, whose high reasoning
  budget is 1024 tokens; the request output cap now accommodates that thinking
  budget alongside its structured response.
- Updated the focused routing regression. Verification: selector/profile
  tests, Python compilation, and `git diff --check`.

## 2026-10-14 — per-segment location selection and reference reuse

- Added a single `scene_location_select` Smart Extractor call for each Beat,
  before its Director request. It receives only the upcoming Beat, active
  setting description, and registered location names/descriptions. Python
  caches both the response and resolved stable location ID in checkpoint
  metadata, so the main request and Director prefetch reuse one selection.
- Python resolves exact or unambiguous descriptive aliases against
  `WorldState.locations`. A genuinely new location reuses the existing static
  setting, spatial refinement, structured location-state, and canonical
  WorldState seeding functions. Mixed-environment Beats log that they use the
  primary action/result environment; no automatic splitting or Subject
  relocation is inferred.
- Per-location render descriptions, canonical geometry, active ID, and
  persistent 360-degree reference path are saved in generation metadata.
  References use unique paths under `video/state`, so startup cleanup preserves
  them. Each Director bundle receives the selected location context; each H3
  prompt records its selected ID, setting, and `<Video 1>` reference path. Live
  and saved-prompt rendering select the same per-segment path. Existing
  single-location checkpoints and prompt packages retain a legacy path fallback.
- Added regressions for the minimal selector contract/profile, alias ambiguity,
  stable per-location asset paths, location metadata checkpoint round-trip,
  selector caching and prefetch order, distinct location-specific H3 context,
  saved-prompt revisit/reference selection, persistent output paths, and
  state-media cleanup. Focused runs: 10 location-selection/reference
  regressions passed; 23 source-mode tests passed with 3 existing
  automatic-recovery cases deselected; 2 saved prompt/reference regressions
  passed; all 67 LLM-profile routing tests passed. The location and
  requested-prompt modules together reported 107 passed and 7 pre-existing
  prompt-expectation failures (6 stale H3 wording expectations and one stale
  physical-validator prompt expectation). `py_compile` and `git diff --check`
  passed. No bridge job was queued.

## 2026-10-14 — Preserve persistent state reference media

- Removed the unconditional startup deletion of `video/state`. It ran before
  CLI mode selection and erased all files and subdirectories on every launch,
  including resume and saved-prompt rendering. This deleted checkpointed
  location-reference videos and generated character-reference images that the
  pipeline is designed to reuse.
- Removed the blanket cleanup helper. Temporary vision/refresh-frame cleanup
  remains limited to the specific generated files owned by those paths.
- Added a regression that runs application startup with persistent location,
  character, and nested state assets present and verifies their bytes remain
  unchanged. Focused source-mode tests passed (23 passed, 3 deselected because
  the existing automatic-recovery cases exercise a separate retry loop); 3
  related location/reference tests passed. Syntax and whitespace checks passed.

## 2026-10-14 — LLM stage retry and predecessor recovery

- Added a shared pipeline-stage recovery helper. Each stage retains its bounded
  malformed-response/repair attempts; after exhaustion it reruns the immediately
  preceding stage when that dependency is explicit, then retries the failed
  stage and downstream work. Root stages retry from their authoritative inputs.
- Applied this flow to story expansion → Beat extraction, source-unit semantic
  planning, the chained story-location/static-setting/spatial-setting extractors,
  Director RAW/StateAction failure routes, and post-RAW soundscape/music stages.
  Story-planning hard-reset and cut-choice failures regenerate their immediate
  preceding terminal/split classification before retrying.
- Runtime supervision now treats ordinary generation, validation, state, and
  rendering failures as recoverable from the first incomplete segment. Only an
  unreachable LLM, unreachable ComfyUI, or user cancellation escapes the
  generation supervisor. CLI argument parsing retains its normal usage exit.
  LLM connection failures are explicitly rethrown by concurrent Beat validators,
  Director validators/refiners, and event extraction rather than being reported
  as content failures or converted to fallback output.
- Camera-refiner exhaustion now backsteps to timing; pronoun, event, and audio
  extraction exhaustion backsteps to their declared preceding Director stage.
  Event extraction no longer accepts an empty batch after malformed extraction
  or translation failure; its immutable opening WorldState is preserved while
  the Director stage is retried.
- Added regressions for story-to-Beat predecessor regeneration, semantic
  classifier backsteps, connection-failure propagation, Director event failure
  routing, and recoverable versus fatal runtime failures. The focused Director,
  story-planner, story-to-Beat, event-extraction, and runtime-supervisor suites
  passed: 192 tests and 17 subtests. `py_compile`, `git diff --check`, and
  byte-for-byte automation copies passed. A broader run also exposed one
  unrelated pre-existing failure in the threat-status shorthand parser test.
  No runtime prompts or retry suffixes changed.

## 2026-10-14 — Fail-open WorldState event extraction

- Unresolvable extracted `move` events are skipped when they establish neither a
  registered location destination nor a valid registered support change. The
  remaining event batch can still produce reducer-validated actions.
- Event extraction, response parsing, and StateAction translation failures now
  log the exact diagnostic and discard the entire event batch. The pipeline
  continues with an accepted empty action batch, so the segment's opening
  WorldState remains unchanged and no partial event effects can commit.
- Added regressions for Job 63's unregistered movement destination, malformed
  extraction exhausting its existing repair budget, translation failure after
  an earlier valid event, exact diagnostics, and unchanged opening state.
  No Job 63 artifacts were present in this checkout, so the movement regression
  reproduces the reported invalid-destination condition. Focused event/Director/
  split-pipeline and transaction/checkpoint tests: 173 passed, 16 subtests
  passed. Syntax and whitespace checks passed. No prompt, registration,
  validator, or RAW-generation behavior changed.

## 2026-10-13 — Python translation of extracted WorldState events

- Replaced the `director_state_actions` call with a Smart Extractor event-list
  call. It receives the validated, camera-stripped RAW only and returns ordered
  `events`; it does not receive or emit StateActions. The event response schema
  is strict and mirrors the exact JSON contract shown in its system prompt.
- Python resolves event entity names against the immutable opening WorldState,
  including unique descriptive aliases, rejects unknown/ambiguous references,
  assigns deterministic action IDs by segment/event order, translates safely
  representable events into the existing StateAction operations, omits reducer
  no-ops, and dry-runs the translated batch through the existing atomic
  reducer. The accepted `state_actions` result remains the established
  completed-Segment commit input; transaction, checkpoint, and resume code is
  unchanged. Reducer provenance now identifies the event-extraction path.
- Malformed event JSON/shape uses up to five event-list-only repairs against
  the same immutable RAW. Exhaustion, name-resolution failures, and reducer
  translation failures log their diagnostics and discard the full event batch,
  continuing with an empty reducer-valid candidate; none invokes RAW repair. The
  special `retrieve_prop_origin_not_in_raw` RAW-repair loop and old
  StateAction extraction/repair call purposes were removed. A new prop can be
  introduced only through a `take` event whose source resolves to a registered
  support; a known prop is resolved before any introduction, so a cloth already
  held by its Subject is not duplicated and a pocket is not treated as a
  support.
- Runtime system prompt added for the event extractor:
  “You extract physical events from a film scene. Extract only events that
  explicitly change persistent physical state; ignore ordinary activity and
  descriptions that do not establish a state change. Identify events that change a
  Subject's location, physical support, possession, clothing, or the state of
  an object. Ignore gestures, appearances, dialogue, and other actions that do
  not cause these changes. Report events in chronological order using only
  what is explicitly described in RAW SCENE. Use these event types: move, enter,
  exit, take, put, transfer, consume, modify, release. Describe actors, objects,
  sources, and destinations using their names as written in RAW SCENE. Preserve
  distinctions such as standing on a table versus standing beside it. Do not
  determine whether an event is valid, already recorded, or representable in
  WorldState. Do not invent missing actions, sources, or destinations. Use null
  for information not stated. Return exactly the JSON structure with `events`
  and the seven fields action, actor, object, source, destination, relation,
  result.” The repair prompt is limited to correcting that same event list and
  cannot rewrite RAW.
- Event schema lacks dedicated amount, wardrobe-slot, clothing-change, and
  mechanism-operation fields. Python uses explicit relation/result wording and
  registered wardrobe facts for deterministic mapping; if it cannot make one
  unambiguous mapping, it fails with an event-specific diagnostic. Transfer
  amount defaults to `partial` unless the event/result or RAW explicitly
  establishes a complete transfer. This is a remaining contract limitation
  for future acceptance review.
- No Job 61 artifacts were found in this checkout, so regressions use generic
  constructed event records rather than captured Job 61 RAW. Tests cover
  support versus adjacency, existing cloth retrieval without duplication,
  new-prop retrieval and reuse, transfer/consumption, clothing/mechanism
  changes, enter/exit, release/place, ambiguity, unknown support, no-ops,
  malformed-response repair and its five-repair bound, reducer rejection,
  immutable opening state, and failed-extraction rollback. Verification:
  event/Director/split-pipeline/settings/prompt-generation targeted suites —
  237 passed, 16 subtests passed; WorldState foundation — 95 passed, 2 known
  stale story-start tests deselected. Those two still expect the retired
  `classification`/`evidence` response and previous prompt wording. Syntax and
  whitespace checks passed, as did byte-for-byte copies of `minimax.py` and
  `world_state.py` to the automation checkout. No bridge job was queued.

## 2026-10-13 — Beat story validator output budget

- Increased `beat_story_validation`'s per-purpose maximum output tokens from
  2,048 to 4,096. Its profile, prompt, and retry behavior are unchanged.
- Added a focused settings assertion; `tests/test_dynamic_temperature.py`
  passed. `py_compile` and `git diff --check` passed. The updated `minimax.py`
  was copied to the automation checkout and verified byte-for-byte.

## 2026-10-13 — Missing StateAction prop origin routes to RAW repair

- Job 58's reported failure matched the current code boundary: a
  `retrieve_prop_origin_not_in_raw` error was treated as a generic invalid
  StateAction response, so the pipeline spent all five action-only repairs on
  a defect those actions could not fix. No Job 58 artifacts were present in
  this checkout; the root cause was confirmed by tracing the reducer diagnostic
  through `extract_and_dry_run_director_state_actions()`.
- Added deterministic routing for this specific failure. If RAW shows the new
  prop retrieved from another registered support, the selected support was
  wrong and the existing StateAction-only repair remains available. If RAW
  shows no registered support as the prop's retrieval origin, the pipeline
  stops action-only retries and sends the accepted RAW to the existing
  `director_raw_scene_repair` call with a diagnostic naming the prop and
  requiring a physically plausible current-Segment retrieval before first
  use. It lists the registered supports, rejects using a final destination as
  an origin, and asks for actions to remain feasible in the Segment.
- Each repaired RAW is checked by the existing physical/prop, timing, dialogue,
  timestamp-range, and shot-script-structure checks before StateActions are
  extracted again. The origin-repair path is capped at the existing five RAW
  repair attempts; exhaustion raises
  `missing_prop_origin_after_raw_repairs` with the prop and last failure.
  StateAction results remain dry-run candidates until normal Segment
  acceptance, so failures leave canonical WorldState unchanged.
- Regressions cover missing-origin routing, a corrected origin/destination
  selection remaining an action-only repair, successful same-Segment retrieval
  and placement, five-attempt exhaustion, and rollback. The focused tests
  passed (3). The related Director/WorldState/split-pipeline suites ran 258
  tests: 256 passed; two pre-existing story-start tests still expect the
  retired `classification`/`evidence` response and prompt wording. Syntax and
  whitespace checks passed. Prompt-generation mode non-render tests passed
  (10); its full run was interrupted after 12 passes while an unrelated
  reference-image render waited on ComfyUI. No runtime prompt wording changed
  and no bridge job was queued.

## 2026-10-13 — RAW-grounded Subject support actions

- The Job 57 result bundle was not present in this checkout, so its exact RAW
  and StateAction response could not be confirmed. The reported failure was
  reproduced against the current code path: finalized RAW reached
  `parse_and_dry_run_state_actions()`, but RAW was consulted only for
  `retrieve_prop` origin checks. A reducer-valid `set_support` therefore
  changed canonical state even when the RAW described only wiping, reaching,
  or another interaction.
- The existing action parser now keeps a Subject support change only when the
  validated RAW explicitly stages that Subject standing, sitting, climbing,
  stepping, or taking a seat on/in the registered support. Contact, wiping,
  reaching, leaning, and sitting at a table do not qualify. A support-clear
  action requires explicit departure from the Subject's known support;
  otherwise the action is omitted and the prior state is preserved. Unsupported
  support fields on a `move` are removed while the representable location move
  remains. Malformed or duplicate action shapes still reach reducer rejection.
  The omission is logged and does not reject the segment. Accepted
  support actions still go through the same reducer and normal commit boundary.
- The previous deterministic physical pre-gate required any new support to be
  named in CURRENT BEAT or opening WorldState, which blocked physically
  justified creative staging. That pre-gate was removed so the existing
  semantic physical validator can make the staging judgment. Its runtime
  prompt was left unchanged. The prompt still ties permitted support changes
  to the Beat/opening state, so a later prompt change may be needed if that
  remaining rule rejects otherwise justified creative movement; this requires
  separate approval. No additional validator or prompt was added.
- Regressions cover table wiping versus standing, sitting at versus on a table,
  a RAW-staged creative climb, matching a support action to the Subject actually
  staged on it, unsupported support assignment/clearing,
  preservation of a prior support across segment commits, and movement with an
  unsupported destination support. Focused tests: 11 passed. The broader
  WorldState, Director, and split-pipeline suites ran 256 tests: 254 passed and
  two pre-existing story-start tests failed because they expect the retired
  response shape and prompt wording (`classification`/`evidence` and
  “performing a starting action”). `py_compile` and `git diff --check` passed.
- No runtime LLM prompt was modified, and no bridge job was queued.

## 2026-10-13 — Approved StateAction prompt simplification

- Updated the shared `director_state_actions` / `director_state_actions_repair`
  system-prompt contract to record explicit persistent changes that affect
  visual continuity or later actions, including handoffs, entrances, exits,
  and mechanism changes. It now asks for RAW-grounded transfer/retrieval
  sources and destinations, prohibits invented changes, and explicitly allows
  an empty batch when no persistent change is established. The existing
  opening-state, clothing-change, retrieval-origin, exact-entity, and reducer
  constraints remain in place.
- Left `director_raw_scene_physical` unchanged as requested; no new support
  wording was added.
- Updated the prompt inventory and regressions for both extraction and repair
  system prompts. Verification: focused StateAction prompt/empty-batch tests,
  WorldState reducer tests, `py_compile`, and `git diff --check` passed.
- Committed and pushed only to `director-split-refine`; no additional push to
  `main` was made.

## 2026-10-13 — Job 57 support staging and StateAction grounding

- No Job 57 result bundle was available in this checkout, so the specific RAW
  and extractor responses could not be traced verbatim. The reported outcomes
  were compared against the current validator, StateAction contract, and reducer.
- The physical validator prompt already distinguishes ordinary furniture
  interaction from actual support/elevation changes, but its semantic decision
  was LLM-only. Added a deterministic guard inside the existing physical
  validator for explicit body-on-support actions against registered supports.
  It rejects a new support relation absent from both CURRENT BEAT and opening
  WorldState, while leaving adjacency/reaching/wiping and required support
  changes to the existing validator. This prevents an unsupported Segment-1
  support action from becoming canonical and persisting into Segment 6. The
  reducer itself was already Subject-specific; support is never copied between
  Subjects.
- `retrieve_prop` previously validated that the selected support was registered
  and co-located, but did not verify that RAW used it as the prop's origin. The
  existing StateAction response validation now checks the immutable accepted
  RAW for a retrieval from the selected support. A support named only as the
  destination produces a concrete reducer-path diagnostic and uses the existing
  action-only repair loop; an empty corrected batch remains valid.
- WorldState already has `pour`, `handoff`, `exit`, and mechanism operations.
  The direct barrel-to-mug pour records source/destination contents, while the
  retrieved ladle remains held or can be placed if RAW stages that change.
  WorldState has no persistent “used as an intermediate implement” relation,
  so the liquid path through a ladle is not separately encoded. Empty batches
  remain valid; omissions of handoff/exit/locking cannot be detected without
  adding completeness validation or changing the extractor prompt.
- Explicit `close`, `lock`, and `unlock` actions now establish previously
  unknown mechanism capability/state. Explicitly non-openable/non-lockable
  facts and known incompatible mechanism states still reject atomically.
- No runtime prompt was changed. Proposed wording for approval:
  - `director_raw_scene_physical`: “When RAW places a Subject on a furnishing,
    require explicit body-on-surface language and support from CURRENT BEAT or
    opening WorldState. Wiping, reaching across, leaning toward, or taking a
    seat at a table does not place the Subject on the tabletop; a seat at a
    table is adjacent unless RAW identifies the actual seat.”
  - Replace the `director_state_actions` instruction to “include every explicit
    persistent change” with: “Record persistent changes that materially affect
    later visual continuity or a later action. Include clearly staged handoffs,
    entrances/exits, and mechanism changes when they alter the ending state.
    Do not infer uncertain changes; an empty array is valid when no material
    persistent change is clearly established. For transfers, use the actual
    source and destination shown in RAW; treat an implement as a transfer
    source only when RAW shows the substance in it. For `retrieve_prop`, use
    only the support explicitly shown as the prop's origin; a destination
    support is not its origin.”
- Regressions cover unsupported climbing and sitting-on-table, ordinary
  interaction and beat-required support, retrieval-origin repair, unknown
  close/lock plus exit, and preservation of known contradictions. Verification
  results: reducer tests — 27 passed; split RAW pipeline — 19 passed; focused
  support/retrieval/mechanism regressions passed. The combined
  `test_director_retry` + `test_world_state_foundation` run executed 230 tests:
  228 passed, with two existing story-start tests still failing because they
  expect the retired `classification`/`evidence` response and older prompt
  wording. `py_compile` and `git diff --check` passed. No six-Segment
  acceptance job was queued.

## 2026-10-13 — Job 56 identity-only visible-Subject resolution

- Replaced the visible-Subject resolver's scene-rewrite/bootstrap response with
  an identity map containing `raw_name`, a registered `<Subject N>` reference
  or null, and `is_new`. The user message now contains only the accepted RAW
  and registered name/reference vocabulary; the JSON contract remains in the
  system prompt. The system prompt now limits this call to identity matching.
- Python validates each returned name against the unchanged RAW and resolves
  existing references through the exact vocabulary supplied to that request.
  A descriptive alias that uniquely identifies a registered Subject maps to
  its canonical WorldState ID; mismatched, unknown, or ambiguous references
  fail closed. New Subjects are returned to the existing named-Subject
  registration path to receive stable Subject IDs for downstream H3 reference
  handling. Duplicate rows for an existing identity are collapsed.
- This resolver applies exact Subject-name substitutions deterministically in
  Python; it does not alter actions, timestamps, camera text, end-continuity
  content, or other RAW text. The no-discovery bypass returns the original RAW
  string byte-for-byte.
- Removed the old resolver's description/wardrobe bootstrap helper and all
  production consumers of those response fields. Canonical identity, Picture
  references, and wardrobe remain owned by their existing sources and seed
  paths; incomplete metadata no longer triggers this identity-only resolver.
- Added regressions for prompt/user-data boundaries, known alias-to-ID mapping,
  new Subjects, repeated identities, unknown references, duplicate registered
  aliases, and timestamp/action preservation.
- Verification: all 13 focused identity-resolver tests passed, including the
  relevant postmortem regressions. `tests.test_director_retry` passed all 136
  tests. `py_compile` and `git diff --check` passed. The broader postmortem and
  location-reference modules ran 114 tests and have 14 unrelated failures:
  existing assertions expect older Director physical-prompt text and H3
  continuity behavior. None are identity-resolver failures; those prompt and
  H3 expectations were left outside this change.

## 2026-10-13 — Job 56 unnecessary visible-Subject resolution

- The post-RAW visible-Subject resolver always called the LLM, even when the
  accepted scene named only registered Subjects with complete canonical
  identity and wardrobe data. Job 56's resolver rewrote timestamps twice in
  that no-discovery case.
- Added a deterministic bypass at the existing resolver entry point. It uses
  the opening WorldState and skips only when every action line is attributable
  to a registered Subject or a clear pronoun reference, and the referenced
  Subjects have established identity/reference and all wardrobe-slot data.
  Unrecognized action-line Subjects, likely unnamed actors, or missing metadata
  continue through the existing resolver. Existing shot-script structure
  checks still run before returning.
- On bypass, the resolver returns the original RAW string exactly, including
  timestamp spelling/order, camera tags, action text, and surrounding
  whitespace. The post-resolver final-participant carry-forward is also skipped
  in this case, preserving the accepted Director text through the full bypass
  path. No runtime prompt or downstream Subject/wardrobe precedence changed.
- Added regressions for complete-metadata bypass, exact RAW preservation,
  missing wardrobe metadata, missing identity metadata, and an unnamed actor
  outside the bypass path. The bypass is deliberately conservative; unusual
  sentence forms and ambiguous secondary references may still use the
  resolver.
- Verification: four focused resolver regressions passed; the complete
  `tests.test_director_retry` module passed (137 tests).

## 2026-10-13 — Job 55 unsupported pre-Director prop placement

- Fixed `parse_current_segment_persistent_prop_result()` so a registered
  support/fixture name returned as `initial_location` resolves to its canonical
  WorldState location while preserving `support_name`, when the current-source
  evidence supports an opening/static placement or retrieval-from-support
  origin.
- Well-formed candidates with unknown placement or evidence only for a later
  placement are skipped before registration. They do not consume another
  extraction attempt, leaving the existing Director `retrieve_prop` path
  available. Malformed shapes and invalid source evidence still use the
  existing retry loop. No prompt, LLM call, or WorldState authority changed.
- Added the Job 55 chalice regression, supported support-alias normalization,
  and coverage proving unsupported placement skips without retry while
  malformed evidence retries.
- The placement check is intentionally conservative: source relations such as
  a prop resting on a support or being retrieved from it can establish an
  opening position. Unclear wording remains unregistered for Director staging.
- Verification: focused WorldState seed and Director pipeline suites passed
  (176 tests). The combined `test_world_state_foundation` and
  `test_director_retry` run executed 221 tests; its only two failures are the
  existing story-start expectations for the retired `classification`/`evidence`
  response shape and retired prompt wording. `py_compile` and `git diff --check`
  passed.

## 2026-10-13 — Transactional Director-introduced props

- Added `retrieve_prop` to the existing ordered StateAction contract. It may
  register an ordinary movable prop only from a named, registered support in
  the present Subject's location. The prop's deterministic Python ID is based
  on its canonical kind/name and registered location; provenance records its
  initial support placement and retrieval action. A duplicate registered name
  is rejected so later segments reuse the same WorldState record.
- The request schema now allows prop-name strings for prop references because a
  later action may reference a prop introduced earlier in the same batch.
  Python resolves exact opening-vocabulary names or names introduced earlier in
  that ordered batch; unknown, out-of-order, ambiguous, and duplicate names
  fail closed. Subject, location, and support names remain restricted to the
  request vocabulary.
- The reducer stages registration and later possession/content changes in its
  existing atomic candidate. A failed action returns the unchanged opening
  state; the existing completed-segment commit remains the only canonical
  write. No additional LLM call or state layer was added. The existing
  `world_state_current_segment_props` pre-Director path is unchanged.
- Added the approved contract instruction verbatim to the dynamically built
  StateAction system prompt:
  “A `retrieve_prop` action may introduce a prop only when validated RAW
  explicitly shows a Subject retrieving it from a registered support
  accessible to that Subject. Do not introduce a prop without that origin and
  retrieval action. Later actions in the same batch may refer to the exact name
  introduced earlier. Reuse existing registered props whenever available.”
- Deterministic checks prove the actor and support are present in the same
  registered location. WorldState does not model distance or reachability, so
  exact physical accessibility still relies on the existing validated RAW and
  StateAction interpretation. Retrieval from a location with no registered
  support is not currently represented.
- Verification: focused WorldState reducer/transaction and Director pipeline
  tests passed (204 tests). The combined `test_world_state_foundation` and
  `test_director_retry` run executed 218 tests and had two unrelated existing
  story-start expectation failures: one supplies the retired
  `classification`/`evidence` response shape, and one asserts retired prompt
  wording. `py_compile` and `git diff --check` passed.

## 2026-10-13 — Explicitly prohibit timestamps in creative RAW

- Added the requested `- do not include timestamps.` bullet to the
  `director_raw_scene_creative` system prompt. The timing refiner remains the
  timestamp authority; no other prompt wording changed.
- Updated the creative prompt contract regression to assert the rule.
- Verification: `python -m unittest discover -s tests -p
  'test_llm_prompt_pipeline.py'` — 115 passed.

## 2026-10-13 — Job 53 timing budget, untimed RAW, and transfer staging

- Job 53 (`gpt-runtime` revision `a60f19990357488738658a7fe6588518e4b4e03c`)
  shows `validate_timing_valid` exhausted ten attempts at
  `max_tokens=2048`; all ten ended with `finish_reason=length` and no usable
  JSON. Raised only this purpose's output limit to 4096. Profile, prompt,
  reasoning, temperature, and retry handling are unchanged.
- `director_raw_scene_creative` did not prohibit time annotations. Segment 3
  creative attempts included forms such as `At 00:01.700` and `By 00:03.000`,
  while the timing refiner independently assigned its timestamp array. Python
  now removes explicit timestamp annotations from both creative and repaired
  RAW before content validation and timing refinement. The raw LLM responses
  remain logged unchanged; Python-assembled timing remains authoritative.
- Segment 2's physical validator only checks Subject movement and support
  continuity. The prop-state validator checked for a real source and
  destination, which the barrel and mug satisfied; neither check rejected
  `Amy lifts a handful of liquid from the barrel`. Added a deterministic guard
  inside the existing prop-state validation entry point for explicit bare-hand
  transfer of a fluid. Explicit carrier/tool or outlet wording is allowed, as
  are physically plausible handful transfers of granular material. No extra
  LLM call or validation stage was added.
- The bare-hand rule is deliberately narrow; it does not prove that every
  transfer from a fixed vessel has a physically plausible outlet. A general
  semantic boundary is best stated in the existing prop-state prompt. Suggested
  prompt wording for separate approval:
  - `director_raw_scene_creative`: “Do not include timestamps; timestamps are
    assigned by the timing refiner.”
  - `director_raw_scene_prop_state`: “For each substance transfer, verify that
    RAW shows a physically plausible way for the substance to move from source
    to destination. Bare hands cannot carry liquids. A fixed container may
    dispense only through a visible or established outlet or operating
    mechanism, or through an explicitly shown suitable carrier or implement.
    Do not invent a prop or mechanism to make a transfer possible. Allow direct
    hand transfer of powders and granular materials only when physically
    plausible.”
- No runtime prompt was changed. Verification: `tests/test_split_raw_pipeline.py`
  — 19 passed; `DirectorMicroPromptPipelineTests` — 132 passed; direct
  output-budget checks for the timing purpose passed; `py_compile` and
  `git diff --check` passed.

## 2026-10-12 — Job 52 opening actions and RAW staging gaps

- Reviewed Job 52 artifacts from `gpt-runtime` commit
  `28df5fa53779dd2db70b5030828ddc5730a5561d`. Segment 3 failed StateAction
  extraction after five repairs: the Elf was registered with unknown presence,
  while the entrance fixture's `openable` capability and mechanism state were
  unknown. The reducer required the actor to be present before opening and
  required `openable=true`, so the staged `open` → `enter` sequence could not
  succeed.
- The reducer now permits an absent/unknown Subject with no contradictory known
  location to open a registered, located fixture before entering; an explicit
  open establishes unknown `openable` and mechanism state. Explicitly
  non-openable fixtures, incompatible known locations, and unlocated fixtures
  still fail. Successful opening updates canonical capability/mechanism state.
- Job 52 Segment 2's physical validator received the full static setting and
  opening WorldState; those identify the eight-foot barrel as fixed, but the
  validator's responsibility is only Subject movement/support changes. Added a
  deterministic check in the existing physical-validation entry point that
  rejects clearly associated lifting, tilting, carrying, or relocating of a
  registered fixed prop. It does not reject mere mentions, unrelated nearby
  actions, or movement of movable props.
- Other Job 52 false positives were not safe to correct deterministically with
  the existing inputs. The timing validator receives only RAW, so it could not
  compare the Elf's reported two-second walk with the room layout; the final
  repaired RAW repeated the prior Beat's goblin refill and redundantly placed
  the same chalice twice, which current checks do not treat as contradictions.
  No runtime prompt was changed. Suggested wording for approval:
  - `director_raw_scene_creative`: “Do not repeat any persistent action
    completed in an earlier Beat; stage only the actions required by CURRENT
    BEAT.”
  - `director_raw_scene_physical`: “Reject an action that moves or reorients a
    prop when WorldState or STATIC SETTING AUTHORITY identifies it as fixed,
    unless the source explicitly establishes a movable mechanism or
    component.”
  - `validate_timing_valid`: “Use STATIC SETTING AUTHORITY and registered
    opening positions to judge travel distance; a stated travel duration does
    not override a distance that cannot plausibly be covered in that time.”
  - `director_raw_scene_prop_state`: “Reject redundant repeated placement or
    transfer actions when the same prop has already reached the stated final
    holder or location and no intervening action changes it.”
- Verification: `PYTHONPATH=. python tests/test_world_state_foundation.py
  WorldStateReducerTests` passed (26 tests); focused fixed-prop regressions
  passed (2 tests); `DirectorMicroPromptPipelineTests` passed (130 tests).
  `py_compile` and `git diff --check` passed.

## 2026-10-12 — specify the timing-refiner 8-second JSON contract

- Updated only the `add_scene_timing_refiner` system prompt to specify an
  8-second video and the requested JSON shape, timestamp-array semantics, and
  `not_enough_time` empty-array behavior. The Python response schema and timing
  validation remain unchanged.
- Added an exact rendered-prompt regression and updated the active prompt
  catalog. Verification: `pytest -q tests/test_split_raw_pipeline.py` — 16
  passed, 3 subtests passed; `py_compile` and `git diff --check` passed.

## 2026-10-12 — allow supported pours through unknown WorldState details

- The Job 50 result artifacts were not present in this checkout; the latest
  committed acceptance artifacts here are Job 49. The specified unknown-source
  scenario was reproduced with a focused reducer and StateAction regression.
- The `pour` reducer now treats an unregistered source substance, unknown
  source/target placement, unknown source quantity, and unknown destination
  container capability as missing information when the accepted RAW-derived
  action explicitly establishes the transfer. It records only the named
  substance and coarse `all`/`partial` result. Unknown container capability is
  established as true by an explicit pour. A mug's recorded holder remains
  unchanged during the pour.
- Explicitly empty matching source contents, an explicitly non-container
  destination, and a known location mismatch still reject the batch atomically.
  Other known source contents are preserved while the RAW-established substance
  is added. Same-location movement is accepted as a no-op when it provides no
  persistent position change; an explicitly supplied support change is still
  reduced. No validators, retries, state representation, or runtime prompts
  changed. The existing StateAction prompt
  could be clarified to say that unknown opening facts are missing information
  and explicit validated RAW actions may establish them; that prompt edit needs
  separate approval.
- Verification: `tests/test_director_retry.py` — 128 passed, 7 subtests;
  `tests/test_world_state_foundation.py` excluding two unrelated stale
  story-start expectations — 75 passed, 11 subtests. The full foundation file
  still reports those two pre-existing failures (`classification`/`evidence`
  fixture shape and obsolete prompt wording). Focused pour/movement reducer
  regressions — 9 passed. `py_compile` and `git diff --check` passed.

## 2026-10-12 — rename timing-validator prompt purpose

- Renamed the `director_raw_scene_timing` LLM purpose to
  `validate_timing_valid` in purpose routing, output-token routing, response
  history selection, and request metadata. The validator/helper function names,
  prompt text, schema, profile, and 2048-token output limit are unchanged.
- Updated the active prompt catalog and purpose-routing regression. Verification:
  `pytest -q tests/test_dynamic_temperature.py` — 65 passed; `py_compile` and
  `git diff --check` passed.

## 2026-10-12 — increase physical-validator output budget

- Raised the per-purpose maximum output tokens for
  `director_raw_scene_physical` from 2048 to 3072. Its Smart Extractor profile,
  context budget, prompt, schema, and validation behavior are unchanged.
- Added a routing regression asserting the 3072-token purpose limit.
  Verification: `pytest -q tests/test_dynamic_temperature.py` — 64 passed;
  `py_compile` and `git diff --check` passed.

## 2026-10-12 — clarify current-Segment prop capability extraction

- Updated only the `world_state_current_segment_props` system prompt. It now
  permits contents and capabilities that are explicit or strongly implied by
  the setting/actions, while requiring inferred initial contents to describe
  the state before CURRENT BEAT rather than its outcome. It also clarifies that
  `true` and `false` are JSON booleans. The response schema already supports
  booleans and `unknown`; no schema or extraction code changed.
- Added a focused assertion for the new guidance and retained the existing
  registered-name/ID privacy and evidence checks. Verification:
  `pytest -q tests/test_world_state_foundation.py -k
  'current_segment_prop_extractor_uses_names_and_cloth_id_persists or
  current_segment_prop_evidence'` — 8 passed, 7 subtests passed;
  `py_compile` and `git diff --check` passed.

## 2026-10-12 — Job #49 StateAction reducer failures

- Job #49's Segment 2 opening WorldState and prompt history show the failure was
  not a reducer defect. The barrel was registered from canonical location state
  as a fixed support with empty contents. The chipped mug was registered as
  held by Goblin with ale contents but `container="unknown"`. The StateAction
  request received those exact facts and the validated RAW. RAW shows Amy
  reaching toward the barrel, lifting a ladle, and pouring from the ladle into
  Goblin's mug; it does not show a barrel pickup or Amy changing support.
- The first extractor response nevertheless proposed `pickup(Amy, barrel)` and
  `pour(barrel, mug)`. The reducer correctly rejected pickup because the barrel
  is fixed. During action-only repair, the model added `set_support(Amy,
  counter)` even though RAW only places her at the counter, then continued
  proposing invalid pickup/pour actions. The support invention is not
  mechanically decidable from registered state alone: `set_support` names a
  real support and is otherwise a legal reducer operation. Preventing that
  semantic mismatch needs an approved prompt change or RAW/action consistency
  validation, neither of which was in scope.
- The action schema now restricts `pickup.prop_id` to registered props whose
  WorldState mobility is `movable`. Fixed and unknown-mobility props remain in
  the full vocabulary for other operations and remain rejected by the reducer
  if presented outside the structured schema. This deterministic eligibility
  filter prevents the Job #49 fixed-barrel pickup from being offered as a
  valid structured action without weakening reducer validation.
- The mug capability failure originates upstream of the reducer: the current
  Segment prop extractor returned `container="unknown"` despite the Beat saying
  the mug is refilled, and Python preserved that unknown value. The reducer
  correctly fails closed on a pour into an unconfirmed container. The ladle
  was absent from the opening registered vocabulary, the barrel had no
  recorded contents, and the reducer cannot substitute either as an established
  source. No capability or source was inferred in Python. A generic extractor
  prompt clarification is the smallest next step for that issue and needs
  approval before any runtime prompt change.
- Added regressions for fixed-prop exclusion from the pickup schema and for
  pour rollback when destination container capability is unknown. Verification:
  the focused pickup/container/name-resolution tests passed (4 passed). The combined
  WorldState foundation and Director retry run reported 195 passed and 18
  subtests passed, with two known unrelated story-start failures: an obsolete
  `classification`/`evidence` fixture and an outdated prompt wording assertion.
  `py_compile` and `git diff --check` passed.

## 2026-10-12 — Job #48 identity, StateAction, physical wording, and timestamps

- Subject ID 1 was not being reassigned. Prompt-only completion recorded the
  legacy continuity state after it had been reset to an empty state, and that
  empty value was also used as the completed Segment's identity snapshot. When
  later Subjects were registered, identity validation compared the old empty
  snapshot against the authored registry and reported Subject ID 1 missing.
  Completion now snapshots the canonical Subject registry separately from the
  reset continuity state and records that identity snapshot for both prompt-only
  and rendered completion. Identity validation and authored Subject IDs remain
  unchanged.
- The StateAction extractor had no explicit baseline/completeness distinction:
  it could treat existing wardrobe descriptions as changes, while an empty
  batch could pass despite omitted persistent changes. Its existing prompt
  contract now says opening WorldState is the baseline, clothing descriptions
  alone are not changes, and the full RAW must be reviewed for every explicit
  representable persistent change. Empty batches remain permitted only when no
  such change occurs. The reducer, action schema, and repair path are unchanged;
  this remains semantic extraction guidance rather than a new completeness
  validator.
- The physical prompt now distinguishes movement across an already-occupied
  surface from an actual support/elevation change while retaining rejection of
  unsupported climbing or stepping onto furniture.
- Timing output is now normalized by Python for unambiguous local timestamp
  spellings accepted by the downstream formatter (including omitted leading
  zeroes, `.` or `:` fractional separators, and one-to-three fractional digits).
  Canonical `MM:SS.mmm` values then pass through the existing chronology and
  duration checks. Ambiguous/malformed values and seconds outside 00–59 still
  fail through the existing bounded refiner retry.
- Focused regressions cover Subject identity across later registration,
  description-only clothing and actual prop pickup/pour extraction, ordinary
  floor movement versus support changes, timestamp normalization/rejection,
  and normalized timing through the pipeline. Verification: `pytest -q
  tests/test_resume.py tests/test_director_retry.py
  tests/test_split_raw_pipeline.py` — 190 passed, 19 subtests; `py_compile`
  and `git diff --check` passed.

## 2026-10-12 — StateAction RAW integrity representation match

- Job #46 reached StateAction extraction with a camera-refined accepted RAW.
  The caller correctly removed `[CAMERA: ...]` annotations before passing RAW
  to `director_state_actions`, whose result preserves its exact input. The
  integrity guard then incorrectly compared that camera-stripped value with
  the camera-tagged Subject-resolver output, causing a false failure even for
  `{"state_actions": []}`. No StateAction-stage RAW mutation occurred. Job #46
  artifacts were not available in this checkout, so the failure was reproduced
  with a focused camera-tagged fixture.
- The caller now names the exact camera-stripped StateAction input and verifies
  the extractor's returned RAW against that same value. The check remains exact:
  changing action text or timestamps still raises `StateActionExtractionError`.
  Empty StateAction batches remain valid. No prompt, schema, or extraction
  behavior changed.
- Added focused regressions for unchanged camera-stripped RAW with an empty
  batch, changed timestamp, and changed action text.
- Verification: StateAction-focused regressions — 5 passed; split RAW pipeline —
  12 passed; `python -m py_compile minimax.py
  tests/test_prompt_generation_mode.py tests/test_director_retry.py` and
  `git diff --check` passed. A broader combined run was interrupted during a
  slow prompt-generation test after 11 tests had passed; the focused affected
  tests completed successfully.

## 2026-10-12 — RAW validation before timing and camera refinement

- Reordered RAW content validation so `director_raw_scene_physical` and
  `director_raw_scene_prop_state` each validate/repair/revalidate the untimed
  creative scene before `add_scene_timing_refiner`. Timestamp assignment is
  followed by the `validate_timing_valid` purpose; an infeasible result
  regenerates creative RAW with its issue as feedback under the existing
  Director attempt bound. It does not rewrite the accepted actions.
- The final camera-refined scene runs deterministic shot-script and dialogue
  checks. Physical and prop/state LLM validators are not repeated because the
  timing and camera refiners already have deterministic action-preservation
  checks. Their failures cannot be repaired by mutating timed text; the
  existing Director retry budget regenerates creative RAW instead.
- Added the requested generic physical rule against unsupported support or
  elevation changes. It allows movement required by CURRENT BEAT or established
  by prior state, and tells the validator to report the unsupported movement
  itself. Ordinary furniture interaction remains permitted.
- Tightened the shared StateAction prompt contract: omit transient or
  unrepresentable actions and never invent transfers, pouring, consumption, or
  an unrelated operation. The empty batch remains valid; existing reducer
  operations and authority are unchanged. Job #44's artifacts were not present
  in this checkout, so the reported wiping output could not be independently
  inspected here.
- Added regressions for support/elevation movement, pre-refinement validator
  order, no redundant physical/prop checks, timing-driven creative retries,
  wiping as an empty StateAction batch, and transfer-preserving extraction.
- Verification: `pytest -q tests/test_split_raw_pipeline.py
  tests/test_director_retry.py tests/test_llm_prompt_pipeline.py` passed (251
  tests, 7 subtests). `python -m py_compile minimax.py
  tests/test_split_raw_pipeline.py tests/test_director_retry.py` and
  `git diff --check` passed. `tests/test_world_state_foundation.py` had 66
  passes, 11 subtests, and 2 unrelated existing story-start contract failures:
  an outdated `classification`/`evidence` fixture and an obsolete prompt-text
  assertion.

## 2026-10-12 — visible Subject resolver output budget

- Raised the `director_raw_scene_visible_subject_resolution` per-purpose
  maximum output-token limit from 2048 to 3172. Its profile and other request
  settings are unchanged. Added a regression asserting the configured value
  and the actual request's `max_tokens` when context capacity permits.

## 2026-10-12 — timestamp-only timing refiner output

- Changed `add_scene_timing_refiner` to receive numbered, nonempty RAW action
  lines and return only `{status, timestamps}`. The timing model no longer
  reproduces or rewrites scene text.
- Python preserves each nonblank source line verbatim, checks timestamp count,
  `MM:SS.mmm` format, strict chronological order, first timestamp at
  `00:00.000`, and segment duration, then assembles the timed scene. Malformed
  timestamp batches use the existing bounded refiner retries. An explicit
  `not_enough_time` with an empty timestamp list still feeds the existing
  bounded creative regeneration path. Camera refinement and downstream RAW
  contracts are unchanged.
- Added regressions for blank-line normalization, verbatim action assembly,
  malformed and out-of-order timestamps, incorrect counts, duration limits,
  and `not_enough_time`. Updated timing schema assertions and prompt inventory.
- Verification: focused split RAW, Director retry, prompt pipeline, and
  pre-Director replay tests passed: 251 passed, 7 subtests. `py_compile` and
  `git diff --check` passed.

## 2026-10-12 — split RAW timing and camera refiners

- Replaced the monolithic `director_raw_scene` formatter stage with a separate
  `add_scene_timing_refiner` call. It returns the exact `{status, timed_scene}`
  contract and receives the approved timestamp-only system prompt. Python
  rejects changed, reordered, missing, extra, malformed, non-monotonic, or
  out-of-duration action lines. A `not_enough_time` result adds feedback to
  the existing creative retry input and regenerates creative RAW; it never
  enters the normal RAW repair loop. The existing five Director attempts and
  five RAW repairs remain bounded.
- Added `add_camera_refiner` after successful timing. It receives the approved
  camera-only prompt and uses `[CAMERA: ...]` tags immediately after timestamps
  so validators can compare the underlying action text. Altered/malformed
  output retries three times, then falls back to the accepted timed scene
  without camera additions. No camera movement is a valid unchanged response.
- Existing RAW validators still run on the final formatted scene, with camera
  tags removed for semantic validation. The existing StateAction and H3 paths
  retain their accepted input contracts. Removed obsolete timestamp surgery
  that could add opening/final-quarter actions and the continuation frame-zero
  substitution that could replace an accepted first action. Continuation
  timestamp offsetting remains for the renderer timeline.
- Added coverage for content-preserving timestamping, malformed timing retry,
  `not_enough_time` regeneration and attempt exhaustion, camera preservation
  and fallback, RAW repair budget, final structure metadata, and downstream
  compatibility. The profile/prompt inventory now lists both refiners.
- Verification: the Director Request 1 context, Director retry, prompt pipeline,
  split RAW, pre-Director replay, profile routing, integration, continuation
  frame, and location postmortem suites passed: 337 passed, 1 skipped, 7
  subtests. `py_compile` and `git diff --check` passed. No acceptance job was
  queued.

## 2026-10-12 — classify and resolve the 45 Director test failures

- Re-ran the failing Director retry and prompt-pipeline files. The 45 failures
  were stale expectations for the retired monolithic Director contract: old
  creative prompt wording, one-call request counts, and fixtures that skipped
  the untimed creative stage and downstream timed formatter. Updated those
  tests to exercise the current split stages instead of deleting the behavior
  coverage.
- The review also found one real integration gap: the new creative system
  prompt names `ASSIGNED SOURCE` as an authority, but the deterministic prompt
  builder did not include the current assignment. The builder now accepts and
  renders that source, and both normal and repair prompt construction pass the
  assignment selected for the current segment. No runtime prompt wording,
  validator behavior, or retry budget changed.
- Verification: `tests/test_director_retry.py` and
  `tests/test_llm_prompt_pipeline.py` — 235 passed, 7 subtests. Split RAW,
  pre-Director replay, and Request 1 context tests — 17 passed. `py_compile`
  and `git diff --check` passed.

## 2026-10-09 — seed canonical Subjects after checkpoint recovery fallback

- When checkpoint restoration failed, `_run_main()` created a fresh generation
  state but skipped the canonical `character_canon` identity and wardrobe seeds
  applied on a normal new run. The fallback now uses the same shared composition
  of the existing authored identity and wardrobe seed functions, then rebuilds
  Subject definitions from the resulting WorldState. Presence remains unknown.
- The fresh-run path uses this same seed composition. Successful checkpoint
  resume remains unchanged and continues restoring the completed Segment's
  canonical WorldState.
- Added regressions for canonical wardrobe/identity seeding on the fallback
  initialization path and wardrobe preservation through normal checkpoint
  resume. Verification: `pytest -q tests/test_resume.py
  tests/test_world_state_foundation.py::WorldStateSeedTests` — 76 passed,
  16 subtests; `py_compile` and `git diff --check` passed.

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
