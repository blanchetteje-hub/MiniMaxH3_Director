# LLM Prompt / Call Inventory

**Branch audited:** `world-state-rebuild` (2026-10-09). **Primary source:** `minimax.py` and `story_planner.py`, including the text request profile map and observed call sites. This is an **index of LLM calls, not verbatim user/system prompt text**: runtime prompts remain user-owned in source. Do not edit prompts merely to make the descriptions here match.

**How to read:** `purpose` selects one of four immutable sampling/reasoning profiles. Context budgets and output-token limits are maintained separately per purpose. Unknown text purposes use `EXTRACTOR_LLM_SETTINGS` plus the standard context/output defaults. `visual_end_state` uses a separate multimodal vision request. A listed purpose does not guarantee execution on every run; some calls are conditional, diagnostic, compatibility, or legacy paths.

## Call catalog

| `purpose` identifier | Settings constant | Purpose | Passed in (summary) | Returns (summary) |
| --- | --- | --- | --- | --- |
| `story_expansion` | `SMART_CREATIVE_LLM_SETTINGS` | Expand the source into filmable narrative | Source story/summary and expansion guidance | Expanded story text |
| `story_to_beats` | `SMART_EXTRACTOR_LLM_SETTINGS` | Derive ordered filmable beats | Expanded story and source/beat budget context | Structured beats |
| `story_to_beats_repair` | `SMART_EXTRACTOR_LLM_SETTINGS` | Repair invalid beat derivation | Original story, draft beats, specific validation issue | Corrected beats |
| `character_canon` | `SMART_CREATIVE_LLM_SETTINGS` | Establish stable configurable character facts | Story, predefined Subjects and configured canon fields | Canonical character facts |
| `story_subject_wardrobe_extract` | `SMART_CREATIVE_LLM_SETTINGS` | Determine one Subject's canonical appropriate wardrobe | Expanded story, Subject identity, appearance and setting | Structured/canonical wardrobe for that Subject |
| `story_location_extract` | `EXTRACTOR_LLM_SETTINGS` | Identify story locations and initial setting | Expanded story and established story context | Overall and opening location information |
| `static_setting_extract` | `EXTRACTOR_LLM_SETTINGS` | Extract permanent location facts without action-only objects | Expanded story and named location context | Static setting description |
| `story_setting_spatial_refine` | `SMART_CREATIVE_LLM_SETTINGS` | Lay out a physically coherent static environment | Extracted setting and location constraints | Spatially refined setting text |
| `story_setting_extract` | `SMART_EXTRACTOR_LLM_SETTINGS` | Serialize canonical location geometry and text | Refined static layout and source location details | Location-state JSON plus matching literal prose |
| `director_raw_scene_subject_resolution` | `SMART_EXTRACTOR_LLM_SETTINGS` | Identify animate Subjects present from the beginning | Complete finalized beat list, known Subjects and opening context | Functional names and supported initial states |
| `registered_subject_story_start_presence` | `SMART_EXTRACTOR_LLM_SETTINGS` | Classify one authored Subject's opening presence | Full beats/story and one registered Subject with source evidence | Present/absent/unknown classification with evidence |
| `world_state_current_segment_subjects` | `SMART_EXTRACTOR_LLM_SETTINGS` | Register identities needed for the current Beat before RAW | Current Beat/source, registered Subject context | New current-segment identity records; no inferred entry/presence |
| `world_state_current_segment_props` | `SMART_EXTRACTOR_LLM_SETTINGS` | Identify explicitly needed persistent props for this Beat | Current Beat/source and registered Subject, prop, location/support vocabulary | Narrow prop registration candidates and initial placement |
| `source_unit_state_effects` | `SMART_EXTRACTOR_LLM_SETTINGS` | Extract explicit durable source effects | One exact source unit and state context | Typed persistent effects, not activity alone |
| `source_unit_terminal` | `SMART_EXTRACTOR_LLM_SETTINGS` | Classify whether a source unit is terminal | Story and current source unit | Binary terminal decision |
| `source_unit_hard_reset` | `SMART_EXTRACTOR_LLM_SETTINGS` | Classify whether a new source unit resets story state | Adjacent source units | Binary hard-reset decision |
| `source_unit_split_gate` | `SMART_EXTRACTOR_LLM_SETTINGS` | Decide whether a source unit can be split at an enumerated boundary | Source unit and legal cut candidates | Binary split decision |
| `source_unit_cut_choice` | `SMART_EXTRACTOR_LLM_SETTINGS` | Select a Python-enumerated legal source cut | Source unit and exact candidates | Selected cut candidate |
| `source_unit_visible_responsibility` | `SMART_EXTRACTOR_LLM_SETTINGS` | Decide whether a source unit requires a concrete visible event | One source unit | Binary visible-event decision |
| `source_unit_local_relation` | `SMART_EXTRACTOR_LLM_SETTINGS` | Relate adjacent source units for grouping | Two adjacent source units | MERGE or NEW_TASK |
| `macro_arc_create` | `SMART_CREATIVE_LLM_SETTINGS` | Create a chapter/arc plan | Authoritative story and allocation constraints | Arc/chapter plan |
| `macro_arc_validate` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check arc/source responsibility | Source text and candidate arc | Validity and specific issue |
| `macro_arc_majority_validate` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check explicit majority/repetition allocation | Source emphasis and candidate chapter/beat plan | Majority/repetition validity assessment |
| `macro_arc_majority_tail_repair` | `SMART_CREATIVE_LLM_SETTINGS` | Repair majority-process placement | Affected arc portion and validator feedback | Corrected arc tail |
| `macro_arc_repair` | `SMART_CREATIVE_LLM_SETTINGS` | Repair an arc defect | Story, candidate arc and validation failure | Revised arc plan |
| `beat_generation` | `SMART_CREATIVE_LLM_SETTINGS` | Write assigned visible Beats | Authoritative source, assigned events, budget, Subject canon and relevant prior context | Specified number of Beats |
| `beat_validation` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check source coverage, fidelity, and beat boundaries | Source/assigned events, candidate Beats, applicable canonical state | Valid/invalid with first issue |
| `beat_destination_presence_extract` | `EXTRACTOR_LLM_SETTINGS` | Extract source-unit destination presence | Source unit and relevant established context | Structured destination/presence facts |
| `beat_instruction_review` | `SMART_EXTRACTOR_LLM_SETTINGS` | Review beat instructions for clarity and usable staging | Beat instructions and applicable source context | Specific issue or approval result |
| `beat_finite_endpoint_extract` | `EXTRACTOR_LLM_SETTINGS` | Observe whether finite assigned activity has completed | Exact finite assignment and candidate Beat | Complete/ongoing/not-applicable classification |
| `beat_coherence_validation` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check physical and causal plausibility inside a Beat | Accepted-candidate Beat, source and relevant known state | Coherence validity and issue |
| `beat_repair` | `SMART_CREATIVE_LLM_SETTINGS` | Repair a specific assigned Beat | Original assignment, failed Beat and validator issue | Corrected Beat |
| `accepted_beat_state_extract` | `EXTRACTOR_LLM_SETTINGS` | Capture auxiliary post-Beat persistent facts | Accepted Beat and prior state/source context | Structured state patch |
| `director_raw_scene` | `SMART_CREATIVE_LLM_SETTINGS` | Stage the current Beat as timed RAW, with reducer actions | Assigned source, current/next Beat, opening continuity, static setting, prop state and registered WorldState vocabulary | Timed RAW scene, completion fields, registered state_actions for dry-run |
| `director_raw_scene_physical` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check RAW spatial/action order | Current Beat, RAW, previous shot end, known Subjects and fixed setting | Physical validity and concrete issue |
| `director_raw_scene_prop_state` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check RAW object provenance and transfers | Current Beat, RAW, previous shot end, prop ledger and static setting | Prop/state validity and issue |
| `director_raw_scene_timing` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check feasible sequential timed actions | Timed RAW scene and segment duration contract | Timing validity and issue |
| `director_raw_scene_pronoun_resolution` | `EXTRACTOR_LLM_SETTINGS` | Disambiguate person pronouns without rewriting RAW | Accepted RAW and established Subject names | RAW with unambiguous pronouns replaced or unchanged RAW |
| `director_raw_scene_visible_subject_resolution` | `SMART_EXTRACTOR_LLM_SETTINGS` | Name new visible foreground animate participants | Accepted RAW and persistent Subject definitions | RAW with stable functional Subject labels plus identity metadata |
| `director_h3_soundscape` | `CREATIVE_LLM_SETTINGS` | Extract audible ambience and effects | Accepted RAW scene and prior relevant audio context | One overall_soundscape value |
| `director_h3_music` | `CREATIVE_LLM_SETTINGS` | Choose or continue the underscore | Current scene, context and previous segment music | One non_diegetic_music cue |
| `continuity_attachment_extract` | `EXTRACTOR_LLM_SETTINGS` | Identify meaningful physical object attachments | Continuity/scene text, Subjects and known objects | Attachment relationships or filtered object facts |
| `continuity_combined_reduced_state` | `SMART_EXTRACTOR_LLM_SETTINGS` | Extract a compact changed-state delta | Committed continuity, newest segment, registered Subjects and relevant Beat context | Structured continuity delta |
| `continuity_state_validation` | `SMART_EXTRACTOR_LLM_SETTINGS` | Check proposed continuity against newest RAW | Newly extracted continuity, established state and newest segment | Validation feedback for delta retry |
| `continuity_phase_2_h3_opening` | `EXTRACTOR_LLM_SETTINGS` | Select compact immediate H3 opening facts | Canonical/observed state, active Subjects and scene context | Concise opening continuity facts |
| `combined_continuity` | `SMART_EXTRACTOR_LLM_SETTINGS` | Update combined legacy continuity | Newest accepted prompt, prior continuity and Subject/prop context | Updated structured continuity observation |
| `subject_continuity` | `SMART_EXTRACTOR_LLM_SETTINGS` | Summarize persistence of Subjects | Recent segment outputs and known Subject definitions | Subject-state continuity summary |
| `final_h3_action_preservation` | `SMART_EXTRACTOR_LLM_SETTINGS` | Compare RAW action with final H3 action | Paired same-timestamp RAW/H3 micro-actions | PRESERVED / OMITTED / CHANGED verdict |
| `json_repair` | `EXTRACTOR_LLM_SETTINGS` | Repair malformed JSON without changing intended semantics | Invalid LLM JSON, target schema/parse issue | Parseable corrected JSON |
| `director_h3_formatter` | `EXTRACTOR_LLM_SETTINGS` | Legacy/optional H3 format translation | Accepted RAW, Subject definitions and H3 formatting contract | Formatted H3 fields, where still invoked |
| `director_raw_scene_coherence` | `SMART_EXTRACTOR_LLM_SETTINGS` | Legacy semantic RAW coherence evaluation | Beat/RAW and established opening context | Coherence verdict and issue, if invoked |
| `visual_end_state` | `VISION_LLM_SETTINGS` | Observe visible final-frame continuity (separate vision path) | Rendered segment image(s) and observed-state extraction instructions | Visual end-state observations |

## Routing and coverage notes

- Text calls use one non-overlapping `LLM_PURPOSE_PROFILES` mapping. Purpose-specific context and max-output requirements are independent maps; the four profiles contain neither value.
- `visual_end_state` uses the separate image-capable request implementation and `VISION_LLM_SETTINGS`; it does not fit one of the four text profiles and remains the only call outside the standardized profile router.
- `director_raw_scene` now includes WorldState actions in the **same** response. At this checkpoint, state actions are dry-run validated but not committed as the canonical reducer result.
- Some compatibility helpers (for example recent-results summary, continuity delta/validation or generic JSON repair) can be called through injected `llm_request` and inherited metadata. The table names the stable explicit purposes; helper calls without an explicit identifier are not separate canonical `purpose` names.
- Context and max-output budgets remain per-request requirements, including 60,000-token story-pipeline contexts and specialized completion sizes. The separate image-capable `visual_end_state` request cannot use a text profile.
- The settings profile, live input shape, output schema, and prompt strings can change independently. When a call is added/removed or its route/contracts change, update this file from actual call sites and update the handoff with the active implementation details. Do not use this index as an alternative runtime source of truth.
