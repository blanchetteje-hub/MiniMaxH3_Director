import json
import tempfile
import unittest
from pathlib import Path

import minimax

from tests.H3.harness import (
    FixtureError,
    build_variant_prompts,
    load_fixture,
    review_template,
    validate_fixture,
)


def fixture():
    return {
        "schema_version": 1,
        "segment": {
            "number": 2,
            "conditioning_mode": "continuation",
            "duration": 6.0,
            "current_beat_text": "Maya opens the door.",
            "next_beat_boundary_text": "Maya steps outside.",
        },
        "inputs": {
            "raw_scene": (
                "[Shot 1] At 00:00.000, Maya reaches for the door. "
                "At 00:03.000, she opens it."
            ),
            "authoritative_opening_state": "Maya stands beside the door.",
            "request2_result": {
                "detailed_description": (
                    "[Shot 1] Maya reaches for the door. "
                    "At 00:03.000, she opens it."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            "final_h3_prompt": "CURRENT PROMPT",
            "subject_definitions": "<Subject 1> is Maya, referenced in <Picture 1>.",
        },
        "render": {
            "workflow_type": "append",
            "workflow_file": "workflow.json",
            "workflow_sha256": "abc",
            "duration": 6.0,
            "megapixels": 0.2,
            "steps": 6,
            "seed": 42,
            "loras": [],
            "previous_video_path": "previous.mp4",
            "refresh_frame_path": None,
            "workflow_inputs": {},
        },
    }


class H3HarnessTests(unittest.TestCase):
    def test_fixture_round_trip_and_validation(self):
        payload = fixture()
        validate_fixture(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_fixture(path)
        self.assertEqual(loaded["inputs"]["final_h3_prompt"], "CURRENT PROMPT")

    def test_fixture_requires_exact_prompt(self):
        payload = fixture()
        del payload["inputs"]["final_h3_prompt"]
        with self.assertRaises(FixtureError):
            validate_fixture(payload)

    def test_variants_are_local_and_exclude_audio_from_action_variants(self):
        variants = build_variant_prompts(fixture())
        self.assertEqual(variants["A_current"], "CURRENT PROMPT")
        self.assertIn("Maya reaches", variants["B_raw_scene"])
        for variant_name in ("B_raw_scene", "C_action_only", "D_compact"):
            with self.subTest(variant_name=variant_name):
                self.assertIn(
                    "Continuing directly from the final state of <Video 1>.",
                    variants[variant_name],
                )
        self.assertNotIn("Footsteps", variants["B_raw_scene"])
        self.assertNotIn("Footsteps", variants["C_action_only"])
        self.assertNotIn("non_diegetic_music", variants["C_action_only"])
        self.assertIn("At 00:03.000", variants["D_compact"])

    def test_raw_scene_variant_strips_trailing_end_continuity_state(self):
        payload = fixture()
        payload["inputs"]["raw_scene"] = (
            "At 00:00.000 seconds, Amy runs toward the door.\n\n"
            "At 00:03.000 seconds, Amy opens it.\n\n"
            "End continuity state: Amy stands beside the open door."
        )

        raw_scene_variant = build_variant_prompts(payload)["B_raw_scene"]

        self.assertIn("At 00:00.000 seconds", raw_scene_variant)
        self.assertIn("Amy runs toward the door", raw_scene_variant)
        self.assertIn("At 00:03.000 seconds", raw_scene_variant)
        self.assertIn("Amy opens it", raw_scene_variant)
        self.assertNotIn("End continuity state", raw_scene_variant)
        self.assertNotIn("Amy stands beside the open door", raw_scene_variant)

    def test_raw_scene_variant_keeps_scene_without_continuity_state_marker(self):
        payload = fixture()
        raw_scene = payload["inputs"]["raw_scene"]

        raw_scene_variant = build_variant_prompts(payload)["B_raw_scene"]

        self.assertIn("At 00:00.000, Maya reaches for the door.", raw_scene_variant)
        self.assertIn("At 00:03.000, she opens it.", raw_scene_variant)

    def test_compact_variant_skips_when_no_timestamps_exist(self):
        payload = fixture()
        payload["inputs"]["request2_result"]["detailed_description"] = (
            "Maya opens the door in one continuous motion."
        )
        variants = build_variant_prompts(payload)
        self.assertEqual(variants["D_compact"]["status"], "skipped")

    def test_review_template_is_blank(self):
        review = review_template(("A_current",))
        self.assertIsNone(review["A_current"]["motion_quality"])
        self.assertEqual(review["A_current"]["notes"], "")

    def test_capture_flags_are_opt_in_and_validated_together(self):
        args = minimax.parse_args([
            "6", "6", "0.2",
            "--capture-h3-segment", "1",
            "--capture-h3-fixture", "fixture.json",
        ])
        self.assertEqual(args.capture_h3_segment, 1)
        self.assertEqual(args.capture_h3_fixture, "fixture.json")
        with self.assertRaises(SystemExit):
            minimax.parse_args(["6", "6", "0.2", "--capture-h3-segment", "1"])

    def test_initial_workflow_accepts_reproducibility_overrides(self):
        workflow = minimax.prepare_initial_workflow(
            6.0,
            0.2,
            "detailed_description: [Shot 1] Test.",
            1,
            noise_seed=123,
            output_prefix="video/h3_experiments/test/A_current",
        )
        _, noise = minimax.find_workflow_node(
            workflow, minimax.NOISE_NODE_NAME, "test", "RandomNoise"
        )
        _, save = minimax.find_workflow_node(
            workflow, minimax.SAVE_VIDEO_NODE_NAME, "test", "SaveVideo"
        )
        self.assertEqual(noise["inputs"]["noise_seed"], 123)
        self.assertEqual(
            save["inputs"]["filename_prefix"],
            "video/h3_experiments/test/A_current",
        )

    def test_capture_writes_exact_prompt_and_effective_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            workflow = minimax.prepare_initial_workflow(
                6.0,
                0.2,
                "detailed_description: [Shot 1] Captured.",
                1,
                noise_seed=77,
            )
            video_path = directory / "segment.mp4"
            video_path.write_bytes(b"video")
            fixture_path = directory / "fixture.json"
            minimax.capture_h3_fixture(
                fixture_path,
                {
                    "segment_number": 1,
                    "conditioning_mode": "initial",
                    "duration": 6.0,
                    "current_beat_text": "Captured.",
                    "next_beat_boundary_text": "",
                    "raw_scene": "Captured.",
                    "authoritative_opening_state": "",
                    "request2_result": {
                        "detailed_description": "Captured.",
                        "overall_soundscape": "N/A",
                        "non_diegetic_music": "N/A",
                    },
                    "subject_definitions": "",
                    "loras": [],
                    "segment_length": 6.0,
                },
                workflow,
                "initial",
                video_path,
            )
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["inputs"]["final_h3_prompt"],
            "detailed_description: [Shot 1] Captured.",
        )
        self.assertEqual(payload["render"]["seed"], 77)
        self.assertEqual(payload["render"]["workflow_type"], "initial")


if __name__ == "__main__":
    unittest.main()
