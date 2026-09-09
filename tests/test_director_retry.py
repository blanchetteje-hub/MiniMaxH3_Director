import unittest
from unittest import mock

import minimax


def segment_bundle():
    return {
        "segment": 1,
        "active_beat_id": 1,
        "current_duration": 6.0,
        "messages": [{"role": "user", "content": "Direct segment 1."}],
        "conditioning_mode": "initial",
        "opening_state_sha256": "opening-hash",
    }


def formatter_response(description):
    """A Request 2 H3 formatter reply with the three plain-text fields."""
    return {
        "detailed_description": description,
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
    }


class DirectorMicroPromptPipelineTests(unittest.TestCase):
    def test_gen_rules_are_near_top_of_director_prompt(self):
        messages = minimax.build_director_continuity_validation_messages(
            opening_state={},
            active_beat_text="",
            detailed_description="",
            segment_number=1,
            gen_rules="Never show on-screen text.",
        )
        combined = "\n".join(m["content"] for m in messages)

        self.assertIn("Never show on-screen text.", combined)
        # The exact ordering between system and user content may vary; just
        # verify the generation rule is present.

    def test_validation_prompt_checks_gen_rules_across_h3_fields(self):
        messages = minimax.build_director_continuity_validation_messages(
            opening_state={},
            active_beat_text="Amy opens the gate.",
            detailed_description="Amy opens the gate beneath a title card.",
            segment_number=1,
            gen_rules="Never show on-screen text and never use music.",
            overall_soundscape="The gate creaks.",
            non_diegetic_music="A string theme rises.",
        )

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn(
            "IMPORTANT GENERATION RULES\n"
            "Never show on-screen text and never use music.",
            combined,
        )
        self.assertIn("overall_soundscape: The gate creaks.", combined)
        self.assertIn("non_diegetic_music: A string theme rises.", combined)
        self.assertIn("generation_rule_violation", combined)

        parsed = minimax.parse_director_continuity_validation({
            "valid": False,
            "issues": [{
                "type": "generation_rule_violation",
                "problem": "The candidate uses music despite the custom rule.",
            }],
        })
        self.assertEqual(
            parsed["issues"][0]["type"],
            "generation_rule_violation",
        )

    def test_validation_prompt_checks_scope_creep_into_exact_next_beat(self):
        messages = minimax.build_director_continuity_validation_messages(
            opening_state={},
            active_beat_text="Amy opens the gate.",
            detailed_description="Amy opens the gate and enters the vault.",
            segment_number=1,
            next_beat_text="Amy enters the vault.",
        )

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("NEXT BEAT\nAmy enters the vault.", combined)
        self.assertIn("next_beat_scope_creep", combined)
        self.assertIn("materially performs, begins, reveals", combined)

        parsed = minimax.parse_director_continuity_validation({
            "valid": False,
            "issues": [{
                "type": "next_beat_scope_creep",
                "problem": "The candidate enters the vault one beat early.",
            }],
        })
        self.assertEqual(parsed["issues"][0]["type"], "next_beat_scope_creep")

    @mock.patch("minimax.validate_ministral_prompt")
    @mock.patch("minimax.format_ministral_prompt")
    @mock.patch("minimax.request_valid_ministral_prompt", create=True)
    @mock.patch("minimax.ask_llm")
    def test_segment_llm_runs_two_requests_without_legacy_seams(
        self,
        ask_llm,
        legacy_director,
        formatter,
        validator,
    ):
        raw_scene = (
            "Mark enters and reacts to the environment without performing "
            "the active beat's listed events."
        )
        formatted = formatter_response(
            "[Shot 1] Mark enters and reacts to the environment."
        )
        ask_llm.side_effect = [raw_scene, formatted]

        payload = minimax.request_segment_llm(
            segment_bundle(),
            ["Mark confronts the Duchess, Cook, piglets, and Cheshire Cat."],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        self.assertEqual(ask_llm.call_count, 2)
        legacy_director.assert_not_called()
        formatter.assert_not_called()
        validator.assert_not_called()

        purposes = [
            call.kwargs["history_metadata"]["purpose"]
            for call in ask_llm.call_args_list
        ]
        self.assertEqual(
            purposes,
            ["director_raw_scene", "director_h3_formatter"],
        )
        # The micro-prompt pipeline performs no Director correction attempts.
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["attempt"]
                for call in ask_llm.call_args_list
            ],
            [1, 1],
        )
        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            "[Shot 1] Mark enters and reacts to the environment.",
        )
        # Python owns beat completion metadata; no semantic gates ran.
        self.assertEqual(payload["llm_result"]["completed_beat_ids"], [1])
        self.assertEqual(payload["raw_scene"], raw_scene)
        self.assertEqual(payload["h3_mode"], "T2VA")

    def test_text_continuity_avoids_lm_studio_schema_rejection(self):
        llm_request = mock.Mock(side_effect=[
            {"subject": {"name": "Amy"}},
        ])

        minimax.request_text_continuity(
            "A full scene description.",
            {"environment": {"location": "bedroom"}},
            llm_request=llm_request,
            history_metadata={"run_id": "r1"},
            content_attempts=1,
            defer_opening=True,
        )

        text_call = llm_request.call_args_list[0]
        self.assertEqual(text_call.kwargs["response_format"], None)

    def test_segment_llm_passes_assigned_beat_id_as_completion(self):
        bundle = segment_bundle()
        bundle["active_beat_id"] = None

        with mock.patch(
            "minimax.ask_llm",
            side_effect=["A quiet scene.", formatter_response("[Shot 1] ...")],
        ), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(payload["llm_result"]["completed_beat_ids"], [])

    @mock.patch("minimax.ask_llm")
    def test_segment_llm_retries_director_request_2_on_missing_description(
        self, ask_llm):
        raw_scene = "Mark enters the room quietly."
        missing_description = {
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        formatted = formatter_response(
            "[Shot 1] Mark enters the room quietly."
        )
        ask_llm.side_effect = [raw_scene, missing_description, formatted]

        payload = minimax.request_segment_llm(
            segment_bundle(),
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        # request 1 plus two request 2 attempts (the first formatter
        # reply omitted the description field and was re-prompted).
        self.assertEqual(ask_llm.call_count, 3)
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["attempt"]
                for call in ask_llm.call_args_list
            ],
            [1, 2, 2],
        )
        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            "[Shot 1] Mark enters the room quietly.",
        )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Room tone.")

    @mock.patch("minimax.ask_llm")
    def test_segment_llm_uses_last_output_after_ten_formatter_failures(
        self, ask_llm):
        raw_scene = "Mark enters the room quietly."
        missing_description = {
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        ask_llm.side_effect = [raw_scene] + [missing_description] * 10

        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(),
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        # No fatal error; the tenth (final) attempt's raw output is salvaged,
        # falling back to the raw scene for the missing description field.

        self.assertEqual(ask_llm.call_count, 11)
        self.assertEqual(payload["llm_result"]["detailed_description"], raw_scene)
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Room tone.")
        self.assertEqual(payload["llm_result"]["non_diegetic_music"], "N/A")
        self.assertEqual(payload["llm_result"]["completed_beat_ids"], [1])

    @mock.patch("minimax.ask_llm")
    def test_segment_llm_salvages_last_free_text_after_ten_formatter_failures(
        self, ask_llm):
        raw_scene = "Mark enters the room quietly."
        # The tenth and final attempt returns free-form text with no labeled
        #  fields; that text becomes the preserved description field.
        last_text = (
            "[Shot 1] Mark enters the room quietly; the lighting dims slowly."
        )
        ask_llm.side_effect = [raw_scene] + ["", last_text] * 5

        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(),
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(ask_llm.call_count, 11)
        self.assertEqual(payload["llm_result"]["detailed_description"], last_text)
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "N/A")


if __name__ == "__main__":
    unittest.main()
