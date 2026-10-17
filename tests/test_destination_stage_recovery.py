"""Failures correct the destination stage without rebuilding accepted upstream state."""
import copy
from unittest import mock

import pytest

import minimax
from pipeline_recovery import PipelineStageExhaustedError
from world_state import empty_world_state, seed_canonical_static_location_state


def fixture(name="wooden post", kind="post"):
    return {"name": name, "type": kind, "world_state_role": "fixture", "mobility": "fixed"}


def state_with_entrance():
    state = empty_world_state("destination-recovery")
    return seed_canonical_static_location_state(state, {
        "location": {"name": "House step"},
        "anchors": [fixture(), fixture("cave entrance", "entrance")], "objects": [],
    })


def extracted(name="Cave", anchors=None):
    return {"location": {"name": name}, "anchors": anchors or [], "objects": []}


def test_semantic_ambiguity_repairs_prose_then_revalidates_before_json():
    state, _ = state_with_entrance()
    before = copy.deepcopy(state)
    responses = iter([
        "A cave with a wooden post.", extracted(anchors=[fixture()]),
        # First repair is physically contradictory; it must not reach JSON.
        "A cave with a wooden post 1 m east of the entrance and 1 m west of the entrance.",
        "The House step wooden post is visible outside the cave entrance.",
        extracted(anchors=[fixture()]),
    ])
    calls = []
    def request(messages, **kwargs):
        calls.append((kwargs["history_metadata"]["purpose"], messages))
        return next(responses)
    # Independent spatial validation supplies a deterministic rejected repair.
    original = minimax.parse_story_setting_text_description
    def parse(value):
        if "east of" in value:
            raise ValueError("contradictory physical placement")
        return original(value)
    with mock.patch.object(minimax, "parse_story_setting_text_description", side_effect=parse):
        result = minimax.extract_story_setting_description("A cave", location_name="Cave",
            world_state=state, llm_request=request, repair_attempts=2)
    assert [purpose for purpose, _ in calls] == ["story_setting_extract", "story_setting_json_extract",
        "story_setting_extract_repair", "story_setting_extract_repair", "story_setting_json_extract"]
    repair = calls[2][1][-1]["content"]
    assert "wooden post" in repair and "House step" in repair and "Ambiguous neighboring fixture" in repair
    assert result["location_state"]["anchors"] == []
    assert state == before
    assert len(state["props"]) == 2


def test_malformed_json_alone_retries_same_accepted_prose():
    request = mock.Mock(side_effect=["A spacious cave.", "broken JSON", extracted()])
    result = minimax.extract_story_setting_description("A cave", location_name="Cave", llm_request=request)
    assert result["text_description"] == "A spacious cave."
    assert request.call_args_list[1].args[0] == request.call_args_list[2].args[0]
    assert [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list] == [
        "story_setting_extract", "story_setting_json_extract", "story_setting_json_extract"]


def test_semantic_exhaustion_is_terminal_and_keeps_original_world():
    state, _ = state_with_entrance()
    before = copy.deepcopy(state)
    request = mock.Mock(side_effect=["A cave with a wooden post.", extracted(anchors=[fixture()]),
        "A cave with a wooden post.", extracted(anchors=[fixture()])])
    with pytest.raises(minimax.StorySettingDescriptionError) as caught:
        minimax.extract_story_setting_description("A cave", location_name="Cave", world_state=state,
            llm_request=request, repair_attempts=1)
    assert isinstance(caught.value, PipelineStageExhaustedError)
    assert caught.value.stage_name == "destination_location"
    assert request.call_count == 4
    assert state == before


def test_explicit_distinct_fixture_is_preserved_in_new_location():
    state, _ = state_with_entrance()
    result = minimax.reconcile_neighboring_location_fixtures(extracted(anchors=[fixture()]), state,
        "Cave contains a separate wooden post, distinct from the House step post.")
    assert result["anchors"] == [fixture()]


def test_spatial_reference_in_a_distinct_fixture_name_does_not_merge_its_landmark():
    state, _ = state_with_entrance()
    garden = fixture("narrow garden south of wooden post", "garden")
    location = extracted(anchors=[garden])
    result = minimax.reconcile_neighboring_location_fixtures(
        location, state, "A narrow garden lies south of the House step wooden post.")
    assert result["anchors"] == [garden]


