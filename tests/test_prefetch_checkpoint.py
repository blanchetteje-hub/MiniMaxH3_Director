import copy
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax


class PrefetchCheckpointTests(unittest.TestCase):
    def test_next_h3_prompt_is_checkpointed_while_comfyui_render_is_running(self):
        args = SimpleNamespace(
            model="ministral",
            lora=(),
            repair=None,
            segment_length=6.0,
            total_length=12.0,
            megapixels=0.5,
            refresh=None,
            resume=1,
            steps=6,
            context_frames=minimax.DEFAULT_CONTEXT_FRAMES,
            ff=False,
        )
        beats = [
            minimax.BeatDefinition("The courier starts the delivery."),
            minimax.BeatDefinition("The courier completes the delivery."),
        ]
        subjects = (
            "<Subject 1> is The Courier, referenced in <Picture 1>."
        )
        first_result = {
            "detailed_description": "[Shot 1] The Courier starts walking.",
            "overall_soundscape": "Footsteps cross the pavement.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }
        next_result = {
            "detailed_description": "[Shot 2] The Courier reaches the door.",
            "overall_soundscape": "Footsteps stop at the doorway.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [2],
        }
        render_started = threading.Event()
        release_render = threading.Event()
        prefetched_checkpoint_saved = threading.Event()
        saved_states = []
        saved_states_lock = threading.Lock()
        checkpoint_directory = tempfile.TemporaryDirectory()
        self.addCleanup(checkpoint_directory.cleanup)
        checkpoint_path = os.path.join(
            checkpoint_directory.name,
            "generation_state.json",
        )
        save_checkpoint_to_disk = minimax.save_generation_state

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "A courier makes a delivery."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return subjects
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            payload = dict(bundle)
            payload["llm_result"] = (
                first_result if bundle["segment"] == 1 else next_result
            )
            return payload

        def block_render(*_args, **kwargs):
            kwargs["render_started_event"].set()
            render_started.set()
            if not release_render.wait(5):
                raise AssertionError("test did not release the ComfyUI render")
            raise RuntimeError("stop after checkpoint timing assertion")

        def capture_checkpoint(state, path=minimax.GENERATION_STATE_FILE):
            del path
            snapshot = copy.deepcopy(state)
            save_checkpoint_to_disk(snapshot, checkpoint_path)
            with open(checkpoint_path, "r", encoding="utf-8") as checkpoint_file:
                persisted_snapshot = json.load(checkpoint_file)
            with saved_states_lock:
                saved_states.append(persisted_snapshot)
            if "prefetched_next_prompt" in persisted_snapshot:
                self.assertTrue(render_started.is_set())
                self.assertFalse(release_render.is_set())
                prefetched_checkpoint_saved.set()

        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch("minimax.os.path.isfile", return_value=False),
            mock.patch("minimax.reset_prompt_history"),
            mock.patch("minimax.load_or_generate_beats", return_value=beats),
            mock.patch("minimax.load_story_arc", return_value={"phases": []}),
            mock.patch("minimax.validate_runtime_environment"),
            mock.patch("minimax.load_workflow", return_value={}),
            mock.patch("minimax.validate_workflow"),
            mock.patch("minimax.verify_reference_images"),
            mock.patch("minimax.verify_global_loras"),
            mock.patch("minimax.save_generation_state", side_effect=capture_checkpoint),
            mock.patch("minimax.request_segment_llm", side_effect=request_segment),
            mock.patch(
                "minimax.request_structured_continuity_state",
                return_value=minimax.continuity_state_for_registry(subjects),
            ),
            mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
            mock.patch(
                "minimax.render_segment_with_retries",
                side_effect=block_render,
            ),
            mock.patch("builtins.print"),
        )

        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as summary_executor, \
                ThreadPoolExecutor(max_workers=1) as prefetch_executor, \
                ThreadPoolExecutor(max_workers=1) as render_executor, \
                ThreadPoolExecutor(max_workers=1) as main_executor:
            run = main_executor.submit(
                minimax._run_main,
                summary_executor,
                prefetch_executor,
                render_executor,
            )
            try:
                self.assertTrue(
                    prefetched_checkpoint_saved.wait(5),
                    "the next H3 prompt was not saved before render completion",
                )
            finally:
                release_render.set()
            with self.assertRaisesRegex(
                RuntimeError,
                "stop after checkpoint timing assertion",
            ):
                run.result(timeout=5)

        with saved_states_lock:
            prefetch_snapshots = [
                state["prefetched_next_prompt"]
                for state in saved_states
                if "prefetched_next_prompt" in state
            ]
        self.assertTrue(prefetch_snapshots)
        saved_prefetch = prefetch_snapshots[0]
        self.assertEqual(saved_prefetch["segment_number"], 2)
        self.assertEqual(saved_prefetch["llm_result"], next_result)
        self.assertIsInstance(saved_prefetch["fingerprint"], str)
        self.assertTrue(saved_prefetch["fingerprint"])


if __name__ == "__main__":
    unittest.main()
