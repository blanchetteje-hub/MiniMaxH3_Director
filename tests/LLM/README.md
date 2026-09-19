# MiniMax H3 Prompt Benchmark

This is a local regression suite for tuning a small-model beat validator.

It contains:

- 20 different story premises
- 20 beat cases per story
- 400 total model calls for the full suite
- correct and deliberately broken beats
- deterministic incoming state built from the correct story path
- fixed issue labels
- smoke / train / holdout / all splits

## Files

- `cases.py` — 20 stories and all 400 generated benchmark cases.
- `prompt_under_test.py` — **the prompt Codex should edit**.
- `llama_client.py` — OpenAI-compatible LLM client.
- `test_prompt_benchmark.py` — pytest suite.
- `score_prompt.py` — easier scoring loop for Codex.
- `skeptic_prompt.py` — short generic second-pass prompt for primary VALID results.

## Endpoint

Defaults to:

    http://127.0.0.1:1234/v1/chat/completions

Override as needed:

    export H3_LLM_URL=http://127.0.0.1:1234/v1/chat/completions
    export H3_LLM_MODEL=your-model-name
    export H3_LLM_TIMEOUT=120
    export H3_LLM_TEMPERATURE=0

The benchmark selects settings by model. Minstral keeps the current settings:
`repeat_penalty=1.1`, `top_p=0.95`, and `min_p=0.05`. Qwen uses temperature 0,
`repeat_penalty=1.15`, default `top_p`/`top_k`/`min_p`, thinking off, its built-in
Jinja chat template, an 8K context, and a user-only prompt layout. Start the
Qwen llama.cpp server with `--jinja` and an 8K context window.

The scoring harness uses the local llama.cpp endpoint above. Override it with
`H3_LLM_URL` if needed.

The benchmark uses the local llama.cpp endpoint for all requests.

## First run

Start small:

    python score_prompt.py --split smoke

To evaluate the frozen primary with the optional skeptic pass:

    python score_prompt.py --split train --mode primary
    python score_prompt.py --split train --mode primary+skeptic

That is only 40 calls: two cases from each story.

Then:

    python score_prompt.py --split train

The training split is the first 15 stories = 300 cases.

When a prompt improves, verify against stories Codex has not been tuning against:

    python score_prompt.py --split holdout

The holdout split is the last 5 stories = 100 cases.

Finally:

    python score_prompt.py --split all

Or use pytest:

    H3_BENCHMARK_SPLIT=smoke pytest -q
    H3_BENCHMARK_SPLIT=train pytest -q
    H3_BENCHMARK_SPLIT=holdout pytest -q
    H3_BENCHMARK_SPLIT=all pytest -q

## Recommended Codex loop

Codex should modify only `build_messages()` in `prompt_under_test.py`.

Suggested workflow:

1. Run `python score_prompt.py --split smoke`.
2. Inspect failures.
3. Make one small prompt change.
4. Run smoke again.
5. Keep the change only if the score improves or fixes failures without regressions.
6. Periodically run `--split train`.
7. Do not tune against holdout continuously.
8. When the training result is strong, run `--split holdout`.
9. Do not modify `cases.py`, expected answers, or the scorer to make the prompt pass.

The full 400-case suite is intentionally expensive. Codex should not run all 400 after every tiny edit.

## Output contract

The model must return:

    {
      "valid": true,
      "issue": ""
    }

or:

    {
      "valid": false,
      "issue": "Short concrete explanation of the problem."
    }

The six labels below remain only as expected diagnostic metadata in the fixtures;
the model does not receive them and validity scoring does not compare them:

- JOB — failed required beat job
- STATE — object, barrier, containment, or location contradiction
- CONTINUITY — dead things returning, cleared threats returning, or invented prior history
- REPEAT — completed action repeated
- UNAUTHORIZED — unsupported important entity, object, or event
- SEQUENCING — later required action performed too early

The benchmark scores whether the returned `valid` boolean matches the expected
validity. The scorer separately reports false negatives, false positives, and the
model's concrete issue text.

## Important design choice

Every benchmark beat receives state produced by the *correct* previous beats.

A deliberately broken candidate is never allowed to corrupt the state of later test cases. This makes every test independent and lets Codex know exactly which prompt change caused a regression.
