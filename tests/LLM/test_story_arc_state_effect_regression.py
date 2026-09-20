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
                    "state_effects": [
                        {
                            "op": "set_item_state",
                            "entity": "shotgun",
                            "owner": "Amy",
                            "value": "equipped",
                        }
                    ],
                },
                {
                    "id": "E2",
                    "event": "Amy retrieves the shotgun from the hall closet and equips it.",
                    "beat_number": 4,
                    "state_effects": [
                        {
                            "op": "set_item_state",
                            "entity": "shotgun",
                            "owner": "Amy",
                            "value": "equipped",
                        }
                    ],
                },
            ],
        }]
    },
    expected_valid=False,
    expected_issues=("state effect belongs to the later retrieval event",),
)


def _coverage_arc(event, end_state, effect=None):
    required_event = {
        "id": "E1",
        "event": event,
        "beat_number": 1,
    }
    if effect is not None:
        required_event["state_effects"] = [effect]
    return {
        "phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Complete the stated event.",
            "broad_progression": event,
            "characters_introduced": [],
            "location": "The stated scene.",
            "required_end_state": end_state,
            "required_events": [required_event],
        }]
    }


def _coverage_case(case_id, event, end_state, effect, expected_valid):
    return StoryArcCase(
        case_id=case_id,
        split="focused",
        theme="horror",
        beat_count=1,
        story_title=case_id.replace("_", " ").title(),
        story=event,
        subject_information="N/A",
        beat_instructions="Preserve the explicitly stated event and persistent result.",
        proposed_arc=_coverage_arc(event, end_state, effect),
        expected_valid=expected_valid,
        expected_issues=("persistent state coverage",) if not expected_valid else (),
    )


PERSISTENT_STATE_COVERAGE_CASES = (
    _coverage_case(
        "missing_barrier_state",
        "Amy locks the basement door.",
        "The basement door is locked.",
        None,
        False,
    ),
    _coverage_case(
        "correct_barrier_state",
        "Amy locks the basement door.",
        "The basement door is locked.",
        {"op": "set_barrier_state", "entity": "basement door", "value": "locked"},
        True,
    ),
    _coverage_case(
        "missing_location_state",
        "Will enters the basement.",
        "Will is in the basement.",
        None,
        False,
    ),
    _coverage_case(
        "correct_location_state",
        "Will enters the basement.",
        "Will is in the basement.",
        {"op": "set_location", "entity": "Will", "value": "basement"},
        True,
    ),
    _coverage_case(
        "missing_equipment_state",
        "Amy equips the pistol.",
        "Amy has the pistol equipped.",
        None,
        False,
    ),
    _coverage_case(
        "correct_equipment_state",
        "Amy equips the pistol.",
        "Amy has the pistol equipped.",
        {"op": "set_item_state", "entity": "pistol", "owner": "Amy", "value": "equipped"},
        True,
    ),
    _coverage_case(
        "missing_terminal_threat_state",
        "The zombie is killed.",
        "The zombie is dead.",
        None,
        False,
    ),
    _coverage_case(
        "correct_terminal_threat_state",
        "The zombie is killed.",
        "The zombie is dead.",
        {"op": "set_threat_state", "entity": "zombie", "value": "dead"},
        True,
    ),
    _coverage_case(
        "missing_clothing_state",
        "Amy is wearing a black tank top.",
        "Amy is wearing a black tank top.",
        None,
        False,
    ),
    _coverage_case(
        "temporary_action_without_state",
        "Amy swings the katana at a zombie.",
        "Amy swings the katana at a zombie.",
        None,
        True,
    ),
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


def test_story_arc_prompt_calls_out_persistent_state_coverage():
    prompt = "\n".join(
        message["content"]
        for message in minimax.build_macro_arc_validation_messages(
            PERSISTENT_STATE_COVERAGE_CASES[0].story,
            PERSISTENT_STATE_COVERAGE_CASES[0].proposed_arc,
        )
    ).casefold()
    assert "check persistent state coverage" in prompt
    assert "same event" in prompt
    assert "persistent change or result" in prompt
    assert "temporary actions" in prompt
    for operation in (
        "set_location", "set_item_state", "set_barrier_state", "set_threat_state",
        "set_object_state", "set_containment", "set_condition", "set_clothing",
    ):
        assert operation in prompt


def test_persistent_state_coverage_regression_cases_have_expected_contract():
    assert len(PERSISTENT_STATE_COVERAGE_CASES) == 10
    assert [case.expected_valid for case in PERSISTENT_STATE_COVERAGE_CASES] == [
        False, True, False, True, False, True, False, True, False, True,
    ]


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.environ.get("H3_RUN_STORY_ARC_REGRESSIONS") != "1",
    reason="set H3_RUN_STORY_ARC_REGRESSIONS=1 to contact the configured local LLM",
)
@pytest.mark.parametrize(
    "case",
    PERSISTENT_STATE_COVERAGE_CASES,
    ids=lambda case: case.case_id,
)
def test_story_arc_persistent_state_coverage(case):
    raw = call_llama(build_messages(case, get_model_settings()))
    valid, issues = normalize_arc_result(raw)

    assert valid == case.expected_valid, (
        f"{case.case_id}: expected valid={case.expected_valid}, got valid={valid}; "
        f"model issues={issues!r}"
    )


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.environ.get("H3_RUN_STORY_ARC_REGRESSIONS") != "1",
    reason="set H3_RUN_STORY_ARC_REGRESSIONS=1 to contact the configured local LLM",
)
def test_story_arc_rejects_effect_owned_by_later_retrieval_event():
    raw = call_llama(build_messages(FOCUSED_CASE, get_model_settings()))
    valid, issues = normalize_arc_result(raw)

    assert valid is False, f"expected INVALID, got VALID; issue={issues!r}"
