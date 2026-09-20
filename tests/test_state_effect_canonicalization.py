import unittest

import minimax


def apply_effects(state, *effects):
    return minimax._apply_required_event_state_effects(
        state,
        [
            {"id": f"E{index}", "state_effects": effect}
            for index, effect in enumerate(effects, start=1)
        ],
    )


class StateEffectCanonicalizationTests(unittest.TestCase):
    def test_lowercase_amy_updates_existing_canonical_character(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"location": "kitchen"}

        result = apply_effects(
            state,
            {"characters": {"amy": {"location": "hallway"}}},
        )

        self.assertEqual(list(result["characters"]), ["Amy"])
        self.assertEqual(result["characters"]["Amy"]["location"], "hallway")

    def test_lowercase_will_updates_existing_canonical_character(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Will"] = {"status": "alert"}

        result = apply_effects(
            state,
            {"characters": {"will": {"status": "injured"}}},
        )

        self.assertEqual(list(result["characters"]), ["Will"])
        self.assertEqual(result["characters"]["Will"]["status"], "injured")

    def test_arbitrary_capitalization_produces_one_character_record(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"location": "kitchen"}

        result = apply_effects(
            state,
            {
                "characters": {
                    "AMY": {"location": "hallway"},
                    "aMy": {"held_objects": ["key"]},
                }
            },
        )

        self.assertEqual(
            [character.casefold() for character in result["characters"]],
            ["amy"],
        )
        self.assertEqual(result["characters"]["Amy"]["location"], "hallway")
        self.assertEqual(result["characters"]["Amy"]["held_objects"], ["key"])

        normalized = minimax.normalize_beat_canonical_state({
            "characters": {
                "Amy": {"location": "kitchen"},
                "aMy": {"held_objects": ["key"]},
            }
        })
        self.assertEqual(list(normalized["characters"]), ["Amy"])
        self.assertEqual(normalized["characters"]["Amy"]["location"], "kitchen")
        self.assertEqual(normalized["characters"]["Amy"]["held_objects"], ["key"])

    def test_nested_environment_threats_namespace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "nest canonical state root"):
            minimax._validate_state_effects(
                {"environment": {"threats": {"zombies": {}}}}
            )
        with self.assertRaisesRegex(ValueError, "nest canonical state root"):
            minimax._validate_state_effects(
                {"environment.threats.zombies": {}}
            )

    def test_top_level_threats_namespace_remains_valid(self):
        effects = {"threats": {"zombies": {"status": "active"}}}

        minimax._validate_state_effects(effects)
        self.assertEqual(minimax._state_effects_patch(effects), effects)

    def test_multiple_well_formed_effects_deep_merge_normally(self):
        state = minimax.new_beat_canonical_state()

        result = apply_effects(
            state,
            {"environment": {"objects": {"pan": {"status": "hot"}}}},
            {"environment": {"objects": {"knife": {"status": "ready"}}}},
            {"characters": {"Amy": {"held_objects": ["key"]}}},
        )

        self.assertEqual(
            result["environment"]["objects"],
            {
                "pan": {"status": "hot"},
                "knife": {"status": "ready"},
            },
        )
        self.assertEqual(result["characters"]["Amy"]["held_objects"], ["key"])

    def test_existing_effect_application_behavior_is_unchanged(self):
        state = minimax.new_beat_canonical_state()

        result = apply_effects(
            state,
            {"environment": {"barriers": {"primary": {"status": "open"}}}},
        )

        self.assertEqual(
            result["environment"]["barriers"]["primary"]["status"],
            "open",
        )
        self.assertEqual(
            result["story_progress"]["persistent_state_effects"]
            ["environment.barriers.primary.status"],
            "open",
        )


if __name__ == "__main__":
    unittest.main()
