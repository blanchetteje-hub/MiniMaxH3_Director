import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax


def _args(**overrides):
    values = {
        "model": "ministral",
        "lora": (),
        "repair": None,
        "generate_beats": None,
        "segment_length": 6.0,
        "total_length": 12.0,
        "megapixels": 0.5,
        "refresh": None,
        "resume": 1,
        "steps": 6,
        "context_frames": minimax.DEFAULT_CONTEXT_FRAMES,
        "ff": False,
        "vision_continuity": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ContinuitySchedulingTests(unittest.TestCase):
    def test_segment_one_allows_initial_continuity(self):
        self.assertEqual(
            minimax.validate_director_continuity({"segment": 1}),
            "initial",
        )

    def test_segment_two_rejects_missing_continuity_loudly(self):
        with self.assertRaisesRegex(
            RuntimeError,
            r"Segment 2 Director continuity is missing",
        ):
            minimax.request_segment_llm(
                {
                    "segment": 2,
                    "current_duration": 6.0,
                    "messages": [],
                },
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

    def test_segment_two_logs_and_accepts_completed_continuity(self):
        bundle = {
            "segment": 2,
            "active_beat_id": None,
            "current_duration": 6.0,
            "messages": [{"role": "user", "content": "Direct segment 2."}],
            "conditioning_mode": "latent_continuation",
            "opening_state": "Amy is beside the doorway.",
            "h3_opening_summary": "Amy is beside the doorway.",
            "continuity_source": "prompt",
            "opening_state_sha256": "opening-hash",
        }
        formatted = {
            "detailed_description": "[Shot 1] Amy looks toward the doorway.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        with mock.patch(
            "minimax.ask_llm",
            side_effect=["Amy looks toward the doorway.", formatted],
        ), mock.patch("builtins.print") as printed:
            minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertIn(
            "Segment 2 Director continuity source: prompt",
            "\n".join(
                str(call.args[0]) for call in printed.call_args_list if call.args
            ),
        )
        bundle["continuity_source"] = "vision"
        self.assertEqual(
            minimax.validate_director_continuity(bundle),
            "vision",
        )

    def test_prompt_continuity_precedes_next_director_without_waiting_for_render(self):
        args = _args()
        render_one_started = threading.Event()
        release_render_one = threading.Event()
        opening_started = threading.Event()
        release_opening = threading.Event()
        director_two_started = threading.Event()
        director_two_openings = []

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "Amy walks toward a doorway."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "<Subject 1> is Amy, referenced in <Picture 1>."
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            segment = int(bundle["segment"])
            if segment == 2:
                director_two_started.set()
                director_two_openings.append(bundle.get("opening_state"))
            payload = dict(bundle)
            payload["llm_result"] = {
                "detailed_description": f"[Shot 1] Segment {segment} continues.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [],
            }
            return payload

        def opening_state(*_args, **_kwargs):
            opening_started.set()
            if not release_opening.wait(5):
                raise AssertionError("test did not release continuity opening")
            return "Amy is beside the doorway."

        def render(segment, *_args, **kwargs):
            kwargs["render_started_event"].set()
            if int(segment) == 1:
                render_one_started.set()
                if not release_render_one.wait(5):
                    raise AssertionError("test did not release Segment 1 render")
            return (None, f"segment_{int(segment):04d}.mp4", 1280, 720, 0.5)

        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.configure_reference_image_overrides"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch(
                "minimax.parse_story_gen_rules",
                return_value=("Amy walks toward a doorway.", ""),
            ),
            mock.patch(
                "minimax.parse_story_beat_instructions",
                return_value=("Amy walks toward a doorway.", []),
            ),
            mock.patch("minimax.os.path.isfile", return_value=False),
            mock.patch("minimax.load_phrase_exclusions", return_value=[]),
            mock.patch("minimax.reset_prompt_history"),
            mock.patch("minimax.load_or_generate_beats", return_value=[]),
            mock.patch("minimax.load_story_arc", return_value={"phases": []}),
            mock.patch("minimax.validate_runtime_environment"),
            mock.patch("minimax.load_workflow", return_value={}),
            mock.patch("minimax.validate_workflow"),
            mock.patch("minimax.verify_reference_images"),
            mock.patch("minimax.verify_global_loras"),
            mock.patch("minimax.save_generation_state"),
            mock.patch("minimax.request_segment_llm", side_effect=request_segment),
            mock.patch(
                "minimax.request_combined_continuity",
                return_value={"reduced_state": {"environment": {"location": "road"}}},
            ),
            mock.patch(
                "minimax.request_continuity_opening_state",
                side_effect=opening_state,
            ),
            mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
            mock.patch("minimax.record_completed_segment", return_value={}),
            mock.patch("minimax.render_segment_with_retries", side_effect=render),
            mock.patch("minimax.stitch_videos"),
        )

        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as summary_executor:
            with ThreadPoolExecutor(max_workers=1) as prefetch_executor:
                with ThreadPoolExecutor(max_workers=1) as render_executor:
                    with ThreadPoolExecutor(max_workers=1) as main_executor:
                        run = main_executor.submit(
                            minimax._run_main,
                            summary_executor,
                            prefetch_executor,
                            render_executor,
                        )
                        self.assertTrue(render_one_started.wait(5))
                        self.assertTrue(opening_started.wait(5))
                        self.assertFalse(
                            director_two_started.is_set(),
                            "Segment 2 Director started before Segment 1 opening state",
                        )
                        release_opening.set()
                        self.assertTrue(director_two_started.wait(5))
                        self.assertEqual(
                            director_two_openings,
                            ["Amy is beside the doorway."],
                        )
                        self.assertFalse(
                            release_render_one.is_set(),
                            "Segment 1 render was incorrectly required for prompt continuity",
                        )
                        release_render_one.set()
                        run.result(timeout=10)

    def test_background_render_handoff_uses_immediately_prior_segment(self):
        args = _args(total_length=18.0)
        segment_two_started = threading.Event()
        release_segment_two = threading.Event()
        segment_three_started = threading.Event()
        render_sources = []

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "Amy walks toward a doorway."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "<Subject 1> is Amy, referenced in <Picture 1>."
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            payload = dict(bundle)
            payload["llm_result"] = {
                "detailed_description": (
                    f"[Shot 1] Segment {bundle['segment']} continues."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [],
            }
            return payload

        def render(segment, *render_args, **kwargs):
            render_sources.append((int(segment), render_args[3]))
            kwargs["render_started_event"].set()
            if int(segment) == 2:
                segment_two_started.set()
                if not release_segment_two.wait(5):
                    raise AssertionError("test did not release Segment 2 render")
            if int(segment) == 3:
                segment_three_started.set()
            return (None, f"segment_{int(segment):04d}.mp4", 1280, 720, 0.5)

        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.configure_reference_image_overrides"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch(
                "minimax.parse_story_gen_rules",
                return_value=("Amy walks toward a doorway.", ""),
            ),
            mock.patch(
                "minimax.parse_story_beat_instructions",
                return_value=("Amy walks toward a doorway.", []),
            ),
            mock.patch("minimax.os.path.isfile", return_value=False),
            mock.patch("minimax.load_phrase_exclusions", return_value=[]),
            mock.patch("minimax.reset_prompt_history"),
            mock.patch("minimax.load_or_generate_beats", return_value=[]),
            mock.patch("minimax.load_story_arc", return_value={"phases": []}),
            mock.patch("minimax.validate_runtime_environment"),
            mock.patch("minimax.load_workflow", return_value={}),
            mock.patch("minimax.validate_workflow"),
            mock.patch("minimax.verify_reference_images"),
            mock.patch("minimax.verify_global_loras"),
            mock.patch("minimax.save_generation_state"),
            mock.patch("minimax.request_segment_llm", side_effect=request_segment),
            mock.patch(
                "minimax.request_combined_continuity",
                return_value={"reduced_state": {"environment": {"location": "road"}}},
            ),
            mock.patch(
                "minimax.request_continuity_opening_state",
                return_value="Amy is beside the doorway.",
            ),
            mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
            mock.patch("minimax.record_completed_segment", return_value={}),
            mock.patch("minimax.render_segment_with_retries", side_effect=render),
            mock.patch("minimax.stitch_videos"),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as summary_executor:
            with ThreadPoolExecutor(max_workers=1) as render_executor:
                with ThreadPoolExecutor(max_workers=1) as main_executor:
                    run = main_executor.submit(
                        minimax._run_main,
                        summary_executor,
                        None,
                        render_executor,
                    )
                    self.assertTrue(segment_two_started.wait(5))
                    self.assertFalse(
                        segment_three_started.is_set(),
                        "Segment 3 started before Segment 2 finished rendering",
                    )
                    release_segment_two.set()
                    run.result(timeout=10)

        self.assertEqual(
            render_sources,
            [
                (1, None),
                (2, os.path.abspath("segment_0001.mp4")),
                (3, os.path.abspath("segment_0002.mp4")),
            ],
        )


if __name__ == "__main__":
    unittest.main()
