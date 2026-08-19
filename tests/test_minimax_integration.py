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
    def test_next_beat_prompt_demands_immediate_dominant_execution(self):
        request = minimax.build_segment_request(
            segment=1,
            total_segments=8,
            segment_length=6,
            total_length=48,
            beats=BEATS,
            completed_beat_ids=[]
        )

        self.assertIn("PRIMARY BEAT EXECUTION - NON-NEGOTIABLE", request)
        self.assertIn("Begin its visible action in the opening moments", request)
        self.assertIn("make it the dominant event", request)
        self.assertIn("devote most of the clip to accomplishing it", request)
        self.assertIn("Actively attempt to complete B001 in THIS segment", request)
        self.assertIn("Do not delay merely because time remains", request)
        self.assertIn("Do not substitute atmosphere", request)

    def test_action_and_dialogue_beats_receive_specific_execution_orders(self):
        action_request = minimax.build_segment_request(
            2, 8, 6, 48, BEATS, [1]
        )
        dialogue_request = minimax.build_segment_request(
            3, 8, 6, 48, BEATS, [1, 2]
        )

        self.assertIn("physical action clearly on screen", action_request)
        self.assertIn("required audible exchange now", dialogue_request)
        self.assertIn("implied conversation do not count", dialogue_request)

    def test_beat_deadline_demands_visible_outcome_and_completion_id(self):
        request = minimax.build_segment_request(
            segment=2,
            total_segments=8,
            segment_length=6,
            total_length=48,
            beats=BEATS,
            completed_beat_ids=[]
        )

        self.assertIn("has reached its pacing deadline", request)
        self.assertIn("unmistakable outcome before the shot ends", request)
        self.assertIn("completed_beat_ids [1]", request)

    def test_low_megapixel_director_guidance_uses_exact_thresholds(self):
        def rules_for(megapixels):
            return minimax.build_director_rules(
                total_length=12,
                segment_length=6,
                total_segments=2,
                subject_definitions=SUBJECTS,
                megapixels=megapixels,
                beats_enabled=False
            )

        at_half = rules_for(0.5)
        below_half = rules_for(0.49)
        at_four_tenths = rules_for(0.4)
        below_four_tenths = rules_for(0.39)

        self.assertNotIn("mostly close-up camera shots", at_half)
        self.assertNotIn("Avoid a lot of movement", at_half)
        self.assertIn("mostly close-up camera shots", below_half)
        self.assertNotIn("Avoid a lot of movement", below_half)
        self.assertIn("mostly close-up camera shots", at_four_tenths)
        self.assertNotIn("Avoid a lot of movement", at_four_tenths)
        self.assertIn("mostly close-up camera shots", below_four_tenths)
        self.assertIn("Avoid a lot of movement", below_four_tenths)

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

    def test_lm_message_normalizer_merges_adjacent_users(self):
        normalized = minimax.normalize_lm_studio_messages([
            {"role": "system", "content": "director"},
            {"role": "user", "content": "original task"},
            {"role": "user", "content": "correction"}
        ])

        self.assertEqual(
            [message["role"] for message in normalized],
            ["system", "user"]
        )
        self.assertIn("original task", normalized[1]["content"])
        self.assertIn("correction", normalized[1]["content"])

    @mock.patch("minimax.requests.post")
    def test_ask_llm_normalizes_adjacent_users_before_http_request(self, post):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            []
        )
        post.return_value = FakeResponse(json.dumps(payload))

        result = minimax.ask_llm([
            {"role": "system", "content": "director"},
            {"role": "user", "content": "original task"},
            {"role": "user", "content": "correction"}
        ])

        self.assertEqual(result, payload)
        outgoing_messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(
            [message["role"] for message in outgoing_messages],
            ["system", "user"]
        )
        self.assertIn("original task", outgoing_messages[1]["content"])
        self.assertIn("correction", outgoing_messages[1]["content"])

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

    def test_unresolved_content_retries_then_uses_best_effort_without_exiting(self):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        llm_request = mock.Mock(return_value=missing)

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat four"}],
            context_for(4),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 3)
        self.assertIn("Jill look at the sky", result[
            "integrated_multimodal_description"
        ])

    def test_content_correction_uses_stateless_system_user_roles_and_can_succeed(self):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        corrected = response(
            "[Shot 4] At 00:01.000, live-action, cinematic, Mark's family run from the "
            "saucers as beams seize and lift them into the craft until the "
            "completed abduction leaves Mark and Jill beside empty pavement.",
            [4]
        )
        llm_request = mock.Mock(side_effect=[missing, corrected])

        result = minimax.request_valid_ministral_prompt(
            [
                {"role": "system", "content": "director"},
                {"role": "user", "content": "beat four"}
            ],
            context_for(4),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 2)
        correction_messages = llm_request.call_args_list[1].args[0]
        self.assertEqual(
            [message["role"] for message in correction_messages],
            ["system", "user"]
        )
        self.assertIn("PREVIOUS BEST-EFFORT JSON", correction_messages[1]["content"])
        self.assertEqual(result["completed_beat_ids"], [4])

    def test_failed_correction_request_keeps_existing_prompt(self):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        llm_request = mock.Mock(side_effect=[missing, RuntimeError("LM failed")])

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat four"}],
            context_for(4),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 2)
        self.assertIn("look at the sky", result["integrated_multimodal_description"])

    @mock.patch("minimax.format_ministral_prompt")
    def test_formatter_exception_uses_raw_best_effort_without_exiting(self, formatter):
        formatter.side_effect = RuntimeError("local formatter broke")
        raw = response(
            "[Shot 1] Raw usable scene description.",
            []
        )
        llm_request = mock.Mock(return_value=raw)

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "one request"}],
            context_for(1),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 3)
        self.assertEqual(
            result["integrated_multimodal_description"],
            raw["integrated_multimodal_description"]
        )

    @mock.patch("minimax.validate_ministral_prompt")
    def test_validator_exception_uses_formatted_prompt_without_exiting(self, validator):
        validator.side_effect = RuntimeError("local validator broke")
        raw = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            []
        )
        llm_request = mock.Mock(return_value=raw)

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "one request"}],
            context_for(1),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 3)
        self.assertIn("Mark", result["integrated_multimodal_description"])

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

    def test_hard_cut_injects_each_subjects_latest_clothing_into_h3_prompt(self):
        prior_records = [
            {
                "llm_result": response(
                    "[Shot 1] <Subject 1> Mark wears a red shirt and blue "
                    "jeans. <Subject 2> Jill is wearing a yellow dress and "
                    "white sneakers.",
                    []
                )
            },
            {
                "llm_result": response(
                    "[Shot 2] Mark is wearing a navy jacket and black jeans "
                    "while Jill continues beside him.",
                    []
                )
            }
        ]
        hard_cut_result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Mark and "
            "<Subject 2> Jill enter the arcade.",
            []
        )

        clothing = minimax.build_hard_cut_clothing_reiteration(
            SUBJECTS,
            hard_cut_result,
            prior_records
        )
        prompt = minimax.build_h3_prompt(
            hard_cut_result,
            SUBJECTS,
            clothing
        )

        integrated = prompt.split(
            "integrated_multimodal_description: ", 1
        )[1].split("\n\noverall_soundscape:", 1)[0]
        self.assertTrue(
            integrated.startswith("[Shot 3] Camera cuts to a new shot:")
        )
        self.assertIn(
            "<Subject 1> Mark is wearing a navy jacket and black jeans.",
            integrated
        )
        self.assertIn(
            "<Subject 2> Jill is wearing a yellow dress and white sneakers.",
            integrated
        )
        self.assertEqual(integrated.count("<Subject 1>"), 1)
        self.assertEqual(integrated.count("<Subject 2>"), 1)

    def test_hard_cut_never_uses_vague_continuity_when_clothing_is_unknown(self):
        definitions = "<Subject 1> is Connie, referenced in <Picture 1>."
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Connie enters.",
            []
        )

        clothing = minimax.build_hard_cut_clothing_reiteration(
            definitions,
            result,
            []
        )

        self.assertEqual(
            clothing,
            ""
        )

    def test_hard_cut_extracts_exact_appositive_and_still_in_clothing(self):
        definitions = (
            "<Subject 1> is Connie, referenced in <Picture 1>.\n"
            "<Subject 2> is Frank, referenced in <Picture 2>."
        )
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Connie and "
            "<Subject 2> Frank wait beside the road.",
            []
        )
        prior_records = [{
            "llm_result": response(
                "[Shot 2] Connie, a faded green jacket over a white shirt and "
                "black jeans, stands nearby. Frank remains in a blue polo, "
                "khaki trousers, and brown shoes while he watches.",
                []
            )
        }]

        clothing = minimax.build_hard_cut_clothing_reiteration(
            definitions,
            result,
            prior_records
        )

        self.assertIn(
            "<Subject 1> Connie is wearing a faded green jacket over a white "
            "shirt and black jeans.",
            clothing
        )
        self.assertIn(
            "<Subject 2> Frank is wearing a blue polo, khaki trousers, and "
            "brown shoes.",
            clothing
        )

    def test_hard_cut_can_recover_exact_clothing_from_continuity_summary(self):
        definitions = "<Subject 1> is Connie, referenced in <Picture 1>."
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Connie enters.",
            []
        )

        clothing = minimax.build_hard_cut_clothing_reiteration(
            definitions,
            result,
            [],
            "- Connie is still in a burgundy coat and black boots."
        )

        self.assertIn(
            "<Subject 1> Connie is wearing a burgundy coat and black boots.",
            clothing
        )

    def test_hard_cut_prefers_latest_summary_over_older_clothing(self):
        definitions = "<Subject 1> is Connie, referenced in <Picture 1>."
        result = response(
            "[Shot 4] Camera cuts to a new shot: <Subject 1> Connie enters.",
            []
        )
        prior_records = [{
            "llm_result": response(
                "[Shot 1] Connie wears a red shirt and blue jeans.",
                []
            )
        }]

        clothing = minimax.build_hard_cut_clothing_reiteration(
            definitions,
            result,
            prior_records,
            "- Connie is now wearing a burgundy coat and black boots."
        )

        self.assertIn(
            "<Subject 1> Connie is wearing a burgundy coat and black boots.",
            clothing
        )
        self.assertNotIn("red shirt", clothing)

    def test_hard_cut_does_not_introduce_absent_defined_subjects(self):
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Mark, wearing a "
            "red shirt and blue jeans, enters alone.",
            []
        )

        clothing = minimax.build_hard_cut_clothing_reiteration(
            SUBJECTS,
            result,
            []
        )

        self.assertIn("<Subject 1> Mark", clothing)
        self.assertNotIn("<Subject 2> Jill", clothing)


if __name__ == "__main__":
    unittest.main()
