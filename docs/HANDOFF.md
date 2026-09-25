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


### Probe results 336-345

The narrow follow-up contracts worked cleanly:

- 336: PASS — setup/alarm + securing/main repeated process => MERGE.
- 337: PASS — ongoing repeated process -> explicit terminal resolution => KEEP.
- 338: PASS — over-split neutral 3-chapter plan repaired to the desired 2 broad chapters.
- 339: open-ended chapter CREATE still over-split the third neutral story into 3 chapters.
- 340: PASS — later colleague-location/containment fact correctly marked needed.
- 341: PASS — earlier alarm correctly marked not needed.
- 342: PASS — stricter opening-context extraction excluded alarm/breakfast/put-away history and retained only current/later-needed state.
- 343: PASS — validator caught an assigned action that was only implied by a later state.
- 344: PASS — repair explicitly restored the omitted action.
- 345: PASS — strict outline revision removed unsupported aftermath and added nothing new.

Architectural implication:
- Do not keep trying to make the 20B chapter CREATE globally optimize for the fewest chapters.
- Let STORY -> rough ordered chapters prioritize coverage/order.
- Then run a tiny adjacent-chapter MERGE/KEEP decision.
- Python performs the merge deterministically.
- Repeat until no adjacent pair should merge.
- Terminal resolution, major time/location/state resets, or other demonstrated hard resets may justify KEEP.
- This is simpler and empirically more reliable than a global chapter-count validator.

### Probe batch 346-355

Queued to stress-test that merge-loop architecture:
- 346: chef first-pair MERGE
- 347: chef terminal boundary KEEP
- 348: post-merge terminal KEEP
- 349: major time/location reset KEEP
- 350: continuous-process MERGE
- 351: rough-split creation optimized only for coverage/order
- 352: return FIRST adjacent merge pair
- 353: stable two-chapter list returns no merge pair
- 354: chef fixed-chapter 8-beat allocation
- 355: second explicit-action coverage validator control


### Probe-hygiene correction and clean batch 356-365

A test-design flaw was discovered in batch 336-355: several prompts embedded the expected decision directly in the required JSON example (for example, `"decision":"KEEP"`, `true`, or `false`). Those probes are useful for prompt-shape exploration but are not clean independent evidence for the semantic decision.

This was made explicit in `PROJECT_NOTES.md`: future probes must specify allowed output values/types without pre-filling the expected answer.

The flaw was exposed by 347: the model returned KEEP, but its reason said the two sections formed a single coherent arc and that combining them preserved continuity.

A clean replacement batch 356-365 was therefore queued.

Early unbiased results:
- 356: MERGE for chef setup/failure -> securing/repeated adaptation.
- 357: KEEP for repeated adaptation -> final repair/closing.
- 358: MERGE for researcher setup/alarm -> securing/repeated diagnostics.
- 359: KEEP for repeated diagnostics -> final resolution/shutdown/reunion.
- 360: KEEP across a three-month time jump + location reset.
- 361: MERGE for one continuous engine diagnosis/repair/testing sequence.
- 362: boundary-index-only Amy test returned `new_chapter_after:[4]`, correctly placing the refresh boundary after the main repeated zombie-fighting process and before the explicit final-resolution material.
- 363-365 were still pending at the last sweep.

Additional important finding from 351:
- telling the 20B model that over-splitting was acceptable caused severe source drift: it expanded a short chef story into 11 invented micro-chapters, adding technician/menu/staff actions not present in STORY.
- Therefore, do not encourage arbitrary rough over-splitting.

Promising simplification under test:
- number authoritative source statements;
- ask the LLM only for chapter-boundary indices;
- Python builds chapter source spans directly from exact `story.txt` material;
- this may eliminate generated chapter-outline drift entirely.


### Clean boundary evidence 356-367

Unbiased replacement probes removed expected-answer leakage from the JSON examples.

Results:
- 356 chef setup/failure -> repeated adaptation: MERGE.
- 357 repeated adaptation -> final repair/closing: KEEP.
- 358 researcher setup/alarm -> repeated diagnostics: MERGE.
- 359 repeated diagnostics -> final resolution/shutdown/reunion: KEEP.
- 360 three-month + location reset: KEEP.
- 361 continuous engine diagnosis/repair/testing: MERGE.
- 362 Amy boundary indices: `[4]`.
- 363 chef boundary indices: `[3]`.
- 364 researcher boundary indices: `[3]`.
- 365 time-jump boundary indices: `[1]`.
- 366 multi-reset story boundary indices: `[1,4]`.
- 367 fully continuous story boundary indices: `[]`.

Current leading simplification:
1. deterministically enumerate authoritative source statements/spans from `story.txt`;
2. LLM returns only chapter-boundary indices;
3. Python builds each chapter directly from exact contiguous source spans;
4. no LLM-generated chapter outline is required unless later evidence shows one adds value;
5. beat-count allocation happens only after chapter spans are fixed.

