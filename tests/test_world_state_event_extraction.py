import copy
from unittest import mock

import pytest

import minimax
from world_state import (
    new_world_state,
    register_explicit_persistent_props,
    seed_canonical_static_location_state,
    seed_story_start_presence,
)


def event(action, actor, object=None, source=None, destination=None, relation=None, result=None):
    return {
        "action": action,
        "actor": actor,
        "object": object,
        "source": source,
        "destination": destination,
        "relation": relation,
        "result": result,
    }


def state_with_entities(*, cloth_held=False, mug=True, barrel=False, wardrobe=False):
    state = new_world_state({
        "source_sha256": "event-extraction-regression",
        "subjects": {
            "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
            "2": {"subject_id": 2, "name": "Goblin", "gender": "unknown", "picture_ids": []},
            "3": {"subject_id": 3, "name": "Dragon", "gender": "unknown", "picture_ids": []},
            "4": {"subject_id": 4, "name": "Elf", "gender": "unknown", "picture_ids": []},
        },
    })
    state, location_id = seed_canonical_static_location_state(
        state,
        {"location": {"name": "Tavern"}, "anchors": [], "objects": []},
    )
    state = seed_story_start_presence(state, [
        {"name": "Amy", "initial_state": "standing in the room"},
        {"name": "Goblin", "initial_state": "standing in the room"},
        {"name": "Dragon", "initial_state": "standing in the room"},
        {"name": "Elf", "initial_state": "standing in the room"},
    ], location_id=location_id)
    props = [
        {"name": "polished table 3", "kind": "support", "mobility": "fixed",
         "needed_for_state": True, "reason": "A registered body support.", "location_id": location_id},
        {"name": "crystal shelf", "kind": "support", "mobility": "fixed",
         "needed_for_state": True, "reason": "A registered prop support.", "location_id": location_id},
        {"name": "door", "kind": "fixture", "mobility": "fixed",
         "needed_for_state": True, "reason": "A registered mechanism.", "location_id": location_id},
    ]
    if cloth_held:
        props.append({"name": "cleaning cloth", "kind": "tool", "mobility": "movable",
                      "needed_for_state": True, "reason": "It persists across scenes.",
                      "holder_subject_id": "subject_1"})
    if mug:
        props.append({"name": "mug", "kind": "container", "mobility": "movable",
                      "needed_for_state": True, "reason": "It receives a transfer.",
                      "location_id": location_id,
                      "contents": [{"substance": "ale", "amount": "some", "consumable": True}],
                      "capabilities": {"container": True}})
    if barrel:
        props.append({"name": "barrel", "kind": "container", "mobility": "fixed",
                      "needed_for_state": True, "reason": "It supplies a transfer.",
                      "location_id": location_id,
                      "contents": [{"substance": "ale", "amount": "some", "consumable": "unknown"}],
                      "capabilities": {"container": True}})
    state = register_explicit_persistent_props(state, props)
    if wardrobe:
        amy = state["subjects"]["subject_1"]
        amy["wardrobe"]["upper"] = [{"garment": "tunic", "condition": "clean"}]
    return state, location_id


def prop_id(state, name):
    return next(key for key, value in state["props"].items() if value["name"] == name)


def test_event_extractor_prompt_requires_explicit_persistent_physical_changes():
    messages = minimax.build_world_state_event_messages("Amy wipes the counter.")
    assert (
        "- Extract only events that explicitly change persistent physical state. "
        "Ignore ordinary activity and descriptions that do not establish a state change."
    ) in messages[0]["content"]
    assert messages[1]["content"] == "RAW SCENE\nAmy wipes the counter."


def test_support_standing_maps_to_subject_specific_set_support():
    state, _ = state_with_entities(mug=False)
    raw = "At 00:01.000, Amy steps onto polished table 3."
    result = minimax.translate_world_state_events(
        state, [event("move", "Amy", "polished table 3", destination="Tavern", relation="onto", result="standing")],
        raw, segment_number=1,
    )
    action = result["state_actions"][0]
    assert action["op"] == "set_support"
    assert action["subject_id"] == "subject_1"
    assert action["support_id"] == prop_id(state, "polished table 3")
    candidate = minimax.reduce_world_state(state, result["state_actions"], segment_number=1).world_state
    assert candidate["subjects"]["subject_1"]["support_id"] == prop_id(state, "polished table 3")
    assert state["subjects"]["subject_1"]["support_id"] is None


