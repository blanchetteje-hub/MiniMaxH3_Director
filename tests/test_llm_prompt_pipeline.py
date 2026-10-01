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
                "PROMPT", {}, llm_request=request,
                history_metadata={"run_id": "run-1"},
                content_attempts=2, defer_opening=True,
            )
        self.assertEqual(result["reduced_state"]["camera"], "wide shot")
        self.assertEqual(result["reduced_state"]["subjects"], {})
        self.assertEqual(result["reduced_state"]["environment"], {})
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
    def test_beat_generation_uses_creative_sampling_and_reasoning_profile(
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
            temperature=0,
            top_p=0.5,
            top_k=40,
            min_p=0,
            repeat_penalty=1.0,
        )

        self.assertEqual(result, {"ok": True})
        request_json = post.call_args.kwargs["json"]
        for name, value in minimax.CREATIVE_LLM_SAMPLING_PARAMETERS.items():
            self.assertEqual(request_json[name], value)
        self.assertEqual(request_json["reasoning_effort"], "high")
        self.assertEqual(request_json["thinking_budget_tokens"], 1024)
        self.assertEqual(
            request_json["reasoning_budget_message"],
            ". Enough thinking, now answer.",
        )
        self.assertEqual(
            request_json["chat_template_kwargs"],
            {"enable_thinking": True},
        )
        self.assertNotIn("thinking", request_json)
        self.assertNotIn("chat_template", request_json)
        self.assertNotIn("jinja", request_json)
        _random_seed.assert_not_called()

    @patch("minimax.generate_random_llm_seed", return_value=777)
    @patch("minimax.requests.post")
    def test_arc_create_uses_same_creative_profile(
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
        )

        self.assertEqual(result, {"ok": True})
        request_json = post.call_args.kwargs["json"]
        for name, value in minimax.CREATIVE_LLM_SAMPLING_PARAMETERS.items():
            self.assertEqual(request_json[name], value)
        self.assertEqual(request_json["reasoning_effort"], "high")
        self.assertEqual(request_json["thinking_budget_tokens"], 1024)
        _random_seed.assert_not_called()

    @patch("minimax.requests.post")
    def test_extractor_forces_temperature_zero_even_if_caller_passes_creative_profile(
        self,
        post,
    ):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "{\"state_effects\": []}"},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "extract"}],
            response_format=None,
            history_metadata={"purpose": "source_unit_state_effects"},
            **minimax.ARC_LLM_SAMPLING_PARAMETERS,
        )

        self.assertEqual(result, {"state_effects": []})
        request_json = post.call_args.kwargs["json"]
        self.assertEqual(request_json["temperature"], 0)
        self.assertEqual(request_json["seed"], minimax.BENCHMARK_SEED)
        self.assertEqual(request_json["reasoning_effort"], "low")
        self.assertEqual(request_json["thinking_budget_tokens"], 128)
        self.assertEqual(
            request_json["reasoning_budget_message"],
            ". Enough thinking, now answer.",
        )
        self.assertEqual(
            request_json["chat_template_kwargs"],
            {"enable_thinking": True},
        )


    @patch("minimax.generate_random_llm_seed", return_value=42)
    @patch("minimax.requests.post")
    def test_ask_llm_respects_requested_completion_when_it_fits_context(
        self, post, _random_seed
    ):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}]
        }
        post.return_value = response
        messages = [{"role": "user", "content": "short request"}]
        minimax.ask_llm(messages, response_format=None, max_tokens=8000)
        request_json = post.call_args.kwargs["json"]
        self.assertEqual(request_json["max_tokens"], 8000)
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
        self.assertEqual(
            request_json["chat_template_kwargs"],
            {"enable_thinking": True},
        )
        self.assertEqual(request_json["reasoning_effort"], "low")
        self.assertEqual(request_json["thinking_budget_tokens"], 128)
        self.assertEqual(
            request_json["reasoning_budget_message"],
            ". Enough thinking, now answer.",
        )


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
                {"enable_thinking": True},
            )
            self.assertEqual(request_json["reasoning_effort"], "low")
            self.assertEqual(request_json["thinking_budget_tokens"], 128)
            self.assertEqual(
                request_json["reasoning_budget_message"],
                ". Enough thinking, now answer.",
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
    def test_source_completion_preserves_participant_scope(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy gets Will and Amber into the basement and locks the door.",
            "Will and Amber step inside; Amy follows them in and locks the door behind all three.",
            assigned_source="Amy gets Will and Amber into the basement and locks the door.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Preserve participant scope", prompt)
        self.assertIn("Only subjects explicitly named by SOURCE as crossing/entering/exiting a barrier may cross it", prompt)

    def test_append_bundle_includes_source_authorized_state(self):
        phase = {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 2,
            "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
            "required_events": [
                {
                    "id": "E1",
                    "event": "Will and Amber enter the basement and are contained there.",
                    "beat_number": 1,
                    "state_effects": [
                        {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                        {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
                    ],
                },
                {
                    "id": "E2",
                    "event": "Amy prepares for the next task.",
                    "beat_number": 2,
                    "state_effects": [],
                },
            ],
            "source_text": "Will and Amber enter the basement. Amy prepares for the next task.",
        }
        arc = {"phases": [phase], "planner": {"type": "source_span"}}
        state_text = minimax.format_source_authorized_opening_state(arc, 2)
        self.assertIn("SOURCE-AUTHORIZED CURRENT STATE", state_text)
        self.assertIn("Will", state_text)
        self.assertIn("Amber", state_text)
        self.assertIn("basement", state_text)


    def test_director_prompt_keeps_state_advisory_and_beat_authoritative(self):
        rules = minimax.build_director_rules(
            64, 8, 8, "", 2,
            conditioning_mode="continuation",
            is_final_story_segment=False,
        )
        normalized = " ".join(rules.split())
        self.assertIn("CURRENT BEAT is the scene to stage", normalized)
        self.assertIn("broad or generic continuity summary conflicts", normalized)
        self.assertIn("CURRENT BEAT wins", normalized)
        self.assertNotIn("Only explicitly authorized subjects may cross a barrier", normalized)
    def test_completion_prompt_protects_authoritative_persistent_state(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy defeats one attacker with the katana.",
            "Amy defeats the attacker, then sets the katana on the floor.",
            assigned_source="Amy defeats one attacker with the katana.",
            authoritative_opening_state=(
                "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict) "
                '{"characters":{"Amy":{"held_objects":["pistol","katana"]}}}'
            ),
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("AUTHORITATIVE OPENING STATE", prompt)
        self.assertIn("Preserve persistent facts already true", prompt)
        self.assertIn("held/equipped items", prompt)
        self.assertIn("Reject dropping, losing, freeing, unlocking, removing", prompt)


    def test_director_prompt_is_minimal_scene_contract(self):
        rules = minimax.build_director_rules(
            64, 8, 8, "", 3,
            conditioning_mode="continuation",
            is_final_story_segment=False,
        )
        normalized = " ".join(rules.split())
        self.assertIn("concrete visible/audible action", normalized)
        self.assertIn("natural physical staging", normalized)
        self.assertIn("Camera movement may clarify action", normalized)
        self.assertIn("NEXT BEAT is boundary context only", normalized)
        self.assertNotIn("Do not invent persistent changes", normalized)
    def test_completion_prompt_disallows_implicit_mover_barrier_crossing(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Mara guides Eli and Noor into the shelter and locks the door.",
            "Mara guides Eli and Noor into the shelter, locks the door, then steps inside with them.",
            assigned_source="Mara guides Eli and Noor into the shelter and locks the door.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Only subjects explicitly named by SOURCE as crossing/entering/exiting a barrier may cross it", prompt)
        self.assertIn("does NOT authorize the mover/helper to follow", prompt)

    def test_completion_prompt_uses_typed_effects_as_persistent_end_state_authority(self):
        effects = [
            {"op": "set_location", "entity": "Eli", "value": "shelter"},
            {"op": "set_location", "entity": "Noor", "value": "shelter"},
            {"op": "set_containment", "entity": "Eli", "container": "shelter", "value": "contained"},
            {"op": "set_containment", "entity": "Noor", "container": "shelter", "value": "contained"},
        ]
        messages = minimax.build_director_raw_scene_completion_messages(
            "Mara guides Eli and Noor into the shelter and locks the door.",
            "Mara follows Eli and Noor into the shelter and locks the door behind all three.",
            assigned_source="Mara guides Eli and Noor into the shelter and locks the door.",
            authoritative_opening_state="Mara starts outside the shelter with Eli and Noor.",
            assigned_state_effects=effects,
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("ASSIGNED TYPED END STATE", prompt)
        self.assertIn('"entity":"Eli"', prompt)
        self.assertIn('"entity":"Noor"', prompt)
        self.assertIn("Require matching typed effects for durable changes", prompt)
        self.assertIn("do not give the mover/helper that same persistent location/containment change", prompt)

    def test_completion_prompt_allows_room_to_room_staging_inside_canonical_location(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy fights zombies in the house.",
            "Amy moves from the kitchen into the hallway and fights a zombie.",
            assigned_source="Amy fights zombies in the house.",
            authoritative_opening_state=(
                "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n"
                '{"characters":{"Amy":{"location":"home"}}}'
            ),
            assigned_state_effects=[],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("coarse story geography/container state", prompt)
        self.assertIn("movement between rooms, hallways, or subareas", prompt)
        self.assertIn("does NOT require another set_location effect", prompt)

    def test_beat_validator_does_not_require_effect_for_new_incidental_target(self):
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy is armed and ready.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy kills a zombie that attacks her.",
            next_beat_job="Amy keeps fighting.",
            candidate_beat="Amy decapitates the attacking zombie with her katana.",
            assigned_state_effects=[],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn(
            "NEVER reject because such a newly introduced incidental entity is injured, killed",
            prompt,
        )
        self.assertIn(
            "Do not invent missing-effect obligations for new incidental entities",
            prompt,
        )

    def test_beat_closed_boundary_contract_lists_contained_occupants(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Will": {
                "containment": "contained",
                "contained_in": "basement",
                "location": "basement",
                "accessible": False,
            },
            "Amber": {
                "containment": "contained",
                "contained_in": "basement",
                "location": "basement",
                "accessible": False,
            },
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        contracts = minimax.build_beat_closed_boundary_contracts(state, [])
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["destination"], "basement")
        self.assertEqual(contracts[0]["occupants"], ["Will", "Amber"])

    def test_beat_destination_presence_parser_is_strict(self):
        self.assertEqual(
            minimax.parse_beat_destination_presence_result(
                {"relation": "AT_DESTINATION"}
            ),
            "AT_DESTINATION",
        )
        with self.assertRaises(ValueError):
            minimax.parse_beat_destination_presence_result(
                {"relation": "INSIDE"}
            )
        with self.assertRaises(ValueError):
            minimax.parse_beat_destination_presence_result(
                {"relation": "AT_DESTINATION", "valid": False}
            )

    def test_beat_destination_presence_prompt_checks_any_point(self):
        messages = minimax.build_beat_destination_presence_messages(
            "basement",
            "Amy",
            "Amy enters the basement, retrieves a pistol, then returns upstairs.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("physically at/inside DESTINATION at any point", prompt)
        self.assertIn("even if the subject later leaves", prompt)
        self.assertIn("Do not decide whether the placement is allowed", prompt)

    def test_beat_destination_presence_contract_tracks_outside_named_subject(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Amy": {
                "location": "home",
                "containment": "free",
                "contained_in": None,
                "accessible": True,
            },
            "Will": {
                "location": "basement",
                "containment": "contained",
                "contained_in": "basement",
                "accessible": False,
            },
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        contracts = minimax.build_beat_destination_presence_contracts(
            state,
            [],
            "Amy retrieves her weapons from a closet in the basement.",
        )
        self.assertEqual(
            contracts,
            [
                {
                    "destination": "basement",
                    "subject": "Amy",
                    "barrier": "basement door",
                }
            ],
        )

    def test_beat_destination_presence_contract_accepts_event_wrapped_effects(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Amy": {
                "location": "home",
                "containment": "free",
                "contained_in": None,
                "accessible": True,
            },
            "Will": {
                "location": "basement",
                "containment": "contained",
                "contained_in": "basement",
                "accessible": False,
            },
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        wrapped_effects = [{"id": "E6", "state_effects": []}]
        contracts = minimax.build_beat_destination_presence_contracts(
            state,
            wrapped_effects,
            "Amy fights zombies inside the basement.",
        )
        self.assertEqual(
            contracts,
            [
                {
                    "destination": "basement",
                    "subject": "Amy",
                    "barrier": "basement door",
                }
            ],
        )

        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy waits outside.",
            current_state=state,
            beat_job="Amy fights zombies.",
            next_beat_job=None,
            candidate_beat="Amy fights zombies inside the basement.",
            assigned_state_effects=wrapped_effects,
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("PYTHON-OWNED CLOSED BOUNDARIES", prompt)
        self.assertIn("basement door protects 'basement'", prompt)

    def test_beat_destination_presence_contract_skips_subject_already_inside(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Will": {
                "location": "basement",
                "containment": "contained",
                "contained_in": "basement",
                "accessible": False,
            },
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        self.assertEqual(
            minimax.build_beat_destination_presence_contracts(
                state,
                [],
                "Will waits inside the basement.",
            ),
            [],
        )

    def test_beat_validator_forbids_retrieving_interior_prop_across_closed_boundary(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Amy": {"location": "home"},
            "Will": {
                "containment": "contained",
                "contained_in": "basement",
                "location": "basement",
                "accessible": False,
            },
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy locks Will in the basement.",
            current_state=state,
            beat_job="Amy retrieves and equips her hidden weapons.",
            next_beat_job="Amy fights attackers.",
            candidate_beat="Amy retrieves her pistol and katana from a closet in the basement.",
            assigned_state_effects=[],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("retrieve/use an object located inside", prompt)
        self.assertIn("Do not stage a required action/object inside the protected destination", prompt)
        self.assertIn("prop, target, or other interior content", prompt)

    def test_beat_validator_forbids_cross_boundary_contact_with_contained_occupant(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Will": {
                "containment": "contained",
                "contained_in": "basement",
                "location": "basement",
                "accessible": False,
            }
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Will is secured in the basement.",
            current_state=state,
            beat_job="Amy defeats another attacker.",
            next_beat_job="Amy keeps fighting.",
            candidate_beat="An attacker reaches for Will's arm before Amy stops it.",
            assigned_state_effects=[],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Known contained occupants: Will", prompt)
        self.assertIn("cannot reach, grab, bite, strike", prompt)
        self.assertIn("physically interact across the boundary", prompt)

    def test_beat_validator_includes_closed_boundary_contract(self):
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Will": {
                "location": "basement",
                "containment": "contained",
                "contained_in": "basement",
                "accessible": False,
            }
        }
        state["environment"]["barriers"] = {
            "door": {"status": "locked"}
        }
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Will is secured in the basement.",
            current_state=state,
            beat_job="Amy defeats another attacker.",
            next_beat_job="Amy keeps fighting.",
            candidate_beat="Amy strikes an attacker and its head falls onto the basement floor.",
            assigned_state_effects=[],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("PYTHON-OWNED CLOSED BOUNDARIES", prompt)
        self.assertIn("basement door protects 'basement'", prompt)
        self.assertIn("object, body part", prompt)
        self.assertIn("may cross into or out of that destination", prompt)


    def test_beat_generation_does_not_inject_closed_boundary_contract(self):
        phase = {
            "required_events": [
                {
                    "id": "E1", "beat_number": 1,
                    "event": "Will enters the basement and the door is locked.",
                    "state_effects": [
                        {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                        {"op": "set_barrier_state", "entity": "door", "value": "locked"},
                    ],
                },
                {
                    "id": "E2", "beat_number": 2,
                    "event": "Amy defeats another attacker.",
                    "depends_on": ["E1"], "state_effects": [],
                },
            ]
        }
        arc = {"planner": {"type": "source_span"}, "phases": [phase]}
        messages = minimax.build_beat_generation_messages(
            "Will enters the basement. Amy defeats another attacker.",
            2, batch_start=1, batch_end=2, current_phase=phase, macro_arc=arc,
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertNotIn("CLOSED BARRIERS AT START", prompt)
        self.assertIn("Will enters the basement and the door is locked.", prompt)
        self.assertIn("people on opposite sides cannot touch, pass objects", prompt)
    def test_beat_validator_includes_python_owned_barrier_binding(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
        ]
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy is in the kitchen.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy gets Will and Amber into the basement and locks the door.",
            next_beat_job="Amy retrieves her weapons.",
            candidate_beat="Amy gets Will and Amber into the basement, then locks the kitchen door.",
            assigned_state_effects=effects,
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("PYTHON-OWNED BARRIER BINDING", prompt)
        self.assertIn("'door' is the boundary of 'basement'", prompt)
        self.assertIn("Do not reinterpret it as an unrelated barrier", prompt)


    def test_beat_generation_does_not_inject_barrier_binding_rules(self):
        phase = {
            "required_events": [{
                "beat_number": 2,
                "event": "Amy gets Will and Amber into the basement and locks the door.",
                "state_effects": [
                    {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                    {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
                    {"op": "set_barrier_state", "entity": "door", "value": "locked"},
                ],
            }]
        }
        messages = minimax.build_beat_generation_messages(
            "Amy protects her children.", 2,
            batch_start=2, batch_end=2, current_phase=phase,
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertNotIn("BARRIER NAME RULES", prompt)
        self.assertIn(
            "Amy gets Will and Amber into the basement and locks the door.",
            prompt,
        )
        self.assertIn("Do not use a different nearby door", prompt)
    def test_barrier_state_prompt_does_not_destroy_retracted_intact_barrier(self):
        messages = minimax.build_director_barrier_state_messages(
            "bulkhead",
            "The intact bulkhead retracts and leaves the corridor open.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("OPEN, not DESTROYED", prompt)
        self.assertIn("retracts", prompt)

    def test_generic_barrier_binds_to_single_containment_destination(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
        ]
        self.assertEqual(
            minimax.build_director_barrier_binding_contract(effects),
            {"entity": "door", "destination": "basement", "state": "locked"},
        )

    def test_barrier_state_contract_uses_active_typed_effect(self):
        effects = [
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
            {"op": "set_location", "entity": "Mara", "value": "hall"},
        ]
        self.assertEqual(
            minimax.build_director_barrier_state_contracts(effects),
            [{"barrier": "door", "expected": "LOCKED", "source_state": "locked"}],
        )

    def test_barrier_state_contract_maps_unlocked_to_open(self):
        effects = [
            {"op": "set_barrier_state", "entity": "hatch", "value": "unlocked"},
        ]
        self.assertEqual(
            minimax.build_director_barrier_state_contracts(effects),
            [{"barrier": "hatch", "expected": "OPEN", "source_state": "unlocked"}],
        )

    def test_barrier_state_prompt_prioritizes_structural_damage(self):
        messages = minimax.build_director_barrier_state_messages(
            "vault door",
            "The vault door is bent and partly detached, leaving an opening.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("damaged-but-present = BROKEN", prompt)
        self.assertIn("intact-and-passable = OPEN", prompt)
        self.assertIn("Do not decide whether the scene is valid", prompt)

    def test_barrier_state_parser_is_strict(self):
        self.assertEqual(
            minimax.parse_director_barrier_state_observation(
                {"status": "LOCKED"}
            ),
            "LOCKED",
        )
        with self.assertRaises(ValueError):
            minimax.parse_director_barrier_state_observation(
                {"status": "SEALED"}
            )

    def test_closed_boundary_contract_binds_generic_locked_door_to_containment(self):
        opening = (
            "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n"
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"},'
            '"Amber":{"containment":"contained","contained_in":"basement"}},'
            '"environment":{"doors":{},"barriers":{"door":{"status":"locked"}},'
            '"windows":{}}}'
        )
        self.assertEqual(
            minimax.build_director_closed_boundary_contracts(opening, []),
            [
                {
                    "barrier": "basement door",
                    "state": "locked",
                    "destination": "basement",
                }
            ],
        )

    def test_closed_boundary_contract_allows_authorized_release(self):
        opening = (
            "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n"
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}},'
            '"environment":{"doors":{},"barriers":{"door":{"status":"locked"}},'
            '"windows":{}}}'
        )
        effects = [
            {
                "op": "set_containment",
                "entity": "Will",
                "container": "basement",
                "value": "free",
            }
        ]
        self.assertEqual(
            minimax.build_director_closed_boundary_contracts(opening, effects),
            [],
        )

    def test_barrier_traversal_prompt_accepts_protected_destination(self):
        messages = minimax.build_director_barrier_traversal_messages(
            "basement door",
            "The object rolls down the stairs and lands on the basement floor.",
            "basement",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("BOUND BARRIER", prompt)
        self.assertIn("PROTECTED DESTINATION", prompt)
        self.assertIn("basement", prompt)
        self.assertIn("even when the barrier noun is not repeated", prompt)
        self.assertIn("object, body part", prompt)

    def test_closed_boundary_contract_exposes_destination_to_traversal_check(self):
        opening = (
            "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n"
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}},'
            '"environment":{"doors":{},"barriers":{"door":{"status":"locked"}},'
            '"windows":{}}}'
        )
        self.assertEqual(
            minimax.build_director_closed_boundary_contracts(opening, []),
            [
                {
                    "barrier": "basement door",
                    "state": "locked",
                    "destination": "basement",
                }
            ],
        )

    def test_barrier_traversal_prompt_is_extraction_only(self):
        messages = minimax.build_director_barrier_traversal_messages(
            "airlock hatch",
            "The creature comes through the airlock hatch into the cargo bay.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("TRAVERSED", prompt)
        self.assertIn("NOT_TRAVERSED", prompt)
        self.assertIn("UNSPECIFIED", prompt)
        self.assertIn("Do not decide whether crossing is allowed", prompt)
        self.assertNotIn("PROTECTED DESTINATION", prompt)

    def test_barrier_traversal_parser_is_strict(self):
        self.assertEqual(
            minimax.parse_director_barrier_traversal_observation(
                {"status": "TRAVERSED"}
            ),
            "TRAVERSED",
        )
        with self.assertRaises(ValueError):
            minimax.parse_director_barrier_traversal_observation(
                {"status": "CROSSED"}
            )

    def test_generic_barrier_binding_refuses_ambiguous_destinations(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Nia", "container": "vault", "value": "contained"},
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
        ]
        self.assertIsNone(
            minimax.build_director_barrier_binding_contract(effects)
        )

    def test_director_assigned_state_effects_returns_only_active_beat_effects(self):
        phase = {
            "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
            "required_events": [
                {
                    "event": "Eli enters the shelter.",
                    "beat_number": 1,
                    "state_effects": [
                        {"op": "set_location", "entity": "Eli", "value": "shelter"}
                    ],
                },
                {
                    "event": "Mara raises the staff.",
                    "beat_number": 2,
                    "state_effects": [
                        {"op": "set_item_state", "entity": "staff", "owner": "Mara", "value": "held"}
                    ],
                },
            ],
        }
        self.assertEqual(
            minimax.director_assigned_state_effects(phase, 1),
            [{"op": "set_location", "entity": "Eli", "value": "shelter"}],
        )
        self.assertEqual(minimax.director_assigned_state_effects({}, 1), [])

    def test_formatter_rejects_noncanonical_timestamp_syntax(self):
        issues = minimax._validate_director_timestamp_correspondence(
            "At 00:00.000, Amy opens the door.\nAt 00:01.500, Amy steps back.",
            "[00:00.000] Amy opens the door. [00:01.500] Amy steps back.",
        )
        self.assertTrue(issues)
        self.assertIn("canonical syntax", " ".join(issues))

    def test_formatter_canonicalizes_dash_timestamp_syntax(self):
        raw = (
            "At 00:00.000, Amy opens the door.\n"
            "At 00:01.500, Amy steps back."
        )
        formatted = minimax._canonicalize_director_timestamps(
            "At 00:00.000 - Amy opens the door. "
            "At 00:01.500 - Amy steps back."
        )
        self.assertEqual(
            minimax._validate_director_timestamp_correspondence(raw, formatted),
            [],
        )
        self.assertIn("At 00:00.000, Amy", formatted)
        self.assertIn("At 00:01.500, Amy", formatted)

    def test_finite_endpoint_prompt_distinguishes_finite_from_repeated_work(self):
        messages = minimax.build_beat_finite_endpoint_messages(
            "Mara is cooking breakfast for Eli.",
            "Mara is still cooking eggs at the stove.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("COMPLETE", prompt)
        self.assertIn("ONGOING", prompt)
        self.assertIn("NOT_APPLICABLE", prompt)
        self.assertIn("Progressive source wording", prompt)

    def test_finite_endpoint_parser_is_strict(self):
        self.assertEqual(
            minimax.parse_beat_finite_endpoint_result({"status": "COMPLETE"}),
            "COMPLETE",
        )
        with self.assertRaises(ValueError):
            minimax.parse_beat_finite_endpoint_result({"status": "DONE"})


    def test_terminal_target_source_detection_only_requires_nonempty_source(self):
        self.assertTrue(minimax.director_source_has_terminal_action(
            "Mara kills the final creature."
        ))
        self.assertTrue(minimax.director_source_has_terminal_action(
            "Mara wounds the creature and keeps fighting."
        ))
        self.assertFalse(minimax.director_source_has_terminal_action(""))
    def test_terminal_target_parser_accepts_only_known_status(self):
        for status in ("MATCH", "NOT_MATCH", "UNKNOWN"):
            self.assertEqual(
                minimax.parse_director_terminal_target_observation({"status": status}),
                status,
            )
        with self.assertRaises(ValueError):
            minimax.parse_director_terminal_target_observation({"status": "DEAD"})

    def test_terminal_target_prompt_is_extraction_only(self):
        messages = minimax.build_director_terminal_target_messages(
            "zombie", "dead",
            "Amy faces a zombie body and strikes it again.",
            "Amy faces a headless zombie corpse from the prior segment.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("TARGET zombie", prompt)
        self.assertIn("REQUIRED END STATE dead", prompt)
        self.assertIn("OPENING FACTS", prompt)
        self.assertIn("headless zombie corpse from the prior segment", prompt)
        self.assertIn("MATCH = REQUIRED END STATE is already true", prompt)
        self.assertIn("UNKNOWN = facts do not establish either", prompt)
        self.assertIn("Do not infer unstated changes", prompt)
    def test_completion_prompt_requires_unresolved_target_for_terminal_action(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy kills the final zombie.",
            "Amy strikes the already-dead zombie corpse again.",
            assigned_source="Amy kills the final zombie.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("has not already reached that exact terminal result", prompt)
        self.assertIn("Reapplying an already-complete irreversible result", prompt)
        self.assertIn("does not satisfy the source action", prompt)
    def test_director_prompt_does_not_encode_terminal_state_machine(self):
        rules = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            story_segment_ending_rules="",
        )
        normalized = " ".join(rules.split())
        self.assertNotIn("already-dead corpse", normalized)
        self.assertNotIn("terminal target", normalized.casefold())
        self.assertIn("CURRENT BEAT wins", normalized)
    def test_completion_prompt_requires_assigned_action_to_happen_now(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Mara cooks breakfast for Eli.",
            "Mara serves Eli freshly cooked eggs.",
            assigned_source="Mara cooks breakfast for Eli.",
        )
        prompt = messages[1]["content"]
        self.assertIn("must visibly perform that source action in this segment", prompt)
        self.assertIn("existing result or aftermath alone is insufficient", prompt)

    def test_director_timestamp_range_rejects_invalid_segment_time(self):
        self.assertTrue(
            minimax._director_timestamp_range_errors(
                "At 00:200.000, Amy moves.",
                segment_seconds=8,
            )
        )
        self.assertTrue(
            minimax._director_timestamp_range_errors(
                "At 01:00.000, Amy moves.",
                segment_seconds=8,
            )
        )
        self.assertEqual(
            minimax._director_timestamp_range_errors(
                "At 00:07.999, Amy moves.",
                segment_seconds=8,
            ),
            [],
        )

    def test_completion_prompt_preserves_equipped_readiness_items(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Mara uses the staff to block one strike.",
            "Mara blocks the strike, then sets the staff on the floor. End continuity state: Mara is still holding the staff.",
            assigned_source="Mara uses the staff to block one strike.",
            authoritative_opening_state="Mara is holding/equipped with the staff.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Preserve persistent facts already true", prompt)
        self.assertIn("End continuity must agree with the last visible state", prompt)


    def test_director_prompt_does_not_encode_item_carry_modes(self):
        rules = minimax.build_director_rules(
            64, 8, 8, "", 4,
            conditioning_mode="continuation",
            is_final_story_segment=False,
        )
        normalized = " ".join(rules.split())
        self.assertNotIn("HELD means", normalized)
        self.assertNotIn("Preserve held/equipped", normalized)
        self.assertNotIn("holster, discard", normalized)
    def test_completion_prompt_requires_named_beneficiaries_and_final_result(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "The cook serves breakfast to Mira and Jon.",
            "The cook hands breakfast to Mira while Jon waits.",
            assigned_source="The cook serves breakfast to Mira and Jon.",
        )
        prompt = messages[1]["content"]
        self.assertIn("explicit hand-off to named people", prompt)
        self.assertIn("visibly receive, be served, or otherwise gain practical access", prompt)
        self.assertIn("work merely made FOR someone", prompt)

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

    def test_director_uses_baseline_creation_contract(self):
        rules = minimax.build_director_rules(
            8, 4, 1, SUBJECTS, 2,
        )
        normalized = " ".join(rules.split())
        self.assertIn("ASSIGNED SOURCE is the story authority", normalized)
        self.assertIn("CURRENT BEAT is the scene to stage", normalized)
        self.assertIn("Harmless local route or prop details are allowed", normalized)
        self.assertIn('RETURN JSON ONLY {"raw_scene":"..."}', normalized)
        self.assertNotIn("finite_activity_complete", normalized)
        self.assertNotIn("final quarter", normalized)

    def test_director_response_schema_contains_raw_scene_only(self):
        schema = minimax.DIRECTOR_RAW_SCENE_RESPONSE_FORMAT[
            "json_schema"
        ]["schema"]
        self.assertEqual(set(schema["properties"]), {"raw_scene"})
        self.assertEqual(schema["required"], ["raw_scene"])
        self.assertIn(
            "CURRENT BEAT",
            schema["properties"]["raw_scene"]["description"],
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


    def test_director_dialogue_rule_is_minimal_and_detector_handles_quotes(self):
        rules = minimax.build_director_rules(
            8, 4, 1, "<Subject 1> is Amy, a woman.", 2,
        )
        self.assertIn("Short dialogue is allowed", rules)
        self.assertTrue(minimax._h3_contains_spoken_dialogue(
            "Amy asks, 'Who wants eggs?'"
        ))
        self.assertEqual(
            minimax.format_h3_spoken_dialogue_constraint(
                "Amy asks, 'Who wants eggs?'"
            ),
            "",
        )

    def test_director_relies_on_beat_for_clothing_and_formatter_preserves_scene(self):
        director_rules = minimax.build_director_rules(
            12, 6, 2, SUBJECTS, 2,
        )
        formatter_messages = minimax.build_h3_formatter_messages(
            "Mark enters wearing a red coat.", "T2VA", 6,
        )
        self.assertNotIn("Any clothing specified in the beat", director_rules)
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
        self.assertNotIn("PHASE:", user_content)
        self.assertNotIn("STORY:", user_content)
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
            "phase_number": 1, "beat_start": 1, "beat_end": 1,
            "required_end_state": "Breakfast is finished.",
            "required_events": [{
                "id": "E1",
                "event": "Amy is cooking breakfast for Will and Amber.",
                "beat_number": 1,
            }],
        }
        messages = minimax.build_beat_generation_messages(
            "Amy is cooking breakfast for Will and Amber.", 1,
            macro_arc={"phases": [phase]}, current_phase=phase,
        )
        normalized = " ".join(messages[1]["content"].split())
        self.assertIn("Finish a finite task in the same beat", normalized)
        self.assertIn("Show the task happening and then finishing", normalized)
        self.assertIn("do not show only the work in progress or only the after-state", normalized)
        self.assertNotIn("show that person receive or use it", normalized)
        self.assertIn("same repeated/ongoing process", normalized)
        self.assertIn("Do not say last, final, every, all, or finished", normalized)
        response_format = minimax.build_beats_response_format(1, beat_start=1)
        desc = response_format["json_schema"]["schema"]["properties"]["beats"]["items"]["properties"]["beat_text"]["description"]
        self.assertIn("activity itself", desc)
        self.assertIn("visible completion endpoint", desc)
        self.assertIn("same sentence", desc)

    def test_minimal_beat_generation_keeps_defined_subjects(self):
        phase = {
            "phase_number": 1, "beat_start": 1, "beat_end": 1,
            "required_events": [{
                "id": "E1", "event": "Amy serves breakfast to Will.", "beat_number": 1,
            }],
        }
        subjects = "<Subject 1> is Amy.\n<Subject 2> is Will."
        messages = minimax.build_beat_generation_messages(
            "Amy serves breakfast to Will.", 1,
            subject_information=subjects,
            macro_arc={"phases": [phase]}, current_phase=phase,
        )
        user_content = messages[1]["content"]
        self.assertIn("KNOWN SUBJECTS", user_content)
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
                    "At 00:00.000, Mark crosses the room.\n"
                    "End continuity state: Mark stands across the room."
                ),
                "beat_complete": True,
            },
            {
                "detailed_description": (
                    "[Shot 1] At 00:00.000, Mark crosses the room."
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


    def test_request_segment_llm_accepts_missing_end_continuity_state(self):
        request = Mock(side_effect=[
            {"raw_scene": "At 00:00.000, Mark crosses the room."},
            {
                "detailed_description": "[Shot 1] At 00:00.000, Mark crosses the room.",
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

        with patch("minimax.ask_llm", request), patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle, [], "run-1", {"source_sha256": "source-1"}
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(payload["raw_scene"], "At 00:00.000, Mark crosses the room.")

    def test_request_segment_llm_ignores_request1_completion_self_report(self):
        scene = (
            "At 00:00.000, Amy cooks breakfast.\n"
            "End continuity state: Amy remains at the stove."
        )
        request = Mock(side_effect=[
            {
                "raw_scene": scene,
                "finite_activity_complete": False,
                "named_beneficiaries_complete": False,
                "activity_tools_settled": False,
                "beat_complete": False,
            },
            {
                "subject_genders": {},
                "detailed_description": "[Shot 1] At 00:00.000, Amy cooks breakfast.",
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
            "messages": [{"role": "user", "content": "Director input."}],
        }

        with patch("minimax.ask_llm", request), patch("builtins.print"):
            payload = minimax.request_segment_llm(bundle, [], "run-1", {})

        self.assertEqual(request.call_count, 2)
        self.assertEqual(payload["raw_scene"], scene)

    def test_independent_completion_validator_is_not_in_generation_path(self):
        scene = "At 00:00.000, Mira serves tea.\nEnd continuity state: Tea is served."
        request = Mock(side_effect=[
            {"raw_scene": scene},
            {
                "subject_genders": {},
                "detailed_description": "[Shot 1] At 00:00.000, Mira serves tea.",
                "overall_soundscape": "Cups clink.",
                "non_diegetic_music": "N/A",
            },
        ])
        bundle = {
            "segment": 1,
            "active_beat_id": 1,
            "current_duration": 4,
            "current_beat_text": "Mira serves tea to Oren.",
            "assigned_source": "Mira makes tea for Oren.",
            "conditioning_mode": "initial",
            "opening_state": "",
            "messages": [{"role": "user", "content": "Direct the current beat."}],
        }
        with patch("minimax.ask_llm", request), patch("builtins.print"):
            minimax.request_segment_llm(bundle, [], "test", {})
        purposes = [
            call.kwargs["history_metadata"]["purpose"]
            for call in request.call_args_list
        ]
        self.assertEqual(
            purposes,
            ["director_raw_scene", "director_h3_formatter"],
        )

    def test_request_segment_llm_reports_dropped_subjects_without_retrying(self):
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
                )
            },
            {
                "subject_genders": {},
                "detailed_description": "[Shot 1] At 00:00.000, Amy opens the basement door.",
                "overall_soundscape": "Door opening.",
                "non_diegetic_music": "N/A",
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
        }

        with patch("minimax.ask_llm", request), patch("builtins.print") as printed:
            payload = minimax.request_segment_llm(bundle, [], "run-8", {})

        self.assertEqual(request.call_count, 2)
        self.assertIn("Amy opens the basement door", payload["raw_scene"])
        output = "\n".join(
            " ".join(str(arg) for arg in call.args)
            for call in printed.call_args_list
        )
        self.assertIn("non-blocking", output)
        self.assertIn("Will", output)
        self.assertIn("Amber", output)
    def test_director_raw_scene_structure_requires_trailing_end_state(self):
        self.assertTrue(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000, Mark crosses the room."
            )
        )
        self.assertTrue(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000, Mark crosses the room.\n"
                "End continuity state:"
            )
        )
        self.assertEqual(
            minimax._director_raw_scene_structure_errors(
                "At 00:00.000, Mark crosses the room.\n"
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


class RuntimeRecoverySupervisorTests(unittest.TestCase):
    def test_main_fails_fast_for_prompt_generation(self):
        with (
            patch.object(
                minimax.sys,
                "argv",
                ["minimax.py", "8", "64", "0.5", "--test-prompt-generation"],
            ),
            patch(
                "minimax._run_main",
                side_effect=RuntimeError("post-director structural failure"),
            ) as run_main,
            patch("minimax.traceback.print_exc"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "post-director structural failure",
            ):
                minimax.main()

        self.assertEqual(run_main.call_count, 1)

    def test_main_retries_recoverable_failure_from_checkpoint(self):
        with (
            patch(
                "minimax._run_main",
                side_effect=[RuntimeError("recoverable"), "done"],
            ) as run_main,
            patch(
                "minimax._checkpoint_file_signature",
                side_effect=[("before", 1), ("after", 2), ("after", 2)],
            ),
            patch(
                "minimax._checkpoint_recovery_resume_segment",
                return_value=4,
            ),
            patch("minimax.time.sleep"),
        ):
            self.assertEqual(minimax.main(), "done")

        self.assertEqual(run_main.call_count, 2)
        self.assertIsNone(
            run_main.call_args_list[0].kwargs["recovery_resume_segment"]
        )
        self.assertEqual(
            run_main.call_args_list[1].kwargs["recovery_resume_segment"],
            4,
        )

    def test_main_propagates_llm_connection_failure(self):
        with patch(
            "minimax._run_main",
            side_effect=minimax.LLMConnectionError("offline"),
        ):
            with self.assertRaises(minimax.LLMConnectionError):
                minimax.main()

    def test_main_propagates_comfyui_connection_failure(self):
        with patch(
            "minimax._run_main",
            side_effect=minimax.ComfyUIConnectionError("offline"),
        ):
            with self.assertRaises(minimax.ComfyUIConnectionError):
                minimax.main()
