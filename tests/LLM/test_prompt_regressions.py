from __future__ import annotations

import os

import pytest

from tests.LLM.llama_client import call_llama, get_model_settings, normalize_result
from tests.LLM.prompt_under_test import build_messages
from tests.LLM.regression_cases import REGRESSION_CASES


RUN_LIVE_REGRESSIONS = os.environ.get("H3_RUN_LLM_REGRESSIONS") == "1"


def test_regression_cases_preserve_validator_contract() -> None:
    settings = get_model_settings()

    for case in REGRESSION_CASES:
        messages = build_messages(case, settings)
        assert [message["role"] for message in messages] == ["system", "user"]
        prompt = "\n".join(message["content"] for message in messages)
        assert '"valid": true' in prompt
        assert '"issue": ""' in prompt
        assert "terminal or exhaustive" in prompt
        assert "STORY" not in prompt
        assert "PHASE GOAL" not in prompt


@pytest.mark.skipif(
    not RUN_LIVE_REGRESSIONS,
    reason="set H3_RUN_LLM_REGRESSIONS=1 to contact the configured local LLM",
)
@pytest.mark.live_llm
@pytest.mark.parametrize(
    "case",
    REGRESSION_CASES,
    ids=lambda case: case.story_slug,
)
def test_validator_prompt_regression(case) -> None:
    raw = call_llama(build_messages(case, get_model_settings()))
    valid, issue = normalize_result(raw)

    assert isinstance(issue, str)
    assert valid == case.expected_valid, (
        f"{case.story_title}: expected valid={case.expected_valid}, "
        f"got valid={valid}; issue={issue!r}; candidate={case.candidate_beat!r}"
    )
