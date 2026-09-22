import unittest

import minimax


def apply_effects(state, *effects):
    return minimax._apply_required_event_state_effects(
        state,
        [{"id": "E1", "state_effects": list(effects)}],
    )


class StateEffectCanonicalizationTests(unittest.TestCase):
    def test_all_supported_operations_translate_to_canonical_state(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"location": "hall", "stored_objects": ["pistol"]}
        state["environment"]["barriers"]["basement_door"] = {}
        result = apply_effects(
            state,
            {"op": "set_location", "entity": "amy", "value": "kitchen"},
            {"op": "set_item_state", "entity": "pistol", "owner": "AMY", "value": "equipped"},
            {"op": "set_barrier_state", "entity": "basement_door", "value": "locked"},
            {"op": "set_threat_state", "entity": "zombie_1", "value": "dead"},
            {"op": "set_object_state", "entity": "generator", "value": "destroyed"},
            {"op": "set_containment", "entity": "Amy", "container": "basement", "value": "contained"},
            {"op": "set_condition", "entity": "house", "value": "blood_soaked"},
            {"op": "set_clothing", "entity": "amy", "slot": "upper", "item": "black tank top", "damage": "damaged"},
        )
        self.assertEqual(result["characters"]["Amy"]["location"], "kitchen")
        self.assertEqual(result["characters"]["Amy"]["equipped_objects"], ["pistol"])
        self.assertEqual(result["characters"]["Amy"]["stored_objects"], [])
        self.assertEqual(result["environment"]["barriers"]["basement_door"]["status"], "locked")
        self.assertEqual(result["threats"]["zombie_1"]["status"], "dead")
        self.assertEqual(result["environment"]["objects"]["generator"]["status"], "destroyed")
        self.assertEqual(result["characters"]["Amy"]["contained_in"], "basement")
        self.assertFalse(result["characters"]["Amy"]["accessible"])
        self.assertEqual(result["environment"]["objects"]["house"]["condition"], "blood_soaked")
        self.assertEqual(result["characters"]["Amy"]["clothing"]["upper"], {"item": "black tank top", "damage": "damaged"})

    def test_item_moves_between_inventory_states(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"stored_objects": ["pistol"]}
        result = apply_effects(
            state,
            {"op": "set_item_state", "entity": "pistol", "owner": "Amy", "value": "held"},
            {"op": "set_item_state", "entity": "pistol", "owner": "Amy", "value": "equipped"},
            {"op": "set_item_state", "entity": "pistol", "owner": "Amy", "value": "dropped"},
        )
        record = result["characters"]["Amy"]
        self.assertEqual(record["held_objects"], [])
        self.assertEqual(record["equipped_objects"], [])
        self.assertEqual(record["stored_objects"], [])
        self.assertEqual(result["environment"]["objects"]["pistol"]["inventory_state"], "dropped")

    def test_case_insensitive_character_resolution_preserves_first_spelling(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"location": "kitchen"}
        result = apply_effects(state, {"op": "set_location", "entity": "aMy", "value": "hallway"})
        self.assertEqual(list(result["characters"]), ["Amy"])
        self.assertEqual(result["characters"]["Amy"]["location"], "hallway")

    def test_invalid_operation_and_values_are_rejected(self):
        invalid = [
            {"op": "invent_field", "entity": "Amy", "value": "x"},
            {"op": "set_barrier_state", "entity": "door", "value": "ajar"},
            {"op": "set_clothing", "entity": "Amy", "slot": "shoes", "item": "boots", "damage": "none"},
            {"op": "set_clothing", "entity": "Amy", "slot": "upper", "item": "shirt", "damage": "torn"},
        ]
        for effect in invalid:
            with self.subTest(effect=effect), self.assertRaises(ValueError):
                minimax._validate_state_effects([effect])

    def test_legacy_nested_effects_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "array"):
            minimax._validate_state_effects({"characters": {"Amy": {"inventory": ["pistol"]}}})

    def test_arc_parser_rejects_ungrounded_freeform_condition_value(self):
        arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Establish the ordinary breakfast setup.",
            "broad_progression": "Amy cooks breakfast.",
            "characters_introduced": ["Amy", "Will", "Amber"],
            "location": "kitchen",
            "required_end_state": "Amy has cooked breakfast.",
            "required_events": [{
                "id": "E1",
                "event": "Amy cooks breakfast for Will and Amber.",
                "beat_number": 1,
                "state_effects": [
                    {"op": "set_condition", "entity": "Will", "value": "eating"},
                ],
            }],
        }]}
        with self.assertRaisesRegex(ValueError, "not lexically grounded"):
            minimax.parse_beat_arc_plan(arc, 1)

    def test_arc_parser_accepts_grounded_freeform_condition_vocabulary(self):
        arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Establish the persistent aftermath.",
            "broad_progression": "The house becomes soaked in blood.",
            "characters_introduced": [],
            "location": "house",
            "required_end_state": "The house is soaked in blood.",
            "required_events": [{
                "id": "E1",
                "event": "The house becomes soaked in blood.",
                "beat_number": 1,
                "state_effects": [
                    {"op": "set_condition", "entity": "house", "value": "blood_soaked"},
                ],
            }],
        }]}
        parsed = minimax.parse_beat_arc_plan(arc, 1)
        self.assertEqual(
            parsed["phases"][0]["required_events"][0]["state_effects"][0]["value"],
            "blood_soaked",
        )

    def test_deep_canonical_state_remains_stable_after_sequential_operations(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Amy"] = {"clothing": {"upper": {"item": "shirt", "damage": "none"}}}
        result = apply_effects(
            state,
            {"op": "set_clothing", "entity": "Amy", "slot": "upper", "item": "coat", "damage": "none"},
            {"op": "set_clothing", "entity": "Amy", "slot": "lower", "item": "jeans", "damage": "destroyed"},
        )
        self.assertEqual(result["characters"]["Amy"]["clothing"]["upper"]["item"], "coat")
        self.assertEqual(result["characters"]["Amy"]["clothing"]["lower"]["damage"], "destroyed")
        self.assertEqual(result["story_progress"]["persistent_state_effects"]["characters.Amy.clothing.upper.item"], "coat")


if __name__ == "__main__":
    unittest.main()
