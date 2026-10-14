# Canonical clothing to WorldState

Canonical per-subject outfit extraction produces a complete prose description. The
`clothing_state_extractor` (SMART_EXTRACTOR_LLM_SETTINGS) converts this description
into all four WorldState slots: `upper`, `lower`, `footwear`, and `other`.

- Preserve garment identity, color, material, condition, and coverage.
- Full-body garments (e.g. dresses, robes, jumpsuits) retain the garment identity
  in both upper and lower; do not turn sleeves or hems into standalone garments.
- The canonical clothing text is retained alongside `clothing_state` in the
  character canon. The resulting structured slots seed initial WorldState.
- On unusable conversion, preserve the entire canonical outfit in `other`
  instead of using the lossy punctuation-based splitter. `N/A` for a slot means
  not specified, not proof of nudity.
- Later accepted wardrobe changes and rendered wardrobe observations retain
  their existing precedence; canonical clothing is only the initial seed.
- Identity references and per-segment clothing references should use current
  WorldState clothing rather than reasserting stale original outfits.

Regressions: `tests/test_clothing_state_extractor.py` covers full-body garments,
unusable converter output, and legacy canon compatibility.

This implementation was developed on an isolated `clothing-state-extractor`
branch while the retry/failure-policy changes were being committed independently
to `multi-location-support`. Integrate carefully before using in local runs.
