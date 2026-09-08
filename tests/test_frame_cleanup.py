import os
import tempfile
import unittest
from unittest import mock

import minimax


class FrameCleanupTests(unittest.TestCase):
    def test_cleanup_removes_vision_and_refresh_frames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vision_dir = os.path.join(temp_dir, "vision", "segment_0002")
            input_dir = os.path.join(temp_dir, "input")
            os.makedirs(vision_dir)
            os.makedirs(input_dir)
            vision_path = os.path.join(vision_dir, "end_01_frame_00010.png")
            refresh_path = os.path.join(
                input_dir, "minimax_refresh_first_frame_0002.png"
            )
            open(vision_path, "w").close()
            open(refresh_path, "w").close()

            with mock.patch.object(minimax, "VISION_FRAME_OUTPUT", os.path.join(temp_dir, "vision")):
                deleted = minimax.cleanup_generated_frames(
                    [vision_path],
                    [os.path.basename(refresh_path)],
                    input_directory=input_dir,
                    vision_segment=2,
                )

            self.assertEqual(set(deleted), {vision_path, refresh_path})
            self.assertFalse(os.path.exists(vision_path))
            self.assertFalse(os.path.exists(refresh_path))
            self.assertFalse(os.path.exists(vision_dir))

    def test_visual_request_cleans_frames_when_analysis_fails(self):
        with mock.patch.object(
            minimax,
            "_request_visual_end_state",
            side_effect=RuntimeError("vision unavailable"),
        ), mock.patch.object(
            minimax, "cleanup_generated_frames"
        ) as cleanup:
            with self.assertRaises(RuntimeError):
                minimax.request_visual_end_state("video.mp4", "", 3)

        cleanup.assert_called_once_with(vision_segment=3)

    def test_refresh_render_cleans_input_frame_when_render_fails(self):
        with mock.patch.object(
            minimax,
            "_render_segment_with_retries",
            side_effect=RuntimeError("render failed"),
        ), mock.patch.object(
            minimax, "cleanup_generated_frames"
        ) as cleanup:
            with self.assertRaises(RuntimeError):
                minimax.render_segment_with_retries(
                    6,
                    6.0,
                    0.5,
                    "prompt",
                    "previous.mp4",
                    6,
                    refresh_interval=6,
                )

        cleanup.assert_called_once_with(
            refresh_frame_names=["minimax_refresh_first_frame_0006.png"],
            input_directory=None,
        )


if __name__ == "__main__":
    unittest.main()
