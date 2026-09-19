from __future__ import annotations

import os
import pytest

from cases import ALL_CASES
from llama_client import LLMError, call_llama, get_model_settings, normalize_result
from prompt_under_test import build_messages


def _selected_cases():
    split = os.environ.get("H3_BENCHMARK_SPLIT", "all").lower()

    if split == "smoke":
        # Two cases per story: one valid and one invalid.
        return [
            c for c in ALL_CASES
            if c.beat_number in (1, 14)
        ]
    if split == "train":
        # First 15 stories = 300 cases.
        train_slugs = {c.story_slug for c in ALL_CASES[:15 * 20]}
        return [c for c in ALL_CASES if c.story_slug in train_slugs]
    if split == "holdout":
        # Last 5 stories = 100 cases.
        train_slugs = {c.story_slug for c in ALL_CASES[:15 * 20]}
        return [c for c in ALL_CASES if c.story_slug not in train_slugs]
    if split == "all":
        return list(ALL_CASES)

    raise RuntimeError(
        "H3_BENCHMARK_SPLIT must be smoke, train, holdout, or all"
    )


CASES = _selected_cases()


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda c: f"{c.story_slug}-beat-{c.beat_number:02d}",
)
def test_validator_prompt(case):
    settings = get_model_settings()
    raw = call_llama(build_messages(case, settings))
    valid, issue = normalize_result(raw)
    assert isinstance(issue, str), f"Issue must be a string: {raw!r}"

    assert valid == case.expected_valid, (
        f"{case.story_title}, beat {case.beat_number}: "
        f"expected valid={case.expected_valid}, got valid={valid}; "
        f"model issue={issue!r}; "
        f"candidate={case.candidate_beat!r}"
    )
