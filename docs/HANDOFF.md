# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first for project-wide architectural rules. This file describes the current branch implementation, active experiment, latest evidence, and immediate next work.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `location-state-text`

Runtime/bridge mailbox branch: `gpt-runtime`

Baseline branch this experiment diverged from: `main`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is development/evaluation only and must not become a production dependency.

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` remains the sole narrative authority. Expansion may add concrete staging/detail where the source is silent, but it may not add, replace, contradict, skip, reorder, or materially alter source events/outcomes.

### Primary goal achieved

### Next goal

Continuity

Location continuity -> currently testing 2-second 360 orbit video as room reference
State continuity -> TBD

Fix observed failures in order. Explain the failure and proposed fix before making substantive architecture/prompt changes.

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


## 2026-10-04 handoff — location-state-test

Created branch `location-state-test` from main commit
`40f4727030507e116c1631367a80ba0711ca000e`.

Goal: test whether one persistent two-second character-free panoramic location reference
prevents H3 from rewriting off-camera environment (for example shelves becoming a torch)
while preserving the validated seamless 22-frame AddGuide seam.

Implementation:
- extract static setting facts from expanded_story.txt with a narrow temperature-0 call;
- fallback to overall_location when the story does not specify detail;
- render one 2-second wide slow-pan environment clip before Segment 1, with all Picture
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
