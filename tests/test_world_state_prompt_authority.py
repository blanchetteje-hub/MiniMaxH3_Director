import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import minimax
from world_state import (
    new_world_state,
    register_explicit_persistent_props,
    seed_canonical_static_location_state,
    seed_canonical_wardrobes,
    seed_current_segment_subject_identities,
    seed_story_start_presence,
)


def _opening_world_state():
    state = new_world_state({"subjects": {
        "1": {
            "subject_id": 1,
            "name": "Amy",
            "gender": "female",
            "picture_ids": [1],
            "canonical_description": "adult person",
        },
        "2": {
            "subject_id": 2,
            "name": "Goblin",
            "gender": "unknown",
            "picture_ids": [2],
        },
    }})
    state, location_id = seed_canonical_static_location_state(
        state,
        {"location": {"name": "Room"}, "anchors": [], "objects": []},
    )
    state = seed_story_start_presence(
        state,
        [
            {"name": "Amy", "initial_state": "standing"},
            {"name": "Goblin", "initial_state": "at the counter"},
        ],
        location_id=location_id,
    )
    state = seed_canonical_wardrobes(state, {
        "Amy": {
            "upper": [{"garment": "blue linen tunic", "condition": "unknown"}],
            "lower": [{"garment": "dark trousers", "condition": "unknown"}],
            "footwear": "N/A",
            "other": "N/A",
        },
    })
    state = register_explicit_persistent_props(state, [{
        "name": "mug",
        "kind": "container",
        "mobility": "movable",
        "needed_for_state": True,
        "reason": "It is held across segments.",
        "location_id": None,
        "holder_subject_id": "subject_2",
        "contents": [],
        "capabilities": {
            "container": True,
            "consumable": False,
            "openable": False,
            "lockable": False,
        },
    }])
    return state


class WorldStatePromptAuthorityTests(unittest.TestCase):
    def test_director_context_ignores_legacy_summary_and_prop_ledger(self):
        state = _opening_world_state()
        messages, _estimated, _recent = minimax.build_generation_messages(
            director_rules="unchanged rules",
            story="",
            beats=["Amy continues the scene."],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=2,
            total_segments=2,
            segment_length=8,
            total_length=16,
            continuity_summary="Legacy says Amy is in the wrong room wearing a red coat.",
            canonical_data="Amy is in the wrong room wearing a red coat.",
            subject_definitions="<Subject 1> is Amy (S1).",
            persistent_movable_prop_state={
                "legacy_mug": {"holder": "Amy", "location": "wrong room"}
            },
            world_state=state,
        )
        prompt = messages[-1]["content"]
        self.assertIn("Subject Amy: present; at Room", prompt)
        self.assertIn("Prop mug: held by Goblin", prompt)
        self.assertNotIn("wrong room", prompt)
        self.assertNotIn("red coat", prompt)
        self.assertNotIn("legacy_mug", prompt)

    def test_final_h3_uses_world_state_and_keeps_picture_and_video_refs(self):
        state = _opening_world_state()
        legacy = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "subject_id": 1,
                    "position": "legacy wrong location",
                    "wardrobe": {
                        "upper": "wrong red coat",
                        "lower": "wrong skirt",
                        "footwear": "wrong shoes",
                        "other": "N/A",
                    },
                }
            }
        }
        with TemporaryDirectory() as temp_dir:
            canonical_data = Path(temp_dir) / "canonical_data.txt"
            canonical_data.write_text(
                "Amy is wearing a wrong red coat.", encoding="utf-8"
            )
            with patch.object(minimax, "CANONICAL_DATA_FILE", str(canonical_data)):
                prompt = minimax.build_h3_prompt(
                    {
                        "detailed_description": (
                            "[Shot 1] <Video 1> is the tavern location reference. "
                            "At 00:01.000, Amy wipes the counter."
                        ),
                        "overall_soundscape": "soft room tone",
                        "non_diegetic_music": "quiet strings",
                    },
                    "<Subject 1> is Amy (S1), referenced in <Picture 1>.",
                    segment_number=2,
                    conditioning_mode="continuation",
                    continuity_state=legacy,
                    subject_state_ledger=legacy["subjects"],
                    character_canon={"characters": [{
                        "name": "Amy",
                        "age": "adult",
                        "gender": "female",
                        "clothing": "wrong red coat",
                    }]},
                    world_state=state,
                )
        self.assertIn("<Picture 1>", prompt)
        self.assertIn("<Video 1>", prompt)
        self.assertIn("blue linen tunic", prompt)
        self.assertIn("dark trousers", prompt)
        self.assertIn("Prop mug: held by Goblin", prompt)
        self.assertNotIn("legacy wrong location", prompt)
        self.assertNotIn("wrong red coat", prompt)
        self.assertNotIn("wrong skirt", prompt)
        self.assertEqual(prompt.count("blue linen tunic"), 1)
        self.assertIn("overall_soundscape: soft room tone", prompt)
        self.assertIn("non_diegetic_music: quiet strings", prompt)

    def test_unknown_world_state_facts_are_not_filled_from_legacy(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Traveler", "picture_ids": []},
        }})
        rendered = minimax.format_world_state_prompt_context(state)
        self.assertIn("No physical facts are established.", rendered)
        self.assertNotIn("Traveler: present", rendered)
        messages, _estimated, _recent = minimax.build_generation_messages(
            director_rules="rules",
            story="",
            beats=["The traveler waits."],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=1,
            segment_length=8,
            total_length=8,
            continuity_summary="Legacy says Traveler is at the gate.",
            world_state=state,
        )
        self.assertNotIn("at the gate", messages[-1]["content"])

    def test_stable_world_state_subject_ids_get_stable_prompt_identity_refs(self):
        state = new_world_state({"subjects": {
            "1": {"subject_id": 1, "name": "Authored", "picture_ids": [1]},
        }})
        state = seed_current_segment_subject_identities(state, [{
            "name": "Dynamic",
            "physical_form": "unknown",
            "source_description": "a silver-haired traveler",
        }])
        first = minimax.world_state_subject_definitions(
            "<Subject 1> is Authored (S1).", state
        )
        second = minimax.world_state_subject_definitions(
            "<Subject 1> is Authored (S1).", state
        )
        self.assertEqual(first, second)
        self.assertEqual(first.count("is Authored"), 1)
        self.assertIn("is Dynamic (S", first)
        self.assertIn("silver-haired traveler", first)


if __name__ == "__main__":
    unittest.main()
