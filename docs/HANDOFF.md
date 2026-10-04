# MiniMax H3 — Development Handoff

Read `docs/PROJECT_NOTES.md` first for project-wide architectural rules. This file describes the current branch implementation, active experiment, latest evidence, and immediate next work.

## Repository / active branch

Repository: `blanchetteje-hub/MiniMaxH3_Director`

Active experimental branch: `location-state-test`

Runtime/bridge mailbox branch: `gpt-runtime`

Baseline branch this experiment diverged from: `main`

Final runtime target: local GPT-OSS 20B-class model. GPT-5.6 Sol is development/evaluation only and must not become a production dependency.

## Primary goal

`story.txt -> gold-standard MiniMax H3 prompts`

`story.txt` remains the sole narrative authority. Expansion may add concrete staging/detail where the source is silent, but it may not add, replace, contradict, skip, reorder, or materially alter source events/outcomes.

### Primary goal achieved

### Next goal

Continuity

Location continuity -> 3-second persistent 360-orbit room reference is accepted; covered geometry stayed ~99% consistent in the latest tavern run
State/subject/action continuity -> active work

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

