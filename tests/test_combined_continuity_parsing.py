import json
import unittest
from unittest.mock import Mock, patch

import minimax


def _state():
    return {
        "environment": {
            "location": "bedroom",
            "details": ["window", {"lighting": "low"}],
        },
        "subjects": {
            "Mark": {
                "position": "beside the window",
                "note": 'He says, "stay here".',
            },
        },
        "camera": "wide shot",
    }


class CombinedContinuityParserTests(unittest.TestCase):
    def assert_parses_state(self, raw, expected=None):
        self.assertEqual(
            minimax._parse_continuity_json_result(raw, "Continuity"),
            _state() if expected is None else expected,
        )

    def test_clean_json_object(self):
        raw = json.dumps(_state())
        self.assert_parses_state(raw)
        self.assertEqual(minimax.parse_llm_json_content(raw), _state())

    def test_json_markdown_fence(self):
        self.assert_parses_state("```json\n" + json.dumps(_state()) + "\n```")

    def test_generic_markdown_fence(self):
        self.assert_parses_state("```\n" + json.dumps(_state()) + "\n```")

    def test_prose_before_valid_json(self):
        self.assert_parses_state("Here is the continuity state:\n" + json.dumps(_state()))

    def test_apostrophe_in_prose_before_valid_json(self):
        self.assert_parses_state("Here's the continuity state:\n" + json.dumps(_state()))

    def test_prose_after_valid_json(self):
        self.assert_parses_state(json.dumps(_state()) + "\nThat is all.")

    def test_nested_objects_and_arrays(self):
        state = _state()
        state["environment"]["nested"] = {
            "items": [{"id": 1}, {"id": 2, "tags": ["a", "b"]}],
        }
        self.assertEqual(
            minimax._parse_continuity_json_result(json.dumps(state), "Continuity"),
            state,
        )

    def test_braces_inside_quoted_strings(self):
        state = _state()
        state["environment"]["description"] = "A sign reads {KEEP OUT}."
        self.assert_parses_state(json.dumps(state), state)

    def test_escaped_quotes_inside_strings(self):
        state = _state()
        state["subjects"]["Mark"]["note"] = 'He says, "stay {here}".'
        self.assert_parses_state(json.dumps(state), state)

    def test_continuity_state_wrapper_is_normalized(self):
        wrapped = {"continuity_state": _state()}
        self.assertEqual(
            minimax._parse_continuity_json_result(
                json.dumps(wrapped),
                "Continuity",
            ),
            _state(),
        )

    def test_unwrapped_state_is_normalized_to_same_shape(self):
        self.assertEqual(
            minimax._parse_continuity_json_result(json.dumps(_state()), "Continuity"),
            minimax._parse_continuity_json_result(
                json.dumps({"continuity_state": _state()}),
                "Continuity",
            ),
        )

    def test_characters_key_is_normalized_to_subjects(self):
        state = _state()
        legacy = dict(state)
        legacy["characters"] = legacy.pop("subjects")
        self.assertEqual(
            minimax._parse_continuity_json_result(json.dumps(legacy), "Continuity"),
            state,
        )

    def test_prompt_derived_clothing_condition_is_discarded(self):
        state = _state()
        state["subjects"]["Mark"]["clothing_condition"] = (
            "his torn sleeve snagged on a thorn and trousers stained with soil"
        )

        parsed = minimax._parse_continuity_json_result(
            json.dumps(state),
            "Continuity",
        )

        self.assertNotIn("clothing_condition", parsed["subjects"]["Mark"])

    def test_clothing_claim_in_physical_condition_is_not_a_wardrobe_fallback(self):
        state = _state()
        state["subjects"]["Mark"]["physical_condition"] = (
            "his torn sleeve snagged on a thorn and trousers stained with soil"
        )

        parsed = minimax._parse_continuity_json_result(
            json.dumps(state),
            "Continuity",
        )

        self.assertNotIn("physical_condition", parsed["subjects"]["Mark"])

    def test_top_level_array_is_not_reduced_to_nested_object(self):
        with self.assertRaises(ValueError):
            minimax._parse_continuity_json_result(
                json.dumps([_state()]),
                "Continuity",
            )

    def test_malformed_outer_object_is_not_reduced_to_nested_object(self):
        with self.assertRaises(ValueError):
            minimax._parse_continuity_json_result(
                '{"outer": {"environment": {"location": "bedroom"}}',
                "Continuity",
            )

    def test_genuinely_malformed_json_still_fails(self):
        with self.assertRaises(ValueError):
            minimax._parse_continuity_json_result(
                '{"environment": {"location": "bedroom"',
                "Continuity",
            )

    def test_parse_failure_logs_complete_raw_response_and_specific_error(self):
        raw_failure = '{"environment": {"location": "bedroom"'
        request = Mock(side_effect=[raw_failure, json.dumps(_state())])

        with patch(
            "minimax._parse_continuity_json_result",
            side_effect=[ValueError("malformed continuity JSON"), _state()],
        ), patch("builtins.print") as printed:
            result = minimax.request_combined_continuity(
                "FINAL H3 PROMPT",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
            )

        self.assertEqual(result["reduced_state"], _state())
        output = "\n".join(
            str(argument)
            for call in printed.call_args_list
            for argument in call.args
        )
        self.assertIn("CONTINUITY RAW RESPONSE - PARSE FAILURE:", output)
        self.assertIn(raw_failure, output)
        parse_error_lines = [
            line
            for line in output.splitlines()
            if line.startswith("CONTINUITY PARSE ERROR:")
        ]
        self.assertTrue(parse_error_lines)
        self.assertNotEqual(
            parse_error_lines[0],
            "CONTINUITY PARSE ERROR: Continuity did not return valid JSON.",
        )

    def test_retry_receives_concise_invalid_json_correction(self):
        request = Mock(side_effect=["not JSON", json.dumps(_state())])

        with patch(
            "minimax._parse_continuity_json_result",
            side_effect=[ValueError("malformed continuity JSON"), _state()],
        ), patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "PROMPT",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
            )

        self.assertEqual(result["reduced_state"], _state())
        self.assertEqual(request.call_count, 2)
        correction = request.call_args_list[1].args[0][1]["content"]
        self.assertIn("previous response was not usable JSON", correction)
        self.assertIn("syntactically invalid JSON", correction)
        self.assertNotIn("not JSON", correction)

    def test_python_owned_identity_metadata_is_stripped_without_retry(self):
        definitions = "<Subject 1> is Mark, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(definitions)
        request = Mock(return_value={
            "version": 5,
            "environment": {"location": "room", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {
                "Mark": {
                    "id": "<Subject 1>",
                    "subject_id": "Mark",
                    "name": "Mark",
                    "gender": "male",
                    "picture_ids": ["<Picture 1>"],
                    "picture_id": "<Picture 1>",
                    "speaker_id": "(S1)",
                    "origin_segment": "Shot 1",
                    "persistent_structural_change": True,
                    "position": "beside the window",
                    "held_props": ["tool"],
                },
            },
        })

        with patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "FULL SEGMENT",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
                subject_definitions=definitions,
                committed_state=committed,
                ending_scene="Mark stands beside the window holding a tool.",
            )

        self.assertEqual(request.call_count, 1)
        mark = result["reduced_state"]["subjects"]["Mark"]
        self.assertEqual(mark["subject_id"], 1)
        self.assertEqual(mark["picture_ids"], [1])
        self.assertEqual(mark["speaker_id"], "(S1)")
        self.assertEqual(mark["position"], "beside the window")
        self.assertEqual(mark["held_props"], ["tool"])

    def test_combined_continuity_marks_end_state_as_final_frame_authority(self):
        definitions = "<Subject 1> is Mark, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(definitions)
        request = Mock(return_value={
            "version": 5,
            "environment": {"location": "room", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {"Mark": {"position": "beside the closed door"}},
        })

        with patch("minimax._print_continuity_phase_result"):
            minimax.request_combined_continuity(
                "At 00:00 Mark fires a tool. Loud impact.",
                {},
                llm_request=request,
                content_attempts=1,
                defer_opening=True,
                subject_definitions=definitions,
                committed_state=committed,
                ending_scene="Mark stands beside the closed door.",
            )

        user_content = request.call_args.args[0][1]["content"]
        self.assertIn(
            "FINAL FRAME AUTHORITY:\nMark stands beside the closed door.",
            user_content,
        )
        self.assertIn("FULL SEGMENT CONTEXT:", user_content)
        self.assertIn(
            "Use FINAL FRAME AUTHORITY for all current-frame fields.",
            user_content,
        )

    def test_noncanonical_subject_keys_retry_and_canonical_keys_are_accepted(self):
        request = Mock(side_effect=[
            {
                "subjects": {
                    "Mark": {
                        "name": "Mark",
                        "pose": "standing",
                        "condition": "unhurt",
                        "props": ["tool"],
                    },
                },
            },
            {
                "subjects": {
                    "Mark": {
                        "name": "Mark",
                        "pose_action": "standing",
                        "physical_condition": "unhurt",
                        "held_props": ["tool"],
                    },
                },
            },
        ])

        with patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "detailed_description: Mark stands in the room.",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
                subject_definitions="<Subject 1> is Mark, referenced in <Picture 1>.",
                committed_state=minimax.continuity_state_for_registry(
                    "<Subject 1> is Mark, referenced in <Picture 1>."
                ),
            )

        self.assertEqual(request.call_count, 2)
        correction = request.call_args_list[1].args[0][1]["content"]
        self.assertIn('SCHEMA ERROR: subjects.Mark.pose', correction)
        self.assertIn("subjects.Mark.condition", correction)
        self.assertIn("subjects.Mark.props", correction)
        self.assertEqual(
            result["reduced_state"]["subjects"]["Mark"]["pose_action"],
            "standing",
        )
        self.assertNotIn("pose", result["reduced_state"]["subjects"]["Mark"])

    def test_noncanonical_top_level_keys_retry_and_canonical_keys_are_accepted(self):
        request = Mock(side_effect=[
            {
                "setting": "room",
                "sound": "room tone",
                "environmental_state": "quiet",
            },
            {
                "environment": {
                    "location": "room",
                    "persistent_state": "quiet",
                },
                "ongoing_audio": "room tone",
            },
        ])

        with patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "PROMPT",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
            )

        self.assertEqual(request.call_count, 2)
        correction = request.call_args_list[1].args[0][1]["content"]
        self.assertIn("SCHEMA ERROR:", correction)
        self.assertIn("setting", correction)
        self.assertIn("sound", correction)
        self.assertIn("environmental_state", correction)
        self.assertEqual(result["reduced_state"]["environment"]["location"], "room")
        self.assertEqual(result["reduced_state"]["ongoing_audio"], "room tone")

    def test_schema_retry_exhaustion_preserves_committed_canonical_state(self):
        request = Mock(return_value={"subjects": {"Mark": {"props": ["tool"]}}})
        committed = minimax.continuity_state_for_registry(
            "<Subject 1> is Mark, referenced in <Picture 1>."
        )
        committed["subjects"]["Mark"]["position"] = "beside the window"

        with patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "detailed_description: Mark stands beside the window.",
                {},
                llm_request=request,
                content_attempts=2,
                defer_opening=True,
                subject_definitions="<Subject 1> is Mark, referenced in <Picture 1>.",
                committed_state=committed,
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            result["reduced_state"]["subjects"]["Mark"]["position"],
            "beside the window",
        )
        self.assertNotIn("props", result["reduced_state"]["subjects"]["Mark"])

    def test_phase_two_uses_request_one_end_state_boundary(self):
        definitions = (
            "<Subject 1> is Alex, referenced in <Picture 1>.\n"
            "<Subject 2> is Blair, referenced in <Picture 2>."
        )
        committed = minimax.continuity_state_for_registry(definitions)
        request = Mock(side_effect=[
            {
                "subjects": {
                    "Alex": {"name": "Alex", "subject_id": 1, "position": "outside"},
                    "Blair": {"name": "Blair", "subject_id": 2, "position": "inside"},
                },
            },
            "Alex stands outside the closed door.",
        ])

        minimax.request_combined_continuity(
            "Earlier: Alex and Blair are visible. Alex closes a door behind Blair.\n"
            "End continuity state: Alex stands outside the closed door.",
            {},
            llm_request=request,
            content_attempts=1,
            subject_definitions=definitions,
            committed_state=committed,
        )

        phase2_user_prompt = request.call_args_list[1].args[0][1]["content"]
        self.assertIn('"Alex"', phase2_user_prompt)
        self.assertNotIn('"Blair"', phase2_user_prompt)

    def test_exhausted_retries_use_an_empty_best_effort_state(self):
        continuity_request = Mock(side_effect=[ValueError("bad"), ValueError("bad")])

        with patch(
            "minimax._parse_continuity_json_result",
            side_effect=ValueError("malformed continuity JSON"),
        ):
            result = minimax.request_combined_continuity(
                "PROMPT",
                {},
                llm_request=continuity_request,
                content_attempts=2,
                defer_opening=True,
            )

        self.assertEqual(result["reduced_state"], minimax.new_continuity_state())
        self.assertEqual(continuity_request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
