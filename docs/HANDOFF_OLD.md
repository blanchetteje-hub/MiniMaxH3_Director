# MiniMax H3 — Archived Development Handoff

This file contains the historical handoff material that predates the narrow-extractor + deterministic-Python breakthrough beginning at acceptance 1610. For current work, read `docs/PROJECT_NOTES.md` and `docs/HANDOFF.md`.

# MiniMax H3 — Development Handoff

Last updated: 2026-09-26

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository:

`blanchetteje-hub/MiniMaxH3_Director`

Active development branch:

`gpt-arc-refresh`

## Current status snapshot — 2026-09-26, acceptance 1211

- Reviewed full acceptance 1211 on `1d4a9015`. Runtime generated all 8 H3
  segments, but acceptance reported missing Segment 5 and returned exit 2.
  Cause: concurrent `Added States:` output was appended directly to the start
  marker (`SEGMENT 5Added States:`). The start regex required end-of-line.
- Fixed capture start-marker parsing to tolerate trailing diagnostic text,
  matching existing end-marker behavior. Added multi-digit/interleaving regression.
  **8 acceptance-runner tests pass**. Reparsing the original captured log recovers
  segments 1–8 without rerunning the LLM. No semantic success is inferred.
- Earlier semantic regression: planner produced **7+1**, not 6+2. Exact logs
  show false MERGE judgments for protection -> gear retrieval and final kill ->
  child release. Chapter boundary remains before terminal resolution, but both
  wrong local groups change beat allocation. No deterministic counting defect.
- Source-aware Director input was used; no input-budget or completion exhaustion
  blocked this run. Breakfast ends with both children seated with plates but
  does not clearly depict both servings or stove shutdown. Do not call it fixed.
- Other deferred failures in this capture include unsupported neck-twist causing
  limb detachment, children visible outside intended protection during combat,
  and stale carried props. Fix earliest actual failure first: local grouping.
- Controls 1212–1214 completed. Retried baseline 1212 again accepts the start
  button despite reactor OFFLINE (only derived action checked). Both corrected
  breakfast positives preserve appearance/location and return VALID.
- Queued **20 paired grouping probes 1215–1234**, exact five Amy pairs plus
  generic fantasy/sci-fi/task controls: current production prompt versus shorter
  wording restricting immediate-response merging to a newly introduced problem,
  not a subsequent task enabled by completed protection/victory.
- Production grouping prompt remains unchanged pending reviewed results. No
  benchmark-specific rules or extra semantic stage added. Next: grade the batch,
  adopt only supported wording, then rerun planning/full acceptance as needed.
- Evidence: `tests/LLM/probes/acceptance_1211_review.json` and
  `tests/LLM/probes/local_relation_1215_1234.json`.

### 2026-09-26 — grouping A/B review and next probe batch

- Completed paired grouping probes 1215-1234 after the documented queue had not
  actually landed on `gpt-runtime`; the missing batch was reconstructed exactly
  from the checked-in manifest without embedding expected labels in prompts.
- Current production wording performed better than the shorter Astra candidate:
  about **8/10 semantic controls** versus **6/10**. The shorter wording regressed
  calm baseline -> new danger, protection -> gear, victory -> release, and
  completed assembly -> calibration. It is rejected.
- Production still has two generic weaknesses: it can treat completed protection
  as causing the next gear task, and it can split retrieve -> immediate consume
  of the exact retrieved item. The first directly explains acceptance 1211's
  7+1 allocation.
- No production code change yet. Queued probes 1235-1254 for one tighter single
  binary wording that says completed protection/victory/assembly is a stopping
  point and explicitly allows immediate follow-through on the exact obtained/
  opened/started object, including use/consume.
- The 20 new controls are generic (domestic fire, fantasy, sci-fi, diving,
  technical work) and each semantic pair is duplicated to expose instability.
- Next: grade 1235-1254. Adopt only if it fixes the two demonstrated ambiguities
  without regressing the stable controls, then rerun planning/full acceptance.

### 2026-09-26 — current production grouping prompt: 18/20; priority fix

- Probes 1255-1274 exercised the **actual current** production local-relation
  prompt on ten generic relations, each duplicated.
- Result: **18/20 parsed decisions correct**. Duplicate pairs were stable except:
  - completed protection -> fetch equipment: one NEW_TASK, one false MERGE;
  - finished assembly -> calibration: one NEW_TASK, one false MERGE.
- All retrieve->equip, retrieve->consume, open->remove, new-danger->immediate
  protection, victory->release, and unrelated-after-protection controls passed.
- This supports keeping one binary grouping call. The failures are instruction
  precedence ambiguity, not evidence for another planner stage.
- Commit `bb47dacc7081133c37d684c2404f654aa615ee52` changes only prompt order:
  STOPPING POINT is evaluated first; same-object follow-through explicitly excludes
  objects whose build/assembly/repair has already finished; new-problem response
  cannot reinterpret a completed protection/solution as a trigger.
- Queued focused regression `grouping-priority-tests-1275` and full
  `gold-prompt-acceptance-1276`. Acceptance remains the deciding evidence:
  it must restore 2 chapters / 6+2 beats and then expose the earliest remaining
  story.txt -> gold-prompt mismatch.

### 2026-09-26 — acceptance 1276 restores 6+2; beneficiary-role gap is next

- Full acceptance 1276 restored the intended source-span structure: **2 chapters,
  6+2 beats**, with the refresh at Segment 7. The grouping-priority change is
  therefore validated on the real story path.
- The run stopped at Director Segment 1 after three Request-1 retries. Two failures
  were legitimate source misses: breakfast was not delivered to both children,
  and Amy's source-assigned clothing was omitted. One completion verdict also
  hallucinated a plate-holding requirement, so the completion gate remains
  imperfect and should not absorb more responsibilities.
- The upstream accepted Beat 1 is the cleaner demonstrated cause: it rewrote
  "cooking breakfast for her young kids" into "Will drinks milk / Amber watches".
  The beat validator currently requires named relational participants to remain,
  but does not reliably preserve their beneficiary/recipient role.
- Queued paired probes **1277-1296** comparing the current named-participant rule
  with one narrow beneficiary-role sentence. Controls include food/products for
  people, performances and lessons where watching is valid, repair, treatment,
  shelter, and delivery. Do not patch until results are reviewed.
- Next decision: if the beneficiary wording materially improves the paired set
  without false-rejecting performance/instruction controls, add it to the existing
  single beat validator, run focused forward-validation tests, then rerun full
  prompt acceptance.

### 2026-09-26 — bridge pytest freeze diagnosis

- The hung `grouping-priority-tests-1275` exposed a bridge execution bug:
  `run_tests` used blocking `subprocess.run(..., capture_output=True)` instead
  of the bridge's managed local-process runner.
- Consequences on Windows: pytest emitted no live progress, the bridge did not
  register pytest in `_ACTIVE_LOCAL_PROCESS`, Ctrl+C/Ctrl+Q could not reliably
  terminate the pytest process tree, and a genuine hang was indistinguishable
  from a merely quiet test run until the long timeout expired.
- Commit `512b7f7e33cf24056845a2add9d56fa002b89a43` routes pytest through
  `run_local_process`, streams `-vv` progress live, uses the existing timeout
  path/tree kill, and reports timeout metadata.
- Commit `d2b16f0cf91f9bda9d7b937c7c20c9fcce930878` adds a bridge regression test
  proving `run_tests` uses the managed process runner.
- Local worker must pull/restart with this code before another `run_tests` job
  can verify whether any individual test itself also hangs.

### 2026-09-26 — full 8-prompt acceptance reached

- Acceptance `gold-prompt-acceptance-1339` completed all 8 H3 prompts.
- Source-span planning remained at the locked target: 2 chapters, 6+2 beats,
  automatic clean refresh at segment 7.
- Beat 1 beneficiary preservation is fixed in the real pipeline: the generated
  beat keeps breakfast for Will and Amber, Director Request 1 serves both
  children, and Segment 1 now emits an H3 prompt successfully.
- The earliest remaining gold-quality mismatch is now inside H3/Director output,
  not planning: Segment 1 completes and serves breakfast, but ends with the
  cooking process insufficiently settled (the stove/cooking appliance remains
  active and continuity carries a temporary plate).
- Request 1 already has an `activity_tools_settled` claim, but 1339 showed the
  20B model can incorrectly mark it true after settling only one tool.
- Jobs `probe-active-settle-1340` through `probe-active-settle-1359` test a
  generic active-tool/process shutdown rule across cooking, machinery, washing,
  welding, weapons/readiness, performances, ongoing/interrupted work, doors,
  lamps, delivery carts, drills, and vehicle arrival.

### 2026-09-26 — H3 barrier blocking fixed; persistent-state guard is next

- Focused barrier-blocking tests 1384 passed 68/68.
- Acceptance 1385 retained the locked 2-chapter / 6+2 plan and generated all 8 H3 prompts.
- The earlier H3-specific basement ambiguity is materially fixed: Segment 2 now explicitly shows Will and Amber crossing into the basement, Amy remaining outside, the door closing/locking between them, and source-authorized continuity keeps the children inside/out of Segments 3-7 until release in Segment 8.
- The next earliest real H3 validity defect is unsupported persistent-state loss during combat-shaped staging: Segment 4 set Amy's katana on the floor even though source-authorized state had her holding/equipping it and the current source did not authorize dropping it.
- The existing post-Director continuity validator is defined but is not part of the active Request 1 -> Request 2 acceptance path. Do not add a new semantic stage solely for this.
- Request 1's existing independent completion check now also receives AUTHORITATIVE OPENING STATE and must preserve persistent facts unless CURRENT SOURCE/BEAT explicitly changes them. This covers held/equipped items, containment, barrier state, clothing, and other durable facts while allowing source-authorized changes and harmless transient staging.
- Implementation commits: `b83e2763f47e9bee8660286e9fda23b370d85b67`, `1688fc8a2c129d4ac7784fe6dc6acd8a13dbd4a0`.
- Probes 1407-1426 exercise that persistent-state contract on neutral controls; focused tests are queued as 1427. Review those before the next full acceptance.

The entries below are historical; this snapshot supersedes old stop/go decisions.

## Historical snapshot — 2026-09-25

Latest planning capture inspected: **job 935** (`amy-planning-hard-reset-stable-935`),
code revision `82ffecba376244f1781cc0daade4d49e4d513a53`.

Structural planning passes: source-span planning remained active and produced
exactly **2 chapters / 6 + 2 beats**. This is not yet semantic acceptance.

Review of the actual accepted beats and developer log found:
- Beat 4 applies an irreversible terminal transition to one target, then repeats that same
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
- both accept the captured duplicate terminal transition, unsupported body transformation,
  and walking through a still-closed locked door;
- the replacement also regresses the repeated-crystal-removal case, while fixing
  an unsupported dead-target assumption on the corrected final-kill control;
- no proposed production change was adopted;
- manifests and scored verdicts are in `tests/LLM/probes/`.

Completed batch **956–975** (`gpt-runtime` queue commit `4d0e006`):
- compact single validator: **7/10** reference matches;
- isolated coherence diagnostic: **7/10** reference matches;
- all 20 completed normally;
- compact validator caught the actual duplicate terminal transition, repeated crystal
  removal, and locked-door crossing; the isolated diagnostic still missed the
  actual duplicate terminal transition;
- both accepted the unsupported body transformation and incorrectly inferred
  that a previous neck injury had already killed the last target;
- compact also rejected different-target terminal transitions by demanding unassigned
  state effects, despite an empty effects list;
- no production change adopted. This does not support adding a separate
  coherence subsystem.

Completed batch **976–995** (`gpt-runtime` queue commit `84cd6c5`):
- **16/20 reference-label matches; 15/20 supported by reviewed explanations**.
  This is a small targeted development set, not broad validator accuracy.
- All 20 returned parseable JSON and completed normally, using 229–957 completion
  tokens. These are semantic failures, not truncation failures.
- 976 correctly catches the actual duplicate terminal transition; crystal removal,
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


### 2026-09-25 — independent Director CURRENT-BEAT completion gate

- Full prompt acceptance 1125 was the first complete 8-segment H3 prompt capture. The earliest gold mismatch was Segment 1: Request 1 claimed completion after serving breakfast only to Will; Amber never visibly received breakfast and the finite domestic activity did not visibly settle.
- Root cause: Request 1 was trusted to self-report `finite_activity_complete`, `named_beneficiaries_complete`, `activity_tools_settled`, and `beat_complete`; there was no independent semantic check of those claims.
- Generic completion probes 1126–1145 returned 18/20 labels; one miss was an ambiguous "lead through" control, and the real miss treated reactor startup/progress as activation.
- Final-frame entailment probes 1166–1185 also returned 18/20; the activation/startup case improved, one false negative demanded the actor's opening motion despite a visibly open final state, and one real miss treated a battery at 42% and charging as satisfying "charges the battery."
- Exact Amy Segment-1 probe 1186 semantically identified the real defect ("Amber does not visibly receive breakfast") but exhausted the deliberately small 512-token probe budget before emitting final JSON.
- Decision: integrate one narrow independent Request-1 completion check because it directly catches the demonstrated gold failure, but do not treat it as a universal semantic oracle.
- Commit `e40cd31d44526d8bcbc20218da63d0e2b4c5befe` adds a strict `{valid, issue}` completion check after Request 1's own structural/self-completion checks pass. It receives only CURRENT BEAT + RAW SCENE, checks explicit actions/results, finite endpoint, named beneficiaries, and final-frame completion, and feeds an INVALID issue back into the existing Request-1 retry loop. It does not judge style, continuity, future beats, or H3 formatting.
- Queued `director-completion-tests-1187` and full prompt acceptance `gold-prompt-acceptance-1188`.


### 2026-09-25 — Director completion gate integration routing fix

- Acceptance `gold-prompt-acceptance-1188` did not exercise the new semantic gate because of an integration bug: the raw beat-validator settings dictionary was unpacked into `ask_llm`, including unsupported internal keys such as `context`.
- Focused tests `director-completion-tests-1187` also exposed compatibility mocks that did not account for the new independent completion call plus one exact locked dialogue phrase removed during prior compaction.
- Commit `59d7db7a230567ed4e0b91d84e16f3c0a7a9ae6` fixes routing:
  - the completion gate now sets `history_metadata.use_beat_validation_settings=true`, allowing `ask_llm` to apply the frozen validation profile through its supported path;
  - legacy/mock bundles with no `current_beat_text` skip the independent semantic gate;
  - affected mocks now include the extra completion-verifier response;
  - the exact canonical dialogue warning phrase is restored.
- Queued `director-completion-tests-1189` and `gold-prompt-acceptance-1190`.


### 2026-09-26 — Director Request 1 context-headroom fix

- A full prompt-generation run reached Segment 6 with Request 1 estimated at about 4395 / 4500 input tokens. With the local 6044-token total context and 128-token safety reserve, only about 1521 completion tokens remained; GPT-OSS 20B repeatedly exhausted that completion allowance before returning a complete structured response.
- Do **not** treat this as a reason to raise token limits first. The project target remains a local 20B-class model, so shorten the job before enlarging the window.
- Inspection confirmed Request 1 no longer needs full-story or full-phase narrative context. The active generation message now omits both `STORY:` and `PHASE:`, retaining scene-local authority: current beat, reserved next-beat boundary, subjects, opening/current continuity, and the Director contract.
- Regression commit `7b90f576ea661d87dacae6af52f0c04c3eec64cc` locks the omission of STORY/PHASE from Director generation messages. Mailbox job `director-context-tests-1454` passed `tests/test_llm_prompt_pipeline.py` at 61/61.
- The live `gpt-runtime` bridge was stale and lacked the current allowlisted `run_acceptance` support. It was synchronized from `gpt-arc-refresh` in mailbox commit `8e7994ee6b88a7e3297216e7027e6389c71dcf5b`.
- Full prompt-generation acceptance `gold-prompt-context-1455` is queued against `gpt-arc-refresh` + model `gpt`. Review the actual per-segment input/completion headroom before making another prompt-size change.
- If 1455 still truncates, reduce the next largest duplicated Request-1 context block. Do not reintroduce story-wide context and do not special-case the Amy/zombie fixture; any reduction must remain valid for fantasy, science fiction, domestic, dialogue-heavy, and other story shapes.


### 2026-09-26 — context blocker closed; finite beat endpoint is earliest gold failure

- Full prompt acceptance `gold-prompt-context-1455` completed successfully with all 8/8 H3 prompts captured. Removing full STORY/PHASE from Director Request 1 closed the demonstrated Segment-6 context/truncation blocker.
- The earliest gold-quality failure moved back to Beat 1. The source responsibility is Amy cooking breakfast for her children, but the accepted beat was only an ongoing tableau: Amy cooks while Will and Amber sit. Director then faithfully expanded that incomplete beat into more ongoing cooking instead of a completed breakfast result.
- The Request-1 completion verifier was not the earliest incorrect boundary. Its trace explicitly judged the generated beat/source wording as satisfied. The Beat CREATE prompt already asks for finite visible endpoints, but the local 20B model ignored that instruction on this run and the combined Beat validator accepted the incomplete candidate.
- Generic finite-endpoint probes `1456-1475` tested domestic, technical, science-fiction, fantasy, fabrication, delivery, performance, and traversal tasks. Of 19 parsed verdicts, 18 matched the intended finite-completion judgment; one additional case exhausted a deliberately small 512-token completion budget. The one semantic overreach demanded handoff of a forged sword merely because it was made "for" a queen, so that broader beneficiary-handoff rule was rejected.
- Production change: commit `8703f8f51e1fa74689d6d917eff5bff9a998e13d` promotes a narrow FINITE ENDPOINT check to the top of the existing combined Beat validator. It requires a finite activity to reach a natural observable endpoint even when the source uses progressive grammar, while explicitly exempting source-authorized ongoing/repeated jobs. No new semantic subsystem was added.
- Regression assertion commit `a5694846cd1c7adea7b369f976f69426825a9c0f`; wording-only follow-up `3361998dbef07425f567db78690538b52fc7f82d` keeps the rule text stable/testable.
- Focused test job `finite-endpoint-tests-1476` reached 73/74; the sole failure was the new assertion spanning a source-code newline, not production behavior. The wording-only follow-up fixes that test mismatch.
- Full acceptance `gold-prompt-endpoint-1477` is the current semantic verification job. It must show Beat 1 no longer finalizes as an activity still underway while preserving non-terminal repeated combat beats.


### 2026-09-26 — finite endpoint verified; beneficiary delivery is next gold boundary

- Full acceptance `gold-prompt-endpoint-1477` verified the finite-endpoint fix. Beat 1's first candidate (ongoing pancake cooking) was rejected by the combined Beat validator, then regenerated into a completed breakfast action. Repeated combat Beats 4-6 remained non-terminal as intended. The focused regression rerun `finite-endpoint-tests-1478` passed 74/74.
- The earliest remaining gold mismatch is still Segment 1, but it is now narrower: the accepted regenerated beat finishes breakfast yet places Will's and Amber's plates on a counter. The children never visibly receive the food.
- Trace review showed why it passed: the Beat validator's relational-role rule allowed a prepared result to be merely "explicitly assigned" to a beneficiary. That wording is too weak for consumables/explicit hand-offs, but a blanket physical-delivery rule would be wrong for commissioned fabrication/repair/creative work (for example a sword forged for a queen can be complete before delivery).
- Narrow beneficiary probes began at 1479. Cases covering breakfast, tea, parcel delivery, and direct hand-off behaved as intended: consumables/explicit deliveries left elsewhere were INVALID; visible receipt was VALID. Earlier generic finite-endpoint evidence also showed the danger of over-requiring delivery for work merely made FOR someone.
- Production commits:
  - `254a94aa9d07c2115b157e1a3eb63966b15d085d`: Beat validator now requires visible receipt/service for finite consumables or explicit hand-offs when immediate receipt is part of source meaning; merely labeling/leaving elsewhere is insufficient. Work merely made FOR someone is complete without delivery unless source requires it; explicit later pickup/storage is allowed.
  - `1aa819b5df6c1dad9d0b3ff8db69d5cbe96741bd`: applies the same distinction to the source-aware Director Request-1 completion verifier.
  - `5734d7a51032d501c3232ec00d94e26d597efb20` and `10f3d700e70b870904cbccc323aed37b5fbb28e7`: regression assertions.
  - `c8ec81722e4ad1b9e9eb0c1c923ce4a6f4e299aa`: source-aware completion test exercises the correct assigned-source branch.
- Regression job `beneficiary-tests-1499` found only stale test expectations (72/74): one old literal phrase and one test hitting the legacy no-source fallback. Those tests were corrected; rerun is `tests-1501`.
- Fresh full prompt acceptance `gold-prompt-beneficiary-1500` is queued. Do not act on later Segment 2/7 issues until 1500 confirms Segment 1 now visibly serves the children.


### 2026-09-26 — finite endpoint verified; beneficiary delivery is next gold boundary

- Acceptance 1477 verified the finite-endpoint fix: Beat 1's ongoing cooking candidate was rejected, regenerated, and accepted only after breakfast visibly finished. Repeated combat beats stayed non-terminal. Regression 1478 passed 74/74.
- The earliest remaining gold mismatch is Segment 1: finished breakfast plates are left on a counter instead of visibly reaching Will and Amber.
- The active distinction is now: immediate consumables/explicit hand-offs must visibly reach the named recipient; work merely made FOR someone does not require delivery unless the source explicitly says so; explicit later pickup/storage is allowed.
- Commits: 254a94aa9d07c2115b157e1a3eb63966b15d085d (Beat validator), 1aa819b5df6c1dad9d0b3ff8db69d5cbe96741bd (Director completion gate), 5734d7a51032d501c3232ec00d94e26d597efb20 and 10f3d700e70b870904cbccc323aed37b5fbb28e7 (tests), c8ec81722e4ad1b9e9eb0c1c923ce4a6f4e299aa (source-aware test branch).
- Regression 1499 exposed only stale test expectations; corrected rerun is tests-1501.
- Fresh full acceptance gold-prompt-beneficiary-1500 is queued. Do not act on later Segment 2/7 issues until Segment 1 is confirmed fixed.


### 2026-09-26 — beneficiary fix verified; assigned persistent end-state is next boundary

- Acceptance 1500 verified Segment 1 beneficiary completion: Amy now visibly serves breakfast plates to both Will and Amber, and both children take them.
- The next earliest mismatch is Segment 2. The accepted beat/Director output moves Amy into the basement with Will and Amber even though the authoritative typed state effects relocate/contain only Will and Amber.
- Prose-only barrier-scope probing was unreliable: GPT-OSS 20B interpreted “Mara gets Eli and Noor into the shelter” as allowing Mara to enter too. Therefore participant grammar is not the authority.
- The stronger generic authority is Python-owned typed state effects. Commit f06023968ba6f02d012f89818d331dd73b0b7599 promotes an early ASSIGNED PERSISTENT END STATE check: an already-known named subject/barrier/item cannot end with a new persistent location/containment/barrier/item-state change unless a matching typed effect authorizes it. Temporary motion and incidental new threats remain exempt.
- Regression coverage commit 82a1e236ed398bf98dd8372cfa27f9f5ef96f431. Focused regression job tests-1512 passed 74/74.
- Full acceptance gold-prompt-state-1513 is currently queued/running and is the next semantic checkpoint.


### 2026-09-26 — source action ownership fixed; timestamp range is next boundary

- Acceptance 1536 confirmed Segment 1 now visibly performs the assigned cooking action before serving breakfast. Segments 1-2 are semantically acceptable under the PROJECT_NOTES gold-standard acceptance target.
- The next earliest real failure is Segment 3 Request 1 producing malformed/out-of-range timestamps such as 00:200.000 and 01:600.000 inside an 8-second segment, plus filler micro-actions. Existing timestamp correspondence missed these because malformed timestamp-like tokens were not recognized by the normal parser.
- Commit 29506319c85f3aaa7c10c9f80eebfdd5f0ba123c adds deterministic timestamp-range validation: seconds must be 00-59 and timestamps must be before the segment endpoint.
- Commit 53b8c6b9b45ffc050e40a0050f77422f13cfbb7e adds regression coverage. Commit b8f5061c3d58d30e15a30cc0191945dd17279dad refreshes a stale validator wording assertion.
- Focused tests are queued as tests-1537; fresh full acceptance is acceptance-1538.


### 2026-09-26 — timestamp fix exposed Director typed-end-state regression

- Acceptance `acceptance-1538` confirmed the malformed/out-of-range timestamp fix: Director Request 1 no longer emitted the previously observed invalid timestamp forms.
- The earliest real failure moved backward to Segment 2 under fresh-run variance: Amy ended inside the basement with Will and Amber even though the authoritative typed effects relocate/contain only Will and Amber. This is a regression of the previously acceptable Segment-2 boundary, not a reason to reopen chapter/beat allocation.
- The source-only Request-1 completion wording is not stable enough by itself for mover/helper barrier scope. The local 20B model can read verbs such as “guide/escort” as permission for the helper to follow.
- Production change: Director completion validation now also receives the exact typed persistent effects assigned to the active beat. For already-known named subjects/barriers/items, those effects are authoritative for new persistent location, containment, barrier, item, damage, and similar end-state changes. A helper/mover may not inherit another subject’s location/containment effect unless it has its own matching effect. Temporary motion that returns to the opening state remains allowed.
- Commits: `344f68f06549efc7c4d48589beb2308c40923fc8` (production) and `8cc20483ff95a7488d0afcf62206d5469d7053b6` (regressions).
- Queued generic typed-end-state probes `1540-1559` plus focused regression job `tests-1560`. Grade the probes before another full Amy acceptance. Keep the rule generic across domestic, technical, fantasy, sci-fi, containment, barrier, and item-state cases; do not special-case the zombie fixture.


### 2026-09-26 — barrier topology should be state + Python + narrow LLM extraction

Barrier-side continuity is a special high-value case and should not depend on one broad semantic validity judgment.

