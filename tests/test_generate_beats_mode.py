import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import desktop_app
import minimax


class GenerateBeatsCliTests(unittest.TestCase):
    def test_parse_args_accepts_count_without_video_positionals(self):
        args = minimax.parse_args(["--generate-beats", "12", "--model", "qwen"])

        self.assertEqual(args.generate_beats, 12)
        self.assertEqual(args.model, "qwen")
        self.assertIsNone(args.segment_length)
        self.assertIsNone(args.total_length)
        self.assertIsNone(args.megapixels)

    def test_parse_args_requires_a_positive_beat_count(self):
        for arguments in (["--generate-beats"], ["--generate-beats", "0"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                minimax.parse_args(arguments)

    def test_story_only_mode_forces_planning_and_stops_before_comfyui(self):
        args = SimpleNamespace(
            generate_beats=7,
            segment_length=None,
            total_length=None,
            megapixels=None,
            resume=1,
            repair=None,
            model="ministral",
            lora=[],
        )
        generated = mock.Mock(return_value=[f"Beat {number}" for number in range(1, 8)])

        def fake_load(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "A complete source story."
            return ""

        with mock.patch("minimax.parse_args", return_value=args), mock.patch(
            "minimax.load_text_file", side_effect=fake_load
        ), mock.patch("minimax.load_or_generate_beats", generated), mock.patch(
            "minimax.reset_prompt_history"
        ), mock.patch(
            "minimax.validate_runtime_environment"
        ) as runtime_validation, mock.patch(
            "minimax.load_story_arc"
        ) as load_arc, mock.patch(
            "builtins.print"
        ) as print_output:
            result = minimax._run_main(mock.Mock())

        self.assertIsNone(result)
        self.assertTrue(
            any(
                call.args
                and call.args[0]
                == "Generating the story arc and beats based on story.txt"
                for call in print_output.call_args_list
            )
        )
        self.assertEqual(generated.call_args.args[2], 7)
        self.assertTrue(generated.call_args.kwargs["force_generate"])
        runtime_validation.assert_not_called()
        load_arc.assert_not_called()

    def test_story_only_mode_rejects_an_empty_story_with_exact_error(self):
        args = SimpleNamespace(
            generate_beats=3,
            segment_length=None,
            total_length=None,
            megapixels=None,
            resume=1,
            repair=None,
            model="ministral",
            lora=[],
        )
        with mock.patch("minimax.parse_args", return_value=args), mock.patch(
            "minimax.load_text_file", return_value="  \n"
        ), mock.patch("minimax.load_or_generate_beats") as generated:
            with self.assertRaisesRegex(
                ValueError,
                r"^story\.txt must have a story defined\.$",
            ):
                minimax._run_main(mock.Mock())

        generated.assert_not_called()

    def test_force_generate_replaces_existing_beats_and_cached_arc(self):
        generated = mock.Mock(return_value=["New beat"])
        with mock.patch("minimax.load_text_file", return_value="1. Old beat"), mock.patch(
            "minimax.generate_beats_from_story", generated
        ):
            result = minimax.load_or_generate_beats(
                "beats.txt",
                "Story",
                1,
                force_generate=True,
            )

        self.assertEqual(result, ["New beat"])
        self.assertFalse(generated.call_args.kwargs["reuse_story_arc"])

    def test_force_generate_allows_a_missing_beats_file(self):
        generated = mock.Mock(return_value=["New beat"])
        with mock.patch("minimax.load_text_file", return_value="") as load, mock.patch(
            "minimax.generate_beats_from_story", generated
        ):
            result = minimax.load_or_generate_beats(
                "beats.txt",
                "Story",
                1,
                force_generate=True,
            )

        self.assertEqual(result, ["New beat"])
        load.assert_called_once_with("beats.txt", required=False)


class GenerateBeatsDesktopTests(unittest.TestCase):
    def make_bridge(self):
        return desktop_app.MiniMaxBridge(
            script_path=Path(__file__),
            python_executable="python-test",
        )

    def test_story_command_contains_only_count_and_formatter_options(self):
        command = self.make_bridge().build_command(
            {"beat_count": "9", "model": "qwen"},
            generate_beats=True,
        )

        self.assertEqual(
            command,
            [
                "python-test",
                "-u",
                str(Path(__file__).resolve()),
                "--generate-beats",
                "9",
                "--model",
                "qwen",
            ],
        )

    @mock.patch("desktop_app.subprocess.Popen")
    def test_empty_story_is_rejected_before_starting_process(self, popen):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as directory:
            story_path = Path(directory) / "story.txt"
            story_path.write_text(" \n", encoding="utf-8")
            with mock.patch.dict(
                desktop_app.FILE_DEFINITIONS,
                {"story": ("Story", story_path, True)},
                clear=True,
            ):
                result = bridge.start_generation(
                    {"beat_count": "4", "model": "ministral"},
                    True,
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "story.txt must have a story defined.")
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