def test_job63_move_without_registered_destination_is_skipped():
    state, _ = state_with_entities(mug=False)
    result = minimax.translate_world_state_events(state, [
        event("move", "Amy", "unregistered stage", destination="far corner", relation="to"),
        event("modify", "Amy", "door", result="locked"),
    ], "Amy moves to the far corner and locks the door.", segment_number=1)
    assert [action["op"] for action in result["state_actions"]] == ["lock"]
    assert state["subjects"]["subject_1"]["location_id"] == state["subjects"]["subject_2"]["location_id"]


def test_movement_beside_registered_surface_does_not_establish_support():
    state, _ = state_with_entities(mug=False)
    result = minimax.translate_world_state_events(
        state,
        [event("move", "Amy", "polished table 3", destination="Tavern", relation="beside")],
        "At 00:01.000, Amy steps beside polished table 3.",
        segment_number=1,
    )
    assert result["state_actions"] == []
    assert state["subjects"]["subject_1"]["support_id"] is None


def test_known_cloth_retrieved_from_unregistered_apron_pocket_is_not_duplicated():
    state, _ = state_with_entities(cloth_held=True, mug=False)
    raw = "At 00:01.000, Amy pulls the cleaning cloth from her apron pocket."
    result = minimax.translate_world_state_events(
        state, [event("take", "Amy", "cleaning cloth", source="apron pocket", relation="from")],
        raw, segment_number=1,
    )
    assert result["state_actions"] == []
    assert sum(prop["name"] == "cleaning cloth" for prop in state["props"].values()) == 1


def test_new_cup_is_retrieved_from_registered_shelf_then_handed_to_dragon():
    state, _ = state_with_entities(mug=False)
    raw = (
        "At 00:01.000, Amy retrieves the crystal cup from crystal shelf.\n"
        "At 00:04.000, Amy hands the crystal cup to Dragon."
    )
    result = minimax.translate_world_state_events(state, [
        event("take", "Amy", "crystal cup", source="crystal shelf", relation="from"),
        event("put", "Amy", "crystal cup", destination="Dragon", relation="to"),
    ], raw, segment_number=4)
    assert [action["op"] for action in result["state_actions"]] == ["retrieve_prop", "handoff"]
    end = minimax.reduce_world_state(state, result["state_actions"], segment_number=4).world_state
    cup = next(prop for prop in end["props"].values() if prop["name"] == "crystal cup")
    assert cup["placement"] == {"kind": "held", "subject_id": "subject_3"}
    assert sum(prop["name"] == "crystal cup" for prop in state["props"].values()) == 0
    next_segment = minimax.translate_world_state_events(
        end, [event("take", "Dragon", "crystal cup")],
        "Dragon holds the crystal cup.", segment_number=5,
    )
    assert next_segment["state_actions"] == []


def test_event_operations_cover_enter_exit_place_pour_consume_clothing_and_lock():
    state, location_id = state_with_entities(barrel=True, wardrobe=True)
    state["subjects"]["subject_1"]["presence"] = "unknown"
    state["subjects"]["subject_1"]["location_id"] = "unknown"
    mug = state["props"][prop_id(state, "mug")]
    # Amy acquires the mug; the following handoff and consumption are staged.
    mug["contents"] = [{"substance": "ale", "amount": "none", "consumable": True}]
    mug["placement"] = {"kind": "located", "location_id": location_id,
                        "support_id": prop_id(state, "polished table 3")}
    raw = "Amy enters, takes the mug, sets it on the table, pours ale into it, Goblin drinks all the ale, Amy puts on a coat, locks the door, and Elf exits."
    events = [
        event("enter", "Amy", destination="Tavern"),
        event("take", "Amy", "mug", source="polished table 3", relation="from"),
        event("put", "Amy", "mug", destination="polished table 3", relation="on"),
        event("transfer", "Amy", "ale", source="barrel", destination="mug", relation="partial"),
        event("consume", "Goblin", "mug", relation="all", result="ale"),
        event("modify", "Amy", "coat", relation="upper put on", result="puts on"),
        event("modify", "Amy", "door", result="locked"),
        event("exit", "Elf"),
    ]
    result = minimax.translate_world_state_events(state, events, raw, segment_number=2)
    assert [action["op"] for action in result["state_actions"]] == [
        "enter", "pickup", "place", "pour", "consume", "change_clothing", "lock", "exit",
    ]
    reduced = minimax.reduce_world_state(state, result["state_actions"], segment_number=2)
    assert reduced.committed
    end = reduced.world_state
    assert end["subjects"]["subject_4"]["presence"] == "absent"
    assert any(layer["garment"] == "coat" for layer in end["subjects"]["subject_1"]["wardrobe"]["upper"])
    assert end["props"][prop_id(state, "door")]["mechanism_state"] == "locked"
    assert end["props"][prop_id(state, "mug")]["contents"][0]["amount"] == "none"


