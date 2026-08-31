import unittest
from unittest import mock

import minimax


def segment_bundle():
    return {
        "segment": 1,
        "active_beat_id": 1,
        "messages": [{"role": "user", "content": "Direct segment 1."}],
        "ministral_context": {"completed_beat_ids": []},
        "conditioning_mode": "initial",
        "opening_state_sha256": "opening-hash",
    }


class DirectorBeatCompletionRetryTests(unittest.TestCase):
    def test_final_incomplete_result_is_used_instead_of_raising(self):
        attempt_limit = minimax.DIRECTOR_BEAT_COMPLETION_ATTEMPTS
        results = [
            {"completed_beat_ids": [], "iteration": attempt}
            for attempt in range(1, attempt_limit + 1)
        ]

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=results,
        ) as request, mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                segment_bundle(),
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(request.call_count, attempt_limit)
        self.assertEqual(payload["llm_result"]["iteration"], attempt_limit)
        self.assertEqual(payload["llm_result"]["completed_beat_ids"], [1])
        self.assertEqual(
            minimax.apply_reported_beat_completions(
                ["Beat one"],
                set(),
                payload["llm_result"]["completed_beat_ids"],
                1,
            ),
            {1},
        )
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["attempt"]
                for call in request.call_args_list
            ],
            list(range(1, attempt_limit + 1)),
        )
        self.assertTrue(any(
            "marking the assigned beat complete" in str(call)
            for call in output.call_args_list
        ))

    def test_final_repeated_dialogue_response_is_used_instead_of_raising(self):
        attempt_limit = minimax.DIRECTOR_BEAT_COMPLETION_ATTEMPTS
        results = [
            {
                "detailed_description": (
                    "[Shot 1] <Subject 1> Amy (S1) says: "
                    "<d>[English] Repeated line.</d>"
                ),
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [1],
                "iteration": attempt,
            }
            for attempt in range(1, attempt_limit + 1)
        ]
        bundle = segment_bundle()
        bundle["dialogue_exclusions"] = ["Repeated line."]

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=results,
        ) as request, mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                bundle,
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(request.call_count, attempt_limit)
        self.assertEqual(payload["llm_result"]["iteration"], attempt_limit)
        self.assertTrue(any(
            "using the latest response and moving on" in str(call)
            for call in output.call_args_list
        ))

    def test_final_continuity_rejection_is_used_instead_of_raising(self):
        attempt_limit = minimax.DIRECTOR_BEAT_COMPLETION_ATTEMPTS
        results = [
            {
                "detailed_description": f"Candidate {attempt}.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [1],
                "iteration": attempt,
            }
            for attempt in range(1, attempt_limit + 1)
        ]
        bundle = segment_bundle()
        bundle.update({
            "segment": 2,
            "conditioning_mode": "latent_continuation",
            "opening_state": {},
        })
        rejected = {
            "valid": False,
            "issues": [{
                "type": "persistent_transition_replay",
                "problem": "The candidate repeats a completed transition.",
            }],
        }

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=results,
        ) as request, mock.patch(
            "minimax.validate_director_continuity_candidate",
            return_value=rejected,
        ) as validate, mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                bundle,
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(request.call_count, attempt_limit)
        self.assertEqual(validate.call_count, attempt_limit)
        self.assertEqual(payload["llm_result"]["iteration"], attempt_limit)
        self.assertTrue(any(
            "using the latest response and moving on" in str(call)
            for call in output.call_args_list
        ))

    def test_continuity_validation_error_uses_latest_response(self):
        latest = {
            "detailed_description": "Use this latest candidate.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }
        bundle = segment_bundle()
        bundle.update({
            "segment": 2,
            "conditioning_mode": "latent_continuation",
            "opening_state": {},
        })

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            return_value=latest,
        ), mock.patch(
            "minimax.validate_director_continuity_candidate",
            side_effect=ValueError("invalid validator response"),
        ), mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                bundle,
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertIs(payload["llm_result"], latest)
        self.assertTrue(any(
            "continuity validation failed" in str(call)
            for call in output.call_args_list
        ))

    def test_director_request_error_uses_previous_response(self):
        previous = {
            "detailed_description": "Use this previous candidate.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=[previous, RuntimeError("transport failed")],
        ) as request, mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                segment_bundle(),
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(request.call_count, 2)
        self.assertIs(payload["llm_result"], previous)
        self.assertTrue(any(
            "using the latest available response and moving on" in str(call)
            for call in output.call_args_list
        ))

    def test_first_director_request_error_uses_best_effort_fallback(self):
        bundle = segment_bundle()
        bundle["ministral_context"]["current_beat_text"] = "Amy opens the gate."

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=RuntimeError("transport failed"),
        ), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle,
                ["Amy opens the gate."],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(
            payload["llm_result"]["detailed_description"],
            "Amy opens the gate.",
        )

    def test_retry_loop_stops_as_soon_as_active_beat_is_completed(self):
        incomplete = {"completed_beat_ids": [], "iteration": 1}
        completed = {"completed_beat_ids": [1], "iteration": 2}

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=[incomplete, completed],
        ) as request:
            payload = minimax.request_segment_llm(
                segment_bundle(),
                ["Beat one"],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(request.call_count, 2)
        self.assertIs(payload["llm_result"], completed)

    @mock.patch("minimax.validate_ministral_prompt")
    @mock.patch("minimax.format_ministral_prompt")
    @mock.patch("minimax.ask_llm")
    def test_actual_generation_path_never_runs_prompt_validation(
        self,
        ask_llm,
        formatter,
        validator,
    ):
        result = {
            "detailed_description": (
                "[Shot 1] Alice enters and reacts to the environment without "
                "performing the active beat's listed events."
            ),
            "overall_soundscape": "Room ambience continues.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }
        ask_llm.return_value = result
        formatter.return_value = result

        payload = minimax.request_segment_llm(
            segment_bundle(),
            ["Alice confronts the Duchess, Cook, piglets, and Cheshire Cat."],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        ask_llm.assert_called_once()
        formatter.assert_called_once_with(
            result,
            segment_bundle()["ministral_context"],
        )
        validator.assert_not_called()
        self.assertIs(payload["llm_result"], result)


if __name__ == "__main__":
    unittest.main()