This removes a demonstrated source-drift surface: generated rough outlines can invent material, while boundary-index output cannot add narrative facts.

Still to test:
- whether statement-level granularity is sufficient when the natural refresh boundary falls inside one long sentence;
- Beat CREATE directly from exact chapter source spans;
- whether concrete action coverage remains reliable when the chapter input is raw source text rather than a generated outline.


### Source-span architecture lock

The chapter-first probes now support replacing generated rough chapter outlines with exact authoritative source spans.

Evidence:
- boundary-index planning worked across Amy, chef, researcher, time-jump, multi-reset, and continuous stories;
- generated chapter prose repeatedly introduced source drift;
- per-unit SPLIT/KEEP decisions were more reliable than global unit selection;
- exact candidate cut points should be offered only after a unit-level SPLIT decision;
- fact-ID continuity selection avoids LLM rewriting established state;
- persistent/current visible continuity is better treated as Python-owned state.

PROJECT_NOTES.md now defines the current planner as:

1. Python creates exact authoritative source units.
2. Each unit independently receives SPLIT/KEEP_TOGETHER.
3. Only SPLIT units get deterministic candidate cut points; the LLM chooses the cut.
4. Refined units produce chapter-boundary indices.
5. Python builds exact chapter source spans.
6. Fixed spans receive beat-count allocation.
7. Exact current source + opening context + budget go to Beat CREATE.
8. A compact story-facing validator checks required-action coverage, material deviation, and chapter scope.
9. Repair the demonstrated issue and validate again.
10. Python canonical state plus fact-ID semantic selection compose later refresh context.

### Probe results 393-404

- 393: correct internal-inspection selection on one mixed-phase unit.
- 394: false-positive global unit selection; inspect one unit per call instead.
- 395: time/location jump inside one unit -> SPLIT.
- 396: continuous same-phase unit -> KEEP_TOGETHER.
- 397: overly aggressive split of terminal resolution -> immediate report.
- 398/399: visible-state classification consistently selected clothing, visible residue, held object, and visible environment damage while excluding history.
- 400: Python visual continuity + minimal semantic context was sufficient for the Amy refresh chapter.
- 401: protected-space relationship change -> INVALID.
- 402: protected-space-preserving control -> VALID.
- 403: revised large-chapter rule keeps terminal resolution + immediate closure together.
- 404: major time/location reset after resolution -> SPLIT.

### Probe batch 405-414

Purpose:
- deterministic candidate cut-point selection only after a unit-level SPLIT gate;
- one compact validator covering MISSING_ACTION, MATERIAL_DEVIATION, and CHAPTER_SCOPE.

Early results:
- 405: ongoing -> resolution sentence chose the correct earlier cut.
- 407: time-jump sentence chose the correct earlier cut.
- 408: chose a grammatical split in terminal closure, proving candidate cut selection must not run unless the prior unit-level gate returned SPLIT.
- 409: combined validator caught protected-state/location deviation as MATERIAL_DEVIATION.
- 410: combined validator accepted harmless storage-location detail.
- 411: combined validator caught an implied-but-omitted acquisition as MISSING_ACTION.
- 412: combined validator caught premature later-chapter resolution as CHAPTER_SCOPE.
- 413: combined validator caught an extra plot-relevant item as MATERIAL_DEVIATION.
- 406 and the clean VALID control remain to be checked/completed before implementation.


### Final architecture probe conclusions before implementation

Latest results close the remaining planner questions.

Validator:
- 425 confirmed the compact validator returns the first issue in rule order: MISSING_ACTION took precedence over a simultaneous extra-object deviation.
- Clean VALID controls pass.
- The same compact validator has now demonstrated MISSING_ACTION, MATERIAL_DEVIATION, and CHAPTER_SCOPE.

Context:
- semantic relevance selection is not reliable enough for the 20B model;
- 428 and 429 hallucinated relevance for unrelated historical facts;
- 433 showed deterministic CURRENT-only context is sufficient when all needed current facts are present;
- 437 showed omitting the waiting subjects' current location/containment makes context insufficient;
- 438 showed harmless extra CURRENT visible environment state is acceptable;
- therefore canonical state should mark CURRENT vs HISTORY and Python should include current truth while excluding history, without LLM relevance filtering.

Beat allocation:
- generic "majority" wording alone produced 5/3 in 434;
- source-unit-count-aware allocation produced 6/2 in 441;
- 442 accepted 6/2;
- 443 rejected 5/3 as underweighting the majority chapter relative to source-unit ownership;
- current preferred rule: minimum capacity for authoritative source units, then deterministic leftover-beat assignment toward explicitly source-emphasized longer chapters.

