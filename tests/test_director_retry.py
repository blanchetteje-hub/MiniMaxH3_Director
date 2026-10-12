import unittest
import json
import re
import copy
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

import minimax
from world_state import (
    build_state_action_only_contract,
    new_world_state,
    register_explicit_persistent_props,
    seed_canonical_static_location_state,
    seed_story_start_presence,
    validate_state_actions,
)


def segment_bundle():
    return {
        "segment": 1,
        "active_beat_id": 1,
        "current_duration": 6.0,
        "messages": [{"role": "user", "content": "Direct segment 1."}],
        "conditioning_mode": "initial",
        "opening_state_sha256": "opening-hash",
    }


def goblin_mug_world_state():
    state = new_world_state({
        "source_sha256": "request1-world-state",
        "subjects": {
            "1": {"subject_id": 1, "name": "Goblin1", "gender": "unknown", "picture_ids": []},
            "2": {"subject_id": 2, "name": "Elf1", "gender": "unknown", "picture_ids": []},
            "3": {"subject_id": 3, "name": "Amy", "gender": "female", "picture_ids": []},
        },
    })
    state, location_id = seed_canonical_static_location_state(
        state,
        {"location": {"name": "Room"}, "anchors": [], "objects": []},
    )
    state = seed_story_start_presence(
        state,
        [
            {"name": "Goblin1", "initial_state": "standing near the table"},
            {"name": "Elf1", "initial_state": "standing near the door"},
            {"name": "Amy", "initial_state": "standing by the counter"},
        ],
        location_id=location_id,
    )
    state = register_explicit_persistent_props(state, [{
        "name": "mug",
        "kind": "object",
        "mobility": "movable",
        "needed_for_state": True,
        "reason": "The mug is transferred between registered Subjects.",
        "location_id": location_id,
    }])
    return state, location_id, next(
        prop_id for prop_id, prop in state["props"].items()
        if prop["name"] == "mug"
    )


def goblin_mug_bundle():
    state, _location_id, _mug_id = goblin_mug_world_state()
    bundle = segment_bundle()
    bundle.update({
        "world_state_opening": copy.deepcopy(state),
        "current_beat_text": "Goblin1 picks up the mug and hands it to Elf1.",
    })
    return bundle


TAVERN_BENCHMARK = json.loads(
    (Path(__file__).parent / "acceptance" / "gold" / "amy_medieval_tavern_six.json")
    .read_text(encoding="utf-8")
)
TAVERN_SOURCE_PARAGRAPHS = TAVERN_BENCHMARK["story_text"].split("\n\n")
TAVERN_SEGMENT_BEATS = [
    "\n".join(item["must_happen"])
    for item in TAVERN_BENCHMARK["beats"]
]
TAVERN_SEGMENT_SOURCES = [
    TAVERN_SOURCE_PARAGRAPHS[0],
    TAVERN_SOURCE_PARAGRAPHS[0],
    TAVERN_SOURCE_PARAGRAPHS[1],
    TAVERN_SOURCE_PARAGRAPHS[2],
    TAVERN_SOURCE_PARAGRAPHS[3],
    TAVERN_SOURCE_PARAGRAPHS[4],
]


def current_prop(name, holder=None, location="Tavern", support=None, evidence="", reason=""):
    return {
        "name": name,
        "kind": "container",
        "mobility": "movable",
        "initial_location": location if holder is None else None,
        "initial_holder": holder,
        "support_name": support,
        "contents": [],
        "capabilities": {
            "container": True,
            "consumable": "unknown",
            "openable": "unknown",
            "lockable": "unknown",
        },
        "reason": reason,
        "evidence": evidence,
    }


def tavern_segment_prop_results(segment_number):
    if segment_number == 1:
        return {"props": [
            current_prop(
                "mug", holder="Goblin1",
                evidence="tiny hands clutching a chipped mug",
                reason="The goblin holds this persistent container in the opening scene.",
            ),
            current_prop(
                "barrel", support=None,
                evidence="a barrel beside the hearth",
                reason="The barrel is the source container for the current tavern service sequence.",
            ),
        ]}
    if segment_number == 3:
        return {"props": [
            current_prop(
                "crystal chalice",
                evidence="Amy pours a steaming cup into a crystal chalice for the elf",
                reason="The chalice is the serving container introduced and handled this Segment.",
            ),
        ]}
    if segment_number == 4:
        return {"props": [
            current_prop(
                "crystal cup", support="shelf",
                evidence="lifts a crystal cup from her shelf",
                reason="The crystal cup is picked up, filled, and handed to the new arrival this Segment.",
            ),
        ]}
    return {"props": []}


def tavern_world_state_from_authorities():
    """Seed from the locked benchmark's authored identity, location, and opening facts."""
    identity_seed = minimax.authoritative_world_state_seed_from_subject_definitions(
        "\n".join(TAVERN_BENCHMARK["input_subjects"]),
        "tests/acceptance/gold/amy_medieval_tavern_six.json",
    )
    state = new_world_state(identity_seed)
    state, location_id = seed_canonical_static_location_state(
        state,
        {
            "location": {"name": "Tavern"},
            "anchors": [
                {"name": "counter", "type": "work surface", "world_state_role": "fixture_support", "mobility": "fixed"},
                {"name": "hearth", "type": "hearth", "world_state_role": "fixture", "mobility": "fixed"},
                {"name": "back table", "type": "table", "world_state_role": "fixture_support", "mobility": "fixed"},
                {"name": "shelf", "type": "shelf", "world_state_role": "fixture_support", "mobility": "fixed"},
                {"name": "high bar stool", "type": "stool", "world_state_role": "fixture_support", "mobility": "fixed"},
            ],
            "objects": [],
        },
    )
    state = seed_story_start_presence(
        state,
        [{"name": "Goblin1", "initial_state": "leaning over the counter, tiny hands clutching a chipped mug"}],
        location_id=location_id,
    )
    state = minimax.extract_registered_subject_story_start_presence(
        state,
        TAVERN_BENCHMARK["story_text"],
        TAVERN_SEGMENT_BEATS,
        location_id=location_id,
        llm_request=mock.Mock(return_value={
            "subject": "Amy",
            "status": "present",
            "initial_state": "Amy wipes a polished table",
        }),
    )
    return state, location_id


def prepare_tavern_segment(state, segment_number):
    subject_reply = {"subjects": []}
    wardrobe_reply = None
    if segment_number == 3:
        subject_reply = {"subjects": [{
            "name": "Elf1",
            "physical_form": "unknown",
            "gender": "female",
            "source_description": "female elf",
            "evidence": "A beautiful female elf steps in, silver hair streaming down its shoulders",
        }]}
        wardrobe_reply = {"clothing": "a wool tunic, a travel cloak, and leather shoes"}
    elif segment_number == 4:
        subject_reply = {"subjects": [{
            "name": "Dragon1",
            "physical_form": "unknown",
            "gender": "unknown",
            "source_description": "dragon-shaped creature",
            "evidence": "a dragon-shaped creature slides onto a high bar stool",
        }]}
        wardrobe_reply = {"clothing": "N/A"}
    replies = [subject_reply]
    if wardrobe_reply is not None:
        replies.append(wardrobe_reply)
    replies.append(tavern_segment_prop_results(segment_number))
    llm = mock.Mock(side_effect=replies)
    state, added_names = minimax.prepare_segment_world_state_for_director(
        state,
        segment_number,
        TAVERN_SEGMENT_BEATS[segment_number - 1],
        TAVERN_SEGMENT_SOURCES[segment_number - 1],
        TAVERN_BENCHMARK["story_text"],
        llm_request=llm,
    )
    included_names = [
        subject["name"] for subject in state["subjects"].values()
        if subject["presence"] == "present"
    ] + added_names
    return state, added_names, list(dict.fromkeys(included_names))


def formatter_response(description):
    """A Request 2 H3 formatter reply with the required response fields."""
    description = str(description)
    if re.search(r"At 00:\d\d\.\d{3},", description) and not re.search(
        r"At 00:0[4-9]\.\d{3},", description
    ):
        description += " At 00:04.500, The action settles into its final visible state."
    return {
        "subject_genders": {},
        "detailed_description": description,
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
    }


def director_response(raw_scene, beat_complete=True):
    """A legacy-shaped RAW fixture without synthetic action padding."""
    scene = str(raw_scene).strip()
    if not scene.startswith("At "):
        scene = "At 00:00.000, " + scene
    if "End continuity state:" not in scene:
        scene += "\nEnd continuity state: The described action has reached its final visible state."
    return {
        "raw_scene": scene,
        "finite_activity_complete": beat_complete,
        "named_beneficiaries_complete": beat_complete,
        "activity_tools_settled": beat_complete,
        "beat_complete": beat_complete,
    }


def pipeline_llm_side_effect(
    non_audio_responses,
    *,
    soundscape="Room tone.",
    music="N/A",
):
    """Adapt legacy scenario fixtures to the sequential RAW refiner stages.

    The supplied non-audio responses describe the same historical scenarios,
    but are routed through the current creative -> timed-format contract.
    """
    queued = iter(non_audio_responses)
    pending_format_response = None
    pending_creative_scene = ""
    pending_timed_scene = ""

    def untimed_scene(response):
        if isinstance(response, dict):
            scene = response.get("raw_scene", "")
        else:
            scene = response
        scene = str(scene or "").strip()
        scene = re.sub(r"(?m)^At\s+\d{2}:\d{2}\.\d{1,3},\s*", "", scene)
        scene = re.sub(r"(?m)^End continuity state:.*$", "", scene)
        return scene.strip()

    def respond(*args, **kwargs):
        nonlocal pending_format_response, pending_creative_scene, pending_timed_scene
        purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
        metadata = kwargs.get("history_metadata") or {}
        if purpose == "director_raw_scene_creative":
            pending_format_response = next(queued)
            pending_creative_scene = untimed_scene(pending_format_response)
            return pending_creative_scene
        if purpose == "add_scene_timing_refiner":
            original_scene = (
                pending_format_response.get("raw_scene", "")
                if isinstance(pending_format_response, dict)
                else ""
            )
            original_scene = re.sub(
                r"(?m)^End continuity state:.*$", "", str(original_scene)
            ).strip()
            action_lines = minimax._normalize_timing_refiner_action_lines(
                pending_creative_scene
            )
            timestamps = [
                f"{int(match.group('minutes')):02d}:{int(match.group('seconds')):02d}."
                f"{int((match.group('fraction') or '0').ljust(3, '0')):03d}"
                for match in minimax._DIRECTOR_TIMESTAMP_RE.finditer(original_scene)
            ]
            if len(timestamps) != len(action_lines) or (timestamps and timestamps[0] != "00:00.000"):
                timestamps = [f"00:00.{index * 100:03d}" for index in range(len(action_lines))]
            pending_timed_scene = minimax._assemble_timed_scene(action_lines, timestamps)
            return {"status": "ok", "timestamps": timestamps}
        if purpose == "add_camera_refiner":
            return pending_timed_scene
        if purpose == "director_raw_scene_repair":
            try:
                repaired = next(queued)
            except StopIteration as error:
                raise AssertionError(
                    f"Unscripted {purpose} call metadata={metadata!r}"
                ) from error
            if metadata.get("stage") == "untimed_creative":
                pending_format_response = director_response(untimed_scene(repaired))
            return repaired
        if purpose == "director_h3_soundscape":
            return {"overall_soundscape": soundscape}
        if purpose == "director_h3_music":
            return {"non_diegetic_music": music}
        if purpose == "director_prop_staging":
            return {"staging": ""}
        if purpose == "director_raw_scene_pronoun_resolution":
            messages = args[0] if args else []
            user_text = str(messages[-1].get("content", "")) if messages else ""
            raw = user_text.split("RAW SCENE\n", 1)[-1].split(
                "\n\nReturn {", 1
            )[0].strip()
            return {"raw_scene": raw}
        if purpose == "director_raw_scene_visible_subject_resolution":
            messages = args[0] if args else []
            user_text = str(messages[-1].get("content", "")) if messages else ""
            raw = user_text.split("RAW SCENE\n", 1)[-1].split(
                "\n\nReturn raw_scene", 1
            )[0].strip()
            return {"raw_scene": raw, "subject_names": []}
        return next(queued)

    return respond


