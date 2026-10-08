import unittest

import minimax


class LocationStatePostmortemTests(unittest.TestCase):
    def test_cli_defaults_disable_routine_refresh_and_use_fixed_story_profile(self):
        args = minimax.parse_args(["8", "6", "0.3"])
        self.assertEqual(args.refresh, 999)
        self.assertEqual(args.refresh, minimax.DEFAULT_REFRESH_INTERVAL)
        self.assertFalse(hasattr(args, "temp"))
        self.assertEqual(
            minimax.STORY_EXPANSION_LLM_SETTINGS["temperature"],
            minimax.DEFAULT_STORY_TEMPERATURE,
        )

    def test_explicit_refresh_interval_overrides_source_span_chapter_refreshes(self):
        arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 3,
                    "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
                },
                {
                    "phase_number": 2,
                    "beat_start": 4,
                    "beat_end": 6,
                    "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
                },
            ]
        }
        self.assertFalse(
            minimax.is_refresh_segment(
                4,
                refresh_interval=minimax.DEFAULT_REFRESH_INTERVAL,
                macro_arc=arc,
            )
        )
        self.assertTrue(
            minimax.is_refresh_segment(
                4,
                refresh_interval=None,
                macro_arc=arc,
            )
        )

    def test_story_expansion_requests_literal_film_ready_prose(self):
        messages = minimax.build_story_expansion_messages(
            "A barkeep serves magical creatures.",
            48,
            total_segments=6,
        )
        text = "\n".join(message["content"] for message in messages)
        self.assertIn("film-ready", text)
        self.assertIn("physically unambiguous", text)
        self.assertIn("Describe physical actions literally", text)
        self.assertIn("Avoid poetic or figurative wording", text)
        self.assertNotIn("You are a novelist", text)

    def test_director_requires_direct_dialogue_for_explicit_speech_beat(self):
        issue = minimax.director_required_dialogue_issue(
            "A goblin asks for a pint.",
            "At 00:03.000, Goblin1 orders a pint from Amy.",
        )
        self.assertIn("no <d>...</d> dialogue", issue)

        self.assertEqual(
            minimax.director_required_dialogue_issue(
                "A goblin asks for a pint.",
                "At 00:03.000, Goblin1 said <d>Give me a pint.</d>",
            ),
            "",
        )

    def test_director_prompt_forbids_spatial_teleport_and_indirect_speech(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE
        self.assertIn("show the actor moving there first", prompt)
        self.assertIn("do not use impossible reach, teleportation, or a hidden cut", prompt)
        self.assertIn("write a brief direct spoken line using <d>...</d>", prompt)
        self.assertIn("Do not add intelligible dialogue", prompt)

    def test_director_prompt_requires_subject_prop_and_position_provenance(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE
        self.assertIn("newly introduced foreground subject", prompt)
        self.assertIn("physically entering through a stated route/boundary", prompt)
        self.assertIn('Do not use "appears"', prompt)
        self.assertIn("Preserve prop identity and provenance", prompt)
        self.assertIn("must not silently become a different object", prompt)
        self.assertIn("source container and destination container distinct", prompt)
        self.assertIn("This applies to every established position", prompt)

    def test_coherence_validator_checks_subject_prop_and_position_provenance(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "A goblin arrives and Amy serves it.",
            (
                "At 00:00.000, Amy stands beside a barrel holding a bucket.\n"
                "At 00:02.000, a goblin appears in a chair.\n"
                "At 00:04.000, Amy holds a mug at the distant bar.\n"
                "At 00:06.000, Amy pours from the mug into a glass."
            ),
            previous_shot_end="Amy stands beside the barrel holding a bucket.",
        )
        text = "\n".join(message["content"] for message in messages)
        self.assertIn("first appearance needs visible provenance", text)
        self.assertIn("'appears'", text)
        self.assertIn("different established position", text)
        self.assertIn("prop cannot silently become another prop", text)
        self.assertIn("source and destination containers", text)

    def test_registered_subject_said_dialogue_gets_stable_speaker_id(self):
        definitions = (
            "<Subject 1> is Amy.\n"
            "<Subject 2> is Dragon1 (S2). Dragon1 is a dragon.\n"
            "<Subject 3> is Goblin1 (S3). Goblin1 is a goblin."
        )
        repaired = minimax.repair_h3_subject_identity(
            "At 00:03.000, Goblin1 said <d>Give me a pint.</d>",
            definitions,
        )
        self.assertIn(
            "Goblin1 (S3) said <d>Give me a pint.</d>",
            repaired,
        )
        self.assertEqual(
            minimax.format_h3_spoken_dialogue_constraint(repaired),
            "",
        )

        normalized_question = minimax.repair_h3_subject_identity(
            "At 00:03.000, Goblin1 asks <d>Can I have a pint?</d>",
            definitions,
        )
        self.assertIn(
            "Goblin1 (S3) said <d>Can I have a pint?</d>",
            normalized_question,
        )

    def test_dynamic_subject_registers_in_its_first_visible_segment(self):
        definitions = "<Subject 1> is Amy."
        state = minimax.continuity_state_for_registry(definitions)
        state, added = minimax.register_named_subject_hints(
            state,
            definitions,
            "At 00:02.000, Goblin1 enters and sits at the table.",
            ["Goblin1"],
            origin_segment=4,
        )
        self.assertEqual(added, ["Goblin1"])
        goblin = state["subjects"]["Goblin1"]
        self.assertEqual(goblin["origin_segment"], 4)
        self.assertEqual(goblin["subject_id"], 2)
        self.assertEqual(goblin["speaker_id"], "(S2)")


if __name__ == "__main__":
    unittest.main()
