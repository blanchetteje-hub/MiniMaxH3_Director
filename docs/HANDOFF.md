# MiniMax H3 — Development Handoff

Last updated: 2026-09-25

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository:

`blanchetteje-hub/MiniMaxH3_Director`

Active development branch:

`gpt-arc-refresh`

## Current status snapshot — 2026-09-25

Latest planning capture inspected: **job 935** (`amy-planning-hard-reset-stable-935`),
code revision `82ffecba376244f1781cc0daade4d49e4d513a53`.

Structural planning passes: source-span planning remained active and produced
exactly **2 chapters / 6 + 2 beats**. This is not yet semantic acceptance.

Review of the actual accepted beats and developer log found:
- Beat 4 fires a pistol to sever a zombie's head, then decapitates that same
  zombie with a katana. The production validator explicitly accepted this
  internally contradictory sequence; it checked the actions independently.
- Beat 7 describes the last zombie "shattering into blood", an unsupported
  physical transformation in the realistic action story.
- Beats 4–6 also repeat nearly the same pistol/neck/katana sequence, so action
  variety remains a later prompt-quality concern.
- Beat 3 places the arsenal in a basement closet after the children are locked
  inside the basement. Treat access continuity as a review concern, not a proven
  failure without resolving the exact location/access assumptions.

**Do not advance to full H3 generation yet.** Fix the demonstrated accepted-beat
coherence failure first, within the existing single validator.

Completed batch **936–955** (`gpt-runtime` queue commit `716c003`):
- 10 matched cases, full production validator versus replacement of check B;
- **6/10 reference-label matches for each variant**, all 20 normal completions;
- both accept the captured double decapitation, unsupported body transformation,
  and walking through a still-closed locked door;
- the replacement also regresses the repeated-crystal-removal case, while fixing
  an unsupported dead-target assumption on the corrected final-kill control;
- no proposed production change was adopted;
- manifests and scored verdicts are in `tests/LLM/probes/`.

Completed batch **956–975** (`gpt-runtime` queue commit `4d0e006`):
- compact single validator: **7/10** reference matches;
- isolated coherence diagnostic: **7/10** reference matches;
- all 20 completed normally;
- compact validator caught the actual double decapitation, repeated crystal
  removal, and locked-door crossing; the isolated diagnostic still missed the
  actual double decapitation;
- both accepted the unsupported body transformation and incorrectly inferred
  that a previous neck injury had already killed the last target;
- compact also rejected different-target decapitations by demanding unassigned
  state effects, despite an empty effects list;
- no production change adopted. This does not support adding a separate
  coherence subsystem.

Completed batch **976–995** (`gpt-runtime` queue commit `84cd6c5`):
- **16/20 reference-label matches; 15/20 supported by reviewed explanations**.
  This is a small targeted development set, not broad validator accuracy.
- All 20 returned parseable JSON and completed normally, using 229–957 completion
  tokens. These are semantic failures, not truncation failures.
- 976 correctly catches the actual double decapitation; crystal removal,
  restoration, different targets, explicit magic, coverage, named participants,
  and current-action-versus-aftermath controls also behave as intended.
- 978 rejects the unsupported body transformation for the wrong reason: it
  invents an earlier completed removal/death of the last zombie. Do not count
  this as evidence that the transformation rule works.
- 979 falsely rejects the corrected final kill using the same invented death and
  target-identity assumption.
- 982 accepts traversal through the explicitly closed, locked door; this
  regresses compact v1's correct rejection in 968.
- 992 accepts next-job completion early. Its reasoning copies NEXT JOB into
  CURRENT JOB. The stored request was checked: both jobs were correctly labeled
  and distinct, so this is a model input-role confusion, not a job-builder bug.
- 994 accepts holding as equipped. This control uses bare effect operations;
  production captures wrap operations in event records. Preserve that limitation
  when interpreting the finding or designing any later test.
- Nine valid responses have a single-space issue string. This is secondary to
  the semantic errors; no parser change was made.

**Decision: do not adopt compact v2. Production validation remains unchanged.**
Shortening helped the demonstrated double-removal case but has not preserved
continuity, next-job ownership, and typed-effect semantics reliably enough.
Do not add a coherence subsystem or stack another untested prompt rule.

