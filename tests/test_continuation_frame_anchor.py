import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from PIL import Image

import minimax


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class ContinuationFrameAnchorTests(unittest.TestCase):
    def make_video(self, directory):
        for number, color in ((1, (255, 0, 0)), (2, (0, 0, 255))):
            Image.new("RGB", (8, 8), color).save(
                os.path.join(directory, f"frame_{number:02d}.png")
            )
        video_path = os.path.join(directory, "segment_0001.mp4")
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-framerate", "1",
                "-i", os.path.join(directory, "frame_%02d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                video_path,
            ],
            check=True,
        )
        return video_path

    def test_segment_one_does_not_request_a_continuation_frame(self):
        with mock.patch("minimax.extract_final_frame") as extract:
            self.assertIsNone(
                minimax.extract_continuation_frame(1, "not-used.mp4")
            )
        extract.assert_not_called()

    def test_segment_two_uses_segment_one_video_as_source(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "segment_0001.mp4")
            expected_path = os.path.join(
                directory, "continuation_frames", "segment_0001_final.png"
            )
            with mock.patch(
                "minimax.extract_final_frame", return_value=expected_path
            ) as extract:
                result = minimax.extract_continuation_frame(
                    2,
                    previous_video,
                    os.path.join(directory, "continuation_frames"),
                )

        self.assertEqual(result, expected_path)
        extract.assert_called_once_with(previous_video, expected_path)

    def test_final_frame_output_path_is_deterministic(self):
        self.assertEqual(
            minimax.continuation_frame_path(1, "/tmp/video-output"),
            os.path.join(
                os.path.abspath("/tmp/video-output"), "segment_0001_final.png"
            ),
        )

    def test_existing_output_png_can_be_safely_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            video_path = self.make_video(directory)
            output_path = minimax.continuation_frame_path(
                1, os.path.join(directory, "continuation_frames")
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            Image.new("RGB", (8, 8), (0, 255, 0)).save(output_path)

            result = minimax.extract_final_frame(video_path, output_path)

            self.assertEqual(result, os.path.abspath(output_path))
            with Image.open(output_path) as image:
                self.assertEqual(image.getpixel((0, 0)), (0, 0, 254))

    def test_missing_or_invalid_source_video_raises_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "final.png")
            with self.assertRaisesRegex(FileNotFoundError, "source video is missing"):
                minimax.extract_final_frame(
                    os.path.join(directory, "missing.mp4"), output_path
                )

            invalid_video = os.path.join(directory, "invalid.mp4")
            with open(invalid_video, "wb") as file:
                file.write(b"not an mp4")
            with self.assertRaisesRegex(RuntimeError, "Failed to extract final frame"):
                minimax.extract_final_frame(invalid_video, output_path)

    def test_existing_reference_picture_connections_remain_unchanged(self):
        workflow = minimax.load_workflow(minimax.APPEND_WORKFLOW_FILE)
        _, batch_before = minimax.find_workflow_node(
            workflow,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            "append template",
            "MiniMaxH3ReferenceToVideo",
        )
        batch_connections = {
            key: value
            for key, value in batch_before["inputs"].items()
            if key.startswith("ref_images.")
        }
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "previous.mp4")
            with open(previous_video, "wb") as file:
                file.write(b"previous")
            with mock.patch("minimax.COMFY_OUTPUT", directory), mock.patch(
                "minimax.prune_missing_reference_images",
                return_value=([], {number: number for number in range(1, 7)}),
            ), mock.patch("minimax.get_video_frame_count", return_value=158):
                prepared = minimax.prepare_append_workflow(
                    6.0,
                    "prompt",
                    previous_video,
                    2,
                )

        load_video_id, load_video = minimax.find_workflow_node(
            prepared,
            minimax.LOAD_VIDEO_NODE_NAME,
            "prepared append workflow",
            "VHS_LoadVideoPath",
        )
        self.assertEqual(load_video["inputs"]["skip_first_frames"], 136)
        self.assertEqual(load_video["inputs"]["frame_load_cap"], 22)
        self.assertEqual(minimax.h3_frame_count_for_duration(6.0), 158)
        _, guide = minimax.find_workflow_node(
            prepared,
            minimax.H3_GUIDE_NODE_NAME,
            "prepared append workflow",
            "MiniMaxH3AddGuide",
        )
        self.assertEqual(guide["inputs"]["frame_idx"], 0)
        self.assertEqual(guide["inputs"]["image"], [load_video_id, 0])
        self.assertEqual(guide["inputs"]["audio"], [load_video_id, 2])
        audio_vae_id, _ = minimax.find_workflow_node(
            prepared,
            minimax.AUDIO_VAE_NODE_NAME,
            "prepared append workflow",
            "VAELoader",
        )
        self.assertEqual(guide["inputs"]["audio_vae"], [audio_vae_id, 0])

        _, batch_after = minimax.find_workflow_node(
            prepared,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            "prepared append workflow",
            "MiniMaxH3ReferenceToVideo",
        )
        self.assertEqual(
            {
                key: value
                for key, value in batch_after["inputs"].items()
                if key.startswith("ref_images.")
            },
            batch_connections,
        )

    def test_continuation_frame_zero_uses_guide_instead_of_reconstructing_cast(self):
        raw = (
            "At 00:00.000, Amy, Goblin1, and Dragon1 fill a reconstructed wide shot.\n\n"
            "At 00:01.000, Griffin1 enters from the far end.\n\n"
            "End continuity state: Griffin1 stands beside Amy."
        )
        anchored = minimax._anchor_continuation_frame_zero_to_guide(raw)
        first_line = anchored.splitlines()[0]
        self.assertIn("supplied opening guide", first_line)
        self.assertNotIn("Goblin1", first_line)
        self.assertNotIn("Dragon1", first_line)
        self.assertIn("At 00:01.000, Griffin1 enters", anchored)
        self.assertIn("End continuity state: Griffin1 stands beside Amy.", anchored)

    def test_continuation_timestamp_shift_hides_guide_math_from_director(self):
        raw = (
            "At 00:00.000, Amy stands beside the barrel.\n\n"
            "At 00:01.000, Amy lifts the mug.\n\n"
            "At 00:07.000, Amy sets it down.\n\n"
            "End continuity state: Amy stands beside the mug."
        )
        shifted = minimax._shift_continuation_timestamps_for_guide(raw)
        self.assertIn("At 00:00.000, Amy stands", shifted)
        self.assertIn("At 00:01.917, Amy lifts", shifted)
        self.assertIn("At 00:07.917, Amy sets", shifted)
        self.assertIn("End continuity state: Amy stands beside the mug.", shifted)

    def test_append_guide_render_budget_preserves_eight_second_delivery(self):
        self.assertEqual(minimax.h3_frame_count_for_duration(8.0), 192)
        self.assertEqual(minimax.h3_guide_render_frame_count(8.0), 226)
        self.assertAlmostEqual(minimax.h3_guide_render_duration(8.0), 226 / 24)

    def test_native_guide_tail_window_is_exactly_22_frames(self):
        with mock.patch("minimax.get_video_frame_count", return_value=194):
            self.assertEqual(
                minimax.h3_guide_tail_window("previous.mp4"),
                (172, 22),
            )


if __name__ == "__main__":
    unittest.main()
