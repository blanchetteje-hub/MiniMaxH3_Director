import unittest

import minimax


def neutral_arc(event_text="Operator opens the primary barrier.", effects=None):
    event = {"id": "E1", "event": event_text, "beat_number": 1}
    if effects is not None:
        event["state_effects"] = effects
    return {"phases": [{
        "phase_number": 1,
        "beat_start": 1,
        "beat_end": 1,
        "narrative_purpose": "Resolve the authorized action.",
        "broad_progression": "The operator completes the required action.",
        "characters_introduced": ["Operator"],
        "location": "Location X",
        "required_end_state": "The primary barrier is open.",
        "required_events": [event],
    }]}


class MacroArcPipelineTests(unittest.TestCase):
    def test_arc_parser_rejects_invalid_canonical_entity_shape(self):
        arc = neutral_arc(effects={"threats": {"entity_group": True}})
        with self.assertRaises(ValueError):
            minimax.parse_beat_arc_plan(arc, 1)

    def test_arc_validator_prompt_owns_event_and_effect_semantics(self):
        prompt = "\\n".join(
            message["content"]
            for message in minimax.build_macro_arc_validation_messages(
                "The operator opens the primary barrier.", neutral_arc()
            )
        ).casefold()
        self.assertNotIn("required_end_state", prompt)
        self.assertIn("state_effects", prompt)
        self.assertIn("persistent facts directly established", prompt)
        self.assertNotIn("state preparation", prompt)
        self.assertNotIn("coverage inventory", prompt)

if __name__ == "__main__":
    unittest.main()