Reviewed verdicts and limitations:
`tests/LLM/probes/compact_v2_976_995_results.json`.

## Direct local iteration resumed — 2026-09-25

The user authorized autonomous iteration again and supplied direct local access
at `http://127.0.0.1:1234`. This supersedes the previous probe pause. No mailbox
worker is needed for new local probes or acceptance runs. Set
`MINIMAX_LM_STUDIO_URL=http://127.0.0.1:1234` for production CLI runs; the checked-in
default still points to the former LAN host.

GitHub `gpt-arc-refresh` was fetched and fast-forwarded to `2bec02d` before work;
a subsequent explicit pull confirmed it was current. The endpoint advertises
`gpt-oss-20b-uncensored-hauhaucs-balanced`; requests select that model explicitly.

The current development experiment replays the 20 compact-v2 controls with an
unchanged rubric, comparing flat input with explicit before/now/later/after
roles. Both variants wrap the two old bare-operation effect controls in
production event records. `tools/probe_validator_roles.py` saves complete local
requests/responses without putting reference labels into requests. This is an
experiment, not an adopted production prompt. Any candidate still needs fresh
planning acceptance before full H3 prompt generation.

Local verification: 53 tests passed across story planner, source-span generation,
runtime adapter, forward beat validation, and acceptance runner.

Observed repair-input defect fixed: `build_beat_generation_messages` previously
listed every chapter event as required even when regenerating just one beat.
The assignment list now includes only `batch_start..batch_end`, with global
numbers preserved; the exact chapter source remains available as context.
A neutral relay-maintenance regression failed for single-beat and partial-range
requests before the fix and passes afterward. The related generation, repair,
validation, and prompt-pipeline batch passes: 73 tests / 5 subtests.

Two stale continuity fixtures now provide required timed action/end-state text,
and a final-frame path expectation is normalized for Windows: 11 tests pass.
A broader sweep still stops on older `test_continuity_summary.py` expectations
about `retention_analysis`, opening wording, and irrelevant subject retention;
the full suite is not green. Production behavior was not changed for those tests.


## Ultimate goal

> **story.txt -> gold-standard MiniMax H3 prompts**

The pipeline is not the product. Preserve or replace existing code only according to whether it improves the path to the gold prompts.

## Rule 0

`story.txt` is the one narrative source of truth.

Creative execution inside the story is allowed. Material deviation outside the story is prohibited.

Chapter outlines, beats, continuity, and other intermediate artifacts are revisable derived data. They do not overrule `story.txt`.

## Current architecture

The active implementation is source-span chapter-first:

1. Python enumerates exact sentence-sized `SourceUnit` spans from `story.txt`.
2. A local 20B LLM makes only narrow semantic decisions: internal SPLIT/KEEP_TOGETHER where legal cuts exist, TERMINAL, HARD_RESET, visible responsibility, local grouping, source-state extraction, beat generation, and beat validation/repair.
3. Python deterministically owns exact cuts, chapter boundaries, beat arithmetic, source/beat ownership, state application, and refresh scheduling.
4. Chapter text is always sliced from authoritative `story.txt`; the LLM does not rewrite chapter outlines.
5. Visible finite responsibilities are grouped locally; explicit repeated/emphasized source material may receive surplus beats.
6. Beats are generated one chapter at a time from exact authoritative source plus compact opening context and an exact beat budget.
7. The single forward validator checks current-job completion, continuity/possibility, next-job leakage, typed state effects, and material fidelity; rejected beats are regenerated and revalidated.
8. Later chapter opening context is composed from Python-owned CURRENT state, not historical recap or an LLM relevance pass.
9. Source-span chapter starts determine H3 refresh points. The compatibility arc may still serialize as `phases`; logical chapter ownership comes from the source-span planner.
10. Final runtime must work entirely locally: deterministic code + local models. GPT-5.6 Sol is development-time tooling only and is not a production dependency.

## Chapter-controlled H3 modes

Refresh cadence is chapter-controlled.

- First beat of Chapter 1: initial generation with `Minimax_auto_API.json`.
- Later beats in the same chapter: append.
- First beat of every later chapter: refresh.
- Remaining beats in that chapter: append.

Chapter boundaries determine refresh points; fixed interval scheduling is retained only where compatibility requires it.

## Gold refresh as the opening-context reference

