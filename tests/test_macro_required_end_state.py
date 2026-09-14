import unittest

import minimax


class MacroRequiredEndStateTests(unittest.TestCase):
    def test_generation_prompt_rejects_optional_end_state_details(self):
        messages = minimax.build_beat_arc_plan_messages(
            "She defeats the intruders and releases her family.",
            5,
            beat_instructions="Beat 4 must show the family entering the safe room.",
        )
        prompt = messages[0]["content"]
        self.assertIn("only states explicitly required", prompt)
        self.assertIn("optional injuries", prompt)
        self.assertIn("logically necessary", prompt)
        self.assertIn("family entering the safe room", messages[1]["content"])

    def test_fidelity_prompt_checks_end_state_authorization(self):
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 5,
                "narrative_purpose": "Conflict",
                "broad_progression": "Defeat the intruders",
                "characters_introduced": [],
                "location": "House",
                "required_end_state": "The protagonist is injured and the furniture is destroyed.",
            }]
        }
        messages = minimax.build_beat_arc_fidelity_messages(
            "She defeats the intruders and releases her family.", arc
        )
        prompt = messages[1]["content"]
        self.assertIn("required_end_state clause", prompt)
        self.assertIn("not explicitly authorized", prompt)
        self.assertIn("environmental damage", prompt)

    def test_fidelity_parser_accepts_a_valid_authorized_arc_result(self):
        parsed = minimax.parse_beat_arc_fidelity({"valid": True, "issues": []})
        self.assertTrue(parsed["valid"])

    def test_fidelity_parser_preserves_rejection_for_optional_state(self):
        parsed = minimax.parse_beat_arc_fidelity({
            "valid": False,
            "issues": ["required_end_state invents an optional injury"],
        })
        self.assertFalse(parsed["valid"])
        self.assertIn("optional injury", parsed["issues"][0])


if __name__ == "__main__":
    unittest.main()
