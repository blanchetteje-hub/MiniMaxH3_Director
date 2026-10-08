import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import minimax
from world_state import (
    UNKNOWN,
    build_director_state_action_contract,
    empty_world_state,
    new_world_state,
    parse_and_dry_run_director_state_actions,
    props_held_by,
    register_explicit_persistent_props,
    reduce_world_state,
    seed_canonical_static_location_state,
    seed_canonical_wardrobes,
    seed_predefined_subject_identities,
    seed_mechanism_action_preconditions,
    seed_story_start_presence,
    stable_world_state_id,
    validate_state_actions,
    validate_world_state,
)


class DestructiveStateMergeRegressionTests(unittest.TestCase):
    def test_sparse_prop_observation_preserves_omitted_facts(self):
        committed = {
            "cup_1": {
                "kind": "cup",
                "owner": "Amy",
                "holder": "N/A",
                "location": "on the shelf",
                "contents": "ale",
                "status": "present",
            }
        }

        merged = minimax.merge_prop_ledger(
            committed,
            {"cup_1": {"kind": "cup", "holder": "Subject Two"}},
        )

        self.assertEqual(merged["cup_1"]["holder"], "Subject Two")
        self.assertEqual(merged["cup_1"]["location"], "N/A")
        self.assertEqual(merged["cup_1"]["contents"], "ale")
        self.assertEqual(merged["cup_1"]["status"], "present")

    def test_n_a_observation_does_not_erase_known_prop_values(self):
        committed = {
            "mug_1": {
                "kind": "mug",
                "holder": "Goblin1",
                "location": "N/A",
                "contents": "ale",
                "status": "present",
            }
        }

        merged = minimax.merge_prop_ledger(
            committed,
            {
                "mug_1": {
                    "kind": "mug",
                    "holder": "N/A",
                    "location": "N/A",
                    "contents": "N/A",
                }
            },
        )

        self.assertEqual(merged["mug_1"]["holder"], "Goblin1")
        self.assertEqual(merged["mug_1"]["contents"], "ale")

    def test_explicit_empty_held_props_clears_but_omission_preserves(self):
        committed = {
            "Amy": {"name": "Amy", "held_props": ["cup_1"]},
        }

        omitted = minimax.merge_subject_state_ledger(
            committed,
            {"subjects": {"Amy": {"name": "Amy"}}},
        )
        cleared = minimax.merge_subject_state_ledger(
            committed,
            {"subjects": {"Amy": {"name": "Amy", "held_props": []}}},
        )

        self.assertEqual(omitted["Amy"]["held_props"], ["cup_1"])
        self.assertEqual(cleared["Amy"]["held_props"], [])

    def test_n_a_wardrobe_does_not_erase_established_slots(self):
        committed = {
            "Amy": {
                "name": "Amy",
                "wardrobe": {
                    "upper": "linen tunic",
                    "lower": "wool trousers",
                    "footwear": "leather boots",
                },
            }
        }

        merged = minimax.merge_subject_state_ledger(
            committed,
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "wardrobe": {
                            "upper": "N/A",
                            "lower": "unknown",
                            "footwear": "barefoot",
                        },
                    }
                }
            },
        )

        self.assertEqual(merged["Amy"]["wardrobe"]["upper"], "linen tunic")
        self.assertEqual(merged["Amy"]["wardrobe"]["lower"], "wool trousers")
        self.assertEqual(merged["Amy"]["wardrobe"]["footwear"], "barefoot")

    def test_registry_merge_does_not_replace_known_facts_with_unknown_defaults(self):
        committed = {
            "Amy": {
                "name": "Amy",
                "subject_id": 1,
                "wardrobe": {"upper": "linen tunic"},
                "held_props": ["cup_1"],
                "position": "beside the counter",
            }
        }
        merged = minimax.merge_subject_state_ledger(
            committed,
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "wardrobe": {"upper": "N/A"},
                        "position": "unknown",
                    }
                }
            },
        )
        registry = minimax.continuity_state_for_registry(
            "<Subject 1> is Amy, a woman.",
            {"subjects": {"Amy": merged["Amy"]}},
        )

        self.assertEqual(merged["Amy"]["wardrobe"]["upper"], "linen tunic")
        self.assertEqual(merged["Amy"]["held_props"], ["cup_1"])
        self.assertEqual(registry["subjects"]["Amy"]["wardrobe"]["upper"], "linen tunic")

    def test_story_wardrobe_extraction_fills_missing_slots_without_replacing_outfit(self):
        state = minimax.new_continuity_state()
        subject = minimax.new_subject_continuity_record({
            "subject_id": 1,
            "name": "Amy",
            "gender": "female",
        })
        subject["wardrobe"].update(upper="linen tunic", lower="wool trousers")
        state["subjects"] = {"Amy": subject}

        updated = minimax.apply_story_subject_wardrobes(
            state,
            "Amy works in a medieval tavern.",
            "<Subject 1> is Amy, a humanoid woman.",
            ["Amy"],
            llm_request=lambda *_args, **_kwargs: {
                "clothing": "blue jacket, leather boots"
            },
        )

        self.assertEqual(updated["subjects"]["Amy"]["wardrobe"]["upper"], "linen tunic")
        self.assertEqual(updated["subjects"]["Amy"]["wardrobe"]["lower"], "wool trousers")
        self.assertEqual(updated["subjects"]["Amy"]["wardrobe"]["footwear"], "leather boots")

    def test_continuity_wardrobe_change_requires_explicit_clothing_action(self):
        definitions = "<Subject 1> is Amy, a humanoid woman."
        committed = minimax.continuity_state_for_registry(definitions)
        committed["subjects"]["Amy"]["wardrobe"].update(
            upper="linen tunic", lower="wool trousers"
        )
        candidate = copy.deepcopy(committed)
        candidate["subjects"]["Amy"]["wardrobe"]["upper"] = "blue jacket"

        rejected = minimax.normalize_structured_continuity_state(
            candidate, definitions, committed_state=committed,
            newest_description="Amy sits at the tavern table.",
        )
        accepted = minimax.normalize_structured_continuity_state(
            candidate, definitions, committed_state=committed,
            newest_description="Amy puts on a blue jacket.",
        )

        self.assertEqual(rejected["subjects"]["Amy"]["wardrobe"]["upper"], "linen tunic")
        self.assertEqual(accepted["subjects"]["Amy"]["wardrobe"]["upper"], "blue jacket")

    def test_explicit_empty_continuity_lists_clear_but_omissions_copy_forward(self):
        definitions = "<Subject 1> is Amy, a humanoid woman."
        committed = minimax.continuity_state_for_registry(definitions)
        committed["subjects"]["Amy"]["held_props"] = ["cup_1"]
        committed["subjects"]["Amy"]["persistent_effects"] = ["ink stains"]
        omitted = copy.deepcopy(committed)
        omitted["subjects"]["Amy"].pop("held_props")
        omitted["subjects"]["Amy"].pop("persistent_effects")
        cleared = copy.deepcopy(committed)
        cleared["subjects"]["Amy"]["held_props"] = []
        cleared["subjects"]["Amy"]["persistent_effects"] = []

        preserved_result = minimax.normalize_structured_continuity_state(
            omitted, definitions, committed_state=committed
        )
        cleared_result = minimax.normalize_structured_continuity_state(
            cleared, definitions, committed_state=committed
        )

        self.assertEqual(preserved_result["subjects"]["Amy"]["held_props"], ["cup_1"])
        self.assertEqual(preserved_result["subjects"]["Amy"]["persistent_effects"], ["ink stains"])
        self.assertEqual(cleared_result["subjects"]["Amy"]["held_props"], [])
        self.assertEqual(cleared_result["subjects"]["Amy"]["persistent_effects"], [])