The locked Amy benchmark has one refresh at Beat 7. Use that prompt as the concrete reference for what a new chapter needs at its start.

It re-establishes only the immediately useful established facts: location, active subjects, spatial relationship, current pose/held weapon, clothing/persistent visible condition, and relevant off-screen aftermath. It does not replay the prior chapter or explain how those facts came to be.

This is the current design target for chapter opening context: minimal current-state facts sufficient to render the first beat correctly.

## Gold target

Locked benchmark:

`tests/acceptance/gold/amy_zombie_house.json`

It remains the behavioral target. The architecture must derive the desired prompts from the source story, not from knowledge of the gold answers.

Generated prompts do not need string equality; they must preserve required events, exclusions, timing, continuity, audio/music progression, and expected end state.

GPT-5.6 Sol is used only during development as an external fuzzy benchmark against the gold target. The finished program must not require Sol or any cloud LLM to run correctly.

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

`run_tests` jobs specify their target code branch explicitly. The bridge mailbox remains isolated on `gpt-runtime`.

The bridge detects changes to its own script during mailbox sync and restarts automatically.

## Branch state

Completed on `gpt-arc-refresh`:

- architecture-reset branch created;
- `docs/PROJECT_NOTES.md` rewritten around the chapter-first approach;
- chapter-first planner/runtime integration is active on this branch.

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

Queued together on 2026-09-24:

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
- `run_tests` jobs target an explicit code branch in a detached test worktree.


### Source-span runtime integration started

The new planner is now preferred by `generate_beats_from_story()` when it can
produce fully deterministic beat/source ownership. Unsupported/ambiguous cases
fall back to the compatibility ARC path instead of failing the run.

Implemented:
- `story_planner.py`: exact source units, gated internal split/cut refinement,
  TERMINAL/HARD_RESET classification, deterministic boundaries, chapter spans,
  beat budgets, explicit-repeatability detection, and deterministic ownership.
- `minimax.py`: StoryPlan -> existing phase-runtime compatibility adapter.
- Source-span phases preserve exact `source_text` separately from normalized
  compatibility `broad_progression`.
- Beat CREATE and Beat regeneration receive only the current source-span
  chapter text; later/earlier chapter prose is hidden.
- Cached source-span arcs bypass the broad macro-arc validator.
- ARC creation/validation remains as a compatibility fallback.

Recent implementation commits:
- 4ae3daf complete deterministic chapter-plan object
- 83df479 chapter-plan tests
- ea07f46 source-span -> phase compatibility adapter
- b208539 adapter tests
- 5cc25a5 chapter-scoped Beat CREATE
- e186ade source-span macro-arc builder
- e6e2a7d preferred source-span path with compatibility fallback
- eed8b75 preferred-path integration test
- 3eaea40 preserve exact source_text through phase parsing

Bridge:
- first branch-native planner test job reached the worker, proving run_tests
  routing works, but the selected Windows Python had no pytest.
- gpt-runtime d7e063a now probes available local Python environments for pytest
  before selecting a runner.
- jobs 567-586 are queued implementation-shaped SPLIT/TERMINAL/HARD_RESET checks.


### Production prompt lock and runtime wiring update

Production-shaped probes after the initial implementation found and fixed two real prompt issues:

- TERMINAL initially let full-story context leak later resolution backward into an
  ongoing majority-process unit. The prompt now uses FULL STORY only to identify
  the central process and judges terminality only from what TARGET UNIT itself
  explicitly accomplishes.
  - majority fighting => NO
  - last zombie/final test => YES
  - immediate closure => NO
- SPLIT initially treated a one-time finite chain such as
  "move kids into basement -> lock door" as process -> resolution.
  The prompt now requires explicit duration/repetition wording (majority, most,
  repeatedly, throughout, or equivalent) before process -> terminal can split.
  - finite escape/protection chain => KEEP_TOGETHER
  - finite diagnose/replace/confirm chain => KEEP_TOGETHER
  - long repeated process -> final resolution => SPLIT
  - explicit three-month jump => SPLIT

Additionally, Python now skips the SPLIT LLM call entirely when no exact
deterministic cut candidate exists. If story.txt cannot be cut exactly, the unit
cannot legally split.

State effects:
- one narrow source-unit persistent-state extraction call now owns source state;
- activity alone never creates state;
- location/containment, equipment, barriers, terminal threat state, explicit
  visible conditions, drops, and clothing are supported;
