import json
import unittest
from unittest.mock import Mock, patch

import minimax


SUBJECTS = "<Subject 1> is Mark, referenced in <Picture 1>."


def committed_state():
    state = minimax.continuity_state_for_registry(SUBJECTS)
    state["environment"]["location"] = "bedroom"
    state["subjects"]["Mark"]["position"] = "beside the window"
    return state


class ContinuityCallContractTests(unittest.TestCase):
    def test_combined_continuity_injects_additional_states(self):
        request = Mock(return_value={"environment": {"location": "bedroom"}})

        with patch("minimax.load_additional_states", return_value="destroyed, broken"):
            minimax.request_combined_continuity(
                "FINAL H3 PROMPT",
                {},
                llm_request=request,
                content_attempts=1,
                defer_opening=True,
            )

        system_prompt = request.call_args.args[0][0]["content"]
        self.assertIn("destroyed, broken", system_prompt)
        self.assertNotIn("{additional_states}", system_prompt)

    def test_combined_continuity_deferred_call_is_phase_one_only(self):
        request = Mock(return_value={"environment": {"location": "bedroom"}})

        result = minimax.request_combined_continuity(
            "FINAL H3 PROMPT",
            {"phase_number": 2, "beat_start": 2, "beat_end": 3},
            llm_request=request,
            history_metadata={"run_id": "run-1"},
            content_attempts=1,
            defer_opening=True,
        )

        self.assertEqual(result["opening_state"], "")
        self.assertEqual(request.call_count, 1)
        messages = request.call_args.args[0]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("FINAL FRAME", messages[0]["content"])
        self.assertIn("TOP-LEVEL KEYS ONLY", messages[0]["content"])
        self.assertIn("Return JSON only", messages[0]["content"])
        self.assertIn("FINAL H3 PROMPT", messages[1]["content"])
        self.assertIsNone(request.call_args.kwargs["response_format"])
        self.assertEqual(request.call_args.kwargs["temperature"], 0.10)
        self.assertEqual(request.call_args.kwargs["top_p"], 0.90)
        self.assertEqual(request.call_args.kwargs["max_tokens"], 6000)
        self.assertEqual(
            request.call_args.kwargs["history_metadata"],
            {
                "run_id": "run-1",
                "purpose": "continuity_combined_reduced_state",
                "content_attempt": 1,
            },
        )

    def test_combined_continuity_runs_phase_two_with_reduced_state(self):
        request = Mock(side_effect=[
            {"environment": {"location": "bedroom"}},
            "Mark remains beside the window.",
        ])
        phase = {"phase_number": 2, "beat_start": 2, "beat_end": 3}

        result = minimax.request_combined_continuity(
            "FINAL H3 PROMPT",
            phase,
            llm_request=request,
            history_metadata={"run_id": "run-1"},
            content_attempts=1,
        )

        self.assertEqual(result["opening_state"], "Mark remains beside the window.")
        self.assertEqual(request.call_count, 2)
        self.assertIsNone(request.call_args_list[0].kwargs["response_format"])
        phase2_messages = request.call_args_list[1].args[0]
        self.assertIn('"bedroom"', phase2_messages[1]["content"])
        self.assertNotIn(json.dumps(phase, ensure_ascii=False, indent=2), phase2_messages[1]["content"])
        self.assertEqual(request.call_args_list[1].kwargs["response_format"], None)
        self.assertEqual(request.call_args_list[1].kwargs["temperature"], 0.10)
        self.assertEqual(request.call_args_list[1].kwargs["top_p"], 0.90)
        self.assertEqual(request.call_args_list[1].kwargs["max_tokens"], 2000)
        self.assertEqual(
            request.call_args_list[1].kwargs["history_metadata"],
            {
                "run_id": "run-1",
                "purpose": "continuity_phase_2_h3_opening",
                "content_attempt": 1,
            },
        )

    def test_continuity_opening_prompt_is_strict_state_serialization(self):
        request = Mock(return_value="Mark is beside the window.")
        reduced_state = {
            "environment": {"location": "bedroom"},
            "subjects": {
                "Mark": {
                    "position": "beside the window",
                    "physical_condition": "breathing heavily",
                },
            },
            "ongoing_audio": "room tone",
        }
        future_phase = {
            "beat_text": "Mark grabs a knife and runs outside.",
            "future_beats": ["A storm destroys the bedroom."],
        }

        minimax.request_continuity_opening_state(
            reduced_state,
            future_phase,
            llm_request=request,
        )

        system_prompt = request.call_args.args[0][0]["content"]
        user_prompt = request.call_args.args[0][1]["content"]
        self.assertIn("facts contained in the supplied continuity state", system_prompt)
        self.assertIn("physical or audible state at frame 0", system_prompt)
        self.assertIn("Do not advance time", system_prompt)
        self.assertIn("begin the next beat", system_prompt)
        self.assertIn("future beats as creative context", system_prompt)
        self.assertIn("Do not introduce props", system_prompt)
        self.assertIn("injuries", system_prompt)
        self.assertIn("environmental changes", system_prompt)
        self.assertIn("spatial relationships", system_prompt)
        self.assertIn("dramatic or narrative commentary", system_prompt)
        self.assertIn("absent or unknown, omit it", system_prompt)
        self.assertIn('"breathing heavily"', user_prompt)
        self.assertIn('"room tone"', user_prompt)
        self.assertNotIn(json.dumps(future_phase, ensure_ascii=False, indent=2), user_prompt)
        self.assertNotIn("grabs a knife", user_prompt)
        self.assertNotIn("destroys the bedroom", user_prompt)

    def test_combined_continuity_retries_invalid_json_with_attempt_metadata(self):
        request = Mock(side_effect=["not json", {"camera": "wide shot"}])

        with patch(
            "minimax._parse_continuity_json_result",
            side_effect=[ValueError("malformed continuity JSON"), {"camera": "wide shot"}],
        ), patch("minimax._print_continuity_phase_result"):
            result = minimax.request_combined_continuity(
                "PROMPT",
                {},
                llm_request=request,
                history_metadata={"run_id": "run-1"},
                content_attempts=2,
                defer_opening=True,
            )

        self.assertEqual(result["reduced_state"], {"camera": "wide shot"})
        self.assertEqual(
            [call.kwargs["history_metadata"]["content_attempt"] for call in request.call_args_list],
            [1, 2],
        )
        self.assertIn(
            "previous response was not usable JSON",
            request.call_args_list[1].args[0][1]["content"],
        )

    def test_continuity_opening_call_overrides_phase_metadata(self):
        request = Mock(return_value="A concise opening.")

        result = minimax.request_continuity_opening_state(
            {"camera": "wide shot"},
            {"phase_number": 3},
            llm_request=request,
            history_metadata={"purpose": "wrong-purpose", "segment": 4},
        )

        self.assertEqual(result, "A concise opening.")
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["response_format"], None)
        self.assertEqual(kwargs["temperature"], 0.10)
        self.assertEqual(kwargs["top_p"], 0.90)
        self.assertEqual(kwargs["max_tokens"], 2000)
        self.assertEqual(
            kwargs["history_metadata"],
            {
                "purpose": "continuity_phase_2_h3_opening",
                "segment": 4,
                "content_attempt": 1,
            },
        )

    def test_structured_continuity_sends_latest_prompt_to_updater_and_validator(self):
        request = Mock(side_effect=[
            {"subjects": {"Mark": {"position": "at the door"}}},
            {"valid": True, "issues": []},
        ])

        result = minimax.request_structured_continuity_state(
            [(7, {
                "detailed_description": "At 00:05, Mark reaches the door.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            })],
            committed_state(),
            SUBJECTS,
            llm_request=request,
            history_metadata={"run_id": "run-1"},
            active_beat_text="Mark reaches the door.",
        )

        self.assertEqual(result["subjects"]["Mark"]["position"], "at the door")
        self.assertEqual(request.call_count, 2)
        updater_prompt = request.call_args_list[0].args[0][1]["content"]
        validator_prompt = request.call_args_list[1].args[0][1]["content"]
        self.assertIn("CURRENT SEGMENT\n7", updater_prompt)
        self.assertIn("FINAL-MOMENT EXCERPT", updater_prompt)
        self.assertIn("Mark reaches the door.", updater_prompt)
        self.assertIn("COMMITTED STATE", validator_prompt)
        self.assertIn("CANDIDATE STATE", validator_prompt)
        self.assertIn("FINAL CLEANED H3 PROMPT", validator_prompt)
        self.assertEqual(
            request.call_args_list[0].kwargs["history_metadata"],
            {"run_id": "run-1", "content_attempt": 1},
        )
        self.assertEqual(
            request.call_args_list[1].kwargs["history_metadata"],
            {
                "run_id": "run-1",
                "purpose": "continuity_state_validation",
                "content_attempt": 1,
            },
        )


class LLMSamplingRoutingTests(unittest.TestCase):
    @patch("minimax.generate_random_llm_seed", return_value=42)
    @patch("minimax.requests.post")
    def test_beat_generation_explicit_sampling_beats_formatter_defaults(
        self,
        post,
        _random_seed,
    ):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"ok\": true}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "test"}],
            response_format=None,
            history_metadata={"purpose": "beat_generation"},
            **minimax.BEAT_LLM_SAMPLING_PARAMETERS,
        )

        self.assertEqual(result, {"ok": True})
        request_json = post.call_args.kwargs["json"]
        for name, value in minimax.BEAT_LLM_SAMPLING_PARAMETERS.items():
            self.assertEqual(request_json[name], value)
        self.assertEqual(
            minimax.BEAT_LLM_SAMPLING_PARAMETERS["repeat_penalty"],
            1.15,
        )
        self.assertEqual(
            minimax.BEAT_LLM_SAMPLING_PARAMETERS["min_p"],
            0.05,
        )
        self.assertEqual(
            minimax.BEAT_LLM_SAMPLING_PARAMETERS["top_k"],
            20,
        )
        self.assertEqual(
            minimax.BEAT_LLM_SAMPLING_PARAMETERS["seed"],
            42,
        )
        self.assertEqual(request_json["top_k"], 20)
        self.assertEqual(request_json["min_p"], 0.05)
        _random_seed.assert_not_called()

    @patch("minimax.generate_random_llm_seed", return_value=777)
    @patch("minimax.requests.post")
    def test_arc_explicit_sampling_uses_deterministic_profile(
        self,
        post,
        _random_seed,
    ):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"ok\": true}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "plan"}],
            response_format=None,
            history_metadata={"purpose": "macro_arc_create"},
            **minimax.ARC_LLM_SAMPLING_PARAMETERS,
        )

        self.assertEqual(result, {"ok": True})
        request_json = post.call_args.kwargs["json"]
        for name, value in minimax.ARC_LLM_SAMPLING_PARAMETERS.items():
            self.assertEqual(request_json[name], value)
        _random_seed.assert_not_called()

    @patch("minimax.generate_random_llm_seed", return_value=42)
    @patch("minimax.requests.post")
    def test_ask_llm_clamps_completion_to_local_context(self, post, _random_seed):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"ok\": true}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        messages = [{"role": "user", "content": "short request"}]
        minimax.ask_llm(messages, response_format=None, max_tokens=8000)

        request_json = post.call_args.kwargs["json"]
        expected_available = (
            minimax.LLM_CONTEXT_TOKEN_BUDGET
            - minimax.LLM_CONTEXT_SAFETY_TOKENS
            - minimax.estimate_message_tokens(messages)
        )
        self.assertEqual(request_json["max_tokens"], expected_available)
        self.assertLess(request_json["max_tokens"], 8000)

    @patch("minimax.requests.post")
    def test_ask_llm_rejects_input_that_leaves_no_completion_room(self, post):
        oversized = "x" * (
            minimax.LLM_CONTEXT_TOKEN_BUDGET
            * int(minimax.CHARS_PER_TOKEN_ESTIMATE + 1)
        )
        with self.assertRaisesRegex(RuntimeError, "Simplify the stage prompt"):
            minimax.ask_llm(
                [{"role": "user", "content": oversized}],
                response_format=None,
            )
        post.assert_not_called()

    @patch("minimax.requests.post")
    def test_unrelated_http_400_does_not_drop_response_format(self, post):
        response = Mock()
        response.status_code = 400
        response.text = '{"error":{"message":"No models loaded."}}'
        response.raise_for_status.side_effect = minimax.requests.HTTPError("400")
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "test"}],
            response_format={"type": "json_object"},
            max_retries=1,
            retry_delay=0,
        )

        self.assertEqual(result, "")
        self.assertEqual(post.call_count, 1)
        self.assertIn("response_format", post.call_args.kwargs["json"])

    @patch("minimax.requests.post")
    def test_schema_specific_http_400_retries_without_response_format(self, post):
        rejected = Mock()
        rejected.status_code = 400
        rejected.text = (
            '{"error":{"message":"response_format json_schema is unsupported"}}'
        )
        rejected.raise_for_status.side_effect = minimax.requests.HTTPError("400")

        accepted = Mock()
        accepted.status_code = 200
        accepted.text = ""
        accepted.raise_for_status = Mock()
        accepted.json.return_value = {
            "choices": [
                {
                    "message": {"content": '{"ok": true}'},
                    "finish_reason": "stop",
                }
            ]
        }
        post.side_effect = [rejected, accepted]

        result = minimax.ask_llm(
            [{"role": "user", "content": "test"}],
            response_format={"type": "json_object"},
            max_retries=1,
            retry_delay=0,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(post.call_count, 2)
        self.assertIn(
            "response_format",
            post.call_args_list[0].kwargs["json"],
        )
        self.assertNotIn(
            "response_format",
            post.call_args_list[1].kwargs["json"],
        )

    @patch("minimax.generate_random_llm_seed", return_value=999)
    @patch("minimax.requests.post")
    def test_beat_validation_remains_pinned_to_benchmark_sampling(
        self,
        post,
        _random_seed,
    ):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"valid\": true, \"issue\": \"\"}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        minimax.ask_llm(
            [{"role": "user", "content": "validate"}],
            response_format=None,
            history_metadata={"purpose": "beat_validation"},
            temperature=0.99,
            repeat_penalty=0.5,
        )

        request_json = post.call_args.kwargs["json"]
        self.assertEqual(
            request_json["temperature"],
            minimax.MISTRAL_24B_SETTINGS["temperature"],
        )
        self.assertEqual(
            request_json["repeat_penalty"],
            minimax.MISTRAL_24B_SETTINGS["repeat_penalty"],
        )
        self.assertEqual(request_json["seed"], minimax.BENCHMARK_SEED)
        self.assertNotIn("thinking", request_json)
        self.assertNotIn("chat_template", request_json)
        self.assertNotIn("jinja", request_json)
        self.assertNotIn("chat_template_kwargs", request_json)


    @patch("minimax.requests.post")
    def test_qwen_beat_validation_transport_matches_benchmark(self, post):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"valid\": true, \"issue\": \"\"}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response
        original = minimax.ACTIVE_FORMATTER
        try:
            minimax.configure_formatter("qwen")
            result = minimax.ask_llm(
                [{"role": "user", "content": "validate"}],
                response_format=None,
                history_metadata={"purpose": "beat_validation"},
            )
            self.assertEqual(result, {"valid": True, "issue": ""})
            request_json = post.call_args.kwargs["json"]
            self.assertEqual(
                request_json["chat_template_kwargs"],
                {"enable_thinking": False},
            )
            self.assertNotIn("thinking", request_json)
            self.assertNotIn("chat_template", request_json)
            self.assertNotIn("jinja", request_json)
        finally:
            minimax.configure_formatter(
                "qwen" if isinstance(original, minimax.QwenFormatter) else "mistral"
            )


    def test_beat_validation_profile_follows_active_model(self):
        original = minimax.ACTIVE_FORMATTER
        try:
            minimax.configure_formatter("mistral")
            mistral_settings = minimax._active_beat_validation_settings()
            self.assertFalse(mistral_settings["user_prompt_only"])
            self.assertEqual(
                mistral_settings["repeat_penalty"],
                minimax.MISTRAL_24B_SETTINGS["repeat_penalty"],
            )

            minimax.configure_formatter("qwen")
            qwen_settings = minimax._active_beat_validation_settings()
            self.assertTrue(qwen_settings["user_prompt_only"])
            self.assertEqual(
                qwen_settings["repeat_penalty"],
                minimax.QWEN38_27B_SETTINGS["repeat_penalty"],
            )

            messages = minimax.build_beat_validation_messages(
                previous_final_beat="Amy equips her weapons.",
                current_state=minimax.new_beat_canonical_state(),
                beat_job="Amy kills attacking zombies.",
                next_beat_job="Amy kills more attacking zombies.",
                candidate_beat=(
                    "Amy kills attacking zombies until the last zombie falls dead."
                ),
                settings=qwen_settings,
            )
            self.assertEqual(messages[0]["content"], "")
            self.assertIn(
                "You validate one candidate story beat.",
                messages[1]["content"],
            )
        finally:
            minimax.configure_formatter(
                "qwen" if isinstance(original, minimax.QwenFormatter) else "mistral"
            )