class WorldStateSeedTests(unittest.TestCase):
    def test_new_world_state_seeds_only_explicit_subject_identities(self):
        seed = {
            "source_path": "subjects.txt",
            "source_sha256": "abc123",
            "subjects": {
                "1": {
                    "subject_id": 1,
                    "name": "Amy",
                    "gender": "female",
                    "picture_ids": [1],
                    "canonical_description": "a woman",
                }
            },
        }

        state = new_world_state(seed)

        self.assertEqual(set(state["subjects"]), {"subject_1"})
        subject = state["subjects"]["subject_1"]
        self.assertEqual(subject["name"], "Amy")
        self.assertEqual(subject["identity"]["canonical_description"], "a woman")
        self.assertEqual(subject["presence"], UNKNOWN)
        self.assertEqual(subject["location_id"], UNKNOWN)
        self.assertEqual(subject["wardrobe"]["upper"], UNKNOWN)
        self.assertEqual(state["props"], {})
        self.assertEqual(state["locations"], {})

    def test_generation_state_ignores_legacy_ledgers_as_seed_authority(self):
        state = minimax.new_generation_state(
            {
                "source_sha256": "run-hash",
                "world_state_seed": {
                    "source_sha256": "subjects-hash",
                    "source_path": "subjects.txt",
                    "subjects": {
                        "1": {
                            "subject_id": 1,
                            "name": "Amy",
                            "gender": "female",
                            "picture_ids": [],
                        }
                    },
                },
                "continuity_state": {
                    "subjects": {"Untrusted": {"position": "at the table"}}
                },
                "prop_ledger": {
                    "untrusted_mug": {"kind": "mug", "holder": "Untrusted"}
                },
            }
        )

        self.assertEqual(set(state["world_state"]["subjects"]), {"subject_1"})
        self.assertEqual(state["world_state"]["props"], {})
        self.assertEqual(state["world_state"]["locations"], {})

    def test_world_state_is_validated_and_round_trips_with_checkpoint(self):
        config = {
            "source_sha256": "run-hash",
            "world_state_seed": {
                "source_sha256": "subjects-hash",
                "source_path": "subjects.txt",
                "subjects": {},
            },
        }
        state = minimax.new_generation_state(config)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generation_state.json"
            minimax.save_generation_state(state, str(path))
            loaded = minimax.load_generation_state(str(path))

        validate_world_state(loaded["world_state"])
        self.assertEqual(loaded["world_state"], state["world_state"])
        self.assertEqual(
            empty_world_state("old-run", "legacy_checkpoint_unseeded")["subjects"],
            {},
        )

    def test_humanoid_identity_requires_clothed_wardrobe_values(self):
        identity = {
            "subject_id": 1,
            "name": "Subject One",
            "gender": "unknown",
            "picture_ids": [],
            "physical_form": "humanoid",
            "source_description": "Subject One is a humanoid individual.",
        }
        state = new_world_state({"subjects": {"1": identity}})
        subject = state["subjects"]["subject_1"]
        self.assertEqual(subject["identity"]["clothing_applicability"], "required")
        self.assertEqual(subject["wardrobe"]["upper"], UNKNOWN)

        subject["wardrobe"] = {
            "upper": [{"garment": "shirt", "condition": "intact"}],
            "lower": [],
            "footwear": [],
            "other": "N/A",
        }
        validate_world_state(state)

        subject["wardrobe"] = {
            "upper": [], "lower": [], "footwear": [], "other": "N/A",
        }
        with self.assertRaisesRegex(ValueError, "requires clothing"):
            validate_world_state(state)

    def test_non_humanoid_animal_can_use_explicit_n_a_wardrobe(self):
        state = new_world_state(
            {
                "subjects": {
                    "1": {
                        "subject_id": 1,
                        "name": "Subject Two",
                        "gender": "unknown",
                        "picture_ids": [],
                        "physical_form": "non_humanoid",
                        "source_description": "Subject Two has a non-humanoid form.",
                    }
                }
            }
        )
        subject = state["subjects"]["subject_1"]
        subject["wardrobe"] = {slot: "N/A" for slot in ("upper", "lower", "footwear", "other")}
        validate_world_state(state)
        self.assertEqual(subject["identity"]["clothing_applicability"], "optional")

    def test_world_state_does_not_infer_body_type_from_subject_name(self):
        state = new_world_state(
            {
                "subjects": {
                    "1": {
                        "subject_id": 1,
                        "name": "Humanoid",
                        "gender": "unknown",
                        "picture_ids": [],
                    }
                }
            }
        )
        subject = state["subjects"]["subject_1"]
        self.assertEqual(subject["identity"]["physical_form"], UNKNOWN)
        self.assertEqual(subject["identity"]["clothing_applicability"], UNKNOWN)
        subject["wardrobe"] = {
            slot: "N/A" for slot in ("upper", "lower", "footwear", "other")
        }
        validate_world_state(state)

    def test_authoritative_seed_reads_type_only_from_subjects_source(self):
        seed = minimax.authoritative_world_state_seed_from_subject_definitions(
            "<Subject 1> is Subject One, a humanoid individual."
        )
        state = new_world_state(seed)
        subject = state["subjects"]["subject_1"]

        self.assertEqual(subject["identity"]["physical_form"], "humanoid")
        self.assertIn("humanoid", subject["identity"]["source_description"])

    def test_story_start_presence_registers_only_explicitly_returned_subjects(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Elf", "gender": UNKNOWN, "picture_ids": []},
            "2": {"subject_id": 2, "name": "Dragon", "gender": UNKNOWN, "picture_ids": []},
        }})
        state, location_id = seed_canonical_static_location_state(
            state,
            {"location": {"name": "Interior"}, "anchors": [], "objects": []},
        )
        state = seed_story_start_presence(
            state,
            [{"name": "Goblin", "initial_state": "seated near the hearth"}],
            location_id=location_id,
        )
        by_name = {item["name"]: item for item in state["subjects"].values()}
        self.assertEqual(by_name["Goblin"]["presence"], "present")
        self.assertEqual(by_name["Goblin"]["location_id"], location_id)
        self.assertEqual(by_name["Elf"]["presence"], UNKNOWN)
        self.assertEqual(by_name["Dragon"]["presence"], UNKNOWN)

        entered = reduce_world_state(state, [{
            "action_id": "elf-entry", "op": "enter",
            "subject_id": "subject_1", "location_id": location_id,
        }], segment_number=1)
        self.assertTrue(entered.committed)
        self.assertEqual(entered.world_state["subjects"]["subject_1"]["presence"], "present")
        self.assertEqual(state["subjects"]["subject_1"]["presence"], UNKNOWN)

    def test_omitted_subject_keeps_explicit_existing_absence_unchanged(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Elf", "gender": UNKNOWN, "picture_ids": []},
            "2": {"subject_id": 2, "name": "Dragon", "gender": UNKNOWN, "picture_ids": []},
        }})
        state, location_id = seed_canonical_static_location_state(
            state, {"location": {"name": "Interior"}, "anchors": [], "objects": []}
        )
        state["subjects"]["subject_2"]["presence"] = "absent"
        state["subjects"]["subject_2"]["provenance"]["presence"] = {
            "authority": "explicit_story_start_absence"
        }
        seeded = seed_story_start_presence(
            state,
            [{"name": "Goblin", "initial_state": "seated near the hearth"}],
            location_id=location_id,
        )
        self.assertEqual(seeded["subjects"]["subject_1"]["presence"], UNKNOWN)
        self.assertEqual(seeded["subjects"]["subject_2"]["presence"], "absent")

    def test_canonical_layered_wardrobe_adapts_without_a_second_model_call(self):
        wardrobes = minimax.world_state_wardrobes_from_character_canon({
            "characters": [{
                "name": "Amy",
                "clothing": "rough-spun shirt, brown trousers, worn leather shoes",
            }]
        })
        self.assertEqual(wardrobes["Amy"]["upper"], [
            {"garment": "rough-spun shirt", "condition": "unknown"}
        ])
        self.assertEqual(wardrobes["Amy"]["lower"], [
            {"garment": "brown trousers", "condition": "unknown"}
        ])
        self.assertEqual(wardrobes["Amy"]["footwear"], [
            {"garment": "leather shoes", "condition": "worn"}
        ])
        self.assertEqual(wardrobes["Amy"]["other"], [])
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
        }})
        seeded = seed_canonical_wardrobes(state, wardrobes)
        self.assertEqual(seeded["subjects"]["subject_1"]["wardrobe"], wardrobes["Amy"])

    def test_non_humanoid_canonical_n_a_wardrobe_is_preserved(self):
        state = new_world_state({"subjects": {
            "1": {
                "subject_id": 1, "name": "Subject One", "gender": UNKNOWN,
                "picture_ids": [], "physical_form": "non_humanoid",
            },
        }})
        wardrobe = minimax.world_state_wardrobes_from_character_canon({
            "characters": [{"name": "Subject One", "clothing": "N/A"}],
        })
        seeded = seed_canonical_wardrobes(state, wardrobe)
        self.assertEqual(
            seeded["subjects"]["subject_1"]["wardrobe"],
            {slot: "N/A" for slot in ("upper", "lower", "footwear", "other")},
        )
        validate_world_state(seeded)

    def test_static_fixture_and_support_ids_are_stable_and_python_generated(self):
        source = {
            "location": {"name": "Hall"},
            "anchors": [{"name": "north door", "type": "door"}],
            "objects": [{
                "name": "bench", "type": "wooden bench",
                "world_state_role": "fixture_support", "mobility": "fixed",
            }, {
                "name": "loose cup", "type": "cup", "world_state_role": "untracked",
            }],
        }
        first, location_id = seed_canonical_static_location_state(empty_world_state(), source)
        second, second_location_id = seed_canonical_static_location_state(empty_world_state(), source)
        self.assertEqual(location_id, second_location_id)
        self.assertEqual(set(first["props"]), set(second["props"]))
        self.assertEqual(len(first["props"]), 2)
        kinds = {prop["name"]: prop["kind"] for prop in first["props"].values()}
        self.assertEqual(kinds, {"north door": "fixture", "bench": "fixture_support"})
        self.assertTrue(all(key.startswith("prop_") for key in first["props"]))
        self.assertEqual(
            stable_world_state_id("location", "Hall"),
            stable_world_state_id("location", "  hall  "),
        )

    def test_duplicate_static_counter_merges_complementary_metadata_once(self):
        state, location_id = seed_canonical_static_location_state(
            empty_world_state(),
            {
                "location": {"name": "Tavern"},
                "anchors": [{
                    "name": "counter", "type": "wooden counter",
                    "wall": "west", "world_state_role": "fixture_support",
                    "mobility": "fixed",
                }],
                "objects": [{
                    "name": "counter", "type": "wooden counter",
                    "near": ["rack", "bar"],
                    "world_state_role": "fixture_support", "mobility": "fixed",
                }],
            },
        )
        self.assertEqual(len(state["props"]), 1)
        counter_id = stable_world_state_id("prop", "counter", scope=location_id)
        self.assertEqual(set(state["props"]), {counter_id})
        counter = state["props"][counter_id]
        registration = counter["provenance"]["registration"]
        self.assertEqual(counter["kind"], "fixture_support")
        self.assertEqual(counter["mobility"], "fixed")
        self.assertEqual(registration["source_fields"], ["anchors", "objects"])
        self.assertEqual(registration["source_type"], "wooden counter")

    def test_exact_duplicate_static_declaration_is_idempotent(self):
        declaration = {
            "name": "front door", "type": "door",
            "world_state_role": "fixture", "mobility": "fixed",
        }
        source = {
            "location": {"name": "Hall"},
            "anchors": [declaration, dict(declaration)],
            "objects": [],
        }
        first, location_id = seed_canonical_static_location_state(
            empty_world_state(), source
        )
        second, second_location_id = seed_canonical_static_location_state(
            first, source
        )
        self.assertEqual(location_id, second_location_id)
        self.assertEqual(first, second)
        self.assertEqual(len(second["props"]), 1)

    def test_static_fixture_and_support_roles_merge_to_combined_role(self):
        state, location_id = seed_canonical_static_location_state(
            empty_world_state(),
            {
                "location": {"name": "Room"},
                "anchors": [{
                    "name": "work table", "type": "table",
                    "world_state_role": "fixture", "mobility": "fixed",
                }],
                "objects": [{
                    "name": "work table", "type": "wooden table",
                    "world_state_role": "support", "mobility": "fixed",
                }],
            },
        )
        self.assertEqual(len(state["props"]), 1)
        table_id = stable_world_state_id("prop", "work table", scope=location_id)
        self.assertEqual(state["props"][table_id]["kind"], "fixture_support")
        self.assertEqual(state["props"][table_id]["mobility"], "fixed")
        self.assertEqual(
            state["props"][table_id]["provenance"]["registration"]["source_type"],
            "wooden table",
        )

    def test_duplicate_static_identity_with_conflicting_mobility_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Conflicting canonical fixture mobility"):
            seed_canonical_static_location_state(
                empty_world_state(),
                {
                    "location": {"name": "Room"},
                    "anchors": [{
                        "name": "counter", "type": "counter",
                        "world_state_role": "fixture_support", "mobility": "fixed",
                    }],
                    "objects": [{
                        "name": "counter", "type": "counter",
                        "world_state_role": "fixture_support", "mobility": "movable",
                    }],
                },
            )

    def test_duplicate_static_identity_with_incompatible_type_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Conflicting canonical fixture types"):
            seed_canonical_static_location_state(
                empty_world_state(),
                {
                    "location": {"name": "Room"},
                    "anchors": [{
                        "name": "counter", "type": "wooden counter",
                        "world_state_role": "fixture_support", "mobility": "fixed",
                    }],
                    "objects": [{
                        "name": "counter", "type": "door",
                        "world_state_role": "fixture_support", "mobility": "fixed",
                    }],
                },
            )

    def test_duplicate_static_identity_with_conflicting_placement_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Conflicting canonical fixture wall"):
            seed_canonical_static_location_state(
                empty_world_state(),
                {
                    "location": {"name": "Room"},
                    "anchors": [{
                        "name": "front door", "type": "door", "wall": "north",
                        "world_state_role": "fixture", "mobility": "fixed",
                    }],
                    "objects": [{
                        "name": "front door", "type": "door", "wall": "south",
                        "world_state_role": "fixture", "mobility": "fixed",
                    }],
                },
            )

    def test_static_fixture_id_is_independent_of_source_array(self):
        anchor_only = {
            "location": {"name": "Hall"},
            "anchors": [{
                "name": "bench", "type": "wooden bench",
                "world_state_role": "fixture_support", "mobility": "fixed",
            }],
            "objects": [],
        }
        object_only = {
            "location": {"name": "Hall"}, "anchors": [],
            "objects": [{
                "name": "bench", "type": "wooden bench",
                "world_state_role": "fixture_support", "mobility": "fixed",
            }],
        }
        both = {
            "location": {"name": "Hall"},
            "anchors": [dict(anchor_only["anchors"][0])],
            "objects": [dict(object_only["objects"][0])],
        }
        seeded = [
            seed_canonical_static_location_state(empty_world_state(), source)[0]
            for source in (anchor_only, object_only, both)
        ]
        ids = [next(iter(state["props"])) for state in seeded]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(ids[1], ids[2])
        self.assertTrue(all(len(state["props"]) == 1 for state in seeded))

    def test_explicit_persistent_prop_registration_requires_and_sets_one_placement(self):
        state, location_id = seed_canonical_static_location_state(
            empty_world_state(),
            {"location": {"name": "Room"}, "anchors": [], "objects": []},
        )
        state = register_explicit_persistent_props(state, [{
            "name": "silver key", "kind": "object", "mobility": "movable",
            "needed_for_state": True, "reason": "It is picked up and carried across segments.",
            "location_id": location_id,
        }])
        self.assertEqual(len(state["props"]), 1)
        prop = next(iter(state["props"].values()))
        self.assertEqual(prop["placement"], {"kind": "located", "location_id": location_id})
        self.assertNotIn("holder_subject_id", prop["placement"])
        with self.assertRaisesRegex(ValueError, "only when explicitly needed"):
            register_explicit_persistent_props(state, [{
                "name": "cup", "kind": "object", "mobility": "movable",
                "needed_for_state": False, "reason": "ordinary detail", "location_id": location_id,
            }])
        with self.assertRaisesRegex(ValueError, "assigned by Python"):
            register_explicit_persistent_props(state, [{
                "id": "invented", "name": "cup", "kind": "object", "mobility": "movable",
                "needed_for_state": True, "reason": "cross-segment action", "location_id": location_id,
            }])

    def test_legacy_visual_raw_and_accepted_state_do_not_seed_world_state(self):
        state = minimax.new_generation_state({
            "world_state_seed": {"subjects": {}},
            "continuity_state": {"subjects": {"Legacy": {"position": "here"}}},
            "accepted_beat_state": {"subjects": {"Legacy": {"location": "there"}}},
            "raw_scene": "Legacy picks up a coin.",
            "visual_observation": {"subjects": {"Legacy": {"presence": "present"}}},
            "subject_state_ledger": {"Legacy": {"presence": "present"}},
            "prop_ledger": {"coin": {"holder": "Legacy"}},
        })
        self.assertEqual(state["world_state"]["subjects"], {})
        self.assertEqual(state["world_state"]["props"], {})
        self.assertEqual(state["world_state"]["locations"], {})

    def test_director_contract_uses_only_registered_ids_and_dry_runs_same_response(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
        }})
        state, location_id = seed_canonical_static_location_state(
            state, {"location": {"name": "Room"}, "anchors": [], "objects": []}
        )
        state = seed_story_start_presence(
            state, [{"name": "Amy", "initial_state": "standing"}], location_id=location_id
        )
        contract = build_director_state_action_contract(state)
        self.assertEqual([item["id"] for item in contract["vocabulary"]["subjects"]], ["subject_1"])
        self.assertEqual([item["id"] for item in contract["vocabulary"]["locations"]], [location_id])
        self.assertIn("never invent entity IDs", contract["instruction"])
        schema = contract["response_format"]["json_schema"]["schema"]
        self.assertIn("raw_scene", schema["required"])
        self.assertIn("state_actions", schema["required"])

        response = {
            "raw_scene": "Amy stays in the room.",
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
            "state_actions": [{
                "action_id": "invented-ref",
                "op": "enter",
                "subject_id": "subject_not_registered",
                "location_id": location_id,
            }],
        }
        result = parse_and_dry_run_director_state_actions(
            state, response, segment_number=1
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["outcomes"][0].code, "unknown_entity_id")
        self.assertEqual(state["subjects"]["subject_1"]["presence"], "present")


