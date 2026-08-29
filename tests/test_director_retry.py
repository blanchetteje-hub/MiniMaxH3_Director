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
    def test_fifth_incomplete_result_is_used_instead_of_raising(self):
        results = [
            {"completed_beat_ids": [], "iteration": attempt}
            for attempt in range(1, 6)
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

        self.assertEqual(request.call_count, 5)
        self.assertIs(payload["llm_result"], results[-1])
        self.assertEqual(
            [
                call.kwargs["history_metadata"]["attempt"]
                for call in request.call_args_list
            ],
            [1, 2, 3, 4, 5],
        )
        self.assertTrue(any(
            "continuing with the latest result" in str(call)
            for call in output.call_args_list
        ))

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


if __name__ == "__main__":
    unittest.main()