Architecture probing has reached diminishing returns. Unless implementation exposes a new concrete failure, the next step should be production implementation on gpt-arc-refresh rather than more prompt probes.


### Production-contract batch 446-455

Results:
- 446: FAIL — mixed source unit containing a source-emphasized main process followed by explicit terminal resolution incorrectly returned KEEP_TOGETHER.
- 447: transport error (HTTP 400), no semantic result.
- 448: PASS — once told the prior gate was SPLIT, chose the correct earlier cut point.
- 449: FAIL — Amy boundary planner returned [2,4], over-splitting setup/protection away from arming/main combat. Gold-implied target is one boundary after unit 4.
- 450: PARTIAL/FAIL — six-beat Beat CREATE covered all source responsibilities and remained unresolved, but invented unsupported presentation/location details ("pistol from jacket pocket", "katana in pantry") and pushed attacking threats toward the basement door. This reinforces that Beat CREATE requires immediate story-facing validation/repair.
- 451: PASS — combined validator caught protected-space/location deviation as MATERIAL_DEVIATION.
- 452: PASS — repair fixed only that demonstrated issue and preserved six beats.
- 453: PASS — clean validator control returned VALID.
- 454: PASS/PARTIAL — Chapter 2 Beat CREATE performed the final confrontation and child release without post-story material; detail remains presentation-level.
- 455: FORMAT FAIL — intended first-issue precedence test was misread as two independent candidates and returned two result objects. The production validator prompt must make clear that all listed beats form one candidate sequence and exactly one first issue is returned.

Conclusion:
- validator/repair architecture remains sound;
- production chapter planning contracts are not yet stable enough to implement unchanged;
- next probes should target only:
  1. large-refresh bias in the per-unit SPLIT/KEEP gate;
  2. preventing chapter-boundary over-splitting of continuous setup/escalation into the main process;
  3. Beat CREATE source-drift controls;
  4. one-candidate/one-first-issue validator output.


### Batch 466-485 summary

Key results:
- Unit gate: mixed ongoing-to-terminal SPLIT passed; continuous KEEP_TOGETHER passed; time-jump SPLIT passed.
- Global chapter-boundary selection remained unreliable: technician, researcher, continuous, and Amy controls over-split.
- Fixed beat/source-unit phrasing worked well and avoided the earlier storage-location invention.
- Unconstrained source-unit assignment could violate order and mix unrelated units.
- Whole-sequence validation could incorrectly infer an omitted assigned action from a later state.

Current test direction:
- evaluate chapter boundaries one candidate at a time;
- enforce deterministic structural rules on beat/source-unit assignment;
- validate each beat only against its assigned source units.

Batch 486-505 is queued for those contracts.


### Batch 486-505 summary

Key results:
- Candidate-by-candidate boundary decisions were still subjective. Amy controls incorrectly accepted boundaries after units 1 and 3; technician controls also accepted an early boundary after unit 2.
- Correct terminal boundary behavior remained consistent: boundary before terminal resolution was accepted; terminal resolution plus immediate closure stayed together.
- Strict beat/source-unit assignment passed for both neutral and Amy controls: [1],[2],[3],[4],[4],[5].
- Structural assignment validator correctly rejected nonadjacent mixing, backward source order, and combining the repeatable unit with other units.
- Structural assignment repair produced the correct monotonic assignment.
- Per-beat validation against only assigned source units correctly caught the omitted Tool-B action, accepted the good control, and rejected an extra Tool-C as MATERIAL_DEVIATION.

Current direction:
- Beat planning decomposition is now strongly supported: deterministic assignment structure -> minimal phrasing -> per-beat assigned-source validation -> targeted repair.
- Chapter boundary judgment remains the main unresolved planner problem.
- Batch 506-525 replaces direct boundary judgment with one-source-unit-at-a-time role classification:
  MAIN_BODY, TERMINAL_RESOLUTION, IMMEDIATE_CLOSURE, RESET_START.
- If role classification is stable, Python will derive chapter boundaries deterministically before TERMINAL_RESOLUTION and RESET_START units, while keeping IMMEDIATE_CLOSURE with its terminal-resolution unit.


### Batch 506-525 summary

The four-way role classifier was still inconsistent:
- setup/preparation was sometimes mislabeled as a reset;
- post-resolution closure was sometimes mislabeled as the resolution itself;
- a real time/location reset was sometimes treated as ordinary main-body material.

The preferred chaptering test is now two independent binary flags per source unit:
- terminal: this unit itself decisively completes the central process;
- reset: this unit begins a new phase after a prior phase because of a major time/location/state reset.

Python derives chapter boundaries from those flags.

Batch 526-545 tests the binary flags across Amy, technician, time-jump, and continuous-process controls.


### Batch 526-545 summary

The binary terminal classifier was stable across all tested shapes:
- setup/preparation/main-process units -> NO;
- decisive final-resolution units -> YES;
- post-resolution closure units -> NO;
- later reset/new-phase units -> NO.

