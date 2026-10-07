import unittest
import json
import re
import copy
from pathlib import Path
from unittest import mock

import minimax
from world_state import (
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
TAVERN_SEGMENT_BEATS = [
    "\n".join(item["must_happen"])
    for item in TAVERN_BENCHMARK["beats"]
]
# The locked benchmark now stores one global story sentence plus authoritative
# per-Segment beat facts; do not index nonexistent story paragraphs.
TAVERN_SEGMENT_SOURCES = list(TAVERN_SEGMENT_BEATS)


def current_prop(name, holder=None, location="Tavern", support=None, evidence="", reason="", contents=None):
    return {
        "name": name,
        "kind": "container",
        "mobility": "movable",
        "initial_location": location if holder is None else None,
        "initial_holder": holder,
        "support_name": support,
        "contents": copy.deepcopy(contents or []),
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
                contents=[{"substance": "unknown", "amount": "some", "consumable": "unknown"}],
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
            "classification": "present",
            "evidence_beat": 1,
            "initial_state": "wiping a polished table",
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


def goblin_mug_transfer_actions(mug_id):
    return [
        {
            "action_id": "pickup-mug",
            "op": "pickup",
            "actor_subject_id": "subject_1",
            "prop_id": mug_id,
        },
        {
            "action_id": "handoff-mug",
            "op": "handoff",
            "from_subject_id": "subject_1",
            "to_subject_id": "subject_2",
            "prop_id": mug_id,
        },
    ]


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


def director_response(raw_scene, beat_complete=True, state_actions=None):
    """A structurally valid Request 1 reply for unit tests."""
    scene = str(raw_scene).strip()
    if not scene.startswith("At "):
        scene = "At 00:00.000, " + scene
    if not re.search(r"At 00:0[4-9]\.\d{1,3},", scene):
        scene += "\nAt 00:04.500, The action settles into its final visible state."
    if "End continuity state:" not in scene:
        scene += "\nEnd continuity state: The described action has reached its final visible state."
    return {
        "raw_scene": scene,
        "finite_activity_complete": beat_complete,
        "named_beneficiaries_complete": beat_complete,
        "activity_tools_settled": beat_complete,
        "beat_complete": beat_complete,
        "state_actions": copy.deepcopy(state_actions or []),
    }


def pipeline_llm_side_effect(
    non_audio_responses,
    *,
    soundscape="Room tone.",
    music="N/A",
):
    """Return current Director pipeline responses without coupling unrelated tests."""
    queued = iter(non_audio_responses)

    def respond(*args, **kwargs):
        purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
        if purpose == "director_h3_soundscape":
            return {"overall_soundscape": soundscape}
        if purpose == "director_h3_music":
            return {"non_diegetic_music": music}
        if purpose == "director_raw_world_state_consistency":
            return {"valid": True, "issue": ""}
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
        response = next(queued)
        if isinstance(response, dict) and "raw_scene" in response:
            response = {**response, "state_actions": response.get("state_actions", [])}
        return response

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
    def test_absent_subject_move_failure_adds_enter_retry_hint(self):
        hint = minimax._director_state_action_retry_hint(
            "move action move: subject_not_known_present: The subject is not explicitly recorded as present."
        )
        self.assertIn("Canonical WorldState records that Subject as not present", hint)
        self.assertIn("use an `enter` action", hint)
        self.assertIn("Do not use `move`", hint)

    def test_unrelated_state_action_failure_gets_no_special_hint(self):
        hint = minimax._director_state_action_retry_hint(
            "pickup action take: prop_not_known_present: prop unavailable"
        )
        self.assertEqual(hint, "")

    def setUp(self):
        self._state_consistency_patcher = mock.patch(
            "minimax.validate_raw_scene_state_action_consistency",
            return_value={"valid": True, "issue": ""},
        )
        self._state_consistency_patcher.start()

    def tearDown(self):
        self._state_consistency_patcher.stop()

    def test_segment_one_can_apply_presence_gated_action_to_amy(self):
        state = new_world_state({
            "source_sha256": "amy-opening-presence",
            "subjects": {
                "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
            },
        })
        state, location_id = seed_canonical_static_location_state(
            state,
            {"location": {"name": "Tavern"}, "anchors": [], "objects": []},
        )
        beats = [
            "Amy steps onto the wooden floor of her medieval tavern, apron tied snugly around her waist, hat perched on her head.",
            "Amy wipes the polished stone counter behind her bar.",
        ]
        state = minimax.extract_registered_subject_story_start_presence(
            state,
            "Amy is a medieval barkeep.",
            beats,
            location_id=location_id,
            llm_request=mock.Mock(side_effect=AssertionError("LLM call is unnecessary")),
        )
        state = register_explicit_persistent_props(state, [{
            "name": "damp rag", "kind": "object", "mobility": "movable",
            "needed_for_state": True, "reason": "Amy picks up the rag during Segment 1.",
            "location_id": location_id,
        }])
        amy_id = next(
            subject_id for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Amy"
        )
        rag_id = next(
            prop_id for prop_id, prop in state["props"].items()
            if prop["name"] == "damp rag"
        )

        outcome = validate_state_actions(state, [{
            "action_id": "amy-picks-up-rag",
            "op": "pickup",
            "actor_subject_id": amy_id,
            "prop_id": rag_id,
        }], segment_number=1)

        self.assertTrue(outcome[0].accepted)
        self.assertNotEqual(outcome[0].code, "subject_not_known_present")

    def test_tavern_segment_one_vocabulary_uses_authoritative_seed_paths(self):
        state, _location_id = tavern_world_state_from_authorities()
        state, added, subject_names = prepare_tavern_segment(state, 1)
        self.assertEqual(added, [])
        subject_by_name = {s["name"]: s for s in state["subjects"].values()}
        self.assertEqual(subject_by_name["Amy"]["presence"], "present")
        self.assertEqual(subject_by_name["Goblin1"]["presence"], "present")
        contract = minimax.build_director_state_action_contract(
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
        contract = minimax.build_director_state_action_contract(
            state,
            current_segment_text=TAVERN_SEGMENT_BEATS[2] + TAVERN_SEGMENT_SOURCES[2],
            current_segment_subject_names=subject_names,
        )
        vocabulary_subject_ids = {
            subject["id"] for subject in contract["vocabulary"]["subjects"]
        }
        self.assertIn(elf_id, vocabulary_subject_ids)
        schema = contract["response_format"]["json_schema"]["schema"]
        action_schemas = schema["properties"]["state_actions"]["items"]["oneOf"]
        enter_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "enter"
        )
        self.assertIn(elf_id, enter_schema["properties"]["subject_id"]["enum"])
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
        contract = minimax.build_director_state_action_contract(
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
        self.assertTrue({"enter", "handoff", "pour", "fill"}.issubset(available_ops))
        fill_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "fill"
        )
        self.assertEqual(
            set(fill_schema["properties"]),
            {"action_id", "op", "actor_subject_id", "target_prop_id", "substance"},
        )
        enter_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "enter"
        )
        self.assertIn(dragon_id, enter_schema["properties"]["subject_id"]["enum"])

    def test_tavern_state_transactions_advance_through_dragon_sip_and_final_segment(self):
        state, location_id = tavern_world_state_from_authorities()
        state, _, _ = prepare_tavern_segment(state, 1)
        generation_state = {"world_state": copy.deepcopy(state)}

        # Segment 1 commits its authoritative opening and registered persistent
        # props as a transaction, so Segment 2 opens from that exact state.
        mug_id = next(prop_id for prop_id, prop in state["props"].items() if prop["name"] == "mug")
        barrel_id = next(prop_id for prop_id, prop in state["props"].items() if prop["name"] == "barrel")
        amy_id = next(subject_id for subject_id, subject in state["subjects"].items() if subject["name"] == "Amy")
        segment_one_actions = [{
            "action_id": "amy-refills-goblin-mug",
            "op": "pour",
            "actor_subject_id": amy_id,
            "source_prop_id": barrel_id,
            "target_prop_id": mug_id,
            "substance": "unknown",
            "amount": "partial",
        }]
        segment_one = minimax.build_world_state_transaction(
            state, segment_one_actions, segment_number=1
        )
        meta = minimax.world_state_transaction_metadata(
            segment_one, "H3 segment 1", completion_mode="prompt_only_transaction"
        )
        minimax.commit_world_state_transaction(generation_state, segment_one, meta)
        segment_two_opening = copy.deepcopy(generation_state["world_state"])
        self.assertEqual(
            segment_two_opening,
            segment_one["predicted_end_world_state"],
        )
        self.assertEqual(
            segment_two_opening["revision"],
            state["revision"] + 1,
        )
        segment_two_opening, _, _ = prepare_tavern_segment(segment_two_opening, 2)
        self.assertEqual(
            segment_two_opening["props"],
            segment_one["predicted_end_world_state"]["props"],
        )
        self.assertEqual(
            next(prop for prop in segment_two_opening["props"].values() if prop["name"] == "mug")["contents"],
            [{"substance": "unknown", "amount": "some", "consumable": "unknown"}],
        )
        generation_state["world_state"] = copy.deepcopy(segment_two_opening)

        # Segment 3 entry is committed before Segment 4 registers its new
        # arrival; the next vocabulary therefore sees Elf1 as present.
        state = generation_state["world_state"]
        state, _, _ = prepare_tavern_segment(state, 3)
        generation_state["world_state"] = copy.deepcopy(state)
        elf_id, _elf = next(
            (subject_id, subject) for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Elf1"
        )
        enter_elf = [{
            "action_id": "elf-enters",
            "op": "enter",
            "subject_id": elf_id,
            "location_id": location_id,
        }]
        segment_three = minimax.build_world_state_transaction(
            state, enter_elf, segment_number=3
        )
        meta = minimax.world_state_transaction_metadata(
            segment_three, "H3 segment 3", completion_mode="prompt_only_transaction"
        )
        minimax.commit_world_state_transaction(generation_state, segment_three, meta)
        state = generation_state["world_state"]
        state, _, segment_four_subjects = prepare_tavern_segment(state, 4)
        generation_state["world_state"] = copy.deepcopy(state)
        self.assertIn("Elf1", segment_four_subjects)

        dragon_id = next(
            subject_id for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Dragon1"
        )
        amy_id = next(
            subject_id for subject_id, subject in state["subjects"].items()
            if subject["name"] == "Amy"
        )
        cup_id = next(
            prop_id for prop_id, prop in state["props"].items()
            if prop["name"] == "crystal cup"
        )
        segment_four_actions = [
            {
                "action_id": "dragon-enters",
                "op": "enter",
                "subject_id": dragon_id,
                "location_id": location_id,
            },
            {
                "action_id": "amy-picks-up-cup",
                "op": "pickup",
                "actor_subject_id": amy_id,
                "prop_id": cup_id,
            },
            {
                "action_id": "amy-fills-cup",
                "op": "fill",
                "actor_subject_id": amy_id,
                "target_prop_id": cup_id,
                "substance": "special brew",
            },
            {
                "action_id": "amy-hands-cup-to-dragon",
                "op": "handoff",
                "from_subject_id": amy_id,
                "to_subject_id": dragon_id,
                "prop_id": cup_id,
            },
        ]
        segment_four = minimax.build_world_state_transaction(
            state, segment_four_actions, segment_number=4
        )
        meta = minimax.world_state_transaction_metadata(
            segment_four, "H3 segment 4", completion_mode="prompt_only_transaction"
        )
        minimax.commit_world_state_transaction(generation_state, segment_four, meta)
        state = generation_state["world_state"]
        cup = state["props"][cup_id]
        self.assertEqual(cup["placement"], {"kind": "held", "subject_id": dragon_id})
        self.assertEqual(cup["contents"][0]["substance"], "special brew")
        self.assertEqual(cup["contents"][0]["amount"], "some")

        # Segment 5 consumes from the same registered cup using the explicit
        # RAW consume action; the coarse remaining amount stays nonempty.
        state, _, _ = prepare_tavern_segment(state, 5)
        generation_state["world_state"] = copy.deepcopy(state)
        segment_five = minimax.build_world_state_transaction(
            state,
            [{
                "action_id": "dragon-sips",
                "op": "consume",
                "actor_subject_id": dragon_id,
                "prop_id": cup_id,
                "substance": "special brew",
                "amount": "partial",
            }],
            segment_number=5,
        )
        meta = minimax.world_state_transaction_metadata(
            segment_five, "H3 segment 5", completion_mode="prompt_only_transaction"
        )
        minimax.commit_world_state_transaction(generation_state, segment_five, meta)
        self.assertEqual(
            generation_state["world_state"]["props"][cup_id]["contents"][0]["amount"],
            "some",
        )

        final_segment = minimax.build_world_state_transaction(
            generation_state["world_state"], [], segment_number=6
        )
        final_meta = minimax.world_state_transaction_metadata(
            final_segment, "H3 segment 6", completion_mode="prompt_only_transaction"
        )
        minimax.commit_world_state_transaction(generation_state, final_segment, final_meta)
        self.assertEqual(
            generation_state["world_state_transactions"]["6"]["completion_mode"],
            "prompt_only_transaction",
        )
        self.assertEqual(
            generation_state["world_state_transactions"]["6"]["final_h3_hash"],
            minimax.hashlib.sha256(b"H3 segment 6").hexdigest(),
        )

    def test_rejected_world_state_transaction_rolls_back_and_detects_stale_opening(self):
        state, _location_id = tavern_world_state_from_authorities()
        state, _, _ = prepare_tavern_segment(state, 1)
        generation_state = {"world_state": copy.deepcopy(state)}
        with self.assertRaisesRegex(ValueError, "transaction candidate rejected"):
            minimax.build_world_state_transaction(
                state,
                [{
                    "action_id": "pick-up-counter",
                    "op": "pickup",
                    "actor_subject_id": "subject_1",
                    "prop_id": next(
                        prop_id for prop_id, prop in state["props"].items()
                        if prop["name"] == "counter"
                    ),
                }],
                segment_number=1,
            )
        self.assertEqual(generation_state["world_state"], state)

        transaction = minimax.build_world_state_transaction(
            state, [], segment_number=1
        )
        generation_state["world_state"]["revision"] += 1
        metadata = minimax.world_state_transaction_metadata(
            transaction, "H3", completion_mode="prompt_only_transaction"
        )
        with self.assertRaisesRegex(ValueError, "opening revision/hash changed"):
            minimax.commit_world_state_transaction(generation_state, transaction, metadata)

    def test_raw_state_action_consistency_and_final_h3_checks_are_state_narrow(self):
        state, _location_id = tavern_world_state_from_authorities()
        state, _, subject_names = prepare_tavern_segment(state, 1)
        contract = minimax.build_director_state_action_contract(
            state,
            current_segment_text=TAVERN_SEGMENT_BEATS[0] + TAVERN_SEGMENT_SOURCES[0],
            current_segment_subject_names=subject_names,
        )
        invalid = mock.Mock(return_value={
            "valid": False,
            "issue": "RAW fills the mug from the barrel but state_actions omit pour.",
        })
        check = self._state_consistency_patcher.temp_original
        result = check(
            raw_scene="Amy fills the mug from the barrel.",
            current_beat=TAVERN_SEGMENT_BEATS[0],
            assigned_source=TAVERN_SEGMENT_SOURCES[0],
            state_actions=[],
            opening_world_state=state,
            predicted_end_world_state=state,
            vocabulary=contract["vocabulary"],
            llm_request=invalid,
        )
        self.assertFalse(result["valid"])
        consistency_system = invalid.call_args.args[0][0]["content"]
        self.assertIn("`fill` is invalid", consistency_system)
        self.assertIn("require `pour` with that registered source", consistency_system)
        sent = invalid.call_args.args[0][1]["content"]
        self.assertIn("OPENING AND PREDICTED ENDING", sent)
        self.assertIn("STATE ACTIONS\n[]", sent)
        self.assertIn("mug", sent)

        prop_messages = minimax.build_current_segment_persistent_prop_messages(
            current_beat="Amy fills a registered cup with special brew.",
            assigned_source="",
            world_state=state,
        )
        self.assertIn("pour/fill/consume", prop_messages[0]["content"])

        h3_invalid = mock.Mock(return_value={
            "valid": False,
            "issue": "Final H3 omits Amy's handoff of the cup.",
        })
        actions = [{"action_id": "handoff", "op": "handoff"}]
        h3_result = minimax.validate_final_h3_world_state_plan(
            final_h3_prompt="Amy leaves the cup on the shelf.",
            raw_scene="Amy hands the cup to Dragon1.",
            state_actions=actions,
            opening_world_state=state,
            predicted_end_world_state=state,
            vocabulary=contract["vocabulary"],
            llm_request=h3_invalid,
        )
        self.assertFalse(h3_result["valid"])
        self.assertEqual(
            h3_invalid.call_args.kwargs["history_metadata"]["purpose"],
            "final_h3_world_state_plan_validation",
        )

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
            contract = minimax.build_director_state_action_contract(
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
                "pickup", "place", "handoff", "pour", "fill", "consume", "enter",
                "exit", "move", "set_support", "change_clothing", "open",
                "close", "lock", "unlock",
            },
        )

    def test_request_one_dry_runs_valid_goblin_mug_transfer_without_committing(self):
        bundle = goblin_mug_bundle()
        opening_world_state = copy.deepcopy(bundle["world_state_opening"])
        _state, _location_id, mug_id = goblin_mug_world_state()
        actions = goblin_mug_transfer_actions(mug_id)
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(
                "At 00:01.000, Goblin1 picks up the mug.\n"
                "At 00:04.500, Goblin1 hands the mug to Elf1.",
                state_actions=actions,
            ),
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
                bundle, [], "run-transfer", {"source_sha256": "source"}
            )

        self.assertTrue(payload["request1_result"]["state_actions_dry_run_accepted"])
        self.assertEqual(payload["request1_result"]["state_actions"], actions)
        self.assertEqual(bundle["world_state_opening"], opening_world_state)
        self.assertEqual(
            bundle["world_state_opening"]["props"][mug_id]["placement"],
            {"kind": "located", "location_id": next(iter(bundle["world_state_opening"]["locations"]))},
        )
        request1 = next(
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene"
        )
        prompt = request1.args[0][-1]["content"]
        self.assertIn("REGISTERED WORLDSTATE VOCABULARY", prompt)
        self.assertIn(mug_id, prompt)
        self.assertIn("Never invent a source prop", prompt)
        action_schemas = request1.kwargs["response_format"]["json_schema"]["schema"]["properties"]["state_actions"]["items"]["oneOf"]
        self.assertEqual(
            {schema["properties"]["op"]["const"] for schema in action_schemas},
            {
                "pickup", "place", "handoff", "pour", "fill", "consume", "enter",
                "exit", "move", "set_support", "change_clothing", "open",
                "close", "lock", "unlock",
            },
        )

    def test_request_one_consistency_retry_reuses_immutable_opening_state(self):
        bundle = goblin_mug_bundle()
        opening = copy.deepcopy(bundle["world_state_opening"])
        mug_id = next(
            prop_id for prop_id, prop in opening["props"].items()
            if prop["name"] == "mug"
        )
        actions = goblin_mug_transfer_actions(mug_id)
        scene = (
            "At 00:00.000, Goblin1 picks up the mug.\n"
            "At 00:04.500, Goblin1 hands the mug to Elf1.\n"
            "End continuity state: Elf1 holds the mug."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(scene),
            director_response(scene, state_actions=actions),
        ]))
        consistency = mock.Mock(side_effect=[
            {"valid": False, "issue": "RAW hands off the mug but handoff is omitted."},
            {"valid": True, "issue": ""},
        ])
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_raw_scene_state_action_consistency", consistency),
            mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-consistency-retry", {"source_sha256": "source"}
            )

        self.assertTrue(payload["request1_result"]["state_actions_dry_run_accepted"])
        self.assertEqual(payload["request1_result"]["state_actions"], actions)
        self.assertEqual(bundle["world_state_opening"], opening)
        self.assertEqual(consistency.call_count, 2)
        self.assertEqual(
            [call.kwargs["opening_world_state"] for call in consistency.call_args_list],
            [opening, opening],
        )
        retry_messages = [
            call.args[0] for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene"
        ][1]
        retry_text = retry_messages[-1]["content"]
        self.assertIn("RAW hands off the mug but handoff is omitted.", retry_text)
        self.assertNotIn("stale", retry_text.casefold())

    def test_request_one_rejects_duplicate_or_unknown_prop_id_then_retries(self):
        for invalid_actions, expected_code in (
            (
                [
                    {"action_id": "pickup-one", "op": "pickup", "actor_subject_id": "subject_1", "prop_id": "mug-id"},
                    {"action_id": "pickup-twice", "op": "pickup", "actor_subject_id": "subject_1", "prop_id": "mug-id"},
                ],
                "prop_not_located",
            ),
            (
                [{"action_id": "pickup-unknown", "op": "pickup", "actor_subject_id": "subject_1", "prop_id": "prop_unregistered"}],
                "unknown_entity_id",
            ),
        ):
            with self.subTest(code=expected_code):
                bundle = goblin_mug_bundle()
                _state, _location_id, mug_id = goblin_mug_world_state()
                invalid_actions = copy.deepcopy(invalid_actions)
                for action in invalid_actions:
                    if action["prop_id"] == "mug-id":
                        action["prop_id"] = mug_id
                request = mock.Mock(side_effect=pipeline_llm_side_effect([
                    director_response(
                        "At 00:01.000, Goblin1 picks up the mug.\n"
                        "At 00:04.500, Goblin1 hands the mug to Elf1.",
                        state_actions=invalid_actions,
                    ),
                    director_response(
                        "At 00:01.000, Goblin1 picks up the mug.\n"
                        "At 00:04.500, Goblin1 hands the mug to Elf1.",
                        state_actions=goblin_mug_transfer_actions(mug_id),
                    ),
                ]))
                with (
                    mock.patch("minimax.ask_llm", request),
                    mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
                    mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
                    mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
                    mock.patch("builtins.print"),
                ):
                    payload = minimax.request_segment_llm(
                        bundle, [], "run-prop-id", {"source_sha256": "source"}
                    )
                request1_calls = [
                    call for call in request.call_args_list
                    if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene"
                ]
                self.assertEqual(len(request1_calls), 2)
                self.assertIn(expected_code, request1_calls[1].args[0][-1]["content"])
                self.assertTrue(payload["request1_result"]["state_actions_dry_run_accepted"])
                self.assertEqual(
                    bundle["world_state_opening"]["props"][mug_id]["placement"]["kind"],
                    "located",
                )

    def test_request_one_rejects_invalid_handoff(self):
        bundle = goblin_mug_bundle()
        bundle["current_beat_text"] = (
            "Goblin1 hands the mug to Elf1 while Amy watches."
        )
        _state, _location_id, mug_id = goblin_mug_world_state()
        wrong_handoff = [{
            "action_id": "invalid-handoff",
            "op": "handoff",
            "from_subject_id": "subject_2",
            "to_subject_id": "subject_3",
            "prop_id": mug_id,
        }]
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(
                "At 00:01.000, Elf1 attempts to give Amy the mug.",
                state_actions=wrong_handoff,
            ),
            director_response(
                "At 00:01.000, Goblin1 picks up the mug.\n"
                "At 00:04.500, Goblin1 hands the mug to Elf1.",
                state_actions=goblin_mug_transfer_actions(mug_id),
            ),
        ]))
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-handoff", {"source_sha256": "source"}
            )
        request1_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene"
        ]
        self.assertIn("giver_not_holder", request1_calls[1].args[0][-1]["content"])
        self.assertTrue(payload["request1_result"]["state_actions_dry_run_accepted"])

    def test_reducer_retry_contains_only_first_failure_and_no_prior_attempt_junk(self):
        bundle = goblin_mug_bundle()
        bundle["current_beat_text"] += " Amy watches."
        _state, _location_id, mug_id = goblin_mug_world_state()
        invalid_batch = [
            {
                "action_id": "wrong-giver",
                "op": "handoff",
                "from_subject_id": "subject_2",
                "to_subject_id": "subject_3",
                "prop_id": mug_id,
            },
            {
                "action_id": "unknown-prop",
                "op": "pickup",
                "actor_subject_id": "subject_1",
                "prop_id": "prop_unregistered",
            },
        ]
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(
                "At 00:01.000, Goblin1 picks up the mug.\n"
                "At 00:04.500, Goblin1 hands the mug to Elf1.",
            ),
            director_response(
                "At 00:01.000, Goblin1 picks up the mug.\n"
                "At 00:04.500, Goblin1 hands the mug to Elf1.",
                state_actions=invalid_batch,
            ),
            director_response(
                "At 00:01.000, Goblin1 picks up the mug.\n"
                "At 00:04.500, Goblin1 hands the mug to Elf1.",
                state_actions=goblin_mug_transfer_actions(mug_id),
            ),
        ]))
        physical = mock.Mock(side_effect=[
            {"valid": False, "issue": "stale physical failure from attempt one"},
            {"valid": True, "issue": ""},
            {"valid": True, "issue": ""},
        ])
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch("minimax.validate_director_raw_scene_physical", physical),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_timing", return_value={"valid": True, "issue": ""}),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-first-failure", {"source_sha256": "source"}
            )
        request1_calls = [
            call for call in request.call_args_list
            if call.kwargs.get("history_metadata", {}).get("purpose") == "director_raw_scene"
        ]
        self.assertEqual(len(request1_calls), 3)
        reducer_retry_prompt = request1_calls[2].args[0][-1]["content"]
        self.assertIn("giver_not_holder", reducer_retry_prompt)
        self.assertNotIn("stale physical failure from attempt one", reducer_retry_prompt)
        self.assertNotIn("unknown_entity_id", reducer_retry_prompt)
        self.assertTrue(payload["request1_result"]["state_actions_dry_run_accepted"])

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
            director_response("Mark closes a door with a thud."),
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
        self.assertIn("exact identity_span", text)
        self.assertIn("Never return raw_scene or a rewritten scene", text)
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
        request = mock.Mock(return_value={
            "mappings": [
                {"timestamp": "00:00.000", "surface_form": "a guard", "identity_span": "guard", "subject_name": "Guard1"},
                {"timestamp": "00:05.000", "surface_form": "another guard", "identity_span": "guard", "subject_name": "Guard2"},
            ],
            "subject_descriptions": {}, "subject_wardrobes": {},
        })
        result, names = minimax.resolve_director_raw_scene_subjects(
            original,
            "<Subject 1> is Mara.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            "At 00:00.000, a Guard1 enters the room.\n"
            "At 00:05.000, another Guard2 blocks the door.\n"
            "End continuity state: both guards remain in the room.",
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
            "mappings": [
                {"timestamp": "00:00.000", "surface_form": "a beautiful female elf with long silver hair", "identity_span": "elf", "subject_name": "Elf1"},
                {"timestamp": "00:05.000", "surface_form": "the elf", "identity_span": "elf", "subject_name": "Elf1"},
            ],
            "subject_descriptions": {
                "Elf1": "Elf1 is a beautiful female elf with long silver hair."
            },
            "subject_wardrobes": {
                "Elf1": {
                    "upper": "forest-green fitted tunic", "lower": "brown trousers",
                    "footwear": "soft leather boots", "other": "N/A",
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
            "mappings": [
                {"timestamp": "00:00.000", "surface_form": "Will", "identity_span": "Will", "subject_name": "Will1"},
                {"timestamp": "00:00.000", "surface_form": "Amber", "identity_span": "Amber", "subject_name": "Amber1"},
            ],
            "subject_descriptions": {}, "subject_wardrobes": {},
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
        self.assertIn("Will and Amber watch Zombie2 enter.", result)
        self.assertIn("Zombie2 falls beside Amy.", result)
        self.assertNotIn("Will1", result)
        self.assertNotIn("Amber1", result)
        self.assertNotIn("Zombie2_1", result)
        self.assertEqual(names, [])

    def test_raw_subject_resolution_mapping_cannot_change_timestamps(self):
        original = (
            "At 00:00.000, a guard enters.\n"
            "At 00:05.500, another guard blocks the door.\n"
            "End continuity state: both guards remain in the room."
        )
        request = mock.Mock(return_value={
            "mappings": [
                {"timestamp": "00:00.000", "surface_form": "a guard", "identity_span": "guard", "subject_name": "Guard1"},
                {"timestamp": "00:05.500", "surface_form": "another guard", "identity_span": "guard", "subject_name": "Guard2"},
            ],
            "subject_descriptions": {}, "subject_wardrobes": {},
        })
        result, names = minimax.resolve_director_raw_scene_subjects(
            original, "", llm_request=request, segment_seconds=6.0,
        )
        self.assertEqual(minimax._director_timestamps(result), minimax._director_timestamps(original))
        self.assertEqual(names, ["Guard1", "Guard2"])

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

    def test_raw_scene_physical_prompt_is_narrow_and_checks_order(self):
        messages = minimax.build_director_raw_scene_physical_messages(
            "Amy pushes Will into the closet and closes the door.",
            (
                "At 00:02.000, Amy closes the closet door.\n"
                "At 00:04.000, Will enters the closet."
            ),
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Validate only subject movement in RAW", text)
        self.assertIn("KNOWN SUBJECT STATE", text)
        self.assertIn("does not need an entrance", text)
        self.assertIn("changes support or elevation", text)
        self.assertIn("Ignore prop identity", text)


    def test_request_one_retries_physically_incoherent_raw_scene(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = (
            "Amy pushes Will into the closet and closes the door behind him."
        )
        bad = director_response(
            "At 00:01.000, Amy closes the closet door.\n"
            "At 00:04.500, Will steps into the closet."
        )
        good = director_response(
            "At 00:01.000, Will steps into the closet.\n"
            "At 00:04.500, Amy closes the closet door behind him."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            bad,
            good,
        ]))
        physical = mock.Mock(side_effect=[
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
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 2)
        self.assertEqual(physical.call_count, 2)
        self.assertEqual(prop_state.call_count, 1)
        self.assertEqual(timing.call_count, 1)
        self.assertIn("Will steps into the closet", payload["raw_scene"])
        request_prompts = [
            call.args[0][-1]["content"]
            for call in semantic_calls
            if call.args and isinstance(call.args[0], list) and call.args[0]
            and isinstance(call.args[0][-1], dict)
        ]
        self.assertTrue(any(
            "Fix this physical/spatial problem" in prompt
            and "door closes before Will enters" in prompt
            for prompt in request_prompts
        ))

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
            "At 00:01.000, Amy pours brew into the cup.\n"
            "At 00:04.500, Amy hands the filled cup to Will."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([bad, good]))
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
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 2)
        self.assertEqual(physical.call_count, 2)
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
            "Fix this prop/state problem" in prompt
            and "redirected onto the table" in prompt
            for prompt in request_prompts
        ))

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
            good,
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
        self.assertEqual(len(semantic_calls), 2)
        second_prompt = semantic_calls[1].args[0][-1]["content"]
        self.assertIn("RETRY REQUIREMENTS", second_prompt)
        self.assertNotIn(
            "final timed micro-beat must land in the final quarter",
            second_prompt,
        )
        self.assertIn("mug_1 is still listed as held by Amy", second_prompt)
        self.assertIn("visibly transfers the mug", payload["raw_scene"])

    def test_request_one_completion_self_report_is_non_blocking(self):
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("Mark starts the action.", beat_complete=False),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 1)
        self.assertFalse(payload["request1_result"]["beat_complete"])
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
        self.assertEqual(len(non_audio_llm_calls(request)), 2)
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
        self.assertEqual(len(non_audio_llm_calls(request)), 1)
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
        self.assertEqual(len(non_audio_llm_calls(request)), 1)
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
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
            camera_choreography_rules=minimax.build_director_camera_choreography_rules(1, "initial"),
        )
        self.assertIn("You are the creative director", prompt)
        self.assertIn("CURRENT BEAT is the story authority", prompt)
        self.assertIn("the scene to stage in this clip", prompt)
        self.assertIn("Add only details needed to physically connect or clearly show CURRENT BEAT", prompt)
        self.assertIn("begin at 00:00.000", prompt)
        self.assertNotIn("AUTHORITATIVE FINAL STATE CONTRACT", prompt)
        self.assertIn("finite_activity_complete", prompt)
        self.assertIn("beat_complete", prompt)
        self.assertLess(len(prompt), 4300)
    def test_director_raw_scene_rejects_early_timeline_completion(self):
        raw_scene = (
            "At 00:00.000, Alex reaches for the latch.\n"
            "At 00:01.300, Alex closes the hatch.\n"
            "End continuity state: Alex stands beside the closed hatch."
        )
        errors = minimax._director_raw_scene_structure_errors(
            raw_scene,
            segment_seconds=8,
        )
        self.assertTrue(errors)
        self.assertIn("too early", errors[0])
        self.assertIn("at or after 6s", errors[0])

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

        self.assertEqual(ask_llm.call_count, 3)
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
                "director_raw_scene",
                "director_h3_soundscape",
                "director_h3_music",
            ],
        )
        self.assertEqual(
            ask_llm.call_args_list[1].kwargs["response_format"],
            minimax.H3_SOUNDSCAPE_RESPONSE_FORMAT,
        )
        self.assertEqual(
            ask_llm.call_args_list[2].kwargs["response_format"],
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
            return director_response(raw_scene)

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
            "At 00:00.0, Mark enters the room.\n"
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
            return director_response(raw_scene)

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
            return director_response(raw_scene)

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
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
            camera_choreography_rules=minimax.build_director_camera_choreography_rules(1, "initial"),
        )
        self.assertIn("Add only details needed to physically connect or clearly show CURRENT BEAT", prompt)
        self.assertIn("Preserve spatial continuity", prompt)
        self.assertNotIn("Do not invent structural geography", prompt)
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
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
            camera_choreography_rules=minimax.build_director_camera_choreography_rules(1, "initial"),
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
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
            camera_choreography_rules=minimax.build_director_camera_choreography_rules(1, "initial"),
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
