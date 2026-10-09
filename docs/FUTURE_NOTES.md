# MiniMax H3 — Future Notes

This file is for promising ideas, heuristics, and experiments that are **not current production architecture** and should not be treated as implemented requirements.

## TODO — future work / experiments

These are **not approved implementation tasks**. Revisit only when they become relevant; detailed notes remain below.

- [ ] **Minimum local LLM context and long-story chunking:** evaluate **6,044 tokens** as the minimum supported context window; redesign story-dependent requests so expanded stories of **50+ beats** and other large story chunks can be processed in bounded, coherent pieces without losing source coverage, beat ordering, or cross-chunk continuity. See [Minimum-context / long-story scaling](#minimum-context--long-story-scaling).
- [ ] **Dialogue-density classification:** evaluate a narrow story-type dialogue prior; keep source dialogue authoritative. See [Dialogue-density classification experiment](#dialogue-density-classification-experiment).
- [ ] **Segment timing / duration fit:** deterministic timing budgets plus narrow extraction for genuinely underspecified action durations. See [Segment timing / duration-fit validation](#segment-timing--duration-fit-validation).
- [ ] **Structured static-space catalog:** evaluate only if simpler location/relative-label handling fails. See [Structured static-space catalog experiment](#structured-static-space-catalog-experiment).
- [ ] **RefMod conditioning:** A/B test previous-segment reference compression and reusable location references. See [RefMod reference-conditioning experiment](#refmod-reference-conditioning-experiment).
- [ ] **Standalone outfit references:** test clothing-only reference assets separately from identity. See [Reusable standalone outfit-reference experiment](#reusable-standalone-outfit-reference-experiment).
- [ ] **Clothing-state reference refresh:** test short updated reference videos when visible wardrobe condition changes materially. See [Clothing-state reference-video refresh](#clothing-state-reference-video-refresh).

The persistent room geometry / navigable topology item is already marked **SOLVED** below and is intentionally not an open TODO.

## Minimum-context / long-story scaling

**Future requirement / proposal, not implemented:** consider **6,044 tokens** as a bare-minimum local LLM context window. Do not enforce this threshold until tested against actual prompt sizes, schemas, reasoning/output reserves, and representative stories.

For expanded stories with **50+ beats**, and any other stage currently supplied large portions of story text:

- Inventory consumers of the expanded story, full beat lists, prior prompts, and other unbounded narrative context.
- Break long inputs into **bounded, meaningfully segmented chunks** (for example, ordered contiguous story/beat spans), rather than truncating the story or silently dropping source events.
- Preserve global source authority, event/beat order, exact coverage, and continuity across boundaries using **Python-owned indexing and compact factual context**. Avoid duplicating an evolving narrative authority or inventing an additional state ledger.
- Only send the local model the story span and necessary context for the current job; keep end-to-end checks that every required source event is accounted for.
- Evaluate the real minimum viable context window and the quality/performance tradeoff using longer stories (50+ beats), without adding unnecessary serial LLM calls or ComfyUI downtime.
- Keep context-window support separate from the four sampling/reasoning profiles, so each task's actual context and output needs can be controlled.

**Status:** TODO for future design/testing; no runtime code or settings changes requested here.

## Dialogue-density classification experiment

Potential future use: estimate how dialogue-heavy the **type of film** should be before deciding how aggressively dialogue should be requested or inserted into generated beats/scenes.

The useful prompt shape tested was:

> Based on the following story text, I want you to return an enum value indicating how much dialogue should be in the film. The amount of dialogue is NOT proportional to the amount of text since this story could be 5 minutes long or it could be 2 hours long, you are only determining how much dialogue would be in this TYPE of story.
>
> The enum values are:
> NONE,
> VERY_LOW,
> LOW,
> MEDIUM,
> LARGE
>
> Story:
>
> [story text]

Observed prompt-shape findings:
- Calling the target a **film** materially improved the judgment.
- Explicitly stating that dialogue amount is **not proportional to story-text length** was also important. The model should classify the expected dialogue density of the story type, not infer duration from the amount of source text.
- The Amy zombie-action story returned **VERY_LOW**, which is directionally appropriate for an action-heavy film.
- The test story, “A romance film about two star-crossed lovers as they try to be together during medieval Spain,” returned **LARGE**, which is directionally appropriate for a dialogue-heavy romance/drama.

Possible future role:
- Run one narrow story-level classification before beat/dialogue generation.
- Use the result only as a global dialogue-density prior or budget signal.
- Do **not** let it override explicit source dialogue, scene needs, or story authority.
- Do **not** assume every beat should contain dialogue merely because the overall classification is high.
- This should remain a narrow classifier rather than another large semantic planning stage.

Status: exploratory only; not yet validated across a broad genre set or wired into production.

## Segment timing / duration-fit validation

Potential future use: validate that the actions and dialogue assigned to one MiniMax H3 segment can plausibly fit within that segment's allotted runtime. Production segments may be anywhere from roughly **5 to 30 seconds**, so timing feasibility should not be assumed merely because a beat is semantically coherent.

The old approach of asking the local model a broad question such as “does this collection of actions fit in N seconds?” was unreliable. Pairwise 8-second fit probes overthought simple cases and could accept intentionally overloaded action chains. Do not revive that holistic judgment as the default.

Preferred future direction:

> **Use deterministic Python timing checks for everything measurable; use a very small local-LLM estimation/extraction call only when the physical duration is genuinely underspecified.**

### Deterministic Python timing checks

Python should handle timing whenever the required duration can be estimated from explicit measurable content.

Examples:
- dialogue word count;
- number of separately timed spoken lines;
- explicit pauses/waits;
- explicit source durations;
- timestamp ordering;
- timestamp bounds against the segment duration;
- deterministic minimum spacing between sequential events where the renderer contract requires it;
- other mechanically measurable timing constraints.

For dialogue, use a configurable approximate speaking-rate baseline rather than asking the LLM whether the dialogue “feels too long.”

A rough planning baseline at about **150 spoken words per minute** is:

- 5 seconds ≈ 12 words;
- 10 seconds ≈ 25 words;
- 20 seconds ≈ 50 words;
- 30 seconds ≈ 75 words.

These are not automatic hard limits because reactions, pauses, movement, delivery speed, and overlapping action consume additional time. They are useful deterministic budget estimates.

A future implementation could reserve part of the segment for non-dialogue action and compare the remaining speech budget against actual dialogue word count.

### Narrow LLM duration estimation only for unknown physical actions

Some physical actions cannot be timed reliably from text alone because key dimensions are unspecified.

Example:

> “Mateo climbs the stairs.”

Python cannot know the duration without knowing facts such as:
- how many stairs;
- stair length/height;
- Mateo's pace;
- whether he is running, walking, injured, carrying something, etc.

For cases like this, a small local-LLM call may estimate only the timing-relevant fact or duration class needed by Python.

The LLM should not decide overall scene validity. Prefer outputs such as:
- a coarse duration estimate/range;
- QUICK / MODERATE / LONG;
- KNOWN_ENOUGH / UNDERSPECIFIED;
- or another very small contract chosen after probing.

Python should then combine that observation with the known segment duration and other measurable timing costs to decide whether the segment is overloaded.

### Architectural intent

Keep the same general pattern used by current continuity invariants:

1. Python owns the segment duration and measurable timing budget.
2. Python calculates everything deterministic.
3. Only genuinely fuzzy physical-duration questions go to a narrow local-LLM call.
4. Python performs the final fit/overload decision.
5. If overloaded, repair/regenerate the earliest responsible stage rather than compressing unrelated actions into unrealistic timestamps.

This may become especially important for dialogue-heavy genres, where semantic beat structure can be correct while spoken content alone exceeds the available 5–30 second segment.


## (SOLVED) Persistent room geometry / navigable topology

Observed production failure: a character can place other characters into one enclosed space and later use the same modeled door as though it leads somewhere incompatible, such as putting children in a closet and then opening that same door to enter a hallway.

Future continuity work should give Python a persistent representation of **actual room geometry and doorway connectivity**, rather than relying only on prose location labels.

Potential direction:
- Track stable spaces/rooms as entities.
- Track barriers/doors as connections between exactly two spaces.
- Preserve which side of a barrier each Subject occupies.
- Preserve containment relationships such as closet -> bedroom -> house.
- Prevent one established doorway from silently changing its destination.
- Allow geometry to expand only when the story introduces a previously unknown connection.
- Render the relevant local topology back into Director/H3 context when needed.

Keep this deterministic and structural where possible. The purpose is not to build a full 3D scene graph; it is to prevent impossible navigation and identity reuse of doors/rooms across segments.

Status: SOLVED.  3-second 360 orbit view of location.


## Structured static-space catalog experiment

Potential future implementation: expand the current prose setting extractor, or
add one narrow companion call, that returns a JSON catalog of persistent static
elements for the location reference.

Possible fields could include:
- entrances/barriers and whether multiple distinct instances are established;
- fixed fixtures and landmarks;
- persistent furniture;
- major surfaces/architectural features;
- lighting sources;
- broad spatial relationships when explicitly supported.

The purpose would be to compare the **textual static-space contract** against the
generated location-reference video/prompt and reduce ambiguity such as one story
door being described as a separate `back door`.

Constraints:
- Do not turn this into a full 3D scene graph.
- Do not catalog action-only props or transient objects.
- Do not invent counts, relative labels, or connectivity the story does not
  establish.
- Keep the 3-second persistent location-reference video as the visual continuity
  mechanism; the JSON catalog would be supporting authority/validation only.

Status: back-pocket experiment only. First evaluate the simpler relative-label
extractor fix.


## RefMod reference-conditioning experiment

Potential future implementation: evaluate **RefMod / MiniMax H3 reference conditioning** as an optimization and continuity tool. Do not integrate it into the current pipeline until controlled tests show a meaningful advantage over the existing reference-image/video workflow.

Two promising uses:

- **Compressed previous-segment video reference:** encode/compress the prior segment into reusable RefMod conditioning to see whether we can retain most of the current continuation/visual-continuity benefit while reducing the substantial VRAM and generation-time cost of passing the full previous video as a reference.
- **Persistent location reference:** create reusable RefMod conditioning for important environments/locations (potentially from multiple views or a short environment/panorama video) so recurring locations retain stronger visual identity and geometry across segments.

Suggested validation:
1. Same prompt/seed/segment with no continuation reference.
2. Current full previous-segment video reference.
3. Equivalent RefMod-conditioned previous-segment reference.
4. Compare character/wardrobe consistency, props, location geometry, transition quality, generation time, and peak VRAM.
5. Separately test persistent location RefMods against the existing location/reference-image approach.

Important constraints:
- Treat RefMod as **visual conditioning**, not authoritative continuity state. Python/canonical state remains the source of truth for subjects, props, locations, and transitions.
- Compression may discard details, so do not assume it can replace full video references for precise identity or short-term continuity.
- Do not replace existing character reference images unless direct A/B testing shows RefMod is superior.
- Prefer this as an optimization/conditioning layer rather than another semantic planning stage.

Status: back-pocket experiment only; not part of current production architecture.

## Reusable standalone outfit-reference experiment

Potential future implementation: generate/reference **outfits by themselves**, without a
person wearing them, so one visual clothing asset can be applied to multiple different
characters.

Possible direction:
- render or otherwise establish a clean isolated visual reference for the outfit itself;
- treat that reference as clothing-only authority, never identity/body authority;
- combine it with each target character's own identity Picture when producing the
  character-specific outfit reference or final H3 conditioning;
- allow the same outfit asset to be reused by Amy, another human, or another compatible
  character without regenerating the garment design from scratch;
- keep fit/body adaptation character-specific so one shared outfit asset does not force the
  same body shape or proportions onto every wearer.

Potential advantages:
- fewer duplicated outfit-generation renders;
- stronger consistency for uniforms, costumes, armor, team clothing, or recurring wardrobe
  shared across multiple characters;
- cleaner separation of identity authority from wardrobe authority.

Risks to test:
- whether H3 can reliably transfer an outfit-only reference onto a person without inventing
  mannequin/body traits;
- whether different body types/species cause fit or geometry artifacts;
- whether identity and outfit references compete when both are supplied.

Status: back-pocket experiment only. Current production architecture still generates a
character-specific 1-second clothing reference, now conditioned by that character's
identity Picture.



## Clothing-state reference-video refresh

Potential future implementation: when a Subject's visible clothing state changes materially
during a segment — for example clothing becomes torn, soaked, bloodied, burned, muddy, or
otherwise visually altered — generate a new short ComfyUI state/reference video so later
segments do not have to reconstruct the changed wardrobe state from text alone.

Possible workflow:
1. Detect and persist the canonical clothing-state change in Python continuity state.
2. After the segment in which the clothing visibly changes, generate a new Subject
   state/reference video.
3. Condition that state-video generation with:
   - the previous segment video where the clothing state changed; and
   - the Subject's initial reference image, when one exists.
4. Tell the H3 prompt to create a video of the person with their clothing in the state
   established by **<Video 1>**.
5. Use the resulting state video as the refreshed visual wardrobe authority for subsequent
   segments until another material clothing-state change occurs.

The previous segment video should provide authority for the changed clothing condition,
while the initial reference image preserves Subject identity. Canonical Python clothing
state remains semantic authority; the refreshed video is visual conditioning.

Questions to validate:
- whether H3 reliably preserves the changed clothing state from <Video 1> while the initial
  image preserves identity;
- whether the initial clean reference image competes with a damaged/soaked clothing state;
- whether one short refreshed state video is sufficient for later segments;
- which clothing-state changes are visually significant enough to justify the extra render.

Status: back-pocket experiment only; do not integrate until clothing-state continuity needs
it and controlled tests show that refreshed state videos improve persistence.
