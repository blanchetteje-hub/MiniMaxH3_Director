import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.acceptance import run_acceptance


class AcceptanceRunnerTests(unittest.TestCase):
    def test_director_plan_stages_expanded_story_for_director_only_run(self):
        plan_dir = (
            Path(__file__).parent
            / "acceptance"
            / "fixtures"
            / "tavern_run21_plan"
        )
        expanded_story = (plan_dir / "expanded_story.txt").read_text(
            encoding="utf-8"
        )

        class FakeProcess:
            stdout = ()

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.jpg"
            image.write_bytes(b"image")
            output_dir = root / "results"

            def inspect_staged_plan(command, cwd, **_kwargs):
                workspace = Path(cwd)
                for filename in (
                    "story_arc.json",
                    "beats.txt",
                    "expanded_story.txt",
                ):
                    self.assertTrue((workspace / filename).is_file())
                self.assertEqual(
                    (workspace / "expanded_story.txt").read_text(
                        encoding="utf-8"
                    ),
                    expanded_story,
                )
                self.assertIn("--director-only", command)
                self.assertNotIn("--generate-beats", command)
                self.assertNotIn("--generate-prompts", command)
                return FakeProcess()

            incomplete_dir = root / "incomplete_plan"
            incomplete_dir.mkdir()
            for filename in ("story_arc.json", "beats.txt"):
                (incomplete_dir / filename).write_text("plan\n", encoding="utf-8")

            with (
                patch.object(run_acceptance, "git_revision", return_value="test"),
                patch.object(
                    run_acceptance.subprocess,
                    "Popen",
                    side_effect=inspect_staged_plan,
                ) as popen,
            ):
                result = run_acceptance.main([
                    "--image1", str(image),
                    "--output-dir", str(output_dir),
                    "--director-plan-dir", str(plan_dir),
                ])

                with self.assertRaisesRegex(
                    FileNotFoundError, "expanded_story.txt"
                ):
                    run_acceptance.main([
                        "--image1", str(image),
                        "--output-dir", str(root / "incomplete_results"),
                        "--director-plan-dir", str(incomplete_dir),
                    ])
                self.assertEqual(popen.call_count, 1)

            self.assertEqual(result, 2)  # No Director prompts were generated.
            report = json.loads(
                (output_dir / "acceptance_run.json").read_text(encoding="utf-8")
            )
            artifact = output_dir / report["artifacts"]["expanded_story.txt"]
            self.assertEqual(artifact.read_text(encoding="utf-8"), expanded_story)

    def test_locked_amy_benchmark_loads(self):
        benchmark = run_acceptance.load_benchmark(
            run_acceptance.DEFAULT_BENCHMARK
        )
        self.assertEqual(benchmark["story_id"], "amy_zombie_house")
        self.assertEqual(len(benchmark["beats"]), 8)
        self.assertEqual(
            [beat["mode"] for beat in benchmark["beats"]],
            [
                "initial",
                "append",
                "append",
                "append",
                "append",
                "append",
                "refresh",
                "append",
            ],
        )

    def test_parse_h3_prompts(self):
        log = """
# ================================================================ DIRECTOR REQUEST 2: H3 prompt - SEGMENT 1
subject_definitions:
<Subject 1> is Amy.
detailed_description: hello
# ================================================================ END H3 PROMPT - SEGMENT 1
noise
# ================================================================ DIRECTOR REQUEST 2: H3 prompt - SEGMENT 2
detailed_description: world
# ================================================================ END H3 PROMPT - SEGMENT 2
"""
        prompts = run_acceptance.parse_h3_prompts(log)
        self.assertEqual(
            prompts[1],
            "subject_definitions:\n<Subject 1> is Amy.\ndetailed_description: hello",
        )
        self.assertEqual(prompts[2], "detailed_description: world")

    def test_parse_h3_prompts_allows_interleaved_start_marker(self):
        log = (
            "# DIRECTOR REQUEST 2: H3 prompt - SEGMENT 5Added States: \n"
            "subject_definitions: Mira\n"
            "detailed_description: Mira opens the gate.\n"
            "# END H3 PROMPT - SEGMENT 5\n"
            "# DIRECTOR REQUEST 2: H3 prompt - SEGMENT 15Added States: \n"
            "detailed_description: Mira returns.\n"
            "# END H3 PROMPT - SEGMENT 15\n"
        )
        prompts = run_acceptance.parse_h3_prompts(log)
        self.assertEqual(set(prompts), {5, 15})
        self.assertIn("Mira opens the gate.", prompts[5])
        self.assertNotIn("Added States", prompts[5])
        self.assertEqual(prompts[15], "detailed_description: Mira returns.")

    def test_parse_h3_prompts_allows_trailing_text_after_end_marker(self):
        log = """
# ================================================================ DIRECTOR REQUEST 2: H3 prompt - SEGMENT 2
detailed_description: world
# ================================================================ END H3 PROMPT - SEGMENT 2Added States:
"""
        prompts = run_acceptance.parse_h3_prompts(log)
        self.assertEqual(prompts[2], "detailed_description: world")

    def test_acceptance_child_env_forces_unbuffered_utf8_output(self):
        env = run_acceptance.acceptance_child_env()
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")

    def test_acceptance_child_env_uses_isolated_video_output(self):
        workspace = Path("temporary_workspace")
        env = run_acceptance.acceptance_child_env(workspace)
        self.assertEqual(
            env["MINIMAX_VIDEO_OUTPUT"],
            str(workspace / "output" / "video"),
        )

    def test_console_echo_replaces_unencodable_host_characters(self):
        class FakeConsole:
            encoding = "cp1252"

            def __init__(self):
                self.value = ""

            def write(self, value):
                value.encode(self.encoding)
                self.value += value

            def flush(self):
                pass

        console = FakeConsole()
        original = run_acceptance.sys.stdout
        try:
            run_acceptance.sys.stdout = console
            run_acceptance._console_write_utf8_safe("before ‑ after\n")
        finally:
            run_acceptance.sys.stdout = original

        self.assertEqual(console.value, "before ? after\n")

    def test_video_command_passes_segment_count_instead_of_seconds(self):
        benchmark = run_acceptance.load_benchmark(run_acceptance.DEFAULT_BENCHMARK)
        command, _ = run_acceptance.build_command(
            "python", benchmark, Path("amy.jpg"), "gpt", .5, [],
        )
        args = __import__("minimax").parse_args(command[2:])
        self.assertEqual(args.total_segments, len(benchmark["beats"]))
        self.assertEqual(args.total_length, args.segment_length * len(benchmark["beats"]))

    def test_planning_only_command_uses_generate_beats(self):
        benchmark = run_acceptance.load_benchmark(
            run_acceptance.DEFAULT_BENCHMARK
        )
        command, refresh_interval = run_acceptance.build_command(
            "python",
            benchmark,
            Path("amy.jpg"),
            "gpt",
            0.5,
            [],
            planning_only=True,
        )
        self.assertEqual(
            command,
            [
                "python",
                "minimax.py",
                "--generate-beats",
                "8",
                "8",
                "--model",
                "gpt",
            ],
        )
        self.assertIsNone(refresh_interval)

    def test_workspace_uses_gold_story_and_subjects_without_stale_state(self):
        benchmark = run_acceptance.load_benchmark(
            run_acceptance.DEFAULT_BENCHMARK
        )
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            for name in ("minimax.py", "mistral_formatter.py", "qwen_formatter.py"):
                (source / name).write_text("# fixture\n", encoding="utf-8")
            (source / "generation_state.json").write_text("{}", encoding="utf-8")
            destination = Path(temporary) / "work"

            run_acceptance.prepare_workspace(source, destination, benchmark)

            self.assertEqual(
                (destination / "story.txt").read_text(encoding="utf-8").strip(),
                benchmark["story_text"].strip(),
            )
            self.assertIn(
                "<Subject 1> is Amy",
                (destination / "subjects.txt").read_text(encoding="utf-8"),
            )
            self.assertFalse((destination / "generation_state.json").exists())


if __name__ == "__main__":
    unittest.main()
