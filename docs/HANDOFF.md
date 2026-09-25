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
- inherited old-branch acceptance/debug chronology removed from this handoff;
- no production planner/runtime code has been replaced yet.

### Chapter-first probe findings

The first probe batch established several useful contracts.

**Chapter boundary selection**
- Probe 317 still over-split when chapter selection and beat allocation were combined.
- Probe 318 separated **chapter boundaries** from beat allocation.
- Boundary-only creation produced exactly two broad chapters:
  1. ordinary opening -> breach -> children secured -> equipment -> main repeated conflict;
  2. explicit final/terminal resolution -> children released/reunited.
- This matches the Amy gold mode pattern: Beats 1-6 in Chapter 1, Beats 7-8 in Chapter 2.
- Conclusion: choose chapter boundaries before asking for beat counts.

**Beat allocation**
- Probe 318's first allocator wording produced the wrong 3/5 split despite correct boundaries.
- Probe 319 isolated allocation and explicitly preserved the source's "majority of the story" emphasis.
- All allocation variants returned **6/2**, and 6/2 validated cleanly.
- Conclusion: fixed chapters -> narrow allocation call; do not make the boundary call also solve integer beat allocation.

**One-beat chapter completion**
- Probe 315 showed that an explicit one-beat budget constrains Beat CREATE, but its weak prompt stopped at an intermediate breakfast result.
- Probe 320's concise whole-chapter-completion rule produced a correct one-beat endpoint: breakfast completed and served to both children.
- Its bad control was rejected, good control accepted, and repair produced the same completed endpoint.
- Conclusion: Beat CREATE gets an explicit beat budget and each beat set must complete the chapter responsibilities assigned to that budget.

**Opening context**
- Gold Beat 7 remains the baseline for the immediate refresh opening.
- Probe 321 extracted the minimum context needed for the **whole later chapter**, including one fact not present in the gold Beat-7 opening description: the children are behind the closed steel safe-room door down the hallway.
- Without that fact, context sufficiency correctly failed; adding it passed.
- Probe 324 confirmed the distinction:
  - gold-like context alone is sufficient for the first refresh beat;
  - the enclosed two-beat chapter needs the child-location/containment fact to plan Beat 2 without inventing spatial state.
- Conclusion: opening context should cover the whole enclosed chapter, not merely the first rendered frame, while still remaining minimal.

**Chapter scope**
- Probe 323 correctly rejected a Beat 6 that prematurely performed the terminal resolution/released the children and accepted an unresolved chapter-ending control.
- Its CREATE subtest invented unspecified equipment because the abstract test chapter said only "source-defined gear."
- Conclusion: Beat CREATE truly has no story access, so the current chapter must carry concrete source details that matter inside that chapter; vague placeholders are insufficient.

**Story authority validator**
- Probe 322 exposed the next real failure. Its reasoning explicitly noticed that "the family leaves the building" was absent from STORY, but its final validation JSON incorrectly said `valid: true`.
- The repair/revised-outline portions correctly removed the invented ending.
- Conclusion: the story-facing validator output contract needs one more focused probe before implementation. Test a shorter INVALID/VALID enum contract or an explicit "unsupported action => INVALID" final-decision rule.

### Current likely decomposition

Evidence currently supports this starting architecture:

1. STORY -> CHAPTER BOUNDARIES CREATE
2. STORY + boundaries -> CHAPTER BOUNDARIES VALIDATE/REPAIR if needed
3. STORY + fixed chapters + total segment budget -> BEAT-COUNT ALLOCATION
4. CURRENT CHAPTER + minimal opening context + exact beat budget -> BEATS CREATE
5. STORY + CURRENT CHAPTER + candidate beats -> BEATS VALIDATE
6. STORY + CURRENT CHAPTER + candidate beats + issue -> BEATS REPAIR
7. accepted prior state + CURRENT CHAPTER -> minimal chapter opening context for the next chapter
8. accepted beats -> downstream H3 scene/prompt generation

This is still provisional. Do not implement until the story-authority validator contract is verified.

### Next bridge target

The next direct probes should focus on:

1. story-authority validation where the candidate adds an event present only in a rough chapter draft;
2. INVALID/VALID enum output versus boolean output;
3. concrete chapter-detail preservation when Beat CREATE cannot see `story.txt`;
4. one more chapter-boundary + 6/2 allocation control on a different neutral story shape, to make sure the logic is generic rather than Amy-specific.


### Probe batch 326-335

Queued together on 2026-09-24 to minimize user bridge handoffs:

- 326: story-authority validator using VALID/INVALID enum
- 327: story-authority validator using explicit boolean decision procedure
- 328: story-authority validator using issue-first output
- 329: story-facing beat repair + chapter-outline revision
- 330: non-Amy chapter-boundary generalization
- 331: non-Amy fixed-chapter beat allocation
- 332: concrete-detail preservation when Beat CREATE cannot see STORY
- 333: chapter-ownership / terminal-event leakage control
- 334: non-Amy opening-context extraction/sufficiency
- 335: non-Amy over-split chapter-boundary validator

Early results:
- 326: PASS — unsupported post-story action => INVALID; clean control => VALID.
- 327: PASS — boolean contract also rejects the unsupported action.
- 328: PASS — issue-first contract returns the unsupported action and INVALID.
- 329: beat repair removed the unsupported new journey, but the revised outline introduced "returns home", which STORY did not state. Outline revision therefore needs the same strict Rule-0 source discipline as beat repair.
- 333: PASS — current-chapter validator rejects final-resolution/release leakage into the earlier chapter and repairs it back to an unresolved ending.
- 330/331/332/334/335 were still pending at the last status sweep.

Interpretation so far: the validator does not need a new semantic subsystem. A shorter explicit decision contract fixes the 322 contradiction. Continue favoring the smallest contract that works.


### Probe results 330-335 and next batch 336-345

Completed findings:
- 330 over-split the neutral researcher story into setup / repeated-process / terminal-resolution chapters.
- 331 correctly allocated the fixed two-chapter neutral story as 6/2.
- 332 preserved named items and rejected invented items, but omitted the explicit action of taking the flashlight before later carrying it.
- 334 over-retained irrelevant history: it treated an earlier alarm as required opening context.
- 335 was too permissive and accepted both the over-split and broad two-chapter plans.

Therefore the next batch deliberately narrows those failures:
- 336: adjacent-chapter MERGE check
- 337: adjacent-chapter KEEP control at terminal resolution
- 338: merge-repair of the neutral over-split plan
- 339: third-story broad-boundary generalization
- 340: positive single-fact context necessity
- 341: negative single-fact context necessity
- 342: strict minimal context extraction
- 343: explicit-action ownership validator
- 344: explicit-action ownership repair
- 345: strict Rule-0 chapter-outline revision

Continue to prefer tiny one-decision calls over larger 20B prompts.
