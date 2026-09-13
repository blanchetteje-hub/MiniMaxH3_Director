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
                "/tmp/video-output", "segment_0001_final.png"
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
            ):
                prepared = minimax.prepare_append_workflow(
                    6.0,
                    "prompt",
                    previous_video,
                    2,
                )

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


if __name__ == "__main__":
    unittest.main()
