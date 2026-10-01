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
- when the source does not establish a new location/route/barrier/container, stay in the nearest established location rather than inventing one
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

### 2749 — focused regression suite

`tests-2749-accepted-state-root-schema`

Result: **39 passed, 9 subtests passed**.

Covered:
- `--generate-beats` CLI + desktop behavior
- summary-to-story pipeline
- accepted-Beat state capture/schema
- forward Beat validation

The 0.4 novelist temperature regression and accepted-state root-object schema are green.

### 2750 — full Amy planning run

`generate-beats-2750-summary-to-story`

Result: **completed successfully through all 8 accepted beats**.

This proves:
- summary -> expanded story -> exactly 8 macro events works end-to-end;
- Beat validation/repair can consume the generated framework;
- accepted-state capture no longer crashes on the demonstrated threat-root shape.

However, the run exposes the next real problem: **the novelist is still altering source story semantics.**

Observed examples in the expanded story/framework:
- source says Amy is cooking breakfast; expansion changes Will/Amber into chasing each other around the kitchen table;
- it invents a back bedroom safe room and extra living-room/hallway travel;
- after stating that the **last zombie** falls, the ending says Amy and the children must `slip past remaining zombies`;
- it then sends the family into the night/outside the house, whereas the source only requires Amy to return to the safe location and bring Will and Amber back out with her.

The clearest acceptance failure is the contradiction:
**last zombie killed -> remaining zombies still present.**

That is upstream story-expansion drift. Do not patch Beat validation or state logic to compensate for it.

A secondary observation is that accepted-state extraction can still overstate a character location from wording such as “ushers them inside”; for example Beat 3 recorded Amy in the back bedroom even though the beat does not clearly establish that Amy entered it. Do not fix this before the upstream expansion failure unless a later run proves it independently blocks continuity.

## Immediate next work

1. Treat 2750 as the current semantic baseline.
2. Fix the **novelist/story-expansion** prompt, not downstream Beat validation.
3. Add the smallest generic source-authority rule that prevents:
   - resurrecting/adding threats after a source-defined final threat is resolved;
   - inventing a new final destination/outcome not present in the source.
4. Keep the existing useful grounding rules and temperature 0.4; avoid overloading a prompt that is otherwise moving in the right direction.
5. Run focused regressions, then another full `--generate-beats 8 8` Amy planning acceptance.
6. Compare the new expanded story first. Only analyze later Beat/state failures after the expansion preserves the source story.

## Public repository rule

Committed repository content must remain SFW/generic.

Runtime/user-provided stories may contain arbitrary content, but committed tests, examples, prompts, comments, fixtures, and docs should remain generic/SFW.

## Handoff maintenance rule

Keep this file current and concise while work continues on `summary-to-story-test`.

When this experiment is merged, abandoned, or replaced:
- preserve durable architectural decisions in `PROJECT_NOTES.md`;
- move obsolete chronology to `HANDOFF_OLD.md`;
- update the active branch and immediate-next-work sections rather than leaving stale queued-job references.