def test_entrance_owner_is_not_destination_interior():
    state, origin = state_with_entrance()
    before = copy.deepcopy(state)
    result = minimax.resolve_scene_location_destination(state, origin,
        {"classification": "transitioning", "location_name": "Cave"},
        source_text="Mara enters a cave through its entrance.", beat_text="Mara enters the cave.")
    assert result["requires_registration"] is True
    assert result["destination_location_id"] is None
    assert minimax.resolve_world_state_location_alias(state, "cave entrance") is None
    assert state == before


def test_canonical_location_name_then_known_connectivity():
    state, origin = state_with_entrance()
    state, interior = seed_canonical_static_location_state(state, extracted("Cave interior"))
    entrance = next(pid for pid, item in state["props"].items() if item["name"] == "cave entrance")
    connections = [{"origin_location_id": origin, "entrance_fixture_id": entrance,
                    "destination_location_id": interior}]
    assert minimax.resolve_world_state_location_alias(state, "Cave interior", connections=connections,
        origin_location_id=origin) == interior
    assert minimax.resolve_world_state_location_alias(state, "cave entrance", connections=connections,
        origin_location_id=origin) == interior


def test_unsupported_selector_and_origin_mismatch_repair_only_selector():
    state, origin = state_with_entrance()
    before = copy.deepcopy(state)
    request = mock.Mock(side_effect=[{"classification": "transitioning", "location_name": "House step"},
        {"classification": "transitioning", "location_name": "Cave"}])
    selection, resolution = minimax.resolve_scene_location_selection_locally(state, origin,
        "Mara enters the cave.", "A house step.", [], source_text="Mara enters a cave.", llm_request=request)
    assert resolution["requires_registration"]
    assert "active origin" in request.call_args_list[1].args[0][1]["content"]
    assert state == before
    with pytest.raises(minimax.DestinationLocationStageError, match="lacks named source"):
        minimax.resolve_scene_location_selection_locally(state, origin, "Mara enters the cave.", "A step.", [],
            source_text="Mara enters a cave.", cached_selection={"classification": "transitioning", "location_name": "Moon"},
            attempts=1)


def test_runtime_destination_reference_failure_keeps_upstream_checkpoint_atomic():
    # Execute the actual nested stage with lightweight dependencies, rather
    # than reimplementing the ordering in a second production helper.
    import ast
    import inspect
    import textwrap
    tree = ast.parse(inspect.getsource(minimax._run_main))
    node = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "prepare_scene_location_for_segment")
    stage_source = ast.get_source_segment(inspect.getsource(minimax._run_main), node)
    state, origin = state_with_entrance()
    checkpoint = {
        "world_state": state, "character_canon": {"Mara": "accepted canon"},
        "wardrobe": {"Mara": "accepted clothing"},
        "location_state": extracted("House step"),
        "metadata": {"active_location_id": origin, "starting_location": "House step",
            "location_contexts": {origin: {"location_id": origin, "name": "House step",
                "setting_description": "A house step."}},
            "scene_location_selections": {"1": {"classification": "transitioning", "location_name": "Cave"}}},
    }
    before = copy.deepcopy(checkpoint)
    scope = dict(vars(minimax))
    scope.update(generation_state=checkpoint, beats=["Mara enters the cave."],
        expanded_story_context="Mara enters a cave.", story="Mara enters a cave.", run_id="test",
        visual_style="", base_subject_definitions="", origin=origin,
        generated_prompts_payload={"config": {}, "reference_jobs": []},
        extract_static_setting=mock.Mock(return_value="A cave."),
        refine_story_setting_spatially=mock.Mock(return_value="A spacious cave."),
        extract_story_setting_description=mock.Mock(return_value={"location_state": extracted(),
            "text_description": "A spacious cave."}),
        ensure_location_reference_for_segment=mock.Mock(side_effect=RuntimeError("reference failed")),
        checkpoint_generation_state=mock.Mock(), save_generated_prompts_file=mock.Mock())
    exec("def factory():\n    active_location_id = origin\n" + textwrap.indent(stage_source, "    ")
         + "\n    return prepare_scene_location_for_segment\n", scope)
    with pytest.raises(RuntimeError, match="reference failed"):
        scope["factory"]()(1)
    assert checkpoint == before
    scope["checkpoint_generation_state"].assert_not_called()


def test_neighbor_owner_in_unrelated_sentence_does_not_silently_merge_fixture():
    state, _ = state_with_entrance()
    with pytest.raises(minimax.NeighborFixtureIdentityError, match="canonical owner"):
        minimax.reconcile_neighboring_location_fixtures(extracted(anchors=[fixture()]), state,
            "A wooden post stands near the cave wall. The House step is visible outside.")