The reset classifier remained too permissive when phrased as any major state/location change:
- Amy's immediate basement move and weapon preparation were incorrectly called resets;
- technician alarm interruption was incorrectly called a reset;
- true time/location discontinuities were correctly identified.

Refinement:
- rename/reset semantics to HARD_RESET;
- HARD_RESET means a narrative discontinuity between phases: explicit time jump, scene break, relocation after a completed phase, or equivalent restart;
- immediate cause-and-effect action in one continuous scene is not a hard reset, even if danger, location, equipment, or state changes.

Boundary rule under test in 546-565:
- always split before HARD_RESET;
- terminal units start a new chapter only when a later non-reset closure unit exists;
- a final terminal unit stays with the current chapter;
- a terminal unit immediately followed by HARD_RESET stays with the current phase and the split occurs at the reset;
- Amy-shaped flags should produce boundary [4] and 6/2 beat allocation.


### Batch 546-565 final chaptering conclusion

The HARD_RESET definition passed every semantic control:
- Amy attack/protection continuation => NO.
- Amy weapon preparation => NO.
- technician alarm interruption => NO.
- technician tool retrieval => NO.
- continuous room-to-room movement => NO.
- three-month field-to-lab transition => YES.
- one-year later return => YES.
- next-morning restart => YES.
- relocation after a completed field phase => YES.
- inciting alarm + immediate reaction => NO.

Terminal classification was already stable in 526-545.

The remaining 556-565 failures were not semantic-planner failures; they came from asking the LLM to execute deterministic boundary/output math:
- several responses changed the requested index-list schema into boolean arrays;
- 565 incorrectly invented a third Amy chapter and returned 6/1/1 instead of the required [4] boundary and 6/2 allocation.

Therefore chapter architecture probing is closed:
- LLM owns only narrow SPLIT/KEEP, exact cut choice, TERMINAL yes/no, and HARD_RESET yes/no.
- Python owns source spans, boundaries, chapters, beat allocation, and structural beat/source-unit assignment.

Implementation started on gpt-arc-refresh:
- story_planner.py added for exact source units, deterministic chapter boundaries/spans, beat allocation, and source-unit/beat assignment.
- narrow TERMINAL and HARD_RESET prompts/parsers added.
- gated internal source-unit SPLIT/KEEP + deterministic cut candidates + exact cut selection added.
- focused local tests pass (14 tests at last local run before bridge integration).

Implementation commits:
- 797759d Add deterministic source-span chapter planner
- 2d8c751 Test deterministic source-span chapter planner
- 05dd476 Add narrow source-unit semantic classifiers
- a27162b Test source-unit semantic classifier contracts
- f95f004 Add exact source-unit refinement pipeline
- d41282f Test exact source-unit refinement

Bridge:
- gpt-runtime commit a4c7fa8 adds a safe run_tests job kind.
- run_tests checks out the requested code branch in a detached dedicated worktree and permits only pytest paths under tests/.
- the local bridge process must be updated/restarted before run_tests jobs can be used.


### Source-span runtime integration started

The new planner is now preferred by `generate_beats_from_story()` when it can
produce fully deterministic beat/source ownership. Unsupported/ambiguous cases
fall back to the legacy ARC loop instead of failing the run.

Implemented:
- `story_planner.py`: exact source units, gated internal split/cut refinement,
  TERMINAL/HARD_RESET classification, deterministic boundaries, chapter spans,
  beat budgets, explicit-repeatability detection, and deterministic ownership.
- `minimax.py`: StoryPlan -> existing phase-runtime compatibility adapter.
- Source-span phases preserve exact `source_text` separately from normalized
  legacy `broad_progression`.
- Beat CREATE and Beat regeneration receive only the current source-span
  chapter text; later/earlier chapter prose is hidden.
- Cached source-span arcs bypass the obsolete broad macro-arc validator.
- Legacy ARC creation/validation remains as a migration fallback.

Recent implementation commits:
- 4ae3daf complete deterministic chapter-plan object
- 83df479 chapter-plan tests
- ea07f46 source-span -> phase compatibility adapter
- b208539 adapter tests
- 5cc25a5 chapter-scoped Beat CREATE
- e186ade source-span macro-arc builder
- e6e2a7d preferred source-span path with legacy fallback
- eed8b75 preferred-path integration test
- 3eaea40 preserve exact source_text through phase parsing

Bridge:
- first branch-native planner test job reached the worker, proving run_tests
  routing works, but the selected Windows Python had no pytest.
- gpt-runtime d7e063a now probes available local Python environments for pytest
  before selecting a runner; this bridge-code change requires a local pull and
  process restart.
- jobs 567-586 are queued implementation-shaped SPLIT/TERMINAL/HARD_RESET checks.
