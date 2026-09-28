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
