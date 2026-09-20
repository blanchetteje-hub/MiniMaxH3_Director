"""Focused regressions found while live-testing the simplified 14B prompts."""

import unittest

import minimax


SUBJECTS = "<Subject 1> is Maya, an adult woman referenced in <Picture 1>."


class SimplifiedPromptRegressionTests(unittest.TestCase):
    def test_continuation_keeps_director_rules(self):
        rules = minimax.build_director_rules(
            12, 6, 2, SUBJECTS, 2,
            conditioning_mode="continuation",
        )
        messages, _, _ = minimax.build_generation_messages(
            rules, "Story", ["One.", "Two."], {1}, [], 2, 2, 6, 12,
            subject_definitions=SUBJECTS,
            conditioning_mode="continuation",
        )
        self.assertEqual(messages[0]["content"], rules)

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

    def test_story_opening_wardrobe_is_seeded_into_continuity(self):
        story = (
            "A realistic action film about a woman, Amy, protecting her two kids "
            "(Will and Amber) from a zombie apocalypse.\n"
            "Amy is at home on a normal day, wearing a tight, black tank top "
            "and denim jeans, cooking breakfast for her young kids."
        )
        subjects = "<Subject 1> is Amy, a woman referenced in <Picture 1>."

        state = minimax.seed_story_wardrobe(subjects, story)

        self.assertEqual(
            state["subjects"]["Amy"]["wardrobe"],
            {
                "upper": "black tank top",
                "lower": "denim jeans",
                "footwear": "N/A",
                "other": "N/A",
            },
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
