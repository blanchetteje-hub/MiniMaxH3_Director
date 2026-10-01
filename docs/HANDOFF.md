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

## Immediate next work

Acceptance 2776 completed all 8 Beats successfully. The generated Beat sequence is coherent and source-faithful enough to move the acceptance boundary downstream.

Next:
1. reuse the saved 2776 plan so Beat sampling does not change underneath the Director test;
2. run Director-only acceptance from that exact story_arc.json + beats.txt;
3. inspect Request 1 / RAW scene output from Segment 1 forward;
4. identify the earliest real Beat -> RAW scene failure;
5. explain that failure and proposed fix before changing code or prompts;
6. do not resume accepted-state cleanup unless the RAW failure demonstrably depends on bad/missing canonical state.

Queued:
- director-2777-beat-to-raw

## Public repository rule

Committed repository content must remain SFW/generic.

Runtime/user-provided stories may contain arbitrary content, but committed tests, examples, prompts, comments, fixtures, and docs should remain generic/SFW.

## Handoff maintenance rule

Keep this file current and concise while work continues on `summary-to-story-test`.

When this experiment is merged, abandoned, or replaced:
- preserve durable architectural decisions in `PROJECT_NOTES.md`;
- move obsolete chronology to `HANDOFF_OLD.md`;
- update the active branch and immediate-next-work sections rather than leaving stale queued-job references.