def make_reducer_state():
    state = new_world_state({
        "source_sha256": "test-source",
        "source_path": "subjects.txt",
        "subjects": {
            "1": {"subject_id": 1, "name": "Subject One", "gender": UNKNOWN, "picture_ids": []},
            "2": {"subject_id": 2, "name": "Subject Two", "gender": UNKNOWN, "picture_ids": []},
        },
    })
    state["locations"] = {
        "location_a": {"id": "location_a", "name": "Area A"},
        "location_b": {"id": "location_b", "name": "Area B"},
    }
    for subject_id in ("subject_1", "subject_2"):
        state["subjects"][subject_id].update({
            "presence": "present",
            "location_id": "location_a",
            "support_id": None,
            "posture": "standing",
        })

    def prop(
        prop_id, name, kind="object", mobility="movable", *,
        location_id="location_a", support_id=None, capabilities=None,
        contents=None, mechanism_state=UNKNOWN, status="present", placement=None,
    ):
        if placement is None:
            placement = {"kind": "located", "location_id": location_id}
            if support_id is not None:
                placement["support_id"] = support_id
        return {
            "id": prop_id,
            "name": name,
            "kind": kind,
            "mobility": mobility,
            "status": status,
            "placement": dict(placement),
            "contents": list(contents or []),
            "capabilities": {
                "container": UNKNOWN,
                "consumable": UNKNOWN,
                "openable": UNKNOWN,
                "lockable": UNKNOWN,
                **(capabilities or {}),
            },
            "mechanism_state": mechanism_state,
            "condition": UNKNOWN,
            "provenance": {},
        }

    state["props"] = {
        "prop_support_a": prop("prop_support_a", "Support A", "support", "fixed"),
        "prop_support_b": prop(
            "prop_support_b", "Support B", "fixture_support", "fixed",
            location_id="location_b",
        ),
        "prop_movable": prop(
            "prop_movable", "Movable object", support_id="prop_support_a"
        ),
        "prop_fixed": prop("prop_fixed", "Fixed object", "fixture", "fixed"),
        "prop_source": prop(
            "prop_source", "Source vessel", "container", capabilities={"container": True},
            contents=[{"substance": "liquid", "amount": "some", "consumable": UNKNOWN}],
        ),
        "prop_target": prop(
            "prop_target", "Target vessel", "container", capabilities={"container": True},
        ),
        "prop_food": prop(
            "prop_food", "Food", "consumable", capabilities={"consumable": True},
            contents=[{"substance": "food", "amount": "some", "consumable": True}],
            placement={"kind": "held", "subject_id": "subject_1"},
        ),
        "prop_door": prop(
            "prop_door", "Door", "fixture", "fixed",
            capabilities={"openable": True, "lockable": True},
            mechanism_state="closed",
        ),
    }
    # The explicitly tracked food is currently held by Subject One.
    state["props"]["prop_food"]["placement"] = {
        "kind": "held", "subject_id": "subject_1"
    }
    validate_world_state(state)
    return state


