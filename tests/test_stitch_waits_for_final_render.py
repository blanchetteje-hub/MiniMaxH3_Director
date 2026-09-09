import copy
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax


def _make_args(**overrides):
    base = {
        "model": "ministral",
        "lora": (),
        "repair": None,
        "generate_beats": None,
        "segment_length": 6.0,
        "total_length": 6.0,
        "megapixels": 0.5,
        "refresh": None,
        "resume": 1,
        "steps": 6,
        "context_frames": minimax.DEFAULT_CONTEXT_FRAMES,
        "ff": False,
        # The final segment must skip vision continuity regardless of cadence;
        # it has no later segment that can consume the resulting state.
        "vision_continuity": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _director_result(segment):
    return {
        "detailed_description": f"[Shot {segment}] A courier walks forward.",
        "overall_soundscape": "Footsteps cross the pavement.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [],
    }


class StitchWaitsForFinalRenderTests(unittest.TestCase):
    """The final segment renders in the background when its vision-continuity
    cadence is skipped; ffmpeg must not start until that render (and its
    done-callback that appends the video path) has finished."""

    def test_stitch_waits_for_backgrounded_final_segment_render(self):
        args = _make_args()
        render_started = threading.Event()
        release_render = threading.Event()
        stitch_ran = threading.Event()
        text_continuity = mock.Mock(return_value={"reduced_state": {}})
        opening_continuity = mock.Mock(return_value="OPENING")

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "A courier makes a delivery."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "<Subject 1> is The Courier, referenced in <Picture 1>."
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            payload = dict(bundle)
            payload["llm_result"] = _director_result(bundle["segment"])
            return payload

        def block_render(*_args, **kwargs):
            kwargs["render_started_event"].set()
            render_started.set()
            if not release_render.wait(5):
                raise AssertionError("test did not release the ComfyUI render")
            return (None, "segment_0001.mp4", 1280, 720, 0.5)

        def stitching(paths):
            # Deterministic race check: if ffmpeg is reached before the render
            # is released, the final segment was still being rendered (and its
            # path was not yet appended to generated_video_paths).
            if not release_render.is_set():
                raise AssertionError(
                    "ffmpeg ran before the final segment finished rendering"
                )
            if not paths:
                raise AssertionError(
                    "ffmpeg ran with no completed segment video paths"
                )
            stitch_ran.set()

        dino_continuity = mock.patch(
            "minimax.update_dino_continuity_references",
            return_value={},
        )
        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.configure_reference_image_overrides"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch(
                "minimax.parse_story_gen_rules",
                return_value=("A courier makes a delivery.", ""),
            ),
            mock.patch(
                "minimax.parse_story_beat_instructions",
                return_value=("A courier makes a delivery.", []),
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
                "minimax.request_text_continuity",
                new=text_continuity,
            ),
            mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
            mock.patch(
                "minimax.request_continuity_opening_state",
                new=opening_continuity,
            ),
            dino_continuity,
            mock.patch("minimax.record_completed_segment", return_value={}),
            mock.patch(
                "minimax.render_segment_with_retries",
                side_effect=block_render,
            ),
            mock.patch("minimax.stitch_videos", side_effect=stitching),
        )
        dino_continuity_mock = None
        for patcher in patches:
            started = patcher.start()
            if patcher is dino_continuity:
                dino_continuity_mock = started
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as main_executor:
            with ThreadPoolExecutor(max_workers=1) as summary_executor:
                with ThreadPoolExecutor(max_workers=1) as render_executor:
                    run = main_executor.submit(
                        minimax._run_main,
                        summary_executor,
                        None,
                        render_executor,
                    )
                    # Wait until segment 1 has been submitted to ComfyUI.
                    self.assertTrue(
                        render_started.wait(5),
                        "the ComfyUI render never started",
                    )
                    # The render is still in flight; ffmpeg must not run yet.
                    self.assertFalse(
                        stitch_ran.is_set(),
                        "ffmpeg ran before the final segment finished rendering",
                    )
                    release_render.set()
                    run.result(timeout=10)

        # Once the task completed, ffmpeg must have run.
        self.assertTrue(stitch_ran.is_set())
        text_continuity.assert_not_called()
        opening_continuity.assert_not_called()
        dino_continuity_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
