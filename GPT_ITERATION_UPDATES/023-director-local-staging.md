# Iteration update 023 — Director local staging boundary

## New earliest observed gold mismatch

Latest full Amy acceptance `run-acceptance-amy-majority-budget-022` completed successfully through all 8 segments and the ARC now preserves source coverage while satisfying the deterministic majority allocation. The earliest remaining gold-quality mismatch is Segment 1.

The generated first beat remains essentially only `Amy is cooking breakfast...`, while locked gold turns that broad activity into a complete, filmable 8-second domestic scene: children present at the table, food handled/served, ordinary reactions/dialogue, and a clean local completion before the zombie beat begins.

## Important architecture finding

This is not merely a breakfast-specific omission. The locked gold routinely adds **local cinematic realization** that the sparse story did not literally enumerate: mundane props, small reactions, short dialogue, camera choreography, and concrete sub-actions. These additions do not change the plot; they make the assigned beat executable and visually complete.

Current Request-1 Director rules contain the opposite instruction: `Do not embellish the beat` / `Do not invent any changes to the scene`. That boundary prevents sparse story input from ever expanding into gold-quality prompts without forcing the user to author prompt-level choreography in `story.txt`, which violates the product goal.

## Probe

`director-local-staging-probe-023` tested a narrow replacement policy with Mistral 24B at temperature 0:

- CURRENT BEAT remains the only story event allowed to advance.
- NEXT BEAT remains a hard forbidden boundary.
- Director may invent ordinary local choreography, mundane props, incidental reactions, and short natural dialogue only when they concretely realize CURRENT BEAT and do not create a new plot development.
- Broad everyday activity should be visually legible and reach a natural local completion when possible.

Result: the model produced a coherent full domestic breakfast scene with Amy, Will, and Amber and did **not** leak the zombie attack into the segment. It chose pancakes/juice rather than the gold's eggs, which is acceptable evidence for the architectural capability but also shows that gold comparison must remain behavioral/fuzzy rather than literal detail matching when the source never specified the detail.

## Correction to previous majority interpretation

Do not optimize ARC allocation merely to make its beat numbering resemble gold. The source says the majority is zombie killing, so the deterministic majority rule is valid source fidelity. Gold prompts are behavioral quality targets, not string or exact decomposition targets. The real current failure is insufficient local realization inside an assigned beat, not that ARC/beat numbering differs from gold.

## Next focused production change

Change only the Request-1 Director semantic boundary:

- retain hard CURRENT BEAT / NEXT BEAT isolation;
- continue forbidding new plot events, future-beat setup, unsupported major state changes, new characters, transformations, mythology, etc.;
- allow **local cinematic staging** needed to concretely realize the current beat: ordinary choreography, mundane props, inherent participants, incidental reactions, short natural dialogue, and camera movement;
- for broad activity beats, prefer a visually legible mini-progression and natural local completion instead of merely restating the beat sentence.

Do not loosen the Request-2 H3 formatter. Request 2 should still faithfully format the RAW SCENE without inventing additional content. Creativity belongs in Request 1, not both stages.

After the focused change: add prompt-regression tests, run them locally, then rerun Amy acceptance and compare Segment 1 first before examining later segments.
