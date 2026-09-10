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

        with patch("builtins.print") as printed:
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

        with patch("minimax._print_continuity_phase_result"):
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

    def test_exhausted_retries_raise_and_do_not_permit_next_director(self):
        malformed = '{"environment": {"location": "bedroom"'
        continuity_request = Mock(side_effect=[malformed, malformed])

        with self.assertRaisesRegex(RuntimeError, "Continuity failed"):
            minimax.request_combined_continuity(
                "PROMPT",
                {},
                llm_request=continuity_request,
                content_attempts=2,
                defer_opening=True,
            )

        # The scheduling caller must not cross the Director boundary after a
        # failed Segment N continuity dependency. The existing Director guard
        # independently enforces that same invariant for Segment 2+.
        with patch("minimax.ask_llm") as director_request:
            with self.assertRaisesRegex(
                RuntimeError,
                "Segment 2 Director continuity",
            ):
                minimax.request_segment_llm(
                    {
                        "segment": 2,
                        "current_duration": 6.0,
                        "messages": [],
                    },
                    [],
                    "run-id",
                    {"source_sha256": "source-hash"},
                )
        director_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
