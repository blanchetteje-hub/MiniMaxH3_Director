# Story Arc Validator Benchmark

This adds a separate 100-case benchmark for the **story arc validator** while
reusing the existing `tests/LLM/llama_client.py` and model profiles.

## Files added

- `story_arc_cases.py` — deterministic seeded generation of 100 new sci-fi,
  horror, and high-fantasy story/arc cases.
- `story_arc_prompt_under_test.py` — the story-arc validator prompt Codex should tune.
- `score_story_arc_prompt.py` — scoring loop.
- `test_story_arc_prompt_benchmark.py` — fixture contract + opt-in live pytest benchmark.

No existing beat-validator benchmark files need to change.

## Case layout

- **Smoke: 10**
  - 5 × 10-beat arcs
  - 5 × 20-beat arcs
- **Train: 80**
  - 79 arcs ranging from 10 through 30 beats
  - 1 × 50-beat arc
- **Holdout: 10**
  - 8 × 20-beat arcs
  - 1 × 30-beat arc
  - 1 × 50-beat arc

The full set is balanced: 50 valid / 50 invalid.

Invalid cases rotate through semantic failures including source-event omissions,
wrong order, wrong ending, unsupported inventions, phase collapse,
required-end-state coverage, dependency errors, missing/misowned/unrelated
state effects, and state-effect value contradictions.

## KISS Codex loop

**Edit only `story_arc_prompt_under_test.py` while tuning.**

1. Run smoke:
   `python -m tests.LLM.score_story_arc_prompt --split smoke`
2. Make one small prompt change.
3. Run smoke again.
4. Periodically run train:
   `python -m tests.LLM.score_story_arc_prompt --split train`
5. Do not tune continuously against holdout.
6. When train is strong, run:
   `python -m tests.LLM.score_story_arc_prompt --split holdout`
7. Final check:
   `python -m tests.LLM.score_story_arc_prompt --split all`

Do **not** change `story_arc_cases.py`, expected validity, or the scorer to make
the prompt pass.

When the benchmark reaches the desired result, port the tuned validator wording
back into production `build_macro_arc_validation_messages()`.

## Pytest

Fixture contract only:

`pytest -q tests/LLM/test_story_arc_prompt_benchmark.py -k fixture_contract`

Live smoke benchmark:

`H3_RUN_STORY_ARC_BENCHMARK=1 H3_STORY_ARC_BENCHMARK_SPLIT=smoke pytest -q tests/LLM/test_story_arc_prompt_benchmark.py`

Use `train`, `holdout`, or `all` for the split variable as needed.

## Output contract

The validator must return exactly one JSON object:

`{"valid": true, "issues": []}`

or:

`{"valid": false, "issues": ["short concrete blocking issue"]}`

Scoring uses the boolean validity result. The fixture diagnostic labels are
metadata for failure analysis only and are never shown to the model.
