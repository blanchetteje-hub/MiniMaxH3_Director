import os
import tempfile
import unittest
from unittest import mock

import minimax


class StitchingTests(unittest.TestCase):
    def test_trim_video_start_removes_exactly_two_frames_at_24_fps(self):
        with mock.patch("minimax.subprocess.run") as run:
            minimax.trim_video_start(
                "segment_0002.mp4",
                "trimmed_segment_0002.mp4",
                minimax.TRIM_SECONDS_AFTER_FIRST,
            )

        run.assert_called_once_with(
            [
                "ffmpeg", "-y",
                "-i", "segment_0002.mp4",
                "-ss", "0.083333",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                "trimmed_segment_0002.mp4",
            ],
            check=True,
        )

    def test_stitching_keeps_first_segment_and_trims_every_later_segment(self):
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
            ), mock.patch(
                "minimax.trim_video_start",
            ) as trim, mock.patch(
                "minimax.subprocess.run",
                side_effect=capture_concat_list,
            ) as run:
                minimax.stitch_videos(video_paths)

        run.assert_called_once()
        self.assertEqual(
            trim.call_args_list,
            [
                mock.call(
                    os.path.abspath(video_paths[1]),
                    os.path.join(
                        os.path.dirname(os.path.abspath(video_paths[1])),
                        "trimmed_segment_0002.mp4",
                    ),
                    2 / 24,
                ),
                mock.call(
                    os.path.abspath(video_paths[2]),
                    os.path.join(
                        os.path.dirname(os.path.abspath(video_paths[2])),
                        "trimmed_segment_0003.mp4",
                    ),
                    2 / 24,
                ),
            ],
        )
        self.assertEqual(captured["command"][-3:-1], ["-c", "copy"])
        self.assertEqual(
            captured["contents"].splitlines(),
            [
                f"file '{os.path.abspath(video_paths[0]).replace(chr(92), '/')}'",
                f"file '{os.path.join(directory, 'trimmed_segment_0002.mp4').replace(chr(92), '/')}'",
                f"file '{os.path.join(directory, 'trimmed_segment_0003.mp4').replace(chr(92), '/')}'",
            ],
        )
        self.assertEqual(captured["contents"].count("trimmed_"), 2)

    def test_successful_stitch_deletes_created_trimmed_videos(self):
        with tempfile.TemporaryDirectory() as directory:
            video_paths = [
                os.path.join(directory, "segment_0001.mp4"),
                os.path.join(directory, "segment_0002.mp4"),
                os.path.join(directory, "segment_0003.mp4"),
            ]
            trimmed_paths = [
                os.path.join(directory, "trimmed_segment_0002.mp4"),
                os.path.join(directory, "trimmed_segment_0003.mp4"),
            ]

            def create_trimmed_video(_input_path, output_path, _trim_seconds):
                with open(output_path, "wb") as trimmed_video:
                    trimmed_video.write(b"trimmed")

            with mock.patch.object(minimax, "VIDEO_OUTPUT", directory), mock.patch.object(
                minimax, "FINAL_VIDEO", os.path.join(directory, "final.mp4")
            ), mock.patch(
                "minimax.trim_video_start", side_effect=create_trimmed_video
            ), mock.patch("minimax.subprocess.run"):
                minimax.stitch_videos(video_paths)

            for trimmed_path in trimmed_paths:
                self.assertFalse(os.path.exists(trimmed_path))

    def test_failed_final_stitch_keeps_created_trimmed_videos(self):
        with tempfile.TemporaryDirectory() as directory:
            video_paths = [
                os.path.join(directory, "segment_0001.mp4"),
                os.path.join(directory, "segment_0002.mp4"),
            ]
            trimmed_path = os.path.join(directory, "trimmed_segment_0002.mp4")

            def create_trimmed_video(_input_path, output_path, _trim_seconds):
                with open(output_path, "wb") as trimmed_video:
                    trimmed_video.write(b"trimmed")

            with mock.patch.object(minimax, "VIDEO_OUTPUT", directory), mock.patch.object(
                minimax, "FINAL_VIDEO", os.path.join(directory, "final.mp4")
            ), mock.patch(
                "minimax.trim_video_start", side_effect=create_trimmed_video
            ), mock.patch(
                "minimax.subprocess.run", side_effect=RuntimeError("final stitch failed")
            ):
                with self.assertRaisesRegex(RuntimeError, "final stitch failed"):
                    minimax.stitch_videos(video_paths)

            self.assertTrue(os.path.exists(trimmed_path))


if __name__ == "__main__":
    unittest.main()
