import os
import tempfile
import unittest
from unittest import mock

import minimax


class LocationStateReferenceTests(unittest.TestCase):
    def test_setting_extractor_does_not_promote_plot_props(self):
        messages = minimax.build_story_setting_description_messages(
            "Amy works in a medieval tavern. Later she pulls up a chair for a unicorn.",
            "medieval tavern",
        )
        system = messages[0]["content"]
        self.assertIn("objects/furniture mentioned only because a later action", system)
        self.assertIn("Do not promote every story prop", system)

    def test_setting_description_parser_uses_fallback(self):
        self.assertEqual(
            minimax.parse_story_setting_description(
                {"setting_description": "N/A"},
                fallback="medieval tavern",
            ),
            "medieval tavern",
        )

    def test_location_reference_prompt_is_character_free_contract(self):
        prompt = minimax.build_location_reference_h3_prompt("medieval tavern")
        self.assertIn("3-second, full 360 orbital camera shot", prompt)
        self.assertIn("no people, characters, creatures, or story action", prompt)
        self.assertEqual(minimax.LOCATION_REFERENCE_DURATION_SECONDS, 3.0)

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
        guide_loader_id, _ = minimax.find_workflow_node(
            workflow,
            minimax.LOAD_VIDEO_NODE_NAME,
            label,
            "VHS_LoadVideoPath",
        )
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
