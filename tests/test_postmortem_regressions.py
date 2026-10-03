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

    def test_director_rules_require_frame_zero_microbeat(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=3,
        )
        self.assertIn(
            "first timed micro-beat MUST be at 00:00.000",
            rules,
        )
        self.assertIn("00:00.000 is an inherited-frame anchor", rules)
        self.assertIn("Do not introduce a new subject", rules)
        self.assertIn("Start CURRENT BEAT immediately after that anchor", rules)

    def test_director_structure_rejects_nonzero_first_timestamp(self):
        errors = minimax._director_raw_scene_structure_errors(
            (
                "At 00:01.000, Amy stands at the counter.\n\n"
                "At 00:06.500, Amy turns toward the door.\n\n"
                "End continuity state: Amy stands at the counter facing the door."
            ),
            segment_seconds=8,
        )
        self.assertTrue(errors)
        self.assertIn("00:00.000", errors[0])

    def test_director_coherence_receives_previous_shot_end(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy opens the tavern door.",
            (
                "At 00:00.000, Amy opens the tavern door.\n\n"
                "At 00:06.500, Amy stands beside the open door.\n\n"
                "End continuity state: Amy stands beside the open door."
            ),
            previous_shot_end="Amy stands at the oak counter.",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("PREVIOUS SHOT END\nAmy stands at the oak counter.", prompt)
        self.assertIn("inherited 00:00.000 frame must be reachable", prompt)
        self.assertIn(
            "Do NOT require a participant introduced by CURRENT BEAT",
            prompt,
        )
        self.assertIn(
            "do not reject a new CURRENT BEAT participant merely because it enters after",
            prompt,
        )

    def test_dynamic_subject_definition_survives_plain_name_in_malformed_prose(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Creature1 (S2), continued from <Video 1>. "
            "Creature1 is a creature."
        )
        filtered, _description = minimax._filter_h3_subject_definitions(
            definitions,
            {1},
            (
                'At 00:00.000, "Amy stands beside Creature1 at the counter. '
                'At 00:06.500, "Creature1 takes a sip.'
            ),
        )
        self.assertIn("<Subject 2> is Creature1", filtered)

    def test_h3_no_dialogue_constraint_is_natural_language(self):
        constraint = minimax.format_h3_spoken_dialogue_constraint(
            "At 00:00.000, Amy wipes the counter."
        )
        self.assertEqual(
            constraint,
            "No intelligible spoken dialogue is heard in this segment.",
        )
        self.assertNotIn("SPOKEN DIALOGUE", constraint)

    def test_new_dynamic_subject_does_not_claim_previous_video(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Centaur1 (S2), continued from <Video 1>. "
            "Centaur1 is a centaur."
        )
        rendered = minimax._append_video_origin_to_h3_subject_definitions(
            definitions,
            previous_visible_subject_ids={1},
        )
        centaur_line = next(
            line for line in rendered.splitlines()
            if line.startswith("<Subject 2>")
        )
        self.assertNotIn("continued from <Video 1>", centaur_line)
        self.assertIn("Centaur1 is a centaur.", centaur_line)
        self.assertIn(2, minimax.parse_subject_registry(rendered))

        filtered, _ = minimax._filter_h3_subject_definitions(
            rendered,
            {1},
            "At 00:01.000, Centaur1 enters the room.",
        )
        self.assertIn("<Subject 2> is Centaur1", filtered)

    def test_previous_visible_dynamic_subject_has_one_video_origin(self):
        definitions = (
            "<Subject 2> is Dragon1 (S2), continued from <Video 1>. "
            "Dragon1 is a dragon. continued from <Video 1>."
        )
        rendered = minimax._append_video_origin_to_h3_subject_definitions(
            definitions,
            previous_visible_subject_ids={2},
        )
        self.assertEqual(
            rendered.lower().count("continued from <video 1>"),
            1,
        )

    def test_subject_resolver_canonicalizes_functional_end_state(self):
        raw = (
            "At 00:00.000, Amy stands at the counter.\n\n"
            "At 00:01.000, a centaur enters from the left.\n\n"
            "At 00:06.200, the centaur sits on a low stool.\n\n"
            "End continuity state: The tall centaur sits across from Amy."
        )

        def fake_llm(_messages, **_kwargs):
            return {
                "raw_scene": (
                    "At 00:00.000, Amy stands at the counter.\n\n"
                    "At 00:01.000, Centaur1 enters from the left.\n\n"
                    "At 00:06.200, Centaur1 sits on a low stool."
                ),
                "subject_names": ["Centaur1"],
            }

        resolved, names = minimax.resolve_director_raw_scene_subjects(
            raw,
            llm_request=fake_llm,
            segment_seconds=8,
        )
        self.assertEqual(names, ["Centaur1"])
        self.assertIn(
            "End continuity state: The tall Centaur1 sits across from Amy.",
            resolved,
        )

    def test_story_to_beats_preserves_explicit_enumerations(self):
        messages = minimax.build_story_to_beats_messages(
            "A barkeep serves magical patrons.",
            (
                "Amy watches the goblin, centaur, dragon, and unicorn "
                "settle around the room."
            ),
            1,
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("Preserve explicit source enumerations", prompt)
        self.assertIn("do not replace a stated list with", prompt)
        self.assertIn("instead of collapsing them into a", prompt)

        validator = minimax.build_beat_validation_messages(
            previous_final_beat="",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy watches the goblin, centaur, dragon, and unicorn settle.",
            next_beat_job="",
            candidate_beat="Amy watches each magical patron settle.",
        )
        self.assertIn(
            "candidate must preserve each listed identity",
            validator[-1]["content"],
        )

    def test_story_beat_repair_preserves_explicit_enumerations(self):
        messages = minimax.build_story_beat_repair_messages(
            "Amy watches the goblin, centaur, dragon, and unicorn settle.",
            6,
            6,
            "Amy watches each magical patron settle.",
            "The explicit participant list was collapsed.",
            ["Amy finishes counting coins."],
            "",
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "Preserve any explicit FULL STORY enumeration",
            prompt,
        )
        self.assertIn("do not replace the list with a", prompt)

    def test_empty_phase_two_continuity_skips_llm(self):
        calls = []

        def fake_llm(*args, **kwargs):
            calls.append((args, kwargs))
            return "should not be called"

        opening = minimax.request_continuity_opening_state(
            {"version": 5},
            {},
            llm_request=fake_llm,
        )
        self.assertEqual(opening, "")
        self.assertEqual(calls, [])

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
