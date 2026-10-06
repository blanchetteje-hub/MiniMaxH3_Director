import copy
import tempfile
import unittest
from pathlib import Path

import minimax
from world_state import UNKNOWN, empty_world_state, new_world_state, validate_world_state


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

        subject["wardrobe"]["upper"] = "N/A"
        with self.assertRaisesRegex(ValueError, "requires clothing"):
            validate_world_state(state)
        subject["wardrobe"]["upper"] = "absent"
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


if __name__ == "__main__":
    unittest.main()
