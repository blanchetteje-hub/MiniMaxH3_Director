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
        self.assertIn("reduced continuity state", messages[0]["content"])
        self.assertIn("MANDATORY OUTPUT CONTRACT", messages[0]["content"])
        self.assertIn("FINAL H3 PROMPT", messages[1]["content"])
        self.assertIn("CONTINUITY OUTPUT CONTRACT (MANDATORY)", messages[1]["content"])
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

        with patch("minimax._print_continuity_phase_result"):
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


class DirectorPromptCallContractTests(unittest.TestCase):
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
        self.assertIn("2. Door opens", user_content)
        self.assertIn("3. Room revealed", user_content)
        self.assertNotIn("1. Opening", user_content)
        self.assertIn("CONTINUITY STATE:", user_content)
        self.assertIn("Mark is at the door.", user_content)

    def test_request_segment_llm_passes_opening_state_only_to_h3_formatter(self):
        request = Mock(side_effect=[
            {"raw_scene": "Mark crosses the room."},
            {
                "detailed_description": "[Shot 1] Mark crosses the room.",
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
        self.assertIsNone(request.call_args_list[0].kwargs["response_format"])
        self.assertIsNone(request.call_args_list[1].kwargs["response_format"])
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

    def test_h3_formatter_prompt_requires_visible_beat_execution(self):
        messages = minimax.build_h3_formatter_messages(
            "The werewolf emerges, chases Amy, and gains ground.",
            "T2VA",
            5,
            continuity_summary="Amy stands at the edge of the forest.",
        )
        system_prompt = " ".join(messages[0]["content"].split())

        self.assertIn("assigned beat's primary action must", system_prompt)
        self.assertIn("continuity once at the beginning of Shot 1", system_prompt)
        self.assertIn("Do not repeat the opening continuity", system_prompt)
        self.assertIn("segments 5 seconds or shorter, prefer", system_prompt)
        self.assertIn("the werewolf emerge, Amy flee", system_prompt)
        self.assertIn("distance between them decrease", system_prompt)

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
            conditioning_mode="latent_continuation",
        )

        self.assertIn("<Subject 1> is Mark, referenced in <Picture 1>.", initial)
        self.assertNotIn("continued from <Video 1>", initial)
        self.assertIn("retention_analysis:", continuation)
        self.assertIn(
            "<Subject 1> (appears in [Shot 1]): fully_preserved - Preserve the "
            "Subject's visible configuration from the final state of <Video 1>",
            continuation,
        )
        self.assertIn(
            "<Video 1> (continuation starting point): fully_preserved - Preserve "
            "the final visible physical state, environment, spatial relationships, "
            "wardrobe condition, and subject configuration as the opening state of "
            "[Shot 1].",
            continuation,
        )
        self.assertNotIn("STRUCTURAL CONTINUITY:", continuation)
        self.assertIn("Mark remains at the door.", continuation)
        self.assertTrue(
            continuation.split("detailed_description: ", 1)[1].startswith(
                "[Shot 1] Continuing directly from the final state of <Video 1>,"
            )
        )
        self.assertIn("SPOKEN DIALOGUE: None.", continuation)


if __name__ == "__main__":
    unittest.main()