def test_ambiguous_names_and_unknown_supports_fail_closed():
    state, _ = state_with_entities(mug=False)
    state["subjects"]["subject_5"] = copy.deepcopy(state["subjects"]["subject_3"])
    state["subjects"]["subject_5"]["id"] = "subject_5"
    state["subjects"]["subject_5"]["name"] = "Dragon2"
    with pytest.raises(minimax.WorldStateEventExtractionError, match="ambiguous subject"):
        minimax.translate_world_state_events(
            state, [event("move", "Dragon", destination="Tavern")],
            "Dragon moves.", segment_number=1,
        )
    state, _ = state_with_entities(mug=False)
    with pytest.raises(minimax.WorldStateEventExtractionError, match="registered support origin"):
        minimax.translate_world_state_events(
            state, [event("take", "Amy", "new cloth", source="apron pocket")],
            "Amy takes new cloth from apron pocket.", segment_number=1,
        )


def test_noop_events_are_omitted_and_reducer_rejection_does_not_mutate_opening():
    state, _ = state_with_entities(cloth_held=True, mug=False)
    opening = copy.deepcopy(state)
    no_op = minimax.translate_world_state_events(
        state, [event("take", "Amy", "cleaning cloth", source="apron pocket")],
        "Amy takes the cleaning cloth.", segment_number=1,
    )
    assert no_op["state_actions"] == []
    invalid = [event("take", "Amy", "door")]
    with pytest.raises(minimax.WorldStateEventExtractionError, match="reducer rejected translation"):
        minimax.translate_world_state_events(state, invalid, "Amy enters.", segment_number=1)
    assert state == opening


def test_release_places_a_held_prop_in_the_actors_registered_location():
    state, location_id = state_with_entities(cloth_held=True, mug=False)
    result = minimax.translate_world_state_events(
        state, [event("release", "Amy", "cleaning cloth")],
        "Amy drops the cleaning cloth.", segment_number=1,
    )
    assert [item["op"] for item in result["state_actions"]] == ["place"]
    end = minimax.reduce_world_state(state, result["state_actions"], segment_number=1).world_state
    cloth = end["props"][prop_id(end, "cleaning cloth")]
    assert cloth["placement"] == {"kind": "located", "location_id": location_id}


def test_malformed_extraction_repair_uses_same_raw_and_preserves_opening_state():
    state, _ = state_with_entities(mug=False)
    opening = copy.deepcopy(state)
    raw = "Amy wipes the counter."
    invalid = {"events": [{"action": "invalid"}]}
    request = mock.Mock(side_effect=[invalid, {"events": []}])
    with mock.patch("minimax.ask_llm", request), mock.patch("minimax.console_log"):
        result = minimax.extract_and_dry_run_world_state_events(state, raw, segment_number=1)
    assert result["events"] == []
    assert result["state_actions"] == []
    assert state == opening
    assert request.call_count == 2
    assert request.call_args_list[1].args[0][-1]["content"].count(raw) == 1
    assert [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list] == [
        "director_world_state_events", "director_world_state_events_repair",
    ]


def test_malformed_event_repair_budget_is_bounded_and_does_not_commit():
    state, _ = state_with_entities(mug=False)
    opening = copy.deepcopy(state)
    raw = "Amy moves beside the counter."
    malformed = {"events": [{"action": "not-an-event"}]}
    request = mock.Mock(return_value=malformed)
    with mock.patch("minimax.ask_llm", request), mock.patch("minimax.console_log") as log:
        result = minimax.extract_and_dry_run_world_state_events(
            state, raw, segment_number=1
        )
    assert request.call_count == 1 + minimax.WORLD_STATE_EVENT_REPAIR_ATTEMPTS
    assert all(call.args[0][-1]["content"].find(raw) >= 0 for call in request.call_args_list)
    diagnostic = f"Malformed event extraction for Segment 1 after {minimax.WORLD_STATE_EVENT_REPAIR_ATTEMPTS} repairs"
    assert result["accepted"] is True
    assert result["events"] == []
    assert result["state_actions"] == []
    assert result["raw_scene"] == raw
    assert (
        "Malformed event extraction for Segment 1 after "
        f"{minimax.WORLD_STATE_EVENT_REPAIR_ATTEMPTS} repairs" in diagnostic
    )
    assert any(
        "discarding the entire event batch" in call.args[0]
        and "Malformed event extraction for Segment 1 after 5 repairs" in call.args[0]
        for call in log.call_args_list
    )
    assert state == opening


