import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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
    def test_canon_covered_dynamic_subject_skips_compatibility_wardrobe_extraction(self):
        canon = {
            "characters": [{
                "name": "Goblin1",
                "gender": "unknown",
                "clothing": "rough-spun shirt, brown trousers, leather shoes",
            }]
        }
        world_state = minimax.seed_character_canon_subject_identities(
            empty_world_state(),
            canon,
        )
        world_state = seed_canonical_wardrobes(
            world_state,
            minimax.world_state_wardrobes_from_character_canon(canon),
        )
        goblin_world_state_subject = next(
            subject for subject in world_state["subjects"].values()
            if subject["name"] == "Goblin1"
        )
        opening_wardrobe = copy.deepcopy(goblin_world_state_subject["wardrobe"])

        base_definitions = "<Subject 1> is Amy (S1)."
        continuity = minimax.continuity_state_for_registry(
            base_definitions,
            minimax.new_continuity_state(),
        )
        continuity, added = minimax.seed_initial_location_subjects(
            continuity,
            base_definitions,
            [{"name": "Goblin1", "initial_state": "leaning over the counter"}],
        )
        self.assertEqual(added, ["Goblin1"])
        extended_definitions = minimax.combine_subject_definitions(
            base_definitions,
            minimax.derive_additional_subject_definitions(
                base_definitions,
                continuity,
            ),
        )
        request = Mock(side_effect=AssertionError("canon wardrobe was re-extracted"))
        wardrobe_sink = {}
        updated = minimax.apply_story_subject_wardrobes(
            continuity,
            "A goblin leans over the counter.",
            extended_definitions,
            added,
            character_canon=canon,
            llm_request=request,
            world_state_wardrobe_sink=wardrobe_sink,
        )

        self.assertEqual(request.call_count, 0)
        self.assertEqual(wardrobe_sink, {})
        self.assertIn("Goblin1", updated["subjects"])
        self.assertEqual(
            updated["subjects"]["Goblin1"]["wardrobe"]["upper"],
            "rough-spun shirt",
        )
        self.assertEqual(
            updated["subjects"]["Goblin1"]["wardrobe"]["lower"],
            "brown trousers",
        )
        self.assertEqual(
            goblin_world_state_subject["wardrobe"], opening_wardrobe
        )

    def test_character_canon_identities_register_without_presence_and_receive_wardrobe(self):
        authored = minimax.authoritative_world_state_seed_from_subject_definitions(
            "<Subject 1> is Subject Alpha (S1)."
        )
        state = seed_predefined_subject_identities(empty_world_state(), authored)
        canon = {
            "characters": [
                {"name": "Subject Alpha", "gender": "female", "clothing": "linen shirt and trousers"},
                {"name": "Subject Beta", "gender": "male", "clothing": "canvas coat and boots"},
                {"name": "Subject Gamma", "gender": "unknown", "clothing": "N/A"},
            ]
        }
        state = minimax.seed_character_canon_subject_identities(state, canon)
        by_name = {subject["name"]: subject for subject in state["subjects"].values()}
        self.assertEqual(set(by_name), {"Subject Alpha", "Subject Beta", "Subject Gamma"})
        for subject in by_name.values():
            self.assertEqual(subject["presence"], UNKNOWN)
            self.assertEqual(subject["location_id"], UNKNOWN)
        self.assertEqual(
            by_name["Subject Beta"]["provenance"]["identity"]["authority"],
            "character_canon",
        )

        seeded = seed_canonical_wardrobes(
            state,
            minimax.world_state_wardrobes_from_character_canon(canon),
        )
        seeded_by_name = {subject["name"]: subject for subject in seeded["subjects"].values()}
        self.assertEqual(seeded_by_name["Subject Beta"]["wardrobe"]["upper"][0]["garment"], "canvas coat")
        self.assertEqual(seeded_by_name["Subject Gamma"]["wardrobe"]["upper"], "N/A")
        self.assertEqual(seeded_by_name["Subject Beta"]["presence"], UNKNOWN)

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

    def test_current_segment_prop_extractor_uses_names_and_cloth_id_persists(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Subject One", "gender": UNKNOWN, "picture_ids": []},
            "2": {"subject_id": 2, "name": "Subject Two", "gender": UNKNOWN, "picture_ids": []},
        }})
        state, location_id = seed_canonical_static_location_state(
            state,
            {
                "location": {"name": "Room"},
                "anchors": [],
                "objects": [{
                    "name": "counter",
                    "type": "wooden counter",
                    "world_state_role": "fixture_support",
                    "mobility": "fixed",
                }],
            },
        )
        state = minimax.seed_story_start_presence(
            state,
            [
                {"name": "Subject One", "initial_state": "near the counter"},
                {"name": "Subject Two", "initial_state": "near the counter"},
            ],
            location_id=location_id,
        )
        beat = "Subject One wipes the counter and hands the cleaning cloth to Subject Two."
        extracted_entry = {
            "name": "cleaning cloth",
            "kind": "tool",
            "mobility": "movable",
            "initial_location": None,
            "initial_holder": "Subject One",
            "support_name": None,
            "contents": [],
            "capabilities": {
                "container": "unknown",
                "consumable": "unknown",
                "openable": "unknown",
                "lockable": "unknown",
            },
            "reason": "The cloth is explicitly handed between the registered Subjects.",
            "evidence": beat,
        }
        captured = {}

        def fake_llm(messages, **_kwargs):
            captured["messages"] = messages
            return {"props": [copy.deepcopy(extracted_entry)]}

        extracted = minimax.extract_current_segment_persistent_props(
            beat, beat, state, llm_request=fake_llm
        )
        self.assertEqual(extracted[0]["initial_holder"], "Subject One")
        prompt_text = "\n".join(message["content"] for message in captured["messages"])
        self.assertIn('"name":"Subject One"', prompt_text)
        self.assertIn('"name":"Subject Two"', prompt_text)
        self.assertIn('"name":"Room"', prompt_text)
        self.assertIn('"name":"counter"', prompt_text)
        for entity_id in (
            *state["subjects"], *state["locations"], *state["props"],
        ):
            self.assertNotIn(entity_id, prompt_text)

        # Python alone resolves the returned registered name to its canonical ID.
        registered_state = minimax.register_extracted_persistent_props(state, extracted)
        cloth_id = next(
            prop_id for prop_id, prop in registered_state["props"].items()
            if prop["name"] == "cleaning cloth"
        )
        self.assertEqual(
            cloth_id,
            stable_world_state_id("prop", "tool|cleaning cloth", scope="subject_1"),
        )
        self.assertEqual(
            registered_state["props"][cloth_id]["placement"],
            {"kind": "held", "subject_id": "subject_1"},
        )

        handed_off = reduce_world_state(registered_state, [{
            "action_id": "cloth-handoff",
            "op": "handoff",
            "from_subject_id": "subject_1",
            "to_subject_id": "subject_2",
            "prop_id": cloth_id,
        }], segment_number=1)
        self.assertTrue(handed_off.committed)
        following_state = handed_off.world_state
        next_prompt = "\n".join(
            message["content"]
            for message in minimax.build_current_segment_persistent_prop_messages(
                "Subject Two places the cloth on the counter.",
                "Subject Two places the cloth on the counter.",
                following_state,
            )
        )
        self.assertIn('"name":"cleaning cloth"', next_prompt)
        self.assertIn('"holder":"Subject Two"', next_prompt)
        for entity_id in (
            *following_state["subjects"], *following_state["locations"],
            *following_state["props"],
        ):
            self.assertNotIn(entity_id, next_prompt)

        placed = reduce_world_state(following_state, [{
            "action_id": "cloth-place",
            "op": "place",
            "actor_subject_id": "subject_2",
            "prop_id": cloth_id,
            "location_id": location_id,
            "support_id": next(
                prop_id for prop_id, prop in following_state["props"].items()
                if prop["name"] == "counter"
            ),
        }], segment_number=2)
        self.assertTrue(placed.committed)
        self.assertEqual(
            placed.world_state["props"][cloth_id]["placement"]["kind"], "located"
        )

        # Supplying a Python ID where a registered holder name is required remains invalid.
        by_id = copy.deepcopy(extracted_entry)
        by_id["initial_holder"] = "subject_1"
        with self.assertRaisesRegex(ValueError, "unregistered holder"):
            minimax.parse_current_segment_persistent_prop_result(
                {"props": [by_id]}, beat, beat, state
            )

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

    def test_director_contract_uses_registered_names_and_resolves_them_before_reducer(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
            "2": {"subject_id": 2, "name": "Baker", "gender": "unknown", "picture_ids": []},
        }})
        state, location_id = seed_canonical_static_location_state(
            state, {"location": {"name": "Room"}, "anchors": [], "objects": []}
        )
        state = seed_story_start_presence(
            state, [{"name": "Amy", "initial_state": "standing"}], location_id=location_id
        )
        contract = build_director_state_action_contract(state)
        vocabulary = contract["vocabulary"]
        self.assertEqual(
            {item["name"] for item in vocabulary["subjects"]}, {"Amy", "Baker"}
        )
        self.assertEqual(vocabulary["locations"], [{"name": "Room"}])
        self.assertIn("exact registered entity names", contract["instruction"])

        def assert_no_id_fields(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertNotEqual(key, "id")
                    self.assertFalse(key.endswith("_id"), key)
                    assert_no_id_fields(nested)
            elif isinstance(value, list):
                for nested in value:
                    assert_no_id_fields(nested)

        assert_no_id_fields(vocabulary)
        schema = contract["response_format"]["json_schema"]["schema"]
        self.assertIn("raw_scene", schema["required"])
        self.assertIn("state_actions", schema["required"])
        action_schemas = schema["properties"]["state_actions"]["items"]["oneOf"]
        enter_schema = next(
            item for item in action_schemas
            if item["properties"]["op"]["const"] == "enter"
        )
        self.assertEqual(
            enter_schema["properties"]["subject_id"]["enum"], ["Amy", "Baker"]
        )
        self.assertEqual(
            enter_schema["properties"]["location_id"]["enum"], ["Room"]
        )

        response = {
            "raw_scene": "Baker enters the room.",
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
            "state_actions": [{
                "action_id": "baker-enters",
                "op": "enter",
                "subject_id": "Baker",
                "location_id": "Room",
            }],
        }
        result = parse_and_dry_run_director_state_actions(
            state,
            response,
            segment_number=1,
            name_resolution=contract["name_resolution"],
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state_actions"][0]["subject_id"], "subject_2")
        self.assertEqual(result["state_actions"][0]["location_id"], location_id)
        self.assertEqual(state["subjects"]["subject_2"]["presence"], "unknown")

    def test_director_name_resolution_rejects_unknown_and_out_of_vocabulary_names(self):
        state = make_reducer_state()
        contract = build_director_state_action_contract(
            state,
            current_segment_text="Subject One Support A",
        )
        response = {
            "raw_scene": "Subject One acts.",
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
            "state_actions": [{
                "action_id": "unknown-prop",
                "op": "pickup",
                "actor_subject_id": "Subject One",
                "prop_id": "Target vessel",
            }],
        }
        # Target vessel is in WorldState, but absent from this request's vocabulary.
        with self.assertRaisesRegex(ValueError, "unknown_registered_name"):
            parse_and_dry_run_director_state_actions(
                state,
                response,
                segment_number=1,
                name_resolution=contract["name_resolution"],
            )
        response["state_actions"][0]["prop_id"] = "Unregistered object"
        with self.assertRaisesRegex(ValueError, "unknown_registered_name"):
            parse_and_dry_run_director_state_actions(
                state,
                response,
                segment_number=1,
                name_resolution=contract["name_resolution"],
            )

    def test_director_name_resolution_rejects_duplicate_registered_names(self):
        state = make_reducer_state()
        duplicate = copy.deepcopy(state["props"]["prop_target"])
        duplicate["id"] = "prop_target_duplicate"
        state["props"][duplicate["id"]] = duplicate
        validate_world_state(state)
        contract = build_director_state_action_contract(
            state,
            current_segment_text="Subject One Target vessel",
        )
        self.assertEqual(
            contract["name_resolution"]["prop"]["Target vessel"],
            ["prop_target", "prop_target_duplicate"],
        )
        response = {
            "raw_scene": "Subject One reaches for the vessel.",
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
            "state_actions": [{
                "action_id": "ambiguous-pickup",
                "op": "pickup",
                "actor_subject_id": "Subject One",
                "prop_id": "Target vessel",
            }],
        }
        with self.assertRaisesRegex(ValueError, "ambiguous_registered_name"):
            parse_and_dry_run_director_state_actions(
                state,
                response,
                segment_number=1,
                name_resolution=contract["name_resolution"],
            )

    def test_director_vocabulary_renders_nested_placements_as_registered_names(self):
        state = make_reducer_state()
        state["props"]["prop_target"]["placement"] = {
            "kind": "held", "subject_id": "subject_2",
        }
        validate_world_state(state)
        contract = build_director_state_action_contract(
            state,
            current_segment_text="Subject One Movable object Support A Target vessel",
        )
        movable = next(
            prop for prop in contract["vocabulary"]["props"]
            if prop["name"] == "Movable object"
        )
        self.assertEqual(movable["placement"], {
            "kind": "located", "location": "Area A", "support": "Support A",
        })
        target = next(
            prop for prop in contract["vocabulary"]["props"]
            if prop["name"] == "Target vessel"
        )
        self.assertEqual(target["placement"], {
            "kind": "held", "subject": "Subject Two",
        })
        self.assertEqual(contract["vocabulary"]["supports"], [{
            "name": "Support A", "location": "Area A",
        }])
        self.assertIn(
            {"name": "Subject Two", "presence": "present", "location": "Area A"},
            contract["vocabulary"]["subjects"],
        )
        self.assertEqual(
            next(
                subject for subject in contract["vocabulary"]["subjects"]
                if subject["name"] == "Subject One"
            )["location"],
            "Area A",
        )
        response = {
                "raw_scene": "Subject Two places the vessel on Support A.",
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
            "state_actions": [{
                "action_id": "place-object",
                "op": "place",
                "actor_subject_id": "Subject Two",
                "prop_id": "Target vessel",
                "location_id": "Area A",
                "support_id": "Support A",
            }],
        }
        resolved = parse_and_dry_run_director_state_actions(
            state,
            response,
            segment_number=1,
            name_resolution=contract["name_resolution"],
        )
        self.assertTrue(resolved["accepted"])
        self.assertEqual(resolved["state_actions"][0], {
            "action_id": "place-object",
            "op": "place",
            "actor_subject_id": "subject_2",
                "prop_id": "prop_target",
            "location_id": "location_a",
            "support_id": "prop_support_a",
        })

        def assert_no_id_fields(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertNotEqual(key, "id")
                    self.assertFalse(key.endswith("_id"), key)
                    assert_no_id_fields(nested)
            elif isinstance(value, list):
                for nested in value:
                    assert_no_id_fields(nested)

        assert_no_id_fields(contract["vocabulary"])


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


class StoryStartRegressionTests(unittest.TestCase):
    def test_classifier_accepts_exact_evidence_with_newline(self):
        value = minimax.parse_registered_subject_story_start_result(
            {"classification": "present",
             "evidence": "Amy wipes a polished table.",
             "initial_state": "wiping table"},
            {"name": "Amy"}, "Amy wipes a\npolished table.", [])
        self.assertEqual(value["classification"], "present")

    def test_classifier_prompt_accepts_opening_action(self):
        messages = minimax.build_registered_subject_story_start_messages(
            {"name": "Amy", "identity": {}}, "Amy wipes a table.", ["Amy wipes a table."])
        self.assertIn("performing a starting action", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
