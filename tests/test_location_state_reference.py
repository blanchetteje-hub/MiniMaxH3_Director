import os
import tempfile
import unittest
from unittest import mock

import minimax


class LocationStateReferenceTests(unittest.TestCase):
    def test_static_setting_extractor_does_not_promote_plot_props(self):
        messages = minimax.build_static_setting_extraction_messages(
            "Amy works in a medieval tavern. Later she pulls up a chair for a unicorn.",
            "medieval tavern",
        )
        system = messages[0]["content"]
        self.assertIn("objects/furniture mentioned only because a later action", system)
        self.assertIn("Do not promote every story prop", system)

    def test_static_setting_extractor_focuses_on_requested_location_and_system_owns_json(self):
        messages = minimax.build_static_setting_extraction_messages(
            "Alice starts at her house, enters a rabbit hole, then sees a meadow.",
            "dark rabbit hole",
        )
        system = messages[0]["content"]
        user = messages[1]["content"]
        self.assertIn(
            "- Focus on the OVERALL LOCATION, use EXPANDED STORY only as a reference. "
            "If the description is short, that is fine.",
            system,
        )
        self.assertIn(
            'Return JSON { "setting_description": "[description]" }',
            system,
        )
        self.assertIn("OVERALL LOCATION\ndark rabbit hole", user)
        self.assertIn("EXPANDED STORY\nAlice starts", user)
        self.assertNotIn("Return exactly setting_description.", user)
        self.assertEqual(
            set(minimax.build_static_setting_extraction_response_format()[
                "json_schema"
            ]["schema"]["properties"]),
            {"setting_description"},
        )

    def test_setting_and_world_state_purpose_routes_use_standard_profiles(self):
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["story_setting_spatial_refine"],
            minimax.SMART_CREATIVE_LLM_SETTINGS,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["story_setting_extract"],
            minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["story_setting_json_extract"],
            minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        )
        self.assertEqual(
            minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["story_setting_json_extract"], 4096,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["story_location_extract"],
            minimax.EXTRACTOR_LLM_SETTINGS,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["static_setting_extract"],
            minimax.EXTRACTOR_LLM_SETTINGS,
        )
        self.assertIs(
            minimax.LLM_PURPOSE_PROFILES["scene_location_select"],
            minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        )
        self.assertEqual(
            minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["scene_location_select"],
            2048,
        )
        self.assertEqual(
            minimax.SMART_EXTRACTOR_LLM_SETTINGS["thinking_budget_tokens"],
            1024,
        )

    def test_scene_location_selector_receives_names_and_returns_minimal_contract(self):
        locations = [
            {"name": "Rabbit Hole", "description": "A grassy hill."},
            {"name": "Tea Garden", "description": "A garden of tables."},
        ]
        messages = minimax.build_scene_location_selection_messages(
            "Alice tumbles from the rabbit hole into Wonderland.",
            "A rabbit hole descends through grass.",
            locations,
        )
        self.assertIn("CURRENT BEAT", messages[1]["content"])
        self.assertIn('"name":"Rabbit Hole"', messages[1]["content"])
        self.assertNotIn("location_", messages[1]["content"])
        self.assertIn("transitioning", messages[0]["content"])
        self.assertEqual(
            minimax.parse_scene_location_selection({
                "classification": "transitioning",
                "location_name": "Tea Garden",
            }),
            {
                "classification": "transitioning",
                "location_name": "Tea Garden",
            },
        )
        schema = minimax.build_scene_location_selection_response_format()
        self.assertEqual(
            set(schema["json_schema"]["schema"]["properties"]),
            {"classification", "location_name"},
        )
        self.assertEqual(
            schema["json_schema"]["schema"]["properties"]["classification"]["enum"],
            ["same_location", "new_location", "transitioning"],
        )

    def test_scene_location_selection_call_is_tagged_and_logged(self):
        request = mock.Mock(return_value={
            "classification": "same_location",
            "location_name": "",
        })
        with mock.patch.object(minimax, "console_log") as log:
            selected = minimax.extract_scene_location_selection(
                "Alice looks around.",
                "A garden.",
                [{"name": "Tea Garden", "description": "A garden."}],
                llm_request=request,
                history_metadata={"segment": 3},
            )
        self.assertEqual(selected["classification"], "same_location")
        self.assertEqual(
            request.call_args.kwargs["response_format"]["json_schema"]["name"],
            "scene_location_select",
        )
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "scene_location_select",
        )
        self.assertTrue(any("LLM result" in str(call) for call in log.call_args_list))

    def test_location_selector_classifies_all_three_segment_location_modes(self):
        for value in ("same_location", "new_location", "transitioning"):
            parsed = minimax.parse_scene_location_selection({
                "classification": value,
                "location_name": "" if value == "same_location" else "Wonderland",
            })
            self.assertEqual(parsed["classification"], value)
        with self.assertRaisesRegex(ValueError, "same_location"):
            minimax.parse_scene_location_selection({
                "classification": "same_location",
                "location_name": "Wonderland",
            })
        self.assertEqual(
            minimax.normalize_cached_scene_location_selection({
                "selection": "existing",
                "location_name": "Tea Garden",
                "mixed_environment": True,
            }),
            {"classification": "new_location", "location_name": "Tea Garden"},
        )

    def test_destination_resolution_reuses_existing_alias_or_requests_creation(self):
        world_state = minimax.empty_world_state("location-transition")
        world_state["locations"] = {
            "location_hole": {"id": "location_hole", "name": "Rabbit Hole"},
            "location_garden": {"id": "location_garden", "name": "Tea Garden"},
        }
        same = minimax.resolve_scene_location_destination(
            world_state,
            "location_hole",
            {"classification": "same_location", "location_name": ""},
        )
        self.assertEqual(same["destination_location_id"], "location_hole")
        existing = minimax.resolve_scene_location_destination(
            world_state,
            "location_hole",
            {"classification": "transitioning", "location_name": "the Tea Garden"},
        )
        self.assertEqual(existing["origin_location_id"], "location_hole")
        self.assertEqual(existing["destination_location_id"], "location_garden")
        self.assertFalse(existing["requires_registration"])
        new = minimax.resolve_scene_location_destination(
            world_state,
            "location_hole",
            {"classification": "new_location", "location_name": "Wonderland meadow"},
        )
        self.assertIsNone(new["destination_location_id"])
        self.assertTrue(new["requires_registration"])
        with self.assertRaisesRegex(ValueError, "active origin"):
            minimax.resolve_scene_location_destination(
                world_state,
                "location_hole",
                {"classification": "transitioning", "location_name": "Rabbit Hole"},
            )

    def test_location_aliases_resolve_only_when_unique(self):
        world_state = minimax.empty_world_state("alias-test")
        world_state["locations"] = {
            "location_wonderland": {"id": "location_wonderland", "name": "Wonderland"},
            "location_garden": {"id": "location_garden", "name": "Tea Garden"},
        }
        self.assertEqual(
            minimax.resolve_world_state_location_alias(world_state, "the Wonderland"),
            "location_wonderland",
        )
        world_state["locations"]["location_garden_copy"] = {
            "id": "location_garden_copy",
            "name": "Secret Garden",
        }
        with self.assertRaisesRegex(ValueError, "ambiguously matches"):
            minimax.resolve_world_state_location_alias(world_state, "Garden")

    def test_location_reference_paths_are_stable_per_location_and_run(self):
        first = minimax.location_reference_output_path("location_one", "run-123")
        same = minimax.location_reference_output_path("location_one", "run-123")
        other = minimax.location_reference_output_path("location_two", "run-123")
        next_run = minimax.location_reference_output_path("location_one", "run-456")
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)
        self.assertNotEqual(first, next_run)
        self.assertEqual(os.path.dirname(first), os.path.abspath(minimax.STATE_MEDIA_OUTPUT))
        self.assertTrue(
            minimax.location_reference_filename_prefix("location_one", "run-123")
            .endswith(os.path.basename(first)[:-4])
        )

    def test_location_selection_metadata_survives_checkpoint_resume(self):
        state = minimax.new_generation_state({"source_sha256": "location-checkpoint"})
        world_state, hole_id = minimax.seed_canonical_static_location_state(
            state["world_state"],
            {"location": {"name": "Rabbit Hole"}, "anchors": [], "objects": []},
        )
        world_state, garden_id = minimax.seed_canonical_static_location_state(
            world_state,
            {"location": {"name": "Tea Garden"}, "anchors": [], "objects": []},
        )
        state["world_state"] = world_state
        state["metadata"] = {
            "active_location_id": garden_id,
            "segment_location_ids": {"1": hole_id, "2": garden_id},
            "segment_location_transitions": {
                "2": {
                    "classification": "transitioning",
                    "origin_location_id": hole_id,
                    "destination_location_id": garden_id,
                },
            },
            "scene_location_selections": {
                "1": {
                    "classification": "same_location",
                    "location_name": "",
                },
            },
            "location_contexts": {
                hole_id: {
                    "name": "Rabbit Hole",
                    "location_reference_video": "/state/hole.mp4",
                },
                garden_id: {
                    "name": "Tea Garden",
                    "location_reference_video": "/state/garden.mp4",
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "generation_state.json")
            minimax.save_generation_state(state, path)
            loaded = minimax.load_generation_state(path)
        self.assertEqual(
            loaded["metadata"]["segment_location_ids"],
            {"1": hole_id, "2": garden_id},
        )
        self.assertEqual(
            loaded["metadata"]["scene_location_selections"]["1"]["classification"],
            "same_location",
        )
        self.assertEqual(
            loaded["metadata"]["location_contexts"][garden_id][
                "location_reference_video"
            ],
            "/state/garden.mp4",
        )
        self.assertEqual(
            loaded["metadata"]["segment_location_transitions"]["2"],
            {
                "classification": "transitioning",
                "origin_location_id": hole_id,
                "destination_location_id": garden_id,
            },
        )
        self.assertEqual(set(loaded["world_state"]["locations"]), {hole_id, garden_id})

    def test_saved_prompt_render_uses_each_segments_selected_location_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = os.path.join(directory, "generated_prompts.txt")
            payload = {
                "version": 1,
                "config": {
                    "segment_length": 8.0,
                    "total_length": 24.0,
                    "megapixels": 0.5,
                    "steps": 6,
                    "trim_frames": 2,
                    "refresh_interval": None,
                    "total_segments": 3,
                    "location_reference_videos": {
                        "location_hole": "/state/hole.mp4",
                        "location_garden": "/state/garden.mp4",
                    },
                },
                "macro_arc": {},
                "reference_jobs": [],
                "prompts": [
                    {
                        "segment": 1,
                        "duration": 8.0,
                        "conditioning_mode": "initial",
                        "location_id": "location_hole",
                        "location_reference_video_path": "/state/hole.mp4",
                        "h3_prompt": "first prompt",
                    },
                    {
                        "segment": 2,
                        "duration": 8.0,
                        "conditioning_mode": "continuation",
                        "location_id": "location_garden",
                        "location_reference_video_path": "/state/garden.mp4",
                        "h3_prompt": "second prompt",
                    },
                    {
                        "segment": 3,
                        "duration": 8.0,
                        "conditioning_mode": "continuation",
                        "location_id": "location_hole",
                        "location_reference_video_path": "/state/hole.mp4",
                        "h3_prompt": "third prompt",
                    },
                ],
            }
            minimax.save_generated_prompts_file(payload, prompt_path)
            calls = []
            render_results = [
                ({}, os.path.join(directory, "one.mp4"), 1280, 720, 0.5),
                ({}, os.path.join(directory, "two.mp4"), 1280, 720, 0.5),
                ({}, os.path.join(directory, "three.mp4"), 1280, 720, 0.5),
            ]
            with (
                mock.patch.object(minimax, "validate_runtime_environment"),
                mock.patch.object(
                    minimax,
                    "render_segment_with_retries",
                    side_effect=lambda *args, **kwargs: calls.append(kwargs) or render_results[len(calls) - 1],
                ),
                mock.patch.object(minimax, "stitch_videos"),
            ):
                minimax.render_generated_prompts(
                    type("Args", (), {"steps": 6})(),
                    prompt_path,
                )
            self.assertEqual(
                [call["location_reference_video_path"] for call in calls],
                ["/state/hole.mp4", "/state/garden.mp4", "/state/hole.mp4"],
            )

    def test_saved_transition_prompt_binds_both_videos_and_keeps_previous_guide(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = os.path.join(directory, "generated_prompts.txt")
            payload = {
                "version": 1,
                "config": {
                    "segment_length": 8.0,
                    "total_length": 24.0,
                    "megapixels": 0.5,
                    "steps": 6,
                    "trim_frames": 2,
                    "refresh_interval": 2,
                    "total_segments": 3,
                    "location_reference_videos": {
                        "location_hole": "/state/hole.mp4",
                        "location_garden": "/state/garden.mp4",
                    },
                },
                "macro_arc": {},
                "reference_jobs": [],
                "prompts": [
                    {"segment": 1, "duration": 8.0, "conditioning_mode": "initial", "location_id": "location_hole", "h3_prompt": "one"},
                    {
                        "segment": 2,
                        "duration": 8.0,
                        "conditioning_mode": "continuation",
                        "location_id": "location_garden",
                        "location_transition": {
                            "classification": "transitioning",
                            "origin_location_id": "location_hole",
                            "destination_location_id": "location_garden",
                        },
                        "location_reference_video_paths": [
                            "/state/hole.mp4", "/state/garden.mp4",
                        ],
                        "h3_prompt": "transition",
                    },
                    {
                        "segment": 3,
                        "duration": 8.0,
                        "conditioning_mode": "continuation",
                        "location_id": "location_garden",
                        "location_reference_video_path": "/state/garden.mp4",
                        "h3_prompt": "after transition",
                    },
                ],
            }
            minimax.save_generated_prompts_file(payload, prompt_path)
            calls = []
            render_results = [
                ({}, os.path.join(directory, "one.mp4"), 1280, 720, 0.5),
                ({}, os.path.join(directory, "two.mp4"), 1280, 720, 0.5),
                ({}, os.path.join(directory, "three.mp4"), 1280, 720, 0.5),
            ]
            with (
                mock.patch.object(minimax, "validate_runtime_environment"),
                mock.patch.object(
                    minimax,
                    "render_segment_with_retries",
                    side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or render_results[len(calls) - 1],
                ),
                mock.patch.object(minimax, "stitch_videos"),
            ):
                minimax.render_generated_prompts(
                    type("Args", (), {"steps": 6})(),
                    prompt_path,
                )
        self.assertEqual(
            calls[1][1]["location_reference_video_paths"],
            ["/state/hole.mp4", "/state/garden.mp4"],
        )
        self.assertTrue(calls[1][1]["force_append"])
        self.assertEqual(calls[1][0][4], os.path.join(directory, "one.mp4"))
        self.assertEqual(
            calls[2][1]["location_reference_video_paths"],
            ["/state/garden.mp4"],
        )
        self.assertFalse(calls[2][1]["force_append"])
        self.assertEqual(calls[2][0][4], os.path.join(directory, "two.mp4"))

    def test_saved_location_reference_jobs_return_reusable_id_mapping(self):
        jobs = [
            {
                "job_id": "location:one",
                "kind": "location_reference",
                "location_id": "location_one",
                "setting_description": "A hillside.",
                "megapixels": 0.5,
                "steps": 6,
                "loras": [],
                "noise_seed": 1,
                "file_token": "run",
            },
            {
                "job_id": "location:two",
                "kind": "location_reference",
                "location_id": "location_two",
                "setting_description": "A garden.",
                "megapixels": 0.5,
                "steps": 6,
                "loras": [],
                "noise_seed": 2,
                "file_token": "run",
            },
        ]
        first_path = minimax.location_reference_output_path("location_one", "run")
        second_path = minimax.location_reference_output_path("location_two", "run")
        with mock.patch.object(
            minimax,
            "render_location_reference_video",
            side_effect=[first_path, second_path],
        ) as render:
            paths = minimax.render_saved_reference_jobs(jobs)
        self.assertEqual(
            paths,
            {
                "location_one": first_path,
                "location_two": second_path,
            },
        )
        self.assertEqual(render.call_count, 2)
        self.assertEqual(
            [call.kwargs["location_id"] for call in render.call_args_list],
            ["location_one", "location_two"],
        )

    def test_location_selection_is_cached_before_director_prefetch(self):
        import inspect

        source = inspect.getsource(minimax._run_main)
        selection_start = source.index("def prepare_scene_location_for_segment(")
        selection_end = source.index("# Assemble the prefetched data", selection_start)
        selection_body = source[selection_start:selection_end]
        cached = selection_body.index("selection_cache.get(cache_key)")
        selector = selection_body.index("extract_scene_location_selection(")
        self.assertLess(cached, selector)
        prefetch_location = source.index(
            "prepare_scene_location_for_segment(segment + 1)"
        )
        prefetch_submit = source.index("director_prefetch_executor.submit(", prefetch_location)
        self.assertLess(prefetch_location, prefetch_submit)
        current_location = source.index("prepare_scene_location_for_segment(segment)")
        current_bundle = source.index("segment_bundle = build_segment_bundle(", current_location)
        self.assertLess(current_location, current_bundle)

    def test_transition_destination_reuses_static_setting_and_reference_pipeline(self):
        import inspect

        source = inspect.getsource(minimax._run_main)
        location_start = source.index("def prepare_scene_location_for_segment(")
        location_end = source.index("# Assemble the prefetched data", location_start)
        location_code = source[location_start:location_end]
        for stage in (
            "extract_static_setting(",
            "refine_story_setting_spatially(",
            "extract_story_setting_description(",
            "seed_canonical_static_location_state(",
            "ensure_location_reference_for_segment(",
        ):
            self.assertIn(stage, location_code)
        self.assertIn("resolution.get(\"requires_registration\")", location_code)
        self.assertIn("ensure_location_reference_for_segment(\n                origin_context", location_code)
        self.assertIn("selection_cache.get(cache_key)", location_code)

    def test_h3_location_reference_context_is_selected_per_location(self):
        rabbit_prompt = minimax.inject_location_reference_into_h3_prompt(
            "detailed_description: [Shot 1] Alice lands.",
            "A grassy hill surrounding a rabbit hole.",
            conditioning_mode="initial",
        )
        garden_prompt = minimax.inject_location_reference_into_h3_prompt(
            "detailed_description: [Shot 1] Alice sits at a tea table.",
            "A flower garden with a long tea table.",
            conditioning_mode="continuation",
        )
        self.assertIn("grassy hill surrounding a rabbit hole", rabbit_prompt)
        self.assertIn("flower garden with a long tea table", garden_prompt)
        self.assertNotIn("flower garden", rabbit_prompt)
        self.assertNotIn("rabbit hole", garden_prompt)

    def test_transition_h3_context_assigns_ordered_temporal_video_roles(self):
        prompt = minimax.inject_location_transition_into_h3_prompt(
            "detailed_description: [Shot 1] Continuing directly from <Video 1>. Alice enters.",
            "Rabbit Hole",
            "A grassy opening above a descending tunnel.",
            "Tea Garden",
            "A garden with a long table beneath flowering trees.",
        )
        self.assertIn("<Video 1> is the 360-degree reference for the ORIGIN", prompt)
        self.assertIn("<Video 2> is the 360-degree reference for the DESTINATION", prompt)
        self.assertLess(prompt.index("<Video 1> is"), prompt.index("<Video 2> is"))
        self.assertIn("the preceding rendered segment's opening guide", prompt)
        self.assertIn("show the physical transition", prompt)
        self.assertIn("final action clearly establish entry", prompt)
        self.assertIn("do not preserve or combine both environments simultaneously", prompt)
        self.assertNotIn("Continuing directly from <Video 1>", prompt)
        initial_transition = minimax.inject_location_transition_into_h3_prompt(
            "detailed_description: Alice steps into the garden.",
            "Tunnel",
            "A narrow tunnel.",
            "Garden",
            "An open garden.",
            has_preceding_guide=False,
        )
        self.assertIn("Begin in the origin environment", initial_transition)
        self.assertNotIn("preceding rendered segment as the separate opening guide", initial_transition)

    def test_director_receives_separate_transition_and_static_location_context(self):
        messages, _, _ = minimax.build_generation_messages(
            director_rules="Director rules",
            story="unused",
            beats=["A traveler leaves the tunnel and enters a garden."],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=1,
            segment_length=8,
            total_length=8,
            static_setting_description=(
                "ORIGIN ENVIRONMENT AT SEGMENT OPENING — tunnel. "
                "DESTINATION ENVIRONMENT AT SEGMENT END — garden."
            ),
            location_transition_context=(
                "Show the physical movement from tunnel to garden and end after entry."
            ),
        )
        user = messages[1]["content"]
        self.assertIn("LOCATION TRANSITION FOR THIS SEGMENT:", user)
        self.assertIn("Show the physical movement from tunnel to garden", user)
        self.assertIn("STATIC SETTING AUTHORITY", user)
        self.assertIn("ORIGIN ENVIRONMENT AT SEGMENT OPENING — tunnel", user)
        self.assertIn("DESTINATION ENVIRONMENT AT SEGMENT END — garden", user)

    def test_transition_reference_connections_keep_origin_then_destination_slots(self):
        workflow = minimax.load_workflow(minimax.APPEND_WORKFLOW_FILE)
        label = "two-location transition test"
        minimax.validate_workflow(workflow, label, is_append=True)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as origin, tempfile.NamedTemporaryFile(suffix=".mp4") as destination:
            origin.write(b"origin")
            destination.write(b"destination")
            origin.flush()
            destination.flush()
            minimax.connect_location_reference_video(
                workflow,
                label,
                [origin.name, destination.name],
            )
        _, conditioner = minimax.find_workflow_node(
            workflow,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            label,
            "MiniMaxH3ReferenceToVideo",
        )
        inputs = conditioner["inputs"]
        first_loader, second_loader = (
            inputs["ref_videos.ref_video_0"][0],
            inputs["ref_videos.ref_video_1"][0],
        )
        self.assertNotEqual(first_loader, second_loader)
        self.assertEqual(
            workflow[first_loader]["inputs"]["video"],
            os.path.abspath(origin.name),
        )
        self.assertEqual(
            workflow[second_loader]["inputs"]["video"],
            os.path.abspath(destination.name),
        )
        self.assertNotIn("ref_video_audios.ref_video_audio_0", inputs)
        self.assertNotIn("ref_video_audios.ref_video_audio_1", inputs)

    def test_transition_render_uses_append_guide_even_on_refresh_schedule(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as previous:
            with (
                mock.patch.object(minimax, "_assert_h3_subject_identity"),
                mock.patch.object(minimax, "_assert_h3_prompt_contains_continuity"),
                mock.patch.object(minimax, "prepare_append_workflow", return_value={}) as append,
                mock.patch.object(minimax, "prepare_refresh_workflow") as refresh,
                mock.patch.object(minimax, "queue_workflow", return_value="prompt"),
                mock.patch.object(minimax, "wait_for_completion", return_value={}),
                mock.patch.object(minimax, "get_video_path", return_value="rendered.mp4"),
                mock.patch.object(minimax, "postprocess_guided_append_video", return_value="rendered.mp4"),
                mock.patch.object(minimax, "get_video_resolution", return_value=(1280, 720)),
            ):
                minimax._render_segment_with_retries(
                    2,
                    8.0,
                    0.5,
                    "transition prompt",
                    previous.name,
                    6,
                    refresh_interval=1,
                    location_reference_video_paths=["/state/origin.mp4", "/state/destination.mp4"],
                    force_append=True,
                )
        append.assert_called_once()
        refresh.assert_not_called()
        self.assertEqual(
            append.call_args.kwargs["location_reference_video_paths"],
            ["/state/origin.mp4", "/state/destination.mp4"],
        )

    def test_spatial_refinement_prompt_uses_requested_contract(self):
        location = "A modest medieval tavern with a counter beside a hearth."
        messages = minimax.build_story_setting_spatial_refinement_messages(location)
        system = messages[0]["content"]
        self.assertIn("Refine this description to be spatially compliant.", system)
        self.assertIn("use east/west/north/south", system)
        self.assertIn("define anchor objects first", system)
        self.assertIn("Define the size of the overall space", system)
        self.assertIn("nothing is overlapping", system)
        self.assertIn("Return plain text, no tables or JSON", system)
        self.assertEqual(messages[1]["content"], location)

    def test_spatial_description_prompt_is_text_only_and_json_is_separate(self):
        messages = minimax.build_story_setting_description_messages(
            "A tavern entrance is on the north wall."
        )
        system = messages[0]["content"]
        self.assertIn("plain text", system)
        self.assertIn("no JSON", system)
        self.assertNotIn('"anchors"', system)
        json_messages = minimax.build_story_setting_json_extraction_messages(
            "An entrance is on the north wall.", "Tavern"
        )
        self.assertIn('"anchors"', json_messages[0]["content"])
        self.assertIn('"objects"', json_messages[0]["content"])
        self.assertIn("ACCEPTED PHYSICAL DESCRIPTION", json_messages[1]["content"])
        self.assertIn("LOCATION NAME\nTavern", json_messages[1]["content"])

    def test_json_parser_preserves_accepted_text(self):
        physical = "The tavern entrance is on the north wall."
        raw = {
            "location": {"name": "Tavern Interior"},
            "anchors": [{"name": "entrance", "type": "door", "wall": "north",
                         "world_state_role": "fixture", "mobility": "fixed"}],
            "objects": [],
        }
        result = minimax.parse_story_setting_json_extraction(
            raw, description=physical, location_name="Tavern Interior",
        )
        self.assertEqual(result["location_name"], "Tavern Interior")
        self.assertEqual(result["location_state"]["anchors"][0]["wall"], "north")
        self.assertEqual(result["text_description"], physical)

    def test_json_extraction_rejects_conflict_with_accepted_text(self):
        description = "The wooden post frames the entrance."
        raw = {
            "location": {"name": "Rabbit Hole"},
            "anchors": [{"name": "wooden post", "type": "post",
                         "location": "center of Rabbit Hole",
                         "world_state_role": "fixture", "mobility": "fixed"}],
            "objects": [],
        }
        with self.assertRaisesRegex(ValueError, "contradictory fixed placement"):
            minimax.parse_story_setting_json_extraction(
                raw, description=description, location_name="Rabbit Hole",
            )

    def test_spatial_extraction_rejects_conflicting_fixture_walls(self):
        location_state = {
            "location": {"name": "Hall"},
            "anchors": [{
                "name": "doorway",
                "type": "door",
                "wall": "north",
            }],
            "objects": [{
                "name": "doorway",
                "type": "door",
                "location": "south wall",
            }],
        }
        errors = minimax.validate_location_geometry_consistency(location_state)
        self.assertEqual(len(errors), 1)
        self.assertIn("doorway", errors[0])
        self.assertIn("contradictory fixed placement", errors[0])

    def test_tunnel_entry_position_and_extension_are_distinct_claims(self):
        location_state = {
            "location": {"name": "Garden"},
            "anchors": [{
                "name": "rabbit-hole entrance",
                "type": "entrance",
                "position": "at the northern edge of Garden",
            }],
            "objects": [{
                "name": "tunnel",
                "type": "passage",
                "location": "south of rabbit-hole entrance",
            }],
        }
        refinement = (
            "The rabbit-hole entrance lies at the garden's northern edge, "
            "with a tunnel extending southward and descending underground."
        )
        self.assertEqual(
            minimax.validate_location_geometry_consistency(
                location_state,
                static_setting="The rabbit-hole entrance is at the northern edge of the garden.",
                spatial_refinement=refinement,
                text_description=refinement,
            ),
            [],
        )

    def test_valid_tunnel_setting_runs_text_and_json_without_repair(self):
        description = (
            "The rabbit-hole entrance lies at the garden's northern edge, "
            "with a tunnel extending southward and descending underground."
        )
        structured = {
            "location": {"name": "Garden"},
            "anchors": [{"name": "rabbit-hole entrance", "type": "entrance",
                         "position": "north edge of Garden",
                         "world_state_role": "fixture", "mobility": "fixed"}],
            "objects": [{"name": "tunnel", "type": "passage",
                         "location": "south of rabbit-hole entrance",
                         "world_state_role": "fixture", "mobility": "fixed"}],
        }
        request = mock.Mock(side_effect=[description, structured])
        result = minimax.extract_story_setting_description(
            description, location_name="Garden", llm_request=request,
        )
        self.assertEqual(result["location_name"], "Garden")
        self.assertEqual(result["text_description"], description)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_json_extract"],
        )

    def test_absolute_and_relative_position_claims_use_distinct_frames(self):
        location_state = {
            "location": {"name": "Garden"},
            "anchors": [],
            "objects": [{
                "name": "tunnel",
                "type": "passage",
                "location": "north of entrance",
            }],
        }
        self.assertEqual(
            minimax.validate_location_geometry_consistency(
                location_state,
                static_setting="The tunnel is on the south wall.",
            ),
            [],
        )

    def test_orientation_does_not_conflict_with_absolute_position(self):
        location_state = {
            "location": {"name": "Garden"},
            "anchors": [],
            "objects": [{
                "name": "tunnel",
                "type": "passage",
                "wall": "north",
            }],
        }
        self.assertEqual(
            minimax.validate_location_geometry_consistency(
                location_state,
                spatial_refinement="The tunnel faces south.",
            ),
            [],
        )

    def test_elevation_claims_are_separate_from_cardinal_axes(self):
        location_state = {
            "location": {"name": "Garden"},
            "anchors": [],
            "objects": [{
                "name": "tunnel",
                "type": "passage",
                "wall": "north",
            }],
        }
        errors = minimax.validate_location_geometry_consistency(
            location_state,
            spatial_refinement="The tunnel descends underground then rises aboveground.",
        )
        self.assertEqual(errors, [])
        claims = minimax._spatial_direction_claims(
            "north wall",
            location_name="Garden",
        )
        self.assertIn(("position", "location:garden", "north_south", "north"), claims)
        diagonal = minimax._spatial_direction_claims(
            "on the north-west wall",
            location_name="Garden",
        )
        self.assertIn(("position", "location:garden", "north_south", "north"), diagonal)
        self.assertIn(("position", "location:garden", "east_west", "west"), diagonal)
        self.assertNotIn("vertical", {claim[2] for claim in claims})
        elevation_travel = minimax._spatial_direction_claims(
            "The tunnel descends underground then rises aboveground."
        )
        self.assertIn(("travel", "entity", "elevation", "down"), elevation_travel)
        self.assertIn(("travel", "entity", "elevation", "up"), elevation_travel)
        self.assertFalse(any(
            minimax._spatial_claims_conflict(left, right)
            for left in elevation_travel
            for right in elevation_travel
        ))
        fixed_elevation = minimax._spatial_direction_claims("The tunnel is underground.")
        fixed_surface = minimax._spatial_direction_claims("The tunnel is at ground level.")
        self.assertIn(("position", "ground", "elevation", "down"), fixed_elevation)
        self.assertIn(("position", "ground", "elevation", "up"), fixed_surface)
        self.assertTrue(minimax._spatial_claims_conflict(
            next(iter(fixed_elevation)), next(iter(fixed_surface))
        ))

    def test_derived_measurement_is_not_a_geometry_constraint_by_itself(self):
        location_state = {
            "location": {"name": "Clearing"},
            "anchors": [{
                "name": "well",
                "type": "well",
                "location": "20 meters east of entrance",
            }],
            "objects": [],
        }
        self.assertEqual(
            minimax.validate_location_geometry_consistency(
                location_state,
                static_setting="A well is part of the clearing.",
                spatial_refinement="A well is 20 meters east of the entrance.",
                text_description="The well sits east of the entrance.",
            ),
            [],
        )

    def test_smart_extractors_use_profile_context_and_purposes(self):
        refine_request = mock.Mock(return_value="A tavern entrance is north of the hearth.")
        refined = minimax.refine_story_setting_spatially(
            "medieval tavern", llm_request=refine_request,
        )
        self.assertIn("entrance", refined)
        self.assertEqual(
            refine_request.call_args.kwargs["history_metadata"]["purpose"],
            "story_setting_spatial_refine",
        )
        description = "A rectangular tavern interior with a northern entrance."
        structured = {"location": {"name": "Tavern Interior"}, "anchors": [], "objects": []}
        request = mock.Mock(side_effect=[description, structured])
        result = minimax.extract_story_setting_description(
            refined, location_name="Tavern Interior", llm_request=request,
        )
        self.assertEqual(result["text_description"], description)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_json_extract"],
        )
        self.assertNotIn("context_token_budget", request.call_args.kwargs)

    def test_story_setting_extraction_repairs_with_exact_issue_and_context(self):
        invalid = "The house is north of the doorway. The house is south of the doorway."
        corrected = "The house is north of the doorway."
        structured = {"location": {"name": "Clearing"}, "anchors": [], "objects": []}
        request = mock.Mock(side_effect=[invalid, corrected, structured])
        result = minimax.extract_story_setting_description(
            "The house is north of the doorway.",
            static_setting="A small clearing.",
            location_name="Clearing",
            llm_request=request,
            history_metadata={"run_id": "repair-test"},
        )
        self.assertEqual(result["text_description"], corrected)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_extract_repair",
             "story_setting_json_extract"],
        )
        repair_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn(invalid, repair_user)
        self.assertIn("north versus south", repair_user)
        self.assertIn("A small clearing.", repair_user)
        self.assertEqual(
            request.call_args_list[2].args[0][-1]["content"].split(
                "ACCEPTED PHYSICAL DESCRIPTION\n", 1
            )[1],
            corrected,
        )

    def test_story_setting_repairs_receive_latest_response_and_changing_issue(self):
        first_invalid = "Location: Clearing\nThe clearing is level."
        second_invalid = "{invalid"
        valid = "A level clearing with a stone path."
        structured = {"location": {"name": "Clearing"}, "anchors": [], "objects": []}
        request = mock.Mock(side_effect=[first_invalid, second_invalid, valid, structured])
        result = minimax.extract_story_setting_description(
            "A level clearing.", location_name="Clearing", llm_request=request,
        )
        self.assertEqual(result["text_description"], valid)
        first_repair = request.call_args_list[1].args[0][-1]["content"]
        second_repair = request.call_args_list[2].args[0][-1]["content"]
        self.assertIn(first_invalid, first_repair)
        self.assertIn("plain text", first_repair)
        self.assertIn(second_invalid, second_repair)
        self.assertIn("JSON", second_repair)
        self.assertEqual(request.call_args_list[2].kwargs["history_metadata"]["repair_attempt"], 2)
        self.assertEqual(request.call_args_list[3].kwargs["history_metadata"]["purpose"],
                         "story_setting_json_extract")

    def test_malformed_story_setting_response_is_repaired_using_parser_issue(self):
        malformed = "{not plain text"
        corrected = "A shaded grove with an entrance along its eastern edge."
        structured = {"location": {"name": "Grove"}, "anchors": [], "objects": []}
        request = mock.Mock(side_effect=[malformed, corrected, structured])
        result = minimax.extract_story_setting_description(
            "A shaded grove.", location_name="Grove", llm_request=request,
        )
        self.assertEqual(result["location_name"], "Grove")
        repair_user = request.call_args_list[1].args[0][-1]["content"]
        self.assertIn(malformed, repair_user)
        self.assertIn("plain text", repair_user)

    def test_story_setting_repair_exhaustion_keeps_latest_diagnostic(self):
        invalid = "The house is north of the gate. The house is south of the gate."
        request = mock.Mock(side_effect=[invalid, invalid, invalid])
        with self.assertRaisesRegex(ValueError, "north versus south"):
            minimax.extract_story_setting_description(
                "A quiet clearing.", llm_request=request, repair_attempts=2,
            )
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_extract_repair",
             "story_setting_extract_repair"],
        )

    def test_spatial_refinement_retries_its_own_conflicting_text(self):
        inconsistent = "The house is north of the gate. The house is south of the gate."
        consistent = "The house is north of the gate."
        request = mock.Mock(side_effect=[inconsistent, consistent])
        result = minimax.refine_story_setting_spatially(
            "A house beside a gate.", llm_request=request,
        )
        self.assertEqual(result, consistent)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_spatial_refine", "story_setting_spatial_refine"],
        )

    def test_wall_sides_are_not_conflicting_fixture_positions(self):
        description = (
            "The house has northern and southern walls. "
            "The house's northern wall faces southward."
        )
        self.assertEqual(minimax.validate_spatial_text_consistency(description), [])
        state = {
            "location": {"name": "Garden"},
            "anchors": [{"name": "house", "type": "building",
                         "world_state_role": "fixture", "mobility": "fixed"}],
            "objects": [],
        }
        self.assertEqual(
            minimax.validate_location_geometry_consistency(
                state, spatial_refinement=description, text_description=description,
            ),
            [],
        )

    def test_same_doorway_on_opposite_walls_requires_text_repair(self):
        invalid = (
            "The doorway is on the north wall. "
            "The doorway is on the south wall."
        )
        self.assertIn(
            "contradictory fixed placement",
            minimax.validate_spatial_text_consistency(invalid)[0],
        )
        with self.assertRaisesRegex(ValueError, "north versus south"):
            minimax.parse_story_setting_text_description(invalid)

    def test_json_retry_uses_unchanged_accepted_description_without_repair(self):
        description = "The tavern has a wooden counter beside the entrance."
        structured = {"location": {"name": "Tavern"}, "anchors": [], "objects": []}
        request = mock.Mock(side_effect=[description, "{invalid json", structured])
        result = minimax.extract_story_setting_description(
            "A tavern with a counter.", location_name="Tavern",
            llm_request=request, json_attempts=2,
        )
        self.assertEqual(result["text_description"], description)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_json_extract",
             "story_setting_json_extract"],
        )
        self.assertEqual(
            request.call_args_list[1].args[0], request.call_args_list[2].args[0],
        )
        self.assertNotIn(
            "PREVIOUS INVALID DESCRIPTION",
            request.call_args_list[2].args[0][-1]["content"],
        )

    def test_json_exhaustion_does_not_rewrite_accepted_text(self):
        description = "A cellar with a north-wall doorway."
        request = mock.Mock(side_effect=[description, "not json", "still not json"])
        with self.assertRaisesRegex(
            minimax.StorySettingJSONExtractionError,
            "accepted description",
        ):
            minimax.extract_story_setting_description(
                description, location_name="Cellar",
                llm_request=request, json_attempts=2,
            )
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            [call.kwargs["history_metadata"]["purpose"] for call in request.call_args_list],
            ["story_setting_extract", "story_setting_json_extract",
             "story_setting_json_extract"],
        )

    def test_initial_location_subject_prompt_contains_only_one_beat(self):
        beat = "A goblin already seated near the hearth asks Amy for a pint."
        possible_subjects = ["Amy", "Goblin1"]
        messages = minimax.build_initial_location_subjects_messages(
            possible_subjects,
            beat,
        )
        self.assertIn("examine a STORY BEAT", messages[0]["content"])
        self.assertIn("making present = false", messages[0]["content"])
        self.assertIn("making present=true", messages[0]["content"])
        self.assertIn("if the POSSIBLE SUBJECT isn't referenced at all", messages[0]["content"])
        self.assertIn("List the Subject (no adjectives)", messages[0]["content"])
        self.assertIn("Return a JSON array of Subjects", messages[0]["content"])
        schema = minimax.INITIAL_LOCATION_SUBJECTS_RESPONSE_FORMAT["json_schema"]["schema"]
        self.assertEqual(schema["type"], "array")
        self.assertEqual(
            set(schema["items"]["properties"]),
            {"subject", "present", "reason"},
        )
        self.assertEqual(
            messages[1]["content"],
            "POSSIBLE SUBJECTS\nAmy, Goblin1\n\nSTORY BEAT\n" + beat,
        )

    def test_initial_location_subject_extractor_uses_first_classification_per_subject(self):
        beats = [
            "Amy wipes the counter while the elf waits by the door.",
            "The blue-coated goblin asks Amy for a pint; the elf steps into the tavern.",
            "The goblin enters from outside, and the elf is already seated.",
        ]
        responses = [
            '[{"subject":"Amy","present":true,"reason":"Amy wipes the counter."},'
            '{"subject":"Elf","present":false,"reason":"The elf waits by the door."}]',
            '[{"subject":"Amy","present":true,"reason":"Amy serves the goblin."},'
            '{"subject":"goblin","present":true,"reason":"The goblin asks for a pint."},'
            '{"subject":"Elf","present":false,"reason":"The elf steps into the tavern."}]',
            '[{"subject":"Goblin1","present":false,"reason":"The goblin enters from outside."},'
            '{"subject":"Elf","present":true,"reason":"The elf is already seated."}]',
        ]
        request = mock.Mock(side_effect=responses)
        result = minimax.extract_initial_location_subjects(
            beats,
            "<Subject 1> is Amy (S1).",
            possible_subjects=["Amy", "Elf1", "Goblin1"],
            llm_request=request,
        )
        self.assertEqual(
            result,
            [{
                "name": "Goblin1",
                "initial_state": "present in the opening scene",
                "reason": "The goblin asks for a pint.",
            }],
        )
        self.assertEqual(request.call_count, len(beats))
        for index, beat in enumerate(beats):
            call = request.call_args_list[index]
            self.assertEqual(
                call.args[0][-1]["content"],
                "POSSIBLE SUBJECTS\nAmy, Elf1, Goblin1\n\nSTORY BEAT\n" + beat,
            )
            self.assertEqual(
                call.kwargs["history_metadata"]["beat_index"], index + 1
            )
            self.assertEqual(
                call.kwargs["history_metadata"]["purpose"],
                "director_raw_scene_subject_resolution",
            )
        self.assertIn("blue-coated goblin", request.call_args_list[1].args[0][-1]["content"])

    def test_initial_location_subject_retry_repeats_only_current_beat(self):
        request = mock.Mock(side_effect=[
            '{"wrong":[]}',
            '[{"subject":"goblin","present":true,"reason":"The goblin asks for ale."}]',
            '[{"subject":"Amy","present":true,"reason":"Amy serves the goblin."},'
            '{"subject":"Goblin1","present":true,"reason":"The goblin asks for ale."}]',
        ])
        result = minimax.extract_initial_location_subjects(
            ["The goblin asks for ale.", "Amy serves the goblin."],
            "<Subject 1> is Amy (S1).",
            possible_subjects=["Amy", "Goblin1"],
            llm_request=request,
        )
        self.assertEqual(
            result,
            [{
                "name": "Goblin1",
                "initial_state": "present in the opening scene",
                "reason": "The goblin asks for ale.",
            }],
        )
        self.assertEqual(request.call_count, 3)
        first_messages = request.call_args_list[0].args[0]
        retry_messages = request.call_args_list[1].args[0]
        self.assertEqual(first_messages, retry_messages)
        self.assertEqual(
            first_messages[-1]["content"],
            "POSSIBLE SUBJECTS\nAmy, Goblin1\n\nSTORY BEAT\nThe goblin asks for ale.",
        )
        self.assertEqual(
            [call.kwargs["history_metadata"]["beat_index"] for call in request.call_args_list],
            [1, 1, 2],
        )
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in request.call_args_list],
            [1, 2, 1],
        )

    def test_initial_location_subject_exact_canon_name_survives_role_normalization(self):
        request = mock.Mock(return_value='[{"subject":"goblin","present":true,"reason":"The goblin asks for ale."}]')
        result = minimax.extract_initial_location_subjects(
            ["The goblin asks for ale."],
            possible_subjects=["Goblin"],
            llm_request=request,
        )
        self.assertEqual(
            result,
            [{
                "name": "Goblin",
                "initial_state": "present in the opening scene",
                "reason": "The goblin asks for ale.",
            }],
        )

    def test_initial_location_subject_resolves_unique_descriptive_name_alias(self):
        result = minimax.parse_initial_location_subjects(
            [{"subject": "Elf", "present": True, "reason": "The elf acts."}],
            possible_subject_names=["Beautiful Female Elf"],
        )
        self.assertEqual(
            result,
            [{"name": "Beautiful Female Elf", "present": True, "reason": "The elf acts."}],
        )

    def test_initial_location_subject_exact_canonical_name_wins_over_alias(self):
        result = minimax.parse_initial_location_subjects(
            [{"subject": "Elf", "present": True, "reason": "The elf acts."}],
            possible_subject_names=["Beautiful Female Elf", "Elf"],
        )
        self.assertEqual(result[0]["name"], "Elf")

    def test_initial_location_subject_rejects_ambiguous_descriptive_alias(self):
        with self.assertRaisesRegex(ValueError, "ambiguous canonical alias"):
            minimax.parse_initial_location_subjects(
                [{"subject": "Elf", "present": True, "reason": "The elf acts."}],
                possible_subject_names=["Beautiful Female Elf", "Tall Male Elf"],
            )

    def test_initial_location_subject_alias_preserves_earliest_classification(self):
        request = mock.Mock(side_effect=[
            '[{"subject":"Elf","present":true,"reason":"The elf waits inside."}]',
            '[{"subject":"Beautiful Female Elf","present":false,"reason":"The elf enters."}]',
        ])
        result = minimax.extract_initial_location_subjects(
            ["The elf waits inside.", "Beautiful Female Elf enters the room."],
            possible_subjects=["Beautiful Female Elf"],
            llm_request=request,
        )
        self.assertEqual(
            result,
            [{
                "name": "Beautiful Female Elf",
                "initial_state": "present in the opening scene",
                "reason": "The elf waits inside.",
            }],
        )
        self.assertEqual(
            request.call_args_list[1].args[0][-1]["content"],
            "POSSIBLE SUBJECTS\nBeautiful Female Elf\n\nSTORY BEAT\nBeautiful Female Elf enters the room.",
        )

    def test_initial_location_subject_retries_unrecognized_keys(self):
        request = mock.Mock(side_effect=[
            '[{"subject":"Unknown","present":true,"reason":"Unknown Subject."}]',
            '[{"subject":"Amy","present":true,"reason":"Amy opens the curtains."}]',
        ])
        result = minimax.extract_initial_location_subjects(
            ["Amy opens the curtains."],
            possible_subjects=["Amy"],
            llm_request=request,
        )
        self.assertEqual(
            result,
            [{
                "name": "Amy",
                "initial_state": "present in the opening scene",
                "reason": "Amy opens the curtains.",
            }],
        )
        self.assertEqual(request.call_count, 2)

    def test_initial_location_subject_incomplete_tavern_goblin_result_retries(self):
        goblin_beat = (
            "A green-skinned goblin leans over the counter clutching a chipped mug "
            "while Amy refills it by pouring liquid from a barrel beside the hearth."
        )
        request = mock.Mock(side_effect=[
            '[{"subject":"Amy","present":true,"reason":"Amy refills the mug."}]',
            '[{"subject":"Amy","present":true,"reason":"Amy refills the mug."},'
            '{"subject":"Goblin","present":true,"reason":"The goblin clutches a chipped mug."}]',
        ])
        result = minimax.extract_initial_location_subjects(
            [goblin_beat],
            "<Subject 1> is Amy (S1).",
            possible_subjects=["Amy", "Goblin1"],
            llm_request=request,
        )
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            result,
            [{
                "name": "Goblin1",
                "initial_state": "present in the opening scene",
                "reason": "The goblin clutches a chipped mug.",
            }],
        )
        self.assertEqual(
            request.call_args_list[0].kwargs["history_metadata"]["attempt"], 1
        )
        self.assertEqual(
            request.call_args_list[1].kwargs["history_metadata"]["attempt"], 2
        )

    def test_initial_location_subject_incomplete_tavern_beat_fails_after_three_attempts(self):
        goblin_beat = (
            "A green-skinned goblin leans over the counter clutching a chipped mug "
            "while Amy refills it by pouring liquid from a barrel beside the hearth."
        )
        incomplete = '[{"subject":"Amy","present":true,"reason":"Amy refills the mug."}]'
        request = mock.Mock(return_value=incomplete)
        with self.assertRaisesRegex(
            ValueError, "omitted explicitly referenced canonical Subjects: Goblin1"
        ):
            minimax.extract_initial_location_subjects(
                [goblin_beat],
                "<Subject 1> is Amy (S1).",
                possible_subjects=["Amy", "Goblin1"],
                llm_request=request,
            )
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in request.call_args_list],
            [1, 2, 3],
        )

    def test_initial_location_subject_parser_rejects_unknown_canon_key(self):
        with self.assertRaisesRegex(ValueError, "unrecognized Subject key"):
            minimax.parse_initial_location_subjects(
                [{"subject": "Unknown", "present": True, "reason": "It acts."}],
                possible_subject_names=["Amy"],
            )

    def test_location_state_prompt_labels_only_needed_fixtures_and_supports(self):
        messages = minimax.build_story_setting_json_extraction_messages(
            "A room with a fixed bench and a loose cup.", "Room",
        )
        system = messages[0]["content"]
        self.assertIn('"world_state_role"', system)
        self.assertIn('"mobility"', system)
        self.assertIn("fixture_support", system)
        self.assertIn("Do not create IDs", system)
        self.assertIn("Do not invent", system)

    def test_dynamic_subject_wardrobe_uses_independent_story_extractor(self):
        state = minimax.new_continuity_state()
        state["subjects"] = {
            "Goblin1": minimax.new_subject_continuity_record({
                "subject_id": 2,
                "name": "Goblin1",
                "gender": "unknown",
            }),
        }
        request = mock.Mock(return_value={
            "clothing": "rough-spun shirt, brown trousers, worn leather shoes"
        })
        updated = minimax.apply_story_subject_wardrobes(
            state,
            "A goblin leans over the counter in a medieval tavern.",
            "<Subject 2> is Goblin1 (S2), present at story start.",
            ["Goblin1"],
            llm_request=request,
        )
        self.assertEqual(request.call_count, 1)
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "story_subject_wardrobe_extract",
        )
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["subject"],
            "Goblin1",
        )
        wardrobe = updated["subjects"]["Goblin1"]["wardrobe"]
        self.assertEqual(wardrobe["upper"], "rough-spun shirt")
        self.assertEqual(wardrobe["lower"], "brown trousers")
        self.assertEqual(wardrobe["footwear"], "worn leather shoes")

    def test_dynamic_subject_wardrobe_keeps_naturally_unclothed_subject_n_a(self):
        state = minimax.new_continuity_state()
        state["subjects"] = {
            "Dragon1": minimax.new_subject_continuity_record({
                "subject_id": 4,
                "name": "Dragon1",
                "gender": "unknown",
            }),
        }
        request = mock.Mock(return_value={"clothing": "N/A"})
        updated = minimax.apply_story_subject_wardrobes(
            state,
            "A dragon enters a medieval tavern.",
            "<Subject 4> is Dragon1 (S4).",
            ["Dragon1"],
            llm_request=request,
        )
        self.assertEqual(
            updated["subjects"]["Dragon1"]["wardrobe"],
            {"upper": "N/A", "lower": "N/A", "footwear": "N/A", "other": "N/A"},
        )

    def test_initial_location_subject_is_registered_before_segment_one(self):
        state = minimax.continuity_state_for_registry(
            "<Subject 1> is Amy (S1).",
            minimax.new_continuity_state(),
        )
        seeded, added = minimax.seed_initial_location_subjects(
            state,
            "<Subject 1> is Amy (S1).",
            [{"name": "Goblin1", "initial_state": "seated near the hearth"}],
        )
        self.assertEqual(added, ["Goblin1"])
        self.assertEqual(seeded["subjects"]["Goblin1"]["origin_segment"], 0)
        self.assertEqual(
            seeded["subjects"]["Goblin1"]["position"],
            "seated near the hearth",
        )
        self.assertEqual(seeded["subjects"]["Goblin1"]["pose_action"], "N/A")

        definitions = minimax.derive_additional_subject_definitions(
            "<Subject 1> is Amy (S1).",
            seeded,
        )
        self.assertEqual(len(definitions), 1)
        self.assertIn("Goblin1", definitions[0])
        self.assertIn("present at story start", definitions[0])
        self.assertNotIn("continued from <Video 1>", definitions[0])

    def test_initial_location_subject_opening_state_is_authoritative(self):
        rendered = minimax.format_initial_location_subjects_opening_state([
            {"name": "Goblin1", "initial_state": "seated near the hearth"},
        ])
        self.assertIn(
            "SUBJECTS ALREADY PRESENT AT STORY START — VISUAL ESTABLISHMENT REQUIRED",
            rendered,
        )
        self.assertIn("Goblin1: already present; seated near the hearth.", rendered)
        self.assertIn("show each Subject at least once", rendered)
        self.assertIn("may remain stationary", rendered)

    def test_request_one_receives_inferred_subjects_as_optional_scene_candidates(self):
        messages, _, _ = minimax.build_generation_messages(
            director_rules="rules",
            story="story",
            beats=["Amy wipes the counter."],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=1,
            segment_length=8,
            total_length=8,
            subject_definitions=(
                "<Subject 2> is Goblin1 (S2), present at story start. "
                "Last known state: Goblin1 was seated near the hearth."
            ),
            initial_location_subjects=[
                {"name": "Goblin1", "initial_state": "seated near the hearth"},
            ],
        )
        prompt = messages[-1]["content"]
        self.assertIn("Goblin1", prompt)
        self.assertIn("seated near the hearth", prompt)
        self.assertIn("show each Subject at least once", prompt)
        self.assertIn("may remain stationary", prompt)

    def test_initial_location_subject_parser_normalizes_role_name(self):
        result = minimax.parse_initial_location_subjects([
            {
                "subject": "goblin",
                "present": True,
                "reason": "The goblin leans over the counter clutching a chipped mug.",
            },
        ])
        self.assertEqual(
            result,
            [{
                "name": "Goblin1",
                "present": True,
                "reason": "The goblin leans over the counter clutching a chipped mug.",
            }],
        )

    def test_physical_validator_prompt_knows_existing_offscreen_subject(self):
        state = minimax.new_continuity_state()
        goblin = minimax.new_subject_continuity_record({
                "subject_id": 2,
                "name": "Goblin1",
            })
        goblin["position"] = "leaning over the counter"
        state["subjects"] = {"Goblin1": goblin}
        messages = minimax.build_director_raw_scene_physical_messages(
            "Goblin1 leans over the counter while Amy refills a mug.",
            "At 00:02.000, the camera pans to Goblin1 leaning over the counter.",
            previous_shot_end="Amy stands beside a west-side table.",
            known_subject_state=state,
        )
        system = messages[0]["content"]
        user = messages[1]["content"]
        self.assertIn("already established in the scene", system)
        self.assertIn("does not need an entrance", system)
        self.assertIn("KNOWN SUBJECT STATE", user)
        self.assertIn("Goblin1: already established", user)
        self.assertIn("leaning over the counter", user)


    def test_new_generation_state_has_location_state(self):
        state = minimax.new_generation_state({})
        self.assertEqual(state["location_state"], {})

    def test_location_reference_prompt_uses_spatial_text_without_extra_world_building(self):
        prompt = minimax.build_location_reference_h3_prompt(
            "The entrance is on the north wall. The counter is on the east wall."
        )
        self.assertIn("subject_definitions: N/A", prompt)
        self.assertIn("medium shot of an empty location", prompt)
        self.assertIn("3-second, full 360 orbital camera shot", prompt)
        self.assertIn("The entrance is on the north wall.", prompt)
        self.assertIn("historical period, culture, and genre", prompt)
        self.assertIn("medieval and fantasy", prompt)
        self.assertNotIn("static, fast", prompt)
        self.assertEqual(minimax.LOCATION_REFERENCE_DURATION_SECONDS, 3.0)

    def test_setting_extractors_preserve_explicit_period_and_genre(self):
        static_prompt = "\n".join(
            message["content"]
            for message in minimax.build_static_setting_extraction_messages(
                "A medieval fantasy tavern with a timber counter.", "Medieval Tavern",
            )
        )
        refinement_prompt = "\n".join(
            message["content"]
            for message in minimax.build_story_setting_spatial_refinement_messages(
                "Medieval fantasy tavern; timber counter on the east wall."
            )
        )
        text_prompt = "\n".join(
            message["content"]
            for message in minimax.build_story_setting_description_messages(
                "Medieval fantasy tavern; timber counter on the east wall.",
                static_setting="Medieval fantasy tavern.",
            )
        )
        self.assertIn("historical period", static_prompt)
        self.assertIn("period-neutral tavern", static_prompt)
        self.assertIn("period-neutral one", refinement_prompt)
        self.assertIn("historical period", text_prompt)
        self.assertIn("medieval fantasy tavern", text_prompt)

    def test_strip_video_audio_uses_video_stream_copy_and_no_audio(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            source = handle.name
            handle.write(b"source")
        try:
            def fake_run(command, **kwargs):
                output = command[-1]
                with open(output, "wb") as handle:
                    handle.write(b"silent-video")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch("minimax.subprocess.run", side_effect=fake_run) as run:
                result = minimax.strip_video_audio(source)

            self.assertEqual(result, source)
            command = run.call_args.args[0]
            self.assertIn("-an", command)
            self.assertIn("-c:v", command)
            self.assertEqual(command[command.index("-c:v") + 1], "copy")
            self.assertEqual(command[command.index("-map") + 1], "0:v:0")
            with open(source, "rb") as handle:
                self.assertEqual(handle.read(), b"silent-video")
        finally:
            if os.path.exists(source):
                os.remove(source)

    def test_location_reference_render_strips_audio_before_return(self):
        workflow = {"dummy": {}}
        with tempfile.NamedTemporaryFile(suffix=".mp4") as handle:
            handle.write(b"video")
            handle.flush()
            with mock.patch("minimax.prepare_location_reference_workflow", return_value=workflow), \
                 mock.patch("minimax.queue_workflow", return_value="prompt-id"), \
                 mock.patch("minimax.wait_for_completion", return_value={}), \
                 mock.patch("minimax.get_video_path", return_value=handle.name), \
                 mock.patch("minimax.strip_video_audio", return_value=handle.name) as strip, \
                 mock.patch("minimax.get_video_resolution", return_value=(1280, 720)):
                returned = minimax.render_location_reference_video(
                    "medieval tavern",
                    0.3,
                    6,
                )

        self.assertEqual(returned, handle.name)
        strip.assert_called_once_with(handle.name)

    def test_location_reference_render_persists_to_unique_location_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "comfy-result.mp4")
            with open(source, "wb") as handle:
                handle.write(b"panoramic-reference")
            expected = os.path.join(
                directory,
                "location_reference_run_location_test.mp4",
            )
            with (
                mock.patch.object(minimax, "STATE_MEDIA_OUTPUT", directory),
                mock.patch.object(minimax, "prepare_location_reference_workflow", return_value={}),
                mock.patch.object(minimax, "queue_workflow", return_value="prompt-id"),
                mock.patch.object(minimax, "wait_for_completion", return_value={}),
                mock.patch.object(minimax, "get_video_path", return_value=source),
                mock.patch.object(minimax, "strip_video_audio", return_value=source),
                mock.patch.object(minimax, "get_video_resolution", return_value=(1280, 720)),
            ):
                returned = minimax.render_location_reference_video(
                    "A forest clearing.",
                    0.3,
                    6,
                    location_id="location_test",
                    file_token="run",
                )
            self.assertEqual(returned, expected)
            with open(expected, "rb") as handle:
                self.assertEqual(handle.read(), b"panoramic-reference")

    def test_h3_prompt_marks_video_one_as_static_location_only(self):
        prompt = minimax.inject_location_reference_into_h3_prompt(
            "detailed_description: [Shot 1] Amy walks behind the bar.",
            "medieval tavern",
            conditioning_mode="continuation",
        )
        self.assertIn("<Video 1> is the persistent LOCATION REFERENCE", prompt)
        self.assertIn("Do not use <Video 1> for characters", prompt)

    def test_append_uses_separate_location_and_guide_loaders(self):
        workflow = minimax.load_workflow(minimax.APPEND_WORKFLOW_FILE)
        label = "location-state append test"
        minimax.validate_workflow(workflow, label, is_append=True)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as handle:
            handle.write(b"x")
            handle.flush()
            location_id = minimax.connect_location_reference_video(
                workflow,
                label,
                handle.name,
                reuse_existing_loader=False,
            )
        guide_id, guide = minimax.find_workflow_node(
            workflow,
            minimax.H3_GUIDE_NODE_NAME,
            label,
            "MiniMaxH3AddGuide",
        )
        guide_loader_id = str(guide["inputs"]["image"][0])
        self.assertEqual(workflow[guide_loader_id]["class_type"], "VHS_LoadVideoPath")
        _, conditioner = minimax.find_workflow_node(
            workflow,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            label,
            "MiniMaxH3ReferenceToVideo",
        )
        self.assertNotEqual(str(location_id), str(guide_loader_id))
        self.assertEqual(guide["inputs"]["image"], [guide_loader_id, 0])
        self.assertEqual(
            conditioner["inputs"]["ref_videos.ref_video_0"],
            [location_id, 0],
        )
        self.assertNotIn(
            "ref_video_audios.ref_video_audio_0",
            conditioner["inputs"],
        )


if __name__ == "__main__":
    unittest.main()
