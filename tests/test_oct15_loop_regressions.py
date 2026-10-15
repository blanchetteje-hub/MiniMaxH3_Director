"""Regressions for the 2026-10-15 Alice Segment-1 restart loop."""
from unittest import mock

import pytest
import minimax
from world_state import (
    new_world_state, seed_canonical_static_location_state,
    register_explicit_persistent_props,
)


def alice_world_state():
    state = new_world_state({
        "source_sha256": "alice-transition-regression",
        "subjects": {"1": {"subject_id": 1, "name": "Alice",
                           "gender": "female", "picture_ids": []}},
    })
    state, location_id = seed_canonical_static_location_state(
        state, {"location": {"name": "front step of Alice's house"},
                "anchors": [], "objects": []},
    )
    state = register_explicit_persistent_props(state, [{
        "name": "left wooden post", "kind": "fixture", "mobility": "fixed",
        "needed_for_state": True, "reason": "A fixed support", "location_id": location_id,
    }])
    return state


def test_first_segment_transition_uses_origin_for_h3_start():
    bundle = {
        "location_name": "dark rabbit hole",
        "location_transition": {
            "classification": "transitioning",
            "origin_location_id": "origin",
            "destination_location_id": "hole",
        },
    }
    metadata = {"starting_location": "incorrect fallback",
                "location_contexts": {"origin": {"name": "front step of Alice's house"}}}
    assert minimax._h3_segment_starting_location(1, bundle, metadata) == "front step of Alice's house"
    assert minimax._h3_segment_starting_location(2, bundle, metadata) == ""
    with pytest.raises(ValueError, match="origin context"):
        minimax._h3_segment_starting_location(1, bundle, {})


def test_nontransition_h3_start_uses_current_location():
    assert minimax._h3_segment_starting_location(
        1, {"location_name": "Tavern", "location_transition": {}},
        {"starting_location": "other"},
    ) == "Tavern"


def test_registered_subject_not_rejected_for_possessive_place_label():
    state = alice_world_state()
    assert minimax._is_registered_non_subject_candidate(
        "Alice", state, "Alice walks from the front step of Alice's house."
    ) is False


def test_registered_fixed_prop_candidate_is_ignored_without_retry():
    state = alice_world_state()
    response = {"props": [{
        "name": "left wooden post", "kind": "object", "mobility": "movable",
        "initial_location": None, "initial_holder": "Alice", "support_name": None,
        "contents": [],
        "capabilities": {"container": "unknown", "consumable": "unknown",
                         "openable": "unknown", "lockable": "unknown"},
        "reason": "Alice grips the post.",
        "evidence": "grabs the left wooden post with both hands",
    }]}
    with mock.patch("minimax.console_log"):
        assert minimax.parse_current_segment_persistent_prop_result(
            response, "Alice grabs the left wooden post with both hands.", "", state
        ) == []
        calls = []
        def llm_request(*args, **kwargs):
            calls.append(1)
            return response
        assert minimax.extract_current_segment_persistent_props(
            "Alice grabs the left wooden post with both hands.", "", state,
            llm_request=llm_request,
        ) == []
    assert len(calls) == 1


def test_fixed_fixture_contact_is_not_reinterpreted_as_pickup():
    state = alice_world_state()
    assert minimax._event_refers_to_fixed_fixture(state, "wooden post")
    event = {"action": "take", "actor": "Alice", "object": "wooden post",
             "source": None, "destination": "hands",
             "relation": "grabs it for balance", "result": None}
    with mock.patch("minimax.console_log"):
        assert minimax._translate_world_state_event(
            state, event, "Alice grabs the wooden post for balance.", 1, 1
        ) == []
