import unittest
import json
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
    """A Request 2 H3 formatter reply with the required response fields."""
    return {
        "subject_genders": {},
        "detailed_description": description,
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
    }


class DirectorMicroPromptPipelineTests(unittest.TestCase):
    def test_h3_formatter_parses_subject_genders(self):
        parsed = minimax.parse_h3_formatter_result(
            "subject_genders: {\"Werewolf\": \"unknown\", "
            "\"Captain\": \"male\"}\n\n"
            "detailed_description: [Shot 1] Captain enters.\n\n"
            "overall_soundscape: Footsteps.\n\n"
            "non_diegetic_music: N/A"
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Werewolf": "unknown", "Captain": "male"},
        )

    def test_subject_gender_aliases_collapse_to_one_canonical_name(self):
        parsed = minimax.parse_h3_formatter_result(
            {
                "subject_genders": {
                    "<Subject 1>": "female",
                    "<Subject 2>": "male",
                    "<Subject 3>": "male",
                    "Jill": "female",
                    "Ben": "male",
                    "Frank": "male",
                },
                "detailed_description": "[Shot 1] Jill, Ben, and Frank enter.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            subject_definitions=(
                "<Subject 1> is Jill, a woman referenced in <Picture 1>.\n"
                "<Subject 2> is Ben, a man referenced in <Picture 2>.\n"
                "<Subject 3> is Frank, a man referenced in <Picture 3>."
            ),
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Jill": "female", "Ben": "male", "Frank": "male"},
        )

    def test_h3_formatter_parses_json_text_response(self):
        parsed = minimax.parse_h3_formatter_result(
            json.dumps({
                "subject_genders": {"Werewolf": "unknown"},
                "detailed_description": "[Shot 1] Werewolf enters.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            })
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["subject_genders"], {"Werewolf": "unknown"})

    @mock.patch("minimax.ask_llm")
    def test_request_2_removes_non_speaking_subject_ids_before_handoff(
        self, ask_llm
    ):
        bundle = segment_bundle()
        bundle["subject_definitions"] = (
            "<Subject 1> is Alice, referenced in <Picture 1>."
        )
        ask_llm.side_effect = [
            "Alice walks over to the window.",
            formatter_response(
                "[Shot 1] Alice (S1) walked over to the window."
            ),
        ]

        payload = minimax.request_segment_llm(
            bundle,
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        description = payload["llm_result"]["detailed_description"]
        self.assertIn("Alice walked over to the window.", description)
        self.assertNotIn("Alice (S1)", description)

        speaking = minimax.parse_h3_formatter_result(
            formatter_response("[Shot 1] Alice (S1) says: <d>[English] Hi.</d>"),
            subject_definitions=bundle["subject_definitions"],
        )
        self.assertIn("Alice (S1) says:", speaking["detailed_description"])

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_h3_response_format_repairs_malformed_json(self, post, _history):
        malformed = mock.Mock()
        malformed.status_code = 200
        malformed.raise_for_status.return_value = None
        malformed.json.return_value = {
            "choices": [{
                "message": {
                    "content": (
                        '{"subject_genders": {}, '
                        '"detailed_description": "[Shot 1] Amy enters.", '
                        '"overall_soundscape": "Footsteps.", '
                        '"non_diegetic_music": "N/A"'
                    )
                }
            }]
        }
        repaired = mock.Mock()
        repaired.status_code = 200
        repaired.raise_for_status.return_value = None
        repaired.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "subject_genders": {"Amy": "female"},
                        "detailed_description": "[Shot 1] Amy enters.",
                        "overall_soundscape": "Footsteps.",
                        "non_diegetic_music": "N/A",
                    })
                }
            }]
        }
        post.side_effect = [malformed, repaired]

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            retry_delay=0,
            response_format=minimax.H3_FORMATTER_RESPONSE_FORMAT,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertEqual(result["subject_genders"], {"Amy": "female"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["response_format"],
            minimax.H3_FORMATTER_RESPONSE_FORMAT,
        )
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])

    def test_h3_formatter_parses_markdown_labels(self):
        parsed = minimax.parse_h3_formatter_result(
            "### subject_genders: {}\n\n"
            "### Detailed Description: [Shot 1] Werewolf enters.\n\n"
            "### Overall Soundscape: Footsteps.\n\n"
            "### Non-Diegetic Music: N/A"
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")

    def test_append_h3_description_has_one_opener_and_no_leading_camera_move(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 2] Live-action, cinematic, The camera pushes in "
                    "toward Mark as Mark opens the door. At 00:02.000, the "
                    "camera pans right as Jill enters."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Mark, referenced in <Picture 1>.",
            segment_number=2,
            conditioning_mode="continuation",
        )

        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:",
            1,
        )[0]
        self.assertTrue(
            description.startswith(
                "[Shot 1] Live-action, cinematic, continues from <Video 1>."
                " Mark opens the door."
            )
        )
        self.assertEqual(description.count("Live-action, cinematic"), 1)
        self.assertNotIn("camera pushes in", description.lower())
        self.assertIn("camera pans right", description.lower())

    def test_formatter_metadata_never_reaches_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "**subject_genders:**\n"
                    "{\n"
                    '  "Amy": "female"\n'
                    "}\n\n"
                    "[Shot 1] Amy walks."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "reference_alignment": (
                    'subject_genders: {"Amy": "female"}\n'
                    "Reference Image 1 establishes Amy's identity."
                ),
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("subject_genders", prompt)
        self.assertNotIn('{"Amy": "female"}', prompt)
        self.assertIn("[Shot 1] Amy walks.", prompt)
        self.assertIn("Reference Image 1 establishes Amy's identity.", prompt)

    def test_mistral_asterisks_never_reach_final_h3_prompt(self):
        formatted = minimax.format_mistral_prompt(
            {
                "detailed_description": "*[Shot 1]* **Amy** walks.",
                "overall_soundscape": "*Footsteps* echo.",
                "non_diegetic_music": "**N/A**",
                "completed_beat_ids": [1],
            },
            {
                "segment_number": 1,
                "segment_duration": 6.0,
                "completed_beat_ids": [],
            },
        )
        prompt = minimax.build_h3_prompt(
            formatted,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("*", prompt)

    def test_mistral_asterisks_in_continuity_never_reach_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Amy waits.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            previous_state="*Amy remains by the door.*",
            segment_number=2,
            conditioning_mode="clean_refresh",
            continuity_state={
                "subjects": {
                    "Amy": {
                        "subject_id": 1,
                        "name": "Amy",
                        "position": "*by the door*",
                        "wardrobe": ["**blue coat**"],
                    },
                },
            },
        )

        self.assertNotIn("*", prompt)
        self.assertIn("Amy remains by the door.", prompt)
        self.assertIn("position: by the door", prompt)

    def test_h3_formatter_parses_json_metadata_followed_by_markdown_fields(self):
        parsed = minimax.parse_h3_formatter_result(
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )

        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")
        self.assertEqual(parsed["non_diegetic_music"], "N/A")
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})

    def test_multiple_fenced_formatter_blocks_do_not_reach_final_h3_prompt(self):
        raw = (
            "```ALIGNMENT\n"
            "Reference alignment: Amy's identity and the cabin remain consistent.\n"
            "```\n\n"
            "```H3\n"
            "detailed_description: [Shot 1] Amy enters the cabin.\n"
            "```\n\n"
            "```SOUND\n"
            "overall_soundscape: Footsteps on the wooden floor.\n"
            "```\n\n"
            "```MUSIC\n"
            "non_diegetic_music: Soft piano undercurrent.\n"
            "```"
        )

        parsed = minimax.parse_h3_formatter_result(raw)
        prompt = minimax.build_h3_prompt(
            parsed,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("```", prompt)
        self.assertIn("Reference alignment: Amy's identity and the cabin remain consistent.", prompt)
        self.assertIn("[Shot 1] Amy enters the cabin.", prompt)
        self.assertIn("Footsteps on the wooden floor.", prompt)
        self.assertIn("non_diegetic_music: Soft piano undercurrent.", prompt)

    def test_h3_component_sanitizer_removes_standalone_fence_lines_only(self):
        value = "Before\n```JSON\nInside\n```\nafter"

        self.assertEqual(
            minimax.sanitize_h3_prompt_component(value),
            "Before\nInside\nafter",
        )

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_ask_llm_preserves_mixed_h3_response(self, post, _history):
        mixed = (
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": mixed}}]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            response_format=None,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertIsInstance(result, str)
        parsed = minimax.parse_h3_formatter_result(result)
        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})

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

    @mock.patch("minimax.validate_mistral_prompt")
    @mock.patch("minimax.format_mistral_prompt")
    @mock.patch("minimax.request_valid_mistral_prompt", create=True)
    @mock.patch("minimax.ask_llm")
    def test_segment_llm_runs_two_requests_without_legacy_seams(
        self,
        ask_llm,
        legacy_director,
        formatter,
        validator,
    ):
        raw_scene = (
            "Mark enters—quietly in a white T-shirt—and reacts to the "
            "environment without performing the active beat's listed events."
        )
        formatted = formatter_response(
            "[Shot 1] Mark enters and reacts to the environment."
        )
        # Even with the structured response format, LM Studio may return the
        # formatter object as JSON text rather than a decoded Python dict.
        ask_llm.side_effect = [raw_scene, json.dumps(formatted)]

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
        self.assertEqual(
            ask_llm.call_args_list[1].kwargs["response_format"],
            minimax.H3_FORMATTER_RESPONSE_FORMAT,
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
        self.assertIn(
            "enters—quietly in a white T-shirt",
            ask_llm.call_args_list[1].args[0][1]["content"],
        )
        self.assertEqual(payload["h3_mode"], "T2VA")

    def test_combined_continuity_avoids_lm_studio_schema_rejection(self):
        llm_request = mock.Mock(side_effect=[
            {"subject": {"name": "Amy"}},
        ])

        minimax.request_combined_continuity(
            "A full scene description.",
            {"environment": {"location": "bedroom"}},
            llm_request=llm_request,
            history_metadata={"run_id": "r1"},
            content_attempts=1,
            defer_opening=True,
        )

        combined_call = llm_request.call_args_list[0]
        self.assertIsNone(combined_call.kwargs["response_format"])

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
    def test_segment_llm_retries_director_request_2_on_timestamp_mismatch(
        self, ask_llm):
        raw_scene = (
            "At 00:00.0, Mark enters the room.\n"
            "At 00:02.500, Mark looks toward the window."
        )
        missing_timestamp = formatter_response(
            "[Shot 1] Mark enters the room. At 00:00.000 seconds, "
            "Mark looks toward the window."
        )
        corrected = formatter_response(
            "[Shot 1] Mark enters the room. At 00:00.000 seconds, "
            "Mark enters. At 00:02.500 seconds, Mark looks toward the window."
        )
        ask_llm.side_effect = [raw_scene, missing_timestamp, corrected]

        payload = minimax.request_segment_llm(
            segment_bundle(),
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        self.assertEqual(ask_llm.call_count, 3)
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["attempt"]
                for call in ask_llm.call_args_list
            ],
            [1, 2, 2],
        )
        self.assertIn(
            "TIMESTAMP VALIDATION FAILURE",
            ask_llm.call_args_list[2].args[0][-1]["content"],
        )
        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            corrected["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")
    def test_segment_llm_does_not_require_opening_timestamp_match(self, ask_llm):
        raw_scene = "At 00:00.000, Mark enters the room."
        formatted = formatter_response("[Shot 1] Mark enters the room.")
        ask_llm.side_effect = [raw_scene, formatted]

        payload = minimax.request_segment_llm(
            segment_bundle(),
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        self.assertEqual(ask_llm.call_count, 2)
        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            formatted["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")
    def test_segment_llm_uses_last_timestamp_mismatch_after_ten_retries(
        self, ask_llm):
        raw_scene = (
            "At 00:00.000, Mark enters the room.\n"
            "At 00:02.000, Mark looks toward the window."
        )
        invalid = formatter_response(
            "[Shot 1] Mark enters the room. At 00:00.000 seconds, "
            "Mark enters."
        )
        ask_llm.side_effect = [raw_scene] + [invalid] * 10

        with mock.patch("builtins.print") as printed:
            payload = minimax.request_segment_llm(
                segment_bundle(),
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(ask_llm.call_count, 11)
        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            invalid["detailed_description"],
        )
        self.assertIn(
            "WARNING: Director Request 2 timestamp validation failed after 10 attempts",
            "\n".join(
                str(call.args[0]) for call in printed.call_args_list if call.args
            ),
        )

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