- source effects attach only to a source unit's final owned beat;
- extracted location operations are applied after entity-establishing effects;
- Chapter refresh replay uses those effects as SOURCE-AUTHORIZED CURRENT STATE.

Runtime:
- source-span chapter starts now override numeric refresh cadence;
- Amy-shaped 6/2 plan therefore renders modes:
  initial, append, append, append, append, append, refresh, append;
- refresh_interval remains the compatibility fallback for non-source-span arcs;
- refresh workflow validation/load is enabled whenever source-span chapter
  refreshes exist even if refresh_interval is unset;
- Beat CREATE/regeneration receives only current chapter source_text;
- chapter refresh H3 opening context prepends deterministic source-authorized
  CURRENT facts and labels rendered continuity supplemental.

Recent commits:
- 680b344 tighten TERMINAL/SPLIT prompts
- cbc81eb skip impossible split calls
- 8e61ea6 require explicit duration for internal process splits
- 41d6846 derive refresh mode from chapter starts
- 630329a validate refresh workflow for chapter starts
- 4d40c3e chapter-driven refresh tests
- bca4079 narrow source-unit state extraction
- 56e15c9 commit state only on final owned beat
- 6ff209a order state creation before location updates
- aaa1fc5 inject source-authorized state at chapter refresh
- 8267c41 make state operation shapes explicit
- c51d010 test source-authorized chapter opening replay

Verification status:
- bridge run_tests routing works;
- bridge machine currently has no Python environment with pytest, so no project
  pytest suite has executed there yet;
- this is an environment/tooling blocker, not a reported test assertion failure.


### Chapter semantics locked; refresh/state integration

Production-shaped probe results:
- tightened TERMINAL prompt fixed the false positive on Amy's majority-fighting
  unit: ongoing/majority process => NO, last-zombie resolution => YES,
  post-resolution release => NO.
- tightened SPLIT prompt now requires explicit duration/repetition wording for
  the process->terminal case. Amy protection/lock chain => KEEP_TOGETHER;
  mixed "most of story repeatedly X, then final X resolves" => SPLIT;
  one-time diagnose/replace/confirm chain => KEEP_TOGETHER.
- HARD_RESET remains stable: immediate cause/effect => NO; explicit substantial
  time/location restart => YES.
- source units with no deterministic exact cut candidate skip the SPLIT LLM
  call entirely.

Runtime integration:
- source-span chapter openings now drive H3 refresh scheduling.
- for the Amy 6/2 plan, conditioning modes are:
  initial, append, append, append, append, append, refresh, append.
- numeric refresh_interval is retained only as a compatibility fallback when the arc
  is not source-span planned.
- visual-continuity cadence and refresh-workflow validation use the same
  chapter-aware scheduling.

Persistent state:
- one narrow source_unit_state_effects call extracts only explicit persistent
  post-unit state.
- activity alone is forbidden from creating state.
- tested clean cases include basement location/barrier, equipped weapons,
  containment release, explicit location after time jump, clothing, dropped
  item/location, dead threat, and visible blood condition.
- repeated/ongoing fighting/testing returns [] rather than invented state.
- source-unit effects attach only to the final beat assigned to that unit, so
  repeated source units do not commit terminal state early.

Recent commits:
- 680b344 tighten source-unit terminal/split prompts
- cbc81eb skip split LLM calls without an exact cut
- 8e61ea6 require explicit duration for internal process splits
- 41d6846 derive refresh workflow from source-span chapter starts
- 630329a validate refresh workflow for chapter starts
- 4d40c3e test chapter-driven refresh scheduling
- bca4079 add narrow source-unit persistent-state extraction
- abf94b6 test source-unit state effect ownership


### Batch 698-777: local visible-responsibility grouping

Production grouping was tested first as a four-way relationship classifier and
then as a binary MERGE/NEW_TASK classifier.

Results:
- four-way 698-717 was mostly useful but ambiguous cases could spend the entire
  completion budget debating labels;
- binary 738-757 improved completion behavior but still over-merged shared-goal
  and incidental-tool-use cases;
- tightened binary 758-777 produced valid JSON for all 20 probes, but four
  important controls remained wrong: 759, 771, 773, and 775.

