"""Opening WorldState footwear cannot silently disappear in Director RAW."""
from unittest import mock

import pytest

import minimax


def opening(*, footwear=None):
    if footwear is None:
        footwear = [{"garment": "simple leather sandals", "condition": "clean"}]
    return {
        "schema_version": 1,
        "props": {},
        "subjects": {
            "subject_1": {
                "name": "Alice", "wardrobe": {"footwear": footwear},
            },
            "subject_2": {
                "name": "Goblin", "wardrobe": {"footwear": "unknown"},
            },
        },
    }


@pytest.mark.parametrize("scene", [
    "Alice stands barefoot on the steps.",
    "At 00:00.000, Alice steps barefoot onto the grass.",
    "At 00:00.000, Barefoot, Alice walks through the garden.",
    "Alice stands barefoot, then takes off her sandals.",
    "Alice removes her coat. Alice stands barefoot.",
    "Alice removes her gloves, then finds sandals. Alice walks barefoot.",
])
def test_rejects_barefoot_before_established_footwear_removal(scene):
    issue = minimax._director_raw_scene_footwear_issue(scene, opening())
    assert "Alice as barefoot" in issue
    assert "WorldState footwear" in issue


@pytest.mark.parametrize("scene", [
    "Alice slips off her sandals. Alice walks barefoot across the grass.",
    "Alice takes off her sandals and then stands barefoot.",
    "Alice removes her sandals, then walks barefoot.",
    "Alice walks on the steps wearing her sandals.",
    'Alice says "I am barefoot." Alice stands on the steps.',
    "Alice watches barefoot children play in the garden.",
    "Alice sees Goblin step barefoot into the room.",
])
def test_allows_explicit_removal_or_non_conflicting_description(scene):
    assert minimax._director_raw_scene_footwear_issue(scene, opening()) == ""


def test_unknown_or_empty_footwear_is_not_assumed_present():
    for footwear in ("unknown", "N/A", []):
        assert not minimax._director_raw_scene_footwear_issue(
            "Alice stands barefoot.", opening(footwear=footwear)
        )


def test_layered_footwear_requires_both_layers_removed():
    state = opening(footwear=[{"garment": "leather boots"}, {"garment": "wool socks"}])
    issue = minimax._director_raw_scene_footwear_issue(
        "Alice removes her boots. Alice walks barefoot.", state
    )
    assert "socks" in issue
    assert not minimax._director_raw_scene_footwear_issue(
        "Alice removes her boots. Alice removes her socks. Alice walks barefoot.", state
    )


def test_existing_physical_entrypoint_rejects_before_llm_or_state_mutation():
    state = opening()
    snapshot = __import__("copy").deepcopy(state)
    llm = mock.Mock(side_effect=AssertionError("Physical LLM should not run"))
    verdict = minimax.validate_director_raw_scene_physical(
        "Alice walks from the steps into the garden.",
        "Alice stands barefoot on the steps.",
        known_subject_state=state,
        llm_request=llm,
    )
    assert verdict["valid"] is False
    assert "Alice as barefoot" in verdict["issue"]
    assert state == snapshot
    llm.assert_not_called()
