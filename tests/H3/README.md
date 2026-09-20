# MiniMax H3 prompt experiments

This is a development-only harness for comparing final H3 prompt strategies
against the same captured segment. It does not change the Director pipeline,
ARC/BEATS, the desktop GUI, or production generation behavior.

## Capture a segment

Run the normal generator with both capture flags:

```text
python3 minimax.py 6 30 0.2 \
  --capture-h3-segment 4 \
  --capture-h3-fixture tests/H3/fixtures/segment_004.json
```

The fixture is written after the selected segment renders successfully. It
contains the Request 1 scene, Request 2 fields, the authoritative opening
state, the exact prompt placed in the ComfyUI prompt node, subject definitions,
source media references, workflow fingerprint, seed, and relevant settings.

## Run an experiment

```text
python3 tests/H3/run_prompt_experiment.py \
  tests/H3/fixtures/segment_004.json
```

Use `--variant A_current` (repeatable) to render a subset. Outputs are written
under `tests/H3/experiments/` unless `--output-dir` is supplied. Each rendered
video has an adjacent `.txt` file containing the exact prompt sent to H3.

`review.json` is intentionally blank and must be completed by a human after
watching the clips. The harness does not score clips, calculate a winner, or
use an LLM judge.

Fixtures refer to existing media rather than copying large videos or workflow
graphs. If a referenced workflow changes after capture, the runner stops before
rendering so comparisons do not silently use different conditions.
