# MiniMax H3 — Future Notes

This file is for promising ideas, heuristics, and experiments that are **not current production architecture** and should not be treated as implemented requirements.

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