Historical intermediate decision (superseded by the exact Amy production check
below):
- two narrow YES/NO judgments were explored after the combined classifier missed
  synthetic controls;
- that decomposition was not adopted because the 20B model became less reliable
  on direct mechanical chains and causal succession.


### Batch 778-797: narrow semantic decomposition

Splitting local grouping into separate continuation/completion and direct-reaction
questions did not produce a generally reliable classifier. The continuation
probe became too literal and rejected obvious mechanical chains such as
retrieve->equip and open->remove; the reaction probe still tended to treat
mere temporal succession as causation.

Do not overfit all synthetic controls. For the real Amy-shaped grouping, the
tightened binary MERGE/NEW_TASK contract from 758-777 already preserves the
important relations:
- breach/attack -> immediate protect/escape: MERGE
- retrieve weapons/gear -> equip: MERGE
- equip -> prolonged/repeated confrontation: NEW_TASK

The remaining real failure is completed protection/escape -> retrieve gear,
which must be NEW_TASK even though both actions respond to the same earlier
danger. Next probes should target that shared-earlier-cause distinction.


### Exact Amy production grouping check — probes 838-842

The current binary local grouping contract was run against the five exact
finite source-unit pairs used by the real Amy planner fixture.

Results:
- 838 breakfast -> breach: NEW_TASK
- 839 breach -> protect children: MERGE
- 840 protect children -> retrieve arsenal: NEW_TASK
- 841 retrieve arsenal -> equip weapons: MERGE
- 842 last zombie -> release children: NEW_TASK

All five production-relevant decisions matched the intended grouping. Synthetic
edge cases from earlier batches remain useful evidence about the 20B model's
limits, but they do not justify adding more grouping layers while the actual
planner path is correct. Treat local grouping as sufficient for the current
production target and move to the next runtime/integration failure.


### Source-span integration checkpoint

After the local planner suite passed 21/21, the dedicated source-span integration
tests were run and repaired against the current chapter-first path.

Fixes:
- escaped literal JSON examples inside the source-unit state extraction f-string;
  the unescaped braces were causing source-span planning to throw and silently
  fall back to the compatibility ARC path;
- refreshed stale source-span test fixtures for current visible-responsibility
  and local-relation calls;
- kept lexical state-effect grounding strict and corrected the adapter fixture
  rather than weakening production validation.

Current local status:
- tests/test_story_planner.py: 21/21 passing
- tests/test_source_span_generation_path.py: passing
- tests/test_source_span_runtime_adapter.py: 11/11 passing

Relevant commits:
- d6524bb8 fix stale local grouping prompt assertion
- 12429e7d update source-span generation fixture for grouped planner
- 6f021d0d ground source-span adapter state fixture
- 1d6e6f89 escape JSON examples in source state prompt
- d5eaef23 use typed threat state in final-beat fixture

Next target: broader beat-generation and refresh integration, fixing only observed
failures on the gpt-arc-refresh production path.


### Broader beat/refresh integration checkpoint

The next integration layer also passes on gpt-arc-refresh:
- tests/test_generate_beats_mode.py
- tests/test_refresh_context_latents.py
- tests/test_forward_beat_validation.py
- tests/test_beat_plan_localization.py

No production changes were required at this layer.

Next target: beat retry/repair/auditing orchestration and structural guarantees,
continuing to fix only observed failures.


### Beat retry/orchestration checkpoint

The stale beat-retry hierarchy fixture was updated to exercise the current
source-span planner rather than intentionally falling into the compatibility
ARC path. The focused retry test now passes.

Relevant commit:
- cb0cfc95 update beat retry test for source-span planner

Next target: confirm the rest of the orchestration/structural layer together:
beat plan auditor, beat repair orchestration, retry hierarchy, and structural
guarantees.


### Orchestration layer checkpoint

The combined orchestration/structural batch now passes on gpt-arc-refresh:
- tests/test_beat_plan_auditor.py
- tests/test_beat_plan_repair_orchestration.py
- tests/test_beat_retry_hierarchy.py
- tests/test_story_arc_structural_guarantees.py

No further production changes were required after updating the stale retry
fixture.

Next target: a broader non-LLM test sweep to catch regressions outside the
source-span/beat path already verified.


### Baseline consistency / guardrail pass

