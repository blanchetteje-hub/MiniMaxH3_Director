import unittest
from unittest.mock import Mock

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
    def test_continuity_updates_registered_subjects_only(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        candidate = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "subject_id": 1,
                    "position": "beside the window",
                },
                "Transient Figure": {
                    "name": "Transient Figure",
                    "position": "near the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Amy stands beside the window while "
            "a transient figure is visible near the doorway.",
            subjects,
            committed_state=committed,
        )

        self.assertIn("Amy", guarded["subjects"])
        self.assertEqual(
            guarded["subjects"]["Amy"]["position"],
            "beside the window",
        )
        self.assertNotIn("Transient Figure", guarded["subjects"])

    def test_anonymous_subjects_do_not_carry_state_between_scenes(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)

        first = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Unregistered Figure": {
                        "name": "Unregistered Figure",
                        "injuries": ["visible wound"],
                    },
                },
            },
            "detailed_description: [Shot 1] An unregistered figure is visible.",
            subjects,
            committed_state=committed,
        )
        second = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Unregistered Figure": {
                        "name": "Unregistered Figure",
                        "position": "near the door",
                    },
                },
            },
            "detailed_description: [Shot 1] A different unregistered figure is visible.",
            subjects,
            committed_state=first,
        )

        self.assertEqual(set(first["subjects"]), {"Amy"})
        self.assertEqual(set(second["subjects"]), {"Amy"})

    def test_zombie_is_not_created_as_a_durable_subject(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        candidate = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "subject_id": 1,
                    "position": "beside the window",
                },
                "Zombie": {
                    "name": "Zombie",
                    "injuries": ["decapitated"],
                    "position": "near the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Amy stands beside the window while "
            "a zombie is visible near the doorway.",
            subjects,
            committed_state=committed,
        )

        self.assertEqual(set(guarded["subjects"]), {"Amy"})
        self.assertNotIn("Zombie", guarded["subjects"])

    def test_explicitly_registered_named_subject_can_be_updated(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        candidate = {
            "subjects": {
                "Will": {
                    "name": "Will",
                    "subject_id": 2,
                    "position": "in the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Will stands in the doorway.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(
            guarded["subjects"]["Will"]["position"],
            "in the doorway",
        )

    def test_merge_boundary_discards_arbitrary_subject_fields(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        guarded = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "subject_id": 1,
                        "position": "beside the window",
                        "made_up_field": "must not persist",
                    },
                },
                "made_up_top_level": "must not persist",
            },
            "detailed_description: Amy stands beside the window.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(
            guarded["subjects"]["Amy"]["position"],
            "beside the window",
        )
        self.assertNotIn("made_up_field", guarded["subjects"]["Amy"])
        self.assertNotIn("made_up_top_level", guarded)

    def test_offscreen_registered_subject_reenters_with_same_identity(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Will"]["position"] = "in the basement"
        committed["subjects"]["Will"]["injuries"] = ["bruise"]

        projected = minimax._phase2_continuity_state_for_scene(
            committed,
            SUBJECTS,
            "detailed_description: [Shot 1] Amy closes and locks the basement door.",
        )
        self.assertNotIn("Will", projected["subjects"])
        self.assertIn("Will", committed["subjects"])

        later = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Will": {
                        "name": "Will",
                        "subject_id": 2,
                        "position": "at the basement doorway",
                    },
                },
            },
            "detailed_description: [Shot 1] Will stands at the basement doorway.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(later["subjects"]["Will"]["subject_id"], 2)
        self.assertEqual(later["subjects"]["Will"]["injuries"], ["bruise"])
        self.assertEqual(
            later["subjects"]["Will"]["position"],
            "at the basement doorway",
        )

    def test_phase_two_prunes_empty_and_unknown_values_without_mutating_state(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Amy"].update({
            "position": "by the doorway",
            "held_props": [],
            "injuries": [],
            "physical_condition": "N/A",
        })
        request = Mock(return_value="Amy is by the doorway.")

        minimax.request_continuity_opening_state(
            state,
            {},
            llm_request=request,
            subject_definitions=SUBJECTS,
            ending_scene="End continuity state: Amy stands by the doorway.",
        )

        user_prompt = request.call_args.args[0][1]["content"]
        self.assertIn('"position": "by the doorway"', user_prompt)
        self.assertNotIn("held_props", user_prompt)
        self.assertNotIn("injuries", user_prompt)
        self.assertNotIn("physical_condition", user_prompt)
        self.assertEqual(state["subjects"]["Amy"]["held_props"], [])
        self.assertEqual(state["subjects"]["Amy"]["physical_condition"], "N/A")

    def test_phase_two_keeps_false_and_zero_values(self):
        state = {
            "environment": {"location": "room"},
            "subjects": {
                "Amy": {
                    "position": "by the doorway",
                    "flag": False,
                    "count": 0,
                },
            },
        }
        request = Mock(return_value="Amy is by the doorway.")

        minimax.request_continuity_opening_state(
            state,
            {},
            llm_request=request,
            ending_scene="End continuity state: Amy stands by the doorway.",
        )

        user_prompt = request.call_args.args[0][1]["content"]
        self.assertIn('"flag": false', user_prompt)
        self.assertIn('"count": 0', user_prompt)

    def test_end_state_projection_does_not_delete_offscreen_registered_subjects(self):
        definitions = (
            "<Subject 1> is Alex, referenced in <Picture 1>.\n"
            "<Subject 2> is Blair, referenced in <Picture 2>.\n"
            "<Subject 3> is Casey, referenced in <Picture 3>."
        )
        state = minimax.continuity_state_for_registry(definitions)
        projected = minimax._phase2_continuity_state_for_scene(
            state,
            definitions,
            "Earlier: Alex, Blair, and Casey are visible.\n"
            "Alex closes a door behind Blair and Casey.\n"
            "End continuity state: Alex stands outside the closed door.",
        )

        self.assertEqual(set(state["subjects"]), {"Alex", "Blair", "Casey"})
        self.assertEqual(set(projected["subjects"]), {"Alex"})

    def test_held_prop_survives_phase_two_and_can_be_cleared_generically(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Amy"]["held_props"] = ["metal tool"]
        request = Mock(return_value="Amy stands by the doorway holding a metal tool.")

        minimax.request_continuity_opening_state(
            committed,
            {},
            llm_request=request,
            subject_definitions=SUBJECTS,
            ending_scene=(
                "End continuity state: Amy stands by the doorway holding a metal tool."
            ),
        )
        self.assertIn("metal tool", request.call_args.args[0][1]["content"])

        cleared = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "subject_id": 1,
                        "held_props": [],
                    },
                },
            },
            "detailed_description: Amy stands by the doorway.",
            SUBJECTS,
            committed_state=committed,
        )
        self.assertEqual(cleared["subjects"]["Amy"]["held_props"], [])

    def test_continuity_cannot_create_a_new_named_subject(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        guarded = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Mara": {
                        "name": "Mara",
                        "position": "at the table",
                    },
                },
            },
            "detailed_description: [Shot 1] Mara stands at the table.",
            subjects,
            committed_state=committed,
        )

        self.assertEqual(set(guarded["subjects"]), {"Amy"})

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
