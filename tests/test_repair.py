import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import minimax


SUBJECTS = "<Subject 1> is Alice, female (S1), referenced in <Picture 1>."


def director_result(segment):
    return {
        "detailed_description": f"[Shot 1] Segment {segment} action.",
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [segment],
    }


def make_checkpoint(directory, total_segments=4):
    state = minimax.new_generation_state(
        minimax.build_run_config(5, total_segments * 5, 0.4, total_segments)
    )
    continuity = minimax.continuity_state_for_registry(SUBJECTS)
    for segment in range(1, total_segments + 1):
        video_path = os.path.join(directory, f"segment_{segment:04d}.mp4")
        with open(video_path, "wb") as video:
            video.write(f"video {segment}".encode("ascii"))
        minimax.record_completed_segment(
            state,
            segment,
            video_path,
            director_result(segment),
            range(1, segment + 1),
            continuity_state=continuity,
            additional_subject_definitions=[],
        )
    checkpoint = os.path.join(directory, "generation_state.json")
    minimax.save_generation_state(state, checkpoint)
    return state, checkpoint


class RepairModeTests(unittest.TestCase):
    def test_parse_args_accepts_repair_and_rejects_conflicting_resume(self):
        args = minimax.parse_args(["5", "300", "0.2", "--repair", "17"])
        self.assertEqual(args.repair, 17)
        self.assertEqual(args.resume, 1)

        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "300", "0.2", "--repair", "0"])
        with self.assertRaises(SystemExit):
            minimax.parse_args([
                "5", "300", "0.2", "--repair", "17", "--resume", "4"
            ])

    def test_repair_rejects_first_and_final_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _ = make_checkpoint(directory)
            with self.assertRaisesRegex(ValueError, "Segment 1"):
                minimax.validate_repair_checkpoint(state, 1)
            with self.assertRaisesRegex(ValueError, "final segment 4"):
                minimax.validate_repair_checkpoint(state, 4)
            with self.assertRaisesRegex(ValueError, "final segment 4"):
                minimax.validate_repair_checkpoint(state, 5)

    def test_repair_requires_all_neighbor_records_and_video_files(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _ = make_checkpoint(directory)
            for missing_segment in (1, 2, 3):
                with self.subTest(missing_record=missing_segment):
                    damaged = copy.deepcopy(state)
                    damaged["segments"][missing_segment - 1] = {}
                    with self.assertRaisesRegex(
                        RuntimeError, f"segment {missing_segment}"
                    ):
                        minimax.validate_repair_checkpoint(damaged, 2)

                with self.subTest(missing_video=missing_segment):
                    damaged = copy.deepcopy(state)
                    damaged["segments"][missing_segment - 1]["video_path"] = (
                        os.path.join(directory, "missing.mp4")
                    )
                    with self.assertRaisesRegex(
                        RuntimeError, f"segment {missing_segment}"
                    ):
                        minimax.validate_repair_checkpoint(damaged, 2)

    def test_repair_anchor_extraction_uses_visible_neighbor_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "previous.mp4")
            next_video = os.path.join(directory, "next.mp4")
            for path in (previous_video, next_video):
                with open(path, "wb") as video:
                    video.write(b"video")
            commands = []

            def create_frame(command, check):
                self.assertTrue(check)
                commands.append(command)
                with open(command[-1], "wb") as frame:
                    frame.write(b"png")

            with mock.patch("minimax.subprocess.run", side_effect=create_frame):
                first_name, last_name = minimax.extract_repair_anchor_frames(
                    previous_video,
                    next_video,
                    17,
                    input_directory=directory,
                )

            self.assertEqual(first_name, "minimax_repair_first_frame_0017.png")
            self.assertEqual(last_name, "minimax_repair_last_frame_0017.png")
            self.assertEqual(commands[0][commands[0].index("-vf") + 1], "reverse")
            self.assertEqual(
                commands[1][commands[1].index("-vf") + 1],
                f"select=eq(n\\,{minimax.TRIM_FRAMES_AFTER_FIRST})",
            )
            self.assertNotIn("select=eq(n\\,0)", commands[1])

    def test_repair_workflow_has_both_keyframes_refs_and_isolated_latent(self):
        with open(minimax.REFRESH_WORKFLOW_FILE, "r", encoding="utf-8") as file:
            refresh = json.load(file)
        with open(minimax.INITIAL_WORKFLOW_FILE, "r", encoding="utf-8") as file:
            initial = json.load(file)
        for image_number in range(1, 7):
            _, node = minimax.find_workflow_node(
                initial,
                f"Reference Image {image_number}",
                "initial test workflow",
                "LoadImage",
            )
            node["inputs"]["image"] = f"reference_{image_number}.png"
        _, original_conditioning = minimax.find_workflow_node(
            refresh,
            minimax.REFRESH_CONDITIONING_NODE_NAME,
            "refresh test workflow",
        )
        original_also_ref = original_conditioning["inputs"]["also_ref_first_frame"]

        with mock.patch(
            "minimax.load_workflow",
            side_effect=[copy.deepcopy(refresh), initial],
        ), mock.patch("minimax.os.path.isfile", return_value=True):
            prepared = minimax.prepare_repair_workflow(
                5,
                0.4,
                "saved prompt",
                "first.png",
                "last.png",
                2,
                steps=8,
            )

        first_id, _ = minimax.find_workflow_node(
            prepared,
            minimax.REFRESH_FIRST_FRAME_NODE_NAME,
            "prepared repair",
        )
        last_id, last_node = minimax.find_workflow_node(
            prepared,
            minimax.REPAIR_LAST_FRAME_NODE_NAME,
            "prepared repair",
            "LoadImage",
        )
        _, conditioning = minimax.find_workflow_node(
            prepared,
            minimax.REFRESH_CONDITIONING_NODE_NAME,
            "prepared repair",
        )
        self.assertEqual(conditioning["inputs"]["first_frame"], [first_id, 0])
        self.assertEqual(conditioning["inputs"]["last_frame"], [last_id, 0])
        self.assertEqual(last_node["inputs"]["image"], "last.png")
        self.assertEqual(
            conditioning["inputs"]["also_ref_first_frame"], original_also_ref
        )
        for index in range(6):
            connection = conditioning["inputs"][f"ref_images.ref_image_{index}"]
            _, reference = minimax.find_workflow_node(
                prepared,
                f"Reference Image {index + 1}",
                "prepared repair",
            )
            self.assertEqual(connection[0], minimax.find_workflow_node(
                prepared,
                f"Reference Image {index + 1}",
                "prepared repair",
            )[0])
            self.assertEqual(reference["inputs"]["image"], f"reference_{index + 1}.png")
        _, latent = minimax.find_workflow_node(
            prepared, minimax.H3_LATENT_SAVE_NODE_NAME, "prepared repair"
        )
        self.assertEqual(
            latent["inputs"]["filename_prefix"],
            minimax.H3_REPAIR_LATENT_FILENAME_PREFIX,
        )
        self.assertNotEqual(
            latent["inputs"]["filename_prefix"], minimax.H3_LATENT_FILENAME_PREFIX
        )
        self.assertEqual(latent["inputs"]["clip_index"], 2)

    def test_normal_refresh_workflow_still_has_no_repair_keyframe_or_latent(self):
        with open(minimax.REFRESH_WORKFLOW_FILE, "r", encoding="utf-8") as file:
            refresh = json.load(file)
        with open(minimax.INITIAL_WORKFLOW_FILE, "r", encoding="utf-8") as file:
            initial = json.load(file)
        with mock.patch(
            "minimax.load_workflow", side_effect=[refresh, initial]
        ), mock.patch("minimax.os.path.isfile", return_value=True):
            prepared = minimax.prepare_refresh_workflow(
                5, 0.4, "prompt", "first.png", 2
            )
        _, conditioning = minimax.find_workflow_node(
            prepared, minimax.REFRESH_CONDITIONING_NODE_NAME, "normal refresh"
        )
        _, latent = minimax.find_workflow_node(
            prepared, minimax.H3_LATENT_SAVE_NODE_NAME, "normal refresh"
        )
        self.assertNotIn("last_frame", conditioning["inputs"])
        self.assertFalse(conditioning["inputs"]["also_ref_first_frame"])
        self.assertEqual(
            latent["inputs"]["filename_prefix"], minimax.H3_LATENT_FILENAME_PREFIX
        )

    def test_repair_keeps_checkpoint_and_original_target_file_untouched(self):
        previous_dynamic = (
            "<Subject 2> is Guard, male (S2), created in generated video "
            "segment 1 and continued from <Video 1>."
        )
        future_dynamic = (
            "<Subject 3> is Pilot, female (S3), created in generated video "
            "segment 2 and continued from <Video 1>."
        )
        with tempfile.TemporaryDirectory() as directory:
            state, checkpoint = make_checkpoint(directory)
            state["segments"][0]["additional_subject_definitions"] = [
                previous_dynamic
            ]
            state["segments"][1]["additional_subject_definitions"] = [future_dynamic]
            state["additional_subject_definitions"] = [future_dynamic]
            minimax.save_generation_state(state, checkpoint)
            before = copy.deepcopy(state)
            subjects_path = os.path.join(directory, "subjects.txt")
            with open(subjects_path, "w", encoding="utf-8") as subjects:
                subjects.write(SUBJECTS)
            beats_path = os.path.join(directory, "beats.txt")
            with open(beats_path, "w", encoding="utf-8") as beats_file:
                beats_file.write(
                    "Original first beat.\nEdited repair beat.\n"
                    "Third beat.\nFourth beat.\n"
                )
            story_path = os.path.join(directory, "story.txt")
            with open(story_path, "w", encoding="utf-8") as story_file:
                story_file.write("A test story.")
            repaired_video = os.path.join(directory, "repair.mp4")
            with open(repaired_video, "wb") as video:
                video.write(b"repair")
            opening_state = {"historical": True}
            fresh_director_result = director_result(2)
            fresh_director_result["detailed_description"] = (
                "[Shot 1] Fresh prompt for the edited repair beat. "
                "<Subject 1> Mark (S1) says: "
                "<d>[English] This repaired line is new.</d>"
            )

            with mock.patch(
                "minimax.continuity_state_for_registry",
                return_value=opening_state,
            ) as continuity, mock.patch(
                "minimax.format_authoritative_opening_state",
                return_value="OPENING",
            ) as opening, mock.patch(
                "minimax.build_h3_prompt",
                return_value="SAVED H3 PROMPT",
            ) as build_prompt, mock.patch(
                "minimax.extract_repair_anchor_frames",
                return_value=("first.png", "last.png"),
            ) as extract, mock.patch(
                "minimax.render_repair_segment_with_retries",
                return_value=({}, repaired_video, 1280, 720, 0.4),
            ) as render, mock.patch(
                "minimax.stitch_videos"
            ) as stitch, mock.patch(
                "minimax.save_generation_state"
            ) as save, mock.patch(
                "minimax.request_segment_llm",
                return_value={"llm_result": fresh_director_result},
            ) as director, mock.patch(
                "minimax.request_structured_continuity_state"
            ) as continuity_llm, mock.patch(
                "minimax.load_or_generate_beats"
            ) as beat_generation:
                result = minimax.repair_existing_segment(
                    2,
                    generation_state_path=checkpoint,
                    subjects_path=subjects_path,
                    beats_path=beats_path,
                    story_path=story_path,
                )

            historical_subjects = continuity.call_args.args[0]
            self.assertIn(previous_dynamic, historical_subjects)
            self.assertNotIn(future_dynamic, historical_subjects)
            self.assertEqual(
                continuity.call_args.args[1],
                before["segments"][0]["continuity_state"],
            )
            self.assertEqual(opening.call_count, 2)
            opening.assert_any_call(
                opening_state, historical_subjects, include_camera=False
            )
            opening.assert_any_call(
                opening_state, historical_subjects, include_camera=True
            )
            self.assertEqual(
                build_prompt.call_args.args[0]["detailed_description"],
                "[Shot 1] Fresh prompt for the edited repair beat. "
                "<Subject 1> Mark (S1) says: "
                "<d>[English] This repaired line is new.</d>",
            )
            self.assertEqual(build_prompt.call_args.args[1], historical_subjects)
            self.assertEqual(build_prompt.call_args.args[3], "OPENING")
            self.assertEqual(build_prompt.call_args.args[4], 2)
            self.assertFalse(build_prompt.call_args.kwargs["ff"])
            extract.assert_called_once_with(
                before["segments"][0]["video_path"],
                before["segments"][2]["video_path"],
                2,
                input_directory=None,
            )
            self.assertEqual(render.call_args.args[3], "SAVED H3 PROMPT")
            director.assert_called_once()
            director_bundle = director.call_args.args[0]
            self.assertEqual(
                director_bundle["ministral_context"]["current_beat_text"],
                "Edited repair beat.",
            )
            self.assertIn(
                "Beat 2: Edited repair beat.",
                director_bundle["messages"][1]["content"],
            )
            continuity_llm.assert_not_called()
            beat_generation.assert_not_called()

            saved = minimax.load_generation_state(checkpoint)
            self.assertEqual(saved, before)
            self.assertEqual(
                saved["segments"][1]["llm_result"],
                before["segments"][1]["llm_result"],
            )
            self.assertEqual(
                saved["segments"][1]["continuity_state"],
                before["segments"][1]["continuity_state"],
            )
            self.assertEqual(
                result["video_path"], os.path.abspath(repaired_video)
            )
            with open(before["segments"][1]["video_path"], "rb") as video:
                self.assertEqual(video.read(), b"video 2")
            with open(repaired_video, "rb") as video:
                self.assertEqual(video.read(), b"repair")
            save.assert_called_once()
            saved_state, saved_path = save.call_args.args
            self.assertEqual(saved_path, checkpoint)
            self.assertEqual(
                saved_state["segments"][1]["dialogues"],
                ["This repaired line is new."],
            )
            self.assertIn(
                "This repaired line is new.",
                saved_state["recent_dialogues"],
            )
            stitch.assert_not_called()

    def test_render_failure_does_not_save_or_stitch(self):
        with tempfile.TemporaryDirectory() as directory:
            _state, checkpoint = make_checkpoint(directory)
            beats_path = os.path.join(directory, "beats.txt")
            with open(beats_path, "w", encoding="utf-8") as beats_file:
                beats_file.write(
                    "First beat.\nRepair beat.\nThird beat.\nFourth beat.\n"
                )
            story_path = os.path.join(directory, "story.txt")
            with open(story_path, "w", encoding="utf-8") as story_file:
                story_file.write("A test story.")
            with mock.patch(
                "minimax.format_authoritative_opening_state", return_value="OPENING"
            ), mock.patch(
                "minimax.build_h3_prompt", return_value="PROMPT"
            ), mock.patch(
                "minimax.request_segment_llm",
                return_value={"llm_result": director_result(2)},
            ), mock.patch(
                "minimax.extract_repair_anchor_frames",
                return_value=("first.png", "last.png"),
            ), mock.patch(
                "minimax.render_repair_segment_with_retries",
                side_effect=RuntimeError("render failed"),
            ), mock.patch("minimax.save_generation_state") as save, mock.patch(
                "minimax.stitch_videos"
            ) as stitch:
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    minimax.repair_existing_segment(
                        2,
                        generation_state_path=checkpoint,
                        subjects_path=os.path.join(directory, "missing_subjects.txt"),
                        beats_path=beats_path,
                        story_path=story_path,
                    )
            save.assert_not_called()
            stitch.assert_not_called()

    def test_main_branches_before_normal_generation_or_llm_work(self):
        args = SimpleNamespace(
            repair=2,
            resume=1,
            steps=7,
            model="ministral",
            lora=[],
        )
        with mock.patch("minimax.parse_args", return_value=args), mock.patch(
            "minimax.validate_runtime_environment"
        ), mock.patch("minimax.verify_global_loras"), mock.patch(
            "minimax.repair_existing_segment", return_value="repaired"
        ) as repair, mock.patch("minimax.load_or_generate_beats") as generate:
            result = minimax._run_main(None)

        self.assertEqual(result, "repaired")
        repair.assert_called_once_with(2, steps=7, global_loras=[])
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
