# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first for project-wide architectural rules. This file describes the current branch implementation, active experiment, latest evidence, and immediate next work.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `summary-to-story-test`

Runtime/bridge mailbox branch: `gpt-runtime`

Baseline branch this experiment diverged from: `gpt-arc-refresh`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is development/evaluation only and must not become a production dependency.

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` remains the sole narrative authority. Expansion may add concrete staging/detail where the source is silent, but it may not add, replace, contradict, skip, reorder, or materially alter source events/outcomes.

Fix observed failures in order. Explain the failure and proposed fix before making substantive architecture/prompt changes.

## Current branch experiment: summary -> expanded story -> beats

This branch is testing a simpler front end to Beat planning than the older source-span/chapter planner.

Current `--generate-beats` flow:

1. Read `story.txt`.
2. Novelist call expands the short story/summary into a runtime-length working story.
3. A second local-model call converts that expanded story into exactly N sequential beat events.
4. Python creates a deterministic one-event-per-beat macro arc.
5. Existing Beat CREATE -> VALIDATE -> REPAIR -> VALIDATE processing turns those events into accepted beats.
6. Accepted-Beat state capture records persistent continuity after each accepted beat.

The expanded story is an intermediate implementation artifact, not a new narrative authority. When it disagrees with `story.txt`, the expansion is wrong.

### CLI contract

`--generate-beats` now takes two required positive values:

`--generate-beats <beat-count> <beat-length-seconds>`

Both are needed so the novelist knows the target total runtime:

`beat-count * beat-length-seconds`

The desktop/UI command path passes both values as well.

## Story expansion / novelist profile

Current novelist settings on this branch:

- temperature: `0.4` (lowered from `0.6` after observed drift)
- reasoning effort: high
- reasoning budget: 1024 tokens
- prompt explicitly preserves every source event/outcome
- explicit transitions must happen visibly rather than being compressed or implied
- ending guard: preserve the source's stated final situation; do not invent a new escape, destination, surviving threat, or aftermath after the source's final event
- target runtime and requested beat count are supplied

The prompt should remain compact. Do not respond to every bad generation by stacking more prose onto it; promote only the smallest generic rule supported by repeated evidence.

## Story-to-beats profile

The second pass receives the full expanded story and must return exactly the requested number of sequential beats.

Current settings:

- temperature: `0`
- reasoning effort: medium
- reasoning budget: 1024 tokens

Python strips story-style clock timestamps before the generated beat framework enters normal validation.

The generated macro arc is intentionally simple:
- one required event per requested beat;
- sequential dependency chain;
- no model-authored bookkeeping/state effects at this stage.

## Beat validation/state behavior retained from baseline

Normal Beat CREATE/VALIDATE/REPAIR remains in place after the new two-pass planner.

Important retained rules:
- Beat CREATE/REPAIR use temperature 0 / seed 42.
- Python owns deterministic bookkeeping and canonical state.
- accepted beats are observed for broad persistent state after validation.
- broad state capture does not imply broad prompt injection later.
- an unspecified observation must not erase a concrete established fact.
- acceptance 2776 completed all 8 Beats successfully and the Beat text is now provisionally stable enough to move downstream.

Accepted-Beat state capture remains useful, but further state-schema/bookkeeping cleanup is **not** the active optimization target. Do not delay Director work to perfect incidental state observations. Revisit state only when a concrete Director failure traces back to missing or incorrect canonical continuity.

## Accepted-Beat state schema fixes on this branch

Earlier accepted-state extraction showed two predictable 20B JSON-shape failures.

1. Nested threat shorthand:
   `{"threats":{"zombies":"active"}}`

   Accepted-state-only normalization converts known threat-state enum strings into:
   `{"threats":{"zombies":{"status":"active"}}}`

   Ambiguous nested strings still fail.

2. Root-level threat shape:
   acceptance 2748 produced a non-object `state_patch.threats`, which the canonical state parser correctly rejected.

   The response schema now requires each allowed root to be an object:
   - `characters`
   - `environment`
   - `threats`
   - `story`

   This prevents ambiguous root-level shorthand instead of making Python guess its meaning.

Relevant branch commits:
- `8a611913770ac8d010a6df55ecec2ea7e479a7e3` — update novelist temperature regression to 0.4
- `1b795fb5b3f85b3615f033c006748458d3665dcf` — constrain accepted-Beat state root shapes
- `9b734d3770d12ebb67a2445ed19973c115d6e3de` — regression coverage

## Terminology refactor

User-facing/code terminology is being changed from **LM Studio** to **LLM host** because the runtime is not tied to LM Studio.

The associated setting/variable naming is being migrated as well, including compatibility handling for the legacy key where needed.

Do not reintroduce LM-Studio-specific naming for generic runtime behavior.

## Latest verification

### 2751 — story expansion prompt regression

`tests-2751-clean-ending-prompt`

Result: **6 passed, 4 subtests passed**.

The newer location/barrier rule was removed from the novelist prompt. The replacement is one compact ending guard:
- preserve the source's stated final situation;
- do not invent a new escape, destination, surviving threat, or aftermath after the source's final event.

### 2752 — full Amy planning run

`generate-beats-2752-summary-to-story`

The expanded story is materially better than 2750:
- no zombies survive after the stated last zombie dies;
- no new escape/aftermath is invented;
- Amy returns to the safe location and retrieves Will and Amber.

The run then fails after Beat 2 in accepted-state capture with:

`State effects cannot nest canonical state root 'threats.story'; roots must remain top-level.`

This is not a novelist failure. It is a local-model JSON namespace-shape failure in the accepted-state extractor.

Current fix:
- accepted-state prompt now explicitly says `characters`, `environment`, `threats`, and `story` are sibling roots and must never be nested inside one another;
- no Python guessing/normalization was added for ambiguous nested roots;
- novelist prompt remains untouched.

Relevant commits:
- `eb207214079bcd001284196a458e015eff47cda6` — simplify novelist prompt and add ending guard
- `fd354a9683df63fde86eb0ffa57286466ce64ed9` — update novelist regression
- `9ee1c04e5fbe8f2c6916c0ca70c72397f350553a` — clarify accepted-state root namespaces
- `a3da214bc1bc5a37af92015c86196362d63e005c` — regression coverage

### 2754 — character canon source-contract failure

`generate-beats-2754-summary-to-story`

Result: failed before story expansion with:

`ValueError: Duplicate canonical character: Unnamed`

Root cause:
- `canonical_data.txt` on this branch contains the configured field list `age, clothing, gender`;
- the character-canon prompt was stale and still treated that file as if it contained character records;
- it also told the local model not to use story/subject information, leaving no character names available;
- GPT-OSS 20B emitted multiple `Unnamed` records and deterministic parsing rejected the duplicate.

Fix:
- `canonical_data.txt` is again treated as the field configuration;
- character names/facts are grounded from `story.txt` + `subjects.txt`;
- the canon cache hash includes configured fields, story, and subjects;
- no special handling for `Unnamed` was added.

Relevant commits:
- `8c18a09ece41805be8d0f4f31f4cf907908622ab` — fix character-canon source contract
- `53f532c6ddccfa35ec00d13f65bf8d4a18b37a4a` — align character-canon regressions

### 2756 — accepted-state threat classification/shape failure

`generate-beats-2756-summary-to-story`

Preceded by `tests-2755-character-canon-fields`: **42 passed, 4 subtests passed**.

2756 confirms the corrected character-canon source contract works and reaches normal story expansion/Beat processing.

Earliest failure after Beat 2:

`Beat state patch entity threats.children_in_kitchen must be an object.`

Interpretation:
- the accepted-state extractor placed a non-threat concept under `threats`;
- it also emitted a scalar threat child even though canonical threat entries are object records.

Fix:
- extractor prompt now says `threats` is only for hostile/dangerous entities; ordinary people/victims/protected characters belong under `characters`;
- response schema now requires every direct child of `threats` to be an object;
- no arbitrary Python scalar normalization was added.

Relevant commits:
- `cd4ab71da690d8922a4dd464fbf6ccd50e406574`
- `13f1c8be24cc1a853c4ea39c609302db925daf5f`

### 2758 — reserved root reused as threat ID

`tests-2757-threat-entry-shape`: **42 passed, 4 subtests passed**.

`generate-beats-2758-summary-to-story` reaches Beat 6 before failing with:

`State effects cannot nest canonical state root 'threats.story'; roots must remain top-level.`

The previous schema change successfully enforced object-shaped threat entries. The remaining failure is namespace-specific: GPT-OSS used the reserved canonical root name `story` as a threat ID despite the prompt already saying the roots are siblings.

Fix:
- reserve canonical root names structurally in the `threats` JSON schema using `propertyNames`;
- threat records remain otherwise flexible;
- no additional extractor prose rule and no Python guessing/normalization were added.

Relevant commits:
- `24715c6e83f6bee8c3b1b127f300865ae0ef6321`
- `663a23c6b31e8e155e255cb94b4b0f1c466bd9b5`

### 2760 — first full successful planning run after schema fixes

`tests-2759-reserved-threat-keys`: **42 passed, 4 subtests passed**.

`generate-beats-2760-summary-to-story`: **completed all 8 beats successfully**.

The reserved canonical-root-name restriction held; accepted-state capture no longer crashed on `threats.story`.

Remaining observation is semantic, not structural:
- the source ending says Amy returns to the safe location and brings Will and Amber back out with her;
- 2760 instead ends with the family stepping back into the hidden room;
- it also invents an unnamed `toddler` and temporarily places Amber in the hallway rather than the shared safe location.

Do not add more novelist prompt rules from this single sample. Earlier runs with the same current prompt preserved the ending better, so treat this as possible temperature/sampling variance first.

### 2761 — repeat novelist sample + reserved character key

`generate-beats-2761-summary-to-story-repeat`

The repeat sample preserves the source ending better than 2760: after the last zombie dies, Amy retrieves Will and Amber from the closet and brings them out into the living room. This supports treating 2760's reversed ending as sampling variance at novelist temperature 0.4 rather than adding another short-story prompt rule.

The run then fails after Beat 5 with:

`State effects cannot nest canonical state root 'characters.environment'; roots must remain top-level.`

This is the same structural class previously seen as `threats.story`: GPT-OSS reused a reserved canonical root name as a direct entity ID.

Fix:
- reserve canonical root names in direct `characters` keys, matching the existing `threats` restriction;
- no new extractor prose rule;
- novelist prompt/temperature remain unchanged.

Relevant commits:
- `05cc4ec427a1f3afdf931e9cda694eae04df592b`
- `79b5fadc2bf06212a550aa35c0ffb48b2ea85340`

### 2763 — successful planning run; summary-guided story-to-beats change

`tests-2762-reserved-character-keys`: **42 passed, 4 subtests passed**.

`generate-beats-2763-summary-to-story`: **completed all 8 beats successfully**.

The run's staging split Will and Amber across different safe locations. That is acceptable as creative staging if both are still retrieved at the end. The larger issue is that the derived Beat framework can lose an explicit source-summary obligation even when the expanded story is otherwise plausible.

Current experiment:
- story-to-beats system prompt now begins: `You are a screenplay writer that converts stories into films using a summary as a final guide.`
- user prompt now passes both the original `SUMMARY` and expanded `STORY`;
- no additional adaptation rules were added.

Relevant commits:
- `6357e1d303c105e056f3c78b53abc3022c7e4a2e`
- `7e8319d51c0d6bda12143ecf3e87154ac29183fd`

### 2765 — blocked before SUMMARY+STORY beat conversion

`tests-2764-summary-guided-story-to-beats`: **42 passed, 4 subtests passed**.

`generate-beats-2765-summary-guided-story-to-beats` failed before story expansion / story-to-beats with:

`Canonical fact has an invalid or duplicate field.`

Cause:
- character-canon JSON allows arbitrary `other_facts[].field` strings;
- GPT-OSS emitted a field that normalized to an already-required core field (`age`, `clothing`, or `gender`);
- deterministic parsing correctly rejected the duplicate.

Fix:
- reserve `age`, `clothing`, and `gender` in the character-canon JSON schema so they cannot be emitted through `other_facts`;
- parser remains strict;
- SUMMARY+STORY beat-conversion prompt remains unchanged and is still awaiting a clean acceptance sample.

Relevant commits:
- `80690ec5b4c948f7ba9f6089db3edb5997cd98a8`
- `e942948a9a0850a3f3b6b0064d3f1eef7d40d8e0`

### 2767 — first clean SUMMARY+STORY beat-conversion sample

`tests-2766-character-canon-core-fields`: **42 passed, 4 subtests passed**.

`generate-beats-2767-summary-guided-story-to-beats`: **completed all 8 beats successfully**.

The new story-to-beats prompt preserved the source-level ending obligation better:
- Beat 8 explicitly retrieves both Will and Amber;
- both children are carried out together.

Keep the SUMMARY+STORY prompt change.

Separate continuity issue observed upstream in the expanded story:
- Will and Amber are placed behind a closed hatch/safe location;
- later the expanded story has zombies lunge at Will and Amber anyway;
- the beat converter carries that contradiction forward.

Do not blame or modify the SUMMARY+STORY beat prompt for that contradiction. One unchanged repeat is queued to determine whether the expanded-story barrier inconsistency repeats before changing the novelist prompt.

### 2768 — repeat confirms prompts; story namespace schema failure

`generate-beats-2768-summary-guided-repeat`

The repeat did **not** reproduce the earlier barrier/safe-location contradiction:
- both kids remain out of the fight;
- Beat 8 retrieves both Will and Amber;
- SUMMARY+STORY beat conversion remains useful and should stay.

The run fails after Beat 3 in accepted-state capture with:

`State effects cannot nest canonical state root 'story.persistent_facts.characters.Amy.location'; roots must remain top-level.`

Cause:
- `story.persistent_facts` was still schema-open enough for GPT-OSS to place character-state data under the story namespace.

Fix:
- accepted-state `story` is now limited to `terminal_states` and `persistent_facts`;
- reserved canonical root names cannot be used directly inside `story.persistent_facts`;
- no novelist or story-to-beats prompt changes were made.

Relevant commits:
- `887fbe8c5ac6f2a47459629eac27f8e38a272d1e`
- `56f4ade89048730627e95eeef2a600b7adcc6852`

### 2770 — prompts remain good; environment container shape failure

`tests-2769-story-namespace-schema`: **42 passed, 4 subtests passed**.

`generate-beats-2770-summary-guided-story-to-beats` again preserves both kids:
- Will and Amber are placed together in the back bedroom closet;
- Beat 8 retrieves both of them and brings them out together.

Keep both current story prompts.

The run fails after Beat 3 in accepted-state application with:

`Canonical environment objects must be an object.`

Cause:
- accepted-state response schema still allowed arbitrary shapes under `environment`;
- canonical state requires `doors`, `windows`, `barriers`, `objects`, and `paths` to be object maps, and `persistent_effects` / `hazards` to be arrays.

Fix:
- encode those known environment container types directly in the accepted-state response schema;
- continue allowing additional environment facts;
- no Python normalization or story-prompt changes.

Relevant commits:
- `8ea3885c4105aa16c1c0883b20a3d784e97013f6`
- `008b884380503e0633bfa2a2734b373c2e41e9d5`

### 2772 — malformed accepted-state keys; test strict structured output

`tests-2771-environment-container-schema`: **42 passed, 4 subtests passed**.

`generate-beats-2772-summary-guided-story-to-beats` again produced a coherent 8-beat framework ending with both Will and Amber retrieved. The failure remained downstream in accepted-state extraction.

Observed extractor output contained syntactically valid but structurally nonsensical keys, including fragments resembling serialized JSON inside key names. Example failure:

`State effects cannot nest canonical state root 'environment.objects":{"pantry_closet":{}}},.threats'; roots must remain top-level.`

The accepted-state response format was still declared with `strict: False`. Rather than adding more semantic field rules, the current experiment changes only this response schema to `strict: True` so llama.cpp must adhere more closely to the JSON schema.

This may reveal whether the flexible schema is compatible with strict structured output. If not, the next failure should be an immediate schema/grammar error rather than corrupted state.

Relevant commits:
- `610f8f3319d41e2b3fb92d61aceaf3e18de8b1f6`
- `459316da5f333abb0f78cadf4c2d1a6c9993c250`

### 2774 — strict output helps; threat-ID ordering bug found

`tests-2773-strict-accepted-state-schema`: **42 passed, 4 subtests passed**.

`generate-beats-2774-strict-accepted-state-schema` reaches Beat 7 with clean structured state before failing again on:

`State effects cannot nest canonical state root 'threats.story'; roots must remain top-level.`

Strict structured output improved the extractor substantially, but llama.cpp still did not reliably enforce the `propertyNames` reservation.

Root cause in Python:
- Python already owns stable threat IDs through `_normalize_threat_patch_ids()`;
- however, `persistent_beat_state_patch()` validated the raw model patch namespace **before** threat IDs were canonicalized;
- therefore a model-invented label such as `story` crashed before Python could rename it to `threat_N`.

Fix:
- canonicalize new threat IDs before `normalize_beat_state_patch()` namespace validation;
- no semantic guessing, prompt changes, or broader normalization added;
- strict accepted-state schema remains enabled.

Relevant commits:
- `30a35e53a940d63c171ea0d29d9421d293ecc52a`
- `d3c0dda6599e2baa7a3287529bad763b6ff4b17b`

### 2798 — malformed accepted-state observation no longer blocks Beat generation

`generate-beats-2798-source-ending` reached Beat 6, then the accepted-state observer emitted an invalid nested canonical root (`environment.story`) and aborted the entire planning run.

This is auxiliary bookkeeping, not Beat authority. The accepted Beat had already passed semantic validation and physical-coherence checks.

Fix:
- accepted-state extraction/application is now fail-soft for structural `ValueError` failures;
- the malformed observation is logged and skipped;
- the already-valid Beat continues normally;
- no new schema rule, normalization guess, or novelist/Beat prompt prose was added.

This deliberately stops state bookkeeping from becoming the optimization target again.

### 2801–2802 — planning succeeds; first Request 2 loss found

`generate-beats-2801-fail-soft-state` completed all 8 Beats successfully. This confirms malformed accepted-state bookkeeping no longer blocks the planning run.

`director-2802-fail-soft-state` then reached Segment 2 with a usable RAW scene. The post-format preservation check caught Request 2 dropping the first material RAW micro-action.

Fix:
- Request 1 remains authoritative and is not regenerated;
- Request 2 still formats normally;
- if the final semantic preservation check fails, Python replaces only `detailed_description` with canonical timed RAW action text, excluding the trailing `End continuity state`;
- soundscape/music and normal H3 assembly remain intact;
- the rebuilt prompt is revalidated and still fails hard if preservation is somehow not restored.

This keeps Request 2 a lossless formatter without adding prompt rules or another semantic repair loop.

### 2805 — deterministic RAW fallback exposed validator false negative

Segment 2 Request 2 lost two RAW actions, so the new Python fallback copied the canonical timed RAW actions into `detailed_description` exactly as intended. The subsequent local-LLM preservation check nevertheless labeled the first and last copied actions OMITTED.

Conclusion: after canonical RAW text is inserted deterministically, preservation is true by construction. Re-asking the 20B to judge identical copied text adds uncertainty and can create false failures.

Change:
- keep the first semantic preservation check on normal Request 2 output;
- on failure, substitute canonical timed RAW text deterministically;
- do not perform a second semantic LLM preservation check on the deterministic fallback.

### 2807 — full Director run completes; earliest real RAW failure identified

`director-2807-trust-raw-fallback` completed all 8 prompt-generation segments and marked all 8 Beats complete. The deterministic RAW fallback now works end-to-end.

However, Segment 2 RAW exposed the earliest real quality failure:
- 00:04.500: Amy slams the closet door shut;
- 00:06.000: Will and Amber then tumble into that already-closed closet.

That is a concrete physical/action-order contradiction, so it is not harmless creative staging.

Fix:
- add one narrow Request-1 semantic coherence check before accepting RAW;
- validate only physical/causal executability and required action order in timestamp order;
- allow harmless invented staging;
- on failure, retry Request 1 with the concrete issue;
- do not add more deterministic special-case regex rules for semantic choreography.

The post-RAW path remains deterministic where possible; this check exists before RAW is accepted because deciding physical/causal coherence is fuzzy semantic work.

### 2809 — RAW coherence wiring bug

The new RAW coherence gate did not actually run because its helper forwarded the entire beat-validator settings dictionary directly into `ask_llm`; that dictionary contains server/runtime-only keys such as `context`, which are not valid per-request arguments.

Fix: the narrow RAW coherence call now uses only supported deterministic request parameters (temperature 0, top_p 1, seed 42, repeat_penalty 1.15, bounded output), matching the style of other narrow semantic checks.

### 2811 — coherence works; add post-RAW pronoun specificity

2811 completed the full prompt-generation run. The new RAW physical/order check triggered retries and produced an ordered Segment 2.

The run also showed that RAW and Request 2 continue to carry person pronouns such as `she`, `her`, `them`, and `their`. MiniMax H3 benefits from explicit named references.

Change:
- keep Request 1 focused on staging the scene;
- after RAW is accepted, run a tiny deterministic pronoun-resolution pass;
- replace only unambiguous person pronouns with explicit names/named groups;
- preserve all timestamps/actions/order/objects/audio/camera/dialogue/end-state meaning;
- fail soft to original RAW if the cleanup changes timestamp/structure or is unusable.

This moves H3-specific reference precision out of the creative RAW prompt instead of adding another Request-1 rule.

### LLM logging convention

All production LLM stages should emit their result or concise verdict through `print()` so bridge `run.log` is sufficient for diagnosis. The pronoun resolver now logs whether it made no replacements or prints each changed line as `Checking pronouns segment: replaced <before> -> <after>`.

### RAW -> final H3 simplification

The former Request 2 formatter no longer owns narrative conversion.

Current post-RAW path:
- pronoun-resolution LLM: explicit-name cleanup only;
- deterministic soundscape extractor: returns only `overall_soundscape`;
- narrow creative music generator: returns only `non_diegetic_music`;
- Python: strips RAW end-state metadata, copies canonical timed RAW into `detailed_description`, uses subject metadata already sourced from text/registry state, and builds the final H3 prompt.

The old final-H3 action-preservation LLM is skipped because copied RAW is preserved by construction.

### 2815 — Python-owned H3 path works; capture/pronoun follow-up

2814 regressions passed 5/5.

2815 generated all 8 final H3 prompts and marked all 8 Beats complete. The bridge return code 2 came only from the acceptance parser still looking for the retired `DIRECTOR REQUEST 2: H3 prompt` start marker after runtime output was renamed to `FINAL H3 PROMPT`.

The new RAW->H3 architecture itself ran end-to-end.

Observed pronoun-cleanup issue:
- several segments were rejected because the tiny resolver rewrote or dropped the trailing `End continuity state:` marker;
- final H3 then retained pronouns from original RAW.

Fix:
- send only the timed RAW body to pronoun resolution;
- preserve/re-attach the exact original End continuity state in Python;
- tell the resolver to scan the entire timed scene and replace every unambiguous personal pronoun;
- acceptance parser recognizes both old and new H3 start markers for compatibility.

### 2816 — LLM settings are task-based, not model-based

Audited the production request path and found remaining model-specific settings:
`MISTRAL_24B_SETTINGS`, `QWEN38_27B_SETTINGS`,
`QWEN_DIRECTOR_SAMPLING_PARAMETERS`, formatter `DEFAULT_LLM_SETTINGS`, and
the `use_beat_validation_settings` transport switch.

Refactor:
- removed all of those model-specific request profiles/switches;
- formatter choice now affects parsing/cleanup only;
- `ask_llm()` selects one profile solely from the request purpose:
  `STORY_EXPANSION_LLM_SETTINGS`,
  `CREATIVE_GENERATION_LLM_SETTINGS`,
  `BEAT_WRITING_LLM_SETTINGS`,
  `STORY_TO_BEATS_LLM_SETTINGS`,
  `MUSIC_GENERATION_LLM_SETTINGS`, or
  `DETERMINISTIC_ANALYSIS_LLM_SETTINGS`;
- Beat validation uses the same system/user prompt shape and deterministic
  request profile regardless of GPT/Qwen/Mistral formatter selection;
- stale per-call ARC/Beat sampler splats were removed so purpose routing is the
  single authority.

### 2834–2836 — H3 audio responsibility split

`director-2834-audio-completeness` completed all 8 prompt-generation segments.
`tests-2835-audio-underscore-normalization` passed.

The remaining settings mismatch was architectural: one LLM call was being asked to
perform deterministic sound extraction and creative music generation, so both fields
were forced through the deterministic-analysis profile.

Current change:
- soundscape extraction is its own `director_h3_soundscape` task and stays on
  `DETERMINISTIC_ANALYSIS_LLM_SETTINGS` (temperature 0, low/128 reasoning,
  seed 42);
- non-diegetic music is its own `director_h3_music` task using
  `MUSIC_GENERATION_LLM_SETTINGS` (temperature 0.6, medium/256 reasoning,
  randomized seed);
- each call has a one-field strict schema and one semantic responsibility;
- no per-call temperature/top-p/seed overrides remain on the H3 audio path;
- underscore cleanup remains deterministic Python normalization after each field.

### 2837 — split works; first real audio-specific failures

`director-2837-h3-audio-task-split` completed all 8 segments.

The responsibility split is stable, but the first real outputs exposed two narrow
prompt defects:

- soundscape extraction converted visual-only facts into sound (for example,
  sunlight reflecting off cereal);
- music generation became too verbose/action-synchronized and had no explicit
  previous-score context, producing a tense final cue even when the RAW scene
  resolved into relief.

Fix:
- soundscape prompt now permits only microphone-audible facts and explicitly
  rejects lighting, visibility, expressions, stillness, positions, silent
  gestures, and merely plausible optional sounds;
- continuation music now receives the previous segment's
  `non_diegetic_music`;
- music output is one concise underscore cue describing the emotional arc,
  not a narration or beat-by-beat synchronization of scene actions;
- task profiles remain unchanged.

### 2838 — audio-quality regressions pass; stale Director tests exposed

The new soundscape/music prompt tests and task-routing tests passed. The broader
`test_director_retry.py` slice exposed stale unit tests that still mocked the
retired Request-2 formatter call shape. Those failures were test-harness drift,
not production-path failures.

Test cleanup:
- RAW-focused tests now use an audio-aware responder so independent soundscape
  and music calls do not consume unrelated mock responses;
- retired formatter-retry tests were replaced with current RAW-copy and
  independent audio fail-soft coverage;
- the pronoun prompt assertion now matches the already-adopted narrowing rule.

### 2839 — 102/103 pass; final failure is test injection drift

The broad regression slice passed 102/103. The remaining failure was the physical/order
retry unit test: it tried to feed coherence-validator replies through a patched
`ask_llm`, but `validate_director_raw_scene_coherence()` owns that semantic boundary.
The test now mocks the validator directly and leaves the Director request mock responsible
only for RAW scene responses.

### 2841 — audio quality improved, remaining contract failures isolated

`director-2841-h3-audio-quality` completed all 8 segments.

Observed:
- microphone-only wording removed the Segment 1 visual-only sunlight sound from
  2837;
- previous-score handoff fixed the major Segment 8 musical direction: the score
  now resolves from tension into warm relief;
- music is still too verbose and action-synchronized despite the word
  `concise`;
- Segment 7 produced malformed soundscape text `:[`;
- Segment 8 incorrectly inferred a gunshot from the state phrase
  `pistol still fired`.

Fix:
- soundscape contract now requires each item to name an audible event/ambience
  and forbids deriving sounds from persistent state descriptions;
- punctuation-only/non-language soundscape output is rejected;
- music is limited to one cue sentence, at most 24 words after the continuation
  prefix, with no character/action/sound-effect narration;
- malformed/overlong audio output gets one bounded retry;
- task-based LLM profiles remain unchanged.

### 2845 — hardened audio contract works; final soundscape-only issue

`director-2845-h3-audio-contract` completed all 8 segments.

Validated fixes:
- malformed Segment 7 soundscape was rejected automatically and succeeded on
  bounded retry;
- Segment 8 no longer invents a gunshot from the persistent state phrase
  `pistol still fired`;
- music is now short enough to resemble the gold cue style while preserving
  previous-score continuity;
- Segment 8 correctly resolves to relieved/warm closing music.

Remaining repeatable audio defect is isolated to soundscape extraction:
- silent motion is still sometimes verbalized as sound (`arms swing`,
  `hand slides`, `sword lifts`);
- one segment with explicit echoed footsteps returned `N/A`.

Final soundscape-only change:
- explicitly distinguish stated audible events from visible motion verbs;
- reject `N/A` when RAW contains deterministic lexical evidence of explicit
  audio such as footsteps, echoes, laughter, groans, impacts, or gunshots;
- leave music and all task-based LLM settings unchanged.

### 2847 — audio locked; next gold mismatch is dynamic Subjects

`director-2847-h3-audio-final` completed all 8 segments.

Audio result:
- explicit footsteps/groans/impacts no longer collapse to N/A;
- malformed output remains protected by the bounded retry;
- persistent state no longer creates fake gunshots;
- silent motion over-conversion is materially reduced;
- music remains short, continuous across append segments, and resolves with the
  scene's emotional state.

Decision: lock the H3 audio path. Do not keep tuning it against this benchmark
unless a new story exposes a concrete regression.

Next larger gold mismatch:
- combat RAW contains visible zombie subjects in Segments 2-8;
- final H3 `subject_definitions` contains only file-backed Amy/Will/Amber;
- camera movement is also absent, but missing Subject identity is the larger
  structural mismatch.

Root cause: the simplified story->beats path builds its Python macro arc with
`characters_introduced: []`, removing the input used by the existing pre-H3
dynamic Subject registry.

Fix in progress:
- beat writing assigns stable numbered functional labels only to distinct
  unnamed animate individuals that require separate identity;
- Python extracts those labels deterministically into
  `characters_introduced`;
- existing Subject registration remains the only downstream identity mechanism;
- no new LLM stage and no LLM settings change.

### 2848 — functional-label architecture passes except ambiguous token syntax

Focused tests passed 4/5. The only failure was deterministic Python treating
`Room2` as a Subject because plain `Word+number` is not semantically unique.

Fix:
- beat writer now marks functional animate identities explicitly as
  `@Guard1`, `@Creature1`, etc.;
- Python extracts only those marked handles;
- Python removes the `@` before validation and saving, leaving ordinary
  `Guard1`/`Creature1` beat prose;
- numbered locations and objects such as `Room2` are ignored by construction;
- no new LLM stage or settings change.

### 2851-2858 — Beat-owned Subject labels rejected

Planning probes established that the marker plumbing itself worked, but the
responsibility was in the wrong stage.

Evidence:
- 2851 produced several functional zombie handles successfully;
- 2852/2853 collapsed later distinct attackers into one label or collective prose;
- the strengthened rule passed focused regressions in 2855;
- fresh production runs 2856/2857/2858 still produced only `Zombie1` while later
  foreground attackers remained collective or reused that one identity.

Decision:
- stop asking story-to-beats to invent H3 Subject identities;
- Beats return to natural story-event description only;
- `characters_introduced` is no longer populated from temporary `@` markers.

### Post-RAW dynamic Subject ownership

Dynamic identity now begins after Request 1 RAW has been accepted and before final
H3 assembly.

Current design:
- the accepted staged RAW is authoritative;
- a narrow deterministic-analysis call sees RAW plus existing Subject definitions;
- it labels distinct unnamed foreground animate participants with stable functional
  names such as `Guard1` or `Creature1`;
- it reuses an existing dynamic name only when RAW clearly continues the same
  individual;
- Python keeps ownership of numeric Subject IDs, speaker IDs, persistence, and
  registration through the existing Subject registry;
- malformed/timestamp-changing/structurally invalid Subject resolution fails soft
  to the accepted RAW.

Beat prompts and Beat repair no longer carry dynamic-Subject labeling rules.

Relevant commits:
- `b79c71e00e1ca8856e666547a70058aa3505db3b` — resolve dynamic Subjects from accepted RAW;
- `ec53cdadcd1db9cc1f40520506f450ab39fa6715` — move Subject identity regressions out of Beats;
- `35e47416b376515743b79a79d3803d17292e9edf` — cover post-RAW Subject resolution;
- `a56e35fbf540f370828349cce86e947ade1e2067` — update project architecture notes.

## Immediate next work

Run focused regressions for:
- story-to-beats no longer emitting/depending on functional Subject handles;
- post-RAW Subject prompt shape;
- stable functional naming from RAW;
- timestamp/shot-structure protection.

If green, run a fresh full Director acceptance and inspect whether final H3 prompts
contain distinct dynamic Subject definitions for concretely staged unnamed actors.
Do not tune camera choreography until this Subject ownership change is verified.

Queued:
- none yet

## Public repository rule

Committed repository content must remain SFW/generic.

Runtime/user-provided stories may contain arbitrary content, but committed tests, examples, prompts, comments, fixtures, and docs should remain generic/SFW.

## Handoff maintenance rule

Keep this file current and concise while work continues on `summary-to-story-test`.

When this experiment is merged, abandoned, or replaced:
- preserve durable architectural decisions in `PROJECT_NOTES.md`;
- move obsolete chronology to `HANDOFF_OLD.md`;
- update the active branch and immediate-next-work sections rather than leaving stale queued-job references.


## 2026-10-02 update — Subject determination locked
Acceptance 2868 confirmed the post-RAW Subject architecture is viable and stable enough to lock. Segment 2 created `Zombie1`; Segment 6 created `Zombie2` and `Zombie3`; no `Will1`/`Amber1`/`Zombie2_1` alias drift remained. Existing accepted-RAW identifiers are now immutable across Subject resolution, while genuinely new unnamed foreground actors can still receive functional identities. Final H3 subject definitions remain scene-scoped. Next work: camera choreography, now the largest remaining gold mismatch.

## 2026-10-02 update — canonical named characters now promote to H3 Subjects
A gap introduced by the post-RAW Subject refactor left named canonical characters such as Will and Amber outside the Subject registry unless they were already file-backed or appeared in formatter subject metadata. The unnamed-actor resolver was working as designed and remains unchanged. Python now deterministically supplies canonical character names as Subject-registration hints, while the existing visual-presence check still requires the exact name to appear in finalized RAW before allocating a Subject ID. Canonical gender is preserved as authoritative during that promotion. This restores named-character Subject definitions without moving identity ownership back into Beats or broadening the unnamed Subject resolver.

## 2026-10-02 update — canonical prose carried by named dynamic Subjects
The first 40-second production render showed a major visual-consistency improvement after the rebuilt ComfyUI workflows, but named characters without reference images drifted after leaving and re-entering frame. Python now deterministically renders canonical age/gender/clothing into natural prose (for example, `Amber is a 5-year-old female wearing a pink dress.`). Structured clothing values are flattened and deduplicated without an LLM call. When a canonical named character is promoted into the Subject registry, that sentence is stored as Python-owned Subject metadata and emitted with the dynamic Subject definition on later appearances/resume. Unnamed dynamic Subjects remain unchanged.

## 2026-10-02 update — full Python Subject state is text-renderable on re-entry
Dynamic/reintroduced Subject definitions now append the deterministic prose representation of the Subject's last Python-owned continuity record, rather than carrying only canonical age/gender/clothing. The renderer reuses the existing H3 continuity text path, so position, pose/action, current wardrobe, topology, body state, physical condition, held props, attached objects, injuries, substances, spatial relationships, persistent effects, and terminal absence/destruction constraints are all recoverable as real text. Canonical identity prose remains separate and comes first. The JSON continuity record remains the single source of truth; no LLM call is used to translate state back into prompt prose.


## 2026-10-02 update — story-level location extraction
A new narrow deterministic-analysis call now reads the complete expanded_story.txt
once before Segment 1 and extracts exactly two fields: overall_location and
starting_location. Python persists those values under generation_state metadata.
The Segment-1 Director receives the starting location as authoritative opening
context, and final H3 assembly independently prepends the Python-owned sentence
"[Shot 1] The scene starts in {starting_location}." so the location cannot be
dropped by the formatter. The overall location is metadata only for now; it is
intentionally not promoted into the unfinished room-geometry/topology system.


## 2026-10-02 update — continuous camera choreography
The official H3 prompt-writing guidance and production renders both point toward
camera motion instead of editorial cutaways when the scene remains continuous.
Director Request 1 now owns that behavior explicitly. Each segment is staged as
one continuous camera take by default; cutaways, inserts, reverse-angle/reaction
cuts, fades, wipes, and shot changes are forbidden unless CURRENT BEAT truly
requires a discontinuous time/location change that cannot be shown continuously.
When framing needs to change, the Director is told to use natural push/pull,
pan, truck, tilt, pedestal, arc, tracking, or static camera behavior and to make
movement follow/reveal/refocus story action rather than decorate it.

To prevent the film from becoming compositionally static while still hiding
segment seams, Segments 4, 7, 10, ... receive a deterministic reframe rule:
begin from the inherited composition, then after about one second move
continuously into a materially different angle/distance/height/framed subject/
viewing side without cutting. Other continuation segments do not force a new
composition. Request 2 remains a formatter and preserves Request 1 camera
choreography rather than inventing its own.


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
