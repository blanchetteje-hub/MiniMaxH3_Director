# Pipeline Failure Policy

Pipeline stages use one of three failure categories:

- **REQUIRED** — the segment or requested output depends on a valid result. Keep
  the stage's existing bounded repair/recovery behavior; if it remains invalid,
  do not accept the dependent output. Infrastructure failures always propagate.
- **OPTIONAL** — an enrichment or bookkeeping result may be omitted. After its
  existing local retries are exhausted, log the diagnostic, discard the
  incomplete result, preserve the last valid input/state, and continue. Never
  backstep or restart upstream generation for an optional content failure.
  Cancellation and infrastructure failures still propagate.
- **CONDITIONAL** — behavior depends on run mode, configuration, or an external
  capability. Review its failure policy separately before changing it; this
  task does not change conditional-stage recovery.

## Audited optional stages

- Rendered visual continuity and wardrobe analysis (when enabled by render mode
  and vision cadence): discard an unusable observation; do not rerender a
  completed segment.
- H3 soundscape and music: omit only the failed field, using the existing `N/A`
  fallback.
- Camera refinement: retain the last valid timed scene without camera tags.
- Pronoun resolution: retain the last valid RAW scene.
- Subject visibility/appearance extraction: discard incomplete candidates;
  retain accepted RAW and previously registered identity/wardrobe facts.
- WorldState event extraction and translation: discard the whole failed event
  batch and preserve opening WorldState.
- Pre-Director prop discovery: reject the whole invalid candidate batch and
  retain already registered props.

The normal creative RAW, blocking RAW validators, timing validation, accepted
state commit, and a requested render remain required dependencies. Mode-gated
stages not listed above are conditional and are not changed by this policy.
