"""Replay captured resolver input; conflicting replies are explicitly reconstructed."""
import ast
import copy
import inspect
import json
from pathlib import Path
from unittest import mock

import pytest

import minimax
from world_state import new_world_state, seed_canonical_static_location_state, seed_current_segment_subject_identities


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "visible_subject_fallback_segment1.json").read_text())


def opening_state():
    state = new_world_state({"subjects": {
        "1": {"subject_id": 1, "name": "Alice", "picture_ids": []},
        "2": {"subject_id": 2, "name": "Knight", "picture_ids": []},
    }})
    state = seed_current_segment_subject_identities(state, [
        {"name": row["name"], "physical_form": "humanoid", "gender": "male",
         "source_description": "One separately registered individual."}
        for row in FIXTURE["known_subjects"] if row["name"].startswith("TurbanedMan")
    ])
    state, location = seed_canonical_static_location_state(state, {
        "location": {"name": FIXTURE["location_name"]}, "anchors": [], "objects": []})
    for row in FIXTURE["registered_subjects"]:
        subject = state["subjects"][row["id"]]
        subject["presence"] = row["presence"]
        if row["presence"] == "present":
            subject["location_id"] = location
    assert minimax._director_raw_subject_vocabulary(state)[0] == FIXTURE["known_subjects"]
    return state


def run_actual_caller(raw, state, definitions):
    """Execute the actual caller through event validation, isolating unrelated startup/rendering."""
    tree = ast.parse(inspect.getsource(minimax._run_main))
    def assigns(statement, name):
        return isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets)
    body = next(node.body for node in ast.walk(tree)
                if isinstance(node, (ast.For, ast.While)) and any(
                    assigns(statement, "request2_result_for_fixture") for statement in node.body))
    start = next(i for i, statement in enumerate(body) if assigns(statement, "request2_result_for_fixture"))
    stop = next(i for i, statement in enumerate(body) if assigns(statement, "reported_beat_ids"))
    function = ast.parse("def replay():\n    pass\n").body[0]
    function.body = copy.deepcopy(body[start:stop + 1]) + [ast.parse("return locals()").body[0]]
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    payload = {"raw_scene": raw, "llm_result": {"detailed_description": raw,
               "overall_soundscape": "Leaves rustle.", "non_diegetic_music": "N/A"},
               "loras": [], "request1_result": {"beat_complete": True}}
    scope = {**vars(minimax), "payload": payload, "segment": 1,
             "segment_bundle": {"current_duration": 8., "conditioning_mode": "initial",
                                "world_state_opening": state},
             "subject_definitions": definitions, "run_id": "captured-fallback-replay",
             "run_config": {"source_sha256": "fallback-replay"}, "beats": [],
             "generation_state": {"world_state": state, "metadata": {}}}
    exec(compile(module, str(Path(minimax.__file__)), "exec"), scope)
    return {"payload": payload, **scope["replay"]()}


@pytest.mark.parametrize("outer_whitespace", [False, True])
def test_two_collective_conflicts_continue_through_caller_worldstate_bindings_and_h3(outer_whitespace):
    state = opening_state()
    before = copy.deepcopy(state)
    raw = FIXTURE["raw_scene"]
    if outer_whitespace:
        raw = "  " + raw + "\n\n"
    definitions = minimax.world_state_subject_definitions("<Subject 1> is Alice.\n<Subject 2> is Knight.", state)
    original_resolver = minimax.resolve_director_raw_scene_subjects
    resolver_request = mock.Mock(side_effect=copy.deepcopy(FIXTURE["resolver_responses"]))
    def resolve(accepted, **kwargs):
        return original_resolver(accepted, llm_request=resolver_request, **kwargs)
    events_request = mock.Mock(return_value={"events": []})
    # The extracted caller shares production functions; only external LLMs are stubbed.
    with mock.patch.object(minimax, "resolve_director_raw_scene_subjects", side_effect=resolve), \
            mock.patch.object(minimax, "ask_llm", events_request), \
            mock.patch.object(minimax, "_director_carry_forward_final_subjects", side_effect=AssertionError("unresolved identities must not be carried")), \
            mock.patch.object(minimax, "console_log") as log:
        result = run_actual_caller(raw, state, definitions)
    assert resolver_request.call_count == 2
    assert [call.kwargs["history_metadata"]["attempt"] for call in resolver_request.call_args_list] == [1, 2]
    assert result["subject_resolution_succeeded"] is False
    assert result["carried_final_subjects"] == []
    assert result["resolved_subject_names"] == result["raw_subject_names"] == []
    assert result["payload"]["raw_scene"] == raw
    assert result["request1_result"]["raw_scene"] == raw
    assert result["request1_result"]["state_actions_dry_run_accepted"] is True
    assert result["request1_result"]["state_actions"] == []
    events_request.assert_called_once()
    assert events_request.call_args.kwargs["history_metadata"]["purpose"] == "director_world_state_events"
    assert any("maps to conflicting identities" in str(call) for call in log.call_args_list)
    assert any("preserving accepted RAW unchanged" in str(call) for call in log.call_args_list)

    references, bound_definitions, _, snapshot = minimax.build_segment_reference_bindings(
        segment_number=1, total_segments=1, detailed_description=raw,
        subject_definitions=definitions, character_references={}, base_reference_count=0)
    prompt = minimax.build_h3_prompt_with_camera_recovery(
        result["llm_result"], bound_definitions, segment_number=1,
        world_state=state, accepted_raw_scene=raw, conditioning_mode="initial")
    assert "Each of the four turbaned men with beards" in prompt
    assert "<Picture" not in prompt
    assert references == {} and snapshot["bindings"] == []
    assert state == before
    assert {name for name in (row["name"] for row in state["subjects"].values())
            if name.startswith("TurbanedMan")} == {f"TurbanedMan{i}" for i in range(1, 5)}
    assert len(state["subjects"]) == 6  # Alice, Knight, and the four original individuals.


def test_collective_cannot_map_to_multiple_individuals_or_create_a_phantom_subject():
    state = opening_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="maps to conflicting identities"):
        minimax.resolve_director_raw_scene_subjects(
            FIXTURE["raw_scene"], state, segment_seconds=8,
            llm_request=mock.Mock(return_value=FIXTURE["resolver_responses"][0]))
    assert state == before
