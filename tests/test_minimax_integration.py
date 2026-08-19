import json
import unittest
from unittest import mock

import minimax


SUBJECTS = (
    "<Subject 1> is Mark, referenced in <Picture 1>.\n"
    "<Subject 2> is Jill, referenced in <Picture 2>."
)
BEATS = [
    "Show Mark, Jill, and his family.",
    "Show flying saucers flying overhead.",
    "Show Mark and Jill talking and trying to figure out what is happening.",
    "Show the saucers abducting Mark's family as they run away."
]


def context_for(beat_number):
    return {
        "segment_number": beat_number,
        "segment_duration": 6.0,
        "subject_definitions": SUBJECTS,
        "completed_beat_ids": list(range(1, beat_number)),
        "next_beat_id": beat_number,
        "current_beat_text": BEATS[beat_number - 1],
        "later_beat_texts": BEATS[beat_number:],
        "beat_deadline_required": True,
        "allow_silence": False,
        "hard_cut_required": beat_number % 3 == 0
    }


def response(description, completed):
    return {
        "integrated_multimodal_description": description,
        "overall_soundscape": "Crowds murmur while footsteps cross the pavement.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": completed
    }


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": self.content}}]
        }


class LmStudioIntegrationTests(unittest.TestCase):
    @mock.patch("minimax.load_text_file")
    def test_blank_or_comment_only_beats_file_disables_beats(self, load_text):
        for contents in ("", "\n  \n", "# no beat tracking\n  # disabled\n"):
            with self.subTest(contents=contents):
                load_text.return_value = contents
                self.assertEqual(minimax.load_beats("beats.txt"), [])

    def test_disabled_beats_are_omitted_from_director_messages(self):
        rules = minimax.build_director_rules(
            total_length=12,
            segment_length=6,
            total_segments=2,
            subject_definitions=SUBJECTS,
            megapixels=0.5,
            beats_enabled=False
        )
        messages, _, _ = minimax.build_generation_messages(
            director_rules=rules,
            story="Two friends walk down a country road.",
            beats=[],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=2,
            segment_length=6,
            total_length=12
        )
        combined = "\n".join(message["content"] for message in messages)

        self.assertNotIn("AUTHORITATIVE STORY BEAT CHECKLIST", combined)
        self.assertNotIn("BEAT COMPLETION REPORTING", combined)
        self.assertNotIn("[NEXT]", combined)
        self.assertIn("Beat tracking is disabled", combined)
        self.assertIn("Two friends walk down a country road.", combined)

    def test_blank_beats_build_a_complete_disabled_formatter_context(self):
        context = minimax.build_ministral_context(
            segment_number=2,
            segment_duration=6.0,
            total_segments=2,
            beats=[],
            completed_beat_ids=[99],
            subject_definitions=SUBJECTS,
            story="Two friends walk down a country road."
        )

        self.assertEqual(context["completed_beat_ids"], [])
        self.assertIsNone(context["next_beat_id"])
        self.assertIsNone(context["current_beat_text"])
        self.assertEqual(context["later_beat_texts"], [])
        self.assertFalse(context["beat_deadline_required"])

    def test_disabled_beats_force_empty_completion_metadata_locally(self):
        context = minimax.build_ministral_context(
            segment_number=1,
            segment_duration=6.0,
            total_segments=1,
            beats=[],
            completed_beat_ids=[],
            subject_definitions=SUBJECTS,
            story="Mark and Jill walk down a country road."
        )
        malformed = response(
            "[Shot 1] Live-action, cinematic, <Subject 1> Mark and "
            "<Subject 2> Jill walk down a country road.",
            [7]
        )

        formatted = minimax.format_ministral_prompt(malformed, context)

        self.assertEqual(formatted["completed_beat_ids"], [])
        self.assertEqual(minimax.validate_ministral_prompt(formatted, context), [])

    def test_parse_llm_json_content_accepts_fences_and_leading_prose(self):
        payload = {"value": 1}
        self.assertEqual(
            minimax.parse_llm_json_content(
                "```json\n" + json.dumps(payload) + "\n```"
            ),
            payload
        )
        self.assertEqual(
            minimax.parse_llm_json_content(
                "Here is the result: " + json.dumps(payload)
            ),
            payload
        )

    @mock.patch("minimax.requests.post")
    def test_ask_llm_selects_configured_ministral_model(self, post):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark, Jill, and Mark's family "
            "stand together in a busy theme park.",
            [1]
        )
        post.return_value = FakeResponse(json.dumps(payload))

        self.assertEqual(minimax.ask_llm([]), payload)

        request_json = post.call_args.kwargs["json"]
        self.assertEqual(request_json["model"], minimax.LM_STUDIO_MODEL)
        self.assertEqual(request_json["response_format"], minimax.RESPONSE_FORMAT)

    @mock.patch("minimax.requests.post")
    def test_ask_llm_falls_back_when_structured_output_gets_http_400(self, post):
        rejected = mock.Mock(
            status_code=400,
            text='{"error":"structured response_format is unavailable"}'
        )
        rejected.raise_for_status.side_effect = minimax.requests.HTTPError(
            "400 Client Error: Bad Request"
        )
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            []
        )
        fallback_result = {"segment": payload}
        post.side_effect = [
            rejected,
            FakeResponse(json.dumps(fallback_result))
        ]

        self.assertEqual(minimax.ask_llm([], max_retries=1), payload)

        first_payload = post.call_args_list[0].kwargs["json"]
        fallback_payload = post.call_args_list[1].kwargs["json"]
        self.assertIn("response_format", first_payload)
        self.assertNotIn("response_format", fallback_payload)
        self.assertEqual(
            fallback_payload["messages"],
            first_payload["messages"]
        )

    @mock.patch("minimax.requests.post")
    def test_ask_llm_reports_lm_studio_http_error_body(self, post):
        rejected = mock.Mock(
            status_code=400,
            text='{"error":"context length exceeded"}'
        )
        rejected.raise_for_status.side_effect = minimax.requests.HTTPError(
            "400 Client Error: Bad Request"
        )
        post.side_effect = [rejected, rejected]

        with self.assertRaisesRegex(
            RuntimeError,
            "context length exceeded"
        ):
            minimax.ask_llm([], max_retries=1)

    @mock.patch("minimax.requests.post")
    def test_plain_labeled_response_reaches_python_formatter_without_retry(self, post):
        labeled = (
            "integrated_multimodal_description: [Shot 1] Live-action, "
            "cinematic, Mark, Jill, and Mark's family stand together in a "
            "busy theme park.\n\n"
            "overall_soundscape: Crowds murmur while footsteps cross the pavement.\n\n"
            "non_diegetic_music: N/A\n\n"
            "completed_beat_ids: [1]"
        )
        post.return_value = FakeResponse(labeled)

        raw = minimax.ask_llm([])
        formatted = minimax.format_ministral_prompt(raw, context_for(1))

        self.assertEqual(post.call_count, 1)
        self.assertEqual(formatted["completed_beat_ids"], [1])
        self.assertTrue(
            formatted["integrated_multimodal_description"].startswith("[Shot 1]")
        )

    def test_python_repair_does_not_make_an_extra_llm_call(self):
        malformed = response(
            "**integrated_multimodal_description:** [Shot 9] At 00:00.000, "
            "Live-action, cinematic, Mark, Jill, and Mark's family stand "
            "together in a busy theme park.",
            ["B001"]
        )
        llm_request = mock.Mock(return_value=malformed)

        formatted = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat one"}],
            context_for(1),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 1)
        self.assertTrue(
            formatted["integrated_multimodal_description"].startswith("[Shot 1]")
        )

    def test_unresolved_content_uses_at_most_two_corrections(self):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        llm_request = mock.Mock(return_value=missing)

        with self.assertRaisesRegex(RuntimeError, "remained invalid"):
            minimax.request_valid_ministral_prompt(
                [{"role": "user", "content": "beat four"}],
                context_for(4),
                llm_request=llm_request
            )

        self.assertEqual(llm_request.call_count, 3)

    def test_one_last_resort_correction_can_succeed(self):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        corrected = response(
            "[Shot 4] Live-action, cinematic, Mark's family run from the "
            "saucers as beams seize and lift them into the craft until the "
            "completed abduction leaves Mark and Jill beside empty pavement.",
            [4]
        )
        llm_request = mock.Mock(side_effect=[missing, corrected])

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat four"}],
            context_for(4),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 2)
        self.assertEqual(result["completed_beat_ids"], [4])

    def test_context_uses_real_total_segment_deadline(self):
        before_deadline = minimax.build_ministral_context(
            segment_number=1,
            segment_duration=6.0,
            total_segments=8,
            beats=BEATS,
            completed_beat_ids=[],
            subject_definitions=SUBJECTS,
            story="A noisy theme park."
        )
        at_deadline = minimax.build_ministral_context(
            segment_number=2,
            segment_duration=6.0,
            total_segments=8,
            beats=BEATS,
            completed_beat_ids=[],
            subject_definitions=SUBJECTS,
            story="A noisy theme park."
        )

        self.assertFalse(before_deadline["beat_deadline_required"])
        self.assertTrue(at_deadline["beat_deadline_required"])

    def test_later_beat_leakage_is_checked_before_deadline(self):
        context = context_for(1)
        context["beat_deadline_required"] = False
        leaked = response(
            "[Shot 1] Live-action, cinematic, Mark, Jill, and their family "
            "stand together as flying saucers suddenly cross overhead.",
            []
        )

        issues = minimax.validate_ministral_prompt(leaked, context)

        self.assertIn(
            "Description prematurely introduces the later flying-saucer beat.",
            issues
        )

    def test_serializer_has_no_language_suffix_or_completion_metadata(self):
        formatted = response(
            "[Shot 1] Live-action, cinematic, Mark, Jill, and Mark's family "
            "stand together at the theme park.",
            [1]
        )
        prompt = minimax.build_h3_prompt(formatted, SUBJECTS)

        self.assertTrue(prompt.startswith("subject_definitions:"))
        self.assertNotIn("All language is in English", prompt)
        self.assertNotIn("completed_beat_ids", prompt)
        self.assertEqual(prompt.count("integrated_multimodal_description:"), 1)
        self.assertEqual(prompt.count("overall_soundscape:"), 1)
        self.assertEqual(prompt.count("non_diegetic_music:"), 1)


if __name__ == "__main__":
    unittest.main()