A consistency audit was performed after an acceptance job was accidentally queued
with the old Mistral selector.

Locked baseline:
- active code branch: `gpt-arc-refresh`
- acceptance model: `gpt`
- acceptance bridge jobs now reject any other branch or model
- `minimax.py`, acceptance runner, bridge, desktop defaults, and web defaults
  all use GPT as the baseline
- acceptance no longer derives or injects the gold refresh cadence; numeric
  `--refresh` is disabled for acceptance with a large compatibility fallback,
  so source-span chapter boundaries must independently produce the refresh
  schedule
- PROJECT_NOTES now reflects the production binary `MERGE | NEW_TASK`
  grouping contract; the earlier two-call decomposition remains historical only

Relevant commits:
- f1fe1e02 bridge GPT acceptance default
- fd82b43a stop acceptance from injecting gold refresh cadence
- f2a6811b align acceptance test with GPT
- f2e9a6d7 / 4368283b desktop/web GPT defaults
- 3855a578 project notes grouping/bridge cleanup
- baf342a6 / 94a87f54 finish UI baseline alignment
- 8940055c / 7b61e8c5 remove obsolete gold-refresh inference
- 98da8708 hard-lock bridge acceptance to GPT + gpt-arc-refresh
- a972887e test the acceptance baseline guardrails
- 50dd83b3 document the hard guardrails

Do not evaluate pre-guardrail acceptance captures as the final baseline. After the
local bridge is updated/restarted, run a fresh planning-only Amy acceptance job.

## Validator role-layout experiment complete — 2026-09-25

Bridge probes 996–1015 tested explicit BEFORE/NOW/LATER/AFTER input roles while
keeping the production-style validator responsibilities intact. Reviewed outcome:
15/20 label matches, 14/20 supported by the reasoning. The layout is **not**
adopted.

Observed remaining failures:
- 1002 and 1006 accepted traversal through unresolved locked barriers;
- 1010 accepted hand-held carry as an exact `equipped` state effect even with
  the production event-record wrapper;
- 1013 accepted use of an explicitly unavailable discarded object;
- 1015 accepted an ordinary tool changing a steel object into another material;
- 998 rejected the unsupported-transformation case for the wrong reason by
  inventing a prior terminal state.

Positive controls for resolved barriers, explicit equipment, distinct targets,
restored removals, repeated-work continuation, and explicit fantasy capability
passed. Production validator remains unchanged.

Next: probe two narrow contracts, roughly 10 cases each:
1. CURRENT STATE vs candidate precondition compatibility (barriers, availability,
   explicit capabilities);
2. candidate vs exact typed state effect support.
Only integrate a change if those narrow calls materially outperform the combined
validator on reviewed explanations, not merely labels.

Evidence: `tests/LLM/probes/role_layout_996_1015_results.json`.

## Validator coherence follow-up — probes 996–1063

Astra's repair-scope commit `c192bd3` was retained. It correctly limits beat
repair assignments to the requested beat range and does not change the
chapter-first architecture.

Explicit BEFORE/NOW/LATER/AFTER relabeling of compact-v2 was tested on the 20
existing controls (996–1015):
- 15/20 reference-label matches;
- the legitimate final-kill false rejection was fixed;
- the unsupported body transformation was still rejected for the wrong invented
  prior-death reason;
- locked-door traversal, missing lock coverage, omitted named participants,
  next-job leakage, and held-vs-equipped still failed;
- the typed-effect control used the production event-record wrapper.
Decision: do not adopt the role-layout variant.

A follow-up decomposition batch (1016–1040) showed why the whole validator should
not simply be split into tiny calls:
- NOW coverage became over-literal on a valid paraphrase;
- LATER ownership falsely rejected an identical repeated job;
- barrier continuity completed 4/4 correctly;
- typed-effect support completed 4/4 correctly;
- within-beat coherence completed 3/3 correctly;
- several requests hit repeat HTTP 400 transport errors from the local endpoint.
Decision: do not split the full validator.

The one narrow check directly matching job 935's demonstrated acceptance failure
was then broadened across 20 generic coherence/physics controls (1041–1060),
with transport retries 1061–1063. Every request that reached the model returned
the intended verdict: **19/19 semantic controls correct**; one ordinary-human
liquefaction control still hit HTTP 400 after retry. Passed controls covered
same-target double removal, non-terminal injury, different targets, regeneration,
component removal/reinstallation, crystals/batteries, unsupported material
transformations, explicit magic/technology, explosions, solvents, and ordinary
melting.