class WorldStateReducerTests(unittest.TestCase):
    def action(self, action_id, op, **fields):
        return {"action_id": action_id, "op": op, **fields}

    def test_reduce_is_pure_and_dry_run_uses_same_ordered_rules(self):
        state = make_reducer_state()
        before = copy.deepcopy(state)
        actions = [
            self.action(
                "take", "pickup", actor_subject_id="subject_1", prop_id="prop_movable"
            ),
            self.action(
                "set-down", "place", actor_subject_id="subject_1",
                prop_id="prop_movable", location_id="location_a",
                support_id="prop_support_a",
            ),
        ]

        validated = validate_state_actions(state, actions, segment_number=3)
        reduced = reduce_world_state(state, actions, segment_number=3)

        self.assertEqual(validated, reduced.outcomes)
        self.assertTrue(all(outcome.accepted for outcome in reduced.outcomes))
        self.assertEqual(state, before)
        self.assertEqual(
            reduced.world_state["props"]["prop_movable"]["placement"],
            {"kind": "located", "location_id": "location_a", "support_id": "prop_support_a"},
        )
        self.assertEqual(props_held_by(reduced.world_state, "subject_1"), ["prop_food"])
        self.assertNotIn("held_props", reduced.world_state["subjects"]["subject_1"])
        self.assertEqual(reduced.world_state["revision"], state["revision"] + 1)
        self.assertTrue(reduced.committed)

    def test_failed_action_batch_returns_original_state_and_stops_at_first_failure(self):
        state = make_reducer_state()
        before = copy.deepcopy(state)
        result = reduce_world_state(
            state,
            [
                self.action(
                    "take", "pickup", actor_subject_id="subject_1",
                    prop_id="prop_movable",
                ),
                self.action(
                    "bad-place", "place", actor_subject_id="subject_1",
                    prop_id="prop_movable", location_id="location_b",
                ),
                self.action(
                    "must-not-run", "enter", subject_id="subject_2",
                    location_id="location_b",
                ),
            ],
            segment_number=1,
        )

        self.assertFalse(result.committed)
        self.assertEqual(result.world_state, before)
        self.assertIsNot(result.world_state, state)
        self.assertEqual(len(result.outcomes), 2)
        self.assertTrue(result.outcomes[0].accepted)
        self.assertFalse(result.outcomes[1].accepted)
        self.assertEqual(result.outcomes[1].code, "destination_location_mismatch")

    def test_empty_and_fully_valid_batches_commit(self):
        state = make_reducer_state()
        empty = reduce_world_state(state, [], segment_number=1)
        valid = reduce_world_state(
            state,
            [self.action("leave-support", "set_support", subject_id="subject_1", support_id=None)],
            segment_number=1,
        )
        self.assertTrue(empty.committed)
        self.assertTrue(valid.committed)

    def test_subject_can_enter_location_then_take_registered_support(self):
        state = make_reducer_state()
        subject = state["subjects"]["subject_2"]
        subject.update({
            "presence": "unknown",
            "location_id": None,
            "support_id": None,
            "posture": UNKNOWN,
        })

        result = reduce_world_state(
            state,
            [
                self.action(
                    "subject-enters", "enter",
                    subject_id="subject_2", location_id="location_b",
                ),
                self.action(
                    "subject-sits", "set_support",
                    subject_id="subject_2", support_id="prop_support_b",
                    resulting_posture="seated",
                ),
            ],
            segment_number=1,
        )

        self.assertTrue(result.committed)
        entered = result.world_state["subjects"]["subject_2"]
        self.assertEqual(entered["presence"], "present")
        self.assertEqual(entered["location_id"], "location_b")
        self.assertEqual(entered["support_id"], "prop_support_b")
        self.assertEqual(entered["posture"], "seated")

    def test_pickup_rejects_fixed_object_and_unknown_mobility(self):
        state = make_reducer_state()
        state["props"]["prop_mobile_unknown"] = copy.deepcopy(state["props"]["prop_movable"])
        state["props"]["prop_mobile_unknown"]["id"] = "prop_mobile_unknown"
        state["props"]["prop_mobile_unknown"]["mobility"] = UNKNOWN
        result = reduce_world_state(
            state,
            [self.action("fixed", "pickup", actor_subject_id="subject_1", prop_id="prop_fixed")],
            segment_number=1,
        )
        unknown_mobility = reduce_world_state(
            state,
            [self.action("unknown", "pickup", actor_subject_id="subject_1", prop_id="prop_mobile_unknown")],
            segment_number=1,
        )
        self.assertEqual([outcome.code for outcome in result.outcomes], ["fixed_object"])
        self.assertEqual([outcome.code for outcome in unknown_mobility.outcomes], ["mobility_unknown"])
        self.assertFalse(result.committed)
        self.assertFalse(unknown_mobility.committed)
        self.assertEqual(result.world_state, state)

    def test_prop_has_one_placement_and_held_lists_are_derived(self):
        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [self.action("take", "pickup", actor_subject_id="subject_1", prop_id="prop_movable")],
            segment_number=1,
        )
        prop = result.world_state["props"]["prop_movable"]
        self.assertEqual(prop["placement"], {"kind": "held", "subject_id": "subject_1"})
        self.assertNotIn("holder_subject_id", prop)
        self.assertNotIn("location_id", prop)
        self.assertEqual(props_held_by(result.world_state, "subject_1"), ["prop_food", "prop_movable"])

    def test_move_clears_support_and_keeps_presence(self):
        state = make_reducer_state()
        state["subjects"]["subject_1"]["support_id"] = "prop_support_a"
        validate_world_state(state)
        result = reduce_world_state(
            state,
            [self.action("move", "move", subject_id="subject_1", destination_location_id="location_b")],
            segment_number=2,
        )
        subject = result.world_state["subjects"]["subject_1"]
        self.assertEqual(subject["presence"], "present")
        self.assertEqual(subject["location_id"], "location_b")
        self.assertIsNone(subject["support_id"])

    def test_same_location_move_remains_unrepresentable_and_rejected(self):
        state = make_reducer_state()
        before = copy.deepcopy(state)
        raw_only = reduce_world_state(state, [], segment_number=2)
        self.assertTrue(raw_only.committed)
        self.assertEqual(raw_only.world_state, before)
        result = reduce_world_state(
            state,
            [self.action(
                "same-room-reposition", "move", subject_id="subject_1",
                destination_location_id="location_a", support_id=None,
            )],
            segment_number=2,
        )
        self.assertFalse(result.committed)
        self.assertEqual(result.world_state, before)
        self.assertEqual(
            [outcome.code for outcome in result.outcomes],
            ["movement_not_representable"],
        )

    def test_move_can_explicitly_establish_new_support(self):
        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [self.action(
                "move", "move", subject_id="subject_1",
                destination_location_id="location_b", support_id="prop_support_b",
            )],
            segment_number=2,
        )
        subject = result.world_state["subjects"]["subject_1"]
        self.assertEqual(subject["presence"], "present")
        self.assertEqual(subject["support_id"], "prop_support_b")

    def test_set_support_null_leaves_support(self):
        state = make_reducer_state()
        state["subjects"]["subject_1"]["support_id"] = "prop_support_a"
        validate_world_state(state)
        result = reduce_world_state(
            state,
            [self.action("leave", "set_support", subject_id="subject_1", support_id=None)],
            segment_number=2,
        )
        self.assertIsNone(result.world_state["subjects"]["subject_1"]["support_id"])

    def test_enter_and_exit_set_exact_presence_semantics(self):
        state = make_reducer_state()
        state["subjects"]["subject_2"].update(
            presence="absent", location_id=UNKNOWN, support_id=None
        )
        entered = reduce_world_state(
            state,
            [self.action("in", "enter", subject_id="subject_2", location_id="location_a")],
            segment_number=1,
        )
        self.assertEqual(entered.world_state["subjects"]["subject_2"]["presence"], "present")
        exited = reduce_world_state(
            entered.world_state,
            [self.action("out", "exit", subject_id="subject_2")],
            segment_number=2,
        )
        subject = exited.world_state["subjects"]["subject_2"]
        self.assertEqual(subject["presence"], "absent")
        self.assertEqual(subject["location_id"], UNKNOWN)

    def test_off_camera_has_no_operation_and_empty_actions_leave_state_unchanged(self):
        state = make_reducer_state()
        no_actions = reduce_world_state(state, [], segment_number=1)
        self.assertEqual(no_actions.world_state, state)
        invalid = validate_state_actions(
            state,
            [self.action("offscreen", "off_camera", subject_id="subject_1")],
            segment_number=1,
        )
        self.assertEqual(invalid[0].code, "unknown_operation")

    def test_pour_uses_all_or_partial_coarse_amounts(self):
        state = make_reducer_state()
        partial = reduce_world_state(
            state,
            [self.action(
                "partial", "pour", actor_subject_id="subject_1",
                source_prop_id="prop_source", target_prop_id="prop_target",
                substance="liquid", amount="partial",
            )],
            segment_number=1,
        )
        self.assertTrue(partial.outcomes[0].accepted)
        self.assertEqual(partial.world_state["props"]["prop_source"]["contents"][0]["amount"], "some")
        self.assertEqual(partial.world_state["props"]["prop_target"]["contents"][0]["amount"], "some")
        all_poured = reduce_world_state(
            state,
            [self.action(
                "all", "pour", actor_subject_id="subject_1",
                source_prop_id="prop_source", target_prop_id="prop_target",
                substance="liquid", amount="all",
            )],
            segment_number=1,
        )
        self.assertEqual(all_poured.world_state["props"]["prop_source"]["contents"][0]["amount"], "none")
        self.assertEqual(all_poured.world_state["props"]["prop_target"]["contents"][0]["amount"], "some")

    def test_fill_adds_explicit_substance_without_source_prop(self):
        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [self.action(
                "fill-cup", "fill", actor_subject_id="subject_1",
                target_prop_id="prop_target", substance="special brew",
            )],
            segment_number=4,
        )
        self.assertTrue(result.committed)
        self.assertEqual(result.world_state["props"]["prop_target"]["contents"], [{
            "substance": "special brew", "amount": "some", "consumable": UNKNOWN,
        }])
        self.assertEqual(state["props"]["prop_target"]["contents"], [])

    def test_explicit_consume_can_learn_unknown_substance_is_consumable(self):
        state = make_reducer_state()
        filled = reduce_world_state(
            state,
            [self.action(
                "fill", "fill", actor_subject_id="subject_1",
                target_prop_id="prop_target", substance="special brew",
            )],
            segment_number=4,
        )
        consumed = reduce_world_state(
            filled.world_state,
            [self.action(
                "sip", "consume", actor_subject_id="subject_1",
                prop_id="prop_target", substance="special brew", amount="partial",
            )],
            segment_number=5,
        )
        self.assertTrue(consumed.committed)
        self.assertEqual(consumed.world_state["props"]["prop_target"]["contents"], [{
            "substance": "special brew", "amount": "some", "consumable": True,
        }])

    def test_fill_requires_present_colocated_actor_known_container_and_substance(self):
        state = make_reducer_state()
        base_action = self.action(
            "fill", "fill", actor_subject_id="subject_1",
            target_prop_id="prop_target", substance="special brew",
        )
        state["subjects"]["subject_1"]["presence"] = "absent"
        result = reduce_world_state(state, [base_action], segment_number=4)
        self.assertFalse(result.committed)
        self.assertEqual(result.outcomes[0].code, "subject_not_known_present")

        state = make_reducer_state()
        state["props"]["prop_target"]["placement"]["location_id"] = "location_b"
        validate_world_state(state)
        result = reduce_world_state(state, [base_action], segment_number=4)
        self.assertFalse(result.committed)
        self.assertEqual(result.outcomes[0].code, "prop_location_mismatch")

        state = make_reducer_state()
        state["props"]["prop_target"]["capabilities"]["container"] = UNKNOWN
        result = reduce_world_state(state, [base_action], segment_number=4)
        self.assertFalse(result.committed)
        self.assertEqual(result.outcomes[0].code, "not_known_container")

        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [self.action(
                "fill-empty", "fill", actor_subject_id="subject_1",
                target_prop_id="prop_target", substance="  ",
            )],
            segment_number=4,
        )
        self.assertFalse(result.committed)
        self.assertEqual(result.outcomes[0].code, "invalid_substance")

    def test_partial_transfer_rejects_unknown_quantity(self):
        state = make_reducer_state()
        state["props"]["prop_source"]["contents"][0]["amount"] = UNKNOWN
        validate_world_state(state)
        outcomes = validate_state_actions(
            state,
            [self.action(
                "partial", "pour", actor_subject_id="subject_1",
                source_prop_id="prop_source", target_prop_id="prop_target",
                substance="liquid", amount="partial",
            )],
            segment_number=1,
        )
        self.assertEqual(outcomes[0].code, "partial_amount_unknown")

    def test_consume_requires_explicitly_consumable_content(self):
        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [self.action(
                "eat", "consume", actor_subject_id="subject_1",
                prop_id="prop_food", substance="food", amount="all",
            )],
            segment_number=1,
        )
        self.assertTrue(result.outcomes[0].accepted)
        self.assertEqual(result.world_state["props"]["prop_food"]["status"], "consumed")
        self.assertEqual(result.world_state["props"]["prop_food"]["placement"], {"kind": "unknown"})

    def test_clothing_change_requires_exact_known_layer_and_preserves_required_clothing(self):
        state = make_reducer_state()
        subject = state["subjects"]["subject_1"]
        subject["identity"]["physical_form"] = "humanoid"
        subject["identity"]["clothing_applicability"] = "required"
        subject["wardrobe"] = {
            "upper": [
                {"garment": "shirt", "condition": "torn"},
                {"garment": "coat", "condition": "intact"},
                {"garment": "vest", "condition": "worn"},
            ],
            "lower": [{"garment": "trousers", "condition": "intact"}],
            "footwear": [],
            "other": "N/A",
        }
        validate_world_state(state)
        result = reduce_world_state(
            state,
            [
                self.action(
                    "remove-vest", "change_clothing", subject_id="subject_1",
                    change="remove", slot="upper", garment="vest",
                ),
                self.action(
                    "replace-shirt", "change_clothing", subject_id="subject_1",
                    change="replace", slot="upper", garment="tunic",
                    condition="clean", replaces="shirt",
                ),
                self.action(
                    "tear-tunic", "change_clothing", subject_id="subject_1",
                    change="set_condition", slot="upper", garment="tunic",
                    condition="torn",
                ),
            ],
            segment_number=2,
        )
        self.assertTrue(all(outcome.accepted for outcome in result.outcomes))
        self.assertEqual(
            result.world_state["subjects"]["subject_1"]["wardrobe"]["upper"],
            [
                {"garment": "tunic", "condition": "torn"},
                {"garment": "coat", "condition": "intact"},
            ],
        )
        self.assertEqual(
            result.world_state["subjects"]["subject_1"]["wardrobe"]["lower"],
            [{"garment": "trousers", "condition": "intact"}],
        )
        # Removing the final upper layer is allowed while a lower garment remains.
        remove_upper = reduce_world_state(
            result.world_state,
            [self.action(
                "remove-coat", "change_clothing", subject_id="subject_1",
                change="remove", slot="upper", garment="coat",
            )],
            segment_number=3,
        )
        self.assertTrue(remove_upper.committed)
        self.assertEqual(remove_upper.world_state["subjects"]["subject_1"]["wardrobe"]["upper"], [
            {"garment": "tunic", "condition": "torn"},
        ])

        # A required-clothing subject cannot remove the last recorded garment.
        result.world_state["subjects"]["subject_1"]["wardrobe"]["lower"] = []
        result.world_state["subjects"]["subject_1"]["wardrobe"]["upper"] = [
            {"garment": "tunic", "condition": "torn"},
        ]
        validate_world_state(result.world_state)
        forbidden = reduce_world_state(
            result.world_state,
            [self.action(
                "remove-last", "change_clothing", subject_id="subject_1",
                change="remove", slot="upper", garment="tunic",
            )],
            segment_number=4,
        )
        self.assertEqual(forbidden.outcomes[0].code, "clothing_required")
        self.assertFalse(forbidden.committed)
        self.assertEqual(forbidden.world_state, result.world_state)

    def test_mechanism_operations_follow_explicit_states_and_capabilities(self):
        state = make_reducer_state()
        result = reduce_world_state(
            state,
            [
                self.action("lock", "lock", actor_subject_id="subject_1", prop_id="prop_door"),
                self.action("unlock", "unlock", actor_subject_id="subject_1", prop_id="prop_door"),
                self.action("open", "open", actor_subject_id="subject_1", prop_id="prop_door"),
                self.action("close", "close", actor_subject_id="subject_1", prop_id="prop_door"),
            ],
            segment_number=1,
        )
        self.assertTrue(all(outcome.accepted for outcome in result.outcomes))
        self.assertEqual(result.world_state["props"]["prop_door"]["mechanism_state"], "closed")

    def test_authored_open_close_actions_seed_only_unknown_logical_preconditions(self):
        state = make_reducer_state()
        state["props"]["prop_door"]["mechanism_state"] = UNKNOWN
        opened = seed_mechanism_action_preconditions(
            state,
            [{"prop_id": "prop_door", "op": "open", "evidence": "opens the door"}],
            segment_number=1,
        )
        self.assertEqual(opened["props"]["prop_door"]["mechanism_state"], "closed")
        open_result = reduce_world_state(
            opened,
            [{"action_id": "open-door", "op": "open", "actor_subject_id": "subject_1", "prop_id": "prop_door"}],
            segment_number=1,
        )
        self.assertTrue(open_result.committed)
        self.assertEqual(open_result.world_state["props"]["prop_door"]["mechanism_state"], "open")

        state["props"]["prop_door"]["mechanism_state"] = UNKNOWN
        closed = seed_mechanism_action_preconditions(
            state,
            [{"prop_id": "prop_door", "op": "close", "evidence": "shuts the door"}],
            segment_number=2,
        )
        self.assertEqual(closed["props"]["prop_door"]["mechanism_state"], "open")
        close_result = reduce_world_state(
            closed,
            [{"action_id": "close-door", "op": "close", "actor_subject_id": "subject_1", "prop_id": "prop_door"}],
            segment_number=2,
        )
        self.assertTrue(close_result.committed)
        self.assertEqual(close_result.world_state["props"]["prop_door"]["mechanism_state"], "closed")

        established_open = copy.deepcopy(state)
        established_open["props"]["prop_door"]["mechanism_state"] = "open"
        preserved = seed_mechanism_action_preconditions(
            established_open,
            [{"prop_id": "prop_door", "op": "open", "evidence": "opens the door"}],
            segment_number=3,
        )
        self.assertEqual(preserved["props"]["prop_door"]["mechanism_state"], "open")
        contradiction = reduce_world_state(
            preserved,
            [{"action_id": "open-again", "op": "open", "actor_subject_id": "subject_1", "prop_id": "prop_door"}],
            segment_number=3,
        )
        self.assertFalse(contradiction.committed)
        self.assertEqual(contradiction.outcomes[0].code, "mechanism_prerequisite_not_met")

        established_closed = copy.deepcopy(state)
        established_closed["props"]["prop_door"]["mechanism_state"] = "closed"
        preserved = seed_mechanism_action_preconditions(
            established_closed,
            [{"prop_id": "prop_door", "op": "close", "evidence": "closes the door"}],
            segment_number=4,
        )
        self.assertEqual(preserved["props"]["prop_door"]["mechanism_state"], "closed")
        contradiction = reduce_world_state(
            preserved,
            [{"action_id": "close-again", "op": "close", "actor_subject_id": "subject_1", "prop_id": "prop_door"}],
            segment_number=4,
        )
        self.assertFalse(contradiction.committed)
        self.assertEqual(contradiction.outcomes[0].code, "mechanism_prerequisite_not_met")

    def test_unknown_ids_and_generic_patch_operations_are_rejected(self):
        state = make_reducer_state()
        outcomes = validate_state_actions(
            state,
            [self.action("unknown", "pickup", actor_subject_id="subject_1", prop_id="prop_unknown")],
            segment_number=1,
        )
        self.assertEqual(outcomes[0].code, "unknown_entity_id")
        patch_action = validate_state_actions(
            state,
            [self.action("patch", "set_subject_field", subject_id="subject_1", field="presence", value="absent")],
            segment_number=1,
        )
        self.assertEqual(patch_action[0].code, "unknown_operation")

    def test_schema_rejects_non_boolean_capabilities(self):
        state = make_reducer_state()
        state["props"]["prop_target"]["capabilities"]["container"] = 1
        with self.assertRaisesRegex(ValueError, "invalid capability value"):
            validate_world_state(state)



