import unittest

import minimax


class MacroArcContractTests(unittest.TestCase):
    def arc(self, event):
        return {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 2,
            "narrative_purpose": "Advance the story.",
            "broad_progression": "Complete the authorized progression.",
            "characters_introduced": ["Operator"],
            "location": "Location X",
            "required_end_state": "The primary barrier is open.",
            "required_events": [event],
        }]}

    def test_complete_arc_schema_preserves_state_effects(self):
        effects = {"environment": {"barriers": {"primary": {"status": "open"}}}}
        parsed = minimax.parse_beat_arc_plan(self.arc({
            "id": "E1",
            "event": "Operator opens the primary barrier.",
            "beat_number": 1,
            "state_effects": effects,
        }), 2)
        self.assertEqual(parsed["phases"][0]["required_events"][0]["state_effects"], effects)

    def test_python_rejects_malformed_effects_without_semantic_interpretation(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            minimax.parse_beat_arc_plan(self.arc({
                "id": "E1",
                "event": "Operator opens the primary barrier.",
                "beat_number": 1,
                "state_effects": {"threats": {"entity_group": True}},
            }), 2)

    def test_unified_validator_mentions_all_arc_semantics(self):
        text = " ".join(
            item["content"]
            for item in minimax.build_macro_arc_validation_messages(
                "The operator opens the primary barrier.",
                self.arc({"id": "E1", "event": "Operator opens the primary barrier.", "beat_number": 1}),
            )
        ).casefold()
        for term in ("source fidelity", "required_end_state", "state_effects", "dependencies"):
            self.assertIn(term, text)
        self.assertNotIn("separate state-preparation", text)

    def test_validator_contract_is_minimal(self):
        parsed = minimax.parse_macro_arc_validation_result({"valid": True, "issues": []})
        self.assertEqual(parsed, {"valid": True, "issues": []})
        with self.assertRaises(ValueError):
            minimax.parse_macro_arc_validation_result({"valid": False, "issues": []})


if __name__ == "__main__":
    unittest.main()
