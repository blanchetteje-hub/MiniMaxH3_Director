import json
import os
import tempfile
import unittest
from unittest import mock

import requests

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
        "detailed_description": description,
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


class ComfyHistoryResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class LmStudioIntegrationTests(unittest.TestCase):
    def test_subject_can_use_multiple_picture_references(self):
        definitions = (
            "<Subject 1> is Mark, a man referenced in <Picture 1> and "
            "<Picture 2>."
        )

        registry = minimax.parse_subject_registry(definitions)
        state = minimax.continuity_state_for_registry(definitions)

        self.assertEqual(registry[1]["picture_ids"], [1, 2])
        self.assertEqual(state["subjects"]["Mark"]["picture_ids"], [1, 2])
        opening = minimax.format_authoritative_opening_state(state, definitions)
        self.assertIn(
            "Preserve Mark's identity from <Picture 1> and <Picture 2>",
            opening,
        )

    def test_picture_reference_can_be_shared_by_multiple_subject_definitions(self):
        definitions = (
            "<Subject 1> is Mark, referenced in <Picture 1>.\n"
            "<Subject 2> is Jill, referenced in <Picture 1>."
        )

        registry = minimax.parse_subject_registry(definitions)

        self.assertEqual(registry[1]["picture_ids"], [1])
        self.assertEqual(registry[2]["picture_ids"], [1])

    def test_generation_user_registry_contains_only_subject_mappings(self):
        messages, _, _ = minimax.build_generation_messages(
            director_rules=(
                "SUBJECTS\n"
                "This system text must not be copied.\n"
                "SHOT AND TIMING\n"
                "This section must not be copied."
            ),
            story="A story.",
            beats=[],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=1,
            segment_length=6,
            total_length=6,
            subject_definitions=SUBJECTS,
        )

        user_content = messages[1]["content"]
        registry_start = user_content.index("SUBJECT REGISTRY")
        story_start = user_content.index("SOURCE STORY / CREATIVE BRIEF")
        registry_section = user_content[registry_start:story_start]
        self.assertIn("canonical_name: Mark", registry_section)
        self.assertIn("picture_ids: [1]", registry_section)
        self.assertNotIn("This system text must not be copied", user_content)
        self.assertNotIn("SHOT AND TIMING", registry_section)

    def test_first_frame_instructions_are_added_only_to_segment_one(self):
        result = response("[Shot 1] Mark stands in a room.", [])
        opening = minimax.build_h3_prompt(
            result,
            SUBJECTS,
            segment_number=1,
            ff=True,
        )
        later = minimax.build_h3_prompt(
            result,
            SUBJECTS,
            segment_number=2,
            ff=True,
        )

        self.assertIn(
            "<Picture 1> is the opening-frame reference for the target video.",
            opening,
        )
        self.assertIn(
            "At 00:00.000, the target video should begin by reproducing <Picture 1> "
            "as closely as possible. Preserve the same camera position, framing, "
            "composition, subject pose, facial expression, clothing, lighting, "
            "environment, object positions, and spatial relationships shown in "
            "<Picture 1>.",
            opening,
        )
        integrated_line = opening.split(
            "detailed_description: ",
            1,
        )[1].splitlines()[0]
        self.assertEqual(
            integrated_line,
            "[Shot 1] At 00:00.000, begin with the composition established by "
            "<Picture 1>. The opening frame should visually match <Picture 1> "
            "as closely as possible.",
        )
        self.assertNotIn("\n[Shot 1]", opening)
        self.assertNotIn("opening-frame reference", later)

    def test_h3_prompt_collapses_adjacent_duplicate_picture_tags(self):
        result = response(
            "[Shot 1] A close-up shows Ben <Picture 2> <Picture 2> "
            "<Picture 2> doing something.",
            [],
        )

        prompt = minimax.build_h3_prompt(result, SUBJECTS)
        description = prompt.split("detailed_description: ", 1)[1].splitlines()[0]

        self.assertEqual(description.count("<Picture 2>"), 1)
        self.assertIn("Ben <Picture 2> doing something.", description)

    def test_story_context_preserves_edges_and_bounds_long_source(self):
        story = "OPENING " + ("middle " * 3000) + " ENDING"

        context = minimax.build_story_context(story, max_chars=120)

        self.assertLessEqual(len(context), 200)
        self.assertTrue(context.startswith("CURRENT STORY CONTEXT"))
        self.assertIn("Other source-story material omitted", context)

    def test_bounded_beat_state_exposes_active_and_ordered_lookahead(self):
        beats = [f"Event {number}" for number in range(1, 12)]

        state = minimax.build_bounded_beat_state(beats, {1, 2}, 3)

        self.assertEqual(state["completed_through"], 2)
        self.assertEqual(state["active_beat"], {"id": 3, "text": "Event 3"})
        self.assertEqual(
            [item["id"] for item in state["ordered_lookahead"]],
            [4, 5, 6, 7, 8, 9, 10, 11],
        )
        self.assertEqual(state["beats_remaining"], 9)

    def test_director_beat_contract_maps_beat_one_to_segment_one(self):
        rules = minimax.build_director_rules(
            total_length=12,
            segment_length=6,
            total_segments=2,
            subject_definitions=SUBJECTS,
            segment_number=1,
            beats_enabled=True,
        )
        messages, _, _ = minimax.build_generation_messages(
            director_rules=rules,
            story="A story.",
            beats=["Opening event", "Later event"],
            completed_beat_ids=[],
            recent_results=[],
            current_segment=1,
            total_segments=2,
            segment_length=6,
            total_length=12,
            subject_definitions=SUBJECTS,
        )

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn(
            "The ACTIVE beat ID must equal the current segment number",
            combined,
        )
        self.assertIn("Segment 1 executes Beat 1", combined)
        self.assertIn("Never repeat any beat already completed", combined)
        self.assertIn("one substantial new exchange or", combined)
        self.assertIn("persistent visible alteration", combined)
        self.assertIn("Beat 1: Opening event", combined)

    def test_director_promotes_unregistered_speakers_but_not_visual_roles(self):
        rules = minimax.build_director_rules(
            total_length=12,
            segment_length=6,
            total_segments=2,
            subject_definitions=SUBJECTS,
            segment_number=1,
            beats_enabled=True,
        )

        self.assertIn(
            "Speaker IDs belong only to Subjects and only when they speak",
            rules,
        )
        self.assertIn(
            "If an unregistered role speaks, promote it to a new `<Subject N>`",
            rules,
        )
        self.assertIn("Every `<d>...</d>` block must have", rules)
        self.assertIn(
            "Never put speaker IDs on non-speaking people in purely visual prose",
            rules,
        )
    def test_formatter_context_uses_bounded_later_beats(self):
        beats = [f"Event {number}" for number in range(1, 12)]

        context = minimax.build_ministral_context(
            segment_number=3,
            segment_duration=6.0,
            beats=beats,
            completed_beat_ids={1, 2},
            subject_definitions=SUBJECTS,
            story="Story",
        )

        self.assertEqual(context["current_beat_text"], "Event 3")
        self.assertEqual(context["later_beat_texts"], [
            "Event 4", "Event 5", "Event 6", "Event 7", "Event 8",
            "Event 9", "Event 10", "Event 11",
        ])

    @mock.patch("minimax.requests.get")
    def test_wait_for_completion_exposes_execution_error_details(self, get):
        get.return_value = ComfyHistoryResponse({
            "prompt-id": {
                "status": {
                    "completed": True,
                    "status_str": "error",
                    "messages": [[
                        "execution_error",
                        {
                            "node_id": "42",
                            "exception_type": "OutOfMemoryError",
                            "exception_message": "CUDA out of memory",
                            "traceback": "trace line",
                        },
                    ]],
                },
            }
        })

        with self.assertRaisesRegex(
            minimax.ComfyUIExecutionError,
            "node=42.*OutOfMemoryError.*CUDA out of memory.*trace line",
        ):
            minimax.wait_for_completion("prompt-id", retry_delay=0)

        get.assert_called_once()

    def test_wait_for_completion_times_out_before_polling_when_deadline_expired(self):
        with self.assertRaises(minimax.ComfyUIRenderTimeout):
            minimax.wait_for_completion(
                "prompt-id",
                timeout=0,
                clock=lambda: 1,
            )

    @mock.patch("minimax.requests.post")
    def test_queue_workflow_refreshes_client_id_after_three_guid_failures(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"prompt_id": "reborn-prompt-id"}

        post.side_effect = [
            requests.ConnectionError("ComfyUI cannot connect using GUID old-guid"),
            requests.ConnectionError("ComfyUI cannot connect using GUID old-guid"),
            requests.ConnectionError("ComfyUI cannot connect using GUID old-guid"),
            response,
        ]

        prompt_id = minimax.queue_workflow({"workflow": "test"}, max_retries=4, retry_delay=0)

        self.assertEqual(prompt_id, "reborn-prompt-id")
        self.assertEqual(post.call_count, 4)
        submitted_guids = [call.kwargs["json"]["client_id"] for call in post.call_args_list]
        self.assertEqual(len(set(submitted_guids)), 2)
        self.assertEqual(submitted_guids[:3], [submitted_guids[0]] * 3)
        self.assertNotEqual(submitted_guids[0], submitted_guids[3])

    @mock.patch("minimax.free_vram")
    @mock.patch("minimax.get_video_resolution", return_value=(640, 360))
    @mock.patch("minimax.get_video_path", return_value="segment.mp4")
    @mock.patch("minimax.wait_for_completion")
    @mock.patch("minimax.queue_workflow")
    @mock.patch("minimax.prepare_initial_workflow")
    def test_render_retry_releases_vram_and_lowers_initial_megapixels(
        self,
        prepare,
        queue,
        wait,
        get_path,
        get_resolution,
        free_vram,
    ):
        prepare.side_effect = lambda duration, megapixels, prompt, segment, steps: {
            "megapixels": megapixels
        }
        queue.side_effect = ["prompt-1", "prompt-2", "prompt-3"]
        wait.side_effect = [
            minimax.ComfyUIExecutionError("oom 1"),
            minimax.ComfyUIRenderTimeout("timeout"),
            {"status": {"completed": True, "status_str": "success"}},
        ]

        result = minimax.render_segment_with_retries(
            1,
            6.0,
            0.50,
            "prompt",
            None,
            6,
        )

        self.assertEqual(
            [call.args[1] for call in prepare.call_args_list],
            [0.50, 0.48, 0.46],
        )
        self.assertEqual(free_vram.call_count, 0)
        self.assertEqual(result[1:], ("segment.mp4", 640, 360, 0.46))

    @mock.patch("minimax.free_vram")
    @mock.patch("minimax.prepare_initial_workflow", return_value={})
    @mock.patch("minimax.queue_workflow", return_value="prompt-id")
    @mock.patch(
        "minimax.wait_for_completion",
        side_effect=minimax.ComfyUIExecutionError("persistent OOM"),
    )
    def test_render_retry_stops_after_ten_retries(
        self,
        wait,
        queue,
        prepare,
        free_vram,
    ):
        with self.assertRaisesRegex(RuntimeError, "after 10 retries"):
            minimax.render_segment_with_retries(
                1,
                6.0,
                0.50,
                "prompt",
                None,
                6,
            )

        self.assertEqual(prepare.call_count, 11)
        self.assertEqual(free_vram.call_count, 0)
        self.assertEqual(
            prepare.call_args_list[-1].args[1],
            0.30,
        )

    @mock.patch("minimax.free_vram")
    @mock.patch("minimax.get_video_resolution", return_value=(640, 360))
    @mock.patch("minimax.get_video_path", return_value="segment.mp4")
    @mock.patch("minimax.wait_for_completion")
    @mock.patch("minimax.queue_workflow", side_effect=["prompt-1", "prompt-2"])
    @mock.patch("minimax.prepare_append_workflow", return_value={})
    def test_append_retry_preserves_inherited_resolution(
        self,
        prepare,
        queue,
        wait,
        get_path,
        get_resolution,
        free_vram,
    ):
        wait.side_effect = [
            minimax.ComfyUIExecutionError("oom"),
            {"status": {"completed": True, "status_str": "success"}},
        ]

        result = minimax.render_segment_with_retries(
            2,
            6.0,
            0.50,
            "prompt",
            "previous.mp4",
            6,
        )

        self.assertEqual(prepare.call_count, 2)
        self.assertEqual(result[-1], 0.50)
        self.assertEqual(free_vram.call_count, 0)

    def test_render_start_signal_is_set_before_waiting_for_video(self):
        render_started = minimax.threading.Event()

        def assert_started_before_wait(prompt_id):
            self.assertEqual(prompt_id, "prompt-id")
            self.assertTrue(render_started.is_set())
            return {"status": {"completed": True, "status_str": "success"}}

        with mock.patch(
            "minimax.prepare_initial_workflow",
            return_value={},
        ), mock.patch(
            "minimax.queue_workflow",
            return_value="prompt-id",
        ), mock.patch(
            "minimax.wait_for_completion",
            side_effect=assert_started_before_wait,
        ), mock.patch(
            "minimax.get_video_path",
            return_value="segment.mp4",
        ), mock.patch(
            "minimax.get_video_resolution",
            return_value=(640, 360),
        ):
            minimax.render_segment_with_retries(
                1,
                6.0,
                0.50,
                "prompt",
                None,
                6,
                render_started_event=render_started,
            )

        self.assertTrue(render_started.is_set())

    @mock.patch("minimax.get_video_resolution", return_value=(640, 360))
    @mock.patch("minimax.get_video_path", return_value="segment.mp4")
    @mock.patch(
        "minimax.wait_for_completion",
        return_value={"status": {"completed": True, "status_str": "success"}},
    )
    @mock.patch("minimax.queue_workflow", return_value="prompt-id")
    @mock.patch("minimax.prepare_append_workflow", return_value={})
    def test_append_render_forwards_configured_context_frames(
        self,
        prepare,
        queue,
        wait,
        get_path,
        get_resolution,
    ):
        del queue, wait, get_path, get_resolution
        for context_frames in (2, 4, 8, 12):
            minimax.render_segment_with_retries(
                2,
                6.0,
                0.50,
                "prompt",
                "previous.mp4",
                6,
                context_frames=context_frames,
            )

        self.assertEqual(
            [call.kwargs["context_frames"] for call in prepare.call_args_list],
            [2, 4, 8, 12],
        )

    def test_next_beat_prompt_demands_immediate_dominant_execution(self):
        request = minimax.build_segment_request(
            segment=1,
            total_segments=4,
            segment_length=6,
            total_length=24,
            beats=BEATS,
        )

        self.assertIn("PRIMARY BEAT EXECUTION: ACTIVE Beat 1", request)
        self.assertIn("Segment 1 must visibly perform and complete Beat 1", request)
        self.assertIn("it may not be deferred to another segment", request)
        self.assertIn("Begin advancing it early", request)
        self.assertIn("clearly enact every required observable event", request)
        self.assertIn("completed_beat_ids: [1]", request)
        self.assertIn("Do not substitute atmosphere", request)

    def test_action_and_dialogue_beats_receive_specific_execution_orders(self):
        action_request = minimax.build_segment_request(
            2, 4, 6, 24, BEATS
        )
        dialogue_request = minimax.build_segment_request(
            3, 4, 6, 24, BEATS
        )

        self.assertIn("show that action clearly on screen", action_request)
        self.assertIn("write the required audible exchange", dialogue_request)
        self.assertIn("Narration, off-screen action", dialogue_request)

    def test_each_segment_requires_its_beat_outcome_and_completion_id(self):
        request = minimax.build_segment_request(
            segment=2,
            total_segments=4,
            segment_length=6,
            total_length=24,
            beats=BEATS,
        )

        self.assertIn("complete Beat 2 within this clip", request)
        self.assertIn("required observable event and its required outcome", request)
        self.assertIn("completed_beat_ids: [2]", request)

    def test_unconfirmed_beat_is_advanced_after_director_retry_fallback(self):
        with mock.patch("builtins.print") as output:
            completed = minimax.apply_reported_beat_completions(
                BEATS,
                {1},
                [],
                2,
            )
        self.assertEqual(completed, {1, 2})
        self.assertTrue(any(
            "treating the assigned beat as complete" in str(call)
            for call in output.call_args_list
        ))

        self.assertEqual(
            minimax.apply_reported_beat_completions(
                BEATS,
                {1},
                [2],
                2,
            ),
            {1, 2},
        )

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
            segment_number=1,
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
    def test_ask_llm_uses_the_model_loaded_by_the_user(self, post):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark, Jill, and Mark's family "
            "stand together in a busy theme park.",
            [1]
        )
        post.return_value = FakeResponse(json.dumps(payload))

        self.assertEqual(minimax.ask_llm([]), payload)

        request_json = post.call_args.kwargs["json"]
        self.assertNotIn("model", request_json)
        self.assertEqual(request_json["response_format"], minimax.RESPONSE_FORMAT)

    @mock.patch("minimax.generate_random_llm_seed", return_value=8675309)
    @mock.patch("minimax.requests.post")
    def test_every_llm_transport_payload_includes_random_seed(
        self,
        post,
        random_seed,
    ):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            [],
        )
        post.return_value = FakeResponse(json.dumps(payload))

        self.assertEqual(
            minimax.ask_llm([], response_format=None),
            payload,
        )

        self.assertEqual(post.call_args.kwargs["json"]["seed"], 8675309)
        random_seed.assert_called_once_with()

    @mock.patch("minimax.generate_random_llm_seed", return_value=42)
    @mock.patch("minimax.requests.post")
    def test_llm_transport_forwards_creativity_sampling_parameters(
        self,
        post,
        _random_seed,
    ):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            [],
        )
        post.return_value = FakeResponse(json.dumps(payload))

        minimax.ask_llm(
            [],
            response_format=None,
            **minimax.BEAT_LLM_SAMPLING_PARAMETERS,
        )

        request_json = post.call_args.kwargs["json"]
        for name, value in minimax.BEAT_LLM_SAMPLING_PARAMETERS.items():
            self.assertEqual(request_json[name], value)

    @mock.patch(
        "minimax.generate_random_llm_seed",
        side_effect=[101, 202],
    )
    @mock.patch("minimax.requests.post")
    def test_llm_transport_retry_gets_a_new_random_seed(
        self,
        post,
        random_seed,
    ):
        payload = response(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together.",
            [],
        )
        post.side_effect = [
            minimax.requests.ConnectionError("temporary failure"),
            FakeResponse(json.dumps(payload)),
        ]

        self.assertEqual(
            minimax.ask_llm(
                [],
                max_retries=2,
                retry_delay=0,
                response_format=None,
            ),
            payload,
        )

        self.assertEqual(
            [call.kwargs["json"]["seed"] for call in post.call_args_list],
            [101, 202],
        )
        self.assertEqual(random_seed.call_count, 2)

    @mock.patch("minimax.time.sleep")
    @mock.patch("minimax.requests.post")
    def test_beat_transport_retries_past_normal_limit_until_success(
        self,
        post,
        sleep,
    ):
        payload = {"beats": ["A valid beat."]}
        post.side_effect = [
            minimax.requests.ConnectionError(f"temporary failure {attempt}")
            for attempt in range(6)
        ] + [FakeResponse(json.dumps(payload))]

        result = minimax.ask_llm(
            [{"role": "user", "content": "create beats"}],
            max_retries=1,
            retry_delay=0,
            response_format=None,
            history_metadata={"purpose": "beat_generation"},
        )

        self.assertEqual(result, payload)
        self.assertEqual(post.call_count, 7)
        self.assertEqual(sleep.call_count, 6)

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

    def test_append_prompt_history_appends_complete_message_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, "prompt_history.txt")
            first_prompt = [{"role": "user", "content": "first prompt"}]
            second_prompt = [{"role": "user", "content": "second prompt"}]

            minimax.append_prompt_history(
                first_prompt,
                history_path,
                {
                    "run_id": "run-123",
                    "source_sha256": "source-abc",
                    "purpose": "director",
                    "segment": 1,
                    "attempt": 1,
                    "conditioning_mode": "initial",
                },
            )
            minimax.append_prompt_history(
                second_prompt,
                history_path,
                {"purpose": "summary", "segment": 2, "attempt": 1},
            )

            history = open(history_path, "r", encoding="utf-8").read()
            self.assertEqual(history.count("=" * 72), 2)
            self.assertIn('"content": "first prompt"', history)
            self.assertIn('"content": "second prompt"', history)
            self.assertIn('"purpose": "director"', history)
            self.assertIn('"purpose": "summary"', history)
            self.assertIn('"run_id": "run-123"', history)
            self.assertIn('"source_sha256": "source-abc"', history)
            self.assertIn('"conditioning_mode": "initial"', history)

    def test_reset_prompt_history_clears_previous_run_before_appending(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, "prompt_history.txt")
            with open(history_path, "w", encoding="utf-8") as history_file:
                history_file.write("old run prompt")

            minimax.reset_prompt_history(history_path)
            minimax.append_prompt_history(
                [{"role": "user", "content": "new run prompt"}],
                history_path,
            )

            with open(history_path, "r", encoding="utf-8") as history_file:
                history = history_file.read()
            self.assertNotIn("old run prompt", history)
            self.assertIn("new run prompt", history)

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
        self.assertEqual(fallback_payload["seed"], first_payload["seed"])

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
            "detailed_description: [Shot 1] Live-action, "
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
            formatted["detailed_description"].startswith("[Shot 1]")
        )

    def test_python_repair_does_not_make_an_extra_llm_call(self):
        malformed = response(
            "**detailed_description:** [Shot 9] At 00:00.000, "
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
            formatted["detailed_description"].startswith("[Shot 1]")
        )

    def test_active_beat_content_is_not_validated_during_video_generation(self):
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

        self.assertEqual(llm_request.call_count, 1)
        self.assertIn("look at the sky", result[
            "detailed_description"
        ])

    @mock.patch("minimax.validate_ministral_prompt")
    def test_runtime_validator_and_correction_are_not_run(
        self,
        validator,
    ):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        validator.return_value = ["Malformed H3 prompt structure."]
        llm_request = mock.Mock(return_value=missing)

        result = minimax.request_valid_ministral_prompt(
            [
                {"role": "system", "content": "director"},
                {"role": "user", "content": "beat four"}
            ],
            context_for(4),
            llm_request=llm_request
        )

        self.assertEqual(llm_request.call_count, 1)
        validator.assert_not_called()
        self.assertIn("look at the sky", result["detailed_description"])
        self.assertEqual(result["completed_beat_ids"], [4])

    @mock.patch("minimax.validate_ministral_prompt")
    def test_correction_limit_does_not_enable_runtime_validation(self, validator):
        missing = response(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky.",
            [4]
        )
        validator.return_value = ["Malformed H3 prompt structure."]
        llm_request = mock.Mock(return_value=missing)

        result = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat four"}],
            context_for(4),
            llm_request=llm_request,
            max_content_corrections=5,
        )

        self.assertEqual(llm_request.call_count, 1)
        validator.assert_not_called()
        self.assertIn("look at the sky", result["detailed_description"])

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

        self.assertEqual(llm_request.call_count, 1)
        self.assertEqual(
            result["detailed_description"],
            raw["detailed_description"]
        )

    @mock.patch("minimax.validate_ministral_prompt")
    def test_validator_exception_uses_formatted_prompt_without_exiting(self, validator):
        validator.side_effect = AssertionError("runtime validator must not run")
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

        self.assertEqual(llm_request.call_count, 1)
        validator.assert_not_called()
        self.assertIn("Mark", result["detailed_description"])

    def test_context_requires_each_active_beat_in_its_assigned_segment(self):
        first_segment = minimax.build_ministral_context(
            segment_number=1,
            segment_duration=6.0,
            beats=BEATS,
            completed_beat_ids=[],
            subject_definitions=SUBJECTS,
            story="A noisy theme park."
        )
        second_segment = minimax.build_ministral_context(
            segment_number=2,
            segment_duration=6.0,
            beats=BEATS,
            completed_beat_ids=[],
            subject_definitions=SUBJECTS,
            story="A noisy theme park."
        )

        self.assertTrue(first_segment["beat_deadline_required"])
        self.assertEqual(first_segment["next_beat_id"], 1)
        self.assertTrue(second_segment["beat_deadline_required"])
        self.assertEqual(second_segment["next_beat_id"], 2)

    def test_future_beat_content_is_not_validated_during_video_generation(self):
        context = context_for(1)
        context["beat_deadline_required"] = False
        leaked = response(
            "[Shot 1] Live-action, cinematic, Mark, Jill, and their family "
            "stand together as flying saucers suddenly cross overhead.",
            []
        )

        llm_request = mock.Mock(return_value=leaked)
        formatted = minimax.request_valid_ministral_prompt(
            [{"role": "user", "content": "beat one"}],
            context,
            llm_request=llm_request,
        )

        self.assertEqual(llm_request.call_count, 1)
        self.assertIn("flying saucers", formatted["detailed_description"])

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
        self.assertEqual(prompt.count("detailed_description:"), 1)
        self.assertEqual(prompt.count("overall_soundscape:"), 1)
        self.assertEqual(prompt.count("non_diegetic_music:"), 0)

    def test_h3_prompt_omits_placeholders_without_mutating_source_values(self):
        formatted = {
            "detailed_description": (
                "[Shot 2] Mark watches an unknown craft settle nearby.\n"
                "- obsolete_camera: N/A\n"
                "- unused_props: [N/A, null, \"\"]"
            ),
            "overall_soundscape": "N/A",
            "non_diegetic_music": "none",
            "completed_beat_ids": [],
        }
        definitions = (
            "<Subject 1> is Mark, gender: N/A, referenced in <Picture 1>.\n"
            "unused_picture_ids: []"
        )
        previous_state = "\n".join((
            "- Location/environment: inside the spacecraft",
            "- Character positions: N/A",
            "- Character appearance/physical condition: []",
            "- Clothing: red jacket",
            "- Props/objects: silver key in Mark's hand",
            "- Camera/framing: unspecified",
            "- Ongoing physical action: Mark watches the unknown craft",
            "- Ongoing audio: null",
        ))
        original_formatted = json.loads(json.dumps(formatted))

        prompt = minimax.build_h3_prompt(
            formatted,
            definitions,
            previous_state=previous_state,
            segment_number=2,
        )

        self.assertNotRegex(prompt, r"(?i)(?<!\w)N\s*/?\s*A(?!\w)")
        self.assertNotRegex(prompt, r"\[\s*\]")
        self.assertNotIn("obsolete_camera", prompt)
        self.assertNotIn("unused_props", prompt)
        self.assertNotIn("unused_picture_ids", prompt)
        self.assertNotIn("overall_soundscape:", prompt)
        self.assertNotIn("non_diegetic_music:", prompt)
        self.assertNotIn("Character positions:", prompt)
        self.assertNotIn("Character appearance/physical condition:", prompt)
        self.assertNotIn("Camera/framing:", prompt)
        self.assertNotIn("Ongoing audio:", prompt)
        self.assertIn("unknown craft", prompt)
        self.assertIn("inside the spacecraft", prompt)
        self.assertIn("red jacket", prompt)
        self.assertIn("silver key in Mark's hand", prompt)
        self.assertEqual(formatted, original_formatted)
        self.assertIn("N/A", previous_state)
        self.assertIn("[]", previous_state)

    def test_hard_cut_injects_each_subjects_latest_clothing_into_h3_prompt(self):
        prior_records = [
            {
                "llm_result": response(
                    "[Shot 1] <Subject 1> Mark wears a red shirt and blue "
                        "jeans at the park entrance; his clothes are clean. "
                        "<Subject 2> Jill is wearing a yellow dress and "
                        "white sneakers beside the fountain; her dress is dry.",
                    []
                )
            },
            {
                "llm_result": response(
                    "[Shot 2] Mark is at the arcade entrance, wearing a navy "
                    "jacket and black jeans; his jacket is wet while Jill "
                    "continues beside him in the same location, wearing a "
                    "yellow dress and white sneakers; her dress is dry.",
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

        subject_text = prompt.split(
            "subject_definitions: ", 1
        )[1].split("\n\ndetailed_description:", 1)[0]
        integrated = prompt.split(
            "detailed_description: ", 1
        )[1].split("\n\noverall_soundscape:", 1)[0]
        self.assertTrue(
            integrated.startswith("[Shot 3] Camera cuts to a new shot:")
        )
        self.assertIn(
            "<Subject 1> Mark is at arcade entrance, wearing a navy jacket "
            "and black jeans, with clothing state: wet",
            clothing
        )
        self.assertIn(
            "<Subject 2> Jill is at fountain, wearing a yellow dress and "
            "white sneakers, with clothing state: dry",
            clothing
        )
        self.assertIn("<Subject 1> Mark", integrated)
        self.assertIn("<Subject 2> Jill", integrated)

    def test_structured_hard_cut_continuity_ignores_legacy_summary_text(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Mark"].update({
            "position": "left side of the bed",
            "physical_condition": "alert",
            "wardrobe": {
                "upper": "red shirt",
                "lower": "blue jeans",
                "footwear": "white sneakers",
                "other": "N/A",
            },
        })
        current = response(
            "[Shot 3] Camera cuts to a new shot: Mark and Jill sit together.",
            [],
        )

        continuity = minimax.build_hard_cut_subject_continuity_from_state(
            SUBJECTS,
            current,
            state,
        )

        self.assertIn("left side of the bed", continuity)
        self.assertIn("red shirt, blue jeans, white sneakers", continuity)
        self.assertNotIn("doorway", continuity)

    def test_first_prompt_omits_previous_state(self):
        formatted = response(
            "[Shot 1] Live-action, cinematic, Mark stands in the theme park.",
            [],
        )
        prompt = minimax.build_h3_prompt(formatted, SUBJECTS)

        self.assertNotIn("Previous state:", prompt)

    def test_segment_one_ignores_any_stale_previous_state_value(self):
        formatted = response(
            "[Shot 1] Live-action, cinematic, Mark stands in the theme park.",
            [],
        )
        stale_state = "\n".join(
            f"- {field}: stale value"
            for field in minimax.PREVIOUS_STATE_FIELDS
        )
        prompt = minimax.build_h3_prompt(
            formatted,
            SUBJECTS,
            previous_state=stale_state,
            segment_number=1,
        )

        self.assertNotIn("Previous state:", prompt)
        self.assertNotIn("stale value", prompt)

    def test_previous_state_precedes_detailed_description(self):
        formatted = response(
            "[Shot 2] At 00:01.000, Mark continues through the theme park.",
            [],
        )
        previous_state = "\n".join(
            f"- {field}: fact {number}"
            for number, field in enumerate(
                minimax.PREVIOUS_STATE_FIELDS,
                start=1,
            )
        )
        prompt = minimax.build_h3_prompt(
            formatted,
            SUBJECTS,
            previous_state=previous_state,
        )

        marker = "- Location/environment: fact 1\n"
        self.assertIn(marker, prompt)
        self.assertLess(
            prompt.index(marker),
            prompt.index("detailed_description:"),
        )

    def test_reference_continuation_block_precedes_detailed_description(self):
        formatted = {
            "detailed_description": (
                "[Shot 2] Camera continues from the previous shot. Mark waits."
            ),
            "overall_soundscape": "Quiet room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["environment"]["location"] = "theme park midway"
        continuation = minimax.format_authoritative_opening_state(
            state,
            SUBJECTS,
        )

        prompt = minimax.build_h3_prompt(
            formatted,
            SUBJECTS,
            previous_state=continuation,
            segment_number=2,
        )

        self.assertIn("<Video 1> is the immediately preceding", prompt)
        self.assertIn("retention_analysis:", prompt)
        self.assertLess(
            prompt.index("<Video 1> is the immediately preceding"),
            prompt.index("detailed_description:"),
        )

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
                        "[Shot 2] Connie is at the roadside, wearing a faded green "
                        "jacket over a white shirt and black jeans; her clothes are "
                        "clean. Frank is beside the road, wearing a blue polo, "
                        "khaki trousers, and brown shoes; his clothes are dry.",
                []
            )
        }]

        clothing = minimax.build_hard_cut_clothing_reiteration(
            definitions,
            result,
            prior_records
        )

        self.assertIn(
            "<Subject 1> Connie is at roadside, wearing a faded green jacket "
            "over a white shirt and black jeans, with clothing state: clean",
            clothing
        )
        self.assertIn(
            "<Subject 2> Frank is at road, wearing a blue polo, khaki trousers, "
            "and brown shoes, with clothing state: dry",
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
            "- Connie is at the arcade entrance, wearing a burgundy coat and "
            "black boots; her coat is wet."
        )

        self.assertIn(
            "<Subject 1> Connie is at arcade entrance, wearing a burgundy coat "
            "and black boots, with clothing state: wet",
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
            "- Connie is now at the arcade entrance, wearing a burgundy coat "
            "and black boots; her coat is wet."
        )

        self.assertIn(
            "<Subject 1> Connie is at arcade entrance, wearing a burgundy coat "
            "and black boots, with clothing state: wet",
            clothing
        )
        self.assertNotIn("red shirt", clothing)

    def test_hard_cut_includes_latest_location_clothing_and_state_after_subjects(self):
        definitions = "<Subject 1> is Connie, referenced in <Picture 1>."
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Connie enters.",
            []
        )
        continuity = minimax.build_hard_cut_subject_continuity(
            definitions,
            result,
            [],
            "- Connie is at the arcade entrance, wearing a burgundy coat and "
            "black boots; the coat is wet and torn."
        )

        prompt = minimax.build_h3_prompt(result, definitions, continuity)
        subject_section = prompt.split(
            "subject_definitions: ", 1
        )[1].split("\n\ndetailed_description:", 1)[0]

        self.assertTrue(subject_section.startswith(definitions))
        self.assertIn("at arcade entrance", continuity)
        self.assertIn("wearing a burgundy coat and black boots", continuity)
        self.assertIn("clothing state: wet and torn", continuity)

    def test_hard_cut_llm_fallback_is_structured_and_filtered(self):
        definitions = "<Subject 1> is Connie, referenced in <Picture 1>."
        result = response(
            "[Shot 3] Camera cuts to a new shot: <Subject 1> Connie enters.",
            []
        )
        llm_request = mock.Mock(return_value={
            "subjects": [{
                "subject_number": 1,
                "name": "Connie",
                "location": "the arcade entrance",
                "clothing": "a burgundy coat and black boots",
                "clothing_state": "wet and torn",
            }, {
                "subject_number": 2,
                "name": "Undefined",
                "location": "the street",
                "clothing": "a red shirt",
                "clothing_state": "clean",
            }]
        })

        continuity = minimax.build_hard_cut_subject_continuity(
            definitions,
            result,
            [],
            "",
            llm_request=llm_request,
        )

        self.assertIn("Connie", continuity)
        self.assertIn("arcade entrance", continuity)
        self.assertNotIn("Undefined", continuity)
        llm_request.assert_called_once()
        self.assertEqual(
            llm_request.call_args.kwargs["response_format"],
            minimax.SUBJECT_CONTINUITY_RESPONSE_FORMAT,
        )

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

        self.assertEqual(clothing, "")


if __name__ == "__main__":
    unittest.main()