Decision: add one narrow within-beat physical/causal coherence gate *after* the
existing production validator returns VALID. It does not own source coverage,
NEXT-job ownership, or typed effects and therefore does not replace or duplicate
those responsibilities. A coherence transport failure consumes the existing
validation retry budget without regenerating the candidate; a semantic coherence
failure regenerates the current beat.

Next required step: run the focused forward-validation/orchestration tests, then
a fresh planning-only Amy acceptance capture. Do not advance to H3 rendering
unless the new capture removes the accepted double-removal / unsupported-physics
failure without introducing a new rejection loop.



## Current execution status — coherence gate verification

Production coherence gate is implemented at commit `0f554b0` and retained.
Generalization evidence is 19/19 correct semantic completions across probes
1041–1063; the remaining case repeatedly returned local HTTP 400 with no model
verdict.

Focused regression job `coherence-gate-tests-1064` is queued on `gpt-runtime`
(commit `2d7f67b`) for:
- forward beat validation;
- beat repair orchestration;
- beat retry hierarchy;
- beat plan localization;
- source-span generation path;
- source-span runtime adapter.

At the last check the mailbox worker had not processed 1064; `gpt-runtime`
still pointed at the queue commit. Do not record those tests as passing until a
result exists.

After 1064 passes, run a fresh planning-only Amy acceptance on the current
`gpt-arc-refresh` head. The acceptance must still derive 2 chapters / 6+2 beats
and must no longer accept the job-935 double-removal or unsupported material
transformation. Only then move on toward H3 prompt generation.


### 2026-09-25 — fresh Amy planning acceptance 1077

- Fresh planning-only acceptance `amy-planning-coherence-current-1077` completed on repository revision `9f0f027c33cb06fefeb0a06bd7dfb46dadddbfea`.
- Structural target is correct: source-span planner produced exactly 2 chapters with 6 + 2 beats.
- The narrow post-validation coherence gate ran on every finalized beat and the old job-935 same-target double-removal / unsupported whole-body transformation failures did not recur.
- The next demonstrated blocker is beat ownership, not chapter allocation:
  - Beat 1 (CURRENT E1) was accepted while also completing E2 and E3.
  - During Beat 1 validation, one rejection explicitly complained that E2 actions were missing even though E2 was NEXT, proving the local validator confused NEXT with CURRENT required work.
  - Beat 6 (CURRENT repeated zombie-killing E6) prematurely completed E7 by killing the final zombie and soaking the house in blood before chapter 2.
- Commit `ed992a5c5a47926a24e211628d1fc62f193c2b85` makes a narrow generic prompt refinement:
  - Beat CREATE says SOURCE STORY is context only and each beat may perform only its listed required event.
  - Beat VALIDATE relabels NEXT as `RESERVED FOR LATER — NEVER REQUIRED IN THIS BEAT`, states CURRENT JOB is the only required work, and explicitly handles identical repeated ongoing jobs as non-terminal instances.
- Generic ownership probe batch `probe-current-later-1078` through `1097` is queued on `gpt-runtime`: 20 cases spanning action, fantasy, sci-fi, domestic activity, repeated processes, and terminal-vs-nonterminal leakage.
- Do not rerun Amy acceptance until the 20 ownership probes are graded. If they are reliable, rerun planning acceptance on the refined prompt; if not, refine the local-LM wording based on the actual misses.


### 2026-09-25 — CURRENT/LATER ownership probe batch 1078–1097

- The 20-case generic ownership probe batch completed across action, fantasy, sci-fi, domestic tasks, repeated processes, and terminal/nonterminal leakage.
- Six probes exhausted the intentionally tiny 256-token probe completion budget before finishing JSON, but their visible reasoning all reached the intended INVALID conclusion; production validator uses a much larger completion budget.
- Of the fully parsed probes, all but one matched the expected label. The lone apparent miss (1086) was an ambiguous/bad control: CURRENT JOB said "defeats the two gate guards" while the candidate merely disarmed one and knocked out the other, so the model's rejection was defensible rather than an ownership failure.
- No demonstrated CURRENT-vs-RESERVED-FOR-LATER confusion remained in the batch.
- Fresh planning-only Amy acceptance `amy-planning-ownership-refined-1098` is queued on `gpt-runtime` to verify the refined prompts end-to-end. Acceptance must still produce 2 chapters / 6+2 beats and must not consume E2/E3 in Beat 1 or E7 in Beat 6.


