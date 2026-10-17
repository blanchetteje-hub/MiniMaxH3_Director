import copy

import pytest

import minimax
from world_state import (
    empty_world_state,
    register_explicit_persistent_props,
    seed_canonical_static_location_state,
)


def surface_world():
    state = empty_world_state("surface-alias")
    state, origin = seed_canonical_static_location_state(
        state, {"location": {"name": "Hill"}, "anchors": [], "objects": []})
    state, destination = seed_canonical_static_location_state(
        state, {"location": {"name": "Underground chamber"}, "anchors": [], "objects": []})
    state = register_explicit_persistent_props(state, [{
        "name": "mossy floor", "kind": "support", "mobility": "fixed",
        "location_id": destination, "needed_for_state": True,
        "reason": "A registered floor within the chamber.",
    }])
    return state, origin, destination


def test_selector_surface_resolves_existing_place_without_mutating_world():
    state, origin, destination = surface_world()
    before = copy.deepcopy(state)
    result = minimax.resolve_scene_location_destination(state, origin, {
        "classification": "transitioning", "location_name": "the mossy floor below",
    })
    assert result["destination_location_id"] == destination
    assert result["requires_registration"] is False
    assert state == before


def test_selector_surface_with_multiple_owners_is_rejected():
    state, origin, _ = surface_world()
    fixture = copy.deepcopy(next(iter(state["props"].values())))
    fixture["placement"]["location_id"] = origin
    state["props"]["another_floor"] = fixture
    with pytest.raises(ValueError, match="ambiguous canonical owners"):
        minimax.resolve_world_state_location_alias(state, "the mossy floor below")


def test_movable_object_does_not_define_a_location_alias():
    state, _, _ = surface_world()
    next(iter(state["props"].values()))["mobility"] = "movable"
    assert minimax.resolve_world_state_location_alias(state, "mossy floor") is None


def test_surface_named_for_a_cave_remains_a_surface_not_a_portal():
    state, _, destination = surface_world()
    fixture = next(iter(state["props"].values()))
    fixture["name"] = "mossy cave floor"
    assert minimax._is_connection_fixture(fixture) is False
    assert minimax.resolve_world_state_location_alias(state, "mossy cave floor") == destination


def test_movable_portal_named_prop_cannot_define_canonical_connectivity():
    state, _, _ = surface_world()
    fixture = next(iter(state["props"].values()))
    fixture["name"] = "cave entrance"
    fixture["mobility"] = "movable"
    assert minimax.matching_connection_fixture_ids(state, "cave") == []