def test_translation_failure_discards_prior_events_and_preserves_opening_world_state():
    state, _ = state_with_entities(mug=False)
    opening = copy.deepcopy(state)
    raw = "Amy locks the door, then retrieves a new cloth from her apron pocket."
    response = {"events": [
        event("modify", "Amy", "door", result="locked"),
        event("take", "Amy", "new cloth", source="apron pocket", relation="from"),
    ]}
    with mock.patch("minimax.ask_llm", return_value=response), mock.patch("minimax.console_log") as log:
        result = minimax.extract_and_dry_run_world_state_events(
            state, raw, segment_number=1
        )
    assert result["accepted"] is True
    assert result["events"] == []
    assert result["state_actions"] == []
    assert result["raw_scene"] == raw
    assert any(
        "new prop 'new cloth' has no registered support origin" in call.args[0]
        for call in log.call_args_list
    )
    assert state == opening


def test_raw_integrity_failure_discards_event_batch_and_keeps_empty_candidate():
    state, _ = state_with_entities(mug=False)
    opening = copy.deepcopy(state)
    raw = "Amy opens the entrance."
    changed_result = {
        "accepted": True,
        "raw_scene": "Amy opens a different door.",
        "state_actions": [{"op": "exit", "subject_id": "subject_amy"}],
        "opening_state_sha256": minimax.world_state_sha256(state),
    }
    with mock.patch("minimax.ask_llm", return_value={"events": []}), mock.patch(
        "minimax.translate_world_state_events", return_value=changed_result
    ), mock.patch("minimax.console_log") as log:
        result = minimax.extract_and_dry_run_world_state_events(
            state, raw, segment_number=1
        )
    assert result["accepted"] is True
    assert result["events"] == []
    assert result["state_actions"] == []
    assert result["raw_scene"] == raw
    assert state == opening
    assert any(
        "changed the accepted RAW" in call.args[0]
        and "discarding the entire event batch" in call.args[0]
        for call in log.call_args_list
    )


def test_alice_grabbing_fixed_wooden_post_discards_entire_rejected_batch():
    state = new_world_state({
        "source_sha256": "alice-fixed-post",
        "subjects": {
            "1": {"subject_id": 1, "name": "Alice", "gender": "female", "picture_ids": []},
        },
    })
    state, location_id = seed_canonical_static_location_state(
        state,
        {"location": {"name": "Tea Garden"}, "anchors": [], "objects": []},
    )
    state = seed_story_start_presence(
        state, [{"name": "Alice", "initial_state": "standing in the garden"}],
        location_id=location_id,
    )
    state = register_explicit_persistent_props(state, [
        {"name": "mug", "kind": "container", "mobility": "movable",
         "needed_for_state": True, "reason": "It can be carried.", "location_id": location_id},
        {"name": "fixed wooden post", "kind": "support", "mobility": "fixed",
         "needed_for_state": True, "reason": "It is fixed in the environment.", "location_id": location_id},
    ])
    opening = copy.deepcopy(state)
    raw = "Alice picks up the mug, then grabs the fixed wooden post."
    response = {"events": [
        event("take", "Alice", "mug"),
        event("take", "Alice", "fixed wooden post"),
    ]}
    with mock.patch("minimax.ask_llm", return_value=response), mock.patch("minimax.console_log") as log:
        result = minimax.extract_and_dry_run_world_state_events(
            state, raw, segment_number=1
        )
    assert result["accepted"] is True
    assert result["events"] == []
    assert result["state_actions"] == []
    assert result["raw_scene"] == raw
    assert state == opening
    assert any(
        "fixed" in call.args[0] and "discarding the entire event batch" in call.args[0]
        for call in log.call_args_list
    )


def test_event_extraction_does_not_swallow_fatal_llm_connection_failure():
    state, _ = state_with_entities(mug=False)
    with mock.patch(
        "minimax.ask_llm",
        side_effect=minimax.LLMConnectionError("LLM unavailable"),
    ), mock.patch("minimax.console_log"):
        with pytest.raises(minimax.LLMConnectionError, match="LLM unavailable"):
            minimax.extract_and_dry_run_world_state_events(
                state,
                "Amy opens the entrance.",
                segment_number=1,
            )


def test_event_extraction_does_not_swallow_non_connection_transport_failure():
    state, _ = state_with_entities(mug=False)
    with mock.patch(
        "minimax.ask_llm",
        side_effect=minimax.requests.HTTPError("LLM endpoint returned 503"),
    ), mock.patch("minimax.console_log"):
        with pytest.raises(minimax.requests.HTTPError, match="503"):
            minimax.extract_and_dry_run_world_state_events(
                state,
                "Amy opens the entrance.",
                segment_number=1,
            )
