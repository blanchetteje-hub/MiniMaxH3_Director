import unittest
from unittest.mock import Mock, patch

import minimax


def segment_result(number):
    return {
        "integrated_multimodal_description": (
            f"[Shot {number}] Camera continues from the previous shot. "
            f"Mark stands beside numbered prop {number}."
        ),
        "overall_soundscape": f"Room tone {number}.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [number],
    }


class ContinuitySummaryTests(unittest.TestCase):
    def test_summary_worker_is_closed_when_generation_raises(self):
        worker = Mock()
        worker.__enter__ = Mock(return_value=worker)
        worker.__exit__ = Mock(return_value=False)
        with patch("minimax.ThreadPoolExecutor", return_value=worker) as factory:
            with patch("minimax._run_main", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    minimax.main()

        factory.assert_called_once_with(
            max_workers=1,
            thread_name_prefix="continuity-summary",
        )
        worker.__exit__.assert_called_once()

    @patch("minimax.requests.post")
    def test_plain_text_summary_uses_chat_completions_without_schema(
        self, post
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "\n".join(
                        f"- fact {number}" for number in range(1, 6)
                    )
                }
            }]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "summarize"}],
            max_retries=1,
            response_format=None,
        )

        self.assertEqual(5, len(result.splitlines()))
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            f"{minimax.LM_STUDIO_URL}/v1/chat/completions",
            url,
        )
        self.assertNotIn("response_format", payload)

    def test_summary_thread_contains_only_the_last_two_exact_results(self):
        messages = minimax.build_summary_messages([
            (1, segment_result(1)),
            (2, segment_result(2)),
            (3, segment_result(3)),
        ])

        combined = "\n".join(message["content"] for message in messages)
        self.assertNotIn("numbered prop 1", combined)
        self.assertIn("numbered prop 2", combined)
        self.assertIn("numbered prop 3", combined)
        self.assertNotIn("completed_beat_ids", combined)
        self.assertEqual(["system", "user"], [m["role"] for m in messages])

    def test_summary_requires_two_results(self):
        with self.assertRaisesRegex(ValueError, "exactly two"):
            minimax.build_summary_messages([(1, segment_result(1))])

    def test_numbered_summary_is_normalized_to_exactly_five_bullets(self):
        raw = "\n".join(f"{number}. fact {number}" for number in range(1, 6))
        self.assertEqual(
            "\n".join(f"- fact {number}" for number in range(1, 6)),
            minimax.normalize_five_bullet_summary(raw),
        )

    def test_malformed_summary_is_requeried_in_separate_plain_text_thread(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append((messages, kwargs))
            if len(calls) == 1:
                return "- only one bullet"
            return "\n".join(f"- fact {number}" for number in range(1, 6))

        summary = minimax.request_five_bullet_summary(
            [(1, segment_result(1)), (2, segment_result(2))],
            llm_request=fake_llm,
        )

        self.assertEqual(2, len(calls))
        self.assertEqual(5, len(summary.splitlines()))
        self.assertIsNone(calls[0][1]["response_format"])
        self.assertNotIn("formatter", calls[0][0][0]["content"].lower())
        self.assertIn("prior response", calls[1][0][-1]["content"].lower())

    def test_generation_context_has_summary_and_only_two_exact_results(self):
        summary = "\n".join(f"- continuity fact {n}" for n in range(1, 6))
        messages, _, recent_count = minimax.build_generation_messages(
            director_rules="DIRECTOR",
            story="SOURCE STORY",
            beats=[],
            completed_beat_ids=set(),
            recent_results=[
                (1, segment_result(1)),
                (2, segment_result(2)),
                (3, segment_result(3)),
            ],
            current_segment=4,
            total_segments=6,
            segment_length=6,
            total_length=36,
            continuity_summary=summary,
        )

        user_content = messages[1]["content"]
        self.assertEqual(2, recent_count)
        self.assertIn(summary, user_content)
        self.assertNotIn("numbered prop 1", user_content)
        self.assertIn("numbered prop 2", user_content)
        self.assertIn("numbered prop 3", user_content)
        self.assertIn("SOURCE STORY", user_content)

    def test_invalid_summary_fails_after_bounded_content_attempts(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append(messages)
            return "not a five-bullet summary"

        with self.assertRaisesRegex(RuntimeError, "exact five-bullet"):
            minimax.request_five_bullet_summary(
                [(1, segment_result(1)), (2, segment_result(2))],
                llm_request=fake_llm,
                content_attempts=2,
            )
        self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main()
