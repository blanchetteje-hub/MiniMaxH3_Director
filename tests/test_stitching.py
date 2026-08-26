import os
import tempfile
import unittest
from unittest import mock

import minimax


class StitchingTests(unittest.TestCase):
    def test_stitching_concatenates_every_segment_without_trimming(self):
        with tempfile.TemporaryDirectory() as directory:
            video_paths = [
                os.path.join(directory, "segment_0001.mp4"),
                os.path.join(directory, "segment_0002.mp4"),
                os.path.join(directory, "segment_0003.mp4"),
            ]
            captured = {}

            def capture_concat_list(command, check):
                self.assertTrue(check)
                list_path = command[command.index("-i") + 1]
                with open(list_path, "r", encoding="utf-8") as concat_file:
                    captured["contents"] = concat_file.read()
                captured["command"] = command

            with mock.patch.object(minimax, "VIDEO_OUTPUT", directory), mock.patch.object(
                minimax,
                "FINAL_VIDEO",
                os.path.join(directory, "final.mp4"),
            ), mock.patch("minimax.subprocess.run", side_effect=capture_concat_list) as run:
                minimax.stitch_videos(video_paths)

        run.assert_called_once()
        self.assertNotIn("-ss", captured["command"])
        self.assertEqual(captured["command"][-3:-1], ["-c", "copy"])
        self.assertEqual(
            captured["contents"].splitlines(),
            [
                f"file '{os.path.abspath(path).replace(chr(92), '/')}'"
                for path in video_paths
            ],
        )
        self.assertNotIn("trimmed_", captured["contents"])


if __name__ == "__main__":
    unittest.main()
