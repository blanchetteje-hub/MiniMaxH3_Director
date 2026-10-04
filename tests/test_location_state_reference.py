import os
import tempfile
import unittest

import minimax


class LocationStateReferenceTests(unittest.TestCase):
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
        self.assertIn("wide panoramic establishing view of medieval tavern", prompt)
        self.assertIn("no people, characters, creatures, or story action", prompt)
        self.assertIn("one continuous slow lateral camera pan", prompt)

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
