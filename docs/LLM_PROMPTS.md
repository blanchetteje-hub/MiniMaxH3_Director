# LLM Prompt / Call Inventory

**Branch audited:** `world-state-rebuild` (2026-10-08). **Primary source:** `minimax.py`, including its `ask_llm()` purpose-routing tables and observed call sites. This is an **index of LLM calls, not verbatim user/system prompt text**: runtime prompts remain user-owned in source. Do not edit prompts merely to make the descriptions here match.

**How to read:** `purpose` is the primary `history_metadata.purpose` identifier; settings names are constants, not expanded per-field values. Settings are selected by purpose, with the fallback `DETERMINISTIC_ANALYSIS_LLM_SETTINGS`. A listed purpose does not guarantee execution on every run; some calls are conditional, diagnostic, compatibility, or legacy paths. Where a helper inherits a caller's `history_metadata` instead of assigning a purpose, it uses that inherited identifier (or the fallback settings).

## Call catalog

| `purpose` identifier | Settings constant | Purpose | Passed in (summary) | Returns (summary) |
| --- | --- | --- | --- | --- |
| `story_expansion` | `STORY_EXPANSION_LLM_SETTINGS` | Expand the source into filmable narrative | Source story/summary and expansion guidance | Expanded story text |
| `story_to_beats` | `STORY_TO_BEATS_LLM_SETTINGS` | Derive ordered filmable beats | Expanded story and source/beat budget context | Structured beats |
| `story_to_beats_repair` | `STORY_TO_BEATS_LLM_SETTINGS` | Repair invalid beat derivation | Original story, draft beats, specific validation issue | Corrected beats |
| `character_canon` | `CREATIVE_GENERATION_LLM_SETTINGS` | Establish stable configurable character facts | Story, predefined Subjects and configured canon fields | Canonical character facts |
| `story_subject_wardrobe_extract` | `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` | Determine one Subject's canonical appropriate wardrobe | Expanded story, Subject identity, appearance and setting | Structured/canonical wardrobe for that Subject |
| `story_location_extract` | `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` | Identify story locations and initial setting | Expanded story and established story context | Overall and opening location information |
| `static_setting_extract` | `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` | Extract permanent location facts without action-only objects | Expanded story and named location context | Static setting description |
| `story_setting_spatial_refine` | `SLIGHTLY_CREATIVE_LLM_SETTINGS` | Lay out a physically coherent static environment | Extracted setting and location constraints | Spatially refined setting text |
| `story_setting_extract` | `SMART_EXTRACTOR_LLM_SETTINGS` | Serialize canonical location geometry and text | Refined static layout and source location details | Location-state JSON plus matching literal prose |
| `director_raw_scene_subject_resolution` | `SMART_EXTRACTOR_LLM_SETTINGS` | Identify animate Subjects present from the beginning | Complete finalized beat list, known Subjects and opening context | Functional names and supported initial states |
| `registered_subject_story_start_presence` | `LONG_CONTEXT_DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Classify one authored Subject's opening presence | Full beats/story and one registered Subject with source evidence | Present/absent/unknown classification with evidence |
| `world_state_current_segment_subjects` | `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` | Register identities needed for the current Beat before RAW | Current Beat/source, registered Subject context | New current-segment identity records; no inferred entry/presence |
| `world_state_current_segment_props` | `LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS` | Identify explicitly needed persistent props for this Beat | Current Beat/source and registered Subject, prop, location/support vocabulary | Narrow prop registration candidates and initial placement |
| `source_unit_state_effects` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Extract explicit durable source effects | One exact source unit and state context | Typed persistent effects, not activity alone |
| `macro_arc_create` | `CREATIVE_GENERATION_LLM_SETTINGS` | Create a chapter/arc plan | Authoritative story and allocation constraints | Arc/chapter plan |
| `macro_arc_validate` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check arc/source responsibility | Source text and candidate arc | Validity and specific issue |
| `macro_arc_majority_validate` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check explicit majority/repetition allocation | Source emphasis and candidate chapter/beat plan | Majority/repetition validity assessment |
| `macro_arc_majority_tail_repair` | `CREATIVE_GENERATION_LLM_SETTINGS` | Repair majority-process placement | Affected arc portion and validator feedback | Corrected arc tail |
| `macro_arc_repair` | `CREATIVE_GENERATION_LLM_SETTINGS` | Repair an arc defect | Story, candidate arc and validation failure | Revised arc plan |
| `beat_generation` | `BEAT_WRITING_LLM_SETTINGS` | Write assigned visible Beats | Authoritative source, assigned events, budget, Subject canon and relevant prior context | Specified number of Beats |
| `beat_validation` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check source coverage, fidelity, and beat boundaries | Source/assigned events, candidate Beats, applicable canonical state | Valid/invalid with first issue |
| `beat_finite_endpoint_extract` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Observe whether finite assigned activity has completed | Exact finite assignment and candidate Beat | Complete/ongoing/not-applicable classification |
| `beat_coherence_validation` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check physical and causal plausibility inside a Beat | Accepted-candidate Beat, source and relevant known state | Coherence validity and issue |
| `beat_repair` | `BEAT_WRITING_LLM_SETTINGS` | Repair a specific assigned Beat | Original assignment, failed Beat and validator issue | Corrected Beat |
| `accepted_beat_state_extract` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Capture auxiliary post-Beat persistent facts | Accepted Beat and prior state/source context | Structured state patch |
| `director_raw_scene` | `DIRECTOR_RAW_SCENE_LLM_SETTINGS` | Stage the current Beat as timed RAW, with reducer actions | Assigned source, current/next Beat, opening continuity, static setting, prop state and registered WorldState vocabulary | Timed RAW scene, completion fields, registered state_actions for dry-run |
| `director_raw_scene_physical` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check RAW spatial/action order | Current Beat, RAW, previous shot end, known Subjects and fixed setting | Physical validity and concrete issue |
| `director_raw_scene_prop_state` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check RAW object provenance and transfers | Current Beat, RAW, previous shot end, prop ledger and static setting | Prop/state validity and issue |
| `director_raw_scene_timing` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check feasible sequential timed actions | Timed RAW scene and segment duration contract | Timing validity and issue |
| `director_raw_scene_pronoun_resolution` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Disambiguate person pronouns without rewriting RAW | Accepted RAW and established Subject names | RAW with unambiguous pronouns replaced or unchanged RAW |
| `director_raw_scene_visible_subject_resolution` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Name new visible foreground animate participants | Accepted RAW and persistent Subject definitions | RAW with stable functional Subject labels plus identity metadata |
| `director_h3_soundscape` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Extract audible ambience and effects | Accepted RAW scene and prior relevant audio context | One overall_soundscape value |
| `director_h3_music` | `MUSIC_GENERATION_LLM_SETTINGS` | Choose or continue the underscore | Current scene, context and previous segment music | One non_diegetic_music cue |
| `continuity_attachment_extract` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Identify meaningful physical object attachments | Continuity/scene text, Subjects and known objects | Attachment relationships or filtered object facts |
| `continuity_combined_reduced_state` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Extract a compact changed-state delta | Committed continuity, newest segment, registered Subjects and relevant Beat context | Structured continuity delta |
| `continuity_state_validation` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Check proposed continuity against newest RAW | Newly extracted continuity, established state and newest segment | Validation feedback for delta retry |
| `continuity_phase_2_h3_opening` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Select compact immediate H3 opening facts | Canonical/observed state, active Subjects and scene context | Concise opening continuity facts |
| `combined_continuity` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Update combined legacy continuity | Newest accepted prompt, prior continuity and Subject/prop context | Updated structured continuity observation |
| `subject_continuity` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Summarize persistence of Subjects | Recent segment outputs and known Subject definitions | Subject-state continuity summary |
| `final_h3_action_preservation` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Compare RAW action with final H3 action | Paired same-timestamp RAW/H3 micro-actions | PRESERVED / OMITTED / CHANGED verdict |
| `json_repair` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Repair malformed JSON without changing intended semantics | Invalid LLM JSON, target schema/parse issue | Parseable corrected JSON |
| `director_h3_formatter` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Legacy/optional H3 format translation | Accepted RAW, Subject definitions and H3 formatting contract | Formatted H3 fields, where still invoked |
| `director_raw_scene_coherence` | `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` | Legacy semantic RAW coherence evaluation | Beat/RAW and established opening context | Coherence verdict and issue, if invoked |
| `visual_end_state` | `VISION_LLM_SETTINGS` | Observe visible final-frame continuity (separate vision path) | Rendered segment image(s) and observed-state extraction instructions | Visual end-state observations |

## Routing and coverage notes

- The routing precedence in `ask_llm()` is story expansion; story-to-beats; long-context deterministic; long-context creative; music; beat writing; Director RAW; creative; smart extractor; slightly creative; and finally deterministic fallback. Several identifiers also appear in the generic deterministic purpose registry but are overridden by an earlier, more specific registry.
- `visual_end_state` uses the separate vision-model request implementation and `VISION_LLM_SETTINGS`, rather than assuming the text `ask_llm()` settings route.
- `director_raw_scene` now includes WorldState actions in the **same** response. At this checkpoint, state actions are dry-run validated but not committed as the canonical reducer result.
- Some compatibility helpers (for example recent-results summary, continuity delta/validation or generic JSON repair) can be called through injected `llm_request` and inherited metadata. The table names the stable explicit purposes; helper calls without an explicit identifier are not separate canonical `purpose` names.
- The settings constant, live input shape, output schema, and prompt strings can change independently. When a call is added/removed or its route/contracts change, update this file from actual call sites and update the handoff with the active implementation details. Do not use this index as an alternative runtime source of truth.
