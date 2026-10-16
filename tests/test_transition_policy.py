"""Transition staging stays source owned while H3 supplies incidental travel."""
import pytest

import minimax


def generation_context(transition=""):
    return minimax.build_generation_messages(
        director_rules="Director rules", story="unused",
        beats=['The traveler crosses the doorway, drops a weapon, and says "Go!".'],
        completed_beat_ids=set(), recent_results=[], current_segment=1,
        total_segments=1, segment_length=8, total_length=8,
        subject_definitions="<Subject 1> Traveler",
        assigned_source='The traveler drops a weapon while crossing and says "Go!".',
        location_transition_context=transition,
    )[0]


@pytest.mark.parametrize("origin,destination", [
    ("hall", "courtyard"), ("ridge", "valley"), ("shaft entrance", "shaft floor"),
])
def test_transition_policy_reaches_creative_stage_without_journey_invention(origin, destination):
    context = minimax.build_location_transition_context(origin, destination)
    creative = minimax.build_director_raw_scene_creative_messages(
        generation_context(context), 8,
    )
    user = creative[1]["content"]
    assert f"WorldState position in {origin}" in user
    assert f"reach {destination}" in user
    assert "Do not invent intermediate hand or foot movements" in user
    assert "Preserve explicit story-critical actions, prop changes, dialogue, injuries" in user
    assert "Unspecified H3 intermediate movements establish no persistent WorldState facts" in user
    assert 'drops a weapon while crossing and says "Go!"' in user


def test_transition_final_h3_keeps_source_action_and_ordered_environment_references():
    raw = '[Shot 1] <Subject 1> Traveler crosses the doorway, drops a weapon and says <d>Go!</d>. Traveler ends in the courtyard.'
    final = minimax.build_h3_prompt(
        {"detailed_description": raw, "overall_soundscape": "A weapon clatters.",
         "non_diegetic_music": "N/A"},
        "<Subject 1> Traveler", segment_number=1, conditioning_mode="initial",
        accepted_raw_scene=raw,
    )
    final = minimax.inject_location_transition_into_h3_prompt(
        final, "Hall", "A stone hall.", "Courtyard", "An open courtyard.",
        has_preceding_guide=False,
    )
    assert final.index("<Video 1> is") < final.index("<Video 2> is")
    assert "ORIGIN environment at the start" in final
    assert "DESTINATION environment at the end" in final
    assert "establish the required destination/end state" in final
    assert "Realize the movement naturally" in final
    assert 'drops a weapon and says <d>Go!</d>' in final
    assert "Traveler ends in the courtyard" in final
    assert "show the physical transition" not in final


def test_same_location_director_and_h3_receive_no_transition_policy():
    messages = generation_context()
    assert "LOCATION TRANSITION FOR THIS SEGMENT" not in messages[1]["content"]
    assert "Do not invent intermediate" not in messages[1]["content"]
    final = minimax.inject_location_reference_into_h3_prompt(
        'detailed_description: [Shot 1] Traveler raises a hand.',
        'A stone hall.', conditioning_mode="initial",
    )
    assert "<Video 1> is the persistent LOCATION REFERENCE" in final
    assert "<Video 2>" not in final
    assert "Realize the movement naturally" not in final
    assert "Traveler raises a hand." in final


def test_transition_raw_repair_retains_endpoint_policy_and_story_action():
    policy = minimax.build_location_transition_context("hall", "courtyard")
    messages = minimax.build_director_raw_scene_repair_messages(
        "Traveler crosses and drops a weapon.", ["Resolve a physical conflict."],
        current_beat="Traveler crosses and drops a weapon.",
        location_transition_context=policy,
    )
    assert policy in messages[1]["content"]
    assert "Traveler crosses and drops a weapon." in messages[1]["content"]
    same_location = minimax.build_director_raw_scene_repair_messages("Traveler waits.", [])
    assert "LOCATION TRANSITION FOR THIS SEGMENT" not in same_location[1]["content"]