### 2026-09-25 — beat integrity and final-state validation

- Acceptance 1098 preserved the correct 2-chapter / 6+2 structure and fixed CURRENT-vs-LATER ownership end-to-end.
- It exposed two new concrete defects:
  - malformed model JSON punctuation leaked raw `{` / `}` fragments into finalized beat prose;
  - typed item-state effects could be accepted from an earlier action even when a later action undid the final state.
- Commit `74fce339d04e122ffb86f4a7571bf06df7751b89`:
  - deterministically rejects finalized beat text containing raw JSON delimiters;
  - tells the validator to judge typed item effects from the candidate's FINAL state after all actions in order.
- Commit `43060527d52d4c19e6aef1d17cce10b667da07ee` refreshes stale prompt assertions.
- Generic final-item-state probes 1100–1118 completed at 19/19 intended semantic labels.
- Refreshed unit job `beat-integrity-tests-1120` is queued.
- Fresh planning acceptance `planning-integrity-refined-1121` is queued. It must preserve 6+2 ownership and additionally reject JSON delimiter leakage plus any beat whose final held/equipped state is contradicted by later actions.


### 2026-09-25 — planning integrity accepted; advance to H3 prompt quality

- Acceptance `planning-integrity-refined-1121` completed successfully on the current chapter-first path.
- It preserved the intended 2-chapter / 6+2 allocation and correct CURRENT-vs-LATER ownership.
- Raw JSON delimiter leakage did not recur.
- Beat 3 now ends with the pistol/katana actually strapped/equipped, matching the typed final-state effects.
- The coherence gate caught a real same-target double-removal candidate in Beat 4 and forced regeneration before acceptance.
- Final accepted Beats 4-6 remained non-terminal; Beat 7 correctly owns the last-zombie resolution and Beat 8 the child release.
- `beat-integrity-tests-1120` exposed one stale assertion that still expected `C. NEXT JOB`; commit `13119ec6a40e438f7c8d5c10ce960cb8a521febb` updates it to `C. RESERVED FOR LATER`.
- Planning-integrity work is now sufficient to resume the primary project goal: story.txt -> gold H3 prompts.
- Queued `beat-integrity-tests-1122` as the final focused regression check.
- Queued `gold-prompt-acceptance-1123` in full prompt-generation mode. This uses `--test-prompt-generation`, so it captures H3 prompts without rendering video. Review generated segments fuzzily against the locked Amy gold target; fix the earliest demonstrated prompt-quality failure and keep changes generic.


### 2026-09-25 — first full H3 prompt acceptance reached Director Request 1 budget gate

- Focused beat-integrity regression `beat-integrity-tests-1122` passed 11/11.
- Full prompt-generation acceptance `gold-prompt-acceptance-1123` preserved the correct chapter/beat planning path but produced no H3 prompts because Director Request 1 exceeded the configured input budget before segment 1:
  - estimated input: 5173 tokens
  - configured input budget: 4500 tokens
  - all 8 prompt segments were therefore missing.
- This is the earliest demonstrated full-pipeline failure; it is not an H3 semantic-quality result yet.
- Do not raise the token budget as the first response. The local ~20B target benefits from shorter prompts, and the Director system template contained substantial duplicated authority/continuity language plus a worked example.
- Commit `6e2acf24a1d50d560657f3d2bd074df162d0ed38` compacts Director Request 1 while preserving the locked behavior contracts: CURRENT-only authority, NEXT exclusion, controlled local staging, finite-activity completion, named beneficiaries, tool settling, persistent-state limits, functional labels, timestamp syntax, spatial/continuity handoff, and structured output.
- Queued `director-prompt-tests-1124` for the focused Director/integration regression set.
- Queued `gold-prompt-acceptance-1125` as the next full prompt-generation acceptance. The first gate is simply whether Request 1 now fits under 4500 tokens and all 8 H3 prompt segments are captured. Only after that should generated prompts be fuzzily compared to gold.