class CurrentSegmentPropVocabularyTests(unittest.TestCase):
    @staticmethod
    def _static_alias_test_state(name, source_type, *, role="fixture"):
        return seed_canonical_static_location_state(
            empty_world_state(),
            {
                "location": {"name": "Hall"},
                "anchors": [],
                "objects": [{
                    "name": name,
                    "type": source_type,
                    "world_state_role": role,
                    "mobility": "fixed",
                }],
            },
        )

    @staticmethod
    def _candidate(
        name, evidence, *, mobility="unknown", initial_location="Hall"
    ):
        return {
            "name": name,
            "kind": "object",
            "mobility": mobility,
            "initial_location": initial_location,
            "initial_holder": None,
            "support_name": None,
            "contents": [],
            "capabilities": {
                "container": "unknown",
                "consumable": "unknown",
                "openable": "unknown",
                "lockable": "unknown",
            },
            "reason": "needed for current-segment state reasoning",
            "evidence": evidence,
        }

    def test_stone_door_alias_resolves_to_entrance_fixture(self):
        state, _ = self._static_alias_test_state("entrance", "door")
        result = minimax.extract_current_segment_persistent_props(
            "The stone door opens.",
            "The stone door opens.",
            state,
            llm_request=lambda *_args, **_kwargs: {
                "props": [self._candidate("stone door", "stone door")]
            },
        )
        self.assertEqual(result, [])

    def test_balanced_outer_quotes_are_removed_from_exact_prop_evidence(self):
        state = make_reducer_state()
        candidate = self._candidate(
            "silver mug",
            '"holding a silver mug in one hand."',
            mobility="movable",
            initial_location=None,
        )
        candidate["initial_holder"] = "Subject One"
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Subject One is holding a silver mug in one hand.",
            "Subject One is holding a silver mug in one hand.",
            state,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["evidence"], "holding a silver mug in one hand.")

    def test_heavy_oak_door_alias_resolves_to_front_door_fixture(self):
        state, _ = self._static_alias_test_state("front door", "door")
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [self._candidate("heavy oak door", "heavy oak door")]},
            "Amy opens the heavy oak door.",
            "Amy opens the heavy oak door.",
            state,
        )
        self.assertEqual(result, [])

    def test_heavy_oak_door_with_fixture_name_as_initial_location_is_omitted(self):
        state, _ = self._static_alias_test_state("front door", "door")
        candidate = self._candidate(
            "heavy oak door",
            "heavy oak door",
            initial_location="front door",
        )
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Amy opens the heavy oak door.",
            "Amy opens the heavy oak door.",
            state,
        )
        self.assertEqual(result, [])

    def test_distinct_movable_object_with_same_type_noun_is_not_merged(self):
        state, _ = self._static_alias_test_state("front door", "door")
        candidate = self._candidate("miniature door", "miniature door", mobility="movable")
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Amy carries a miniature door.",
            "Amy carries a miniature door.",
            state,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "miniature door")

    def test_current_segment_extractor_never_creates_new_fixed_scene_entity(self):
        state, _ = self._static_alias_test_state("front entrance", "door")
        candidate = self._candidate(
            "iron latch",
            "iron latch on the front entrance",
            mobility="fixed",
            initial_location="Hall",
        )
        candidate["support_name"] = "front entrance"
        candidate["capabilities"]["openable"] = True
        candidate["capabilities"]["lockable"] = True
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Amy pushes the iron latch on the front entrance.",
            "Amy pushes the iron latch on the front entrance.",
            state,
        )
        self.assertEqual(result, [])

    def test_alias_matching_multiple_same_type_fixtures_fails_closed(self):
        state, _ = seed_canonical_static_location_state(
            empty_world_state(),
            {
                "location": {"name": "Hall"},
                "anchors": [
                    {"name": "entrance", "type": "door"},
                    {"name": "front door", "type": "door"},
                ],
                "objects": [],
            },
        )
        with self.assertRaisesRegex(ValueError, "ambiguously matches multiple"):
            minimax.parse_current_segment_persistent_prop_result(
                {"props": [self._candidate("stone door", "stone door")]},
                "The stone door opens.",
                "The stone door opens.",
                state,
            )

    def test_support_alias_is_omitted_as_canonical_python_owned_entity(self):
        state, _ = self._static_alias_test_state(
            "bar counter", "counter", role="fixture_support"
        )
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [self._candidate(
                "stone counter", "stone counter", initial_location="bar counter"
            )]},
            "Amy leans on the stone counter.",
            "Amy leans on the stone counter.",
            state,
        )
        self.assertEqual(result, [])

    def test_registered_fixture_is_exposed_separately_from_supports(self):
        state = make_reducer_state()
        messages = minimax.build_current_segment_persistent_prop_messages(
            "Subject One opens the door.",
            "Subject One opens the door.",
            state,
        )
        user_prompt = messages[-1]["content"]
        fixtures = user_prompt.split("CANONICAL FIXTURES\n", 1)[1].split(
            "\n\nReturn only props", 1
        )[0]
        supports = user_prompt.split("CANONICAL SUPPORTS\n", 1)[1].split(
            "\n\nCANONICAL FIXTURES", 1
        )[0]
        self.assertIn('"name":"Door"', fixtures)
        self.assertIn('"name":"Fixed object"', fixtures)
        self.assertNotIn('"name":"Door"', supports)


    def test_fixture_prompt_exposes_source_type_and_alias_rule(self):
        state = make_reducer_state()
        messages = minimax.build_current_segment_persistent_prop_messages(
            "Subject One opens the heavy metal door.",
            "Subject One opens the heavy metal door.",
            state,
        )
        self.assertIn('"name":"Door"', messages[-1]["content"])
        self.assertIn('"source_type":"unknown"', messages[-1]["content"])
        self.assertIn("descriptive aliases of those fixtures", messages[0]["content"])


    def test_unplaced_prop_candidate_is_ignored(self):
        state = make_reducer_state()
        result = minimax.parse_current_segment_persistent_prop_result(
            {
                "props": [{
                    "name": "cloth",
                    "kind": "tool",
                    "mobility": "movable",
                    "initial_location": None,
                    "initial_holder": None,
                    "support_name": None,
                    "contents": [],
                    "capabilities": {
                        "container": "unknown",
                        "consumable": "unknown",
                        "openable": "unknown",
                        "lockable": "unknown",
                    },
                    "reason": "used in this segment",
                    "evidence": "cloth",
                }]
            },
            "Subject One wipes a surface with a cloth.",
            "Subject One wipes a surface with a cloth.",
            state,
        )
        self.assertEqual(result, [])


    def test_extractor_retries_three_times_then_recovers_explicit_holder(self):
        state = make_reducer_state()
        candidate = {
            "name": "cloth",
            "kind": "tool",
            "mobility": "movable",
            "initial_location": None,
            "initial_holder": None,
            "support_name": None,
            "contents": [],
            "capabilities": {
                "container": "unknown",
                "consumable": "unknown",
                "openable": "unknown",
                "lockable": "unknown",
            },
            "reason": "used in this segment",
            "evidence": "Subject One wipes a surface with a cloth.",
        }
        request = mock.Mock(return_value={"props": [candidate]})
        result = minimax.extract_current_segment_persistent_props(
            "Subject One wipes a surface with a cloth.",
            "Subject One wipes a surface with a cloth.",
            state,
            llm_request=request,
        )
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["initial_holder"], "Subject One")

    def test_holder_recovery_fails_closed_when_multiple_subjects_are_in_sentence(self):
        state = make_reducer_state()
        candidate = {
            "name": "cloth",
            "kind": "tool",
            "mobility": "movable",
            "initial_location": None,
            "initial_holder": None,
            "support_name": None,
            "contents": [],
            "capabilities": {
                "container": "unknown",
                "consumable": "unknown",
                "openable": "unknown",
                "lockable": "unknown",
            },
            "reason": "used in this segment",
            "evidence": "Subject One and Subject Two wipe a surface with a cloth.",
        }
        request = mock.Mock(return_value={"props": [candidate]})
        with self.assertRaisesRegex(ValueError, "exactly one explicit initial location or holder"):
            minimax.extract_current_segment_persistent_props(
                "Subject One and Subject Two wipe a surface with a cloth.",
                "Subject One and Subject Two wipe a surface with a cloth.",
                state,
                llm_request=request,
            )
        self.assertEqual(request.call_count, 3)


    def test_redundant_location_is_dropped_when_holder_is_known(self):
        state = make_reducer_state()
        result = minimax.parse_current_segment_persistent_prop_result(
            {
                "props": [{
                    "name": "wooden mug",
                    "kind": "container",
                    "mobility": "movable",
                    "initial_location": "Area A",
                    "initial_holder": "Subject One",
                    "support_name": None,
                    "contents": [],
                    "capabilities": {
                        "container": True,
                        "consumable": "unknown",
                        "openable": "unknown",
                        "lockable": "unknown",
                    },
                    "reason": "held at segment start",
                    "evidence": "wooden mug",
                }]
            },
            "Subject One carries a wooden mug.",
            "Subject One carries a wooden mug.",
            state,
        )
        self.assertIsNone(result[0]["initial_location"])
        self.assertEqual(result[0]["initial_holder"], "Subject One")

    def test_registered_subject_id_holder_is_normalized_to_canonical_name(self):
        state = make_reducer_state()
        candidate = self._candidate("mug", "holds a mug between its fingers")
        candidate["initial_location"] = "location_a"
        candidate["initial_holder"] = "subject_1"
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Subject One holds a mug between its fingers.",
            "Subject One holds a mug between its fingers.",
            state,
        )
        self.assertEqual(result[0]["initial_holder"], "Subject One")

    def test_registered_location_id_is_normalized_to_canonical_name(self):
        state = make_reducer_state()
        candidate = self._candidate(
            "wooden tray",
            "wooden tray",
            mobility="movable",
            initial_location="location_a",
        )
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "A wooden tray rests in Area A.",
            "A wooden tray rests in Area A.",
            state,
        )
        self.assertEqual(result[0]["initial_location"], "Area A")

    def test_unregistered_or_ambiguous_holder_id_still_fails_closed(self):
        state = make_reducer_state()
        candidate = self._candidate("mug", "holds a mug between its fingers")
        candidate["initial_holder"] = "subject_99"
        with self.assertRaisesRegex(ValueError, "unregistered holder"):
            minimax.parse_current_segment_persistent_prop_result(
                {"props": [candidate]},
                "Subject One holds a mug between its fingers.",
                "Subject One holds a mug between its fingers.",
                state,
            )

        ambiguous = make_reducer_state()
        ambiguous["subjects"]["subject_2"]["name"] = "subject_1"
        candidate = self._candidate("mug", "holds a mug between its fingers")
        candidate["initial_holder"] = "subject_1"
        with self.assertRaisesRegex(ValueError, "unregistered holder"):
            minimax.parse_current_segment_persistent_prop_result(
                {"props": [candidate]},
                "Subject One holds a mug between its fingers.",
                "Subject One holds a mug between its fingers.",
                ambiguous,
            )


    def test_self_referential_initial_location_is_treated_as_ungrounded(self):
        state = make_reducer_state()
        result = minimax.parse_current_segment_persistent_prop_result(
            {
                "props": [{
                    "name": "heavy oak door",
                    "kind": "fixture",
                    "mobility": "unknown",
                    "initial_location": "heavy oak door",
                    "initial_holder": None,
                    "support_name": None,
                    "contents": [],
                    "capabilities": {
                        "container": "unknown",
                        "consumable": "unknown",
                        "openable": True,
                        "lockable": "unknown",
                    },
                    "reason": "used in this segment",
                    "evidence": "heavy oak door",
                }]
            },
            "Amy opens the heavy oak door.",
            "Amy opens the heavy oak door.",
            state,
        )
        self.assertEqual(result, [])


    def test_support_name_used_as_initial_location_is_normalized(self):
        state = make_reducer_state()
        result = minimax.parse_current_segment_persistent_prop_result(
            {
                "props": [{
                    "name": "damp cloth",
                    "kind": "tool",
                    "mobility": "movable",
                    "initial_location": "Support A",
                    "initial_holder": None,
                    "support_name": None,
                    "contents": [],
                    "capabilities": {
                        "container": "unknown",
                        "consumable": "unknown",
                        "openable": "unknown",
                        "lockable": "unknown",
                    },
                    "reason": "needed for pickup",
                    "evidence": "damp cloth",
                }]
            },
            "Subject One picks up a damp cloth from Support A.",
            "Subject One picks up a damp cloth from Support A.",
            state,
        )
        self.assertEqual(result[0]["initial_location"], "Area A")
        self.assertEqual(result[0]["support_name"], "Support A")

    def test_descriptive_support_alias_used_as_initial_location_is_normalized(self):
        state, _ = self._static_alias_test_state(
            "linen basket", "basket", role="support"
        )
        candidate = self._candidate(
            "damp cloth",
            "damp cloth pulled from the linen basket beside it",
            mobility="movable",
            initial_location="linen basket beside it",
        )
        result = minimax.parse_current_segment_persistent_prop_result(
            {"props": [candidate]},
            "Amy wipes the counter with a damp cloth pulled from the linen basket beside it.",
            "Amy wipes the counter with a damp cloth pulled from the linen basket beside it.",
            state,
        )
        self.assertEqual(result[0]["initial_location"], "Hall")
        self.assertEqual(result[0]["support_name"], "linen basket")


