from __future__ import annotations

import os

import pytest

from tests.LLM.llama_client import call_llama, get_model_settings, normalize_result
from tests.LLM.prompt_under_test import build_validation_messages


STATE_EFFECT_REGRESSION_CASES = (
    {
        "name": "missing_transition",
        "story": "An operator is in the upper hall while the chamber hatch is locked.",
        "phase_goal": "Track the hostile units in the facility.",
        "previous": "The operator is in the upper hall; the chamber hatch is locked.",
        "state": {
            "characters": {"operator": {"location": "upper_hall"}},
            "environment": {"barriers": {"chamber_hatch": {"status": "locked"}}},
        },
        "job": "The hostile units approach the operator in the upper hall.",
        "candidate": (
            "Hostile units approach the operator in the upper hall; the chamber "
            "hatch remains locked, and no one opens or unlocks it."
        ),
        "effects": [
            {
                "id": "E1",
                "state_effects": {
                    "environment": {
                        "barriers": {"chamber_hatch": {"status": "open"}}
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
