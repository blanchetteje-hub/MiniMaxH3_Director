"""Focused regressions found while live-testing the simplified 14B prompts."""

import unittest

import minimax


SUBJECTS = "<Subject 1> is Maya, an adult woman referenced in <Picture 1>."


class SimplifiedPromptRegressionTests(unittest.TestCase):
    def test_latent_continuation_keeps_director_rules(self):
        rules = minimax.build_director_rules(
            12, 6, 2, SUBJECTS, 2,
            conditioning_mode="latent_continuation",
        )
        messages, _, _ = minimax.build_generation_messages(
            rules, "Story", ["One.", "Two."], {1}, [], 2, 2, 6, 12,
            subject_definitions=SUBJECTS,
            conditioning_mode="latent_continuation",
        )
        self.assertEqual(messages[0]["content"], rules)

    def test_compound_future_location_alias_is_detected(self):
        arc = {"phases": [
            {
                "phase_number": 1, "beat_start": 1, "beat_end": 1,
                "characters_introduced": ["Maya"], "location": "Street",
            },
            {
                "phase_number": 2, "beat_start": 2, "beat_end": 2,
                "characters_introduced": [],
                "location": "Collapsed bridge / Rescue boat",
            },
        ]}
        issues = minimax.validate_generated_beat_macro_introductions(
            ["Maya boards a rescue boat."], arc,
        )
        self.assertTrue(issues)

    def test_wardrobe_extraction_is_scoped_to_named_subject(self):
        description = (
            "Maya, wearing a red jacket and black jeans, kneels beside Leo. "
            "Leo sits upright in a yellow raincoat."
        )
        self.assertEqual(
            minimax._explicit_wardrobe_from_description(description, "Maya")["upper"],
            "red jacket",
        )
        self.assertEqual(
            minimax._explicit_wardrobe_from_description(description, "Leo"),
            {},
        )

    def test_empty_handed_clears_held_props(self):
        self.assertTrue(minimax._explicit_list_clear_is_grounded(
            "held_props",
            "By the final frame, Maya stands empty-handed.",
            "Maya",
        ))

    def test_na_explanation_normalizes_to_na(self):
        self.assertEqual(
            minimax.sanitize_previous_state_value("N/A (the action ended)"),
            "N/A",
        )

    def test_summary_prompt_uses_parser_labels(self):
        result = {
            "detailed_description": "[Shot 1] Maya stands in a room.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }
        system = minimax.build_summary_messages([(1, result)])[0]["content"]
        for label in minimax.PREVIOUS_STATE_FIELDS:
            self.assertIn(label, system)


if __name__ == "__main__":
    unittest.main()
