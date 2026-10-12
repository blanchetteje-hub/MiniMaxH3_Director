import copy
import json
from pathlib import Path

import minimax


FIXTURE = (
    Path(__file__).parent
    / "acceptance"
    / "fixtures"
    / "tavern_job33_pre_director"
    / "replay.json"
)


def _fixture_parts():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return (
        fixture,
        copy.deepcopy(fixture["pre_director"]["world_state"]),
        copy.deepcopy(fixture["pre_director"]["location_state"]),
        fixture["inputs"]["subject_definitions"],
    )


def _request1_user_text(world_state, location_state, subject_definitions, references=None):
    messages, _estimated, _recent = minimax.build_generation_messages(
        director_rules="Director rules.",
        story="A short story.",
        beats=["The task is completed."],
        completed_beat_ids=set(),
        recent_results=[],
        current_segment=1,
        total_segments=1,
        segment_length=8,
        total_length=8,
        subject_definitions=subject_definitions,
        static_setting_description="A stone room with a counter and table.",
        world_state=world_state,
        canonical_location_state=location_state,
        character_references=references or {},
    )
    return messages[1]["content"]


def test_subjects_section_keeps_canonical_numbering_and_picture_refs_only():
    fixture, state, location_state, definitions = _fixture_parts()
    user_text = _request1_user_text(state, location_state, definitions)
    subjects = user_text.split("SUBJECTS:\n", 1)[1].split("\n\n", 1)[0]

    assert "<Subject 1> Amy; <Picture 1>" in subjects
    assert "<Subject 267280715056018> Goblin" in subjects
    assert "(S267280715056018)" not in subjects
    assert "unknown" not in subjects
    assert "confident woman" not in subjects
    assert "canonical clothing" not in subjects
    assert fixture["pre_director"]["world_state"]["subjects"]


def test_subject_locations_are_compact_and_use_only_explicit_posture():
    _fixture, state, location_state, definitions = _fixture_parts()
    amy = next(subject for subject in state["subjects"].values() if subject["name"] == "Amy")
    amy["posture"] = "standing"
    user_text = _request1_user_text(state, location_state, definitions)
    locations = user_text.split("SUBJECT LOCATIONS (WorldState):\n", 1)[1].split("\n\n", 1)[0]

    assert "Amy: standing on tavern floor" in locations
    assert "Elf:" not in locations
    assert "Dragon-shaped creature:" not in locations
    assert "at the tavern's wooden floor" not in user_text


def test_wardrobe_reference_suppresses_only_a_matching_current_wardrobe():
    _fixture, state, location_state, definitions = _fixture_parts()
    amy = next(subject for subject in state["subjects"].values() if subject["name"] == "Amy")
    current_upper = amy["wardrobe"]["upper"][0]["garment"]
    current_other = amy["wardrobe"]["other"][0]["garment"]
    definitions += "\n<Picture 2> references only the clothing that Amy is currently wearing."
    matching_reference = {
        "Amy": {
            "picture_number": 2,
            "image_name": "amy-outfit.png",
            "authority": "clothing_only",
            "wardrobe": {"upper": current_upper, "other": current_other},
        }
    }
    matching_text = _request1_user_text(
        state, location_state, definitions, matching_reference,
    )
    wardrobe_section = matching_text.split(
        "WARDROBE (current WorldState", 1
    )[1].split("\n\n", 1)[0]
    assert "- Amy:" not in wardrobe_section

    matching_reference["Amy"]["wardrobe"]["upper"] = "outdated red coat"
    outdated_text = _request1_user_text(
        state, location_state, definitions, matching_reference,
    )
    assert "Amy: upper:" in outdated_text
    assert "outdated red coat" not in outdated_text
    assert "current WorldState overrides older reference clothing" in outdated_text


def test_static_positions_do_not_replace_dynamic_subject_or_prop_state():
    _fixture, state, location_state, definitions = _fixture_parts()
    amy = next(subject for subject in state["subjects"].values() if subject["name"] == "Amy")
    counter_id = next(prop_id for prop_id, prop in state["props"].items() if prop["name"] == "counter")
    amy["support_id"] = counter_id
    amy["posture"] = "standing"
    goblin_id = next(key for key, subject in state["subjects"].items() if subject["name"] == "Goblin")
    cloth_id = next(prop_id for prop_id, prop in state["props"].items() if "cloth" in prop["name"])
    state["props"][cloth_id]["name"] = "chipped mug"
    state["props"][cloth_id]["placement"] = {"kind": "held", "subject_id": goblin_id}

    user_text = _request1_user_text(state, location_state, definitions)
    assert "Amy: standing on counter" in user_text
    assert "back table: northwest corner" in user_text
    assert "back table: on tavern floor" not in user_text
    assert "chipped mug: held by Goblin" in user_text
    assert "counter: east side" in user_text


def test_unknown_subject_and_prop_locations_are_not_filled_in():
    _fixture, state, location_state, definitions = _fixture_parts()
    dragon_id = next(
        key for key, subject in state["subjects"].items()
        if subject["name"] == "Dragon-shaped creature"
    )
    state["subjects"][dragon_id]["presence"] = "unknown"
    state["subjects"][dragon_id]["location_id"] = "unknown"
    cloth_id = next(prop_id for prop_id, prop in state["props"].items() if "cloth" in prop["name"])
    state["props"][cloth_id]["placement"] = {"kind": "unknown"}

    user_text = _request1_user_text(state, location_state, definitions)
    locations = user_text.split("SUBJECT LOCATIONS (WorldState):\n", 1)[1].split("\n\n", 1)[0]
    props = user_text.split("PROPS:\n", 1)[1].split("\n\n", 1)[0]
    assert "Dragon-shaped creature:" not in locations
    assert "cloth soaked in ale-scented oil" in props
    assert "cloth soaked in ale-scented oil:" not in props
    assert "held by" not in props
