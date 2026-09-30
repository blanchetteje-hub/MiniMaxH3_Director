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


    def test_beat_validator_rejects_aftermath_only_finite_action(self):
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="None",
            current_state={},
            beat_job="Amy is cooking breakfast for her kids.",
            next_beat_job="A zombie attacks.",
            candidate_beat="Amy is in the kitchen having finished cooking breakfast.",
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn('"having finished X"', prompt)
        self.assertIn("must show that activity occurring in THIS beat", prompt)

    def test_director_rules_require_visible_action_not_static_aftermath(self):
        rules = minimax.build_director_rules(
            8, 8, 1, SUBJECTS, 1,
            conditioning_mode="initial",
        )
        self.assertIn(
            "Complete every action, object interaction, participant role, and visible result",
            rules,
        )
        self.assertIn(
            "Preserve concrete assigned actions and interactions",
            rules,
        )
        self.assertIn(
            "You are the creative director",
            rules,
        )


if __name__ == "__main__":
    unittest.main()