def non_audio_llm_calls(request):
    """Return request calls except the two independent post-RAW audio jobs."""
    return [
        call
        for call in request.call_args_list
        if str((call.kwargs.get("history_metadata") or {}).get("purpose", ""))
        not in {"director_h3_soundscape", "director_h3_music"}
    ]


class DirectorMicroPromptPipelineTests(unittest.TestCase):

    def test_continuation_raw_uses_extended_timeline_after_guide_shift(self):
        bundle = segment_bundle()
        bundle.update({
            "segment": 2,
            "current_duration": 8.0,
            "conditioning_mode": "continuation",
            "current_beat_text": "Amy completes the task and steps back.",
            "subject_definitions": "<Subject 1> is Amy.",
            "messages": [{"role": "user", "content": "Direct segment 2."}],
        })
        response = director_response(
            "At 00:00.000, Amy continues the task.\n"
            "At 00:07.900, Amy finishes and steps back."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([response]))
        pronoun_resolver = mock.Mock(side_effect=lambda raw_scene, **kwargs: raw_scene)
        validators = (
            mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.resolve_director_raw_scene_pronouns", pronoun_resolver),
        )
        with (
            mock.patch("minimax.ask_llm", request),
            validators[0],
            validators[1],
            validators[2],
            validators[3],
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-continuation-time", {"source_sha256": "source"}
            )

        self.assertIn("At 00:08.817, Amy finishes", payload["raw_scene"])
        pronoun_resolver.assert_called_once()
        self.assertIn("At 00:08.817, Amy finishes", pronoun_resolver.call_args.args[0])
        self.assertAlmostEqual(
            pronoun_resolver.call_args.kwargs["segment_seconds"],
            8.0 + 22 / 24,
        )
        self.assertTrue(
            minimax._director_timestamp_range_errors(
                payload["raw_scene"],
                segment_seconds=minimax._director_raw_scene_timeline_duration(
                    8.0, "continuation"
                ),
            ) == []
        )

    def test_action_only_extractor_repairs_actions_without_changing_raw(self):
        world_state, _location_id, mug_id = goblin_mug_world_state()
        opening = copy.deepcopy(world_state)
        raw_scene = (
            "At 00:01.000, Goblin1 picks up the mug.\n"
            "At 00:04.500, Goblin1 hands the same mug to Elf1."
        )
        rejected = {"state_actions": [{
            "action_id": "bad-pickup",
            "op": "pickup",
            "actor_subject_id": "Unknown Subject",
            "prop_id": "mug",
        }]}
        repaired = {"state_actions": [
            {
                "action_id": "pickup-mug",
                "op": "pickup",
                "actor_subject_id": "Goblin1",
                "prop_id": "mug",
            },
            {
                "action_id": "handoff-mug",
                "op": "handoff",
                "from_subject_id": "Goblin1",
                "to_subject_id": "Elf1",
                "prop_id": "mug",
            },
        ]}
        request = mock.Mock(side_effect=[rejected, repaired])
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.console_log"),
        ):
            result = minimax.extract_and_dry_run_director_state_actions(
                world_state,
                raw_scene,
                segment_number=1,
                run_id="run-id",
                run_config={"source_sha256": "source-hash"},
            )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["raw_scene"], raw_scene)
        self.assertEqual(result["state_actions"][-1]["prop_id"], mug_id)
        self.assertEqual(
            result["state_actions"][-1]["to_subject_id"], "subject_2"
        )
        self.assertEqual(world_state, opening)
        self.assertEqual(request.call_count, 2)
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["director_state_actions"],
            minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["director_state_actions_repair"],
            minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        )
        initial_user = request.call_args_list[0].args[0][-1]["content"]
        repair_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn(raw_scene, initial_user)
        self.assertIn(raw_scene, repair_user)
        self.assertIn("FIRST REDUCER FAILURE", repair_user)
        self.assertIn("Unknown Subject", repair_user)
        initial_system = request.call_args_list[0].args[0][0]["content"]
        repair_system = request.call_args_list[1].args[0][0]["content"]
        action_contract = build_state_action_only_contract(
            world_state,
            current_segment_text=raw_scene,
            current_segment_subject_names=["Goblin1", "Elf1"],
        )
        operation_shapes = json.dumps(
            action_contract["prompt_operation_shapes"],
            ensure_ascii=False,
            indent=2,
        )
        for system_prompt in (initial_system, repair_system):
            self.assertIn('"state_actions": []', system_prompt)
            self.assertIn("PERMITTED STATEACTION OBJECT STRUCTURES", system_prompt)
            self.assertIn(operation_shapes, system_prompt)
            self.assertIn('"op": "pickup"', system_prompt)
            self.assertIn('"actor_subject_id": "<registered Subject name>"', system_prompt)
            self.assertNotIn('"subject_1"', system_prompt)
        self.assertIn("entire corrected state_actions batch", repair_system)
        self.assertIn("do not return only the failing action", repair_system)
        self.assertEqual(
            request.call_args_list[0].kwargs["response_format"]["json_schema"]["schema"]["required"],
            ["state_actions"],
        )
        self.assertEqual(
            request.call_args_list[1].kwargs["history_metadata"]["purpose"],
            "director_state_actions_repair",
        )

    def test_action_only_extractor_fails_closed_after_five_repairs(self):
        world_state, _location_id, _mug_id = goblin_mug_world_state()
        opening = copy.deepcopy(world_state)
        raw_scene = "At 00:01.000, Goblin1 moves within the tavern."
        invalid = {"state_actions": [{
            "action_id": "invalid-move",
            "op": "move",
            "subject_id": "Goblin1",
            "destination_location_id": "Tavern",
        }]}
        request = mock.Mock(return_value=invalid)
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.console_log"),
        ):
            with self.assertRaisesRegex(
                minimax.StateActionExtractionError,
                "after 5 action-only repairs",
            ):
                minimax.extract_and_dry_run_director_state_actions(
                    world_state,
                    raw_scene,
                    segment_number=1,
                )
        self.assertEqual(request.call_count, 6)
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["purpose"]
                for call in request.call_args_list
            ],
            ["director_state_actions"]
            + ["director_state_actions_repair"] * 5,
        )
        self.assertEqual(world_state, opening)

    def test_tavern_segment_one_vocabulary_uses_authoritative_seed_paths(self):
        state, _location_id = tavern_world_state_from_authorities()
        state, added, subject_names = prepare_tavern_segment(state, 1)
        self.assertEqual(added, [])
        subject_by_name = {s["name"]: s for s in state["subjects"].values()}
        self.assertEqual(subject_by_name["Amy"]["presence"], "present")
        self.assertEqual(subject_by_name["Goblin1"]["presence"], "present")
        contract = build_state_action_only_contract(
            state,
            current_segment_text=TAVERN_SEGMENT_BEATS[0] + TAVERN_SEGMENT_SOURCES[0],
            current_segment_subject_names=subject_names,
        )
        vocabulary = contract["vocabulary"]
        self.assertEqual(
            {subject["name"] for subject in vocabulary["subjects"]},
            {"Amy", "Goblin1"},
        )
        self.assertEqual(
            {prop["name"] for prop in vocabulary["props"]},
            {"mug", "barrel", "counter", "hearth"},
        )
        mug = next(prop for prop in state["props"].values() if prop["name"] == "mug")
        self.assertEqual(
            mug["placement"],
            {"kind": "held", "subject_id": "subject_goblin1_34aa4679d81b"},
        )

    def test_tavern_segment_three_registers_elf_before_raw_and_allows_enter(self):
        state, location_id = tavern_world_state_from_authorities()
        state, _, _ = prepare_tavern_segment(state, 1)
        state, added, subject_names = prepare_tavern_segment(state, 3)
        self.assertEqual(added, ["Elf1"])
        elf_id, elf = next(
            (subject_id, subject)
            for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Elf1"
        )
        self.assertEqual(elf["presence"], "unknown")
        self.assertEqual(elf["location_id"], "unknown")
        self.assertEqual(elf["identity"]["physical_form"], "unknown")
        self.assertEqual(elf["wardrobe"]["upper"][0]["garment"], "wool tunic")
        contract = build_state_action_only_contract(
            state,
            current_segment_text=TAVERN_SEGMENT_BEATS[2] + TAVERN_SEGMENT_SOURCES[2],
            current_segment_subject_names=subject_names,
        )
        vocabulary_subject_names = {
            subject["name"] for subject in contract["vocabulary"]["subjects"]
        }
        self.assertIn("Elf1", vocabulary_subject_names)
        schema = contract["response_format"]["json_schema"]["schema"]
        action_schemas = schema["properties"]["state_actions"]["items"]["oneOf"]
        enter_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "enter"
        )
        self.assertIn("Elf1", enter_schema["properties"]["subject_id"]["enum"])
        outcome = validate_state_actions(state, [{
            "action_id": "elf-enters",
            "op": "enter",
            "subject_id": elf_id,
            "location_id": location_id,
        }], segment_number=3)
        self.assertTrue(outcome[0].accepted)

    def test_tavern_segment_four_registers_dragon_and_distinguishes_vessels(self):
        state, location_id = tavern_world_state_from_authorities()
        state, _, _ = prepare_tavern_segment(state, 1)
        state, _, _ = prepare_tavern_segment(state, 3)
        state, added, subject_names = prepare_tavern_segment(state, 4)
        self.assertEqual(added, ["Dragon1"])
        dragon_id, dragon = next(
            (subject_id, subject)
            for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Dragon1"
        )
        self.assertEqual(dragon["presence"], "unknown")
        self.assertEqual(dragon["identity"]["physical_form"], "unknown")
        cup_id, cup = next(
            (prop_id, prop) for prop_id, prop in state["props"].items()
            if prop["name"] == "crystal cup"
        )
        shelf_id = next(
            prop_id for prop_id, prop in state["props"].items()
            if prop["name"] == "shelf"
        )
        self.assertEqual(cup["placement"], {
            "kind": "located", "location_id": location_id, "support_id": shelf_id,
        })
        contract = build_state_action_only_contract(
            state,
            current_segment_text=TAVERN_SEGMENT_BEATS[3] + TAVERN_SEGMENT_SOURCES[3],
            current_segment_subject_names=subject_names,
        )
        self.assertEqual(
            {prop["name"] for prop in contract["vocabulary"]["props"]},
            {"mug", "crystal cup", "shelf", "high bar stool"},
        )
        schema = contract["response_format"]["json_schema"]["schema"]
        action_schemas = schema["properties"]["state_actions"]["items"]["oneOf"]
        available_ops = {
            item["properties"]["op"]["const"] for item in action_schemas
        }
        self.assertTrue({"enter", "handoff", "pour"}.issubset(available_ops))
        enter_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "enter"
        )
        self.assertIn("Dragon1", enter_schema["properties"]["subject_id"]["enum"])

    def test_reducer_operation_contract_does_not_depend_on_verb_spelling(self):
        state, _location_id = tavern_world_state_from_authorities()
        state, _, _ = prepare_tavern_segment(state, 1)
        state, _, _ = prepare_tavern_segment(state, 3)
        state, _, subject_names = prepare_tavern_segment(state, 4)
        shared_entities = (
            "Amy Goblin1 Elf1 Dragon1 mug barrel crystal chalice cup "
            "bar counter Tavern"
        )
        variants = (
            f"{shared_entities}. Amy refills the cup.",
            f"{shared_entities}. Elf1 is handing the chalice to Dragon1.",
            f"{shared_entities}. Amy is locking the barrel.",
            f"{shared_entities}. Goblin1 steps outside.",
            f"{shared_entities}. Elf1 slides onto the stool.",
        )
        operation_sets = []
        for text in variants:
            contract = build_state_action_only_contract(
                state,
                current_segment_text=text,
                current_segment_subject_names=subject_names,
            )
            schemas = contract["response_format"]["json_schema"]["schema"][
                "properties"]["state_actions"]["items"]["oneOf"]
            operation_sets.append({
                item["properties"]["op"]["const"] for item in schemas
            })
        self.assertTrue(operation_sets)
        self.assertTrue(all(operations == operation_sets[0] for operations in operation_sets))
        self.assertEqual(
            operation_sets[0],
            {
                "pickup", "place", "handoff", "pour", "consume", "enter",
                "exit", "move", "set_support", "change_clothing", "open",
                "close", "lock", "unlock",
            },
        )

    def test_request_one_uses_action_free_contract_and_readable_world_state(self):
        bundle = goblin_mug_bundle()
        opening_world_state = copy.deepcopy(bundle["world_state_opening"])
        goblin_id = next(
            subject_id for subject_id, subject
            in opening_world_state["subjects"].items()
            if subject["name"] == "Goblin1"
        )
        mug_id = next(
            prop_id for prop_id, prop
            in opening_world_state["props"].items()
            if prop["name"] == "mug"
        )
        opening_world_state["props"][mug_id]["placement"] = {
            "kind": "held", "subject_id": goblin_id,
        }
        bundle["world_state_opening"] = copy.deepcopy(opening_world_state)
        bundle["messages"], _token_estimate, _recent_count = (
            minimax.build_generation_messages(
                director_rules=minimax.build_director_rules(
                    6, 6, 1, "", 1,
                    conditioning_mode="initial",
                    is_final_story_segment=True,
                ),
                story="",
                beats=["Goblin1 waits behind the counter."],
                completed_beat_ids=set(),
                recent_results=[],
                current_segment=1,
                total_segments=1,
                segment_length=6,
                total_length=6,
                subject_definitions=minimax.world_state_subject_definitions(
                    "", opening_world_state,
                ),
                conditioning_mode="initial",
                world_state=opening_world_state,
            )
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("At 00:01.000, Goblin1 waits beside the counter."),
        ]))
        validators = (
            mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
        )
        with (
            mock.patch("minimax.ask_llm", request),
            validators[0],
            validators[1],
            validators[2],
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-raw-only", {"source_sha256": "source"}
            )

        self.assertNotIn("state_actions", payload["request1_result"])
        self.assertNotIn("state_actions_dry_run_accepted", payload["request1_result"])
        self.assertEqual(bundle["world_state_opening"], opening_world_state)
        self.assertEqual(
            bundle["world_state_opening"]["props"][mug_id]["placement"],
            {"kind": "held", "subject_id": goblin_id},
        )
        request1 = next(
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene_creative"
        )
        prompt = "\n".join(
            str(message.get("content") or "")
            for message in request1.args[0]
        )
        self.assertIn("SUBJECT LOCATIONS (WorldState)", prompt)
        self.assertIn("PROPS:\nWorldState placement", prompt)
        self.assertIn("Goblin1: in Room", prompt)
        self.assertIn("mug: held by Goblin1", prompt)
        self.assertIn("held props are exclusive", prompt)
        self.assertNotIn("REGISTERED WORLDSTATE VOCABULARY", prompt)
        self.assertNotIn("STATE ACTION CONTRACT", prompt)
        self.assertNotIn("state_actions", prompt)
        self.assertIsNone(request1.kwargs["response_format"])
        self.assertIn("CURRENT BEAT", prompt)

    def test_director_system_prompt_has_no_state_action_contract(self):
        for prompt in (
            minimax.ADD_SCENE_TIMING_REFINER_SYSTEM_TEMPLATE,
            minimax.ADD_CAMERA_REFINER_SYSTEM,
        ):
            self.assertNotIn("state_actions", prompt)
            self.assertNotIn("registered entity names", prompt)

    def test_h3_soundscape_prompt_is_extraction_only(self):
        messages = minimax.build_h3_soundscape_messages(
            "At 00:01.000, Amy closes the door."
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Extract only the overall soundscape", text)
        self.assertIn("only sounds a microphone could hear", text)
        self.assertIn("Omit lighting", text)
        self.assertIn("Do not invent optional or merely plausible sounds", text)
        self.assertIn("Do not rewrite", text)
        self.assertNotIn("non_diegetic_music", text)
        self.assertIn("Return exactly overall_soundscape", text)

    def test_h3_music_prompt_is_generation_only(self):
        messages = minimax.build_h3_music_messages(
            "At 00:01.000, Amy closes the door.",
            conditioning_mode="continuation",
            previous_music="Soft warm piano, calm and understated.",
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Generate only the non-diegetic music", text)
        self.assertIn("PREVIOUS MUSIC", text)
        self.assertIn("Soft warm piano, calm and understated.", text)
        self.assertIn("defines only how the score begins", text)
        self.assertIn("make the score follow its emotional arc", text)
        self.assertIn("MUST explicitly transition", text)
        self.assertIn("same emotional state throughout", text)
        self.assertIn("Do not name characters, narrate scene actions", text)
        self.assertIn("or synchronize the score to specific actions", text)
        self.assertIn("Return one musical cue sentence", text)
        self.assertIn("at most 24", text)
        self.assertIn("Do not name characters", text)
        self.assertNotIn("overall_soundscape", text)
        self.assertIn("Continue the established score seamlessly.", text)
        self.assertIn("Return exactly non_diegetic_music", text)

    def test_h3_music_continuation_treats_previous_music_as_start_only(self):
        messages = minimax.build_h3_music_messages(
            (
                "At 00:00.000, breakfast remains calm.\n"
                "At 00:03.000, an attacker crashes through the window.\n"
                "At 00:06.000, the room erupts into a violent struggle."
            ),
            conditioning_mode="continuation",
            previous_music="Cheerful light piano and playful strings.",
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Cheerful light piano and playful strings.", text)
        self.assertIn("PREVIOUS MUSIC describes only the musical state", text)
        self.assertIn("more threatening, violent, frightening", text)
        self.assertIn("MUST explicitly transition", text)
        self.assertNotIn("transition only when", text)

    def test_h3_soundscape_prompt_rejects_visual_only_facts(self):
        messages = minimax.build_h3_soundscape_messages(
            "At 00:01.000, sunlight crosses the table while Mira looks left."
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("only sounds a microphone could hear", text)
        self.assertIn("Omit lighting", text)
        self.assertIn("silent gestures", text)
        self.assertIn("pistol still fired", text)
        self.assertIn("Each listed item must itself name an audible event", text)
        self.assertIn("Do not turn motion verbs into sounds", text)
        self.assertIn("rising steam", text)

    @mock.patch("minimax.ask_llm")
    def test_audio_contract_retries_malformed_soundscape(self, ask_llm):
        ask_llm.side_effect = [
            "Mark closes a door with a thud.",
            {"status": "ok", "timestamps": ["00:00.000"]},
            "At 00:00.000, Mark closes a door with a thud.",
            {"overall_soundscape": ":["},
            {"overall_soundscape": "door thud"},
            {"non_diegetic_music": "Sparse piano."},
        ]
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "door thud")
        sound_calls = [
            call for call in ask_llm.call_args_list
            if call.kwargs["history_metadata"]["purpose"] == "director_h3_soundscape"
        ]
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in sound_calls],
            [1, 2],
        )

    def test_h3_soundscape_parser_rejects_na_when_raw_has_explicit_audio(self):
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result(
                {"overall_soundscape": "N/A"},
                raw_scene=(
                    "At 00:01.000, footsteps echo down the corridor. "
                    "At 00:03.000, a groan rattles the door."
                ),
            )

    def test_h3_soundscape_parser_allows_na_without_audio_cues(self):
        self.assertEqual(
            minimax.parse_h3_soundscape_result(
                {"overall_soundscape": "N/A"},
                raw_scene="At 00:01.000, Mira silently turns toward the window.",
            ),
            "N/A",
        )

    def test_h3_soundscape_parser_rejects_punctuation_only_output(self):
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result({
                "overall_soundscape": ":[",
            })

    def test_h3_music_parser_rejects_overlong_cue(self):
        overlong = " ".join(["music"] * 33)
        with self.assertRaises(ValueError):
            minimax.parse_h3_music_result({
                "non_diegetic_music": overlong,
            })

    def test_h3_audio_parsers_accept_only_their_single_field(self):
        soundscape = minimax.parse_h3_soundscape_result({
            "overall_soundscape": "Door slam.",
        })
        music = minimax.parse_h3_music_result({
            "non_diegetic_music": "Low strings.",
        })
        self.assertEqual(soundscape, "Door slam.")
        self.assertEqual(music, "Low strings.")
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result({
                "overall_soundscape": "Door slam.",
                "non_diegetic_music": "Low strings.",
            })
        with self.assertRaises(ValueError):
            minimax.parse_h3_music_result({
                "overall_soundscape": "Door slam.",
                "non_diegetic_music": "Low strings.",
            })

    def test_raw_subject_resolution_prompt_is_post_raw_and_narrow(self):
        messages = minimax.build_director_raw_subject_resolution_messages(
            (
                "At 00:01.000, a guard enters.\n"
                "At 00:04.000, another guard blocks the door."
            ),
            "<Subject 1> is Mara.\n<Subject 2> is Guard1, continued from <Video 1>.",
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("unnamed foreground animate identities", text)
        self.assertIn("finalized timed RAW scene", text)
        self.assertIn("Keep already-named Subjects unchanged", text)
        self.assertIn("most specific explicit role/species plus an integer", text)
        self.assertIn("one stable functional name", text)
        self.assertIn("Reuse a KNOWN SUBJECT when RAW continues", text)
        self.assertIn("Do not label interchangeable background crowds/groups", text)
        self.assertIn("KNOWN SUBJECTS", text)

    def test_raw_subject_resolution_accepts_only_identity_labeling(self):
        original = (
            "At 00:00.000, a guard enters the room.\n"
            "At 00:05.000, another guard blocks the door.\n"
            "End continuity state: both guards remain in the room."
        )
        resolved_timed = (
            "At 00:00.000, Guard1 enters the room.\n"
            "At 00:05.000, Guard2 blocks the door."
        )
        request = mock.Mock(return_value={
            "raw_scene": resolved_timed,
            "subject_names": ["Guard1", "Guard2"],
        })
        result, names = minimax.resolve_director_raw_scene_subjects(
            original,
            "<Subject 1> is Mara.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            resolved_timed
            + "\nEnd continuity state: both guards remain in the room.",
        )
        self.assertEqual(names, ["Guard1", "Guard2"])
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "director_raw_scene_visible_subject_resolution",
        )

    def test_raw_subject_resolution_bootstraps_identity_and_wardrobe_once(self):
        original = (
            "At 00:00.000, a beautiful female elf with long silver hair enters.\n"
            "At 00:05.000, the elf sits at the back table.\n"
            "End continuity state: the elf remains seated."
        )
        resolved_timed = (
            "At 00:00.000, Elf1, a beautiful female elf with long silver hair, enters.\n"
            "At 00:05.000, Elf1 sits at the back table."
        )
        request = mock.Mock(return_value={
            "raw_scene": resolved_timed,
            "subject_names": ["Elf1"],
            "subject_descriptions": {
                "Elf1": "Elf1 is a beautiful female elf with long silver hair."
            },
            "subject_wardrobes": {
                "Elf1": {
                    "upper": "forest-green fitted tunic",
                    "lower": "brown trousers",
                    "footwear": "soft leather boots",
                    "other": "N/A",
                }
            },
        })

        result, names, descriptions, wardrobes = (
            minimax.resolve_director_raw_scene_subjects(
                original,
                "<Subject 1> is Amy.",
                llm_request=request,
                segment_seconds=6.0,
                return_subject_bootstrap=True,
                story_context=(
                    "Amy serves fantasy patrons in a refined medieval tavern where "
                    "humanoid guests wear practical period clothing."
                ),
            )
        )

        self.assertIn("Elf1 sits at the back table", result)
        self.assertEqual(names, ["Elf1"])
        self.assertEqual(
            descriptions,
            {"Elf1": "Elf1 is a beautiful female elf with long silver hair."},
        )
        self.assertEqual(
            wardrobes["Elf1"],
            {
                "upper": "forest-green fitted tunic",
                "lower": "brown trousers",
                "footwear": "soft leather boots",
                "other": "N/A",
            },
        )
        prompt = request.call_args.args[0]
        self.assertIn("explicit non-clothing appearance facts", prompt[0]["content"])
        self.assertIn("choose one simple setting-appropriate outfit now", prompt[0]["content"])
        self.assertIn("Use STORY CONTEXT only when RAW does not specify clothing", prompt[0]["content"])
        self.assertIn("humanoid guests wear practical period clothing", prompt[1]["content"])
        self.assertIn("subject_wardrobes", prompt[1]["content"])

    def test_raw_subject_resolution_preserves_existing_identifiers(self):
        original = (
            "At 00:00.000, Will and Amber watch Zombie2 enter.\n"
            "At 00:05.000, Zombie2 falls beside Amy.\n"
            "End continuity state: Will and Amber remain nearby; Zombie2 is down."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:00.000, Will1 and Amber1 watch Zombie2_1 enter.\n"
                "At 00:05.000, Zombie2_1 falls beside Amy."
            ),
            "subject_names": ["Will1", "Amber1", "Zombie2_1"],
        })
        result, names = minimax.resolve_director_raw_scene_subjects(
            original,
            (
                "<Subject 1> is Amy.\n"
                "<Subject 2> is Will.\n"
                "<Subject 3> is Amber."
            ),
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertIn("Will1 and Amber1 watch Zombie2 enter.", result)
        self.assertIn("Zombie2 falls beside Amy.", result)
        self.assertIn("Will1", result)
        self.assertIn("Amber1", result)
        self.assertNotIn("Zombie2_1", result)
        self.assertEqual(names, ["Will1", "Amber1"])

    def test_raw_subject_resolution_rejects_timestamp_drift(self):
        original = (
            "At 00:01.000, a guard enters.\n"
            "At 00:04.000, another guard blocks the door.\n"
            "End continuity state: both guards remain in the room."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:01.000, Guard1 enters.\n"
                "At 00:05.000, Guard2 blocks the door."
            ),
            "subject_names": ["Guard1", "Guard2"],
        })
        with self.assertRaisesRegex(ValueError, "changed timestamps"):
            minimax.resolve_director_raw_scene_subjects(
                original,
                "",
                llm_request=request,
                segment_seconds=6.0,
            )

    def test_raw_subject_resolution_rejects_timestamp_outside_effective_timeline(self):
        original = (
            "At 00:00.000, a guard enters.\n"
            "At 00:08.917, the guard sits.\n"
            "End continuity state: the guard sits by the door."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:00.000, Guard1 enters.\n"
                "At 00:08.917, Guard1 sits."
            ),
            "subject_names": ["Guard1"],
        })
        with self.assertRaisesRegex(ValueError, "timestamp must be before"):
            minimax.resolve_director_raw_scene_subjects(
                original,
                "<Subject 1> is Mara.",
                llm_request=request,
                segment_seconds=8.0 + 22 / 24,
            )

    def test_raw_pronoun_resolution_prompt_is_narrow(self):
        messages = minimax.build_director_pronoun_resolution_messages(
            (
                "At 00:01.000, Amy pushes Will and Amber toward the closet.\n"
                "At 00:04.000, she pushes them inside.\n"
                "End continuity state: they are inside the closet."
            ),
            (
                "<Subject 1> is Amy.\n"
                "<Subject 2> is Will.\n"
                "<Subject 3> is Amber."
            ),
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Change only the pronoun itself", text)
        self.assertIn("especially she, he, they, him, her, them", text)
        self.assertIn("replace only clear personal subject/object pronouns", text)
        self.assertIn("Prefer names for standalone they/them", text)
        self.assertIn("keep 'her hand', 'his collar', and 'their bowls' as written", text)
        self.assertIn("Do not add, remove, combine, split, or reinterpret actions", text)
        self.assertIn("- Do not alter timestamps.", messages[0]["content"])
        self.assertTrue(
            all(
                line.startswith("- ")
                for line in messages[0]["content"].splitlines()
            )
        )

    def test_raw_pronoun_resolution_accepts_name_only_rewrite(self):
        original = (
            "At 00:00.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, she pushes them into the closet.\n"
            "End continuity state: they are inside the closet."
        )
        resolved_timed = (
            "At 00:00.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, Amy pushes Will and Amber into the closet."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            resolved_timed + "\nEnd continuity state: they are inside the closet.",
        )
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "director_raw_scene_pronoun_resolution",
        )

    def test_raw_pronoun_resolution_accepts_unchanged_valid_timestamps(self):
        original = (
            "At 00:00.000, Amy opens the door.\n"
            "At 00:05.500, Amy closes it.\n"
            "End continuity state: Amy stands by the closed door."
        )
        timed_scene = original.split("\nEnd continuity state:", 1)[0]
        request = mock.Mock(return_value={"raw_scene": timed_scene})
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(result, original)

    def test_raw_pronoun_resolution_preserves_clear_local_possessives(self):
        original = (
            "At 00:00.000, she looks at Will and touches her palm.\n"
            "At 00:04.500, Will gives her their bowls.\n"
            "End continuity state: Amy stands beside Will."
        )
        resolved_timed = (
            "At 00:00.000, Amy looks at Will and touches her palm.\n"
            "At 00:04.500, Will gives Amy their bowls."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            resolved_timed + "\nEnd continuity state: Amy stands beside Will.",
        )

    def test_raw_pronoun_resolution_logs_replacements(self):
        original = (
            "At 00:00.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, she pushes them into the closet.\n"
            "End continuity state: they are inside the closet."
        )
        resolved_timed = (
            "At 00:00.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, Amy pushes Will and Amber into the closet."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        with mock.patch("builtins.print") as printer:
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
                llm_request=request,
                segment_seconds=6.0,
            )
        output = "\n".join(
            str(call.args[0]) for call in printer.call_args_list if call.args
        )
        self.assertIn("Checking pronouns segment:", output)
        self.assertIn("replaced", output)
        self.assertIn("Amy pushes Will and Amber", output)

    def test_raw_pronoun_resolution_preserves_end_state_exactly(self):
        original = (
            "At 00:00.000, Amy looks at Will.\n"
            "At 00:04.500, she waves to him.\n"
            "End continuity state: she stands beside him."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:00.000, Amy looks at Will.\n"
                "At 00:04.500, Amy waves to Will."
            )
        })
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertTrue(
            result.endswith("End continuity state: she stands beside him.")
        )
        sent = request.call_args.args[0][-1]["content"]
        self.assertNotIn("End continuity state:", sent)

    def test_raw_pronoun_resolution_rejects_timestamp_drift(self):
        original = (
            "At 00:01.000, Amy grabs Will.\n"
            "At 00:04.500, she pushes him into the closet.\n"
            "End continuity state: Will is inside."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:01.000, Amy grabs Will.\n"
                "At 00:05.000, Amy pushes Will into the closet."
            )
        })
        with self.assertRaisesRegex(ValueError, "changed timestamps"):
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy. <Subject 2> is Will.",
                llm_request=request,
                segment_seconds=6.0,
            )

    def test_raw_pronoun_resolution_rejects_job35_timestamp_change(self):
        original = (
            "At 00:00.000, Amy opens the door.\n"
            "At 00:07.250, Amy closes it.\n"
            "End continuity state: Amy stands by the closed door."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:00.000, Amy opens the door.\n"
                "At 00:08.167, Amy closes it."
            )
        })
        with self.assertRaisesRegex(ValueError, "changed timestamps"):
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy.",
                llm_request=request,
                segment_seconds=8.0,
            )

    def test_raw_pronoun_resolution_rejects_timestamp_order_and_count_changes(self):
        original = (
            "At 00:00.000, Amy enters.\n"
            "At 00:03.000, Amy waves.\n"
            "At 00:07.000, Amy sits.\n"
            "End continuity state: Amy sits by the door."
        )
        altered_scenes = (
            (
                "At 00:00.000, Amy enters.\n"
                "At 00:07.000, Amy waves.\n"
                "At 00:03.000, Amy sits."
            ),
            (
                "At 00:00.000, Amy enters.\n"
                "At 00:07.000, Amy sits."
            ),
        )
        for altered_scene in altered_scenes:
            with self.subTest(altered_scene=altered_scene):
                request = mock.Mock(return_value={"raw_scene": altered_scene})
                with self.assertRaisesRegex(ValueError, "changed timestamps"):
                    minimax.resolve_director_raw_scene_pronouns(
                        original,
                        "<Subject 1> is Amy.",
                        llm_request=request,
                        segment_seconds=8.0,
                    )

    def test_raw_pronoun_resolution_rejects_timestamp_outside_duration(self):
        original = (
            "At 00:00.000, Amy enters.\n"
            "At 00:08.167, Amy sits.\n"
            "End continuity state: Amy sits by the door."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:00.000, Amy enters.\n"
                "At 00:08.167, Amy sits."
            )
        })
        with self.assertRaisesRegex(ValueError, "out-of-range timestamps"):
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy.",
                llm_request=request,
                segment_seconds=8.0,
            )

    def test_raw_scene_physical_prompt_is_narrow_and_checks_order(self):
        messages = minimax.build_director_raw_scene_physical_messages(
            "Amy pushes Will into the closet and closes the door.",
            (
                "At 00:02.000, Amy closes the closet door.\n"
                "At 00:04.000, Will enters the closet."
            ),
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertEqual(
            messages[0]["content"],
            "Validate only subject movement in the RAW SCENE.  Update subject "
            "positions after each sentence internally and determine if the "
            "following sentence's actions, whether movement or not, can occur "
            "spatially.\n\nReturn only one JSON object with boolean valid and "
            "string issue. Report only the first concrete problem.",
        )
        self.assertIn("KNOWN SUBJECT STATE", text)
        self.assertIn("CURRENT BEAT", text)
        self.assertIn("STATIC SETTING AUTHORITY", text)
        self.assertIn("RAW SCENE", text)
        self.assertIn('{"valid": true, "issue": ""}', text)


    def test_request_one_repairs_physically_incoherent_raw_scene(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = (
            "Amy pushes Will into the closet and closes the door behind him."
        )
        bad = director_response(
            "At 00:01.000, Amy closes the closet door.\n"
            "At 00:04.500, Will steps into the closet."
        )
        good_raw = director_response(
            "At 00:00.000, Will steps into the closet.\n"
            "At 00:04.500, Amy closes the closet door behind him."
        )["raw_scene"]
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            bad,
            good_raw,
        ]))
        physical = mock.Mock(side_effect=[
            {"valid": True, "issue": ""},
            {"valid": False, "issue": "The door closes before Will enters."},
            {"valid": True, "issue": ""},
        ])
        prop_state = mock.Mock(return_value={"valid": True, "issue": ""})
        timing = mock.Mock(return_value={"valid": True, "issue": ""})
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch(
                "minimax.validate_director_raw_scene_physical",
                physical,
            ),
            mock.patch(
                "minimax.validate_director_raw_scene_prop_state",
                prop_state,
            ),
            mock.patch(
                "minimax.validate_director_raw_scene_timing",
                timing,
            ),
            mock.patch("minimax.console_log") as console_log,
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 4)  # creative, timing, camera, repair
        self.assertEqual(physical.call_count, 3)
        self.assertEqual(prop_state.call_count, 1)
        self.assertEqual(timing.call_count, 1)
        self.assertIn("Will steps into the closet", payload["raw_scene"])
        log_messages = [
            str(call.args[0]) for call in console_log.call_args_list if call.args
        ]
        physical_verdicts = [
            json.loads(message.removeprefix("DIRECTOR RAW VALIDATOR RESULT "))
            for message in log_messages
            if message.startswith("DIRECTOR RAW VALIDATOR RESULT ")
        ]
        self.assertEqual(
            [item["valid"] for item in physical_verdicts if item["validator"] == "physical/spatial"],
            [False, True],
        )
        self.assertTrue(any(
            message.startswith("DIRECTOR RAW REPAIR DISPATCH ")
            and "director_raw_scene_repair" in message
            and "door closes before Will enters" in message
            for message in log_messages
        ))
        repair_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose")
            == "director_raw_scene_repair"
        ]
        self.assertEqual(len(repair_calls), 1)
        repair_call = repair_calls[0]
        self.assertIsNone(repair_call.kwargs["response_format"])
        self.assertFalse(repair_call.kwargs["parse_json_response"])
        self.assertEqual(repair_call.kwargs["history_metadata"]["attempt"], 1)
        self.assertIn(
            "Fix the RAW PROMPT based on the VALIDATOR ERRORS.",
            repair_call.args[0][0]["content"],
        )
        self.assertEqual(
            repair_call.args[0][-1]["content"],
            "RAW PROMPT\n"
            + "At 00:00.000, Amy closes the closet door.\n"
            + "At 00:00.100, Will steps into the closet.\n"
            + "End continuity state: Will steps into the closet."
            + "\n\nVALIDATOR ERRORS:\n"
            "- The door closes before Will enters.",
        )
        self.assertEqual(
            physical.call_args_list[2].args[1],
            minimax._normalize_director_raw_scene_structure(
                good_raw, segment_seconds=6.0
            ).strip(),
        )

    def test_five_failed_raw_repairs_regenerate_director_raw(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = "Amy pushes Will into the closet and closes the door."
        bad = director_response(
            "At 00:01.000, Amy closes the closet door.\n"
            "At 00:04.500, Will steps into the closet."
        )
        good = director_response(
            "At 00:00.000, Will enters the closet.\n"
            "At 00:04.500, Amy closes the closet door behind him."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            bad,
            *([bad["raw_scene"]] * minimax.DIRECTOR_RAW_SCENE_REPAIR_ATTEMPTS),
            good,
        ]))
        first_attempt_physical_calls = 0

        def physical_result(*args, **kwargs):
            nonlocal first_attempt_physical_calls
            attempt = (kwargs.get("history_metadata") or {}).get("attempt", 1)
            if attempt > 1:
                return {"valid": True, "issue": ""}
            first_attempt_physical_calls += 1
            if first_attempt_physical_calls == 1:
                return {"valid": True, "issue": ""}
            return {
                "valid": False,
                "issue": "The door closes before Will enters.",
            }

        physical = mock.Mock(side_effect=physical_result)
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_director_raw_scene_physical", physical),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        director_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "add_scene_timing_refiner"
        ]
        repair_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene_repair"
        ]
        creative_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose")
            == "director_raw_scene_creative"
        ]
        self.assertEqual(len(creative_calls), 2)
        self.assertEqual(len(director_calls), 2)
        self.assertEqual(len(repair_calls), 5)
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in repair_calls],
            [1, 2, 3, 4, 5],
        )
        self.assertIn("Will enters the closet", payload["raw_scene"])

    def test_director_raw_repair_prompt_matches_requested_contract(self):
        raw = "At 00:00.000, Mira remains at the doorway."
        messages = minimax.build_director_raw_scene_repair_messages(
            raw,
            ["Mira crosses the room without visible movement.", "The support changes."],
        )
        self.assertEqual(
            messages[0]["content"],
            "Fix the RAW PROMPT based on the VALIDATOR ERRORS.\n"
            "Only alter what is needed to fix the error(s).\n"
            "Return the altered RAW PROMPT.",
        )
        self.assertEqual(
            messages[1]["content"],
            "RAW PROMPT\n"
            "At 00:00.000, Mira remains at the doorway.\n\n"
            "VALIDATOR ERRORS:\n"
            "- Mira crosses the room without visible movement.\n"
            "- The support changes.",
        )

    def test_request_one_retries_prop_state_failure_separately(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = (
            "Amy pours brew into a cup and hands the cup to Will."
        )
        bad = director_response(
            "At 00:01.000, Amy pours brew onto the table.\n"
            "At 00:04.500, Amy hands the empty cup to Will."
        )
        good = director_response(
            "At 00:00.000, Amy pours brew into the cup.\n"
            "At 00:04.500, Amy hands the filled cup to Will."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            bad,
            good["raw_scene"],
        ]))
        physical = mock.Mock(return_value={"valid": True, "issue": ""})
        prop_state = mock.Mock(side_effect=[
            {"valid": False, "issue": "The brew is redirected onto the table."},
            {"valid": True, "issue": ""},
        ])
        timing = mock.Mock(return_value={"valid": True, "issue": ""})
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_director_raw_scene_physical", physical),
            mock.patch("minimax.validate_director_raw_scene_prop_state", prop_state),
            mock.patch("minimax.validate_director_raw_scene_timing", timing),
            mock.patch("minimax.console_log") as console_log,
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 4)  # creative, timing, camera, repair
        self.assertEqual(physical.call_count, 3)
        self.assertEqual(prop_state.call_count, 2)
        self.assertEqual(timing.call_count, 1)
        self.assertIn("filled cup", payload["raw_scene"])
        request_prompts = [
            call.args[0][-1]["content"]
            for call in semantic_calls
            if call.args and isinstance(call.args[0], list) and call.args[0]
            and isinstance(call.args[0][-1], dict)
        ]
        self.assertTrue(any(
            "VALIDATOR ERRORS:\n- The brew is redirected onto the table." in prompt
            for prompt in request_prompts
        ))
        log_messages = [
            str(call.args[0]) for call in console_log.call_args_list if call.args
        ]
        prop_verdicts = [
            json.loads(message.removeprefix("DIRECTOR RAW VALIDATOR RESULT "))
            for message in log_messages
            if message.startswith("DIRECTOR RAW VALIDATOR RESULT ")
            and '"validator": "prop/state"' in message
        ]
        self.assertEqual(
            [item["valid"] for item in prop_verdicts],
            [False, True],
        )
        repair_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose")
            == "director_raw_scene_repair"
        ]
        self.assertEqual(len(repair_calls), 1)
        self.assertEqual(
            repair_calls[0].kwargs["history_metadata"]["validator"],
            "PROP/STATE",
        )

    def test_structure_dialogue_and_timing_failures_use_raw_repair(self):
        cases = [
            (
                "_director_raw_scene_structure_errors",
                "SHOT SCRIPT",
                ["A required shot-script field is missing."],
                [],
            ),
            (
                "director_required_dialogue_issue",
                "DIALOGUE",
                "Required direct dialogue is missing.",
                "",
            ),
            (
                "validate_director_raw_scene_timing",
                "TIMING",
                {"valid": False, "issue": "The movement is compressed."},
                {"valid": True, "issue": ""},
            ),
        ]
        for function_name, expected_validator, first_result, next_result in cases:
            with self.subTest(validator=expected_validator):
                bundle = segment_bundle()
                bundle["current_beat_text"] = "Mira crosses the room and reaches the door."
                initial_raw = director_response(
                    "At 00:01.000, Mira remains beside the table.\n"
                    "At 00:04.500, Mira reaches the door."
                )
                repaired_raw = (
                    "At 00:00.000, Mira leaves the table.\n"
                    "At 00:04.500, Mira reaches the door."
                )
                request = mock.Mock(side_effect=pipeline_llm_side_effect([
                    initial_raw,
                    repaired_raw,
                ]))
                validator_patch = (
                    nullcontext()
                    if function_name == "validate_director_raw_scene_timing"
                    else mock.patch(
                        "minimax." + function_name,
                        side_effect=(
                            [
                                {"valid": True, "issue": ""},
                                first_result,
                                next_result,
                            ]
                            if function_name == "validate_director_raw_scene_physical"
                            else [first_result, next_result]
                        ),
                    )
                )
                timing_patch = mock.patch(
                    "minimax.validate_director_raw_scene_timing",
                    side_effect=(
                        [first_result, next_result]
                        if function_name == "validate_director_raw_scene_timing"
                        else None
                    ),
                    return_value=(
                        None
                        if function_name == "validate_director_raw_scene_timing"
                        else {"valid": True, "issue": ""}
                    ),
                )
                with (
                    mock.patch("minimax.ask_llm", request),
                    validator_patch,
                    mock.patch(
                        "minimax.validate_director_raw_scene_physical",
                        return_value={"valid": True, "issue": ""},
                    ),
                    mock.patch(
                        "minimax.validate_director_raw_scene_prop_state",
                        return_value={"valid": True, "issue": ""},
                    ),
                    timing_patch,
                    mock.patch("minimax.console_log"),
                    mock.patch("builtins.print"),
                ):
                    payload = minimax.request_segment_llm(
                        bundle, [], "run-id", {"source_sha256": "source-hash"}
                    )

                repair_calls = [
                    call for call in request.call_args_list
                    if call.kwargs.get("history_metadata", {}).get("purpose")
                    == "director_raw_scene_repair"
                ]
                timing_calls = [
                    call for call in request.call_args_list
                    if call.kwargs.get("history_metadata", {}).get("purpose")
                    == "add_scene_timing_refiner"
                ]
                self.assertEqual(len(repair_calls), 1)
                self.assertEqual(len(timing_calls), 1)
                self.assertEqual(
                    sum(
                        call.kwargs.get("history_metadata", {}).get("purpose")
                        == "director_raw_scene_creative"
                        for call in request.call_args_list
                    ),
                    1,
                )
                self.assertEqual(
                    repair_calls[0].kwargs["history_metadata"]["validator"],
                    expected_validator,
                )
                self.assertIn("Mira reaches the door", payload["raw_scene"])

    def test_python_structure_normalization_leaves_only_semantic_retry_blockers(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = "Amy completes the exchange with Will."
        early = {
            "raw_scene": (
                "At 00:00.000, Amy begins the exchange.\n"
                "At 00:03.000, Amy finishes the exchange.\n"
                "End continuity state: Amy and Will remain together."
            ),
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
        }
        good = director_response(
            "At 00:00.000, Amy begins the exchange.\n"
            "At 00:04.500, Amy visibly transfers the mug to Will."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            early,
            good["raw_scene"],
        ]))
        physical = mock.Mock(return_value={"valid": True, "issue": ""})
        prop_state = mock.Mock(side_effect=[
            {
                "valid": False,
                "issue": "mug_1 is still listed as held by Amy; show the transfer to Will.",
            },
            {"valid": True, "issue": ""},
        ])
        timing = mock.Mock(return_value={"valid": True, "issue": ""})

        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_director_raw_scene_physical", physical),
            mock.patch("minimax.validate_director_raw_scene_prop_state", prop_state),
            mock.patch("minimax.validate_director_raw_scene_timing", timing),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )

        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 4)  # creative, timing, camera, repair
        repair_prompt = next(
            call.args[0][-1]["content"]
            for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose")
            == "director_raw_scene_repair"
        )
        self.assertIn("VALIDATOR ERRORS:", repair_prompt)
        self.assertIn("mug_1 is still listed as held by Amy", repair_prompt)
        self.assertIn("visibly transfers the mug", payload["raw_scene"])

    def test_request_one_completion_self_report_is_non_blocking(self):
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("Mark starts the action.", beat_complete=False),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 3)
        self.assertTrue(payload["request1_result"]["beat_complete"])
        self.assertEqual(
            payload["request1_result"]["completion_metadata_source"],
            "validated_split_raw_pipeline",
        )
        self.assertIn("Mark starts the action.", payload["raw_scene"])


    def test_request_one_retries_only_when_raw_scene_is_unusable(self):
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            {"raw_scene": ""},
            director_response("Mark completes the action."),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 4)
        self.assertIn("Mark completes the action.", payload["raw_scene"])

    def test_request_one_python_normalizes_missing_end_state_marker_without_retry(self):
        malformed = {
            "raw_scene": (
                "At 00:00.000, Mark reaches for the latch.\n"
                "At 00:04.500, Mark closes the hatch."
            ),
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
        }
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            malformed,
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 3)
        self.assertEqual(payload["raw_scene"].count("End continuity state:"), 1)
        self.assertTrue(
            payload["raw_scene"].endswith(
                "End continuity state: Mark closes the hatch."
            )
        )

    def test_request_one_does_not_repair_semantic_omission_during_baseline(self):
        bundle = segment_bundle()
        bundle["messages"] = [{
            "role": "user",
            "content": (
                "CURRENT BEAT: Amy opens a hidden panel and retrieves three tools.\n"
                "NEXT BEAT: Amy exits the room."
            ),
        }]
        omitted_scene = "Amy opens the panel and retrieves only two tools."
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(omitted_scene, beat_complete=False),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 3)
        self.assertIn("only two tools", payload["raw_scene"])

    def test_request_two_result_does_not_contain_completion_metadata(self):
        parsed = minimax.parse_h3_formatter_result(formatter_response("[Shot 1] Mark waits."))
        self.assertNotIn("completed_beat_ids", parsed)

    def test_missing_reported_completion_does_not_advance_beat_plan(self):
        with self.assertRaisesRegex(RuntimeError, "refusing to advance"):
            minimax.apply_reported_beat_completions(
                ["Mark completes the action."],
                set(),
                [],
                1,
            )

    def test_h3_action_preservation_prompt_ignores_harmless_incidental_detail(self):
        messages = minimax.build_h3_action_preservation_messages(
            (
                "A deep thud sounds from the front door as it opens slightly; "
                "a small crack appears at the gap."
            ),
            "A deep thud sounds from the front door as it opens slightly.",
            current_beat="A thud at the front door interrupts the kitchen.",
        )
        prompt = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("CURRENT BEAT", prompt)
        self.assertIn("Do not fail harmless decorative clauses", prompt)
        self.assertIn("small crack appears", prompt)

    def test_h3_formatter_repairs_named_dialogue_speaker_id(self):
        parsed = minimax.parse_h3_formatter_result(
            {
                "subject_genders": {},
                "detailed_description": (
                    '[Shot 1] Will calls out (S1) <d>[English] Amy!</d>'
                ),
                "overall_soundscape": "Will calls out.",
                "non_diegetic_music": "N/A",
            },
            subject_definitions=(
                "<Subject 1> is Amy, a woman.\n"
                "<Subject 2> is Will, a boy."
            ),
        )
        self.assertIn("Will calls out (S2) <d>[English] Amy!</d>", parsed["detailed_description"])
        self.assertNotIn("Will calls out (S1)", parsed["detailed_description"])

    def test_h3_formatter_parses_subject_genders(self):
        parsed = minimax.parse_h3_formatter_result(
            "subject_genders: {\"Werewolf\": \"unknown\", "
            "\"Captain\": \"male\"}\n\n"
            "detailed_description: [Shot 1] Captain enters.\n\n"
            "overall_soundscape: Footsteps.\n\n"
            "non_diegetic_music: N/A"
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Werewolf": "unknown", "Captain": "male"},
        )

    def test_subject_gender_aliases_collapse_to_one_canonical_name(self):
        parsed = minimax.parse_h3_formatter_result(
            {
                "subject_genders": {
                    "<Subject 1>": "female",
                    "<Subject 2>": "male",
                    "<Subject 3>": "male",
                    "Jill": "female",
                    "Ben": "male",
                    "Frank": "male",
                },
                "detailed_description": "[Shot 1] Jill, Ben, and Frank enter.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            subject_definitions=(
                "<Subject 1> is Jill, a woman referenced in <Picture 1>.\n"
                "<Subject 2> is Ben, a man referenced in <Picture 2>.\n"
                "<Subject 3> is Frank, a man referenced in <Picture 3>."
            ),
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Jill": "female", "Ben": "male", "Frank": "male"},
        )

    def test_h3_formatter_parses_json_text_response(self):
        parsed = minimax.parse_h3_formatter_result(
            json.dumps({
                "subject_genders": {"Werewolf": "unknown"},
                "detailed_description": "[Shot 1] Werewolf enters.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            })
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["subject_genders"], {"Werewolf": "unknown"})

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_does_not_add_non_speaking_subject_ids(
        self, ask_llm
    ):
        bundle = segment_bundle()
        bundle["subject_definitions"] = (
            "<Subject 1> is Alice, referenced in <Picture 1>."
        )
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response("Alice walks over to the window."),
        ])

        payload = minimax.request_segment_llm(
            bundle,
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        description = payload["llm_result"]["detailed_description"]
        self.assertIn("Alice walks over to the window.", description)
        self.assertNotIn("Alice (S1)", description)

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_h3_response_format_repairs_malformed_json(self, post, _history):
        malformed = mock.Mock()
        malformed.status_code = 200
        malformed.raise_for_status.return_value = None
        malformed.json.return_value = {
            "choices": [{
                "message": {
                    "content": (
                        '{"subject_genders": {}, '
                        '"detailed_description": "[Shot 1] Amy enters.", '
                        '"overall_soundscape": "Footsteps.", '
                        '"non_diegetic_music": "N/A"'
                    )
                }
            }]
        }
        repaired = mock.Mock()
        repaired.status_code = 200
        repaired.raise_for_status.return_value = None
        repaired.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "subject_genders": {"Amy": "female"},
                        "detailed_description": "[Shot 1] Amy enters.",
                        "overall_soundscape": "Footsteps.",
                        "non_diegetic_music": "N/A",
                    })
                }
            }]
        }
        post.side_effect = [malformed, repaired]

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            retry_delay=0,
            response_format=minimax.H3_FORMATTER_RESPONSE_FORMAT,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertEqual(result["subject_genders"], {"Amy": "female"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["response_format"],
            minimax.H3_FORMATTER_RESPONSE_FORMAT,
        )
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])

    def test_h3_formatter_parses_markdown_labels(self):
        parsed = minimax.parse_h3_formatter_result(
            "### subject_genders: {}\n\n"
            "### Detailed Description: [Shot 1] Werewolf enters.\n\n"
            "### Overall Soundscape: Footsteps.\n\n"
            "### Non-Diegetic Music: N/A"
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")

    def test_append_h3_description_has_one_opener_and_no_leading_camera_move(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 2] Live-action, cinematic, The camera pushes in "
                    "toward Mark as Mark opens the door. At 00:02.000, the "
                    "camera pans right as Jill enters."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Mark, referenced in <Picture 1>.",
            segment_number=2,
            conditioning_mode="continuation",
        )

        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:",
            1,
        )[0]
        self.assertIn("[Shot 1] Live-action cinematic, seamless continuation. Mark opens the door.", description)
        self.assertEqual(description.count("Live-action cinematic"), 1)
        self.assertNotIn("camera pushes in", description.lower())
        self.assertIn("camera pans right", description.lower())

    def test_formatter_metadata_never_reaches_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "**subject_genders:**\n"
                    "{\n"
                    '  "Amy": "female"\n'
                    "}\n\n"
                    "[Shot 1] Amy walks."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "reference_alignment": (
                    'subject_genders: {"Amy": "female"}\n'
                    "Reference Image 1 establishes Amy's identity."
                ),
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("subject_genders", prompt)
        self.assertNotIn('{"Amy": "female"}', prompt)
        self.assertIn("[Shot 1] Amy walks.", prompt)
        self.assertIn("Reference Image 1 establishes Amy's identity.", prompt)

    def test_mistral_asterisks_never_reach_final_h3_prompt(self):
        formatted = minimax.format_mistral_prompt(
            {
                "detailed_description": "*[Shot 1]* **Amy** walks.",
                "overall_soundscape": "*Footsteps* echo.",
                "non_diegetic_music": "**N/A**",
                "completed_beat_ids": [1],
            },
            {
                "segment_number": 1,
                "segment_duration": 6.0,
                "completed_beat_ids": [],
            },
        )
        prompt = minimax.build_h3_prompt(
            formatted,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("*", prompt)

    def test_mistral_asterisks_in_continuity_never_reach_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Amy waits by the door.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            previous_state="*Amy remains by the door.*",
            segment_number=2,
            conditioning_mode="clean_refresh",
            continuity_state={
                "subjects": {
                    "Amy": {
                        "subject_id": 1,
                        "name": "Amy",
                        "position": "*by the door*",
                        "wardrobe": ["**blue coat**"],
                    },
                },
            },
        )

        self.assertNotIn("*", prompt)

    def test_h3_formatter_parses_json_metadata_followed_by_markdown_fields(self):
        parsed = minimax.parse_h3_formatter_result(
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )

        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")
        self.assertEqual(parsed["non_diegetic_music"], "N/A")
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})

    def test_multiple_fenced_formatter_blocks_do_not_reach_final_h3_prompt(self):
        raw = (
            "```ALIGNMENT\n"
            "Reference alignment: Amy's identity and the cabin remain consistent.\n"
            "```\n\n"
            "```H3\n"
            "detailed_description: [Shot 1] Amy enters the cabin.\n"
            "```\n\n"
            "```SOUND\n"
            "overall_soundscape: Footsteps on the wooden floor.\n"
            "```\n\n"
            "```MUSIC\n"
            "non_diegetic_music: Soft piano undercurrent.\n"
            "```"
        )

        parsed = minimax.parse_h3_formatter_result(raw)
        prompt = minimax.build_h3_prompt(
            parsed,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("```", prompt)
        self.assertIn("Reference alignment: Amy's identity and the cabin remain consistent.", prompt)
        self.assertIn("[Shot 1] Live-action cinematic, Amy enters the cabin.", prompt)
        self.assertIn("Footsteps on the wooden floor.", prompt)
        self.assertIn("non_diegetic_music: Soft piano undercurrent.", prompt)

    def test_h3_component_sanitizer_removes_standalone_fence_lines_only(self):
        value = "Before\n```JSON\nInside\n```\nafter"

        self.assertEqual(
            minimax.sanitize_h3_prompt_component(value),
            "Before\nInside\nafter",
        )

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_ask_llm_preserves_mixed_h3_response(self, post, _history):
        mixed = (
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": mixed}}]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            response_format=None,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertIsInstance(result, str)
        parsed = minimax.parse_h3_formatter_result(result)
        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})


    def test_director_prompt_is_compact_creative_contract(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_CREATIVE_SYSTEM_TEMPLATE.format(
            segment_length="8"
        )
        self.assertIn("expand on a single BEAT", prompt)
        self.assertIn("CURRENT BEAT is the story authority", prompt)
        self.assertIn("ASSIGNED SOURCE", prompt)
        self.assertNotIn("camera", prompt.casefold())
        self.assertNotIn("timestamp", prompt.casefold())
        self.assertNotIn("End continuity state", prompt)
        self.assertNotIn("beat_complete", prompt)
        self.assertEqual(minimax.build_director_rules(8, 8, 1, "", 1), "")

    def test_director_raw_scene_allows_action_to_finish_before_segment_end(self):
        raw_scene = (
            "At 00:00.000, Alex reaches for the latch.\n"
            "At 00:01.300, Alex closes the hatch.\n"
            "End continuity state: Alex stands beside the closed hatch."
        )
        errors = minimax._director_raw_scene_structure_errors(
            raw_scene,
            segment_seconds=8,
        )
        self.assertEqual(errors, [])

    def test_director_raw_scene_accepts_final_quarter_timeline(self):
        raw_scene = (
            "At 00:00.000, Alex reaches for the latch.\n"
            "At 00:06.200, Alex closes the hatch.\n"
            "End continuity state: Alex stands beside the closed hatch."
        )
        self.assertEqual(
            minimax._director_raw_scene_structure_errors(
                raw_scene,
                segment_seconds=8,
            ),
            [],
        )

    def test_preserved_barrier_unspecified_means_unchanged(self):
        issue = minimax.compare_director_barrier_state(
            {
                "barrier": "kitchen door window",
                "expected": "BROKEN",
                "source_state": "broken",
                "preserved": True,
            },
            "UNSPECIFIED",
        )
        self.assertEqual(issue, "")

    def test_director_final_state_contract_allows_small_route_details(self):
        base_messages = [
            {"role": "system", "content": "director"},
            {"role": "user", "content": "base"},
        ]
        bundle = {
            "segment": 2,
            "current_duration": 8,
            "conditioning_mode": "continuation",
            "messages": base_messages,
            "current_beat_text": "Amy moves Will and Amber into the basement.",
            "assigned_source": "Amy gets Will and Amber into the basement.",
            "assigned_state_effects": [
                {"op": "set_location", "entity": "Will", "value": "basement"},
                {"op": "set_location", "entity": "Amber", "value": "basement"},
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "contained",
                },
                {
                    "op": "set_containment",
                    "entity": "Amber",
                    "container": "basement",
                    "value": "contained",
                },
                {"op": "set_barrier_state", "entity": "door", "value": "locked"},
            ],
            "opening_state": (
                'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
                '{"characters":{"Amy":{"location":"home"},'
                '"Will":{"location":"home"},"Amber":{"location":"home"}},'
                '"environment":{"barriers":{"door":{"status":"open"}}}}'
            ),
            "registry_state": {"subjects": {}},
            "subject_definitions": "",
        }
        topology = minimax.build_director_barrier_topology_contract(
            bundle["assigned_state_effects"],
            "",
            bundle["assigned_source"],
            bundle["current_beat_text"],
            bundle["opening_state"],
        )
        binding = minimax.build_director_barrier_binding_contract(
            bundle["assigned_state_effects"]
        )
        self.assertTrue(topology)
        self.assertEqual(binding["destination"], "basement")
        route_line = (
            f"- People entering {binding['destination']} must use that "
            f"{binding['entity']}. Small route details are okay."
        )
        self.assertIn("Small route details are okay", route_line)

    def test_assigned_barrier_unspecified_still_fails(self):
        issue = minimax.compare_director_barrier_state(
            {
                "barrier": "kitchen door window",
                "expected": "BROKEN",
                "source_state": "broken",
            },
            "UNSPECIFIED",
        )
        self.assertIn("must end broken", issue)

    def test_validation_prompt_checks_scope_creep_into_exact_next_beat(self):
        messages = minimax.build_director_continuity_validation_messages(
            opening_state={},
            active_beat_text="Amy opens the gate.",
            detailed_description="Amy opens the gate and enters the vault.",
            segment_number=1,
            next_beat_text="Amy enters the vault.",
        )

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("NEXT BEAT\nAmy enters the vault.", combined)
        self.assertIn("next_beat_scope_creep", combined)
        self.assertIn("materially performs, begins, reveals", combined)

        parsed = minimax.parse_director_continuity_validation({
            "valid": False,
            "issues": [{
                "type": "next_beat_scope_creep",
                "problem": "The candidate enters the vault one beat early.",
            }],
        })
        self.assertEqual(parsed["issues"][0]["type"], "next_beat_scope_creep")

    @mock.patch("minimax.validate_mistral_prompt")
    @mock.patch("minimax.format_mistral_prompt")
    @mock.patch("minimax.request_valid_mistral_prompt", create=True)
    @mock.patch("minimax.ask_llm")

    def test_segment_llm_runs_raw_soundscape_music_without_legacy_seams(
        self,
        ask_llm,
        legacy_director,
        formatter,
        validator,
    ):
        raw_scene = (
            "Mark enters—quietly in a white T-shirt—and reacts to the environment."
        )
        ask_llm.side_effect = pipeline_llm_side_effect(
            [director_response(raw_scene)],
            soundscape="Quiet room tone.",
            music="Low restrained strings.",
        )

        payload = minimax.request_segment_llm(
            segment_bundle(),
            ["Mark confronts the Duchess, Cook, piglets, and Cheshire Cat."],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        self.assertEqual(ask_llm.call_count, 5)
        legacy_director.assert_not_called()
        formatter.assert_not_called()
        validator.assert_not_called()

        purposes = [
            call.kwargs["history_metadata"]["purpose"]
            for call in ask_llm.call_args_list
        ]
        self.assertEqual(
            purposes,
            [
                "director_raw_scene_creative",
                "add_scene_timing_refiner",
                "add_camera_refiner",
                "director_h3_soundscape",
                "director_h3_music",
            ],
        )
        self.assertEqual(
            ask_llm.call_args_list[2].kwargs["response_format"],
            None,
        )
        self.assertEqual(
            ask_llm.call_args_list[3].kwargs["response_format"],
            minimax.H3_SOUNDSCAPE_RESPONSE_FORMAT,
        )
        self.assertEqual(
            ask_llm.call_args_list[4].kwargs["response_format"],
            minimax.H3_MUSIC_RESPONSE_FORMAT,
        )
        self.assertIn(
            "enters—quietly in a white T-shirt",
            payload["llm_result"]["detailed_description"],
        )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Quiet room tone.")
        self.assertEqual(
            payload["llm_result"]["non_diegetic_music"],
            "Low restrained strings.",
        )
        self.assertEqual(payload["h3_mode"], "T2VA")

    def test_combined_continuity_avoids_llm_host_schema_rejection(self):
        llm_request = mock.Mock(side_effect=[
            {"subject": {"name": "Amy"}},
        ])

        minimax.request_combined_continuity(
            "A full scene description.",
            {"environment": {"location": "bedroom"}},
            llm_request=llm_request,
            history_metadata={"run_id": "r1"},
            content_attempts=1,
            defer_opening=True,
        )

        combined_call = llm_request.call_args_list[0]
        self.assertIsNone(combined_call.kwargs["response_format"])


    def test_segment_llm_carries_request_one_completion_claim(self):
        bundle = segment_bundle()
        bundle["active_beat_id"] = None
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("A quiet scene."),
        ]))

        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertNotIn("completed_beat_ids", payload["llm_result"])
        self.assertTrue(payload["request1_result"]["beat_complete"])

    @mock.patch("minimax.ask_llm")

    def test_audio_field_failures_fall_back_independently(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return {"unexpected": "bad field"}
            if purpose == "director_h3_music":
                return {"non_diegetic_music": "Soft low strings."}
            if purpose == "director_raw_scene_creative":
                return raw_scene
            if purpose == "add_scene_timing_refiner":
                return {"status": "ok", "timestamps": ["00:00.000"]}
            if purpose == "add_camera_refiner":
                return "At 00:00.000, " + raw_scene
            raise AssertionError(f"Unexpected LLM purpose {purpose!r}")

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(),
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(payload["llm_result"]["overall_soundscape"], "N/A")
        self.assertEqual(
            payload["llm_result"]["non_diegetic_music"],
            "Soft low strings.",
        )
        self.assertIn(
            "Mark enters the room quietly.",
            payload["llm_result"]["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_uses_canonical_raw_timestamps(self, ask_llm):
        raw_scene = (
            "At 00:00.000, Mark enters the room.\n"
            "At 00:04.500, Mark looks toward the window."
        )
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response(raw_scene),
        ])
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        description = payload["llm_result"]["detailed_description"]
        self.assertIn("At 00:00.000, Mark enters the room.", description)
        self.assertIn("At 00:04.500, Mark looks toward the window.", description)

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_preserves_raw_timestamps(self, ask_llm):
        raw_scene = "At 00:00.000, Mark enters the room."
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response(raw_scene),
        ])
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertIn(
            "At 00:00.000, Mark enters the room.",
            payload["llm_result"]["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")

    def test_audio_generation_never_rewrites_raw_actions(self, ask_llm):
        raw_scene = (
            "At 00:00.000, Mark enters the room.\n"
            "At 00:04.500, Mark looks toward the window."
        )
        ask_llm.side_effect = pipeline_llm_side_effect(
            [director_response(raw_scene)],
            soundscape="Footsteps and quiet room tone.",
            music="Sparse strings.",
        )
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        description = payload["llm_result"]["detailed_description"]
        self.assertIn("Mark enters the room.", description)
        self.assertIn("Mark looks toward the window.", description)
        self.assertNotIn("Footsteps and quiet room tone.", description)

    @mock.patch("minimax.ask_llm")

    def test_soundscape_failure_does_not_block_music(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return ""
            if purpose == "director_h3_music":
                return {"non_diegetic_music": "Sparse piano."}
            if purpose == "director_raw_scene_creative":
                return raw_scene
            if purpose == "add_scene_timing_refiner":
                return {"status": "ok", "timestamps": ["00:00.000"]}
            if purpose == "add_camera_refiner":
                return "At 00:00.000, " + raw_scene
            raise AssertionError(f"Unexpected LLM purpose {purpose!r}")

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "N/A")
        self.assertEqual(payload["llm_result"]["non_diegetic_music"], "Sparse piano.")

    @mock.patch("minimax.ask_llm")
    def test_no_music_skips_music_request(self, ask_llm):
        for mode in ("initial", "continuation"):
            with self.subTest(conditioning_mode=mode):
                ask_llm.reset_mock()
                ask_llm.side_effect = pipeline_llm_side_effect(
                    [director_response("Mark enters the room quietly.")],
                    soundscape="Quiet room tone.",
                    music="Sparse piano.",
                )
                bundle = segment_bundle()
                bundle["conditioning_mode"] = mode
                bundle["previous_music"] = "Sparse piano."
                with mock.patch("builtins.print"):
                    payload = minimax.request_segment_llm(
                        bundle, [], "run-id", {"no_music": True}
                    )
                self.assertEqual(payload["llm_result"]["non_diegetic_music"], "N/A")
                self.assertEqual(payload["llm_result"]["overall_soundscape"], "Quiet room tone.")
                purposes = [
                    call.kwargs.get("history_metadata", {}).get("purpose")
                    for call in ask_llm.call_args_list
                ]
                self.assertNotIn("director_h3_music", purposes)
                self.assertIn("director_h3_soundscape", purposes)

    @mock.patch("minimax.ask_llm")

    def test_music_failure_does_not_block_soundscape(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return {"overall_soundscape": "Quiet room tone."}
            if purpose == "director_h3_music":
                return ""
            if purpose == "director_raw_scene_creative":
                return raw_scene
            if purpose == "add_scene_timing_refiner":
                return {"status": "ok", "timestamps": ["00:00.000"]}
            if purpose == "add_camera_refiner":
                return "At 00:00.000, " + raw_scene
            raise AssertionError(f"Unexpected LLM purpose {purpose!r}")

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Quiet room tone.")
        self.assertEqual(payload["llm_result"]["non_diegetic_music"], "N/A")

    def test_wrong_bound_guard_allows_small_route_details_with_correct_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        raw = (
            "At 00:04.000, Will and Amber run down a short hall and stairs, "
            "then go through the basement door into the basement."
        )
        self.assertEqual(
            minimax._director_wrong_bound_barrier_errors(raw, binding),
            [],
        )

    def test_deterministic_crossing_guard_rejects_unauthorized_helper(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Amy, Will, and Amber rush into the basement.",
            contracts,
        )
        self.assertTrue(any("Amy" in issue for issue in issues))

    def test_deterministic_crossing_guard_rejects_ambiguous_follow_pronoun(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Will and Amber step inside as she follows.",
            contracts,
        )
        self.assertTrue(any("follow-pronoun" in issue for issue in issues))

    def test_deterministic_crossing_guard_rejects_following_into_destination(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = (
            "At 00:04.000, Will and Amber enter the basement while Amy follows closely behind.\n"
            "At 00:05.200, Amy locks the basement door.\n"
            "At 00:07.700, Amy steps out of the basement."
        )
        issues = minimax._director_unauthorized_destination_crossing_errors(
            raw, contracts
        )
        self.assertTrue(any("Amy is not authorized to follow" in issue for issue in issues))

    def test_deterministic_crossing_guard_allows_staying_outside_destination(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = (
            "At 00:04.000, Will and Amber enter the basement while Amy remains outside.\n"
            "At 00:05.200, Amy locks the basement door."
        )
        self.assertEqual(
            minimax._director_unauthorized_destination_crossing_errors(raw, contracts),
            [],
        )

    def test_deterministic_crossing_guard_rejects_unauthorized_dash(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = "At 00:04.000, Amy and the kids dash through the broken window into the basement."
        issues = minimax._director_unauthorized_destination_crossing_errors(raw, contracts)
        self.assertTrue(any("Amy is not authorized to cross" in issue for issue in issues))

    def test_containment_crossing_requires_visible_entry_not_just_final_state(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"location":"kitchen"},'
            '"Amber":{"location":"kitchen"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
        ]
        raw = (
            "At 00:03.000, Amy pushes them into the basement door.\n"
            "At 00:04.000, Will and Amber reach the basement door; Amy shuts it.\n"
            "End continuity state: Will and Amber are inside the basement."
        )
        issues = minimax._director_missing_containment_crossing_errors(raw, effects, opening)
        self.assertTrue(any(issue.startswith("Will must visibly cross") for issue in issues))
        self.assertTrue(any(issue.startswith("Amber must visibly cross") for issue in issues))

    def test_containment_crossing_accepts_named_entry(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
        ]
        raw = (
            "At 00:04.000, Will and Amber step into the basement through its door.\n"
            "End continuity state: Will and Amber are inside the basement."
        )
        self.assertEqual(
            minimax._director_missing_containment_crossing_errors(raw, effects, ""),
            [],
        )

    def test_opening_held_prop_cannot_end_unassigned_on_belt(self):
        registry = {"subjects": {"Amy": {"held_props": ["pistol", "katana"]}}}
        raw = (
            "At 00:00.000, Amy swings her katana and fires her pistol.\n"
            "At 00:07.000, Amy stands with the katana hanging on her belt.\n"
            "End continuity state: Amy holds a pistol with a katana on her belt."
        )
        issues = minimax._director_opening_held_unassigned_stow_errors(
            raw, registry, "Amy cuts the target with the katana and fires the pistol."
        )
        self.assertTrue(any("katana" in issue for issue in issues))
        self.assertFalse(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_may_be_stowed_when_source_assigns_it(self):
        registry = {"subjects": {"Amy": {"held_props": ["katana"]}}}
        raw = (
            "At 00:06.000, Amy places the katana on her belt.\n"
            "End continuity state: Amy stands with the katana on her belt."
        )
        self.assertEqual(
            minimax._director_opening_held_unassigned_stow_errors(
                raw, registry, "Amy clips the katana to her belt."
            ),
            [],
        )

    def test_both_hands_action_requires_release_of_opening_held_prop(self):
        registry = {"subjects": {"Amy": {"held_props": ["pistol", "katana"]}}}
        raw = (
            "At 00:00.000, Amy holds a pistol and katana.\n"
            "At 00:04.000, Amy lifts the arm with both hands and throws it away.\n"
            "End continuity state: Amy holds both weapons."
        )
        issues = minimax._director_occupied_hands_errors(raw, registry)
        self.assertTrue(any("cannot use both hands" in issue for issue in issues))

        released = raw.replace(
            "At 00:04.000, Amy lifts",
            "At 00:03.000, Amy sets down the pistol.\nAt 00:04.000, Amy lifts",
        )
        self.assertEqual(minimax._director_occupied_hands_errors(released, registry), [])

    def test_opening_held_prop_cannot_be_reacquired_without_release(self):
        registry = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol", "katana"],
                },
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            (
                "At 00:00.000, Amy holds a pistol and katana.\n"
                "At 00:01.000, Amy pulls pistol from holster and aims it.\n"
                "End continuity state: Amy holds pistol and katana."
            ),
            registry,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_use_is_not_reacquisition(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:00.000, Amy pulls the trigger on her pistol and fires.",
            "At 00:00.000, Amy shoots the zombie with her pistol.",
            "At 00:00.000, Amy raises her pistol toward the zombie.",
        ):
            self.assertEqual(
                minimax._director_opening_held_reacquire_errors(
                    raw_scene,
                    registry,
                ),
                [],
            )

    def test_opening_held_prop_lift_from_surface_is_rejected(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:02.200, Amy lifts the pistol from a nearby table.",
            "At 00:02.200, Amy raises her pistol off the counter.",
        ):
            issues = minimax._director_opening_held_reacquire_errors(
                raw_scene,
                registry,
            )
            self.assertTrue(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_raise_to_use_is_not_reacquisition(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:02.200, Amy lifts her pistol toward the zombie.",
            "At 00:02.200, Amy raises her pistol to eye level.",
        ):
            self.assertEqual(
                minimax._director_opening_held_reacquire_errors(
                    raw_scene,
                    registry,
                ),
                [],
            )

    def test_opening_held_prop_pronoun_requires_unique_holder(self):
        state = {
            "subjects": {
                "Amy": {"held_props": ["pistol"]},
                "Riley": {"held_props": ["pistol"]},
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, She pulls the pistol from her belt and fires.",
            state,
        )
        self.assertEqual(issues, [])

    def test_opening_held_prop_pull_from_belt_reacquire_is_rejected(self):
        state = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                }
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, She pulls the pistol from her belt and fires.",
            state,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_pull_out_reacquire_is_rejected(self):
        state = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                }
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, Amy pulls out her pistol and aims at the body.",
            state,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_direct_reacquire_is_rejected(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:00.000, Amy pulls the pistol from a holster.",
            registry,
        )
        self.assertTrue(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_can_be_reacquired_after_release(self):
        registry = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                },
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            (
                "At 00:00.000, Amy holsters the pistol.\n"
                "At 00:01.000, Amy draws the pistol from the holster.\n"
                "End continuity state: Amy holds the pistol."
            ),
            registry,
        )
        self.assertEqual(issues, [])


    def test_deterministic_crossing_guard_allows_authorized_children(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Will and Amber rush into the basement while Amy stays outside.",
            contracts,
        )
        self.assertEqual(issues, [])


    def test_bound_generic_barrier_rejects_wrong_qualified_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        issues = minimax._director_wrong_bound_barrier_errors(
            "At 00:05.000, Amy slams the kitchen door shut.",
            binding,
        )
        self.assertTrue(any("kitchen door" in issue for issue in issues))

    def test_bound_generic_barrier_rejects_wrong_crossing_doorway(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        issues = minimax._director_wrong_bound_barrier_errors(
            "At 00:02.000, they sprint through the broken kitchen doorway directly into the basement.",
            binding,
        )
        self.assertTrue(any("kitchen doorway" in issue for issue in issues))

    def test_bound_generic_barrier_allows_destination_or_generic_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        for raw_scene in (
            "At 00:05.000, Amy slams the basement door shut.",
            "At 00:05.000, Amy locks the door.",
            "At 00:01.000, a zombie shatters the kitchen door window.",
        ):
            self.assertEqual(
                minimax._director_wrong_bound_barrier_errors(raw_scene, binding),
                [],
            )

    def test_bound_basement_door_rejects_window_route_into_basement(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        raw = "At 00:04.000, Amy and the kids dash through the broken window into the basement."
        issues = minimax._director_wrong_bound_barrier_errors(raw, binding)
        self.assertTrue(any("through a window" in issue for issue in issues))

    def test_preserved_containment_rejects_visual_relocation(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"},'
            '"Amber":{"containment":"contained","contained_in":"basement"}}}'
        )
        raw = (
            "At 00:06.000, through the broken kitchen door window, "
            "Will and Amber look up at the scene."
        )
        issues = minimax._director_preserved_containment_errors(raw, opening, [])
        self.assertTrue(any(issue.startswith("Will is canonically contained") for issue in issues))
        self.assertTrue(any(issue.startswith("Amber is canonically contained") for issue in issues))

    def test_preserved_containment_allows_subject_still_in_container(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}}}'
        )
        raw = "At 00:06.000, Will stands inside the basement looking toward the door."
        issues = minimax._director_preserved_containment_errors(raw, opening, [])
        self.assertEqual(issues, [])

    def test_preserved_containment_allows_explicit_release_effect(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}}}'
        )
        effects = [
            {"op":"set_containment","entity":"Will","value":"free","container":"basement"}
        ]
        raw = "At 00:04.000, Will steps into the living room."
        issues = minimax._director_preserved_containment_errors(raw, opening, effects)
        self.assertEqual(issues, [])

    def test_unassigned_external_end_rejects_helper_following_outside(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"},"Will":{"location":"basement"},'
            '"Amber":{"location":"basement"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "value": "free", "container": "basement"},
            {"op": "set_containment", "entity": "Amber", "value": "free", "container": "basement"},
        ]
        subjects = (
            "<Subject 1> is Amy, a woman.\n"
            "<Subject 2> is Will, a boy.\n"
            "<Subject 3> is Amber, a girl."
        )
        raw = (
            "At 00:07.500, all three stand outside in sunlight.\n"
            "End continuity state: Amy, Will, and Amber stand on the sunny patio outside the house."
        )
        issues = minimax._director_unassigned_external_end_errors(
            raw, opening, effects, subjects
        )
        self.assertTrue(any(issue.startswith("Amy ends outside") for issue in issues))
        self.assertFalse(any(issue.startswith("Will ends outside") for issue in issues))
        self.assertFalse(any(issue.startswith("Amber ends outside") for issue in issues))

    def test_unassigned_external_end_allows_outside_containment_boundary(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "value": "contained", "container": "basement"},
            {"op": "set_containment", "entity": "Amber", "value": "contained", "container": "basement"},
        ]
        subjects = "<Subject 1> is Amy, a woman."
        for ending in (
            "Amy is outside the basement; Will and Amber are inside.",
            "Amy stands outside the basement door while Will and Amber are inside.",
            "Amy stands outside the kitchen doorway beside the basement door.",
        ):
            raw = "At 00:07.000, Amy locks the basement door.\nEnd continuity state: " + ending
            self.assertEqual(
                minimax._director_unassigned_external_end_errors(
                    raw, opening, effects, subjects
                ),
                [],
            )

    def test_authorized_external_end_is_allowed(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"}}}'
        )
        effects = [
            {"op": "set_location", "entity": "Amy", "value": "outside home"},
        ]
        raw = (
            "At 00:05.000, Amy steps outside.\n"
            "End continuity state: Amy stands outside the house."
        )
        issues = minimax._director_unassigned_external_end_errors(
            raw, opening, effects, "<Subject 1> is Amy, a woman."
        )
        self.assertEqual(issues, [])


    def test_director_prompt_allows_small_route_details(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_CREATIVE_SYSTEM_TEMPLATE.format(
            segment_length="8"
        )
        self.assertIn("Add only details needed to physically connect", prompt)
        self.assertNotIn("timestamps", prompt.casefold())
        self.assertNotIn("camera choreography", prompt.casefold())
    def test_completion_prompt_allows_small_route_details(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy gets Will and Amber into the basement and locks the door.",
            (
                "At 00:00.000, Amy grabs Will and Amber.\n"
                "At 00:01.000, Will and Amber descend the kitchen stairs.\n"
                "At 00:02.000, Will and Amber enter the basement.\n"
                "At 00:03.000, Amy locks the basement door.\n"
                "End continuity state: Will and Amber are in the basement; Amy is outside."
            ),
            assigned_source=(
                "Amy rushes Will and Amber to the basement, gets them inside, "
                "and locks the door."
            ),
            authoritative_opening_state="Amy, Will, and Amber are in the kitchen.",
            assigned_state_effects=[
                {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            ],
        )
        prompt = messages[-1]["content"]
        self.assertIn("harmless staging detail", prompt)
        self.assertIn("may NOT replace a concrete SOURCE action", prompt)


    def test_completion_prompt_rejects_ambiguous_collective_crossing(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy moves Will and Amber into the basement and locks the door.",
            (
                "At 00:00.000, Amy grabs Will and Amber.\n"
                "At 00:01.000, They descend into the basement.\n"
                "At 00:02.000, Amy locks the basement door.\n"
                "End continuity state: Will and Amber are inside the basement; Amy is outside."
            ),
            assigned_source=(
                "Amy rushes Will and Amber to the basement, gets them inside, "
                "and locks the door."
            ),
            authoritative_opening_state="Amy, Will, and Amber are outside the basement.",
            assigned_state_effects=[
                {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            ],
        )
        prompt = messages[-1]["content"]
        self.assertIn('collective language such as "they"', prompt)
        self.assertIn("explicitly name only the authorized crossers", prompt)



    def test_director_prompt_keeps_source_and_current_beat_as_authority(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_CREATIVE_SYSTEM_TEMPLATE.format(
            segment_length="8"
        )
        self.assertIn("CURRENT BEAT is the story authority", prompt)
        self.assertIn("the scene to stage in this clip", prompt)
    def test_completion_prompt_rejects_concrete_action_substitution(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "A parent grabs two children and rushes them into the shelter.",
            (
                "At 00:00.000, the parent lifts both children.\n"
                "At 00:02.000, the parent carries them toward the shelter.\n"
                "End continuity state: the children are inside the shelter."
            ),
            assigned_source=(
                "A parent grabs two children and rushes them into the shelter."
            ),
            authoritative_opening_state=(
                "The parent and both children begin outside the shelter."
            ),
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "may NOT replace a concrete SOURCE action or participant interaction",
            prompt,
        )


    def test_director_prompt_does_not_encode_terminal_target_rules(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_CREATIVE_SYSTEM_TEMPLATE.format(
            segment_length="8"
        )
        self.assertNotIn("already terminal target", prompt)
        self.assertNotIn("new, another, or incoming target", prompt)
    def test_completion_prompt_preserves_new_target_distinction(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "The operator repeatedly disables incoming drones.",
            (
                "At 00:00.000, the operator cuts an arm from the disabled drone on the floor.\n"
                "End continuity state: the disabled drone remains on the floor."
            ),
            assigned_source="The operator repeatedly disables incoming drones.",
            authoritative_opening_state="A disabled drone lies on the floor.",
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "may not satisfy the action by reusing a target already dead, destroyed, or terminal",
            prompt,
        )

    def test_completion_prompt_rejects_unassigned_terminal_outcome(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Operator damages the machine's outer panel.",
            (
                "At 00:00.000, Operator dents the machine's outer panel.\n"
                "At 00:01.000, The machine collapses permanently and stops.\n"
                "End continuity state: The machine is motionless and permanently stopped."
            ),
            assigned_source="Operator damages the machine's outer panel.",
            authoritative_opening_state="N/A",
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn("non-terminal injury/damage/change", prompt)
        self.assertIn("motionless/collapsed", prompt)



if __name__ == "__main__":
    unittest.main()
