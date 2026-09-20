from __future__ import annotations

import os

import pytest

import minimax
from tests.LLM.llama_client import call_llama, get_model_settings
from tests.LLM.score_story_arc_prompt import normalize_arc_result
from tests.LLM.story_arc_cases import StoryArcCase
from tests.LLM.story_arc_prompt_under_test import build_messages


FOCUSED_CASE = StoryArcCase(
    case_id="focused_state_effect_wrong_event_ownership",
    split="focused",
    theme="horror",
    beat_count=4,
    story_title="Breakfast Before the Armory",
    story=(
        "Amy, wearing a blue sweater and dark trousers, cooks breakfast in the "
        "kitchen. Later, Amy retrieves the named shotgun from the hall closet "
        "and equips it before leaving."
    ),
    subject_information="Amy is an adult woman wearing a blue sweater and dark trousers.",
    beat_instructions="Preserve the source order and assign the two source events to beats.",
    proposed_arc={
        "phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 4,
            "narrative_purpose": "Prepare the character and retrieve the equipment.",
            "broad_progression": "Amy cooks, then retrieves and equips the shotgun.",
            "characters_introduced": ["Amy"],
            "location": "Kitchen and hall closet",
            "required_end_state": "Amy is equipped with the shotgun.",
            "required_events": [
                {
                    "id": "E1",
                    "event": "Amy cooks breakfast in the kitchen.",
                    "beat_number": 1,
                    "state_effects": {
                        "characters": {
                            "Amy": {"equipped_objects": ["shotgun"]}
                        }
                    },
                },
                {
                    "id": "E2",
                    "event": "Amy retrieves the shotgun from the hall closet and equips it.",
                    "beat_number": 4,
                    "state_effects": {
                        "characters": {
                            "Amy": {"equipped_objects": ["shotgun"]}
                        }
                    },
                },
            ],
        }]
    },
    expected_valid=False,
    expected_issues=("state effect belongs to the later retrieval event",),
)


def test_story_arc_prompt_calls_out_wrong_event_state_effect_ownership():
    prompt = "\n".join(
        message["content"]
        for message in minimax.build_macro_arc_validation_messages(
            FOCUSED_CASE.story,
            FOCUSED_CASE.proposed_arc,
            subject_information=FOCUSED_CASE.subject_information,
            beat_instructions=FOCUSED_CASE.beat_instructions,
        )
    ).casefold()
    assert "actually establishes" in prompt
    assert "earlier" in prompt
    assert "ordinary setup event" in prompt
    assert "later event also carries the effect" in prompt


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.environ.get("H3_RUN_STORY_ARC_REGRESSIONS") != "1",
    reason="set H3_RUN_STORY_ARC_REGRESSIONS=1 to contact the configured local LLM",
)
def test_story_arc_rejects_effect_owned_by_later_retrieval_event():
    raw = call_llama(build_messages(FOCUSED_CASE, get_model_settings()))
    valid, issues = normalize_arc_result(raw)

    assert valid is False, f"expected INVALID, got VALID; issue={issues!r}"