Current design direction:
- canonical typed state/effects define the authorized persistent transition (for example which subjects end in a destination/container and the barrier's final state);
- Python deterministically derives the allowed transition contract from those effects and opening state;
- a narrow local-LLM call only extracts each named subject's observed final relation to the destination from RAW SCENE using `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`;
- Python compares extracted observations with the authorized contract and decides pass/fail;
- the LLM does not decide whether following another subject was permitted, and helper verbs such as guide/escort/push/lead never grant a crossing by themselves.

This is intentionally more specific than ordinary continuity because the Amy basement boundary has repeatedly demonstrated instruction-fragile failure. It must remain generic for doors, gates, portals, airlocks, shelters, rooms, vehicles, containment areas, and similar barriers.

The existing typed-effect Director change passes focused deterministic tests: `tests-1560` = 79/79. Direct validity probes showed the remaining weakness: GPT-OSS can still reinterpret helper grammar or over-reason missing effects. Therefore do not rely on direct LLM validity for barrier topology. Probe batch `probe-barrier-extract-1561` through `1580` tests the narrower extraction-only contract before production wiring.


### 2026-09-26 — barrier topology extractor accepted; Python now owns validity

- Barrier extraction probes `1561-1580` completed. The 10 RAW-scene cases all produced the intended semantic final-side placement. One RAW case emitted the right meaning with a malformed enum token (`ATDESTINATION`), which the production strict response schema prevents.
- Source-text cases still showed helper-verb ambiguity (for example guide/get/escort can make the 20B model infer the helper followed). Therefore source prose is never passed to the topology extractor. It reads only the generated RAW SCENE.
- Production commit `fdcd79da53e55ed54b871d88e29c96aa73dffc6d` adds the barrier-topology path inside the existing Director Request-1 retry loop:
  - Python derives destination-side expectations from source-owned typed state effects plus canonical opening state;
  - already-known subjects with an authorized location/containment effect must end at the destination;
  - an unassigned subject is forbidden from ending there only when canonical opening state establishes that subject started elsewhere;
  - a narrow LLM call extracts only `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED` from RAW SCENE;
  - Python performs the deterministic pass/fail comparison.
- Commit `b8e5bb2501d581cdfab4e2873dff1b8486db8bb4` routes the extractor through the existing frozen validator-settings mechanism instead of passing internal validator settings directly to `ask_llm`.
- This specifically avoids treating helper verbs as crossing authority while remaining generic for rooms, doors, gates, portals, shelters, airlocks, vehicles, and containment areas.
- Focused mailbox regression/acceptance still needs a real local run before this checkpoint is considered accepted. Do not claim the Amy basement regression closed until that run proves Segment 2 leaves Amy on the authorized side while Will/Amber reach the basement.


### 2026-09-26 — topology validator works; Director generation needed the contract up front

- Fresh full acceptance `acceptance-1582` proved the new barrier-topology validator is catching the Amy basement error rather than accepting it. Segment 2 failed three Request-1 attempts: attempts 1 and 3 were rejected by the deterministic topology comparison because Amy ended in the basement; attempt 2 was rejected by the existing typed-effect completion verifier for the same unauthorized crossing.
- This is a successful detection result but not yet an accepted end-to-end fix: repeated regeneration exhausted the 3-attempt Request-1 budget, so the Director generation prompt itself lacked enough explicit topology guidance.
- The accepted Beat 2 wording included the ambiguous phrase that Amy “secures the door behind her.” Do not deterministically rewrite narrative prose to repair this. Canonical state/effects remain the authority.
- Production commit `580f2d888925b91eb20ecf9c95df26f736339db4` now injects the Python-derived final-side contract into Director Request 1 before generation. Example shape: named subjects with authorized effects MUST end at the destination; a known unassigned subject proven by opening state to start elsewhere MUST NOT end there. Helper/mover verbs cannot override the contract, though temporary crossing is allowed if final placement matches.
- The later topology extractor and Python comparison remain as enforcement. This gives three layers: state-derived generation constraint, narrow RAW-scene extraction, deterministic Python validation.
- Next checkpoint: regression suite, then fresh full Amy acceptance. Success requires Segment 2 to generate a valid scene with Will/Amber in the basement and Amy on the non-basement side without exhausting retries.


### 2026-09-26 — Segment 1 verifier overreach narrowed back to source authority

- Regression suite `tests-1583` passed 79/79.
- Fresh acceptance `acceptance-1584` did not reach Segment 2 because Segment 1 exhausted its three Request-1 attempts. The accepted Beat 1 had strengthened source wording into a specific action: Amy “hands the steaming pancakes” to Will and Amber. RAW scenes where she finished breakfast, placed it in front of them, and they picked it up were rejected because the completion verifier treated the derived beat’s hand-to-hand gesture as a source requirement.
- The verifier also over-policed the children briefly holding ordinary breakfast props as persistent typed inventory changes even though plates/food were newly introduced incidental scene props.
- Production commit `dc3dca728c3baab6ee506a2d90cfa79ad4a4e2c0` restores the intended authority boundary:
  - SOURCE alone defines required actions/results/participant roles;
  - DERIVED BEAT may stage SOURCE but may not strengthen it with a stricter transfer method, prop, destination, or gesture;
  - visible receipt/service/practical access is enough for consumables unless SOURCE itself requires a particular hand-off;
  - ordinary newly introduced serving/consumable props are not treated as persistent inventory merely because a known subject holds them at segment end;
  - durable tracked inventory/readiness/location/containment/barrier/etc. remain governed by opening state and typed effects.
- Generic source-authority probes `1585-1604` are queued, followed by `tests-1605` and fresh full acceptance `acceptance-1606`.
- If 1606 clears Segment 1, immediately inspect Segment 2 to verify the new state-derived barrier contract now generates and validates Will/Amber inside the basement while Amy ends outside.


### 2026-09-26 — Segment 2 topology passes, but barrier identity and location granularity required tightening

- `acceptance-1606` successfully generated through Segment 3 and proved the side-of-barrier fix: Segment 2 ends with Amy in the kitchen while Will and Amber are in the basement. This closes the original “Amy followed the kids into the basement” failure.
- However, Segment 2 still exposed a barrier-identity error: the Director locked a “kitchen door” instead of the barrier securing the basement children. The source-owned typed effect was too generic (`set_barrier_state(entity="door", value="locked")`). Barrier identity is therefore not considered fully solved yet.
- Segment 4 then failed because the completion verifier treated Amy moving from kitchen to hallway as an unauthorized durable location change even though canonical `set_location(Amy, home)` is coarse story geography and both spaces are subareas inside the same home.
- Production commit `7e0ec590d33a90b48cefc3a85528810cbd8df0ff` addresses both demonstrated failures:
  - canonical `set_location` is explicitly coarse story geography/container state; room/hallway/subarea movement inside that location is local staging and does not require a new location effect;
  - when one event has exactly one containment destination and exactly one generic barrier noun (`door|gate|hatch|barrier`), Python deterministically binds that barrier to the destination boundary (for example generic `door` + contained-in `basement` => basement boundary); ambiguous multi-destination cases are left unbound rather than guessed;
  - Director generation receives this barrier binding up front, and the completion verifier rejects satisfying it with an unrelated same-type barrier.
- Regression commit `a88538c6960b08d36888edb2ed4b8e5ca11b4121` refreshes three stale prompt-wording assertions and adds coverage for local movement plus unambiguous/ambiguous barrier binding.
- Source-authority probes `1585-1604` were mixed: several reasoning traces still over-weighted derived staging despite the explicit authority rule. Production should therefore continue relying on source authority + deterministic state checks rather than trusting those direct probes as holistic validity judges.
- Next checkpoint: run focused regressions, then fresh full acceptance. Inspect Segment 2 for **basement-door identity**, not only Amy/children sides, and Segment 4 for allowed kitchen→hallway staging.


### 2026-09-26 — first complete 8-segment acceptance; next hard failure is terminal-action ownership

- `tests-1607` passed 82/82.
- `acceptance-1608` is the first structurally complete 8-segment prompt-generation acceptance after the recent fixes.
- Segment 2 now satisfies both barrier requirements: Amy ends outside the basement, Will and Amber end inside, and the locked barrier is explicitly the basement door. This closes the original basement-side and wrong-door regressions.
- Segment 4 no longer fails on kitchen/hallway-scale movement, confirming canonical `set_location` is now correctly treated as coarse story geography rather than room-level staging.
- The next hard semantic failure is Segment 7. Source assigns “Amy kills the last of the zombies,” but RAW begins with the already-terminal target from Segment 6 and has Amy reuse that target. The completion gate incorrectly accepted interaction with an already-terminal target as evidence of a newly assigned kill.
- Production commit `df49c6aeb5455bf7e2d66a9f0d780b797485efd3` adds a generic terminal-action invariant to beat generation, Director generation, and Director completion: an irreversible terminal result must begin from a target or process that has not already reached that result and visibly cause the transition in the current beat. An already-satisfied terminal state cannot satisfy the same newly assigned action again.
- Regression commit `7899fd73337b0f7e379122cc6ef3fa3b52775e3a` covers the new terminal-target rule.
- Segment 1 still has softer gold-quality distance (children reach for breakfast rather than a stronger fully served/stove-settled endpoint), and Segment 8 has over-elaborated release staging. Do not prioritize those artistic/quality differences ahead of the demonstrated Segment-7 source violation.
- Next checkpoint: regression suite, then fresh full acceptance. Verify Segment 7 uses an unresolved final target rather than reusing an already-terminal target; after that, reassess the earliest remaining gold-quality mismatch.


---

# Archived HANDOFF snapshot — 2026-09-28

The following was moved out of the live handoff because it is historical experiment/acceptance chronology rather than context needed for future decisions.

# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first. It is the architectural source of truth.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active development branch: `gpt-arc-refresh`

## Earlier work in one paragraph

Earlier batches established the source-span, chapter-first architecture: `story.txt` is authoritative; Python owns exact source spans, chapter boundaries, beat arithmetic, typed canonical state, and refresh scheduling; the local 20B handles only narrow semantic work. The Amy gold path stabilized at 2 chapters / 6+2 beats, Beat ownership and finite completion were hardened, and full 8-segment H3 prompt generation became reliable enough that the remaining failures shifted from planning to subtle continuity and physical-state violations. Detailed pre-breakthrough history is archived in `docs/HANDOFF_OLD.md`.

## Current breakthrough and work since

### 2026-09-26 — terminal-action prompt rule was insufficient; moved to narrow extraction + Python decision

- `tests-1609` passed the prompt-contract regression, but `acceptance-1610` still repeated the Segment-7 failure: RAW begins with the already-terminal target from Segment 6 and reuses that same target for a new terminal action.
- This proves broad generation/completion wording is still too instruction-fragile for the local 20B. Do not keep stacking prose rules for this case.
- Production commit `2675c3958abb9aa78c35fbe2f1eaee9ba4fdaee6` adds a narrow terminal-target extraction path inside the existing Request-1 acceptance loop:
  - it runs only when SOURCE explicitly contains a terminal action (kill/destroy/defeat/eliminate/finish/resolve);
  - the LLM answers only the target/process status immediately before that terminal action: `ACTIVE_OR_UNRESOLVED | ALREADY_TERMINAL | UNSPECIFIED`;
  - the extractor does not decide scene validity;
  - Python rejects `ALREADY_TERMINAL` deterministically and feeds that exact failure back into the existing Request-1 retry loop;
  - `UNSPECIFIED` is not automatically rejected, leaving ordinary ambiguity to the existing completion verifier.
- Regression commit `f38802ba98a2f6779a24dd8c7fbc68656f5983d7` covers terminal-action detection, strict enum parsing, and extraction-only prompt scope.
- Generic terminal-target probes `1611-1630` are queued across living/dead creatures, intact/destroyed machinery, active/resolved processes, wounded/unconscious targets, and already-finished tasks. `tests-1631` and full acceptance `acceptance-1632` are queued behind them.
- This follows the same proven architecture as barrier topology: narrow fuzzy extraction by the local model, deterministic Python acceptance, no new semantic pipeline stage.


### 2026-09-27 — terminal-target extraction accepted; earliest remaining gap moved to Beat 1 finite completion

- `tests-1631` passed 87/87.
- Terminal-target probes `1611-1630`: 16/20 strict successes. Three cases reasoned to the expected answer but exhausted the small 300-token probe budget before emitting final JSON; one real miss treated an already unconscious/restrained guard as still unresolved for a `defeat` action.
- `acceptance-1632` fixed the demonstrated Segment-7 failure: the final target is visibly unresolved before Amy performs the assigned terminal action, so the action causes a real unresolved→terminal transition rather than reusing the prior terminal target.
- Commit `a4de6aa4f00d056cf4d35f51fe4afc3d376fb584` makes terminal extraction action-relative: terminal means already dead for `kill`, already destroyed for `destroy`, already neutralized/incapacitated for `defeat/eliminate`, already complete for `finish/complete`, and already resolved for `resolve`.
- The earliest remaining gold-quality failure is now Segment 1. In `acceptance-1632`, Beat 1 was accepted on the first try as “Amy is cooking breakfast...” even though the finite activity had no completion endpoint; Director then ended the segment with Amy still cooking. This is an upstream beat-validation miss, not an H3 formatter problem.
- Production commit `9f188533c8b698de3c5f11c9a4f366c39f03575f` adds a narrow post-VALID finite-endpoint extractor inside the existing beat validation loop. It returns only `COMPLETE | ONGOING | NOT_APPLICABLE`; Python rejects `ONGOING`. Explicit repeated/ongoing assignments (majority/most/repeatedly/throughout/continuing/etc.) return NOT_APPLICABLE and remain non-terminal by design.
- Regression commit `dd81535d44feb2a0e953d51374d2f1ae3644e81f` covers the finite-endpoint extraction contract.
- Generic endpoint probes `1633-1642` are queued. A second 10-case synthetic batch was attempted twice but blocked by connector safety checks; do not treat that as a model result.
- Next checkpoint: regression suite + fresh full acceptance. Beat 1 should be regenerated until breakfast reaches a natural visible endpoint instead of ending while cooking is still underway.


### 2026-09-27 — Beat 1 finite endpoint fixed; terminal extractor needed opening-state authority

- Finite-endpoint probes `1633-1642`: 8/10 strict final JSON successes. The two missing finals (`1633`, `1638`) reasoned to the expected ONGOING classification but exhausted the small probe token budget before emitting JSON. No semantic misclassification was observed in the 10-case batch.
- `acceptance-1644` proves the Beat-1 finite endpoint issue is fixed in production. The first Beat-1 candidate (“still cooking”) was rejected; the accepted candidate explicitly finishes frying pancakes and serves Will and Amber. Segment 1 now ends with both children holding plated breakfast rather than Amy still cooking.
- `tests-1643` exposed only test-harness integration breakage: two mocked beat-validator tests did not know about the new finite-endpoint extraction call and therefore returned the old validity schema. Production acceptance itself completed all eight segments.
- `acceptance-1644` also exposed why Segment 7 can still regress despite terminal-target extraction: the extractor saw only SOURCE + RAW SCENE. Segment 6 continuity knew the zombie was headless/dead, but Segment 7 RAW compressed that to “zombie body lying on the floor,” and the local model reasonably classified that as potentially unresolved.
- Production commit `4b8fabe39c50e1fcbc7a74ae5d923155e9f736f3` now passes AUTHORITATIVE OPENING STATE into terminal-target extraction. Opening state is explicitly already true at 00:00.000 unless RAW visibly changes it, so a terminal state from the prior segment cannot disappear through RAW compression.
- Test-harness commit `8ef7ba4545be2108d379b30385f50e17a1ae230a` updates the two forward-validation mocks to return `COMPLETE` for the new narrow endpoint call. Regression commit `2f451120318c5bb212a2710b747c35d7b829dbaf` asserts the terminal extractor receives and treats opening state as authoritative.
- Next checkpoint: regression suite + full acceptance. Segment 1 should remain complete/served; Segment 7 should reject any RAW that targets a zombie already established terminal by opening continuity.

### 2026-09-27 — acceptance 1646 passes prior fixes; locked-boundary traversal is next topology target

- `tests-1645` passed **89/89**.
- `acceptance-1646` completed all 8 segments. Beat 1 now rejects an incomplete cooking-only candidate and accepts a finished breakfast endpoint. Segment 7 now begins with an active final zombie and performs a real terminal transition, confirming the opening-state-aware terminal extractor fixed the demonstrated terminal-target regression.
- The next demonstrated hard continuity failure remains spatial/barrier topology: Segment 6 invents a larger zombie **emerging from the basement door** while Will and Amber are canonically contained behind that locked basement boundary and the active beat has no barrier-opening/breach state effect. This is not an Amy-specific wording issue; it is a generic locked-boundary traversal invariant.
- Design under test: when canonical opening state says a bound barrier is closed/locked and the active beat has no authorized effect that opens, unlocks, breaks, or otherwise changes that barrier, Python owns the invariant that no subject may traverse it. A narrow local-LLM extractor should answer only whether RAW SCENE visibly establishes a crossing through the named boundary: `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`. Python decides validity. Do not ask the LLM whether traversal was permitted.
- Queued generic traversal probes `probe-barrier-traversal-1647` through `1666` across basement doors, gates, airlocks, portals, vaults, shelters, train doors, laboratory doors, drawbridges, and ambiguous controls. The prompt does not expose the expected answer.
- Do not wire this into production until the probe batch is graded. If accepted, integrate it into the existing Director Request-1 retry loop rather than creating a new semantic pipeline stage.

### 2026-09-27 — locked-boundary traversal extractor accepted and wired

- Processed traversal probes `1647-1659` were **13/13 semantically correct**. The remaining queued controls `1660-1666` had not produced result commits at implementation time and are not counted as model evidence.
- Production commit `93e9997a8cb6b269fbfb12c37872a7e4d366fe28` adds a generic closed-boundary invariant to the existing Director Request-1 loop:
  - canonical opening state identifies a currently closed/locked barrier;
  - Python conservatively binds a generic `door|gate|hatch|barrier` to a containment destination only when that destination is unambiguous;
  - current typed effects disable the prohibition when the beat explicitly authorizes release from that container or opens/unlocks/breaks/destroys the relevant barrier;
  - otherwise Director generation receives an explicit no-traversal contract;
  - a narrow local-LLM extractor classifies RAW SCENE only as `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`;
  - Python rejects `TRAVERSED`. The LLM never decides whether crossing was permitted.
- This specifically targets the demonstrated Segment-6 regression where a zombie was invented as emerging through the locked basement boundary while Will and Amber remained canonically contained behind it. The rule remains generic for doors, gates, hatches, portals/boundaries represented in canonical barrier state, shelters, vehicles, and similar containment boundaries.
- Regression commit `bcaa4891e807bdb9d80fc9bd06f5381a820153f0` adds contract derivation, authorized-release, extraction-only prompt, and strict-parser coverage.
- Queued `tests-1667` and fresh full `acceptance-1668`. Acceptance should verify Segment 6 no longer routes an attacking zombie through the locked basement boundary, while Segment 8 still permits Will/Amber release because its typed containment effects authorize that transition.

### 2026-09-27 — acceptance 1668 closes unauthorized crossing; next failure is barrier final-state contradiction

- `acceptance-1668` completed all 8 segments. The new closed-boundary traversal invariant fixed the demonstrated Segment-6 regression: the third zombie now attacks from the broken kitchen-entry side rather than emerging through the locked basement boundary.
- Segment 8 still permits Will and Amber to leave the basement, confirming that explicit `set_containment(..., value="free")` effects correctly disable the no-traversal prohibition for the authorized release beat.
- `tests-1667` had not produced a result commit when this checkpoint was reviewed, so do not claim that regression suite passed yet.
- Earliest new hard failure is Segment 2 barrier state. RAW visibly locks the basement door at 00:05.500, then at 00:06.500 says Amy is watching through the **open basement door**. This contradicts the same beat's source-owned `set_barrier_state(..., value="locked")` effect even though no subject crosses the boundary.
- The broad completion verifier accepted that contradiction, so do not add more prose to it. Use the established pattern: a narrow local-LLM extractor reports only the final observed state of the source-owned barrier; Python compares it to the typed effect.
- Queued generic barrier-final-state probes `probe-barrier-state-1669` through `1688` across doors, gates, airlocks, vaults, portals, shelters, garage doors, lab doors, and bulkheads. Enum under test: `LOCKED | CLOSED | OPEN | BROKEN | DESTROYED | UNSPECIFIED`. Expected answers are stored only in bridge job metadata, not shown to the model.
- Do not wire the extractor into production until the probe batch is graded. If accepted, integrate it into the existing Request-1 loop alongside topology/traversal extraction rather than creating another semantic pipeline stage.

### 2026-09-27 — closed-boundary fix held; Segment 7 terminal-state wording tightened

- `acceptance-1668` completed all 8 segments and confirmed the new closed-boundary invariant works end to end:
  - Segment 6 no longer invents a zombie crossing through the locked basement boundary; the attacking zombie instead enters from the already-broken kitchen entry.
  - Segment 8 still releases Will and Amber successfully because the active typed containment effects authorize that transition.
- The next demonstrated hard failure is Segment 7 reusing the just-killed Zombie3 as the final live target. Segment 6 visibly puts Zombie3 into an irreversible terminal state; Segment 7 then reuses the same continuing target as if it were unresolved again.
- Developer-log inspection showed the terminal-target extractor received rendered continuity containing explicit prior terminal-state evidence but GPT-OSS still classified the target as `ACTIVE_OR_UNRESOLVED`. Its reasoning treated the target as potentially unresolved because the terminal rule said only “already dead” without defining obvious terminal physical evidence.
- Production commit `c9fec04a21b4a4a57f15eea93769e0dce5a316f2` tightens only the existing action-relative terminal extractor: for an irreversible terminal action, explicit prior terminal-state evidence remains terminal even if RAW later uses a vaguer noun; vague wording does not reactivate the same target.
- Regression commit `512e459627f045208029fcfff6b2544514cb8e35` locks that prompt contract.
- Queued generic terminal-physical probes `1669-1688`, followed by `tests-1689` and fresh full `acceptance-1690`.
- `tests-1667` and traversal controls `1660-1666` had not produced result commits when this checkpoint was inspected; do not count them as evidence unless they later appear.

### 2026-09-27 — barrier final-state extractor accepted and wired

- `tests-1667` passed **93/93**.
- Initial barrier-state probes `1669-1688` produced **19/20 strict final JSON** with no wrong completed JSON. Probe `1675` timed out while debating OPEN vs BROKEN for a damaged-but-passable barrier, exposing an ambiguity in the enum definitions rather than a demonstrated semantic miss.
- The extractor contract was tightened so structural state outranks passability:
  - intact + passable => `OPEN`;
  - damaged/breached/warped but still physically present => `BROKEN`;
  - removed/gone/no longer functioning as a barrier => `DESTROYED`.
- Focused edge probes `1689-1704` were **16/16 strict correct** at review time. Jobs `1705-1708` were still pending and are supplemental.
- Production commit `2983787ea8b9bb9c06f54a7a5383284226443572` adds a narrow final barrier-state extractor to the existing Director Request-1 loop. Python derives source-owned expected states only from the active beat's typed `set_barrier_state` effects and compares them to the local model's extraction.
- Mapping is deterministic: `locked|blocked -> LOCKED`, `closed -> CLOSED`, `open|unlocked -> OPEN`, `broken -> BROKEN`, `destroyed -> DESTROYED`.
- The local model does not decide validity; it only extracts `LOCKED | CLOSED | OPEN | BROKEN | DESTROYED | UNSPECIFIED`. Python rejects any mismatch, including UNSPECIFIED when the active source effect requires a specific final barrier state.
- This directly targets the `acceptance-1668` Segment-2 failure where RAW locked the basement door and then described the same door as open.
- Regression commit `5c77587fd6fc68b8cefe7195779a86fd3b2868a5` adds typed-contract, unlocked/open mapping, structural-precedence prompt, and strict-parser coverage.
- Queued `tests-1709` and fresh full `acceptance-1710`.

### 2026-09-27 — acceptance 1710 reveals generic barrier binding must move upstream into Beat CREATE/VALIDATE

- `tests-1709` passed **97/97**.
- The final-state extractor fixed the prior Director-level Segment-2 contradiction, but `acceptance-1710` exposed an earlier source-binding failure in the generated Beat 2 itself: after putting Will and Amber in the basement, the beat said Amy **locks the kitchen door**.
- This is earlier than Director generation and therefore must be corrected in the beat layer. The existing deterministic binding already has enough information: one generic barrier effect (`door`) + one containment destination (`basement`) => that generic barrier is the basement boundary.
- Production commit `260abb229709226285e72f0dc99d0c90f99dbc8d` reuses that Python-owned binding in both Beat CREATE and Beat VALIDATE:
  - Beat CREATE gets a compact `PYTHON-OWNED BARRIER BINDINGS` section keyed by beat number.
  - Beat VALIDATE derives the same binding from the active beat's assigned typed effects and explicitly forbids reinterpretation as an unrelated nearby barrier.
  - No new semantic call or pipeline stage was added.
- The same production commit tightens the barrier-state extractor wording after supplemental probe `1705` misclassified an intact retracted bulkhead as DESTROYED. `DESTROYED` now requires the barrier to be physically absent/dismantled/destroyed; an intact barrier that retracts/slides/swings/lifts/moves out of the passage is OPEN.
- Regression commit `044cffdd5b356e753d070037f8f23049ed79f35e` adds Beat CREATE binding, Beat VALIDATE binding, and retract/open wording coverage.
- Queued `tests-1711` and full `acceptance-1712`.
- Also queued focused intact-moving-barrier probes `1713-1718`; these are supplemental and should all classify OPEN.
- Acceptance checkpoint: Beat 2 must identify the generic `door` as the basement boundary before Director generation. If that holds, continue to the next earliest demonstrated mismatch rather than adding more barrier rules.

### 2026-09-27 — acceptance 1712 fixes Beat-2 binding; next failure is unnamed destination crossing

- `tests-1711` passed **100/100**.
- Focused intact-moving-barrier probes `1713-1718` were **6/6 OPEN**, confirming the revised barrier-state wording correctly distinguishes an intact moved/open barrier from DESTROYED.
- `acceptance-1712` fixed the upstream generic-door mistake: Beat 2 now explicitly locks the **basement door**, and Director Segment 2 preserves Will/Amber inside while Amy remains outside.
- The next earliest hard failure is Beat/Segment 5. Generated Beat 5 sends a detached target component **down the staircase to the basement floor** while the basement boundary remains canonically locked.
- The beat coherence checker caught one version of this violation on attempt 2 but accepted a retry containing the same protected-destination crossing. Director's current closed-boundary traversal extractor also misses it because RAW never explicitly names the basement door.
- This is still the same topology responsibility, not a reason for a new semantic stage. The observation contract needs to detect crossing of the **bound destination boundary** even when the barrier noun is omitted.
- Queued 20 generic destination-boundary traversal probes `1719-1738` across basements, shelters, vaults, cargo bays, courtyards, labs, garages, engine rooms, bunkers, and archives.
- Probe contract supplies both `BOUND BARRIER` and `PROTECTED DESTINATION`, then asks only whether any physical thing crosses that destination boundary during RAW: `TRAVERSED | NOT_TRAVERSED | UNSPECIFIED`. Explicit destination entry/exit counts even when the barrier noun is absent. Unseen route inference remains forbidden.
- Do not wire until `1719-1738` are graded. If stable, generalize the existing closed-boundary traversal extractor to include destination-boundary crossing rather than creating another validator stage.

### 2026-09-27 — destination-boundary traversal generalized inside existing topology check

- Destination-boundary probes `1719-1738` produced **19/20 strict finals** with every completed JSON semantically correct. Probe `1720` timed out while reasoning toward NOT_TRAVERSED on an intentionally borderline “top of stairs” case; there was no wrong completed classification.
- This is sufficient to generalize the existing closed-boundary traversal observation rather than add another semantic stage.
- Production commit `64970d3ac9de8693872d93228db10012f9056a56` changes the existing traversal extractor to accept both:
  - `BOUND BARRIER`, and
  - optional Python-owned `PROTECTED DESTINATION`.
- When a protected destination is known, the local model now returns TRAVERSED if RAW explicitly shows/states any physical thing moving into or out of that destination even when the barrier noun itself is omitted. It still returns UNSPECIFIED when start/end sides differ but the crossing route is not established, and it must not infer unseen routes.
- The model still does not decide whether traversal is allowed. Python continues to reject TRAVERSED only for a canonically closed unchanged boundary.
- This directly targets `acceptance-1712` Segment 5, where a detached target component was sent from the kitchen down onto the basement floor despite the locked basement boundary.
- Regression commit `8e9bf54e13148ed0559b2d5f9af7a5609e04e018` adds protected-destination prompt coverage and verifies the existing closed-boundary contract exposes the destination to the traversal check.
- Queued `tests-1739` and full `acceptance-1740`.

### 2026-09-27 — acceptance 1740 proves Director catch; impossible crossing must be blocked in Beat CREATE/VALIDATE

- `tests-1739` ran 102 tests with **101 passed / 1 failed**. The failure was a stale assertion in `test_barrier_traversal_prompt_is_extraction_only` expecting the old prompt wording after the traversal extractor was intentionally generalized; this was not a production semantic failure.
- `acceptance-1740` exited structurally incomplete at Segment 5 because the new Director destination-boundary check worked: it repeatedly rejected RAW that crossed the canonically locked basement boundary.
- The run therefore demonstrated an earlier upstream assignment failure. Generated Beat 5 itself placed zombie/body-part action inside the basement while the basement boundary remained locked. Director could not legally realize the beat.
- Production commit `77e9b1c3490336ee04317ee10967fe9332e9103c` moves the same Python-owned closed-boundary constraint upstream without a new semantic stage:
  - `build_beat_closed_boundary_contracts` reuses the existing canonical closed-boundary derivation.
  - Beat CREATE derives canonical state before each beat from the accepted macro arc and includes per-beat `PYTHON-OWNED CLOSED BOUNDARIES`.
  - Beat VALIDATE independently derives the same contract from CURRENT STATE + active typed effects.
  - The contract applies to any person, creature, object, body part, or other physical thing, so an untracked zombie/remnant cannot cross a protected boundary merely because it lacks a canonical entity record.
  - Current typed effects still authorize legitimate opening/release transitions.
- Regression commit `2bed4d36e7d5eb79559822a25d57ae9f13f0ab07` updates the stale traversal-prompt assertion and adds Beat CREATE + Beat VALIDATE closed-boundary coverage.
- Queued `tests-1741` and full `acceptance-1742`.
- Acceptance checkpoint: Beat 5 must no longer propose any attacker/remnant entering the locked basement; Director should therefore be able to realize the assignment instead of exhausting retries.

### 2026-09-27 — acceptance 1742 isolates Beat VALIDATE false positive as the real regression source

- `tests-1741` ran 104 tests with **103 passed / 1 failed**. The sole failure was a synthetic fixture issue: its required events lacked IDs, so `source_authorized_state_before_beat` could not replay the event ledger. The production derivation itself was confirmed separately from the real acceptance log.
- The `acceptance-1742` developer log proves Beat CREATE **did receive** the Python-owned closed-boundary contract for Beats 3-6:
  - `basement door protects 'basement' and begins locked`
  - no person/creature/object/body part may cross unless typed effects authorize it.
- The initial generated Beat 4 obeyed that contract and stayed outside the basement.
- The real regression was Beat VALIDATE falsely rejecting that valid Beat 4 with: “Missing typed state effect for the newly introduced incidental target after its terminal transition.”
- That rejection contradicts the validator's intended scope: a new incidental target/threat that exists only in CURRENT JOB/CANDIDATE BEAT is not part of canonical persistent state and must not require a typed effect merely because the candidate kills/damages/removes it.
- The unnecessary regeneration then produced an impossible basement-door beat, which Director correctly rejected three times. Thus the earliest root cause is the validator false positive, not topology.
- Production commit `ea5cc8bdb1c2ad4d11c0275d44a0126e7fc896e4` strengthens the existing Beat VALIDATE prompt:
  - NEVER reject a newly introduced incidental entity merely for being injured/killed/destroyed/removed without a typed effect.
  - Typed end-state obligations apply only to entities already in CURRENT STATE or explicitly named by STATE EFFECTS IF VALID.
  - The typed-effects section must validate listed effects only; it must not invent missing-effect obligations for new incidental entities.
- Regression commit `16f50f38c202b981a08452113a6c581f2413ddeb`:
  - fixes the synthetic closed-boundary test fixture by adding required-event IDs/dependency;
  - adds explicit coverage for the no-effect-required incidental-target validator rule.
- Queued `tests-1743` and full `acceptance-1744`.
- Acceptance checkpoint: a valid repeated-combat beat that introduces and kills one incidental attacker should survive Beat VALIDATE without requiring a new typed death effect, avoiding needless regeneration into a topology violation.

### 2026-09-27 — acceptance 1744 advances to Beat 6; protect contained occupants from cross-boundary contact

- `tests-1743` ran 105 tests with **104 passed / 1 failed**. The sole failure was a stale assertion expecting the old exact validator wording around listed typed effects; production semantics were otherwise covered and the new incidental-target regression passed.
- `acceptance-1744` confirms the incidental-zombie false positive is gone:
  - Beat 4 survived validation after one unrelated structural retry.
  - Segments 1-5 rendered prompts successfully.
  - The prior Beat-4/5 basement-crossing dead-end did not recur.
- The next earliest hard failure is Beat 6. Generated Beat 6 says: “The third zombie reaches for a child’s arm...” while Will and Amber remain canonically contained behind the locked basement door.
- This is a closed-boundary topology violation even without explicit entry/exit wording: an outside attacker cannot physically reach/grab/bite/strike a contained occupant across a closed boundary.
- Production commit `12b3db0cd40d3754aae370b39faefcbce89cd6fa` strengthens the existing Python-owned closed-boundary contract rather than adding another semantic stage:
  - Beat closed-boundary contracts now list known contained occupants for each protected destination.
  - Beat CREATE is told that while the boundary remains closed, outside entities cannot reach/grab/bite/strike/exchange objects with or otherwise physically interact across the boundary with those occupants.
  - Beat VALIDATE receives the same occupant-aware constraint.
  - Legitimate release/opening beats remain exempt because the existing contract is omitted when active typed effects authorize release/opening.
- Test maintenance commit `5f114095f7de2135e1aee1799655b9eccbba0e71` updates the stale forward-validator wording assertion.
- Regression commit `4dd448521e2401b6801084da07e5ddf20f0ffe95` adds canonical occupant-list coverage and explicit cross-boundary-contact prompt coverage.
- Queued `tests-1745` and full `acceptance-1746`.
- Acceptance checkpoint: Beat 6 must stop giving an outside attacker physical access to Will/Amber while the basement boundary is closed.

### 2026-09-27 — acceptance 1746 completes 8/8; next earliest issue is interior prop access across locked basement

- `tests-1745` ran 107 tests with **106 passed / 1 failed**. The sole failure was a stale exact-string assertion in `test_validator_prompt_includes_assigned_state_effects`; all new contained-occupant regressions passed.
- `acceptance-1746` completed **all 8 segments**. The prior Beat-6 child-access violation was removed after regeneration; the accepted Beat 6 no longer lets an outside attacker reach Will or Amber.
- However, review of the completed run found an earlier remaining topology error in Beat 3:
  - Beat 2 locks Will and Amber inside the basement with Amy outside.
  - Beat 3 then invents Amy's hidden pistol/katana as being in **a closet in the basement** and requires her to retrieve them.
  - Director attempts to satisfy this impossible assignment by having Amy reach through/into the locked basement boundary while still describing the door as locked.
- This is the same closed-boundary responsibility, not a new semantic class: a closed boundary must block physical access not only to contained occupants but also to interior props, targets, and other contents.
- Production commit `16ecc43dd5b6a5e291ee71cf6bc422c62f89c39d` tightens the existing Beat CREATE + Beat VALIDATE closed-boundary contract:
  - while closed, an outside entity cannot retrieve/use an object located inside or otherwise physically interact across the boundary with an occupant, prop, target, or other interior content;
  - do not stage a required action/object inside the protected destination when the acting subject remains outside and no opening/release is authorized.
- Test-maintenance commit `460e69ff80c8265ca0ab12dc9e12b98f76967493` refreshes the stale typed-effect prompt assertion.
- Regression commit `64c43b1f0a35b132fc5aa2b87b6122f2bc7be40a` adds direct coverage for the Beat-3 failure mode: retrieving required weapons from a closet inside a locked protected destination.
- Queued `tests-1747` and full `acceptance-1748`.
- Acceptance checkpoint: Beat 3 must keep the hidden arsenal accessible to Amy on her side of the locked basement boundary; later combat beats must likewise avoid staging required targets/actions inside the protected basement unless an opening/release effect authorizes it.

### 2026-09-27 — acceptance 1748 shows prompt-only closed-boundary rules remain instruction-fragile; probe narrow Beat destination-presence extractor

- `tests-1747` ran 108 tests with **107 passed / 1 failed**. The only failure was a brittle exact-string assertion spanning a prompt line break. Test-maintenance commit `4e9bad14f4dd584d081c7e5bc712cfed1f686658` normalizes prompt whitespace before asserting the sentence.
- `acceptance-1748` did not resolve the locked-basement topology issue:
  - Beat 3 initially placed Amy's hidden arsenal in a basement storage closet after Amy had locked Will/Amber inside and remained outside.
  - Beat coherence rejected one version, but the finalized/assigned Beat 3 still retained basement-storage wording while Director staged Amy in the kitchen area.
  - Beat 4 then explicitly assigned Amy to fight **inside the locked basement**. Beat VALIDATE rejected two door-breach variants but accepted a later inside-basement version, and Director eventually accepted RAW that simply started Amy in the basement instead of showing a crossing.
- This is evidence that more prose in the already-long Beat CREATE/VALIDATE contract is the wrong direction. Per PROJECT_NOTES doctrine, move the deterministic closed-boundary consequence to Python plus a tiny semantic extractor.
- Existing Director final-side extraction is insufficient because a subject may enter a protected destination and later leave. The needed Beat-level observation is narrower:
  - INPUT: one protected DESTINATION, one canonically outside NAMED SUBJECT, one CANDIDATE BEAT.
  - OUTPUT: `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`.
  - `AT_DESTINATION` means the beat places the subject physically at/inside the destination at **any point**, even if it later leaves.
  - The extractor does not decide validity; Python rejects `AT_DESTINATION` when canonical opening state puts that subject outside and no active typed effect authorizes opening/release.
- Queued 20 generic probes `1749-1768` across basements, shelters, vaults, engine rooms, bunkers, labs, cargo bays, courtyards, archives, and garages. Expected answers exist only in job metadata.
- Do not wire the extractor until `1749-1768` are graded. If stable, integrate it as a tiny observation inside existing Beat VALIDATE rather than adding another broad rule or semantic pipeline.

### 2026-09-27 — Beat destination-presence extractor accepted and wired

- Re-read the latest `PROJECT_NOTES.md` before this iteration. The governing doctrine remains: do not stack more rules into an overloaded prompt when an explicit rule keeps being ignored; prefer canonical Python truth + a tiny semantic extractor + deterministic Python decision.
- Destination-presence probes `1749-1768`:
  - **19/20 produced result files**; `1751` had no result file and is not counted.
  - **17/19 exact enum matches**.
  - The two disagreements were only `NOT_AT_DESTINATION` vs `UNSPECIFIED` controls (`1750`, `1766`).
  - Crucially for the production decision, every completed true-positive case where the named subject was physically inside the destination at any point was detected: **9/9 AT_DESTINATION**.
  - No completed negative/ambiguous control was falsely classified `AT_DESTINATION`.
- This is sufficient for a conservative deterministic rule: Python rejects **only** `AT_DESTINATION`; `NOT_AT_DESTINATION` and `UNSPECIFIED` both pass this narrow check and remain subject to the existing validators.
- Production commit `84a6d46a7285304d57497e49064a7b9c07d5fa16` adds the narrow Beat destination-presence extractor inside the existing Beat VALIDATE loop:
  - Python derives active closed-boundary contracts from canonical CURRENT STATE + active typed effects.
  - For each protected destination, Python selects only tracked named subjects mentioned in the candidate whose canonical state places them outside that destination.
  - The local model receives only DESTINATION, NAMED SUBJECT, and CANDIDATE BEAT and returns `AT_DESTINATION | NOT_AT_DESTINATION | UNSPECIFIED`.
  - `AT_DESTINATION` means the candidate establishes the subject physically at/inside the protected destination at any point, even if it later leaves.
  - Python rejects only `AT_DESTINATION` and regenerates the beat. The extractor never decides validity.
  - Authorized opening/release beats remain exempt through the existing closed-boundary contract derivation.
- Regression commit `5d51646a8a3526f8bed64708152a43fa7b45ea59` covers strict parsing, any-point prompt semantics, outside-subject contract derivation, and skipping a subject already inside the protected destination.
- Test-maintenance commit `4e9bad14f4dd584d081c7e5bc712cfed1f686658` from the prior checkpoint normalizes the recurring typed-effect prompt assertion instead of comparing across source line breaks.
- Queued `tests-1769` and full `acceptance-1770`.
- Acceptance checkpoint: after Beat 2 locks Will/Amber in the basement with Amy outside, Beats 3-6 must not place Amy physically inside the basement at any point unless an active source-owned opening/release transition authorizes it. Beat 3's hidden arsenal must therefore be staged somewhere accessible on Amy's side of the boundary.



### 2026-09-27 — acceptance 1770 exposed wrapped-effect plumbing bug in Beat boundary validation

- `acceptance-1770` completed 8/8 but still allowed the old topology failure:
  - Beat 6 explicitly placed Amy fighting zombies **inside the locked basement** while Will/Amber remained contained there.
  - Segment 7 then continued with Amy in the basement although the basement boundary was still canonically locked.
- The newly added Beat destination-presence extractor itself was not the problem. The 1770 developer log contained **no `beat_destination_presence_extract` calls** for the accepted combat beats.
- Root cause: Beat VALIDATE passed assigned effects as event wrappers:
  `[{"id":"E6","state_effects":[]}]`
  while the shared Python boundary derivation expects the flat typed-effect list. `_validate_state_effects` rejected that wrapper shape, so closed-boundary derivation silently returned no contracts. Beat CREATE used flat effects and therefore did receive the boundary contract, explaining the asymmetry.
- Production commit `9ac76adcc7cc81136fe61d899440bd94d2807e09`:
  - adds one deterministic normalizer for Beat assigned effects;
  - flattens event wrappers before Python barrier-binding / closed-boundary derivation;
  - leaves the validator-facing wrapped event structure intact for traceability.
- Regression commit `1b69bdacc52c24bf197f827b197b137efe8790a7` proves the real production shape (wrapped event with empty `state_effects`) still yields the basement closed-boundary contract and destination-presence candidate for Amy.
- Queued `tests-1771` and full `acceptance-1772`.
- Acceptance checkpoint: after Beat 2 locks Will/Amber in the basement with Amy outside, the destination-presence extractor must now actually run on later candidate beats mentioning Amy and deterministically reject any candidate that places her inside the basement before an authorized opening/release.


### 2026-09-27 — acceptance 1772 fixed Beat boundary plumbing; terminal target still ignored supplemental opening fact

- `tests-1771`: 112/113 passed. The sole failure was test-only: an assertion searched the raw multi-line prompt for a sentence that is split by a newline. Commit `00d2b78ec55d037a4dc9830905fc8b7e3f8118ad` checks the normalized prompt instead.
- `acceptance-1772` completed all 8 segments. The wrapped-effect boundary fix worked:
  - Beat VALIDATE now receives `PYTHON-OWNED CLOSED BOUNDARIES` after Beat 2.
  - Accepted Beats 3-7 keep Amy outside the locked basement; no later beat places her inside before Beat 8 release.
  - Beat 8 explicitly unlocks/opens the basement door and releases Will/Amber.
- The earliest important regression is again Segment 7's terminal action. Segment 6 continuity says Amy is near **the already-terminal target on the kitchen floor**, but Segment 7 RAW begins with a generic target wording and reuses that same target again.
- The terminal-target extractor did run, but returned `ACTIVE_OR_UNRESOLVED`. Root cause is authority wording:
  - canonical SOURCE-AUTHORIZED CURRENT STATE does not track the incidental per-segment terminal target;
  - RENDERED CONTINUITY does track it as dead;
  - the extractor prompt called the whole bundle AUTHORITATIVE OPENING STATE but only explicitly said to treat AUTHORITATIVE OPENING STATE as already true, while also labeling rendered continuity supplemental;
  - the 20B therefore treated RAW's vaguer `zombie on the floor` wording as alive and ignored the prior rendered dead-state fact.
- Production commit `dd9b185477684286e2a06de3a7dfecf38d3e2068` makes the narrow terminal extractor's authority rule explicit:
  - canonical state wins only on conflict;
  - rendered continuity is still true for opening facts canonical state does not address;
  - RAW omission or a vaguer noun cannot erase an opening fact;
  - an an opening terminal target remains terminal unless RAW visibly establishes restoration.
- Regression commit `922de00ce1d90ec04e408aa93b250d2d7483f743` locks that prompt contract.
- Queued `tests-1773` and full `acceptance-1774`.
- Acceptance checkpoint: Segment 7 must reject any RAW that reuses the Segment-6 terminal target for the newly assigned terminal action; it must introduce/show an actually unresolved final zombie before the terminal action.


### 2026-09-27 — runtime termination policy: only infrastructure outages are automatically fatal

- User-defined runtime invariant: automatic process termination is allowed only when the required LLM runtime cannot be reached, or when ComfyUI cannot be reached during a render-enabled run. Prompt-generation mode intentionally bypasses ComfyUI. Explicit user cancellation/help remain user-controlled exits, not failures.
- All other failures must recover indefinitely. Local stages may use bounded retry cycles (normally 10 attempts), but exhausting a local budget must move control back to an earlier durable stage/checkpoint instead of ending the Python process.
- Audit found the previous application boundary violated this rule: uncaught `BeatGenerationError`, `ValueError`, `RuntimeError`, workflow/render errors, etc. were printed as “best effort” and then the process ended.
- Production commits:
  - `d53ebabbd5864939a478da1f07159f3fc0842707`: adds a persistent application recovery supervisor; recoverable exceptions restart from the durable generation checkpoint; final render-barrier failures escalate to recovery; stitching now retries forever in 10-attempt cycles instead of giving up.
  - `668aa27a46753eb153ad376d1caf195329ee2d6e`: preserves `LLMConnectionError` through ARC/source-span broad retry handlers so an actual LLM outage cannot be accidentally swallowed; incomplete render sets no longer fall through to best-effort stitching.
  - `c028ecae83e745e9e52378bf549ce6a5362cbece`: recovery resumes only from a checkpoint written/changed by the failed attempt, preventing stale `generation_state.json` from an older run from being consumed.
  - `d7fbe7f38c2fd956dee7d292a92108b05a0215c2`: preserves LLM outage propagation through the remaining ARC create/validate retry scopes.
- Recovery behavior:
  - a recoverable failure after committed segments restarts from the next uncommitted segment;
  - a failure before a trustworthy current-run checkpoint restarts from the beginning/earlier stage;
  - if all segments were committed and a later non-connection failure occurs, recovery deliberately backs up to the final segment rather than terminating;
  - FFmpeg stitch failures retry the same completed set indefinitely;
  - ComfyUI execution/render failures remain recoverable; only inability to connect to ComfyUI is fatal.
- Regression commit `b425eb86c1c491dda3ce92f1a1aa4e56c258ad10` covers supervisor retry and fatal propagation for LLM/ComfyUI connection errors.
- Queued `tests-1775` and full `acceptance-1776`.


### 2026-09-27 — final H3 validation now follows Python-owned truth + tiny extractor architecture

- New direction: do not trust Request 2 / formatter output merely because its JSON parsed and timestamps matched. The actual final H3 string assembled by Python is the render boundary and must be validated there.
- Acceptance 1774 exposed the need: Request 2 still contained `Amy ... flips eggs`, but later deterministic wardrobe reconciliation accidentally consumed the action and the final H3 string contained only `Amy, wearing black tank top and denim jeans.` The pre-assembly formatter checks could not see this loss.
- Final-H3 validation architecture:
  1. Python deterministically pairs RAW SCENE and final-H3 micro-actions by canonical timestamp.
  2. A tiny local extractor sees exactly one RAW micro-action and one final-H3 micro-action.
  3. Extractor returns only `PRESERVED | OMITTED | CHANGED`.
  4. Python owns acceptance: any non-PRESERVED required RAW action rejects the final prompt.
  5. Additional final-H3 invariants should follow the same pattern: deterministic Python contracts plus narrow observation extractors, not one holistic “is this prompt good?” judge.
- Commit `291028805a719b6c45211e6589281db419399091` independently fixes the demonstrated wardrobe-regex bug so canonical wardrobe replacement no longer swallows a following physical action.
- Commit `a92225e1e87357159795634b8341f96bf0c8f1c3` adds the first final-H3 action-preservation extractor and replayable post-Director fixture API.
- Commit `a3786944f47dfb9eb6f7127e5bdac4781e3ab132` adds `tools/run_h3_prompt_fixtures.py`, which runs only final-H3 extractors against saved fixtures.
- Commit `1ca78bf998d716a6c8c6687f49b02a28087d2228` adds the allowlisted bridge job kind `run_h3_prompt_fixtures` for fast local fixture replay after the bridge worker is updated/restarted.
- Commit `ae4c8583a681bf6cfa6049b6fc12d20c67d9e8b7` adds prompt-generation capture flags:
  - `--capture-h3-validation-segment N`
  - `--capture-h3-validation-fixture PATH`
  These save accepted RAW + fully assembled final H3 + minimal authority metadata before ComfyUI and also work in `--test-prompt-generation` mode.
- Seed fixtures:
  - `tests/fixtures/h3_prompt_validation/amy_segment1_preserved.json`
  - `tests/fixtures/h3_prompt_validation/amy_segment1_action_omitted.json`
  Both reuse the accepted Segment-1 RAW from acceptance 1774; only the final H3 candidate differs.
- Queued 20 narrow action-preservation probes `h3-action-1777` through `h3-action-1796` across domestic, fantasy, sci-fi, transfer, repair, travel, and magical cases. Expected labels cover preserved, omitted, and materially changed actions.
- Do not wire this extractor as a production rejection gate until the 20B probe matrix is graded. Once stable, production should reject/regenerate at the final H3 boundary before continuity extraction or ComfyUI.


### 2026-09-27 — final-H3 action extractor promoted to production

- Probe cap calibration on the previous GPT-OSS-20B model:
  - 32 tokens: 20/20 truncated before JSON.
  - 64 tokens: 20/20 truncated before JSON.
  - 128 tokens: 10/20 normal completions.
  - 256 tokens: first baseline batch completed 20/20; semantic stress batch completed 19/20.
  - 384 tokens: semantic stress rerun completed 20/20 normally.
- Production-relevant decision is binary: `PRESERVED` passes; both `OMITTED` and `CHANGED` reject. Across the completed 256/384 semantic stress cases, the extractor was 39/39 on that binary decision.
- Exact three-way labels are intentionally not required for correctness because the model sometimes calls a missing action `CHANGED` instead of `OMITTED`; both mean the final H3 failed to preserve RAW.
- Commit `ca9d68bda53b99b7eea98efad1bde0e570412ba6`:
  - removes the stale/undefined `_active_validator_settings()` dependency from this extractor;
  - pins the proven local profile directly: temperature 0, top_p 1, max_tokens 384, seed 42, repeat_penalty 1.15;
  - runs `validate_final_h3_action_preservation()` immediately after `build_h3_prompt()`;
  - raises `BeatGenerationError` on any non-PRESERVED RAW micro-action, before continuity extraction or ComfyUI.
- Continue testing in ~20-case batches. Prefer generic, domain-diverse cases and focus on false PRESERVED decisions, because false rejection is recoverable via regeneration while false PRESERVED would allow a broken final prompt through.


### 2026-09-27 — final-H3 action extractor locked at 512 tokens

- The 512-token verification batch `1941-1960` completed **20/20 normally**.
- Exact three-way classification was **20/20** on this batch, with **zero false PRESERVED** decisions.
- Combined with prior stress runs, the production-critical binary rule remains clean: only `PRESERVED` passes; `OMITTED` and `CHANGED` both reject.
- Commit `4cacaeb4b1f6bde1a99403c8d80756b475b692f9` raises only this extractor's production completion cap from 384 to **512**. The prompt and deterministic Python gate are unchanged.
- Do not spend more probe budget on this same invariant unless acceptance exposes a concrete false PRESERVED/false rejection. Next step is a fresh full acceptance run to identify the earliest remaining real gold-prompt failure; only then add another narrow extractor if deterministic Python cannot resolve it.


### 2026-09-27 — continuity attached_objects extractor promoted

- Acceptance `1961` completed all 8 segments, but exposed the next earliest quality failure in continuity state:
  - Segment 6 final frame had Amy holding a katana with a zombie head hanging from the blade.
  - Combined continuity incorrectly put `"zombie head"` in Amy's `attached_objects`.
  - Phase 2 serialized that as “her zombie head remains attached to her,” and the bad fact leaked into Segment 7.
- Root cause: the continuity schema allowed `attached_objects` but the local 20B had no narrow semantic definition of attachment-to-Subject versus merely held/carried/attached-to-something-else.
- New tiny extractor contract:
  - input: SUBJECT, one CANDIDATE ATTACHED OBJECT, FINAL-FRAME TEXT;
  - output: `ATTACHED | NOT_ATTACHED | UNSPECIFIED`;
  - Python keeps the claim only for `ATTACHED`; both other values are dropped.
- 50-probe batch `continuity-attachment-1962` through `2011`:
  - 50/50 normal completions;
  - 48/50 exact three-way labels;
  - the two exact misses were only `UNSPECIFIED -> NOT_ATTACHED`;
  - 50/50 on the production keep/drop decision;
  - zero false `ATTACHED`.
- Production commit `ded7f4c94af0c91af82bdd090d545be56bdd0d12` adds the extractor with the proven short-prompt profile (temperature 0, top_p 1, max_tokens 512, seed 42, repeat_penalty 1.15) and filters combined-continuity `attached_objects` immediately after Subject guarding.
- User preference for future narrow extractor tests: target ~50 probes per batch when practical.


### 2026-09-27 — acceptance 2012 fixed attachment corruption; earliest remaining issue is RAW physical coherence

- `acceptance-2012` completed all 8 segments.
- The Segment-6 attachment bug is fixed:
  - combined continuity now keeps Amy's `attached_objects` empty;
  - the zombie head is no longer serialized as physically attached to Amy;
  - Segment 7 no longer inherits the corrupted “head remains on Amy” fact.
- Gold comparison discipline remains fuzzy, not reconstructive:
  - do not require exact wording, timestamp count, choreography, camera path, or harmless staging;
  - only source/continuity violations or failures of the four hard H3 prompt-writing rules are actionable.
- The earliest actionable mismatch is Segment 1 RAW physical coherence:
  - at 00:02.500 Amy explicitly keeps the pancake tray in her left hand;
  - at 00:03.500 she extends that same left hand to offer Amber a pancake, with no release/transfer/repositioning;
  - this is a concrete simultaneous-use conflict, not a harmless gold-staging difference.
- Existing beat coherence runs before Director generation and cannot catch this; there is no RAW-scene adjacent-action coherence gate yet.
- Queued 50 generic narrow probes `raw-coherence-2013` through `raw-coherence-2062`.
  Extractor contract:
  - input: PREVIOUS MICRO-ACTION + NEXT MICRO-ACTION;
  - output: `COMPATIBLE | CONFLICT | UNSPECIFIED`;
  - intended Python decision if proven: reject/regenerate RAW only on `CONFLICT`.
- Probe batch spans hand occupancy, two-handed objects, feet/pedals, body-position transitions, dropping/retrieving objects, carried children, tools, weapons, controls, and explicit repositioning.


### 2026-09-27 — abandoned broad limb LLM judgment; deterministic explicit same-hand guard

- RAW physical-coherence investigation after acceptance 2012:
  - broad adjacent-action LLM judge was too permissive;
  - narrower binary limb-conflict judge reached 49/50 twice but repeatedly missed the same staff->clap edge case;
  - fact-extraction variants were also unstable: invented releases, collapsed unrelated gestures onto held objects, inconsistent object labels, malformed JSON, and high reasoning/token cost.
- Do not continue stacking prompt rules for this failure class.
- The actual observed acceptance bug is much narrower and explicitly lexical:
  - one RAW micro-action says a named left/right hand is occupied holding/carrying/gripping an object;
  - the immediately following RAW micro-action explicitly names that same hand and performs a different object-manipulation action;
  - no explicit release/transfer/reposition occurs and the held object is not referenced.
- Production commit `92390fc0cfa00da01739db38059cf41d5bae46e2` adds a conservative deterministic Python guard for only that explicit pattern. Ambiguous same-hand motion is skipped rather than guessed.
- Regression commit `80e86ba87ea4a47501abbed22716405e46752731` adds controls for:
  - the Amy tray conflict;
  - valid same-hand same-object continuation;
  - explicit release before reuse;
  - ambiguous same-hand movement that must be ignored.
- Queued `tests-2313` and full `acceptance-2314`.


### 2026-09-27 — acceptance 2318 fixed wrong-door binding; next failure is explicit RAW end-state contradiction

- `acceptance-2318` completed all 8 segments.
- The prior wrong-door failure is fixed: generic `door` state extraction is now qualified by the Python-owned containment destination, so Segment 2 ends with the basement door locked rather than accepting an unrelated kitchen door.
- `tests-2317` exposed two false-positive regressions in the new deterministic RAW guards:
  - the same-hand verb regex treated the noun `hand` as an action verb;
  - the set-down guard treated any object mentioned later in the placement sentence as the placed object.
- Production commits:
  - `c8fc549a61b4f341b79138eedac8d29dc1c7ec66`: narrows both RAW guards and extends explicit set-down/held-again checking to the trailing `End continuity state`.
  - `f1c33243f53bad6e5196edd16c88b6b2479063b4`: handles `in front of` placement wording and simple singular/plural object matching.
  - `6d486cb4f95f5e6b3eb720513867e64fc9fdab56`: adds a regression for the demonstrated Segment-1 contradiction.
- Earliest actionable acceptance failure is Segment 1 RAW:
  - the last timed action sets the second breakfast plate in front of Amber;
  - the trailing end state then says Amy is holding two plates;
  - no pickup/reacquisition occurs.
- This remains a deterministic explicit-state contradiction, so do not add another broad LLM coherence judge.
- Next checkpoint: focused regression suite + fresh full acceptance. Segment 1 must regenerate if its trailing end state contradicts the final visible object state.


### 2026-09-27 — acceptance 2320 exposed continuity fallback rolling canonical state backward

- `tests-2319`: 29/29 passed.
- The prior RAW object-state/end-state regressions are fixed.
- `acceptance-2320` no longer reproduced the Segment-1 plate contradiction.
- Earliest real failure moved to continuity after Segment 2:
  - RAW and final H3 correctly put Will and Amber in the basement and lock the basement door.
  - The combined continuity extractor failed schema three times.
  - Its fallback copied the pre-Segment-2 rendered continuity state, resurrecting Will/Amber in the kitchen doorway and discarding the newly committed containment/location/barrier facts.
  - Segment 3 then inherited that stale state and continued with the children in the kitchen.
- This is a deterministic ownership bug, not an LLM reasoning problem. Python-owned source state must survive continuity extraction failure and must override conflicting prompt-continuity claims.
- Production commits:
  - `d2bb84704a9154a10517a9deb08adba9ba5bccb4`: adds a narrow typed-effect -> continuity overlay helper.
  - `976d81b4cea7a746f2e0c821cb8e88332ed8e280`: applies assigned source effects after combined continuity extraction and on fallback; generic barrier names are qualified with the Python-owned containment destination.
  - `da7f9046583730acc31bd19c6b5228d20aa61082`: regressions for authoritative containment/location and barrier naming.
- Next checkpoint: focused regressions + fresh acceptance. After Segment 2, Will/Amber must remain in the basement and the basement door must remain locked even if the continuity LLM returns unusable JSON.


### 2026-09-28 — acceptance 2322: canonical continuity now survives, but stale move metadata and duplicate clothing state remain

- `tests-2321`: 31/31 passed.
- The Segment-2 continuity fallback no longer moves Will/Amber back to the kitchen. Python-owned containment/location/barrier state survives continuity schema failure.
- Earliest remaining defect actually begins in Segment 1 ARC state effects:
  - Amy's tank top and jeans are correctly emitted as `set_clothing`;
  - the same garments are also incorrectly emitted as `set_item_state=equipped`;
  - the authoritative continuity overlay then treats those item-state effects as held/equipped props.
- Segment 2 also reveals stale transient continuity after an authoritative move:
  - Will/Amber are correctly moved to `basement`;
  - old visual fields survive: `pose_action=eating pancakes`, `topology=seated`, and `spatial_relationships=at kitchen table`.
- Fixes:
  - `1551a10777ac00cd531c1f67a517abe19afb7997`: reject same-garment duplicate `set_clothing` + `set_item_state` pairs, and clear location-dependent transient visual fields when authoritative containment/location changes.
  - `41692bf849a96ccda6dba2881c1cb19909af2d75`: regressions for duplicate clothing state and stale move metadata.
- Held ordinary props are intentionally preserved across authoritative movement unless source state says otherwise; e.g. a child may still carry a pancake into the basement.
- Next checkpoint: focused regressions + fresh full acceptance.


### 2026-09-28 — acceptance 2324: explicit broken barrier was weakened to generic object damage

- `tests-2323`: 33/33 passed.
- Duplicate clothing item-state and stale move metadata fixes are holding.
- Earliest remaining defect is in ARC typed state for E2:
  - source/event says the kitchen door window is broken/shattered;
  - ARC emitted `set_object_state(entity="kitchen door window", value="damaged")`;
  - continuity then correctly preserved that weaker but wrong canonical fact as `kitchen door window damaged`.
- This is a deterministic typed-operation selection issue, not a need for another semantic pipeline.
- Production commits:
  - `01fa61d65795773e13e45fb2678001229d059fe1`: for barrier-like entities (door/window/gate/hatch/barrier), explicit break/shatter/smash wording rejects generic object damage and requires `set_barrier_state=broken`.
  - `03b8b43255f4b0e979098496733add0cc8559040`: regressions for reject/accept cases.
- Next checkpoint: focused regressions + fresh full acceptance. Segment 2 canonical continuity should say the kitchen door window is broken, not merely damaged.


### 2026-09-28 — acceptance 2326: source-span planner incorrectly fell back to legacy ARC after one repairable extractor error

- `tests-2325`: 35/35 passed.
- The explicit broken-barrier rule itself is correct.
- `acceptance-2326` exposed a control-flow regression:
  - source-span state extraction produced `set_object_state=destroyed/damaged` for an explicitly broken window;
  - deterministic validation correctly rejected it;
  - instead of repairing that tiny extractor response, the planner immediately abandoned source-span planning and entered the legacy ARC loop.
- This violates the current architecture direction: repairable source-span/state-extractor failures must remain inside the current deterministic + tiny-extractor path rather than switch semantic architectures.
- Production commits:
  - `a58e538712dd10d05b254794f421583ff323f295`: source-unit state extraction now retries locally with the exact validation error as correction feedback; a failed source-span plan restarts source-span planning instead of entering the legacy ARC loop.
  - `a455b345551ae4a2a99c62aa0ded3fbbd0147206`: regression proving an invalid broken-window object-state response repairs to `set_barrier_state=broken`.
- Next checkpoint: focused regressions + fresh full acceptance. Expected: source-span planner remains active, repairs the broken-window state locally, and does not print/use the legacy ARC fallback.


### 2026-09-28 — broken-barrier validator loop was over-scoped

- During `acceptance-2328`, source-span planning repeatedly rejected Source Unit 3 with:
  `Explicitly broken/shattered barrier-like entities must end with set_barrier_state=broken.`
- Root cause: the deterministic rule looked for any break/shatter word anywhere in the source unit, then required every barrier-like effect in that unit to be `broken`. A unit containing both a broken kitchen window and a separately locked basement door therefore rejected the legitimate locked-door effect.
- Fixes:
  - `bdc89ea828f360115d8c697bae57efef4b232c2c`: scope break-state enforcement to the specific non-generic barrier entity named in the same clause as the break/shatter wording; generic `door/window/gate/hatch/barrier` names are skipped rather than guessed.
  - `d05b62740b615f4d55ce3a26fa555c9e44f2c43e`: regression for a source unit containing both a broken kitchen door window and a locked basement door.
- The in-flight `acceptance-2328` run used the bad validator and should be ignored/cancelled if still running.


### 2026-09-28 — acceptance 2330: repeated irreversible target state

- `tests-2329`: 37/37 passed.
- `acceptance-2330` completed all 8 segments on the source-span path. The broken-window state is now `set_barrier_state=broken`; no legacy ARC fallback occurred.
- Earliest remaining continuity defect was a repeated irreversible target transition: the next segment reused a target whose prior exact final frame had already established the relevant terminal result.
- Existing terminal-target extraction was the correct mechanism, but reduced continuity had dropped the decisive prior-frame fact and trigger logic was too specific.
- The public repository must remain SFW. Runtime source may contain arbitrary user content, but committed code/tests/docs should not embed graphic or sexual examples.
- Production commits:
  - `1abd9928aacd5db27a84e7cbe7877050d0cb090e`: added exact prior final-frame context to terminal-state extraction.
  - `5af1232d03b38e606cff919d1415c9a09ace05a5`: replaced explicit trigger/example language with generic irreversible terminal-state logic.
  - `69c312d1d51e972ae27bfff7c43c9a19a766d404`: replaced explicit regressions with SFW machine-state examples.
- Expected behavior: if a later segment tries to reapply an irreversible terminal result to the same continuing target without an explicit reversal/restoration, Request 1 should reject and regenerate it.


### 2026-09-28 — public-repo SFW cleanup and generic terminal-state micro-extractor

- Public repository rule is now explicit in `docs/PROJECT_NOTES.md`: committed code/tests/fixtures/comments/docs stay SFW; arbitrary runtime source content is handled only at runtime.
- Removed domain-specific graphic examples from active prompt contracts, regression fixtures, current handoff, and archived handoff.
- Terminal-target validation now follows the preferred deterministic + tiny-extractor pattern:
  - LLM sees ASSIGNED SOURCE + authoritative opening state + RAW;
  - it maps the observed pre-action target condition to exactly one Python-owned enum: `ACTIVE_OR_UNRESOLVED | ALREADY_TERMINAL | UNSPECIFIED`;
  - no domain-specific examples are embedded in the repository;
  - Python alone decides whether `ALREADY_TERMINAL` invalidates the candidate.
- Commits:
  - `83dbf8d3bb7ebcb1ab25ca4c1ad1c88cbf01d8b1`, `9cb4dd18fc88149216c34cb2ed47583b82342528`: remove graphic prompt examples.
  - `e2a523c0ec6ea300bce13c9b33f2bfcfd5a882bf`: SFW regression fixture.
  - `49a3f2ea5362b6e75d6917d8559b6872f199edfe`, `98ed6f55bc5cb0833a8844936f099f601991600d`: sanitize current + archived handoff history.
  - `e573dac1b2c7b8d9abd8f3f2c57b28f2506ca100`: architectural SFW rule in PROJECT_NOTES.
  - `397455495a14ba6c42f48703677c5cfca2e27fb0`, `6b312f8b4ed1c109f47016a15ffd60431f31e850`: abstract terminal-state micro-extractor regression + implementation.
- Repo scan of `minimax.py`, requested regressions, HANDOFF, HANDOFF_OLD, and PROJECT_NOTES found zero remaining graphic-keyword hits from the cleaned categories.


### 2026-09-28 — terminal duplicate check now compares Python-owned typed end state

- Acceptance `2334` proved the prior generic terminal-target extractor was only partially effective: it rejected one repeated terminal target attempt, then accepted a retry that reapplied the same completed result.
- A 50-case SFW probe matrix of the old extractor showed the responsibility was still too broad. The 20B model had to infer both the terminal outcome and the pre-action target state from prose, producing wrong active/terminal classifications, malformed keys, and token exhaustion.
- A replacement comparator was tested on 50 SFW cases:
  - Python supplies `TARGET` and `REQUIRED END STATE`;
  - the LLM returns only `MATCH | NOT_MATCH | UNKNOWN`;
  - production only rejects on `MATCH`.
- On all parsed probes, the production-critical binary decision was clean: every truly already-complete state returned `MATCH`, while every case that should permit the action returned non-`MATCH`. One 256-token probe truncated; production keeps the larger normal completion budget.
- Production commit `2011a79c9c09d6bc0cd64b1ccd9cd2e36e9a4027`:
  - derives comparator contracts from Python-owned typed state effects;
  - limits the duplicate-result gate to `set_barrier_state`, `set_threat_state`, and `set_object_state`;
  - removes source-prose inference from the comparator;
  - rejects Request 1 only when the observed pre-action state already matches the exact assigned typed end state.
- Regression commit `40d366c424e91e420d3cca0fd668a0ffecb0da86` covers typed contract selection, prompt shape, and strict parser behavior.
- Next checkpoint: requested regression suite, then fresh full acceptance. The Segment-7-style repeated completed target must regenerate until the assigned typed terminal state is not already true before the action.


### 2026-09-28 — preserve temporary barrier transitions

- Acceptance `2436` passed the terminal-target regression and produced a source-faithful 8-segment run, but exposed a new upstream state-contract defect at the final release beat.
- ARC correctly emitted `set_containment=free` for the children and did **not** invent an unstated persistent door state.
- The beat/Director nevertheless made the temporary unlock permanent even though canonical opening state still had the basement door locked and no `set_barrier_state` effect changed that final state.
- This is now handled as a Python-owned preservation invariant:
  - a containment/release effect may authorize temporary crossing of a closed barrier;
  - if no typed barrier-state effect changes that barrier, its opening canonical state must be restored by beat/segment end.
- Commit `c8544d0b96c35a7f2cee4bccd63312201b75589b` adds Director final-barrier preservation contracts and reuses the existing tiny barrier-state extractor to verify the final visible state.
- Commit `500aff99521644f6712437d8d29ea475dd67cdc0` feeds the same final-barrier constraint into BEAT CREATE and BEAT VALIDATE so bad plans are prevented upstream when possible.
- Commit `d07bb2e23a481ab49234206e81d79e9110c14662` adds regressions for a contained subject being released through a locked generic barrier and for explicit barrier effects overriding preservation.
- Next checkpoint: requested regression suite, then full acceptance. Final release may temporarily unlock/open the basement boundary, but without an explicit barrier effect it must end locked again.


### 2026-09-28 — containment transition clears stale spatial relationships

- Acceptance `2438` confirmed the temporary barrier-transition fix works: the final release beat unlocks/opens the basement door, lets Will and Amber out, then closes and relocks it.
- The accompanying regression run `2437` had two test-only failures caused by a missing `import json`; product code was not implicated. Commit `bb6742efd396eba75eed4051832600e6147e7452` fixes the test import.
- Earliest new acceptance defect was actually Segment 2 continuity: after Will and Amber were authoritatively moved/contained in the basement, prompt-derived spatial relationships such as `in Amy's arms` survived even though Amy remained in the kitchen. That stale relation propagated through later segments and eventually mutated into `inside Amy's arms in the basement`.
- Root cause: `_continuity_apply_authoritative_state_effects()` cleared transient pose/topology/spatial relationships only when prompt-derived `position` differed from the canonical container. If the extractor already wrote `position=basement`, contradictory spatial relationships could survive.
- Commit `c50508260e05834ad848442f011e73e17837dddd` makes every canonical `set_containment` transition invalidate prompt-derived pose/topology/spatial relationships, then re-adds only the canonical `inside <container>` relationship for contained subjects.
- Commit `51e5f0f669deb01b9469d7693bf7394f80baf80b` adds a regression for the exact stale-cross-location relation case.
- Next checkpoint: requested regression suite and full acceptance. Segment 2 continuity should now show Will/Amber simply inside the basement, with no stale physical relationship to Amy outside.


### 2026-09-28 — split LLM prompt generation from ComfyUI rendering

User-requested unattended two-phase workflow:

- `--generate-prompts N`
  - generates the story arc, N beats, Director RAW scenes, continuity, and final validated H3 prompts;
  - sends nothing to ComfyUI;
  - writes `generated_prompts.txt` incrementally after each finalized H3 prompt;
  - file is human-readable JSON despite the `.txt` extension;
  - stores render metadata with every prompt so the later render phase does not need the LLM;
  - standalone invocation defaults to 8-second segments and 0.5 MP; normal video positionals may be supplied to override those defaults as long as COUNT matches the resulting segment count;
  - recovery reuses the already-written prompt prefix and existing beat plan rather than regenerating semantic work.
- `--generate-from-prompts`
  - loads `generated_prompts.txt`;
  - skips story/ARC/BEAT/Director/continuity LLM generation entirely;
  - sequentially sends the saved final H3 prompts to ComfyUI and stitches the resulting clips;
  - uses the same existing `render_segment_with_retries()` workflow scheduling, including initial vs append vs chapter/numeric refresh selection;
  - validates that the saved conditioning mode matches the workflow schedule before rendering.
- Prompt file currently stores per-segment duration, final H3 prompt, conditioning mode, subject definitions, opening continuity state/summary, and LoRAs plus run-level segment length, total length, megapixels, steps, trim frames, refresh interval, and macro arc.
- Commits:
  - `0e9399dd32d3858c63fa8190bbe23adb871dd0fc`: CLI arguments/defaults.
  - `f452ebd0e9eb14364a0ca0366fb89d22aa6fc0d6`: saved prompt format + render-only executor.
  - `355c2f71568586ba44c9f7c17faa910530cc8f88`: main execution wiring.
  - `c928a912e2a28ecb4fd5d928a88ab3bd5ce0caec`: recovery-safe prompt prefix reuse.
  - `5c66c8efb27223ddd679a323df8ae36faa738315`: regressions for CLI defaults, file round-trip, and saved workflow schedule.


### 2026-09-28 — acceptance 2440: containment fix held; malformed timestamp wrapper exposed

- Acceptance `2440` confirmed the containment-overlay correction:
  - Will and Amber remain simply located in the basement after Segment 2;
  - stale cross-location relationships such as `in Amy's arms` no longer propagate.
- The barrier restoration behavior also held in Segment 8: the basement door is temporarily opened for release, then ends locked again.
- The next earliest deterministic H3 defect appeared in Segment 6: Request 2 returned timestamp wrappers such as `[At 00:00.000, ]` and `[07.999]`.
- Existing timestamp correspondence validation incorrectly accepted the nested form because its canonical regex found the inner `At 00:00.000,` token and ignored the surrounding brackets.
- Commit `5d4f5c37e1f54b925c568db6e919e69113ca0233` explicitly rejects bracketed/nested timestamp wrappers during Request-2 timestamp validation, forcing a formatter retry before final H3 assembly.
- Commit `70846f73e9b904544861bb66ed121de7e325c834` adds a SFW regression for the nested timestamp case.
- `tests-2441` showed all new split-generation regressions passing; its sole failure was an older preserved-barrier fixture passing raw JSON instead of the production SOURCE-AUTHORIZED wrapper. Commit `72796c243afaf6a300e82d766fbc87ef6204c93a` corrects that fixture.


### 2026-09-28 — GPT-20B context budget corrected to 8192

- LM Studio was configured for an 8192-token context, but production code still hard-capped the local LLM context at 6044 tokens.
- `call_llm()` computed `effective_max_tokens = min(max_tokens, context_budget - safety - estimated_input)`, so ordinary creative prompts could be sent with much smaller completion caps such as `2634`.
- Commit `819d613b51d0baee773f2246e2c0cf946f068056` changes `LLM_CONTEXT_TOKEN_BUDGET` from 6044 to 8192 and the default `call_llm(... max_tokens=...)` ceiling from 8000 to 8192.
- The 128-token safety reserve and input-size subtraction remain. This prevents impossible requests while allowing the GPT-20B runtime to use its full configured context instead of an obsolete ~6k software cap.


### 2026-09-28 — Segment-level Director retry exhaustion now escalates to planning

- User run became stuck indefinitely on Segment 4. The log repeatedly showed `Director Request 1 closed-boundary traversal check failed`, then after 3 local attempts the application supervisor resumed from Segment 4 and reused the same planning checkpoint.
- One retry also showed the deeper contract mismatch: RAW created a durable terminal zombie-state change while the assigned typed end state was empty. This demonstrates the current Beat/typed-state checkpoint itself can be incompatible with Director validation, so replaying the same segment cannot necessarily heal it.
- Commit `fe4254683e3ce1507ebf2117505bd425e490800e` changes recovery narrowly: when Director Request 1 exhausts its local 3-attempt completion budget, recovery escalates to planning at Segment 1 instead of reusing the same later-segment checkpoint forever.
- In `--generate-prompts` mode, Segment-1 recovery forces a fresh beat plan, allowing a poisoned Beat/typed-state contract to be regenerated while preserving the application's recover-forever policy.


# Archived current HANDOFF chronology — through 2026-10-01

This material was moved out of HANDOFF.md on 2026-10-01 to keep the active handoff concise.

## 2026-09-28 — acceptance 2445 + GPT formatter timestamp wrappers

- `tests-2444` passed 51/51 (1 skipped) across prompt-generation mode, requested prompt regressions, and minimax integration coverage.
- `acceptance-2445` completed all 8 segments with canonical timestamp syntax throughout, so the parenthesized timestamp failure from `acceptance-2443` did not reproduce on the next stochastic run.
- Nevertheless, `acceptance-2443` demonstrated a real GPT-OSS formatter quirk: Request 2 could emit wrappers such as `(At 00:01.500, )` around otherwise valid timestamps, and the shared timestamp checker could see the valid inner token.
- Architectural rule: model-specific representation cleanup belongs in the model formatter. Shared orchestration should enforce the final H3 contract, not accumulate GPT-specific punctuation repair.
- Commit `b9b5297509bc25f5cc2f30846e65eddcaef58e4a` adds GPT-only deterministic unwrapping for parenthesized or bracketed local timestamps before canonical normalization.
- Commit `b6b0ee96a254460277bb6fb11d470369bf3f9c1c` adds formatter regression coverage for both wrapper forms.
- `acceptance-2445` also showed one `Added States:` string visually interleaved inside the printed Segment-6 H3 block. This has not yet been proven to be part of the actual prompt object rather than concurrent console-output/capture interleaving, so do not patch it until a direct prompt-object or repeated acceptance result proves the defect.
- Next checkpoint: run formatter/regression tests, then fresh full acceptance. Confirm wrapped timestamps are normalized by `gpt_formatter.py`; if `Added States:` appears again, trace its origin before changing production behavior.


## 2026-09-28 — acceptance 2451 formatter follow-up

- `tests-2450` imported successfully after the prior regex syntax fix and ran 54 tests, but the new timestamp-wrapper regression failed because the Python raw regex accidentally contained literal double backslashes, so it did not match real `(At ... )` / `[At ... ]` text.
- `acceptance-2451` completed all 8 segments. Its final prompts used canonical timestamps, but Segment 4's captured `generated_h3_prompt` ended with a literal `Added States:` line. This proves the earlier 2445 observation was not merely console interleaving.
- Both defects are GPT-OSS representation quirks and belong in `gpt_formatter.py`, not shared orchestration.
- Commit `052e11f8e7af37437e95c81ea82f81445af56dbb` fixes the wrapper regex and strips a trailing `Added States:` control label from GPT-rendered fields.
- Commit `7472eec0faf95350560c5acae6f365c65b5e7758` adds regression coverage for the control-label cleanup.
- 2451 also exhausted Director Request-1 retries once at Segment 4 and correctly escalated to replanning, after which the full run completed. Treat that as recovered model variance unless fresh acceptances show a consistent pattern.


## 2026-09-28 — Director-only test path and retry recovery

- Repeated late-segment Request-1 failures were wasting full ARC/BEATS regeneration time because exhausted Director retries triggered the recovery supervisor's plan invalidation path.
- `DIRECTOR_RAW_SCENE_ATTEMPTS` is now 5 (was 3).
- New `--director-only` mode:
  - requires existing valid `story_arc.json` and `beats.txt`;
  - never calls ARC/BEATS generation or repair;
  - implies prompt-generation test mode, so ComfyUI is never called;
  - runs the normal per-segment Director Request 1 -> Request 2 -> formatter/final-H3 validation path;
  - on exhausted Director retries, recovery resumes from the last committed segment and does not invalidate/rebuild the frozen plan.
- Acceptance runner now accepts `--director-plan-dir PATH`, copying a frozen `story_arc.json` + `beats.txt` into its isolated workspace before invoking `minimax.py --director-only`.
- Bridge `run_acceptance` jobs may set `director_plan_job` to a prior acceptance job ID. The bridge reuses saved plan files when available; for older jobs such as `acceptance-2451`, it can materialize the embedded `generated_story_arc` and `generated_beats_text` from `acceptance_run.json` into a local temporary directory. The actual runtime story/plan is not added to the public code branch.
- Full acceptance artifacts now preserve `story_arc.json` and `beats.txt` for later Director-only runs.
- Mailbox queue was purged before this change; no unprocessed bridge jobs remain.
- Relevant commits: `bed344efb92d54ef35b8ffacc77be2519f098a6d`, `f77774decddde57c313ce33b9fb55e0314e65174`, `c8eccde5fbc8a5a1d836cfcbf2b2965e90d895dd`, `c62550df1dfb3cb297e7355f007592bbe5bba074`, `b15bca3e89de32db38c1535ff14150a53bdeeea2`, `d264644d405a8d913b0eab7bdc0978df964a52d7`.
- Next action: pull `gpt-arc-refresh`, restart the bridge, then run targeted tests and a Director-only acceptance using `director_plan_job: "acceptance-2451"` before doing another full ARC/BEATS acceptance.


## 2026-09-28 — Director-only acceptance 2457 findings

- `tests-2456` passed: 54/54 targeted regression tests.
- `acceptance-2457` completed, but exposed a flaw in the frozen-plan harness: `story_arc.json` was copied without a matching `.sha256` sidecar, so normal `load_story_arc()` rejected it as a stale cache. The run therefore did not exercise frozen typed state effects even though `beats.txt` was reused.
- Director-only mode now parses the explicitly supplied frozen `story_arc.json` directly and validates its declared beat count/schema without using the normal story-source cache hash gate. It still fails closed if the supplied frozen arc is invalid.
- Prompt-only checkpoints now persist the exact assembled `h3_prompt` per completed segment. The acceptance runner prefers that exact field over parsing console text, avoiding false prompt contamination from concurrent/asynchronous stdout such as `Added States:`.
- The GPT formatter's trailing `Added States:` cleanup regex also had accidental literal backslashes and is now corrected.
- Stale `tests/test_director_retry.py` helpers were updated to the current five-field Request-1 completion response and current containment prompt wording.
- Relevant commits: `8c494f0e4760f686ffbe468e32408346f1e0d13d`, `3a6d83ba5245ea2a227609bd8582963859244116`, `9f16c086213e0f179d2e718c34b9f4b154739ba2`, `a4d035f09e007c4bdc63d3e5e78f0b46e0d0088c`.


## 2026-09-28 — Director-only acceptance 2459

- `acceptance-2459` is the first clean frozen-plan Director-only acceptance using the saved arc's typed state effects.
- Segment 2 containment now behaves correctly: Will/Amber end inside the basement while Amy remains outside in the kitchen.
- Exact checkpointed H3 prompts contain no `Added States:` contamination; prior appearances inside acceptance reports were caused by stdout scraping/interleaving.
- Earliest remaining real prompt defect: Segment 5 authorizes only a non-terminal arm sever + limb disposal, but Request 1 added `zombie remains motionless on floor`, inventing a terminal/incapacitated outcome not assigned by source.
- Rather than add another semantic pipeline/call, the existing independent Request-1 completion validator now explicitly rejects stronger terminal outcomes when SOURCE authorizes only non-terminal injury/damage/change.
- `tests/test_director_retry.py` fixtures were also updated to emit structurally valid timed RAW SCENEs with a trailing `End continuity state:`, matching the current production Request-1 contract instead of failing for obsolete fixture shape.
- Relevant commits: `fcf95ee5116ae698735f0c214b9d8cdf14565a21`, `f7f0ad4a8dd5bbd1e17cc955d7d0e6cbe534a653`.

## 2026-09-28 — acceptance 2461 + regression cleanup

- `tests-2460` exposed 13 failures (79 passed). Most Director failures were not independent production defects: legacy unit-test bundles supplied derived beat text but no authoritative `assigned_source`, while the newer independent completion verifier still made an extra semantic LLM call. That exhausted mocked response queues and obscured the formatter failures.
- Commit `2e08b3acb708cf0af85a94ab4a32f1978b7e3bf4` fixes the GPT-only wrapped-local-timestamp regex. The previous raw regex still contained literal double escapes and failed to unwrap `(At ... )` / `[At ... ]` reliably.
- Commit `2545ab269bd4df67aa928b95e1dd029a44660542` makes the independent Request-1 semantic completion verifier explicitly source-authority based: it runs only when both CURRENT BEAT and authoritative `assigned_source` are present. Legacy/unit callers without source retain structural + self-reported completion checks; production Director bundles continue through the independent verifier.
- `acceptance-2461` completed all 8 frozen-plan Director segments. The Segment-5 unassigned terminal outcome from 2459 did not recur, confirming the terminal-scope prompt fix moved the failure downstream.
- Do not treat later prompt-quality observations from 2461 as the next production target until the targeted regression suite is green again.
- Next checkpoint: run the same targeted Director/formatter/prompt-generation tests. If green, run another Director-only acceptance against the frozen `acceptance-2451` plan and identify the earliest remaining real prompt defect.

## 2026-09-28 — targeted baseline green; Segment 2 crossing ambiguity

- `tests-2469` is green: 90/90 targeted tests passed (8 subtests passed).
- Re-review of `acceptance-2465` found the earliest remaining production prompt defect in Segment 2. RAW used `They descend the kitchen stairs` after Amy grabbed Will and Amber, which can visually include Amy crossing into the basement even though the authoritative typed end state moves only Will and Amber there and leaves Amy outside to lock the door.
- The independent completion verifier received the correct typed end state and participant-scope rule, but GPT-OSS 20B rationalized `They` as only Will and Amber and returned valid.
- Commit `0f33cd7c7d02ffc2dd305adb618056b2dd1f3ef7` tightens only the existing participant-scope rule: collective crossing language such as `they`, `we`, `all`, or `the group` is invalid when it could include an unauthorized mover/helper; RAW must explicitly name authorized crossers.
- Commit `1c8344e36f727a668a4660a891926ed5eb4debad` adds a regression assertion for that prompt rule.
- Next checkpoint: rerun the targeted tests, then rerun Director-only acceptance against the frozen `acceptance-2451` plan. The expected Segment-2 repair is explicit wording such as `Will and Amber descend/enter the basement` while Amy remains outside.

## 2026-09-28 — Director structural-geography tightening

- The Segment-2 `They descend the kitchen stairs` wording in `acceptance-2465` was not present in the frozen beat plan; Request 1 invented `kitchen stairs` as local staging.
- Commit `e92e4d8d51910a3a25cdb828ec933853165957a1` tightens the existing RAW Director prompt: do not invent structural geography/travel routes (stairs, hallways, corridors, extra doors, ladders, elevators, rooms, floors, tunnels, gates, passages). If a route is unspecified, move named subjects directly toward/through the established destination boundary without defining how the building connects.
- The same commit tightens the existing Request-1 completion verifier to reject invented route-defining structures. This stays within the existing Director generate/verify retry loop; no new semantic stage was added.
- Commit `c1c07ca7ee8338737de13e8e024c476551ad99a0` adds regression coverage for both prompt constraints.

## 2026-09-28 — deterministic Director route/crossing guards

- `acceptance-2473` proved the 20B model can ignore explicit semantic rules: it generated `Amy, Will, and Amber rush down the kitchen stairs into the basement`, then the independent verifier incorrectly rationalized that only Will and Amber crossed.
- Root cause included a contradictory Python-added final-side note allowing temporary unauthorized crossing if the subject returned before the end. That loophole was removed.
- Commit `67b07da70d7ac6e89ac076ab8892212703b15b6d` adds deterministic Request-1 guards inside the existing acceptance gate:
  - reject route-defining structures that appear in RAW but are absent from source/beat/opening continuity;
  - reject an explicitly named subject with NOT_AT_DESTINATION topology when RAW states that subject moves into/through/to the typed destination.
- These are deterministic lexical/state checks, not a new semantic pipeline. The existing local-LLM completion verifier remains for broader source completion.
- Commit `ab8418996d8b887bc4f56b9a814a272f4d613d3a` adds focused regression tests and fixes the geography test to use `DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE`.

## 2026-09-28 — Segment 2 cleared; Segment 4 opening-held prop contradiction

- `tests-2476` is green: 94/94 targeted tests passed.
- `acceptance-2477` finally clears Segment 2: no invented route geometry; Amy steps back, Will/Amber enter the basement, Amy remains on the kitchen side, and the basement door ends locked.
- Segment 3 is acceptable.
- Earliest remaining production defect is Segment 4: RAW begins with Amy already holding pistol + katana, then later says she `pulls pistol from holster`, inventing a holster and reacquiring an item already held in canonical opening continuity.
- Commit `57e4e078d88171f22e4f90fdbf2468f26bf478a5` extends the existing deterministic object-state gate to compare RAW against structured `registry_state.held_props`; an opening-held item cannot be reacquired unless RAW explicitly releases/stows it first.
- Commit `7a7a4414158efcf1727279cfec4352b4d8a5bdfe` adds regression coverage for reject/allow cases.

## 2026-09-29 — Segment 4 infinite restart root cause fixed

- User supplied a live run showing Segment 4 repeatedly restarting with `global flags not at the start of the expression at position 38`; this was a Python regex exception, not an LLM stall.
- `tests-2478` reproduced the same exception in `test_opening_held_prop_cannot_be_reacquired_without_release`.
- Pending `acceptance-2479` was removed from the runtime queue; no new acceptance is queued until the regression suite is green.
- Root cause: `_director_opening_held_reacquire_errors` embedded `_DIRECTOR_HELD_REACQUIRE_RE.pattern`, which contained an inline `(?i)` flag, inside a larger regex that already had preceding tokens. Python rejects nested global flags away from pattern start.
- Commits `9aa323f46297def8bacfb8c98bda41b460da7b1a` and `603b0e9d78c3c08316f2e3c1b679cde59b381661` split the reusable reacquire fragment into a flag-free string pattern and compile the standalone regex with `re.IGNORECASE`.
- Commit `559cc68e686272eb6b3931cb6c3ebb43321490c3` makes `re.error` non-recoverable in the outer generation loop. Regex/programming defects now fail fast instead of restarting the same checkpoint forever.


## 2026-09-29 — Request-1 KISS + preserved-state semantics

- Preserved canonical state now follows the core state rule: if a barrier state is already established in the opening state and no typed effect changes it, a RAW-scene extractor result of `UNSPECIFIED` means "not restated" and does **not** override the canonical state. Explicitly assigned barrier transitions still require an observed matching result; `UNSPECIFIED` remains invalid for those.
- Director Request 1 was reduced to a compact creative-director contract: ASSIGNED SOURCE -> CURRENT BEAT -> OPENING STATE -> Python-owned FINAL STATE CONTRACT -> NEXT BEAT boundary.
- Python now appends one concise `AUTHORITATIVE FINAL STATE CONTRACT` covering final-side topology, barrier end states, barrier binding, and closed-boundary traversal constraints rather than several verbose prose blocks.
- No Director 1B/state-repair stage was added. First evaluate the simpler creative call plus corrected deterministic state semantics.


## 2026-09-29 — Held-prop use vs reacquisition

- acceptance-2484 completed all 8 Director-only segments; preserved BROKEN/LOCKED barriers no longer fail when RAW omits them.
- acceptance-2485 exposed the next earliest deterministic false positive: _director_opening_held_reacquire_errors treated phrases such as "pulls the trigger on her pistol" as reacquiring an already-held pistol because the regex allowed the prop to appear far after the reacquire verb.
- The guard now requires the canonical held prop to be the direct object of pull/draw/retrieve/take/grab/pick-up. Ordinary use such as pulling a trigger, shooting with, or raising an already-held pistol is allowed.
- Keep the KISS Request-1 prompt unchanged while measuring this deterministic fix.


## 2026-09-29 — Crossing-route contract tightened

- acceptance-2487 confirmed Segment 4 no longer exhausts retries after the held-prop fix; it cleared on attempt 2.
- The earliest recurring failure moved to Segment 2: GPT-OSS 20B repeatedly invented basement stairs/hallways even though the compact Director prompt forbids unestablished route geometry.
- Keep Request 1 compact. When Python has both a destination topology contract and a bound destination barrier, append one explicit route line: move authorized subjects directly through that destination boundary and do not invent stairs, hallways, corridors, or intermediate route geometry.


## 2026-09-29 — Held-prop sourced-lift reacquisition

- acceptance-2490 confirmed the explicit crossing-route contract: Segment 2 passed on its first Request-1 attempt with no invented stairs/hallways.
- The next continuity hole appeared in Segment 4: RAW reacquired an already-held pistol via "lifts the pistol from a nearby table". The direct-object guard correctly ignored ordinary weapon use but did not yet treat lift/raise-from-source phrasing as acquisition.
- Opening-held reacquisition now also rejects lift/raise of the held prop when followed by from/off/out of a source. Ordinary lift/raise-to-aim/use remains valid.

- `tests-2491` passed 102/102 targeted tests (plus 6 subtests), including the new sourced-lift regression.
- `acceptance-2492` is queued as the next frozen-plan Director-only acceptance using `director_plan_job: "acceptance-2451"`.
- Relevant production fix: `27922a035998c14f6d4826707ad61091f59ab5c6`.


## 2026-09-29 — acceptance 2492 concrete-action fidelity

- `acceptance-2492` completed all 8 frozen-plan Director segments and confirmed the opening-held sourced-lift fix: Segment 4 no longer reacquired the pistol from an invented surface.
- The earliest remaining real production defect moved earlier to Segment 2. Assigned source/beat requires Amy to grab Will and Amber and rush them to the basement, but RAW substituted `Amy lifts Will and Amber` / carries them. This is a material physical-action substitution, not harmless staging.
- The existing Request-1 completion verifier required source actions to occur but did not explicitly forbid replacing one concrete source action/participant interaction with a materially different physical action.
- Commit `fd436b0791c59b01eed69fec95d710d63869a1b8` adds one compact source-fidelity sentence to Request 1 and its existing independent completion verifier. No new LLM call or semantic stage was added.
- `tests-2493` is queued. If green, rerun the frozen-plan Director-only acceptance against `acceptance-2451`. Do not address the later Segment-7 kitchen/living-room teleport until this earlier Segment-2 defect is cleared.


## 2026-09-29 — acceptance 2494 barrier identity

- `acceptance-2494` confirmed the Segment 2 concrete-action substitution fix: Amy now grabs Will and Amber rather than lifting/carrying them.
- The next earliest defect is still Segment 2: RAW conflated the broken kitchen entry door with the basement boundary. It explicitly pushed the children toward/through the broken door, then `slams the kitchen door shut` and locks it even though Python's generic `door` effect is bound to the basement destination.
- The semantic completion verifier had the correct AUTHORITATIVE BARRIER BINDING but accepted the wrong explicitly qualified barrier. This responsibility is deterministic: when Python binds a generic barrier to one destination, an explicit state-changing action on a differently qualified same-type barrier is invalid.
- Commit `abd8db92c351f8b77bbe3bdab15c0a36f6df1076` adds a narrow Python guard for this case. Generic `the door` and the destination-qualified barrier remain valid; actions on a nested window such as `kitchen door window` are not misclassified as door-state changes.
- `tests-2495` is queued. If green, rerun the frozen-plan Director-only acceptance against `acceptance-2451`.


## 2026-09-29 — acceptance 2497 prompt-continuity location drift

- `tests-2496` passed 106/106 targeted tests plus 6 subtests.
- `acceptance-2497` cleared the earlier Segment 2 concrete-action and wrong-bound-barrier defects. Segment 2 RAW now grabs Will and Amber, moves them through the basement door, then closes/locks the basement door.
- The next earliest defect is prompt-derived continuity immediately after Segment 2: the continuity extractor invented `Amy.position = "outside kitchen doorway"` even though RAW never moves Amy outside and no source-owned location/containment effect authorizes that persistent spatial change. That invented position then contaminates Segments 3-6.
- Commit `360990a7248fc7122306d08353a80a7bbf47cfa6` adds a narrow deterministic merge guard: a newly external/`outside` subject position cannot replace a known committed placement unless that subject has a source-owned `set_location` or `set_containment` effect. Ordinary internal room refinement remains allowed.
- `tests-2498` and frozen-plan Director-only `acceptance-2499` are queued together to reduce bridge round-trips.


## 2026-09-29 — acceptance 2499 wrong-bound crossing route

- `tests-2498` passed 109/109 targeted tests plus 6 subtests.
- `acceptance-2499` confirmed the prompt-continuity outside-location corruption is cleared; Amy no longer gets pushed outside the house after Segment 2.
- Earliest remaining defect is still Segment 2: RAW says `They sprint through the broken kitchen doorway directly into the basement`. This incorrectly uses the kitchen entry boundary as the basement crossing route even though the scene separately has a basement door.
- Existing deterministic bound-barrier guard covered wrong qualified barrier state changes, but not wrong qualified barriers used as the crossing route into the bound destination.
- Commit `0a735335cdefb2a65d2b7bb844413912b9d952ea` extends the same narrow Python guard to reject `through/via/across <wrong qualified door/doorway> ... into <destination>` when Python binds the generic barrier to that destination.
- `tests-2500` and frozen-plan Director-only `acceptance-2501` are queued together.


## 2026-09-29 — acceptance 2501 pull-out reacquisition

- `tests-2500` passed 110/110 targeted tests plus 6 subtests.
- `acceptance-2501` cleared the Segment 2 wrong-bound crossing-route defect.
- Earliest remaining defect moved to Segment 4: Segment 3 leaves Amy holding pistol + katana, but Segment 4 says `Amy pulls out her pistol` before firing. The held-prop deterministic guard already rejected direct reacquisition forms but missed the phrasal verb `pulls out <prop>`.
- Commit `940ed4ccd792ba97d67543ce3e9d15554796460e` extends the existing held-prop guard to cover `pull/pulls/pulled/pulling out <held prop>` without changing Director semantics or adding a new LLM stage.
- `tests-2502` and frozen-plan Director-only `acceptance-2503` are queued together.


## 2026-09-29 — acceptance 2503 unassigned external relocation

- `tests-2502` passed 111/111 targeted tests plus 6 subtests.
- `acceptance-2503` cleared the Segment 4 `pulls out her pistol` reacquisition defect.
- Segments 1-7 are now materially clean enough to advance. Earliest remaining defect is Segment 8: RAW moves Amy outside with Will and Amber and ends with all three on a sunny patio, but only Will and Amber have source-owned movement/containment effects for the escape.
- Existing topology validation only reasoned about the basement boundary, so Amy could remain correctly outside the basement while still being incorrectly relocated outside the house.
- Commit `af12046bca490d1707f5bd2383b11cdc2a647a0c` adds a narrow deterministic end-state guard: if a known subject explicitly ends outside/on a porch/patio/exterior and no source-owned set_location/set_containment effect authorizes that persistent relocation, reject Request 1. Already-external subjects and explicitly authorized moves remain valid.
- `tests-2504` and frozen-plan Director-only `acceptance-2505` are queued together.


## 2026-09-29 — acceptance 2505 preserved containment

- `tests-2504` passed 113/113 targeted tests plus 6 subtests.
- `acceptance-2505` cleared Amy's unauthorized outside relocation in Segment 8.
- Earliest remaining defect is Segment 7: Will and Amber are still canonically contained in the basement, but RAW stages them `through the broken kitchen door window` looking at the fight before their release beat. Prompt-derived continuity then incorrectly moves them out of the basement.
- Existing topology guards only activate around typed destination transitions; they did not protect unchanged containment on a beat with no containment effect.
- Commit `fa2769520c569be680fc880152fb39f00f37a41a` adds a deterministic preserved-containment guard: a subject canonically contained in a location cannot be visually staged elsewhere unless the current beat carries a source-owned set_location/set_containment effect for that subject. Explicitly keeping the subject in the container remains valid.
- `tests-2506` and frozen-plan Director-only `acceptance-2507` are queued together.


## 2026-09-29 — acceptance 2507 pronoun held-prop reacquisition

- `tests-2506` passed 116/116 targeted tests plus 6 subtests.
- `acceptance-2507` cleared the Segment 7 preserved-containment leak; Will and Amber now remain in the basement until their release beat.
- Earliest remaining defect is Segment 4: RAW begins with Amy already holding pistol + katana, then says `She pulls the pistol from her belt` before firing. This is another held-prop reacquisition.
- The held-prop guard was subject-name anchored, so the production pronoun form `She pulls...` bypassed it even though equivalent `Amy pulls...` regressions passed.
- Commit `1aa135386671a4c42764f570b07357ef034ae70d` broadened sourced pull phrasing; commit `9101c02d0fa451b89e327123ab1abd0564dce41f` fixes the actual production hole by allowing an unambiguous pronoun actor only when exactly one opening-state subject holds that prop.
- `tests-2508` and frozen-plan Director-only `acceptance-2509` are queued together.


## 2026-09-29 — tests 2508 pronoun regression correction

- `tests-2508` was red: 116 passed, 1 failed, 6 subtests passed. The failing production-shaped regression was `She pulls the pistol from her belt`.
- Root cause: pronoun matching required gender metadata, but the held-prop guard can receive minimal opening state containing only `held_props`. The production parser therefore still missed the exact pronoun form seen in acceptance 2507.
- Commit `1e5d545a5d797d190e10188323ab68c5667fe39a` makes pronoun resolution depend only on uniqueness of the opening-state prop holder: if exactly one Subject holds that prop, `she/he/they` is accepted as an unambiguous actor; if multiple Subjects hold the same prop, pronouns are not used for deterministic rejection.
- `acceptance-2509` is diagnostic only because the regression suite was red. It suggests the next issue may be Segment 8 failing to actually clear Will and Amber out of the house, but do not fix that until the held-prop regression is green.
- `tests-2510` and frozen-plan Director-only `acceptance-2511` are queued.

## 2026-09-29 — Director RAW timing must use the clip window

- A fresh Director RAW scene for an 8-second Segment 2 completed all timed action by 00:01.300. The existing contract only required the final timestamp to be before the segment endpoint, so this was structurally accepted.
- Fix: Request 1 now explicitly paces timed action across the full clip, and Python deterministically rejects RAW scenes whose final timed micro-beat occurs before the final quarter of the segment. For an 8-second clip, the last timed action must be at or after 6.0 seconds and still before 8.0 seconds.
- This remains inside the existing Director Request-1 structure gate; no new LLM stage or semantic pipeline was added.
- Added focused regressions for rejecting a 1.3-second ending in an 8-second clip and accepting a 6.2-second ending.
- Next checkpoint: run the focused Director regression suite, then a fresh Director-only acceptance using the frozen plan and verify Segment 2 uses the full 8-second timing window.

## 2026-09-29 — direct endpoint continuation and frozen-plan checks

- `gpt-arc-refresh` was pulled at `5a44e3e9`. The local GPT-OSS endpoint at `http://192.168.0.203:1234` is directly reachable, so no bridge program is needed for this session. The endpoint briefly timed out, then recovered.
- The new final-quarter timing gate exposed stale mocked Director fixtures. Their RAW and formatter examples now extend to 00:04.500 in the tests' six-second segment. The focused Director/formatter/prompt-generation suite is green: **136 passed, 8 subtests passed**. Production timing behavior is unchanged from `5a44e3e9`.
- The frozen `acceptance-2451` arc and beats were materialized from its saved `acceptance_run.json` on `gpt-runtime`. The direct runner uses `tests/acceptance/run_acceptance.py --director-plan-dir /tmp/amy-frozen-2451 --image1 Amy.jpg`. All acceptance outputs are in `/tmp`; none are committed. An initial diagnostic used the repository image because `Amy.jpg` was not present, but `Amy.jpg` later appeared in the workspace and is used for subsequent checks.
- A completed direct frozen-plan run is at `/tmp/amy-director-20260929-r4/acceptance_run.json` (8/8 segments, refresh at Segment 7). Every segment's last RAW timestamp was in the final quarter, so the timing rule passed live. This run exposed the earliest persistent-state defect at Segment 4: Amy began holding pistol + katana but ended with the katana on her belt. Prompt-derived continuity then carried that unauthorized belt state into Segment 5.
- Earlier diagnostic runs also exposed deterministic Segment-2 false positives and missed crossings. The external-location guard treated `Amy outside the basement` as outdoors; it now distinguishes an interior containment boundary from outside the house. The crossing guard now recognizes `while Amy follows behind`, exit-from-destination evidence, and `dash`; bound-door routing rejects a window route into the basement. These are all Python checks inside the existing Request-1 gate, with no new LLM calls or longer model prompts.
- A later direct run with `Amy.jpg` showed a Segment-2 RAW scene that moved the children only to the basement door, closed it, and claimed they were inside in the final-state sentence. The new deterministic containment-crossing check requires each newly contained subject to visibly cross in a timed action; final-state assertion or approach alone is insufficient. A fresh run then passed Segment 2 with `Amy pushes Will and Amber through the kitchen side of the basement door into the basement` before she shut and locked it.
- The held-prop gate now also rejects an opening-held prop ending on a belt/holster/sheath unless authoritative source explicitly assigns that stow. The focused regression uses the production Segment-4 katana case and an authorized-stow control.
- Direct frozen-plan run `/tmp/amy-director-20260929-r6`, using `Amy.jpg`, cleared Segment 2 with an explicit door crossing and Segment 4 with both weapons still held. It was stopped at the earliest new clear defect in Segment 5: RAW began with pistol and katana occupying both hands, then said Amy lifted a severed arm `with both hands` without releasing either weapon. The end state still claimed both were held. The existing Request-1 structure gate now rejects this exact occupied-hands contradiction unless one opening-held prop is visibly released first. No LLM prompt or call was added. Evidence is preserved under `/tmp/amy-director-seg5-evidence-r6/`.
- Next checkpoint: rerun the frozen-plan Director acceptance with `Amy.jpg` and review the earliest new real defect. Keep GPT-OSS 20B jobs narrow and use Python for typed-state and crossing invariants. Commit and push this handoff with the code changes to `gpt-arc-refresh`; do not add the untracked runtime `Amy.jpg`.

## 2026-09-29 — Director Request 1 wording simplified for local gpt-oss 20B

- Target runtime model remains `GPT-OSS-20B.gguf`.
- The exact model card adds no special prompt syntax beyond being a gpt-oss 20B derivative. Keep using the runtime's gpt-oss/Harmony chat template.
- Director Request 1 now uses short, literal, ordered rules: SOURCE -> CURRENT BEAT -> OPENING STATE -> END STATE RULES -> NEXT BEAT.
- Removed abstract wording such as "authoritative final state contract", "persistent changes", and the blanket ban on invented structural geography from the creative call.
- Harmless route details (for example, a short hall or stairs) are now allowed. The real invariants remain enforced: required destination, correct bound door/gate, which people cross, and required end state.
- Removed the deterministic unestablished-route rejection and the matching completion-verifier rule so harmless route detail is not accepted by the prompt and then rejected later.
- Timing is now stated with a concrete number for each clip: the last timed action must be at or after 75% of the clip length and before the exact endpoint.

## 2026-09-29 — ARC CREATE + BEAT CREATE simplified for Qwen/local 20–27B

- Read the complete current \`docs/PROJECT_NOTES.md\` before changing prompts. Architecture remains unchanged: \`story.txt\` is narrative authority; Python owns arithmetic/bookkeeping/state application; local LLM calls should be short, concrete, and low-ambiguity.
- Runtime evaluation is moving to an uncensored Qwen3.8-27B variant. Qwen's official guidance emphasizes correct chat-template role separation, and its function-calling guidance notes that simpler templates that rely less on the model staying on track are more reliable.
- ARC CREATE was rewritten without changing its output schema or ARC validation/repair loop:
  - system message now states only the stable job;
  - user message has short SOURCE / SUBJECTS / BEAT COUNT / repeated-process sections;
  - majority arithmetic is precomputed by Python and stated as concrete beat numbers rather than a prose allocation algorithm;
  - state-effect argument ownership is now a short operation lookup list;
  - JSON schema continues to enforce output shape/count.
- BEAT CREATE was rewritten with the same style:
  - ASSIGNED EVENT is stated as the beat authority and chapter source as context;
  - barrier binding, closed-boundary, and final-state text is concrete rather than "canonical/authoritative physical constraints" prose;
  - beneficiary rules explicitly distinguish food/consumable/hand-off receipt from repair/build/custom work that need not be delivered unless source says so;
  - repeated-process and previous-beat rules remain, but use short direct wording.
- No validator, repair prompt, semantic stage, state operation, or deterministic guard was removed.
- Next checkpoint: run the focused ARC/Beat prompt regression suite, then compare fresh Qwen planning/beat-generation behavior before simplifying validators or repair prompts.

## 2026-09-29 — Qwen acceptance bridge support + stale regression fixtures

- `tests-2516-qwen-planning` completed: 112 passed, 12 failed, 6 subtests passed. The failures were regression-fixture drift, not live-Qwen behavior:
  - `tests/test_beat_at_a_time_validator.py` mocks expected only the primary beat-validator call and did not supply the newer finite-endpoint and coherence responses, causing response-list exhaustion / schema failures.
  - two prompt regressions asserted superseded exact wording after the prompt simplification.
- The validator fixtures now return `COMPLETE` / `NOT_APPLICABLE` for finite-endpoint checks as appropriate and VALID for coherence, while preserving the original primary-validator assertions. Prompt assertions now target the current semantic wording.
- `acceptance-2517-qwen-full` did not run MiniMax at all. The bridge rejected the job before process launch with: `Acceptance jobs must use the 'gpt' baseline; got 'qwen'.`
- Bridge acceptance now permits all formatter models already supported by runtime: `gpt`, `mistral`, and `qwen`. Unsupported model names still fail closed. Added regression coverage that Qwen reaches the acceptance command as `--model qwen`.
- Relevant commits: `f25b3ec522fec2226eaded7a95374af9fdfc2da9`, `7589afc0cc015324216cc8c1b913f6b17bdd7109`, `35bb5276053276ab2c584e985f066eca60ff4c80`, `032a2c5a65e68f1dea156fce86ee266fa7d39ce3`.
- Next checkpoint: rerun the corrected regression suite. Then restart the bridge from the updated branch before queueing/running the full Qwen acceptance; a bridge process started before `35bb5276` still has the old in-memory GPT-only gate.

## 2026-09-29 — Beat retry now performs an actual repair

- Qwen at temperature 0 exposed a retry-contract bug: after a finite-endpoint rejection, the retry path regenerated Beat 1 from essentially the same one-beat creation prompt. Deterministic decoding therefore returned the same incomplete beat repeatedly.
- Keep temperature 0. The problem is prompt state, not sampling.
- The existing retry call now receives the rejected candidate text in addition to the exact validator/extractor issue. The repair instruction explicitly says to keep the assigned event/story meaning, change only what is needed to fix that issue, and not return the rejected wording unchanged.
- This restores the intended BEATS CREATE -> VALIDATE -> REPAIR -> VALIDATE behavior without adding another LLM stage or weakening finite-endpoint validation.
- Added a focused regression proving the rejected candidate and concrete failure are passed into the repair callback.
- Next checkpoint: run the focused Beat validation regressions, then rerun the Qwen planning/beat path. Beat 1 should be repaired from an ongoing cooking action into a visibly completed endpoint instead of repeating the same candidate.

## 2026-09-29 — Qwen finite-endpoint repair wording made procedural

- Acceptance `2521` developer logs proved the Beat repair plumbing works: Qwen receives the rejected Beat 1 text and the exact finite-endpoint failure on every retry.
- Qwen nevertheless returned the rejected sentence verbatim at temperature 0. This is a prompt-comprehension failure, not a parser or sampling failure.
- The phrase "observable completion endpoint" was too abstract for this model. Finite-endpoint repair now adds one concrete procedural rule: rewrite the same finite activity so it visibly finishes inside the beat, state the ordinary completed result, do not leave progressive/in-progress wording, and do not advance into the next story event.
- Temperature remains 0. No validator rule was weakened and no new semantic stage was added.
- The same `2521` logs also exposed a separate upstream state issue: later Beat CREATE prompts incorrectly say Amy is inside the locked basement. Do not conflate that with the finite-endpoint loop; inspect source-unit state extraction after Beat 1 repair advances.



## 2026-09-29 — Qwen Director sampling separated from deterministic calls

- Acceptance output showed Qwen Director Request 1 becoming overly static at the formatter default temperature of 0.15, repeatedly staging subjects as standing/remaning in place rather than using the beat creatively.
- Commit `e5a45f110b6b670715a7237048a1ae332e4eeee5` adds a Qwen-only Director Request 1 sampling profile in `minimax.py`:
  - temperature: 0.50
  - top_p: 0.92
  - top_k: 40
  - min_p: 0.03
  - presence_penalty: 0.10
  - frequency_penalty: 0.08
  - repeat_penalty: 1.08
  - seed remains 42
- This profile applies only to the creative RAW-scene Director call. ARC/Beat validators, narrow extractors, and Request 2 keep their existing deterministic/conservative settings.
- Next checkpoint: pull `gpt-arc-refresh` and rerun the Qwen acceptance locally. Judge whether Request 1 regains useful motion/staging without increasing state/continuity violations. No bridge job is required before that rerun.


## 2026-09-29 — acceptance 2526 exposed wrong ARC movement-state ownership

- Full Qwen acceptance `2526` generated a valid 6+2 beat plan but repeatedly failed Director Request 1 at Segment 2 and restarted planning after each 5-attempt local Director budget.
- Earliest wrong artifact is upstream in ARC state effects, not Director:
  - Source/event: Amy rushes Will and Amber to the basement, gets them inside, then locks the door.
  - Incorrect ARC effects assigned `set_containment Amy -> basement: contained` and `set_location Amy -> basement`.
  - Amy is the actor/helper; the children are the entities whose containment/location changes. The bad canonical effects therefore forced Director Request 1 toward a contradictory end state.
- Commit `e87312b3aba496a8e7daddeecff8f55bf816bbe8` tightens ARC CREATE, VALIDATE, and REPAIR generically:
  - movement/containment effects belong to the entity whose FINAL state changes;
  - a helper/escort/causative actor does not inherit the destination;
  - if A leads/gets/puts B into X, B may receive the effect; A receives it only when source separately says A enters/remains in X.
- This is an existing ARC semantic responsibility; no new LLM stage or Director workaround was added.
- Next checkpoint: pull `gpt-arc-refresh` and rerun the full Qwen acceptance. Verify E2 no longer places Amy inside the basement, then see whether Segment 2 advances under the new Qwen Director sampling profile.


## 2026-09-29 — Request 1 self-validation removed from production gating

- Qwen acceptance `2527` stalled at Segment 1: Director Request 1 failed its 5-attempt local budget before the independent source-based completion validator could meaningfully own the decision.
- Root cause: the creative Request 1 response still carried four model-owned completion booleans (`finite_activity_complete`, `named_beneficiaries_complete`, `activity_tools_settled`, `beat_complete`) and production logic required all four to be true before invoking the independent completion validator.
- Commit `ad656a0fe04fb36253d1648046c5042313051df3` changes production behavior when authoritative source is available:
  - Request 1 still returns the legacy/self-report fields for compatibility;
  - those self-reported booleans no longer gate or fail production acceptance;
  - the existing narrow source-based completion validator owns completion;
  - legacy/unit callers without authoritative source retain the old self-report behavior.
- This keeps KISS responsibility separation: Request 1 creates; narrow validators validate.
- Replacement full Qwen acceptance queued as `2528`.


## 2026-09-30 — Director prompt rollback + typed inventory ownership

- Qwen evaluation regressed Director reliability; GPT-OSS-20B was restored for the current acceptance path. Model size alone is not treated as an upgrade.
- Restoring the pre-simplification Director Request-1 prompt contract materially improved runtime behavior: the next run advanced past Segment 2. Prompt rollback commit: `4a17d724c13eda496fbbfa521addaf7994e425e9`.
- New Segment-3 defects exposed a typed-inventory ownership bug:
  - canonical beat state already distinguishes `held_objects`, `equipped_objects`, and `stored_objects`;
  - continuity projection incorrectly collapsed both `held` and `equipped` into `held_props`, which could make a sheathed/holstered item appear hand-held;
  - prompt-derived continuity could also promote incidental serving props (for example a pancake tray) into durable held state without a typed `set_item_state`.
- Commit `9bfec85000b78301ea3695c03af09b11f6b80477` makes persistent inventory Python-owned:
  - newly visible held props persist only when typed state authorizes `held`;
  - `equipped` is not represented as hand-held;
  - Director Request 1 receives a deterministic canonical item-state contract with exact meanings for HELD / EQUIPPED / STORED;
  - timed micro-beats that merely restate unchanged state (for example “window remains broken; door stays locked”) are rejected;
  - retrieval/equipment beats reject unassigned awkward `release ... from ...` wording.
- Source-unit state extraction now receives recent prior source text as REFERENCE ONLY so tiny extractors can resolve anaphora such as “She equips the weapons” back to named items in the preceding source. State is still extracted only from the current source unit.
- Commit `94f69ff14f40723f31aa085882eec6dcd100427c` adds a deterministic carry-mode guard: an item assigned `equipped` cannot end held in-hand, and an item assigned `held` cannot end holstered/sheathed/stowed.
- Regressions: `86bf439e2cfb949263e87ee1b24573130e598759`, `da57820a2fb2e91579142152c0b04bbba4d09624`.
- Pending verification:
  - `tests-2620-typed-inventory`
  - GPT item-anaphora probes `2621-2640`
- Next checkpoint: verify those tests/probes. If green, rerun GPT acceptance on current head and inspect Segment 3 first for (1) pistol/katana typed effects, (2) no pancake-tray carryover, (3) no held/equipped contradiction, and (4) no timed continuity-only filler.


## 2026-09-30 — typed-inventory verification checkpoint

- `tests-2620-typed-inventory` ran 85 targeted tests plus 6 subtests. Result: 84 passed, 1 failed; the only failure was a stale regression expecting an incidental `pancake` prop to survive an authoritative move. Under the new typed-inventory ownership rule, untyped prompt-derived held props must be cleared rather than persist.
- Updated that stale assertion in commit `18dfc6f843a3b4dcf846d7cbaea693bb27f73807` to expect no persisted held prop.
- GPT-OSS item-anaphora probes `2621-2640` were 20/20 correct. Each resolved the pronoun owner and the prior-source grouped item reference, then emitted one `set_item_state(..., value=equipped)` effect per resolved item.
- This validates the current source-unit extraction design: prior source is REFERENCE ONLY for pronoun/anaphora resolution; persistent state still comes only from the current source unit.
- Next checkpoint: rerun the focused typed-inventory tests on current head. If green, run a fresh GPT acceptance and inspect the earliest real runtime defect, starting at Segment 3 for pistol/katana item states, pancake-tray carryover, held/equipped contradictions, and timed continuity-only filler.

## 2026-09-30 — Director baseline reset: generate first, promote rules from evidence

This section supersedes older Director-specific guidance that treated typed state,
barrier topology, terminal-target state, item carry mode, or completion extractors
as blocking acceptance gates.

- ARC and BEATS are unchanged. Their CREATE -> VALIDATE -> REPAIR -> VALIDATE loops
  remain the semantic planning authority.
- Director Request 1 is now a minimal creative stage:
  - ASSIGNED SOURCE is story authority;
  - CURRENT BEAT is the scene to stage now;
  - OPENING CONTINUITY is advisory frame-0 context;
  - a broad/generic continuity summary may not override a concrete CURRENT BEAT;
  - NEXT BEAT is only the boundary.
- Request 1 no longer receives Python-generated final-state contracts, barrier
  contracts, or HELD/EQUIPPED/STORED item instructions.
- Request 1 structured output is now creation-only: \`{"raw_scene":"..."}\`.
  Model-owned completion booleans were removed from the production schema.
- Existing deterministic Director checks are retained as diagnostics only.
  Hand conflicts, item-state contradictions, missing subjects, topology/crossing,
  barrier binding, containment, early timing, and End-continuity structure may emit
  warnings but do not trigger regeneration.
- Independent completion, terminal-target, barrier-side, barrier-traversal, and
  barrier-state LLM checks are no longer called from the Director generation path.
  Keep the helper code for experiments/regressions until evidence shows whether any
  narrow check deserves promotion back to a blocker.
- Request 2 remains a formatter/translator. Malformed formatter responses may retry
  up to three times; timestamp correspondence/syntax problems are diagnostic only
  after deterministic normalization and do not block the run.
- Director content failures must not invalidate a valid ARC/beat plan. Recovery
  resumes from the last committed segment/checkpoint and retains planning.
- Development method from this checkpoint:
  1. generate the complete prompt set whenever transport/parser output is usable;
  2. compare all prompts to gold;
  3. collect concrete recurring failures;
  4. add the smallest generic rule only when full-run evidence shows it is needed;
  5. never add a rule merely to make internal state more formally complete.
- Gold-prompt principle: optimize for story-visible continuity needed by the next
  clip, not a perfectly normalized world-state ontology. Refresh segments may
  restate important visible state more strongly; append segments should lean on
  video continuity and only concise relevant state.



## 2026-09-30 — Refocus on BEAT generation; frozen Director beats 5-8 invalid

- Active development focus moves back upstream to BEAT generation/validation before further Director tuning.
- The frozen eight-beat Director test plan was inspected manually and contains a major continuity failure beginning at Beat 5:
  - Beat 5 has Amy shoot/unlock the basement door after she deliberately locked Will and Amber behind it for safety.
  - Beat 5/6 then drift spatially around the basement-door encounter instead of preserving Amy outside the children's safe area.
  - Beat 8 has Amy push the children out in a way that follows from the corrupted containment/location logic rather than a clean safe-room release.
- Treat frozen Beats 5-8 as INVALID test input. Do not use that plan to judge Director quality or add Director rules.
- Beats 1-4 are not automatically promoted to gold; the next task is to rebuild and validate the complete eight-beat plan against the locked gold story behavior.
- A concise reference list of the locked gold beats is now stored in \`docs/GOLD_BEATS.md\`.
- Next checkpoint: focus on ARC/BEATS output until all eight generated beats preserve story order, containment, actor/location ownership, and end-state continuity. Only then freeze the plan again for Director-only testing.


## 2026-09-30 — Canonical character profiles before ARC/BEATS

- Active focus remains upstream on BEAT-plan correctness.
- New rule: stable main-character facts are established once before ARC/BEAT generation rather than being re-invented in later beats or Director prompts.
- Initial canonical fields are intentionally small: \`age\` and baseline \`clothing\`.
- New persisted file: \`character_canon.json\`.
  - keyed to a SHA-256 of the current story text plus \`subjects.txt\`;
  - reused unchanged while those inputs match;
  - automatically regenerated when either source changes.
- Canonicalization precedence:
  1. explicit facts in the story;
  2. explicit facts already present in \`subjects.txt\`;
  3. only genuinely missing values are inferred once by the local LLM.
- The canonicalizer receives both the synopsis and existing subject definitions. This prevents it from inventing a new age/clothing value when the user has already supplied one elsewhere.
- Canonical clothing means the baseline outfit only. Temporary later state such as dirt, blood, bile, damage, wetness, etc. remains continuity state and does not replace the baseline outfit.
- ARC CREATE, ARC VALIDATE, and BEAT CREATE now receive a separate \`CANONICAL CHARACTER FACTS\` section. These facts are context/canon, not story events to schedule.
- Current character-canon prompt is deliberately simple and based on the proven local test:
  - system: establish factual canonical film information; return succinct JSON;
  - output: \`{"characters":[{"name":"...","age":"...","clothing":"..."}]}\`.
- This is the first canonical-data layer. Do not generalize to locations/props/etc. until observed failures justify it.
- Commits:
  - \`fc1f964e4320f5f52cf1ee0d4753daf343a96334\` implementation
  - \`b9cafa809408573479d0635b4e2bb2b0b9cc75db\` focused regressions

## 2026-09-30 — configurable canonical data + compact Beat CREATE prompt

- Canonical character facts are now user-configurable through `canonical_data.txt`.
- Initial configured fields: `age, clothing, gender`.
- The implementation is generic rather than hardcoding those three fields:
  - comma/newline-separated labels are normalized to machine keys;
  - the LLM response schema is built dynamically from the configured fields;
  - `character_canon.json` now stores `version: 2`, the configured field list, and per-character values;
  - the canon hash includes story text, `subjects.txt`, and the configured field list, so changing `canonical_data.txt` forces regeneration.
- Explicit story/subject facts remain authoritative; only missing configured values are creatively established once.
- Canonical results continue to be reused deterministically by Python and are exposed to planning as character facts.
- Segment 1 Director Request 1 now receives `CANONICAL STARTING CHARACTER FACTS` so applicable identity/appearance facts are established in the opening portrayal. It is explicitly forbidden from introducing an absent/future character solely to display canon.
- Beat CREATE was replaced with the new compact creative prompt:
  - `SOURCE FILM`
  - `KNOWN SUBJECTS`
  - `CHARACTER FACTS`
  - `ASSIGNED EVENTS`
  - optional `PREVIOUS BEAT` only when real
  - optional repair/user-specific sections only when applicable.
- Removed from the normal Beat CREATE prompt: barrier-name rules, closed-boundary sections, preserved-barrier sections, and the beneficiary-specific food/hand-off prose.
- Core creative rules now explicitly include spatial awareness, one-to-two concise sentences, and names instead of pronouns.
- Relevant commits:
  - `621f5eff08787427a5eb7ca4b69c2843410786be` — implementation
  - `9af7023ea1857e877935f030e947d0a839974dd1` — fix canonical_data.txt newline parsing
  - `c7ce7c9782a3c926b123e84289fdf982eed64326` — `canonical_data.txt`
  - `5028f94268de69c0926cb962fd4ce353f0d53328` — canonical/prompt regressions
  - `6139f0875aa99b54b6c46d6a05dedf145149d92e` — updated Beat CREATE regression
- Next checkpoint: run the focused test suite, then generate a fresh Amy beat plan and inspect the exact Beat CREATE prompt/output before doing more Director tuning.

## 2026-09-30 — hard sampling split + beat-only optimization phase

- LLM routing is now responsibility-based and defaults to deterministic behavior.
- Explicit creative allowlist:
  - `character_canon`
  - `macro_arc_create`
  - `macro_arc_repair`
  - `macro_arc_majority_tail_repair`
  - `beat_generation` (including single-beat repair/regeneration)
  - `director_raw_scene`
- Creative request profile:
  - temperature `0.8`
  - top_p `0.95`
  - top_k `0`
  - min_p `0.05`
  - repeat_penalty `1.15`
  - seed `42`
  - `reasoning_effort="high"`
  - `thinking_budget_tokens=1024`
  - `chat_template_kwargs.enable_thinking=true`
- Every non-creative `ask_llm` call now forces temperature `0` and seed `42`, including unlabeled/new calls. This prevents validators/extractors from accidentally sampling because a caller forgot metadata.
- The direct visual end-state LLM path was also changed from temperature `0.10` to `0`, seed `42`, repeat penalty `1.15`.
- `--deterministic` is not sent in request JSON because llama.cpp implements it as a process-level flag. The llama-server hosting deterministic calls must be launched with it.
- Server-only/native settings remain outside request JSON. Current expected runtime includes 8192 context, flash attention, Jinja, port 1234, cache RAM 32768, seed 42, `-np 1`, and the reasoning-budget exhaustion message.
- Do not pin `--reasoning-budget 1024` globally if using per-request routing; creative calls now send `thinking_budget_tokens=1024`.
- Commits:
  - `a31dab19a5f6cad888a6506445f8204e3448305f` — responsibility-based sampling/reasoning routing
  - `13bba833bd43673b928839b133f0c3c3d5f5664d` — keep creative reasoning controls request-native
  - `814969404dff9a78f600b24d7d2382179def4d35` — deterministic default + visual extractor temp 0
  - `73fbba2747aac5dc706548027736ca67352c9e41` — routing regressions
  - `fce8913ace62349baa92ff945b50cdee1ed0ad41` — project policy documentation

### Active development scope

The sole optimization target is now **beat generation**.

Process:
1. generate beats;
2. analyze the earliest incorrect beat/artifact;
3. repair the smallest responsible prompt/validator/state handoff;
4. regenerate and compare again.

Do not tune Director prompts during this phase. Director quality is downstream of beat quality.

Barrier/state information will be reintroduced only when a concrete beat failure demonstrates that one specific fact is needed. Add the minimum necessary fact/rule; do not restore the previous broad barrier blocks.

## 2026-09-30 — deterministic calls now use low reasoning

- Deterministic LLM calls remain temperature `0`, seed `42`.
- They now also use:
  - reasoning enabled;
  - `reasoning_effort="low"`;
  - `thinking_budget_tokens=128`;
  - `reasoning_budget_message=". Enough thinking, now answer."`.
- The same budget-exhaustion message is now sent per request for creative calls as well; creative calls keep high effort and a 1024-token reasoning budget.
- Current llama.cpp supports `reasoning_budget_message` in the request payload, so this no longer depends only on the server launch default.
- Commits: `67793614298b28ce8cb8f414127d21e7e6a57a31`, `4af3910b996bf067df997eabacd4297f05db7fe3`, `468523f3077b25316f849ad87afc09cb98992a82`.

## 2026-09-30 — full story context for beats + boundary enforcement dormant

Observed repair failure:
- Beat 7 correctly expanded "She lets her kids out of the basement" to opening
  the basement door and releasing Will/Amber.
- Python rejected it because the canonical barrier was locked and the assigned
  state effects did not include `set_barrier_state`.
- The repair prompt then incorrectly asked the creative model to preserve the
  source event while avoiding the source-required boundary transition.

Changes:
- `SOURCE FILM` in both phase Beat CREATE and single-beat repair now receives
  the full parsed `story.txt` narrative rather than the current chapter span.
- The assigned event remains the local execution authority.
- Beat boundary/barrier enforcement is now fully dormant:
  - removed deterministic unassigned barrier end-state rejection;
  - removed barrier binding / closed-boundary / preserved-barrier sections from
    the beat semantic validator;
  - filtered boundary/containment facts and effects from the validator view;
  - removed the post-validator destination-presence boundary gate.
- Boundary helper code remains in place for later surgical reintroduction.
- Relevant commits:
  - `56f40c58ef7a7cfa19eb1cdfa5561b33b70f9bb9` — full story in Beat CREATE/repair
  - `1e0019b1fd9a629388e5d719f609dfbe5da35b60` — disable structural barrier rejection
  - `222bc8929399f573e58d76539fbbcd46dc97b1dc` — boundary-blind semantic validator
  - `0089a064c2c857ff4518f6e12aeadd27bf237e23` — disable destination-presence gate
  - `e650fda8fedf7a9634b5cd7304fd79c9f0ec9328` — update regressions



## 2026-09-30 — forced beat generation checkpoint + creative seed fix

Observed user-facing failure:
- `--generate-beats` printed the source-span planner output and then jumped directly to
  `Story arc and beats generated successfully.`
- The newly generated `beats.txt` was repeatedly identical.
- No per-beat CREATE/VALIDATE logging appeared, making it look as though Beat VALIDATE
  was not running.

Root causes:
- Explicit creative ARC/BEAT requests were routed through the creative profile but still
  pinned to `BENCHMARK_SEED` (42), so identical prompts were intentionally reproducible.
- When explicit force-generation started with an already-empty `beats.txt`,
  `load_or_generate_beats()` passed `reset_validation_state=False`. A completed
  `beat_validation_state.json` with a matching fingerprint could therefore short-circuit
  `_run_forward_beat_validation()`, returning the previous finalized beats without calling
  Beat CREATE or Beat VALIDATE.

Fixes:
- Creative requests now call `generate_random_llm_seed()`; deterministic validators and
  extractors remain temperature 0 / seed 42.
- Any explicit `force_generate=True` now resets beat validation state, even when
  `beats.txt` is empty before launch. Normal non-forced recovery behavior is unchanged.
- Production commit: `8dfcc060efdb4286f6481358283f204ed344b7c7`.
- Regression commits: `310b587074b4c3cd0b4dddf4c96fab3790393624`,
  `587165ef65fec9a70049a1da4a6be4e3577353e0`.
- Queued bridge regression: `tests-2698-force-beat-validation-random-seed`.

Expected next manual run:
- source-span planning may still be structurally similar;
- Beat CREATE lines must appear;
- each beat must visibly enter the single-beat validator;
- repeated explicit Generate Beats runs should no longer be locked to identical creative output.

## 2026-09-30 — Beat CREATE subject guard regression + hidden source classification delay

Observed full-run failure:
- Source-span planning completed and saved story_arc.json.
- Beat generation then failed before contacting the LLM with:
  `Parsed subjects.txt information was not included in the beat generation prompt; refusing to contact LM Studio.`

Root cause:
- `build_beat_generation_messages()` computed the compact `subject_text` aliases but the
  compact Beat CREATE refactor omitted the `KNOWN SUBJECTS` section from the actual prompt.
- `verify_subjects_in_beat_messages()` correctly detected that omission and aborted.
- Fix: restore `KNOWN SUBJECTS\n{subject_text}` in Beat CREATE.
- Production commit: `f00b65a1af16101ebefdbad8e90a189294a8879e`.
- Existing regression `test_minimal_beat_generation_keeps_defined_subjects` already encodes
  this exact contract and was ahead of production code.

Planner latency clarification:
- After the final `Source span ...` line, `plan_story_chapters()` calls
  `classify_source_units()` before visible-event classification.
- With 8 source units this performs 15 sequential deterministic LLM calls:
  - 8 terminal classifiers (one per unit);
  - 7 hard-reset classifiers (units 2-8).
- These calls currently have no progress logging, so the program appears idle until
  `classify_visible_source_unit_ids()` begins printing `Event N requires...`.
- They exist only to derive chapter boundaries; Beat CREATE has not begun during this pause.

## 2026-09-30 — current working-tree changes: canonical data, planning diagnostics, and compact validation

This section records the uncommitted changes made after the previous checkpoint. It supersedes the earlier canonical-data descriptions above where they conflict.

### Canonical character data

- `canonical_data.txt` is now authored character information, not a comma/newline-separated list of fields. The included example defines Amy, Will, and Amber directly.
- The canonicalization request sends only the contents of `canonical_data.txt` to the LLM. It no longer uses `story.txt` or `subjects.txt` to establish character facts.
- Every character must receive `age`, `clothing`, and `gender`. The LLM copies values stated in the file and invents a reasonable value only when one of those three is missing.
- Additional fields are extracted only when explicitly stated in `canonical_data.txt`; the LLM is instructed not to invent additional fields.
- `character_canon.json` now uses version 3 and is keyed by a SHA-256 hash of the canonical-data text alone. It is reused when the file is unchanged and regenerated when it changes.
- Segment 1 Director Request 1 receives the original `canonical_data.txt` text under `CANONICAL STARTING CHARACTER FACTS`.
- README documentation and canonical-character regression tests were updated for this file-driven format.

### Source-span planning diagnostics

- Source-span refinement accepts an `on_source_span` callback. The runtime uses it to print every finalized span as it is extracted:
  `Source span N [start:end]: text`.
- Each `source_unit_visible_responsibility` decision now prints:
  `Event N requires a concrete on-screen event: YES|NO`.
- Each `source_unit_local_relation` decision now prints both source spans and the parsed `MERGE` or `NEW_TASK` result.
- Each `source_unit_state_effects` result now prints the source unit, source text, and JSON state effects, including an empty list when no persistent effect is found.
- These diagnostics are flushed immediately so a live planning run shows progress while each narrow LLM request completes.

### Beat creation and acceptance diagnostics

- Batch Beat CREATE prints every generated beat as:
  `Beat N created: <beat text>`.
- Single-beat repair/regeneration prints the same creation line.
- After a candidate passes validation and its checkpoint is saved, acceptance prints:
  `Beat N accepted: <beat text>`.
- The existing detailed acceptance line remains and reports committed required events and the completed-event cursor.

### Beat validation prompt and coherence context

- The main `beat_validation` prompt was reduced from roughly 1,280 fixed words to roughly 374 fixed words.
- The compact prompt retains the essential checks: current-job completion, finite versus ongoing work, participant/beneficiary preservation, previous-state continuity, reserved-later ownership, assigned final-state effects, and material fidelity.
- Boundary/barrier/containment effects remain filtered from this semantic validator according to the active boundary-dormant architecture.
- The post-validation physical/causal coherence prompt receives the previously accepted beat under `PREVIOUS BEAT` when one exists. Beat 1 omits that section.
- Focused validator and planner regressions were updated to assert the shorter wording and the previous-beat handoff.

### Verification

- Focused canonical, planner, source-span, beat-generation, and validator tests pass after these changes.
- The compact `beat_validation` prompt was checked at approximately 374 fixed words before dynamic story/state content is inserted.
- No commit has been created for this working-tree update.


## 2026-09-30 — source-classifier progress logging

- Added live progress logging for the 15 deterministic source classification calls that
  previously created a long silent pause after source-span extraction.
- For each source unit:
  - terminal classifier prints `Terminal check span N: YES|NO`;
  - hard-reset classifier prints `Hard-reset check span N: YES|NO` for spans 2+.
- With 8 source spans this produces exactly 15 concise progress lines before visible-event
  classification begins.
- Production commit: `f8abf9fbebfacb38ce41da780f92bc249409878b`.
- Regression commit: `0be78bbb5989e2ec993b6405a25ad992cfa5e00f`.
- No new bridge job was queued.

Subject/canonical clarification:
- `canonical_data.txt` now owns canonical character facts and no longer depends on
  `subjects.txt`.
- `subjects.txt` remains useful for known visual-subject identity/mapping into planning
  prompts, so the restored `KNOWN SUBJECTS` block remains in Beat CREATE for now.


## 2026-10-01 — Beat CREATE/REPAIR moved to temperature 0

Local repeated testing showed that GPT-OSS 20B Beat writing becomes unstable at any
temperature above zero. A captured repair trace also showed correct internal reasoning
followed by a sampled final answer that reintroduced the exact ambiguity it had identified.

Changes:
- Beat CREATE (`beat_generation`) now uses temperature `0`, seed `42`, and
  repeat penalty `1.15`.
- Beat CREATE keeps the high reasoning profile (`reasoning_effort="high"`,
  `thinking_budget_tokens=1024`) because reasoning quality was useful; only answer
  sampling was causing drift.
- Beat repair now has its own `beat_repair` purpose and uses the same temperature-0,
  high-reasoning Beat writing profile.
- Beat repair prompt now explicitly requires the smallest textual change, preservation of
  unaffected wording, and explicit replacement/non-reintroduction when the reported issue
  identifies a bad/ambiguous word.
- Existing REPAIR -> VALIDATE flow remains intact; a repaired beat cannot be accepted
  without another validator/coherence pass.
- Other creative calls (ARC create/repair, character canon, Director raw scene) remain on
  their existing creative sampling profile; this change is Beat-specific.

Commits:
- `8c7f04140c38e413c9b2185bf63405643ce8a911` — production routing + repair contract
- `bc7901f474420c8c0454309fdbb8df4654a565e0` — Beat CREATE/REPAIR routing regressions
- `7d35e7dd596f5d73777f547ac98b84d87e62676f` — repair purpose/revalidation-order regression
- `6a1384286c62ffbf95972f4653194aca91bc0c31` — PROJECT_NOTES sampling policy update


## 2026-10-01 — typed location seeding + deterministic state preflight

Observed failure:
- Beat 2 passed both semantic and coherence validation, then state commit raised:
  `set_location references an untracked entity: 'zombie'`.
- The generic outer exception handler treated that deterministic state-application error as
  a generation failure, deleted the arc/checkpoint, and restarted from arc creation.

Fixes:
- Required-event state application now derives entity namespaces from the arc's own typed
  state effects.
- An unknown `set_location` entity may be seeded only when typed effects establish exactly
  one role for that entity (character, threat, object, or barrier).
- Conservative singular/plural aliases are supported so typed roles such as `zombies`
  can establish the namespace for a location effect on `zombie`.
- No story-specific threat vocabulary was added.
- All required-event state effects are replayed in a deterministic preflight immediately
  after the arc is saved and before Beat CREATE/VALIDATE begins.
- State-application failures now raise `RequiredEventStateApplicationError`, preserve the
  current saved arc, and bypass the old generic arc-wipe/restart path.
- The top-level runtime also treats this exception as deterministic/fail-fast instead of
  endlessly replaying the same invalid arc.

Commits:
- `28bf277bfb2ee4a766670144115eac88b5f7142a` — production state-role seeding,
  preflight, and retry-scope fix.
- `87f79a1ca030cc9de1d66d8d478904b1ca8caebb` — typed-location/preflight regressions.
- `b8f3d7242eae44308e188054d6883ea51716d417` — regression proving deterministic
  preflight failure preserves the saved arc and never starts Beat generation.


### 2026-10-01 follow-up — preflight exception catch placement corrected

Acceptance `acceptance-2700-state-preflight-location` was interrupted while running
`test_state_preflight_failure_preserves_saved_arc_and_does_not_start_beats`.

Root cause:
- The dedicated `RequiredEventStateApplicationError` catch had been inserted into the
  JSON-repair retry loop instead of the outer Beat-generation recovery loop.
- The real outer loop still caught the deterministic state error as generic `Exception`,
  deleted the arc/checkpoint, and restarted indefinitely.

Fix:
- Removed the stray JSON-repair catch.
- Added the dedicated state-application catch immediately before the actual generic
  Beat-generation recovery catch.
- Deterministic preflight failures now preserve the saved arc and propagate instead of
  entering the arc-wipe loop.

Commit: `61d0325f6a52d751de0c2d70f18451302c782611`.


## 2026-10-01 — updated Amy acceptance: state/split fixes green; Beat final-location miss found

Bridge results:
- `tests-2704-source-state-split-fixes`: 57/57 passed.
- `generate-beats-2705-gpt-updated-story-v2`: completed successfully against the
  updated locked Amy story.

2705 confirmed:
- source majority sentence remained one intact span;
- newly introduced zombie emitted `set_threat_state=active` before
  `set_location(zombie, house)`;
- final kid retrieval no longer emitted nonsensical `Will -> Amy` /
  `Amber -> Amy` locations;
- full 8-beat generation completed without state-preflight failure.

Earliest real semantic miss:
- Beat 2 CURRENT JOB says Amy moves the children to safety **and returns to the
  kitchen**.
- Candidate ended after placing the children in a closet and never showed Amy's
  return, even though assigned state includes `set_location(Amy, kitchen)`.
- Beat validator incorrectly returned VALID.

Fix:
- Beat validator now states that every assigned `set_location(entity, place)`
  must be visibly true at the candidate's final state.
- If CURRENT JOB explicitly says an actor returns to a location, the candidate
  must show that return before ending.

Commits:
- `b0dc4bfbc75a693f2697cbb3249d88d6d9c60ea0` — final-location validator rule.
- `9be30ba0ab1cbc21833bf29d524585f075ab4a43` — regression coverage.


## 2026-10-01 — accepted Beat state capture: threat shorthand crash

Acceptance `generate-beats-2710-gpt-accepted-state` demonstrated that broad post-acceptance
state capture is retaining useful concrete continuity (closets, objects, carried/stored items,
threat injuries, and environmental changes), but its first attempt failed after Beat 4 with:
`Beat state patch entity threats.zombies must be an object.`

Root cause:
- the accepted-Beat extractor may use an unambiguous scalar shorthand such as
  `{"threats":{"zombies":"active"}}`;
- canonical threat entries require object records such as
  `{"threats":{"zombies":{"status":"active"}}}`;
- parsing validated the generic canonical patch shape before the accepted-state path had a
  chance to normalize this harmless shorthand.

Fix:
- accepted-Beat state capture now converts only scalar values in the existing canonical
  threat-state enum (`active`, `incapacitated`, `dead`, `removed`, `cleared`) into
  `{"status": value}` before generic state-patch validation;
- ambiguous scalar threat values remain errors rather than being guessed;
- the normalization is accepted-state-specific and does not loosen the generic canonical
  patch contract.

Regression cleanup:
- the broad-capture prompt assertion now matches its actual capitalization;
- the source-span generation regression now reflects the current documented contract that
  Beat CREATE receives the full story under SOURCE FILM while ASSIGNED EVENTS remain the
  chapter-local execution authority.

Commits:
- `f9aa9b60d7646d50db0ade54e9a2ef2e05737383` — normalize accepted Beat threat status shorthand;
- `2e193e1e4c0078e75d72699abcc327af3933c6f4` — accepted-state shorthand regression;
- `509fd416e52e5a4375125ed906d39cb0896d424a` — align source-span regression with full-story Beat context.

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


## 2026-10-03 update — continuation reference window widened

The latest 8x6 local render was substantially better overall, but exposed two
off-camera continuity failures at append boundaries: a Picture-backed character
reverted to the Picture outfit when absent from the preceding clip's final moment,
and a later wide shot rebuilt subject placement after the preceding clip ended
close on only two subjects.

Root cause: append conditioning intentionally loaded only the final 22 frames
(~0.92 seconds at 24 fps), even though H3 reference-video conditioning can use a
longer video history.

Change:
- append and repair now pass the full previous clip when it is <=15 seconds;
- longer previous clips use only the most recent 15 seconds;
- an 8-second H3 clip therefore supplies all 192 aligned frames with no leading
  skip;
- clean refresh remains on the proven final-22-frame latent-context path;
- Picture-backed continuation Subjects now say their `wardrobe`, position, pose,
  and physical state come from `<Video 1>` rather than only their `clothing
  condition`.

Next local acceptance should specifically inspect boundaries where a character or
room participant leaves frame before the cut, because those are the cases this
change is intended to improve.


## 2026-10-03 update — 56-frame reference tail + RAW wrapper rejection

The full 8-second reference-video experiment was a mixed quality result and raised
runtime/VRAM substantially. Append and repair now use the most recent 56 frames
(~2.33 seconds) instead. For the normal 8-second/192-frame source this means
`skip_first_frames=136`, `frame_load_cap=56`. Clean refresh stays at 22 frames.

A separate Segment-3 prompt defect was traced upstream, not to H3 formatting:
Request 1 returned `Frame 0 (At 00:00.000, ):` and bullet-listed the action below
the timestamp. The old structure check found the embedded timestamp and accepted
the malformed RAW, which Python later copied into final H3 output. Request-1
structure validation now rejects timestamps wrapped by labels/prose and rejects
timestamp-only lines whose action is moved to following bullets. The Director must
retry with normal `At mm:ss.mmm, action` lines.

---

## 2026-10-03 handoff — native Guide overlap replaces append Ref2V

Implemented on `summary-to-story-test`:

- append uses the exact final 22 rendered frames as native
  `MiniMaxH3AddGuide` conditioning at frame 0;
- prior video/audio are disconnected from append Ref2V, which now carries
  persistent Picture references only;
- final H3 continuation text no longer claims a nonexistent preceding
  `<Video 1>` reference;
- raw append duration includes the duplicate guide head, then Python removes 20
  frames and the existing stitch removes the remaining 2;
- Director has a ~0.92-second airlock before CURRENT BEAT begins;
- coherence checks now cover final-frame participant omission and moving an
  occupied chair/stool/seat.

No custom node package is required. Local ComfyUI must include the native
`MiniMaxH3AddGuide` node; otherwise queueing fails with an update-ComfyUI
message.

Next acceptance target: rerun the tavern torture test, especially Segment 2→3
and 4→5, verify Griffin1 survives Segment 4's final-frame state, and compare
camera continuity/runtime against the Ref2V-tail experiments.

## 2026-10-03 handoff — latest native-Guide postmortem

Active branch is `h3-add-guidance-test`. The latest 48-second tavern render showed good
visual continuation into Segments 2 and 3, an audio discontinuity into Segment 2, and hard
visual cuts at the exact Segment 4 and 5 joins. The cuts matched a prompt conflict: the
hidden 22-frame Guide carried the real close composition, while the continuation 00:00
RAW line reconstructed all semantic-state Subjects into a different composition.

Implemented next test:
- Add Guide receives the aligned previous audio tail plus audio VAE as well as the 22 video frames;
- continuation frame 0 is deterministically rewritten to a generic Guide-authority anchor,
  so prompt-derived PREVIOUS SHOT END cannot force off-camera Subjects into the opening frame;
- Guide length remains 22 frames.

Next acceptance: rerun the same tavern torture test and inspect 1→2 audio plus 3→4 and
4→5 visual/camera seams. If hard cuts remain after the prompt conflict is removed, the
next architectural candidate is a preserved/masked AV overlap rather than adding more
Director wording or immediately increasing reference length.

## 2026-10-03 handoff — Director timing regression fixed

The Guide test initially stalled on Segment 2 because Request 1 was being asked to write a
synthetic 8.91667-second timeline. The local 20B model began emitting malformed timestamps
(`01:00.000`, `02:500.000`, etc.) and missing the End continuity state.

Fix: Director is back to a normal delivered-duration timeline. For continuation segments,
Python now shifts every nonzero accepted timestamp by the 22-frame Guide duration and then
replaces frame 0 with the Guide-authority anchor. Hidden Guide timing is no longer exposed
to Request 1. Audio+video Guide conditioning from the prior commit remains enabled.

Next action: rerun the same 48-second tavern test from Segment 1. Acceptance remains 1→2
audio continuity and 3→4 / 4→5 visual seams.

Follow-up: post-shift pronoun/timestamp validation now uses the raw H3 prompt duration (delivered duration + Guide offset), while Request 1 structure validation remains on delivered duration only.

## 2026-10-03 fix — refresh loader ambiguity exposed by location reference

Segment 6 clean refresh failed before queueing with
`WorkflowConfigurationError: ... contains multiple nodes named 'Load Video'`.

Root cause: refresh still used the legacy logical name `"Load Video"`. The exported
refresh workflow's actual previous-segment loader is titled
`Load Video (Path) 🎥🅥🅗🅢`, so node lookup previously succeeded only through the
fallback that selected the sole `VHS_LoadVideoPath` node. The location-state experiment
adds a second `VHS_LoadVideoPath` node for the persistent location clip, making that
fallback ambiguous.

Fix: `REFRESH_LOAD_VIDEO_NODE_NAME` now aliases the workflow's exact
`LOAD_VIDEO_NODE_NAME` title. The persistent location loader keeps its separate
`Location Reference Video` title. Added a regression proving the refresh prior-video
loader remains uniquely resolvable after a location-reference loader is added.

Next acceptance: rerun/resume through the next clean refresh and verify Segment 6 renders;
then evaluate the location-reference experiment on background geometry/fixtures as planned.

## 2026-10-04 handoff — location-state-test

Created branch `location-state-test` from main commit
`40f4727030507e116c1631367a80ba0711ca000e`.

Goal: test whether one persistent three-second character-free panoramic location reference
prevents H3 from rewriting off-camera environment (for example shelves becoming a torch)
while preserving the validated seamless 22-frame AddGuide seam.

Implementation:
- extract static setting facts from expanded_story.txt with a narrow temperature-0 call;
- fallback to overall_location when the story does not specify detail;
- render one 3-second wide orbital environment clip before Segment 1, with all Picture
  references disconnected;
- save/checkpoint the location-reference path;
- pass it as Ref2V Video 1 to initial and append segments, visual-only/no reference audio;
- keep append AddGuide on its own loader and unchanged;
- clean refresh receives four sampled frames from the same location clip through ref_images;
- final H3 prompt explicitly says the location reference owns static spatial layout only,
  never characters or current camera framing.

Next acceptance should focus only on background geometry/fixtures when the camera reveals an
area that was previously off-screen. Do not evaluate character persistence as part of this
test.

Refinement after diff review: the setting extractor now explicitly excludes furniture/props
that appear only because a later story action uses or introduces them. This keeps the
location reference honest: a vague "medieval tavern" is mostly designed by H3, then the
experiment tests whether that invented room persists off camera instead of pre-seeding
future beat objects into the panorama.

## 2026-10-04 handoff — tavern location-reference acceptance and prompt/state fixes

Latest 48-second tavern run established a useful split:

- the persistent 3-second location-reference video is successful for environment
  continuity; Segments 1-5 matched the covered room geometry extremely closely,
  with invention limited mainly to the slice the orbit did not show reliably;
- remaining failures were primarily prompt/state problems: ambiguous physical
  prose, indirect speech conflicting with the no-dialogue constraint, spatially
  impossible staging, dynamic Subject registration lag, and a Segment 6 clean
  refresh discontinuity.

Fixes now on `location-state-test`:

- CLI/default automatic refresh is `999`, matching desktop/web defaults;
- legacy GUI settings are migrated once: an old saved default `refresh: 6` becomes `999` and old default story temperature `0.8` becomes `0.4`; later explicit user choices are preserved;
- an explicit refresh interval is authoritative and no longer loses to
  source-span chapter-boundary refresh scheduling; `None` retains the legacy
  source-span fallback for programmatic callers;
- story-expansion default temperature is 0.4 and its prompt asks for film-ready,
  literal, physically unambiguous prose rather than literary ambiguity;
- an explicit Beat speech act (asks/orders/says/etc.) must become direct
  `<d>...</d>` dialogue in RAW; after same-segment Subject registration the
  final H3 identity repair emits the stable form such as
  `Goblin1 (S3) said <d>Give me a pint.</d>`;
- Director/RAW coherence now explicitly rejects hidden spatial teleportation such
  as serving a distant bar/table while still established at the door;
- post-RAW Subject resolution gets two attempts and is no longer allowed to fail
  open. Every resolved dynamic Subject must be registered before that segment's
  H3 prompt is assembled;
- Subject-resolver responses are now retained in prompt history for diagnosis;
- guided append postprocessing removes all 22 native Guide overlap frames and
  guided clips receive no additional two-frame stitch trim.

Next acceptance: rerun the tavern test as a new run with the revised humanoid-
creature story. Verify Segment 6 stays on normal Guide continuation (not
clean-refresh), new creatures are registered in the segment where they first
appear, explicit speech is tagged, and door/bar movement is physically staged.
Do not change the accepted location-reference architecture before this rerun.


### 2026-10-04 — provenance fixes after second tavern acceptance

The second tavern run kept room/location continuity strong but exposed four
specific upstream failures:

- reference-video audio could still be heard even though Ref2V audio inputs were
  disconnected and the location prompt requested N/A audio;
- a new goblin could "appear" in a chair without a physical entrance/reveal;
- held/container props could silently change identity (bucket -> mug,
  mug -> glass/chalice);
- an established actor could interact with a distant object without explicit
  travel (Amy at barrel -> crystal shelf/bar).

Current fixes:

- every rendered location-reference video is now atomically remuxed with ffmpeg
  using video stream-copy plus `-an`; the file used by all later conditioning
  therefore contains no audio stream regardless of what H3 generated;
- Director generation and RAW coherence validation both require visible
  provenance for a newly introduced foreground Subject: explicit physical entry
  through a route/boundary or explicit continuous camera motion revealing an
  already-present offscreen Subject; "appears" alone is insufficient;
- Director/validator preserve prop identity and acquisition provenance. A prop
  cannot silently become another prop, newly handled props need a stated source
  and acquisition action unless already established, and every transfer keeps
  an explicit, distinct, traceable source and destination;
- spatial travel validation is generalized: interaction with any different
  established position requires explicit actor movement there first. This is no
  longer a door/bar-specific rule.

These are prompt + low-temperature semantic-validator contracts, not
tavern-specific deterministic rewrites. The ffmpeg audio removal is the only
deterministic media transformation in this change.


### 2026-10-04 — setting-label and RAW pacing follow-up

Latest tavern acceptance was substantially improved but exposed two prompt-level
issues plus one renderer/location conflict:

- Segment 3 compressed prop acquisition and use into one late timestamp, making
  the cup visually appear in Amy's hand even though RAW named a shelf origin.
- Segment 4 invented a lid and immediately sealed the cup, again compressing an
  invented prerequisite/action chain.
- The persistent setting text called the only visible entrance a `back door`,
  while the location-reference video established a single door; this may have
  encouraged H3 to reinterpret the doorway geometry when the dragon entered.

Implemented on `location-state-test`:

- setting extraction no longer treats relative action labels
  (front/back/side, left/right) as proof of distinct static architecture; a
  single established instance is described generically;
- RAW Director now explicitly gives physical prerequisites their own earlier
  timed micro-beat instead of combining prerequisite + dependent action at one
  timestamp;
- RAW Director has a dedicated `DIRECTOR_RAW_SCENE_LLM_SETTINGS` profile at
  temperature `0.2` with high reasoning/random seed; other creative generation
  remains at `0.8`;
- focused regressions cover the setting, pacing, transfer, and sampling contracts.

Follow-up after the next tavern run:
- the room geometry remained stable, so the location-reference architecture is
  accepted for this test;
- prompt-only pacing was not enough: Segment 3 compressed doorway-to-back-table
  travel into about 1.5 seconds and H3 hid the missing travel with a cut; Segment
  4 similarly omitted the dragon's route from the doorway to the bar stool;
- a new narrow temperature-0 timing-feasibility validator now checks only whether
  consecutive physical transitions can visibly fit between their timestamps,
  with no hardcoded minimum duration;
- RAW transfer wording is now generic and requires an explicit, distinct source
  and destination plus source provenance for what is transferred;
- RAW invention is now explicitly economical: useful staging is still allowed,
  but optional secondary reactions/consequences and extra object/substance motion
  should not be added once the Beat action is already readable.

Next acceptance: rerun the same tavern story/Beats and inspect Segment 3/4 travel,
Segment 4 transfer behavior, and Segment 5 reaction/fluid choreography.


### 2026-10-04 — spatial acceptance; movable-prop bookkeeping is next

The newest tavern render no longer showed the prior spatial/teleportation failures. Treat
the location-reference + travel/timing architecture as provisionally accepted. The visible
remaining failures were ordinary props: glasses and the basket could still appear or
disappear.

Implemented on `location-state-test`:

- generation state now carries a separate persistent movable-prop ledger with stable IDs;
- the existing combined-continuity call maintains that ledger while H3 renders, so there
  is no additional always-on LLM request;
- ledger records track kind, owner, holder, location, contents, and
  present/lost/destroyed status and copy unchanged props forward while offscreen;
- source-authorized typed item state remains higher authority: held/equipped/stored/
  dropped/lost effects deterministically update the matching ledger record, so the new
  movable-prop ledger does not compete with existing canonical inventory truth;
- Request 1 receives the ledger as authoritative movable-prop state;
- strong prop-interaction Beats may trigger one tiny pre-RAW temperature-0 staging call;
  it returns either nothing or one minimal staging sentence when a required prop is not
  currently available;
- this is proactive repair before RAW generation, not a validator-driven
  generate/reject/regenerate loop;
- checkpoint/resume state and Director prefetch fingerprints include the prop ledger;
- focused regressions cover copy-forward/update, schema acceptance, conditional staging,
  test-mock routing, and resume slicing.

Next acceptance: reuse the tavern story/Beats and inspect mug/glass/basket identity,
location/possession, transfer contents, and whether the pre-RAW staging call fires only when
needed. No spatial/location changes should be made unless that regression reappears.

### 2026-10-04 — prop persistence accepted; Segment 2→3 ownership/state fix

Latest tavern acceptance materially improved movable-object continuity:

- the prior appearing/disappearing glasses and basket were gone;
- fluid/container behavior was acceptable overall;
- location geometry and earlier spatial/travel fixes remained stable.

The remaining Segment 3 failure was not renderer-only. Logs showed two upstream causes:

1. Segment 2's final timed action still had Goblin1 present, putting his mug on the counter
   and stepping back toward the hearth, but the End continuity state omitted Goblin1.
   Combined continuity therefore preserved the Subject identity but lost his position.
2. The prop ledger correctly tracked `mug_1` as owned by Goblin1 and sitting on the
   counter, but Segment 3 Director repurposed that mug as the source for Elf1's drink.

Implemented on `location-state-test`:

- post-RAW Subject resolution is followed by deterministic final-participant carry-forward:
  if a stable named Subject is present in the final timed micro-action but omitted by End
  continuity state, Python copies that exact final-action evidence into End state;
- explicit leave/exit/fully-occluded final actions are excluded from carry-forward;
- this adds no LLM call and does not alter the H3 timed action itself; it repairs semantic
  bookkeeping used by the next segment;
- Director now treats ledger `owner` / `holder` as exclusive continuity facts rather
  than generic inventory;
- the existing conditional prop pre-staging micro-call treats a matching prop owned/held
  by another Subject as unavailable unless CURRENT BEAT explicitly authorizes taking,
  reuse, or transfer, and should stage a distinct ordinary instance instead;
- Request 1 receives the same ownership rule in the injected prop-state block.

Focused regressions were added for omitted final Subjects, explicit exits, newly resolved
Subjects before registry append, and owned-prop prompt policy.

Next acceptance: rerun the same tavern case. Segment 2→3 is the key checkpoint:
Goblin1 should retain his semantic position near the hearth, should not drift into Elf1's
seat, and `mug_1` should remain Goblin1's instead of being reused to serve Elf1.

### 2026-10-04 — generated current-clothing Picture references

The tavern acceptance showed that Amy's correct rendered wardrobe survived only Segment 1;
later segments fell back toward the clothing in her original identity Picture. A separate
current-clothing visual authority is now implemented on `location-state-test`.

Implementation:

- when a visible character has no generated clothing reference yet, or the character's
  canonical current wardrobe changes, Python renders an isolated 1-second H3 character
  reference using the same base render path as the location reference;
- the character is front-facing in a neutral pose with the current outfit visible; there is
  no 360 orbit, camera move, cut, or story action;
- Python samples the 0.5-second frame and places that PNG in the ComfyUI input directory;
- the generated Picture is added to H3 subject definitions as clothing-only authority, e.g.
  `<Picture 2> references only the clothing that Amy is currently wearing.`;
- Picture numbering is dense and positional. Empty template `LoadImage` nodes do not
  reserve Picture numbers: if only Picture 1 is active, the first generated reference is
  Picture 2;
- Pictures 1-6 reuse the existing template LoadImage nodes when available. Once all active
  positions through 6 are occupied, Python dynamically creates `LoadImage` nodes for
  Picture 7, Picture 8, and so on; six is not a hard maximum;
- each character keeps the same generated Picture number after assignment. A later wardrobe
  change creates a versioned replacement PNG for that Picture instead of shifting every
  later Picture number;
- generated reference metadata is checkpointed and stored with each finalized H3 prompt so
  resume and saved-prompt rendering retain the exact image version used by that segment;
- no extra LLM call is added. The trigger/description comes from the existing canonical
  Subject/wardrobe state.

Focused regressions assert the dense Picture-2 case, stable numbering across an outfit
change, dynamic creation above Picture 6, clothing-only definition filtering, and the
front-facing one-second/no-orbit prompt contract.

Next acceptance: rerun the tavern story. Amy should use Picture 1 for identity and the new
generated Picture for her current clothing, so the post-Segment-1 renders should stop
reverting to the outfit in the original identity reference.

### 2026-10-04 — state media directory consolidation

All generated visual-state media now uses one persistent directory:
`<ComfyUI output>/video/state/`.

- location-reference video prefix moved from `video/location_state/location_reference`
  to `video/state/location_reference`;
- character-reference 1-second videos moved from `video/character_state/` to
  `video/state/`;
- sampled character-reference PNGs are now written persistently to the same
  `output/video/state/` directory instead of being authored in ComfyUI/input;
- because ComfyUI `LoadImage` reads from its input directory, Python stages a copy of the
  authoritative state PNG into ComfyUI/input only when preparing a workflow. The persisted
  checkpoint path points to the state-directory original.

The old `location_state` and `character_state` output prefixes are no longer used by new
renders.

### 2026-10-04 — outfit-reference identity conditioning

Production test showed that the generated clothing Picture could bleed its newly invented
face/body back into Amy's appearance. The isolated 1-second clothing render now conditions
on the target character's existing source Picture when available.

- the target Subject's original `picture_id` is resolved to its configured LoadImage;
- that source image is connected as the only Picture in the isolated outfit-reference
  workflow, so it is locally `<Picture 1>`;
- the outfit-reference prompt explicitly states that Picture 1 owns only identity/physical
  appearance (face, hair, age, build, species, body), while current clothing text owns the
  outfit and must not be copied from the identity Picture;
- the resulting sampled Picture remains clothing-only authority in the final story prompt;
- video-only/dynamic Subjects with no source Picture currently fall back to unconditioned
  outfit-reference generation and log a warning.

A possible future alternative—standalone reusable outfit assets that can be applied to
multiple characters—is documented in `docs/FUTURE_NOTES.md`.

### 2026-10-04 — clothing-reference persistence + portrait reference canvas

Two production fixes are now active on `location-state-test`:

- Person/outfit reference renders use a portrait 13:19 canvas. Python computes width/height
  from the requested megapixel budget and writes those dimensions directly into the isolated
  character-reference conditioner. The 3-second location orbit keeps the normal landscape
  workflow unchanged.
- Generated clothing Pictures no longer regenerate because the vision observer describes
  the rendered wardrobe differently. Each clothing Picture persists its intended wardrobe
  and condition. A new version is authorized only when the immediately preceding segment
  explicitly changes/removes/adds clothing or explicitly damages/soils/wets/burns it.
- Authorized changes are applied to the prior intended clothing-reference state, not to
  vision-observed wardrobe, preventing renderer drift from becoming canonical.

### 2026-10-04 — newest tavern postmortem: dynamic identity, transfer semantics, fixed fixtures

Newest production evidence separated four visible symptoms into three upstream causes:

1. Segment 2's extra plate was actually RAW's invented `small wooden tray`; the apparent
   extra cup is consistent with H3 compensating for RAW telling Amy to tilt a barrel as if
   it were a handheld pouring vessel.
2. Segment 4's generated Dragon1 state Picture existed before the render, but final H3
   labeled it clothing-only while the Subject definition said only `Dragon1 is a dragon`.
   H3 therefore had no Picture-owned dragon identity on first appearance. RAW also
   explicitly misdirected the brew onto Dragon1's scales instead of filling the cup.
3. Segment 5 used source-less liquid on Dragon1's tongue because the prior End continuity
   omitted the just-handed crystal cup, so the prop ledger did not carry that drink source
   forward. Segment 6 then conflicted with location authority by moving an established
   hanging lantern onto a table.

Implemented:

- dynamic Subjects with no external Picture now promote their generated state Picture to
  identity + current-appearance authority; source-backed characters retain the separate
  identity-Picture + clothing-Picture model;
- later outfit changes for dynamic Subjects reuse the previous generated Picture as identity
  conditioning;
- first unconditioned dynamic-reference generation no longer mentions nonexistent
  `<Picture 1>`;
- RAW generation/validation preserves the Beat's transfer destination/recipient/container,
  binds drinks/material to a real established source, and rejects final End states that drop
  a just-transferred/materially changed prop;
- RAW avoids unnecessary helper supports/containers/utensils used only to settle props;
- the existing extracted static-setting sentence is now supplied to Request 1 and coherence
  validation, preventing RAW from relocating explicit fixed fixtures before final H3
  location-reference injection.

Next production acceptance: rerun the same tavern case. Check Segment 2 for direct,
provenanced barrel -> Goblin1 mug transfer without a surprise helper prop; Segment 4 must
use the generated Dragon1 identity on its first appearance and fill/hand over the crystal
cup rather than pour onto the dragon; Segment 5 must sip from that carried cup; Segment 6
must preserve the established lantern placement and Elf1's table. Do not chase the apparent
overall quality degradation yet: this analyzed run predates the 13:19 character-reference
and clothing-reference persistence fixes.

### 2026-10-04 — 16GB split-mode reference assets fixed

The 16GB path was audited after noticing that versioned/torn-clothing references cannot be
created during the LLM-only phase. The issue was real: prompt-only mode skipped ComfyUI,
therefore it also skipped location-reference and dynamic character/clothing-reference
creation, while render-only mode assumed those files already existed.

Current behavior:

- `generated_prompts.txt` now contains ordered `reference_jobs` in addition to segment
  prompts;
- location and character reference jobs freeze all generation inputs needed by ComfyUI;
- character outputs are immutable/versioned PNGs, with a run token in prompt-only mode;
- a later dynamic-character clothing state references the prior generated Picture as its
  identity dependency instead of overwriting it;
- each segment retains the exact reference-version metadata that was current when its H3
  prompt was finalized;
- the render-only phase generates all saved references first in dependency order, then
  renders the saved segments in order;
- prompt-only H3 text receives the same persistent-location authority clause as normal mode.

Acceptance target: run the desktop 16GB flow end-to-end with at least one dynamic character
and one explicit clothing-condition change, inspect `generated_prompts.txt` before starting
ComfyUI, then verify v001 and v002 both remain under `output/video/state` and the appropriate
segment uses each version.

### 2026-10-04 — sliding dynamic-Subject references + per-segment Picture map

Implemented the requested conservative dynamic-reference lifecycle:

- persistent Subject/reference records are never deleted or renumbered;
- each segment gets a frozen `reference_bindings` map that records both the persistent
  canonical Picture number and the segment-local Picture number;
- H3 Subject definitions and ComfyUI reference wiring use the same segment-local generated
  reference map;
- a Subject remains retained for `ceil(total_segments / 2)` segments since its last
  explicit visual appearance, so a potentially passive/background Subject is not dropped
  immediately;
- after expiry, its Subject definition and configured/generated reference conditioning are
  removed only for the current segment; a later explicit re-entry restores the same
  persistent identity/reference version;
- `--disable-subject-removal` (also exposed in the desktop UI) keeps every previously seen
  Subject bound indefinitely;
- `generation_state.json` keeps the full tracking/binding history, and each completed
  segment plus `generated_prompts.txt` freezes the exact map/exclusions needed for 16GB
  replay.

Production acceptance: use a run with several dynamic Subjects entering/leaving. Verify an
inactive Subject remains bound through the sliding window, ages out at the threshold, its
configured/generated Picture is disconnected, another generated Subject can pack into the
vacated dynamic slot, and later re-entry restores the original identity asset even if the
H3 Picture number differs from its earlier segment.


### 2026-10-04 — 8/6 acceptance follow-up: transfer semantics, compressed travel, retained background Subjects

The next 8-second / 6-segment tavern render exposed three upstream issues despite strong
location continuity:

- Segment 2 RAW was accepted with the impossible phrase that ale was poured "from" a
  barrel lid. The Director and coherence validator now explicitly distinguish a fixed
  container from its lid/cap/handle/rim/latch; contents must come from the actual container
  or an established dispensing opening/tap.
- Segment 4 again allowed Amy to interact with a shelf/bar-area prop without explicit travel
  from her prior table position. Coherence validation now treats distinct named
  fixture/interaction areas from STATIC SETTING AUTHORITY as established positions and
  requires explicit movement between them.
- The final closing Beat compressed unlatching, crossing the doorway, closing, and locking
  into one timestamp. Timing validation now explicitly rejects sequential dependency chains
  hidden inside a single timestamp when they cannot execute visibly as one continuous take.
- Sliding Subject retention now derives explicit visual evidence from the complete accepted
  RAW scene, including its End continuity state, instead of only the stripped timed
  description. A patron that the accepted final frame says remains present therefore refreshes
  its retention age rather than being dropped merely because it performs no new Beat action.

The uploaded acceptance artifacts predate the new per-segment `reference_bindings` package:
they contain generated character-reference records but no frozen binding snapshots. The next
run must be made from current `location-state-test` and should show `reference_bindings` plus
`excluded_picture_ids` in each generated prompt record before reference-slot behavior is
judged.

Next acceptance: rerun the same tavern case from current branch head. Verify Segment 2 uses
the barrel/container as the ale source; Segment 4 visibly moves Amy to the shelf/bar and the
Dragon reference is both generated and bound; the closing sequence visibly traverses the
door before exterior framing; and background Goblin/Elf identity references remain bound
when the RAW End state keeps them present.


### 2026-10-05 — RAW validator split

The former combined RAW coherence validator is now split for the local ~20B runtime:

- `director_raw_scene_physical` checks subject movement/spatial continuity, entry/reveal,
  travel between established positions, barriers/seats/supports, fixed architecture, and
  final subject/barrier state.
- `director_raw_scene_prop_state` checks prop identity/provenance, ledger holder/owner/contents,
  source/destination transfers, CURRENT BEAT object/recipient/container/result fidelity,
  material sources, and final prop state.
- `director_raw_scene_timing` remains a third independent check.

Request 1 now evaluates physical/spatial -> prop/state -> timing, with a category-specific
retry message for each failure. Compatibility wrappers remain for old callers, but production
runtime no longer asks one large coherence prompt to reason about every domain at once.
The RAW Director prompt itself was intentionally left alone because it is being revised separately.


### 2026-10-05 — continuation Picture authority fix

Generated character references were being lost at the final H3 render boundary because
blank configured Picture slots were pruned before generated refs were attached. Their slot
numbers were then replaced in prompt text with "the supplied opening guide," even though a
generated character Picture would occupy that same segment-local number.

Current behavior:

- generated segment-local Picture IDs are protected from configured-slot exclusion and
  canonical remapping in append/refresh prompt conditioning;
- explicit generated `<Picture N>` identity/clothing authority survives into the actual H3
  prompt;
- the opening guide anchors only frame-0 pose/position/physical state for visible Subjects;
- Picture-definition lines no longer receive duplicated opening-guide state language.

Focused tests passed for generated-Picture preservation and non-duplication of guide authority.


### 2026-10-05 — dynamic reference identity descriptions + species-neutral reference portraits

The latest tavern acceptance confirmed that generated character Pictures now reach H3
correctly, but exposed an upstream identity-flattening bug for newly resolved dynamic
Subjects. RAW retained useful explicit appearance facts (for example a female silver-haired
elf and a humanoid dragon with obsidian scales/wings/amber eyes), while Python registered
only the functional fallback `Elf1 is an elf.` / `Dragon1 is a dragon.`. The first
generated identity Picture therefore had too little authority and could contradict the Beat.

Current fix on `location-state-test`:

- the existing post-RAW Subject-resolution call now also returns one concise
  `subject_descriptions` entry for each newly named dynamic Subject;
- those descriptions may use only explicit visual identity facts already present in RAW
  (species/type, sex/gender wording, age, hair, skin/scales/fur, build, anatomy/body, and
  distinguishing features), excluding action, pose, location, props, camera, mood, and
  invented details;
- Python persists that description as the dynamic Subject's canonical description during
  registration instead of falling back to species-only text;
- canonical source-character descriptions still override resolver descriptions for planned
  named characters;
- the resolver API remains backward compatible for older tests/callers, while production
  requests the new description map;
- the isolated one-second character-reference prompt is now species-neutral: it asks for a
  single subject's complete physical appearance and species/anatomy traits, and only shows
  clothing/accessories when explicitly described. It no longer assumes every Subject is a
  clothed humanoid.

Focused tests cover returned dynamic identity descriptions and the species-neutral
character-reference prompt contract.

Next acceptance: rerun the same tavern case and inspect the generated PNGs before judging
the final video. Elf1 should preserve the explicit female/silver-haired identity and
Dragon1 should preserve the humanoid-dragon/obsidian-scale/wing/amber-eye identity. After
that, investigate the two remaining spatial failures separately rather than changing the
reference architecture.


### 2026-10-05 — one-source dynamic wardrobe bootstrap

The dynamic-reference identity fix is now consolidated with initial wardrobe assignment so
clothing has one authoritative source before a new dynamic Subject's generated Picture is
rendered.

Current architecture on `location-state-test`:

- the existing post-RAW Subject-resolution call now bootstraps both non-clothing identity
  and initial wardrobe for each newly named foreground dynamic Subject;
- `subject_descriptions` contains only stable non-clothing identity facts already present
  in RAW (species/type, sex/gender wording, age, hair, skin/scales/fur, build, anatomy/body,
  distinguishing features);
- `subject_wardrobes` contains exactly `upper`, `lower`, `footwear`, and `other`;
- explicit RAW clothing is preserved; when a human/normally clothed humanoid has no clothing
  specified, the same LLM call assigns one simple setting-appropriate outfit exactly once;
- animals/creatures that normally do not wear clothing receive N/A wardrobe fields unless
  RAW explicitly provides clothing; explicit garment/footwear absence uses `absent` and
  overrides invention;
- Python stores that wardrobe directly in the new Subject continuity record before any
  character-reference media is generated;
- identity prose is deterministically stripped of any accidental wearing-clause so wardrobe
  is not duplicated in two canonical fields;
- the character-reference renderer is now a consumer only: it visualizes the persisted
  identity + wardrobe and is explicitly forbidden from adding/removing/redesigning clothing;
- later clothing changes continue through the existing persistent wardrobe continuity path;
  there is no second first-appearance clothing decision downstream.

Compatibility: older direct callers/tests of the Subject resolver may still request only
names or names+descriptions; production requests the full bootstrap tuple.

Acceptance target: rerun the tavern. Before video evaluation, inspect Elf1/Dragon1 generated
state metadata and PNGs. Elf1 should have both the RAW-derived female/silver-haired identity
and one persisted setting-appropriate outfit; Dragon1 should retain the RAW-derived dragon
identity and should not acquire humanoid clothing unless RAW explicitly says so. The same
persisted wardrobe must be what the story H3 prompt references.


### 2026-10-05 — expanded-story context for dynamic wardrobe bootstrap

The consolidated dynamic Subject bootstrap now receives the complete
`expanded_story.txt` as read-only wardrobe context.

- The existing post-RAW Subject-resolution call gets a `STORY CONTEXT` block containing
  the expanded story.
- RAW remains authoritative for actions and explicit appearance/clothing.
- STORY CONTEXT is used only when RAW leaves clothing unspecified, so the one-time
  canonical wardrobe can match the established setting, period, culture, and visual world.
- The expanded story is loaded once for the video run and reused both for existing
  story-location extraction and dynamic Subject bootstrap, including resumed runs.
- No extra LLM stage was added; this only enriches the existing identity+wardrobe bootstrap.
- Focused regression coverage confirms the story context reaches that prompt.

Acceptance target remains the tavern run: Goblin1/Elf1 clothing should now reflect the
expanded story's visual world while Dragon1 should stay unclothed unless the story/RAW
establishes clothing.


### 2026-10-05 — cumulative Director Request 1 retry blockers

Observed Segment 3 repeatedly bounced between independent blockers: final timestamp too
early, prop-transfer incoherence, then missing 00:00.000 staging. The retry path was resetting
to the clean base prompt after every failure and passing only the latest issue, so a later
retry could reintroduce a defect already corrected on an earlier attempt.

Fix on `location-state-test`:

- Request 1 now keeps a short unique list of every blocking failure observed during the
  current segment attempt loop.
- Every retry is still rebuilt from the clean base prompt, but appends one compact
  `RETRY REQUIREMENTS` block containing ALL blockers seen so far.
- Structure retries now include the exact structure error returned by Python instead of only
  a generic "begin at 00:00.000" reminder.
- Physical/spatial, prop/state, timing, dialogue, and empty-scene blockers all use the same
  cumulative mechanism.
- This does not add an LLM stage or preserve/re-feed the rejected RAW; it only prevents the
  model from forgetting already-discovered constraints while keeping retry prompts small.
- Regression coverage reproduces a structure failure followed by a prop/state failure and
  verifies the third Request 1 prompt contains both requirements.

Acceptance target: rerun the failed tavern Segment 3. Once a retry learns that the final
micro-beat must be >= 6s and frame zero must be 00:00.000, those constraints should remain
present while it also repairs the mug transfer instead of oscillating between validators.

### 2026-10-05 — Python now owns three Director RAW structure repairs

Request 1 is normalized before semantic validators run. Python now inserts a
missing `00:00.000` anchor, moves only a too-early final timestamp to the 75%
segment boundary, and guarantees exactly one trailing
`End continuity state:` marker. These cases no longer need Director
regeneration. Earlier timestamps are deliberately unchanged, so compressed
travel (for example doorway -> back table in 1.5s) still reaches the existing
timing-feasibility LLM unchanged. Prop/state semantic retries are also
unchanged.

### 2026-10-05 — run-level H3 visual style

- Added `--visual-style "STYLE"` with default `Live-Action cinematic`.
- Python now owns the global visual-style prefix at the final H3 assembly boundary. Every final `detailed_description` begins `[Shot 1] {visual_style}, ...`; Request 2 is told not to invent or repeat a global style phrase.
- The historical `Live-action, cinematic` formatter prefix is stripped if it still appears, then the configured style is inserted once.
- The style is saved in generation-state/run config and `generated_prompts.txt` metadata. Resume/repair reuse the saved style unless `--visual-style` explicitly overrides it.
- The desktop UI exposes Visual style and passes it to `minimax.py` as one subprocess argv element, so spaces require no platform-specific quoting inside the app.

### 2026-10-05 — per-defined-Subject canonical appropriate attire

The Amy reference test exposed a wardrobe-authority loss: the expanded story said
`rough-spun tunic and leather apron`, but the earlier broad character-canon pass
collapsed that to `tunic and apron`, producing an incomplete clothing reference.

Current fix on `location-state-test`:

- after `expanded_story.txt` exists, every pre-defined Subject from `subjects.txt`
  gets its own independent `story_subject_wardrobe_extract` LLM request;
- the call is deterministic/low-budget (temperature 0, low reasoning, 128 thinking
  budget through the normal analysis profile; output capped at 128 tokens);
- each call receives the full expanded story but reasons about exactly one Subject;
- the prompt explicitly asks for the Subject's **appropriate attire**: preserve all
  explicit material/texture/color/wear/layer details, then fill only missing normal
  outfit pieces so a normally clothed Subject has a complete coherent outfit;
- "appropriate attire" is species/body/setting aware. Dragons, animals, and other
  beings that appropriately do not wear clothes return `N/A` unless the story
  explicitly clothes them; a normally clothed modern person may receive ordinary
  attire such as a T-shirt and blue jeans when the story is silent;
- the earlier broad character-canon pass no longer invents clothing when source
  clothing is absent; it returns `N/A` and leaves final wardrobe ownership to this
  expanded-story per-Subject extractor;
- each extracted outfit overwrites that Subject's `character_canon.json`
  `clothing` value and is therefore the canonical defined-Subject outfit used by
  Director/H3/reference generation;
- canonical attire is seeded into structured wardrobe state before fallback story
  parsing, and `apron` is now recognized as an `other` wardrobe component;
- explicit no-clothing values do not generate a bogus `wearing ...` sentence.

Dynamic/video-created Subjects keep the existing one-source post-RAW wardrobe bootstrap;
this new extractor applies only to pre-defined Subjects.

### 2026-10-05 — latest tavern postmortem: Elf promotion, support routes, prop render identity, audio specificity

The 18:16 tavern run showed that the accepted location/Guide architecture remained stable, but
five upstream/render-boundary gaps were still visible:

- Segment 3's Subject resolver correctly returned both `Goblin1` and `Elf1`, including an
  Elf identity description and wardrobe, but its rewritten RAW still said generic `the elf`.
  Python required the literal functional name to appear in RAW and silently filtered `Elf1`,
  so no Elf generated reference was created.
- Segment 1 RAW contained an unsupported support transition (Amy was established on the floor,
  then "steps down from the counter"), and Segment 6 again chose gratuitous tabletop traversal.
- Segment 3's final timed action left Amy at the back table while End continuity state incorrectly
  relocated her near the counter; Segment 4 therefore began with bad semantic position authority.
- H3 visually duplicated/merged distinct drink containers even though the prop ledger itself was
  correct (Goblin mug duplication; Segment 4 glass/cup merging/substitution).
- Segment 2 soundscape reduced the Goblin entry to a generic `footstep`, leaving H3 room to
  exaggerate it into heavy/repeated footsteps.
- Dragon1's generated identity Picture was finally used, but the unclothed nonhuman reference
  acquired inappropriate human sex anatomy. This is not a defined-Subject attire-extractor issue:
  Dragon1 is dynamic and is intentionally allowed to remain unclothed.

Implemented on `location-state-test`:

- dynamic Subject resolution now explicitly requires every returned `subject_names` label to be
  applied in returned RAW; Python also deterministically canonicalizes unambiguous generic
  role/species nouns in timed RAW using the resolved functional name before promotion. A resolved
  name that still cannot be found now raises instead of silently disappearing;
- Director creation and the physical validator now preserve body support/elevation literally:
  no stepping down/off/over or climbing onto counters/tables/bars/etc. without an established or
  Beat-required reason, and ordinary floor routes are preferred;
- the physical validator now explicitly rejects End continuity state that relocates a Subject away
  from its final timed position without a later timed move;
- every final H3 prompt now carries one compact render-boundary prop rule: established handheld/
  movable props remain one distinct physical object and may not duplicate, merge, or substitute;
- soundscape extraction now preserves source/count/duration/intensity when RAW establishes them and
  specifically avoids turning one step into generic/plural or exaggerated footsteps;
- generated nonhuman identity references keep external anatomy species-appropriate and do not
  invent human sex-specific anatomy unless explicitly established; no clothing is added merely to
  cover anatomy.

Focused regressions were added for the exact Elf metadata-with-generic-RAW failure, unsupported
support transitions/stale End position, final H3 prop identity contract, sound source/count
specificity, and unclothed nonhuman reference anatomy.

Commits:
- `8dc31b5efe8fc3f0e4375edfe3cd598b17fa5f7b` — implementation
- `43227243a157e2679695e0c80f7c7095e087c70f` — focused regressions

Next acceptance: rerun the same tavern case from current `location-state-test`. Before judging
video, confirm Segment 3 logs register `Elf1` and create/bind its generated Picture. Then inspect:
Segment 1 stays on an ordinary floor-side wiping route; Segment 2 keeps one Goblin mug and does not
invent heavy/repeated footsteps; Segment 4 starts Amy from the back-table state and keeps the
existing chalice/new Dragon cup distinct; Segment 6 uses a visible ordinary floor route rather than
a tabletop shortcut or teleport.



### 2026-10-05 — resolver restart-loop hotfix
- Fixed a regression from the stricter dynamic Subject resolver enforcement.
- If returned Subject metadata is valid but the resolver fails to rewrite its functional name into RAW, Python first retries the naming deterministically against the already-accepted Director RAW.
- If no safe deterministic mapping exists, that resolver entry is warned/dropped instead of restarting the entire segment.
- Raised the per-defined-Subject wardrobe extractor output cap from 128 to 256 tokens after local GPT-OSS repeatedly truncated the JSON response at 128.
- No LLM prompt wording changed in this hotfix.
- Commit: `5f6668bba909898984b374c14cfae4ed6aef7f7e`.


### 2026-10-05 — prop ledger identity lock + delta-only continuity props
- Fixed deterministic prop-ledger corruption where the combined continuity observer could overwrite an existing prop ID with a different object kind (for example `mug_1` becoming a cloth).
- `merge_prop_ledger()` now treats `prop_id -> kind` as immutable identity. Same-kind observations may update mutable state; a conflicting different-kind observation is assigned a fresh unique prop ID instead of rewriting the existing object.
- Simplified the `COMBINED_CONTINUITY_SYSTEM` prop instructions so the LLM reports only NEW props or CHANGES. Unchanged props are omitted because Python copies the committed ledger forward.
- Removed the redundant instruction telling the LLM to copy unchanged/offscreen props forward.
- Kept the rest of the Combined Continuity wording unchanged because it still defines semantic final-frame facts the LLM must observe.
- Added regressions for a `mug_1 -> cloth` collision and for delta-only prop prompt wording.
- Commits: `79474334b75f3625d3b467f8da1ccd6e19c5b7e7`, `4c8f927c58c28bfbde65e4319cb467db5b63ed1f`.
- Tests were added but not executed through this chat environment.


### 2026-10-05 — tavern regression: simplify validators, retire prop staging, add persistent Subject ledger
Latest rendered tavern run regressed despite character references working. Root causes were primarily upstream scene/continuity handling rather than missing Pictures:
- Segment 2's first RAW used a camera reveal for the goblin, but the prop validator rejected the goblin's chipped mug because it was not already in the ledger even though CURRENT BEAT introduced it. Retry accumulation degraded this into literal `appears` wording.
- Segment 3/4 showed the same over-validation pattern for newly introduced cups/chalices. Segment 3 also accepted impossible cross-room interaction and a malformed `held_props` shape caused a useful continuity response (including the chalice) to be discarded.
- Elf1 lost the explicit female fact because the post-RAW Subject resolver was restricted to appearance facts present in RAW even though CURRENT BEAT said female.
- Goblin1 remained referenced/registered but Segment 4's timed H3 action omitted him while Dragon1 entered the same visual area.

Changes:
- Retired the proactive `director_prop_staging` LLM path completely, including its dead schema/trigger/helpers/purpose entry.
- Simplified `director_raw_scene_prop_state`: a prop explicitly introduced by CURRENT BEAT may first appear in the scene; existing ledger props remain identity/state constrained; source/destination and real source-container checks remain.
- Simplified `director_raw_scene_physical` to only entry/reveal, travel between established positions, support/elevation changes, and final End-position consistency.
- Added deterministic RAW rejection for `appears` / `suddenly appears` / `pops into view` introduction wording before the physical LLM validator.
- Subject resolver now receives CURRENT BEAT and may use explicit non-clothing appearance facts from RAW or CURRENT BEAT. Explicit female/male wording in the resolved canonical description is deterministically copied into Subject registration.
- Combined Continuity sanitizes harmless `held_props:[{"id":"..."}]` variants into string IDs before strict schema validation, preventing an unrelated list-shape error from discarding otherwise useful prop observations.
- Removed implementation-language from modified prompts: no `Python owns...`, `Python copies...`, or prop-ledger copy-forward explanation. Combined Continuity user input now labels the database simply `COMMITTED PROP LEDGER:`.
- Director Request 1 likewise states required timestamp/end-state behavior directly rather than explaining Python normalization.
- Added deterministic final-H3 continuing-Subject state insertion for continuation clips. A known Subject with a concrete opening position that is absent from current timed action gets a concise line such as `Continuing Subjects: Goblin1 remains beside the counter.`
- Added `subject_state_ledger`, a Python-owned durable all-Subjects database parallel to the prop ledger. It is seeded from configured `subjects.txt`, persists dynamic Subjects and last-known state across offscreen segments, is checkpointed run-level and per-segment, and is intentionally not yet used as a new semantic/render authority. `last_updated_segment` means ledger update, not rendered observation.
- Future design note: the Subject ledger currently treats N/A/empty continuity values as unknown and therefore does not clear prior nonempty state from an empty observation. Before it becomes authoritative for every-world-state use, explicit clear/change semantics should be defined rather than inferring clears from absence.

Prompt changes made in this batch:
- `director_raw_scene_prop_state` now begins: `Validate only prop continuity in RAW. A prop introduced by CURRENT BEAT may first appear in this scene.`
- `director_raw_scene_physical` now begins: `Validate only subject movement in RAW.` and enumerates only the four narrow rejection cases above.
- `director_raw_scene_subject_resolution` receives a `CURRENT BEAT` block and the description rule now says appearance facts may come from `RAW or CURRENT BEAT`.
- `COMBINED_CONTINUITY_SYSTEM`: `Omit unchanged props.`; removed architecture explanations about Python.
- Director Request 1: direct behavior only for 00:00.000, final-quarter timing, and exactly one End continuity state.

Implementation commits:
- `90c96a26be5949910759356585b90da3e78276c6` — simplify validators/continuity and add Subject state ledger
- `a28c323e2941a72390cd4c885aa648ce082227a6` — finish stationary Subject carry-forward and state seeding
- `a102960ab54f06c6a45a06262c27a07dae3fb048` — remove retired prop-staging code and clarify Subject ledger timestamp
Regression commits:
- `347fe1efabf4b65e7319728fe2ea314fc693cdf7`
- `cd3bb16e907264d6e4f50dba9e3b6b7dac96dd7b`
- `6cc56dbc4fceece85030858b835a796d1935b0c8`

Regressions cover CURRENT-BEAT prop introduction, deterministic pop-in rejection without an LLM call, CURRENT-BEAT gender/appearance input to Subject resolution, held-prop schema sanitization, offscreen Subject persistence, and deterministic stationary-Subject H3 carry-forward.
Tests were updated but not executed through this chat/GitHub connector environment.

Next local acceptance run:
- Segment 2 should no longer burn retries merely because CURRENT BEAT introduces Goblin1's chipped mug, and accepted RAW must not contain pop-in `appears` wording.
- Segment 3 Elf1 reference/registry should retain explicit female identity; Amy must visibly travel before interacting at the back table; mug/chalice identities should remain separate; a harmless held_props shape slip must not erase the chalice.
- Segment 4 should retain Goblin1 through deterministic continuing-Subject text when he remains in the location, and pouring must have a real source container. Watch specifically for cup floating/duplication even with correct prompt state.
- Inspect `generation_state.json.subject_state_ledger`: configured Subjects should exist from run start, dynamic Subjects should be added, and offscreen Subjects should retain last-known state.


### 2026-10-05 — object-state-work branch

Created branch `object-state-work` from `main` at commit
`8dc5c86e2cc0ae8f3b79aaa8e327b100b5b792ac`.

This branch is the active workspace for the next object-state work. The latest
implementation and acceptance target are the 2026-10-05 Subject/prop ledger
handoff immediately above; no new implementation changes are part of this
branch setup.
