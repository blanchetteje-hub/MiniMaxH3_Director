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
- Director optimization is not the current focus; stabilize planning/beats first.

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

## Immediate next work

Queued:
- `tests-2753-state-root-siblings`
- `generate-beats-2754-summary-to-story`

When processed:
1. confirm the focused tests are green;
2. confirm the accepted-state extractor no longer produces nested canonical roots;
3. inspect the expanded story first and preserve the clean novelist prompt unless new evidence requires a change;
4. then identify the earliest real Beat/state failure;
5. explain the failure and proposed fix before making further changes.

## Public repository rule

Committed repository content must remain SFW/generic.

Runtime/user-provided stories may contain arbitrary content, but committed tests, examples, prompts, comments, fixtures, and docs should remain generic/SFW.

## Handoff maintenance rule

Keep this file current and concise while work continues on `summary-to-story-test`.

When this experiment is merged, abandoned, or replaced:
- preserve durable architectural decisions in `PROJECT_NOTES.md`;
- move obsolete chronology to `HANDOFF_OLD.md`;
- update the active branch and immediate-next-work sections rather than leaving stale queued-job references.