class DirectorRawSceneCompletionTests(unittest.TestCase):
    def test_completion_prompt_requires_named_beneficiaries_and_final_result(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "The cook serves breakfast to Mira and Jon.",
            "The cook hands breakfast to Mira while Jon waits.",
        )
        prompt = messages[1]["content"]
        self.assertIn("every named beneficiary", prompt)
        self.assertIn("required result must already be true", prompt)
        self.assertIn("still in progress", prompt)

    def test_completion_parser_normalizes_valid_issue(self):
        self.assertEqual(
            minimax.parse_director_raw_scene_completion(
                {"valid": True, "issue": "ignored"}
            ),
            {"valid": True, "issue": ""},
        )
        self.assertEqual(
            minimax.parse_director_raw_scene_completion(
                {"valid": False, "issue": "  Amber never receives breakfast.  "}
            ),
            {
                "valid": False,
                "issue": "Amber never receives breakfast.",
            },
        )


class DirectorPromptCallContractTests(unittest.TestCase):
    def test_director_allows_only_controlled_local_staging(self):
        rules = minimax.build_director_rules(
            8,
            4,
            1,
            SUBJECTS,
            2,
        )

        self.assertIn("LOCAL STAGING", rules)
        self.assertIn(
            "A finite action in CURRENT BEAT is NOT complete merely because RAW SCENE "
            "shows the subject performing it",
            rules,
        )
        self.assertIn(
            "beat_complete=true` requires each named beneficiary to visibly receive "
            "or participate in the completed result",
            rules,
        )
        self.assertIn(
            "visibly stop, set down, close, or otherwise settle it before the handoff",
            rules,
        )
        self.assertIn('"finite_activity_complete": true', rules)
        self.assertIn('"named_beneficiaries_complete": true', rules)
        self.assertIn('"activity_tools_settled": true', rules)
        self.assertIn(
            "Set `beat_complete` true only when all three completion checks above are true",
            rules,
        )
        self.assertIn(
            "Local staging may not invent consequential persistent changes",
            rules,
        )
        self.assertIn(
            "assign it a simple functional stable label formed from its role/type "
            "plus a number",
            rules,
        )
        self.assertIn(
            "Do not assign Subject-style labels to crowds, collective groups",
            rules,
        )
        self.assertIn("NEXT BEAT is a forbidden boundary", rules)
        self.assertIn(
            'Use the canonical timestamp syntax exactly: "At 00:ss.mmm,"',
            rules,
        )
        self.assertIn("NO arbitrary maximum timestamp count", rules)
        self.assertNotIn("Create between", rules)
        self.assertNotIn("At 00:ss.mmm seconds", rules)

    def test_director_response_schema_carries_completion_contract(self):
        schema = minimax.DIRECTOR_RAW_SCENE_RESPONSE_FORMAT[
            "json_schema"
        ]["schema"]
        properties = schema["properties"]
        self.assertIn(
            "natural visible endpoint",
            properties["raw_scene"]["description"],
        )
        self.assertIn(
            "every finite activity",
            properties["finite_activity_complete"]["description"],
        )
        self.assertIn(
            "every named person",
            properties["named_beneficiaries_complete"]["description"],
        )
        self.assertIn(
            "tools/appliances used only for a completed finite activity",
            properties["activity_tools_settled"]["description"],
        )
        self.assertIn(
            "finite_activity_complete",
            properties["beat_complete"]["description"],
        )
        self.assertEqual(
            schema["required"],
            [
                "raw_scene",
                "finite_activity_complete",
                "named_beneficiaries_complete",
                "activity_tools_settled",
                "beat_complete",
            ],
        )

    def test_formatter_music_rule_matches_locked_gold_modes(self):
        initial = minimax.build_h3_formatter_messages(
            "At 00:00.000, Amy cooks breakfast.",
            "T2VA",
            8,
            conditioning_mode="initial",
        )
        continuation = minimax.build_h3_formatter_messages(
            "At 00:00.000, Amy runs.",
            "T2VA",
            8,
            continuity_summary="Amy is in the kitchen.",
            conditioning_mode="continuation",
        )

        self.assertIn(
            "Choose a minimal scene-appropriate non-diegetic underscore",
            initial[1]["content"],
        )
        self.assertIn(
            "non_diegetic_music MUST begin exactly with "
            "'continues from <Video 1>.'",
            continuation[1]["content"],
        )
        self.assertIn(
            "non_diegetic_music is the formatter's one allowed creative "
            "finishing choice",
            initial[0]["content"],
        )

    def test_previous_visible_subjects_resolve_plain_names_for_video_origin(self):
        definitions = (
            "<Subject 1> is Amy, a woman.\n"
            "<Subject 2> is Will, a 10-year-old boy.\n"
            "<Subject 3> is Amber, a 14-year-old girl."
        )
        recent = [(
            1,
            {
                "detailed_description": (
                    "[Shot 1] Amy stands by the stove while Will and Amber sit "
                    "at the kitchen table."
                )
            },
        )]
        self.assertEqual(
            minimax.extract_previous_visible_subject_ids(
                recent,
                2,
                definitions,
            ),
            {1, 2, 3},
        )

    def test_director_dialogue_uses_canonical_h3_form_and_detector_handles_quotes(self):
        rules = minimax.build_director_rules(
            8,
            4,
            1,
            "<Subject 1> is Amy, a woman.",
            2,
        )
        self.assertIn(
            "Amy (S1) says <d>[English]The eggs are ready.</d>",
            rules,
        )
        self.assertIn(
            "Do NOT put spoken words in bare single/double quotation marks",
            rules,
        )
        self.assertTrue(
            minimax._h3_contains_spoken_dialogue(
                "Amy asks, 'Who wants eggs?'"
            )
        )
        self.assertEqual(
            minimax.format_h3_spoken_dialogue_constraint(
                "Amy asks, 'Who wants eggs?'"
            ),
            "",
        )

    def test_first_two_director_prompts_require_beat_clothing(self):
        clothing_requirement = (
            "Any clothing specified in the beat must be part of the response."
        )
        director_rules = minimax.build_director_rules(
            12,
            6,
            2,
            SUBJECTS,
            2,
        )
        formatter_messages = minimax.build_h3_formatter_messages(
            "Mark enters wearing a red coat.",
            "T2VA",
            6,
        )

        self.assertIn(clothing_requirement, director_rules)
        self.assertNotIn(clothing_requirement, formatter_messages[0]["content"])
        self.assertIn("Mark enters wearing a red coat.", formatter_messages[1]["content"])

    def test_director_source_is_only_current_assignment(self):
        phase = {
            "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
            "phase_number": 1, "beat_start": 1, "beat_end": 2,
            "required_events": [
                {"beat_number": 1, "event": "Mira serves tea to Oren."},
                {"beat_number": 2, "event": "Oren leaves the tower."},
            ],
        }
        source = minimax.director_assigned_source(phase, 1)
        self.assertEqual(source, "Mira serves tea to Oren.")
        self.assertEqual(minimax.director_assigned_source(phase, 3), "")
        self.assertEqual(minimax.director_assigned_source({}, 1), "")
        messages, _, _ = minimax.build_generation_messages(
            "Director rules.", "Story context.",
            ["Mira makes tea while Oren watches.", "Oren departs."],
            set(), [], 1, 2, 8, 16, current_phase=phase,
        )
        assignment = messages[1]["content"].split(
            "ASSIGNED SOURCE — authoritative work for this segment:\n", 1
        )[1].split("\n\n", 1)[0]
        self.assertEqual(assignment, source)
        check = minimax.build_director_raw_scene_completion_messages(
            "Mira makes tea while Oren watches.", "Mira serves Oren tea.", source
        )
        self.assertIn(source, check[1]["content"])
        self.assertNotIn("leaves the tower", check[1]["content"])

    def test_generation_messages_scope_beats_to_current_phase_and_carry_summary(self):
        phase = {"phase_number": 2, "beat_start": 2, "beat_end": 3}
        rules = minimax.build_director_rules(12, 6, 2, SUBJECTS, 2)

        messages, estimated, recent_count = minimax.build_generation_messages(
            rules,
            "A story.",
            ["Opening", "Door opens", "Room revealed"],
            {1},
            [(1, {"detailed_description": "old scene"})],
            2,
            3,
            6,
            18,
            continuity_summary="Mark is at the door.",
            subject_definitions=SUBJECTS,
            current_phase=phase,
        )

        self.assertGreater(estimated, 0)
        self.assertEqual(recent_count, 0)
        user_content = messages[1]["content"]
        self.assertIn(json.dumps(phase, ensure_ascii=False, indent=2), user_content)
        self.assertIn(
            "CURRENT BEAT — EXECUTE ONLY THIS:\n2. Door opens",
            user_content,
        )
        self.assertIn(
            "NEXT BEAT — BOUNDARY ONLY, DO NOT INCLUDE ANY PART OF IT:\n"
            "3. Room revealed",
            user_content,
        )
        self.assertNotIn("1. Opening", user_content)
        self.assertNotIn("BEATS:", user_content)
        self.assertIn("CONTINUITY STATE:", user_content)
        self.assertIn("Mark is at the door.", user_content)

    def test_generation_messages_include_only_current_and_next_beat(self):
        phase = {"phase_number": 1, "beat_start": 1, "beat_end": 4}
        rules = minimax.build_director_rules(24, 6, 4, SUBJECTS, 2)

        messages, _, _ = minimax.build_generation_messages(
            rules,
            "A story.",
            ["Opening", "Door opens", "Room revealed", "Leaves room"],
            {1},
            [],
            2,
            4,
            6,
            24,
            subject_definitions=SUBJECTS,
            current_phase=phase,
        )

        user_content = messages[1]["content"]
        self.assertIn(
            "CURRENT BEAT — EXECUTE ONLY THIS:\n2. Door opens",
            user_content,
        )
        self.assertIn(
            "NEXT BEAT — BOUNDARY ONLY, DO NOT INCLUDE ANY PART OF IT:\n"
            "3. Room revealed",
            user_content,
        )
        self.assertNotIn("1. Opening", user_content)
        self.assertNotIn("4. Leaves room", user_content)
        self.assertNotIn("BEATS:", user_content)

    def test_phase_beats_text_returns_current_and_next_separately(self):
        self.assertEqual(
            minimax._phase_beats_text(
                ["Opening", "Door opens", "Room revealed", "Leaves room"],
                {"phase_number": 1},
                2,
            ),
            ("2. Door opens", "3. Room revealed"),
        )

    def test_phase_beats_text_handles_first_and_final_beats(self):
        beats = ["Opening", "Door opens", "Room revealed"]

        self.assertEqual(
            minimax._phase_beats_text(beats, None, 1),
            ("1. Opening", "2. Door opens"),
        )
        self.assertEqual(
            minimax._phase_beats_text(beats, None, 3),
            ("3. Room revealed", "N/A"),
        )

    def test_phase_beats_text_handles_empty_and_out_of_range_beats(self):
        self.assertEqual(
            minimax._phase_beats_text([], None, 2),
            ("N/A", "N/A"),
        )
        self.assertEqual(
            minimax._phase_beats_text(["Only beat"], None, 99),
            ("1. Only beat", "N/A"),
        )

    def test_recent_dialogue_exclusions_are_added_to_generation_prompt(self):
        rules = minimax.build_director_rules(30, 6, 5, SUBJECTS, 5)

        messages, _, _ = minimax.build_generation_messages(
            rules,
            "A story.",
            ["The next beat"],
            set(),
            [],
            5,
            5,
            6,
            30,
            subject_definitions=SUBJECTS,
            dialogue_exclusions=["  We must leave now!  "],
        )

        user_content = messages[1]["content"]
        self.assertIn(
            "RECENT SPOKEN SENTENCE EXCLUSIONS (previous 5 segments)",
            user_content,
        )
        self.assertIn("- We must leave now!", user_content)

        formatter_messages = minimax.build_h3_formatter_messages(
            "Mark crosses the room.",
            "T2VA",
            6,
            dialogue_exclusions=["We must leave now!"],
        )
        self.assertIn("We must leave now!", formatter_messages[1]["content"])

    def test_phrase_exclusions_are_added_to_raw_scene_prompt(self):
        rules = minimax.build_director_rules(30, 6, 5, SUBJECTS, 5)

        messages, _, _ = minimax.build_generation_messages(
            rules,
            "A story.",
            ["The next beat"],
            set(),
            [],
            5,
            5,
            6,
            30,
            subject_definitions=SUBJECTS,
            phrase_exclusions=["  forbidden phrase  ", "Art"],
        )

        user_content = messages[1]["content"]
        self.assertIn("WORDS AND PHRASES NOT ALLOWED IN BEATS", user_content)
        self.assertIn(
            'Do not use any of the following words or phrases in any beat.',
            user_content,
        )
        self.assertIn('- "forbidden phrase"', user_content)
        self.assertIn('- "Art"', user_content)

    def test_beat_generation_requires_observable_finite_endpoints(self):
        phase = {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "required_end_state": "Breakfast is finished.",
            "required_events": [
                {
                    "id": "E1",
                    "event": "Amy is cooking breakfast for Will and Amber.",
                    "beat_number": 1,
                }
            ],
        }
        messages = minimax.build_beat_generation_messages(
            "Amy is cooking breakfast for Will and Amber.",
            1,
            macro_arc={"phases": [phase]},
            current_phase=phase,
        )
        user_content = messages[1]["content"]
        normalized = " ".join(user_content.split())
        self.assertIn("Complete each required event visibly in its beat", normalized)
        self.assertIn(
            "For a finite activity, show a visible transition: include the assigned "
            "activity itself, then show it finishing",
            normalized,
        )
        self.assertIn(
            "Do not output only the activity underway or only its after-state",
            normalized,
        )
        self.assertIn(
            "If an activity or result is for a person or group, keep them as "
            "beneficiaries rather than spectators",
            normalized,
        )
        self.assertIn(
            "Merely watching the work is not enough unless watching/listening is "
            "itself the intended result",
            normalized,
        )
        self.assertIn(
            "same repeated/ongoing process to adjacent beats",
            normalized,
        )
        self.assertIn(
            "Do not say last, final, every, all, finished",
            normalized,
        )
        response_format = minimax.build_beats_response_format(1, beat_start=1)
        beat_text_description = (
            response_format["json_schema"]["schema"]["properties"]["beats"]
            ["items"]["properties"]["beat_text"]["description"]
        )
        self.assertIn("activity itself", beat_text_description)
        self.assertIn("visible completion endpoint", beat_text_description)
        self.assertIn("same sentence", beat_text_description)
        self.assertNotIn("CURRENT PHASE", normalized)
        self.assertNotIn("NEXT PHASE", normalized)

    def test_minimal_beat_generation_keeps_defined_subjects(self):
        phase = {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "required_events": [
                {
                    "id": "E1",
                    "event": "Amy serves breakfast to Will.",
                    "beat_number": 1,
                }
            ],
        }
        subjects = "<Subject 1> is Amy.\n<Subject 2> is Will."
        messages = minimax.build_beat_generation_messages(
            "Amy serves breakfast to Will.",
            1,
            subject_information=subjects,
            macro_arc={"phases": [phase]},
            current_phase=phase,
        )
        user_content = messages[1]["content"]
        self.assertIn("DEFINED SUBJECTS:", user_content)
        compact_subjects = minimax._format_beat_arc_subject_names(subjects)
        self.assertIn(compact_subjects, user_content)
        self.assertNotIn("is Amy", user_content)
        minimax.verify_subjects_in_beat_messages(messages, compact_subjects)

    def test_arc_validation_subject_guard_matches_compact_prompt(self):
        subjects = (
            "<Subject 1> is Amy, a woman shown in <Picture 1>.\n"
            "<Subject 2> is Will, a 10-year-old boy.\n"
            "<Subject 3> is Amber, a 14-year-old girl."
        )
        arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 1,
                    "narrative_purpose": "Baseline.",
                    "broad_progression": "Amy cooks breakfast.",
                    "characters_introduced": [],
                    "location": "Kitchen",
                    "required_events": [
                        {
                            "id": "E1",
                            "event": "Amy cooks breakfast.",
                            "beat_number": 1,
                        }
                    ],
                }
            ]
        }
        messages = minimax.build_macro_arc_validation_messages(
            "Amy cooks breakfast.",
            arc,
            subject_information=subjects,
        )
        compact_subjects = minimax._format_beat_arc_subject_names(subjects)
        self.assertEqual(
            compact_subjects,
            "<Subject 1> = Amy; <Subject 2> = Will; <Subject 3> = Amber",
        )
        self.assertIn(compact_subjects, messages[1]["content"])
        self.assertNotIn(subjects, messages[1]["content"])
        minimax.verify_subjects_in_beat_messages(messages, compact_subjects)

    def test_phrase_exclusions_are_added_to_beat_generation_prompt(self):
        phase = {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 2,
            "required_end_state": "The action is complete.",
        }
        messages = minimax.build_beat_generation_messages(
            "A story.",
            2,
            macro_arc={"phases": [phase]},
            current_phase=phase,
            phrase_exclusions=["forbidden phrase", "Art"],
        )

        user_content = messages[1]["content"]
        self.assertIn("WORDS AND PHRASES NOT ALLOWED IN BEATS", user_content)
        self.assertIn(
            "Do not use any of the following words or phrases in any beat.",
            user_content,
        )
        self.assertIn('- "forbidden phrase"', user_content)
        self.assertIn('- "Art"', user_content)

    def test_phrase_exclusions_are_added_to_story_arc_prompt(self):
        messages = minimax.build_beat_arc_plan_messages(
            "A story.",
            5,
            phrase_exclusions=["forbidden phrase"],
        )

        user_content = messages[1]["content"]
        self.assertIn("WORDS AND PHRASES NOT ALLOWED IN BEATS", user_content)
        self.assertIn('- "forbidden phrase"', user_content)

    def test_phrase_exclusions_are_added_to_h3_formatter_prompt(self):
        messages = minimax.build_h3_formatter_messages(
            "Mark crosses the room.",
            "T2VA",
            6,
            phrase_exclusions=["forbidden phrase"],
        )

        user_content = messages[1]["content"]
        self.assertIn("WORDS AND PHRASES NOT ALLOWED IN DIRECTOR OUTPUT", user_content)
        self.assertIn('- "forbidden phrase"', user_content)

    def test_request_segment_llm_passes_bundle_context_to_h3_formatter(self):
        request = Mock(side_effect=[
            {
                "raw_scene": (
                    "At 00:00.000 seconds, Mark crosses the room.\n"
                    "End continuity state: Mark stands across the room."
                ),
                "beat_complete": True,
            },
            {
                "detailed_description": (
                    "[Shot 1] At 00:00.000 seconds, Mark crosses the room."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
        ])
        bundle = {
            "segment": 2,
            "active_beat_id": 2,
            "current_duration": 4.5,
            "conditioning_mode": "clean_refresh",
            "opening_state": "Mark starts beside the window.",
            "messages": [{"role": "user", "content": "Director input."}],
            "opening_state_sha256": "hash-2",
            "dialogue_exclusions": ["We must leave now!"],
            "phrase_exclusions": ["forbidden phrase"],
        }

        with patch("minimax.ask_llm", request):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-1",
                {"source_sha256": "source-1"},
            )

        self.assertEqual(payload["h3_mode"], "I2VA")
        formatter_user = request.call_args_list[1].args[0][1]["content"]
        self.assertIn("MODE: I2VA", formatter_user)
        self.assertIn("DURATION: 4.5 seconds", formatter_user)
        self.assertIn("Mark starts beside the window.", formatter_user)
        self.assertIn("Mark crosses the room.", formatter_user)
        self.assertIn("We must leave now!", formatter_user)
        self.assertIn('"forbidden phrase"', formatter_user)
        self.assertIn(
            "AUTHORITATIVE OPENING STATE:\nMark starts beside the window.",
            formatter_user,
        )
        minimax._verify_authoritative_opening_state_handoff(
            request.call_args_list[1].args[0],
            "Mark starts beside the window.",
            2,
        )
        self.assertEqual(
            request.call_args_list[0].kwargs["response_format"],
            minimax.DIRECTOR_RAW_SCENE_RESPONSE_FORMAT,
        )
        self.assertEqual(
            request.call_args_list[1].kwargs["response_format"],
            minimax.H3_FORMATTER_RESPONSE_FORMAT,
        )
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["director_raw_scene", "director_h3_formatter"],
        )
        self.assertEqual(
            request.call_args_list[0].kwargs["history_metadata"]["conditioning_mode"],
            "clean_refresh",
        )
        self.assertEqual(
            request.call_args_list[1].kwargs["history_metadata"]["h3_mode"],
            "I2VA",
        )

    def test_request_segment_llm_retries_missing_end_continuity_state(self):
        request = Mock(side_effect=[
            {
                "raw_scene": "At 00:00.000 seconds, Mark crosses the room.",
                "beat_complete": True,
            },
            {
                "raw_scene": (
                    "At 00:00.000 seconds, Mark crosses the room.\n"
                    "End continuity state: Mark stands across the room."
                ),
                "beat_complete": True,
            },
            {
                "detailed_description": (
                    "[Shot 1] At 00:00.000 seconds, Mark crosses the room."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
        ])
        bundle = {
            "segment": 1,
            "active_beat_id": 1,
            "current_duration": 4,
            "conditioning_mode": "continuation",
            "opening_state": "",
            "messages": [{"role": "user", "content": "Director input."}],
            "opening_state_sha256": "hash-1",
            "dialogue_exclusions": [],
            "phrase_exclusions": [],
        }

        with patch("minimax.ask_llm", request):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-1",
                {"source_sha256": "source-1"},
            )

        self.assertEqual(request.call_count, 3)
        retry_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn("RAW SCENE STRUCTURE ERROR", retry_user)
        self.assertIn("End continuity state", retry_user)
        self.assertTrue(payload["request1_result"]["beat_complete"])
        self.assertIn(
            "End continuity state: Mark stands across the room.",
            payload["raw_scene"],
        )

    def test_request_segment_llm_retries_failed_completion_check(self):
        request = Mock(side_effect=[
            {
                "raw_scene": (
                    "At 00:00.000, Amy cooks breakfast.\n"
                    "End continuity state: Amy remains at the stove."
                ),
                "finite_activity_complete": True,
                "named_beneficiaries_complete": False,
                "activity_tools_settled": False,
                "beat_complete": True,
            },
            {
                "raw_scene": (
                    "At 00:00.000, Amy cooks breakfast.\n"
                    "At 00:02.000, Amy serves Will and Amber.\n"
                    "At 00:03.500, Amy turns off the stove and sets down the pan.\n"
                    "End continuity state: Amy stands beside Will and Amber with "
                    "breakfast served and the stove off."
                ),
                "finite_activity_complete": True,
                "named_beneficiaries_complete": True,
                "activity_tools_settled": True,
                "beat_complete": True,
            },
            {"valid": True, "issue": ""},
            {
                "subject_genders": {},
                "detailed_description": (
                    "[Shot 1] At 00:00.000, Amy cooks breakfast. "
                    "At 00:02.000, Amy serves Will and Amber. "
                    "At 00:03.500, Amy turns off the stove and sets down the pan."
                ),
                "overall_soundscape": "Kitchen sounds.",
                "non_diegetic_music": "Quiet underscore.",
            },
        ])
        bundle = {
            "segment": 1,
            "active_beat_id": 1,
            "current_beat_text": "Amy cooks breakfast for Will and Amber.",
            "current_duration": 4,
            "conditioning_mode": "initial",
            "opening_state": "",
            "subject_definitions": (
                "<Subject 1> is Amy.\n"
                "<Subject 2> is Will.\n"
                "<Subject 3> is Amber."
            ),
            "messages": [{"role": "user", "content": "Director input."}],
            "opening_state_sha256": "hash-1",
            "dialogue_exclusions": [],
            "phrase_exclusions": [],
        }

        with patch("minimax.ask_llm", request):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-1",
                {"source_sha256": "source-1"},
            )

        self.assertEqual(request.call_count, 4)
        retry_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn("REQUEST 1 COMPLETION ERROR", retry_user)
        self.assertIn("named beneficiary requirement", retry_user)
        self.assertIn("tool/appliance", retry_user)
        self.assertTrue(payload["request1_result"]["finite_activity_complete"])
        self.assertTrue(payload["request1_result"]["named_beneficiaries_complete"])
        self.assertTrue(payload["request1_result"]["activity_tools_settled"])
        self.assertTrue(payload["request1_result"]["beat_complete"])

    def test_independent_completion_rejection_retries_before_formatting(self):
        scene = "At 00:00.000, Mira serves tea.\nEnd continuity state: Tea is served."
        request = Mock(side_effect=[
            {"raw_scene": scene, "beat_complete": True},
            {"valid": False, "issue": "Oren has not received tea."},
            {"raw_scene": scene, "beat_complete": True},
            {"valid": True, "issue": ""},
            {"detailed_description": "[Shot 1] At 00:00.000, Mira serves tea.",
             "overall_soundscape": "Cups clink.", "non_diegetic_music": "N/A"},
        ])
        bundle = {
            "segment": 1, "active_beat_id": 1, "current_duration": 4,
            "current_beat_text": "Mira serves tea to Oren.",
            "assigned_source": "Mira makes tea for Oren.",
            "conditioning_mode": "initial", "opening_state": "",
            "messages": [{"role": "user", "content": "Direct the current beat."}],
        }
        with patch("minimax.ask_llm", request):
            minimax.request_segment_llm(bundle, [], "test", {})
        purposes = [c.kwargs["history_metadata"]["purpose"]
                    for c in request.call_args_list]
        self.assertEqual(purposes, [
            "director_raw_scene", "director_raw_scene_completion",
            "director_raw_scene", "director_raw_scene_completion",
            "director_h3_formatter",
        ])
        self.assertIn("Oren has not received tea.",
                      request.call_args_list[2].args[0][-1]["content"])
        self.assertTrue(request.call_args_list[1].kwargs[
            "history_metadata"]["use_beat_validation_settings"])
        self.assertIn("Mira makes tea for Oren.",
                      request.call_args_list[1].args[0][1]["content"])


    def test_request_segment_llm_retries_when_named_subjects_are_dropped(self):
        subjects = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Will, a 10-year-old boy.\n"
            "<Subject 3> is Amber, a 14-year-old girl."
        )
        request = Mock(side_effect=[
            {
                "raw_scene": (
                    "At 00:00.000, Amy opens the basement door.\n"
                    "End continuity state: Amy stands beside the open basement door."
                ),
                "beat_complete": True,
            },
            {
                "raw_scene": (
                    "At 00:00.000, Amy opens the basement door.\n"
                    "At 00:02.000, Will and Amber step out beside Amy.\n"
                    "End continuity state: Amy stands with Will and Amber outside the basement."
                ),
                "beat_complete": True,
            },
            {"valid": True, "issue": ""},
            {
                "subject_genders": {},
                "detailed_description": (
                    "[Shot 1] At 00:00.000, Amy opens the basement door. "
                    "At 00:02.000, Will and Amber step out beside Amy."
                ),
                "overall_soundscape": "Door opening and footsteps.",
                "non_diegetic_music": "Quiet underscore.",
            },
        ])
        bundle = {
            "segment": 8,
            "active_beat_id": 8,
            "current_beat_text": "Amy opens the basement door and lets Will and Amber out.",
            "current_duration": 4,
            "conditioning_mode": "continuation",
            "opening_state": "",
            "subject_definitions": subjects,
            "messages": [{"role": "user", "content": "Director input."}],
            "opening_state_sha256": "hash-8",
            "dialogue_exclusions": [],
            "phrase_exclusions": [],
        }

        with patch("minimax.ask_llm", request):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-8",
                {"source_sha256": "source-8"},
            )

        self.assertEqual(request.call_count, 4)
        retry_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn("RAW SCENE dropped named Subject(s)", retry_user)
        self.assertIn("Will", retry_user)
        self.assertIn("Amber", retry_user)
        self.assertIn("Will and Amber step out", payload["raw_scene"])

    def test_director_raw_scene_structure_requires_trailing_end_state(self):
        self.assertTrue(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000 seconds, Mark crosses the room."
            )
        )
        self.assertTrue(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000 seconds, Mark crosses the room.\n"
                "End continuity state:"
            )
        )
        self.assertEqual(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000 seconds, Mark crosses the room.\n"
                "End continuity state: Mark stands across the room."
            ),
            [],
        )

    def test_h3_formatter_prompt_is_a_conservative_raw_scene_translator(self):
        messages = minimax.build_h3_formatter_messages(
            (
                "At 00:00.000 seconds, Amy raises the pistol.\n"
                "At 00:02.000 seconds, Amy fires and the zombie collapses."
            ),
            "T2VA",
            5,
            continuity_summary=(
                "Amy is in the hallway holding a pistol. The children are in the basement."
            ),
        )
        system_prompt = " ".join(messages[0]["content"].split())

        self.assertIn("RAW SCENE is authoritative", system_prompt)
        self.assertIn("Preserve every visible action and its order", system_prompt)
        self.assertIn("Do not invent actions, props, people", system_prompt)
        self.assertIn("Do not copy unrelated continuity facts", system_prompt)
        self.assertIn("overall_soundscape", system_prompt)
        self.assertIn("non_diegetic_music", system_prompt)
        self.assertNotIn("Video Prompt Writing Guide", system_prompt)
        self.assertNotIn("Motion type", system_prompt)
        self.assertNotIn("Construction Example", system_prompt)
        self.assertEqual(system_prompt.count("Live-action, cinematic"), 1)

        user_prompt = messages[1]["content"]
        self.assertIn("AUTHORITATIVE OPENING STATE:", user_prompt)
        self.assertIn("The children are in the basement.", user_prompt)
        self.assertIn("At 00:02.000 seconds, Amy fires", user_prompt)

    def test_request_two_opening_instructions_follow_conditioning_mode(self):
        raw_scene = (
            "At 00:00.000 seconds, the camera tracks behind Amy as she runs "
            "down the hallway."
        )
        continuation = minimax.build_h3_formatter_messages(
            raw_scene,
            "T2VA",
            6,
            continuity_summary="Mark remains on the street.",
            conditioning_mode="continuation",
        )[1]["content"]
        clean_refresh = minimax.build_h3_formatter_messages(
            "Mark continues down the street.",
            "I2VA",
            6,
            continuity_summary="Mark remains on the street.",
            conditioning_mode="clean_refresh",
        )[1]["content"]
        initial = minimax.build_h3_formatter_messages(
            "Mark enters the room.",
            "T2VA",
            6,
            conditioning_mode="initial",
        )[1]["content"]

        self.assertIn("<Video 1>", continuation)
        self.assertIn(
            "Preserve every camera movement explicitly present in RAW SCENE",
            continuation,
        )
        self.assertIn(
            "including camera movement beginning at 00:00.000",
            continuation,
        )
        self.assertIn(
            "Keep it at its original timestamp and do not move it later",
            continuation,
        )
        self.assertIn(raw_scene, continuation)
        self.assertNotIn("not a camera movement", continuation)
        self.assertNotIn("Camera movement may occur later", continuation)
        self.assertIn("supplied first frame", clean_refresh)
        self.assertIn("CLEAN-REFRESH OPENING RULE", clean_refresh)
        self.assertNotIn(
            "<Video 1> already establish the opening composition",
            clean_refresh,
        )
        self.assertNotIn("<Video 1>", initial)
        self.assertNotIn("OPENING RULE", initial)

        opening = minimax.format_authoritative_opening_state(
            minimax.continuity_state_for_registry(SUBJECTS),
            SUBJECTS,
            conditioning_mode="clean_refresh",
        )
        self.assertIn("supplied first frame establishes", opening)
        self.assertNotIn("<Video 1> is the immediately preceding", opening)
        self.assertNotIn("final observable state of <Video 1>", opening)

        final_prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Mark looks toward the street.",
                "overall_soundscape": "City hum.",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=2,
            conditioning_mode="clean_refresh",
        )
        self.assertTrue(
            final_prompt.split("detailed_description: ", 1)[1].startswith(
                "[Shot 1] The opening composition is established by "
                "the supplied first frame."
            )
        )

    def test_h3_formatter_contract_preserves_schema_and_audio_constraints(self):
        messages = minimax.build_h3_formatter_messages(
            "Mark crosses the room.",
            "T2VA",
            6,
        )
        system_prompt = messages[0]["content"]
        schema = (
            '"subject_genders": {},',
            '"detailed_description": "[Shot 1] ...",',
            '"overall_soundscape": "...",',
            '"non_diegetic_music": "..."',
        )

        positions = [system_prompt.index(item) for item in schema]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("only sounds supported by RAW SCENE", system_prompt)
        self.assertIn(
            "non_diegetic_music is the formatter's one allowed creative "
            "finishing choice",
            system_prompt,
        )
        self.assertIn(
            "Use `N/A` only when silence/no score is explicitly required",
            system_prompt,
        )
        self.assertIn("Do not advance the", system_prompt)

    def test_nonfinal_story_segment_protects_the_handoff_frame(self):
        rules = minimax.build_director_rules(
            12,
            6,
            2,
            SUBJECTS,
            1,
            is_final_story_segment=False,
        )
        formatter_messages = minimax.build_h3_formatter_messages(
            "Mark walks onward.",
            "T2VA",
            6,
            is_final_story_segment=False,
        )

        for prompt in (rules, formatter_messages[0]["content"]):
            self.assertIn("NONFINAL STORY SEGMENT", prompt)
            self.assertIn("cut to black", prompt)
            self.assertIn("cut to white", prompt)
            self.assertIn("fade to black", prompt)
            self.assertIn("fade to white", prompt)
            self.assertIn("empty transitional frame", prompt)
            self.assertIn("title card", prompt)
            self.assertIn("credits", prompt)
            self.assertIn("abstract transition", prompt)
            self.assertIn("full lens obstruction", prompt)
            self.assertIn("completely obscured lens", prompt)
            self.assertIn("deliberate blackout", prompt)
            self.assertIn(
                "assigned beat explicitly requires that exact visual event",
                prompt,
            )

    def test_final_story_segment_has_no_handoff_frame_prohibition(self):
        rules = minimax.build_director_rules(
            12,
            6,
            2,
            SUBJECTS,
            2,
            is_final_story_segment=True,
        )
        formatter_system = minimax.build_h3_formatter_messages(
            "The assigned beat ends in a blackout.",
            "T2VA",
            6,
            is_final_story_segment=True,
        )[0]["content"]

        for prompt in (rules, formatter_system):
            self.assertIn("This is the final story segment", prompt)
            self.assertNotIn("NONFINAL STORY SEGMENT", prompt)
            self.assertNotIn("do not invent or use a cut to black", prompt)
            self.assertIn("explicitly assigned blackout", prompt)

    def test_nonfinal_assigned_blackout_is_preserved_by_the_prompt_contract(self):
        messages = minimax.build_h3_formatter_messages(
            "The assigned beat explicitly requires a deliberate blackout.",
            "T2VA",
            6,
            is_final_story_segment=False,
        )

        self.assertIn(
            "assigned beat explicitly requires that exact visual event",
            messages[0]["content"],
        )
        self.assertIn("deliberate blackout", messages[1]["content"])

    def test_h3_continuation_opener_is_not_duplicated(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 1] Live-action, cinematic, continues from <Video 1>. "
                    "Mark crosses the room."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "continues from <Video 1>. Quiet underscore.",
            },
            "<Subject 1> is Mark, referenced in <Picture 1>.",
            segment_number=2,
            conditioning_mode="continuation",
        )

        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:", 1
        )[0]
        self.assertEqual(description.count("continues from <Video 1>."), 1)
        self.assertIn("Mark crosses the room.", description)

    def test_h3_prompt_initial_and_continuation_have_distinct_contracts(self):
        result = {
            "detailed_description": "[Shot 4] Mark waits silently.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        definitions = (
            "<Subject 1> is Mark, referenced in <Picture 1>.\n"
            "<Subject 2> is Amy, female, continued from <Video 1>."
        )

        initial = minimax.build_h3_prompt(
            result,
            definitions,
            segment_number=1,
            conditioning_mode="initial",
        )
        continuation = minimax.build_h3_prompt(
            result,
            definitions,
            previous_state="Mark remains at the door.",
            segment_number=2,
            conditioning_mode="continuation",
        )

        self.assertIn("<Subject 1> is Mark, referenced in <Picture 1>.", initial)
        self.assertNotIn("continued from <Video 1>", initial)
        self.assertNotIn("retention_analysis:", continuation)
        self.assertNotIn("unresolved spatial position", continuation)
        self.assertNotIn("Mark remains at the door.", continuation)
        self.assertTrue(
            continuation.split("detailed_description: ", 1)[1].startswith(
                "[Shot 1] Live-action, cinematic, continues from <Video 1>."
            )
        )
        self.assertIn("SPOKEN DIALOGUE: None.", continuation)


if __name__ == "__main__":
    unittest.main()
