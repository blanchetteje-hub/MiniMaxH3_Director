import unittest

import minimax


SUBJECTS = (
    "<Subject 1> is Amy, referenced in <Picture 1>.\n"
    "<Subject 2> is Will, referenced in <Picture 2>."
)


def _wardrobe(**overrides):
    values = {field: "N/A" for field in minimax._WARDROBE_FIELDS}
    values.update(overrides)
    return values


class RequestedPromptRegressionTests(unittest.TestCase):
    def test_dialogue_addressees_are_not_visual_subjects(self):
        description = (
            'Amy calls out to Will and Amber, "Breakfast is ready!"'
        )
        self.assertEqual(
            minimax._subject_ids_referenced_by_description(description, SUBJECTS),
            {1},
        )

    def test_dialogue_only_name_is_not_promoted_by_named_subject_hints(self):
        state, added = minimax.register_named_subject_hints(
            minimax.continuity_state_for_registry(
                "<Subject 1> is Amy, referenced in <Picture 1>."
            ),
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            'Amy calls out "Will! Amber! Breakfast is ready!"',
            ["Will", "Amber"],
            origin_segment=1,
        )
        self.assertEqual(added, [])
        self.assertNotIn("Will", state["subjects"])
        self.assertNotIn("Amber", state["subjects"])

    def test_anonymous_zombie_cannot_take_registered_wills_identity(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Will"]["position"] = "in the basement"
        candidate = {
            "subjects": {
                "Will": {
                    "subject_id": 2,
                    "name": "Will",
                    "position": "at the top of the stairs",
                },
            },
        }
        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] A zombie crashes through the kitchen window.\n\n"
            "overall_soundscape: glass breaking",
            SUBJECTS,
            committed_state=committed,
        )
        self.assertEqual(
            guarded["subjects"]["Will"]["position"],
            "in the basement",
        )

    def test_explicit_visual_will_can_resolve(self):
        self.assertEqual(
            minimax._subject_ids_referenced_by_description(
                "<Subject 2> Will stands in the doorway.",
                SUBJECTS,
            ),
            {2},
        )

    def test_wardrobe_reconciliation_preserves_adjacent_choreography(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Amy"]["wardrobe"] = _wardrobe(
            upper="black tank top",
            lower="denim jeans",
        )
        cases = (
            (
                "Amy stands wearing a black tank top and denim jeans, her katana "
                "raised as the camera pans right across the living room.",
                "her katana raised as the camera pans right across the living room.",
            ),
            (
                "Amy prepares breakfast wearing a tight black tank top and denim "
                "jeans, as the camera pans across the scene.",
                "as the camera pans across the scene.",
            ),
            (
                "Amy wears a black tank top and denim jeans while holding a pistol.",
                "while holding a pistol.",
            ),
        )
        for source, preserved in cases:
            with self.subTest(source=source):
                result = minimax.reconcile_h3_wardrobe_with_canonical_state(
                    source,
                    SUBJECTS,
                    state,
                )
                self.assertIn("black tank top and denim jeans", result)
                self.assertIn(preserved, result)

    def test_quoted_speech_uses_actor_not_addressee(self):
        formatted = minimax.format_mistral_prompt(
            {
                "detailed_description": (
                    'Amy calls out to Will and Amber, "Come on up, kids. It\'s safe now."'
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            {"subject_definitions": SUBJECTS},
        )
        description = formatted["detailed_description"]
        self.assertIn(
            "Amy (S1) calls out to Will and Amber: "
            "<d>[English] Come on up, kids. It's safe now.</d>",
            description,
        )
        self.assertNotIn("<Subject 2> Will", description)

    def test_spoken_dialogue_does_not_emit_none_constraint(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    'Amy calls out to Will, "Come on up!"'
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=1,
        )
        self.assertNotIn("SPOKEN DIALOGUE: None", prompt)

    def test_silent_scene_keeps_none_constraint(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "Amy waits silently.",
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=1,
        )
        self.assertIn("SPOKEN DIALOGUE: None", prompt)

    def test_continuation_style_prefix_is_unique_and_timed_action_survives(self):
        for description in (
            "[Shot 1] Live-action, cinematic. At 00:00.000 seconds, Amy moves.",
            "[Shot 1] Live-action, cinematic, Amy moves.",
            "[Shot 1] Live-action, cinematic. Live-action, cinematic. Amy moves.",
        ):
            with self.subTest(description=description):
                prompt = minimax.build_h3_prompt(
                    {
                        "detailed_description": description,
                        "overall_soundscape": "room tone",
                        "non_diegetic_music": "N/A",
                    },
                    SUBJECTS,
                    segment_number=2,
                    conditioning_mode="continuation",
                )
                rendered = prompt.split("detailed_description: ", 1)[1].split(
                    "\n\noverall_soundscape:",
                    1,
                )[0]
                self.assertEqual(rendered.count("Live-action, cinematic"), 1)
                self.assertIn("Amy moves", rendered)
                if "00:00.000" in description:
                    self.assertIn("At 00:00.000 seconds, Amy moves.", rendered)


if __name__ == "__main__":
    unittest.main()
