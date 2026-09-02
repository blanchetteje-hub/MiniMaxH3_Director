import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import minimax


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


class AutoRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = load_json(minimax.INITIAL_WORKFLOW_FILE)
        cls.refresh = load_json(minimax.REFRESH_WORKFLOW_FILE)

    def test_refresh_argument_and_schedule(self):
        args = minimax.parse_args(["5", "50", "0.5", "--refresh", "5"])

        self.assertEqual(args.refresh, 5)
        self.assertEqual(
            [
                segment
                for segment in range(1, 16)
                if minimax.is_refresh_segment(segment, args.refresh)
            ],
            [5, 10, 15],
        )
        self.assertFalse(minimax.is_refresh_segment(1, 1))
        self.assertTrue(minimax.is_refresh_segment(2, 1))

    def test_refresh_defaults_to_every_sixth_segment(self):
        args = minimax.parse_args(["5", "50", "0.5"])

        self.assertEqual(args.refresh, 6)
        self.assertTrue(minimax.is_refresh_segment(6, args.refresh))

    def test_conditioning_mode_uses_the_refresh_schedule_as_source_of_truth(self):
        self.assertEqual(
            minimax.conditioning_mode_for_segment(1, 5),
            "initial",
        )
        self.assertEqual(
            minimax.conditioning_mode_for_segment(4, 5),
            "latent_continuation",
        )
        self.assertEqual(
            minimax.conditioning_mode_for_segment(5, 5),
            "clean_refresh",
        )
        self.assertEqual(
            minimax.conditioning_mode_for_segment(6, 5),
            "latent_continuation",
        )

    def test_refresh_conditioning_does_not_imply_a_hard_cut(self):
        self.assertEqual(
            minimax.conditioning_mode_for_segment(3, 3),
            "clean_refresh",
        )
        self.assertFalse(minimax.is_hard_cut_segment(3))

    def test_director_rules_leave_conditioning_details_to_segment_request(self):
        rules = minimax.build_director_rules(
            total_length=18,
            segment_length=6,
            total_segments=3,
            subject_definitions="",
            segment_number=2,
            beats_enabled=False,
        )

        self.assertIn("CONTINUATION AND VISUAL CONDITIONING", rules)
        self.assertIn("continuity database, NOT text", rules)
        self.assertIn("Silently internalize the opening state", rules)
        self.assertIn("Never mention the same continuity fact more than once", rules)
        self.assertIn("Integrate continuity facts naturally", rules)
        self.assertNotIn("VISUAL CONDITIONING MODE:", rules)
        self.assertNotIn("receives trailing H3 AV latent context", rules)
        self.assertNotIn("does NOT receive previous latent context", rules)

    def test_segment_requests_switch_back_to_latent_after_refresh(self):
        def request(segment, mode):
            return minimax.build_segment_request(
                segment=segment,
                total_segments=6,
                segment_length=6,
                total_length=36,
                beats=[],
                conditioning_mode=mode,
            )

        initial = request(1, "initial")
        refresh = request(5, "clean_refresh")
        after_refresh = request(6, "latent_continuation")

        self.assertIn("There is no previous-video context", initial)
        self.assertIn("does NOT receive previous latent context", refresh)
        self.assertIn("exact final rendered frame", refresh)
        self.assertIn("first_frame plus the clean registered", refresh)
        self.assertNotIn("receives trailing H3 AV latent context", refresh)

        self.assertIn("receives trailing H3 AV latent context", after_refresh)
        self.assertIn("plus its pinned final frame", after_refresh)
        self.assertNotIn("does NOT receive previous latent context", after_refresh)

    def test_picture_referenced_subjects_start_visible_only_for_initial_generation(self):
        initial = minimax.build_segment_request(1, 6, 6, 36, [], "initial")
        refresh = minimax.build_segment_request(5, 6, 6, 36, [], "clean_refresh")
        continuation = minimax.build_segment_request(
            6,
            6,
            6,
            36,
            [],
            "latent_continuation",
        )

        self.assertIn(
            "Every Picture-referenced Subject required in this segment must already "
            "occupy a defined position in the opening composition",
            initial,
        )
        self.assertIn("Do not describe such a Subject as entering frame", initial)
        self.assertIn("John walks toward the rack", initial)
        self.assertNotIn("Every Picture-referenced Subject required", refresh)
        self.assertNotIn("Every Picture-referenced Subject required", continuation)

    def test_refresh_argument_must_be_positive(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "50", "0.5", "--refresh", "0"])

    def test_refresh_interval_participates_in_run_fingerprint(self):
        every_five = minimax.build_run_config(
            5, 50, 0.5, 10, refresh_interval=5
        )
        every_six = minimax.build_run_config(
            5, 50, 0.5, 10, refresh_interval=6
        )

        self.assertEqual(every_five["refresh_interval"], 5)
        self.assertNotEqual(
            every_five["source_sha256"],
            every_six["source_sha256"],
        )

    def test_last_frame_is_extracted_atomically_into_comfy_input(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "segment_0004.mp4")
            with open(previous_video, "wb") as file:
                file.write(b"video")

            def create_frame(command, check):
                self.assertTrue(check)
                self.assertEqual(command[:4], ["ffmpeg", "-y", "-i", previous_video])
                self.assertIn("reverse", command)
                self.assertEqual(command[command.index("-frames:v") + 1], "1")
                with open(command[-1], "wb") as frame:
                    frame.write(b"png")

            with mock.patch("minimax.subprocess.run", side_effect=create_frame):
                frame_name = minimax.extract_refresh_first_frame(
                    previous_video,
                    5,
                    input_directory=directory,
                )

            self.assertEqual(frame_name, "minimax_refresh_first_frame_0005.png")
            with open(os.path.join(directory, frame_name), "rb") as frame:
                self.assertEqual(frame.read(), b"png")
            self.assertFalse(
                any(name.startswith(".refresh_0005_") for name in os.listdir(directory))
            )

    def test_refresh_workflow_sets_frame_references_and_segment_inputs(self):
        refresh = copy.deepcopy(self.refresh)
        initial = copy.deepcopy(self.initial)
        for image_number in range(1, 7):
            _, node = minimax.find_workflow_node(
                initial,
                f"Reference Image {image_number}",
                "initial test workflow",
                "LoadImage",
            )
            node["inputs"]["image"] = f"reference_{image_number}.png"

        with mock.patch(
            "minimax.load_workflow",
            side_effect=[refresh, initial],
        ), mock.patch("minimax.secrets.randbelow", return_value=123):
            prepared = minimax.prepare_refresh_workflow(
                6.0,
                0.4,
                "refresh prompt",
                "minimax_refresh_first_frame_0005.png",
                5,
                steps=9,
                lora_override=("refresh.safetensors", 0.6),
            )

        _, frame = minimax.find_workflow_node(
            prepared,
            minimax.REFRESH_FIRST_FRAME_NODE_NAME,
            "prepared refresh workflow",
            "LoadImage",
        )
        self.assertEqual(
            frame["inputs"]["image"],
            "minimax_refresh_first_frame_0005.png",
        )
        for image_number in range(1, 7):
            _, reference = minimax.find_workflow_node(
                prepared,
                f"Reference Image {image_number}",
                "prepared refresh workflow",
                "LoadImage",
            )
            self.assertEqual(
                reference["inputs"]["image"],
                f"reference_{image_number}.png",
            )
        _, duration = minimax.find_workflow_node(
            prepared, minimax.DURATION_NODE_NAME, "prepared refresh workflow"
        )
        _, prompt = minimax.find_workflow_node(
            prepared, minimax.PROMPT_NODE_NAME, "prepared refresh workflow"
        )
        _, scheduler = minimax.find_workflow_node(
            prepared, minimax.SCHEDULER_NODE_NAME, "prepared refresh workflow"
        )
        _, latent_save = minimax.find_workflow_node(
            prepared, minimax.H3_LATENT_SAVE_NODE_NAME, "prepared refresh workflow"
        )
        _, save_video = minimax.find_workflow_node(
            prepared, minimax.SAVE_VIDEO_NODE_NAME, "prepared refresh workflow"
        )
        self.assertEqual(duration["inputs"]["value"], 6.0)
        self.assertEqual(prompt["inputs"]["text"], "refresh prompt")
        self.assertEqual(scheduler["inputs"]["steps"], 9)
        self.assertEqual(latent_save["inputs"]["clip_index"], 5)
        self.assertEqual(save_video["inputs"]["filename_prefix"], "video/segment_0005")

    def test_refresh_omits_only_reference_incompatible_subject_pictures(self):
        refresh = copy.deepcopy(self.refresh)
        initial = copy.deepcopy(self.initial)
        definitions = (
            "<Subject 1> is Alpha, referenced in <Picture 1>.\n"
            "<Subject 2> is Beta, referenced in <Picture 2>."
        )
        state = minimax.continuity_state_for_registry(definitions)
        state["subjects"]["Alpha"]["persistent_structural_change"] = True

        with mock.patch(
            "minimax.load_workflow",
            return_value=refresh,
        ), mock.patch("minimax.prune_missing_reference_images"):
            prepared = minimax.prepare_refresh_workflow(
                6.0,
                0.4,
                "refresh prompt",
                "refresh_frame.png",
                5,
                reference_workflow=initial,
                continuity_state=state,
            )

        _, conditioning = minimax.find_workflow_node(
            prepared,
            minimax.REFRESH_CONDITIONING_NODE_NAME,
            "prepared refresh workflow",
        )
        self.assertNotIn(
            "ref_images.ref_image_0",
            conditioning["inputs"],
        )
        self.assertIn(
            "ref_images.ref_image_1",
            conditioning["inputs"],
        )

    def test_scheduled_segment_uses_refresh_then_next_segment_uses_append(self):
        common_patches = (
            mock.patch("minimax.extract_refresh_first_frame", return_value="frame.png"),
            mock.patch("minimax.prepare_refresh_workflow", return_value={"refresh": True}),
            mock.patch("minimax.prepare_append_workflow", return_value={"append": True}),
            mock.patch("minimax.queue_workflow", return_value="prompt-id"),
            mock.patch("minimax.wait_for_completion", return_value={}),
            mock.patch("minimax.get_video_path", return_value="rendered.mp4"),
            mock.patch("minimax.get_video_resolution", return_value=(1280, 720)),
        )
        entered = [patcher.start() for patcher in common_patches]
        extract, prepare_refresh, prepare_append = entered[:3]
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(common_patches)])

        minimax.render_segment_with_retries(
            5,
            6.0,
            0.4,
            "prompt 5",
            "segment_0004.mp4",
            8,
            refresh_interval=5,
        )
        extract.assert_called_once()
        prepare_refresh.assert_called_once()
        prepare_append.assert_not_called()

        extract.reset_mock()
        prepare_refresh.reset_mock()
        minimax.render_segment_with_retries(
            6,
            6.0,
            0.4,
            "prompt 6",
            "segment_0005.mp4",
            8,
            refresh_interval=5,
        )
        extract.assert_not_called()
        prepare_refresh.assert_not_called()
        prepare_append.assert_called_once()

    def test_refresh_notice_is_flushed_before_and_after_ffmpeg(self):
        events = []
        notice = (
            "AUTO REFRESH: segment 5 is using "
            "'Minimax_auto_refresh_API.json'."
        )

        def extract(*args, **kwargs):
            del args, kwargs
            events.append("ffmpeg")
            return "frame.png"

        def capture_print(*args, **kwargs):
            if args and args[0] == notice:
                self.assertTrue(kwargs.get("flush"))
                events.append("notice")

        with mock.patch(
            "minimax.extract_refresh_first_frame",
            side_effect=extract,
        ), mock.patch(
            "minimax.prepare_refresh_workflow",
            return_value={"refresh": True},
        ), mock.patch(
            "minimax.queue_workflow",
            return_value="prompt-id",
        ), mock.patch(
            "minimax.wait_for_completion",
            return_value={},
        ), mock.patch(
            "minimax.get_video_path",
            return_value="rendered.mp4",
        ), mock.patch(
            "minimax.get_video_resolution",
            return_value=(1280, 720),
        ), mock.patch("builtins.print", side_effect=capture_print):
            minimax.render_segment_with_retries(
                5,
                6.0,
                0.4,
                "prompt 5",
                "segment_0004.mp4",
                8,
                refresh_interval=5,
            )

        self.assertEqual(events[:3], ["notice", "ffmpeg", "notice"])


if __name__ == "__main__":
    unittest.main()
