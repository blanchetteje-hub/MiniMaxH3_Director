import unittest

import minimax


class LocationStatePostmortemTests(unittest.TestCase):
    def test_cli_defaults_disable_routine_refresh_and_story_expansion_uses_standard_profile(self):
        args = minimax.parse_args(["8", "6", "0.3"])
        self.assertEqual(args.refresh, 999)
        self.assertEqual(args.refresh, minimax.DEFAULT_REFRESH_INTERVAL)
        self.assertFalse(hasattr(args, "temp"))
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["story_expansion"],
            minimax.SMART_CREATIVE_LLM_SETTINGS,
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
        text = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn("film-ready", text)
        self.assertIn("physically unambiguous", text)
        self.assertIn("Describe physical actions literally", text)
        self.assertIn(
            "Avoid poetic or figurative wording when it could change how an action or object is visualized.",
            text,
        )
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

    def test_spatial_and_dialogue_rules_remain_in_their_existing_validators(self):
        physical = minimax.build_director_raw_scene_physical_messages(
            "Amy crosses the room.",
            "At 00:00.000, Amy crosses the room.",
        )
        text = "\n".join(message["content"] for message in physical)
        self.assertIn("subject movement", text)
        self.assertIn("CURRENT BEAT", text)
        self.assertIn("STATIC SETTING AUTHORITY", text)
        issue = minimax.director_required_dialogue_issue(
            "Amy asks for help.",
            "At 00:00.000, Amy looks toward Will.",
        )
        self.assertIn("no <d>...</d> dialogue", issue)

    def test_retired_monolithic_director_prompt_is_not_still_exposed(self):
        self.assertFalse(hasattr(minimax, "DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE"))
        self.assertFalse(hasattr(minimax, "DIRECTOR_RAW_SCENE_RESPONSE_FORMAT"))
        self.assertEqual(minimax.build_director_rules(8, 8, 1, "", 1), "")

    def test_coherence_compatibility_builder_uses_physical_prompt_contract(self):
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
        self.assertIn("subject movement", text)
        self.assertIn("CURRENT BEAT", text)
        self.assertIn("STATIC SETTING AUTHORITY", text)
        self.assertIn("RAW SCENE", text)

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
