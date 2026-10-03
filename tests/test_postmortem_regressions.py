import unittest

import minimax


class PostmortemRegressionTests(unittest.TestCase):
    def test_director_coherence_requires_end_state_to_match_final_timed_action(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy steps into the courtyard.",
            (
                "At 00:00.000, Amy stands at the counter.\n\n"
                "At 00:02.000, Amy opens the door.\n\n"
                "At 00:04.000, Amy steps through the doorway into the courtyard.\n\n"
                "End continuity state: Amy stands at the counter."
            ),
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("MUST describe the state produced by the final timed action", prompt)
        self.assertIn("explicitly compare", prompt)

    def test_subject_resolver_prefers_explicit_species_over_generic_creature(self):
        messages = minimax.build_director_raw_subject_resolution_messages(
            "At 00:01.000, a dragon shifts outside while a griffin watches Amy."
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("If RAW says dragon, use Dragon1", prompt)
        self.assertIn("if RAW says griffin, use Griffin1", prompt)
        self.assertIn("Use CreatureN only when the type is truly unknown", prompt)

    def test_subject_resolver_reuses_single_known_functional_species(self):
        raw = (
            "At 00:00.000, Griffin waits beside the counter.\n\n"
            "At 00:02.000, Griffin lifts its mug.\n\n"
            "At 00:04.000, Griffin settles beside Amy.\n\n"
            "End continuity state: Griffin remains beside Amy."
        )

        def fake_llm(_messages, **_kwargs):
            return {
                "raw_scene": (
                    "At 00:00.000, Griffin waits beside the counter.\n\n"
                    "At 00:02.000, Griffin lifts its mug.\n\n"
                    "At 00:04.000, Griffin settles beside Amy."
                ),
                "subject_names": ["Griffin"],
            }

        resolved, names = minimax.resolve_director_raw_scene_subjects(
            raw,
            subject_definitions=(
                "<Subject 4> is Griffin1 (S4), continued from <Video 1>."
            ),
            llm_request=fake_llm,
            segment_seconds=5,
        )
        self.assertIn("Griffin1 waits beside the counter", resolved)
        self.assertIn("Griffin1 settles beside Amy", resolved)
        self.assertEqual(names, [])

    def test_new_functional_subject_definition_keeps_semantic_role(self):
        state, added = minimax.register_named_subject_hints(
            minimax.new_continuity_state(),
            "",
            "At 00:01.000, Griffin1 lands beside the counter.",
            ["Griffin1"],
            origin_segment=3,
        )
        self.assertEqual(added, ["Griffin1"])
        definitions = minimax.derive_additional_subject_definitions("", state)
        self.assertEqual(len(definitions), 1)
        self.assertIn("Griffin1 is a griffin.", definitions[0])

    def test_beat_validator_treats_missing_ordinary_prop_as_unknown(self):
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy stands at the bar.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy pours water from a chalice.",
            next_beat_job="Amy serves the next guest.",
            candidate_beat="Amy pours water from a chalice.",
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "ordinary story/staging prop is NOT unavailable merely because CURRENT STATE",
            prompt,
        )
        self.assertIn("Missing state is unknown, not absent", prompt)

    def test_visible_process_does_not_require_invented_completion_endpoint(self):
        finite_messages = minimax.build_beat_finite_endpoint_messages(
            "Amy polishes a crystal goblet by the hearth.",
            "Amy polishes a crystal goblet by the hearth.",
        )
        finite_prompt = finite_messages[-1]["content"]
        self.assertIn(
            "satisfied by visibly performing an activity/process",
            finite_prompt,
        )
        self.assertIn("Do not invent a completion endpoint", finite_prompt)

        validator_messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy stands by the hearth.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy polishes a crystal goblet by the hearth.",
            next_beat_job="A guest arrives.",
            candidate_beat="Amy polishes a crystal goblet by the hearth.",
        )
        self.assertIn(
            "visible performance of an activity/process itself",
            validator_messages[-1]["content"],
        )

    def test_final_h3_prompt_contains_explicit_continuous_take_contract(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 1] At 00:00.000, a lantern glows on the counter. "
                    "At 00:04.000, the camera pans toward the door."
                ),
                "overall_soundscape": "soft room tone",
                "non_diegetic_music": "quiet strings",
            },
            "",
            segment_number=2,
            conditioning_mode="continuation",
        )
        self.assertIn(
            "Stage this segment as one continuous camera take with no cuts or cutaways",
            prompt,
        )
        self.assertIn("reframe only through continuous camera movement", prompt)


if __name__ == "__main__":
    unittest.main()
