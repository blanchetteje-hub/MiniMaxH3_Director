# MiniMax H3 — Development Handoff

Last updated: 2026-09-24

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository:

`blanchetteje-hub/MiniMaxH3_Director`

Active development branch:

`gpt-arc-refresh`

This branch was created from `gpt-test-branch` on 2026-09-24 specifically for a chapter-first architecture reset.

Always inspect the current branch head. Do not trust stale SHAs in chat history.

## Ultimate goal

> **story.txt -> gold-standard MiniMax H3 prompts**

The pipeline is not the product. Preserve or replace existing code only according to whether it improves the path to the gold prompts.

## Rule 0

`story.txt` is the one narrative source of truth.

Creative execution inside the story is allowed. Material deviation outside the story is prohibited.

Chapter outlines, beats, continuity, and other intermediate artifacts are revisable derived data. They do not overrule `story.txt`.

## New branch direction

The old locked ARC/BEATS architecture is intentionally **not** a constraint on this branch.

The new model is chapter-first:

1. Split the complete story into rough chapters.
2. In `story_arc.json`, use `chapters`, not `phases`.
3. Generate beats for one chapter at a time.
4. Beat CREATE receives only the current chapter plus the minimum opening context/runtime constraints. It has no adjacent-chapter knowledge.
5. Validate/repair those beats against `story.txt`, not against the rough chapter outline.
6. The chapter outline may change if the beats fit the source story better.
7. Each later chapter is treated as enclosed and receives only a compact description of how it begins.
8. Use as many narrow LLM calls as prove useful. Do not reproduce the old call graph by habit.

## Chapter-controlled H3 modes

Refresh cadence is no longer user-controlled.

- First beat of Chapter 1: initial generation with `Minimax_auto_API.json`.
- Later beats in the same chapter: append.
- First beat of every later chapter: refresh.
- Remaining beats in that chapter: append.

Arbitrary "refresh every N segments" scheduling is obsolete and should be removed when runtime work begins.

## Gold refresh as the opening-context reference

The locked Amy benchmark has one refresh at Beat 7. Use that prompt as the concrete reference for what a new chapter needs at its start.

It re-establishes only the immediately useful established facts: location, active subjects, spatial relationship, current pose/held weapon, clothing/persistent visible condition, and relevant off-screen aftermath. It does not replay the prior chapter or explain how those facts came to be.

This is the current design target for chapter opening context: minimal current-state facts sufficient to render the first beat correctly.

## Gold target

Locked benchmark:

`tests/acceptance/gold/amy_zombie_house.json`

It remains the behavioral target. The architecture must derive the desired prompts from the source story, not from knowledge of the gold answers.

Generated prompts do not need string equality; they must preserve required events, exclusions, timing, continuity, audio/music progression, and expected end state.

GPT-5.6 Sol remains the fuzzy final evaluator against the gold target.

## Global H3 facts that survive the architecture reset

- Canonical action timestamp: `At mm:ss.nnn,`
- One discrete action per timestamp.
- Dialogue uses `(S#)` only for the speaker.
- Prefer names over ambiguous pronouns.
- Append music explicitly begins from `continues from <Video 1>.`
- Append video context uses only the final 22 frames of the prior clip.
- For 8-second H3 segments: 192 aligned frames, skip 170, load cap 22.
- The tested refresh path uses the final 22 decoded frames as VAE context latents with `context_frames = 7` plus prior audio.
- Re-state persistent visual details when the incoming video context does not actually prove them.
- Avoid ending append clips on dialogue when practical.
- Difficult body-disconnection actions often render better as multiple timed stages.
- Persistent Subject identity belongs to Python, not continuity LLM invention.
- Do not special-case benchmark vocabulary in production logic.

## Local bridge

Bridge implementation:

`tools/chatgpt_llama_bridge.py`

Mailbox branch:

`gpt-runtime`

Jobs:

`bridge/jobs/<job>.json`

Results:

`bridge/results/<job>/result.json`

Normal worker command:

`python tools/chatgpt_llama_bridge.py`

The worker can execute direct `llama_chat` jobs and allowlisted local test/acceptance jobs.

Important global caveat: the current bridge executable worktree defaults to `gpt-test-branch`. Until that plumbing is changed, branch-reset experiments on `gpt-arc-refresh` should use direct `llama_chat` jobs rather than accidentally running old-branch production tests.

The bridge process does not hot-reload changes to `tools/chatgpt_llama_bridge.py`; bridge-code changes require a local pull/restart.

## Branch state

Completed on `gpt-arc-refresh`:

- architecture-reset branch created;
- `docs/PROJECT_NOTES.md` rewritten around the chapter-first approach;
- inherited old-branch acceptance/debug chronology intentionally removed from this handoff.

No production planner/runtime implementation has been changed yet for the chapter-first design.

The immediate task is to use direct bridge probes to discover the smallest effective contracts for:

1. story -> chapter split;
2. source-faithful chapter validation;
3. chapter-only beat creation;
4. story-facing beat validation/repair;
5. minimum opening context needed by a later enclosed chapter.

Do not add production architecture until the probes provide evidence.
