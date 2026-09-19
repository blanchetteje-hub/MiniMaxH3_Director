from __future__ import annotations

import os

import pytest

import minimax
from tests.LLM.llama_client import call_llama, get_model_settings, normalize_result


STATE_EFFECT_REGRESSION_CASES = (
    {
        "name": "missing_transition",
        "story": "An operator is in a chamber while the chamber hatch is locked.",
        "phase_goal": "Open the hatch and secure the chamber.",
        "previous": "The operator is in the chamber; the chamber hatch is locked.",
        "state": {
            "characters": {"operator": {"location": "chamber"}},
            "environment": {"barriers": {"chamber_hatch": {"status": "locked"}}},
        },
        "job": "The operator opens the chamber hatch.",
        "candidate": "Hostile units approach the operator elsewhere in the facility.",
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
        "phase_goal": "Stop both hostile units.",
        "previous": "Two hostile units are active in the loading bay.",
        "state": {
            "threats": {
                "unit_3": {"status": "active"},
                "unit_4": {"status": "active"},
            }
        },
        "job": "The operator stops both hostile units.",
        "candidate": "The operator destroys unit_3 but only wounds unit_4.",
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
        "phase_goal": "Stop the hostile unit.",
        "previous": "The facility entrance is intact and the hostile unit is active.",
        "state": {
            "environment": {
                "barriers": {
                    "front_hatch": {"status": "closed", "condition": "intact"}
                }
            },
            "threats": {"unit_1": {"status": "active"}},
        },
        "job": "The operator stops unit_1.",
        "candidate": "The hostile unit kicks down the front hatch.",
        "effects": [
            {"id": "E1", "state_effects": {"threats": {"unit_1": {"status": "destroyed"}}}}
        ],
    },
    {
        "name": "unmodeled_structure_damage",
        "story": "An operator must stop a hostile unit inside a facility.",
        "phase_goal": "Stop the hostile unit.",
        "previous": "The facility ceiling is intact and the hostile unit is active.",
        "state": {
            "environment": {"structures": {"ceiling": {"condition": "intact"}}},
            "threats": {"unit_1": {"status": "active"}},
        },
        "job": "The operator stops unit_1.",
        "candidate": "The hostile unit breaks through the ceiling.",
        "effects": [
            {"id": "E1", "state_effects": {"threats": {"unit_1": {"status": "destroyed"}}}}
        ],
    },
)


def _messages(case):
    return minimax.build_beat_validation_messages(
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
