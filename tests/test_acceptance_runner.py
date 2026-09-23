import json
from pathlib import Path
import tempfile
import unittest

from tests.acceptance import run_acceptance


class AcceptanceRunnerTests(unittest.TestCase):
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

    def test_refresh_schedule_maps_to_interval_seven(self):
        benchmark = run_acceptance.load_benchmark(
            run_acceptance.DEFAULT_BENCHMARK
        )
        self.assertEqual(
            run_acceptance.infer_refresh_interval(benchmark["beats"]),
            7,
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

    def test_acceptance_child_env_forces_unbuffered_output(self):
        env = run_acceptance.acceptance_child_env()
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")

    def test_planning_only_command_uses_generate_beats(self):
        benchmark = run_acceptance.load_benchmark(
            run_acceptance.DEFAULT_BENCHMARK
        )
        command, refresh_interval = run_acceptance.build_command(
            "python",
            benchmark,
            Path("amy.jpg"),
            "mistral",
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
                "--model",
                "mistral",
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