class CurrentSegmentSubjectEvidenceTests(unittest.TestCase):
    def test_balanced_outer_quotes_are_removed_from_exact_subject_evidence(self):
        result = minimax.parse_current_segment_subject_result(
            {"subjects": [{
                "name": "Elf_1",
                "physical_form": "humanoid",
                "gender": "unknown",
                "source_description": "elf perched on a stool",
                "evidence": '"the elf perched on a stool"',
            }]},
            "Amy serves the elf perched on a stool.",
            "",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Elf_1")


class RegisteredSubjectStoryStartEvidenceTests(unittest.TestCase):
    def test_authored_subject_in_beat_one_is_seeded_present_without_llm(self):
        state = new_world_state({
            "source_sha256": "opening-presence",
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
            "Amy wipes down the bar.",
        ]
        request = mock.Mock(side_effect=AssertionError("LLM call is unnecessary"))

        state = minimax.extract_registered_subject_story_start_presence(
            state, "Amy is a medieval barkeep.", beats,
            location_id=location_id, llm_request=request,
        )

        amy = state["subjects"]["subject_1"]
        self.assertEqual(amy["presence"], "present")
        self.assertEqual(amy["location_id"], location_id)
        self.assertEqual(
            amy["provenance"]["presence"]["authority"],
            "registered_subject_story_start_classifier",
        )
        request.assert_not_called()

    def test_all_beats_entry_candidates_are_filtered_but_later_nonentrants_remain(self):
        beats = [
            "Amy steps onto the wooden floor.",
            "A tall elf, a stout dwarf, and a mischievous goblin shuffle into the tavern.",
            "An old traveler sits quietly beside the hearth.",
        ]
        result = minimax.parse_initial_location_subjects(
            {"subjects": [
                {"name": "TallElf1", "initial_state": "inside the tavern"},
                {"name": "StoutDwarf1", "initial_state": "inside the tavern"},
                {"name": "MischievousGoblin1", "initial_state": "inside the tavern"},
                {"name": "OldTraveler1", "initial_state": "beside the hearth"},
            ]},
            beats=beats,
        )
        self.assertEqual([item["name"] for item in result], ["OldTraveler1"])

    def test_explicit_presence_uses_exact_numbered_beat_as_evidence(self):
        subject = {"name": "Amy"}
        beats = [
            "Amy stands behind her wooden bar holding a mug of ale.",
            "Amy opens the tavern door.",
        ]
        result = minimax.parse_registered_subject_story_start_result(
            {
                "classification": "present",
                "evidence_beat": 1,
                "initial_state": "behind the wooden bar holding a mug of ale",
            },
            subject,
            "Amy is a medieval barkeep.",
            beats,
        )
        self.assertEqual(result["evidence"], beats[0])
        self.assertEqual(result["classification"], "present")

    def test_unknown_presence_requires_zero_evidence_beat(self):
        result = minimax.parse_registered_subject_story_start_result(
            {
                "classification": "unknown",
                "evidence_beat": 0,
                "initial_state": "",
            },
            {"name": "Elf1"},
            "",
            ["Amy stands behind the bar."],
        )
        self.assertEqual(result["evidence"], "")
        with self.assertRaisesRegex(ValueError, "evidence_beat 0"):
            minimax.parse_registered_subject_story_start_result(
                {
                    "classification": "unknown",
                    "evidence_beat": 1,
                    "initial_state": "",
                },
                {"name": "Elf1"},
                "",
                ["Amy stands behind the bar."],
            )



class RegisteredSubjectStoryStartEvidenceTests(unittest.TestCase):
    def test_later_subject_presence_does_not_import_beat_action_pose(self):
        beats = [
            "Amy stands behind the tavern bar.",
            "A unicorn saunters to the middle of the tavern and steps onto a low chair.",
        ]
        result = minimax.parse_initial_location_subjects(
            {"subjects": [{
                "name": "Unicorn",
                "initial_state": "standing on a low chair in the middle of the tavern",
            }]},
            beats=beats,
        )
        self.assertEqual(
            result,
            [{
                "name": "Unicorn",
                "initial_state": (
                    "present in the story's starting location; exact position and "
                    "pose unknown"
                ),
            }],
        )

    def test_story_start_parser_uses_numbered_beat_as_exact_evidence(self):
        subject = {"name": "Amy"}
        beats = [
            "Amy stands behind her wooden bar holding a mug of ale.",
            "She opens the tavern door for arriving patrons.",
        ]

        result = minimax.parse_registered_subject_story_start_result(
            {
                "classification": "present",
                "evidence_beat": 1,
                "initial_state": "behind the wooden bar holding a mug of ale",
            },
            subject,
            "Amy is a medieval barkeep.",
            beats,
        )

        self.assertEqual(result["classification"], "present")
        self.assertEqual(result["evidence"], beats[0])
        self.assertEqual(
            result["initial_state"],
            "behind the wooden bar holding a mug of ale",
        )

    def test_unknown_story_start_requires_zero_evidence_beat(self):
        with self.assertRaisesRegex(ValueError, "evidence_beat 0"):
            minimax.parse_registered_subject_story_start_result(
                {
                    "classification": "unknown",
                    "evidence_beat": 1,
                    "initial_state": "",
                },
                {"name": "Amy"},
                "Amy is a medieval barkeep.",
                ["Amy stands behind the bar."],
            )


if __name__ == "__main__":
    unittest.main()
