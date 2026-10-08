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

    def test_smart_extractor_profile_is_high_1024_seed_42_with_8192_context(self):
        profile = minimax.SMART_EXTRACTOR_LLM_SETTINGS
        self.assertEqual(profile["seed"], 42)
        self.assertEqual(profile["context_token_budget"], 8192)
        self.assertEqual(profile["reasoning_effort"], "high")
        self.assertEqual(profile["thinking_budget_tokens"], 1024)
        self.assertEqual(
            minimax.SMART_EXTRACTOR_LLM_PURPOSES,
            {"story_setting_extract", "director_raw_scene_subject_resolution"},
        )
        self.assertEqual(
            minimax.SLIGHTLY_CREATIVE_LLM_PURPOSES,
            {"story_setting_spatial_refine"},
        )
        self.assertIn(
            "static_setting_extract",
            minimax.DETERMINISTIC_ANALYSIS_LLM_PURPOSES,
        )
        self.assertEqual(
            minimax.DETERMINISTIC_ANALYSIS_LLM_SETTINGS["thinking_budget_tokens"],
            256,
        )
        self.assertEqual(
            minimax.DETERMINISTIC_ANALYSIS_LLM_SETTINGS["max_output_tokens"],
            1024,
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

    def test_spatial_description_prompt_emits_json_and_text(self):
        messages = minimax.build_story_setting_description_messages(
            "A 30 ft by 20 ft tavern with an entrance on the north wall."
        )
        system = messages[0]["content"]
        self.assertIn("describe ALL objects", system)
        self.assertIn("Define anchors", system)
        self.assertIn("Do not include exact coordinates", system)
        self.assertIn("Keep it literal without embellishment", system)
        self.assertIn("Location: [location]", system)
        self.assertIn('"anchors"', system)
        self.assertIn('"objects"', system)

    def test_spatial_description_parser_splits_state_from_render_text(self):
        raw = """Location: Tavern Interior
{
  "location": {"name": "Tavern Interior"},
  "anchors": [{"name": "entrance", "type": "door", "wall": "north"}],
  "objects": [{"name": "bar counter", "type": "counter", "location": "east"}]
}
Text description based on JSON
The tavern is rectangular. The entrance is on the north wall.
"""
        parsed = minimax.parse_story_setting_description(raw)
        self.assertEqual(parsed["location_name"], "Tavern Interior")
        self.assertEqual(
            parsed["location_state"]["anchors"][0]["wall"],
            "north",
        )
        self.assertEqual(
            parsed["text_description"],
            "The tavern is rectangular. The entrance is on the north wall.",
        )

    def test_smart_extractors_use_profile_context_and_purposes(self):
        refine_request = mock.Mock(
            return_value="30 ft by 20 ft tavern; entrance north."
        )
        refined = minimax.refine_story_setting_spatially(
            "medieval tavern",
            llm_request=refine_request,
        )
        self.assertEqual(refined, "30 ft by 20 ft tavern; entrance north.")
        self.assertNotIn("context_token_budget", refine_request.call_args.kwargs)
        self.assertEqual(
            refine_request.call_args.kwargs["history_metadata"]["purpose"],
            "story_setting_spatial_refine",
        )

        structured_request = mock.Mock(return_value="""Location: Tavern Interior
{"location":{"name":"Tavern Interior"},"anchors":[],"objects":[]}
Text description based on JSON
A rectangular tavern interior.
""")
        result = minimax.extract_story_setting_description(
            refined,
            llm_request=structured_request,
        )
        self.assertEqual(
            result["text_description"],
            "A rectangular tavern interior.",
        )
        self.assertNotIn("context_token_budget", structured_request.call_args.kwargs)
        self.assertEqual(
            structured_request.call_args.kwargs["history_metadata"]["purpose"],
            "story_setting_extract",
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
            '{"Amy":{"present":true,"reason":"Amy wipes the counter."},'
            '"Elf":{"present":false,"reason":"The elf waits by the door."}}',
            '{"goblin":{"present":true,"reason":"The goblin asks for a pint."},'
            '"Elf":{"present":false,"reason":"The elf steps into the tavern."}}',
            '{"Goblin1":{"present":false,"reason":"The goblin enters from outside."},'
            '"Elf":{"present":true,"reason":"The elf is already seated."}}',
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
            '{"goblin":{"present":true,"reason":"The goblin asks for ale."}}',
            "{}",
        ])
        result = minimax.extract_initial_location_subjects(
            ["The goblin asks for ale.", "Amy serves the goblin."],
            possible_subjects=["Goblin1"],
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
            "POSSIBLE SUBJECTS\nGoblin1\n\nSTORY BEAT\nThe goblin asks for ale.",
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
        request = mock.Mock(return_value='{"goblin":{"present":true,"reason":"The goblin asks for ale."}}')
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

    def test_initial_location_subject_retries_unrecognized_keys(self):
        request = mock.Mock(side_effect=[
            '{"subjects":{"present":true,"reason":"Unknown wrapper key."}}',
            '{"Amy":{"present":true,"reason":"Amy opens the curtains."}}',
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

    def test_initial_location_subject_parser_rejects_unknown_canon_key(self):
        with self.assertRaisesRegex(ValueError, "unrecognized Subject key"):
            minimax.parse_initial_location_subjects(
                {"Unknown": {"present": True, "reason": "It acts."}},
                possible_subject_names=["Amy"],
            )

    def test_location_state_prompt_labels_only_needed_fixtures_and_supports(self):
        messages = minimax.build_story_setting_description_messages(
            "A room with a fixed bench and a loose cup."
        )
        system = messages[0]["content"]
        self.assertIn('"world_state_role"', system)
        self.assertIn('"mobility"', system)
        self.assertIn("only identify persistent fixtures/supports needed for cross-segment", system)
        self.assertIn("Do not create IDs", system)

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
        result = minimax.parse_initial_location_subjects({
            "goblin": {
                "present": True,
                "reason": "The goblin leans over the counter clutching a chipped mug.",
            },
        })
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

    def test_existing_visible_subject_bootstrap_fills_only_missing_metadata(self):
        state = minimax.new_continuity_state()
        state["subjects"] = {
            "Goblin1": minimax.new_subject_continuity_record({
                "subject_id": 2,
                "name": "Goblin1",
                "canonical_description": "Goblin1 is a goblin.",
                "wardrobe": {
                    "upper": "N/A",
                    "lower": "N/A",
                    "footwear": "N/A",
                    "other": "N/A",
                },
            }),
        }
        updated, changed = minimax.apply_visible_subject_bootstrap_metadata(
            state,
            {"Goblin1": "Goblin1 is a green-skinned humanoid goblin."},
            {
                "Goblin1": {
                    "upper": "rough-spun shirt",
                    "lower": "brown trousers",
                    "footwear": "worn leather shoes",
                    "other": "N/A",
                },
            },
        )
        self.assertEqual(changed, ["Goblin1"])
        self.assertIn("green-skinned", updated["subjects"]["Goblin1"]["canonical_description"])
        self.assertEqual(
            updated["subjects"]["Goblin1"]["wardrobe"]["upper"],
            "rough-spun shirt",
        )

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
                "A medieval fantasy tavern with a timber counter.",
                "Medieval Tavern",
            )
        )
        refinement_prompt = "\n".join(
            message["content"]
            for message in minimax.build_story_setting_spatial_refinement_messages(
                "Medieval fantasy tavern; timber counter on the east wall."
            )
        )
        final_prompt = "\n".join(
            message["content"]
            for message in minimax.build_story_setting_description_messages(
                "Medieval fantasy tavern; timber counter on the east wall.",
                static_setting="Medieval fantasy tavern.",
            )
        )
        self.assertIn("historical period", static_prompt)
        self.assertIn("period-neutral tavern", static_prompt)
        self.assertIn("period-neutral one", refinement_prompt)
        self.assertIn("medieval fantasy tavern", final_prompt)

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
