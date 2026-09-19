from __future__ import annotations

import os

import pytest

from tests.LLM.llama_client import call_llama, get_model_settings, normalize_result
from tests.LLM.prompt_under_test import build_validation_messages


STATE_EFFECT_REGRESSION_CASES = (
    {
        "name": "explicit_effect_contradiction",
        "story": "An operator engages two active hostile units in the upper hall.",
        "phase_goal": "Engage both hostile units.",
        "state": {
            "characters": {"operator": {"location": "upper_hall"}},
            "threats": {
                "unit_1": {"status": "active", "location": "upper_hall"},
                "unit_2": {"status": "active", "location": "upper_hall"},
            },
        },
        "previous": "Both hostile units are active in the upper hall.",
        "job": "The operator attacks both hostile units.",
        "candidate": (
            "The operator attacks unit_1 and unit_2. The listed state effects "
            "that they are dead do not occur; both remain active."
        ),
        "effects": [
            {
                "id": "E1",
                "state_effects": {
                    "threats": {
                        "unit_1": {"status": "dead"},
                        "unit_2": {"status": "dead"},
                    }
                },
            }
        ],
    },
    {
        "name": "incomplete_terminal_effect",
        "story": "An operator must stop two hostile units.",
        "phase_goal": "Engage both hostile units in the loading bay.",
        "previous": "Two hostile units are active in the loading bay.",
        "state": {
            "threats": {
                "unit_3": {"status": "active"},
                "unit_4": {"status": "active"},
            }
        },
        "job": "The operator attacks both hostile units.",
        "candidate": (
            "The operator decapitates unit_3 and attacks unit_4; unit_4 remains "
            "active."
        ),
        "effects": [
            {
                "id": "E1",
                "state_effects": {
                    "threats": {
                        "unit_3": {"status": "destroyed"},
                        "unit_4": {"status": "destroyed"},
                    }
                },
            }
        ],
    },
    {
        "name": "unmodeled_barrier_damage",
        "story": "An operator must stop a hostile unit without damaging the facility.",
        "phase_goal": "Defeat the hostile unit at the facility entrance.",
        "previous": "The facility entrance is intact and the hostile unit is active.",
        "state": {
            "environment": {
                "barriers": {
                    "front_hatch": {"status": "closed", "condition": "intact"}
                }
            },
            "threats": {"unit_1": {"status": "active"}},
        },
        "job": "The operator defeats unit_1.",
        "candidate": "The operator destroys unit_1, and the hostile unit kicks down the front hatch.",
        "effects": [
            {"id": "E1", "state_effects": {"threats": {"unit_1": {"status": "destroyed"}}}}
        ],
    },
    {
        "name": "unmodeled_structure_damage",
        "story": "An operator must stop a hostile unit inside a facility.",
        "phase_goal": "Defeat the hostile unit inside the facility.",
        "previous": "The facility ceiling is intact and the hostile unit is active.",
        "state": {
            "environment": {"structures": {"ceiling": {"condition": "intact"}}},
            "threats": {"unit_1": {"status": "active"}},
        },
        "job": "The operator defeats unit_1.",
        "candidate": "The operator destroys unit_1, and the hostile unit breaks through the ceiling.",
        "effects": [
            {"id": "E1", "state_effects": {"threats": {"unit_1": {"status": "destroyed"}}}}
        ],
    },
)


def _messages(case):
    return build_validation_messages(
        story=case["story"],
        phase_goal=case["phase_goal"],
        previous_final_beat=case["previous"],
        current_state=case["state"],
        beat_job=case["job"],
        next_beat_job=None,
        candidate_beat=case["candidate"],
        settings=get_model_settings(),
        assigned_state_effects=case["effects"],
    )


def test_state_effect_regression_prompt_contract():
    for case in STATE_EFFECT_REGRESSION_CASES:
        prompt = "\n".join(message["content"] for message in _messages(case))
        assert "STATE EFFECTS TO COMMIT IF VALID" in prompt
        assert '"id":"E1"' in prompt
        assert "persistent change" in prompt


@pytest.mark.skipif(
    os.environ.get("H3_RUN_LLM_REGRESSIONS") != "1",
    reason="set H3_RUN_LLM_REGRESSIONS=1 to contact the configured local LLM",
)
@pytest.mark.live_llm
@pytest.mark.parametrize("case", STATE_EFFECT_REGRESSION_CASES, ids=lambda case: case["name"])
def test_state_effect_regression(case):
    valid, issue = normalize_result(call_llama(_messages(case)))
    assert valid is False, f"expected INVALID, got VALID; issue={issue!r}"
