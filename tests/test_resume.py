import json
import os
import tempfile
import threading
import unittest
from unittest import mock

import minimax


def formatted_result(shot):
    return {
        "detailed_description": (
            f"[Shot {shot}] Live-action, cinematic, two friends keep walking."
        ),
        "overall_soundscape": "Footsteps and a light breeze.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [shot],
    }


class ResumeTests(unittest.TestCase):
    def test_resume_waits_for_an_in_flight_final_checkpoint_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            state = minimax.new_generation_state(
                minimax.build_run_config(5, 15, 0.5, 3)
            )
            video_paths = {}
            latent_paths = {}
            for segment in (1, 2):
                video_path = os.path.join(directory, f"segment_{segment:04d}.mp4")
                latent_path = os.path.join(directory, f"latent_{segment:04d}")
                with open(video_path, "wb") as video_file:
                    video_file.write(b"video")
                with open(latent_path, "wb") as latent_file:
                    latent_file.write(b"latent")
                video_paths[segment] = video_path
                latent_paths[segment] = latent_path

            minimax.record_completed_segment(
                state,
                1,
                video_paths[1],
                formatted_result(1),
                [1],
            )
            minimax.save_generation_state(state, checkpoint)

            def finish_segment_two():
                threading.Event().wait(0.05)
                minimax.record_completed_segment(
                    state,
                    2,
                    video_paths[2],
                    formatted_result(2),
                    [1, 2],
                )
                minimax.save_generation_state(state, checkpoint)

            writer = threading.Thread(target=finish_segment_two)
            writer.start()
            try:
                with mock.patch(
                    "minimax.get_h3_latent_path",
                    side_effect=lambda segment: latent_paths[segment],
                ):
                    restored = minimax.restore_generation_state(
                        3,
                        ["First", "Second", "Third"],
                        checkpoint,
                        checkpoint_wait_timeout=1,
                        checkpoint_poll_interval=0.01,
                    )
            finally:
                writer.join()

            self.assertEqual(
                [record["segment_number"] for record in restored["state"]["segments"]],
                [1, 2],
            )
            self.assertEqual(restored["previous_video_path"], video_paths[2])

    def test_generation_state_contains_migratable_structured_continuity_state(self):
        state = minimax.new_generation_state(
            minimax.build_run_config(5, 10, 0.5, 2)
        )

        self.assertEqual(
            state["continuity_state"]["version"],
            minimax.CONTINUITY_STATE_VERSION,
        )
        migrated = minimax.migrate_continuity_state({
            "environment": "hallway",
            "subjects": {"1": {"position": "left"}},
        })
        self.assertEqual(migrated["environment"]["location"], "hallway")
        self.assertEqual(migrated["subjects"]["1"]["position"], "left")
        self.assertEqual(state["additional_subject_definitions"], [])

    def test_internal_subject_definitions_are_restored_from_segment_checkpoint(self):
        definition = (
            "<Subject 2> is Jenny, created in generated video "
            "segment 1 and continued from <Video 1>."
        )
        with tempfile.TemporaryDirectory() as directory:
            video_path = os.path.join(directory, "segment_0001.mp4")
            with open(video_path, "wb") as video_file:
                video_file.write(b"video")
            checkpoint = os.path.join(directory, "generation_state.json")
            config = minimax.build_run_config(5, 10, 0.5, 2)
            state = minimax.new_generation_state(config)
            minimax.record_completed_segment(
                state,
                1,
                video_path,
                formatted_result(1),
                [],
                additional_subject_definitions=[definition],
            )
            minimax.save_generation_state(state, checkpoint)

            restored = minimax.restore_generation_state(
                2,
                [],
                checkpoint,
            )

        self.assertEqual(restored["additional_subject_definitions"], [definition])
        self.assertEqual(
            restored["state"]["additional_subject_definitions"],
            [definition],
        )
        self.assertEqual(
            restored["state"]["segments"][0]["additional_subject_definitions"],
            [definition],
        )

    def test_new_subject_identity_is_saved_in_generation_state_json(self):
        definition = (
            "<Subject 2> is New Guard, male (S2), created in generated video "
            "segment 1 and continued from <Video 1>."
        )
        continuity = minimax.new_continuity_state()
        continuity["subjects"]["New Guard"] = (
            minimax.new_subject_continuity_record({
                "subject_id": 2,
                "name": "New Guard",
                "gender": "male",
                "picture_ids": [],
                "picture_id": None,
                "speaker_id": "S2",
                "origin_segment": 1,
            })
        )

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            state = minimax.new_generation_state(
                minimax.build_run_config(5, 10, 0.5, 2)
            )
            state["continuity_state"] = continuity
            state["additional_subject_definitions"] = [definition]
            minimax.save_generation_state(state, checkpoint)
            saved = minimax.load_generation_state(checkpoint)

        subject = saved["continuity_state"]["subjects"]["New Guard"]
        self.assertEqual(subject["subject_id"], 2)
        self.assertEqual(subject["gender"], "male")
        self.assertEqual(subject["speaker_id"], "S2")
        self.assertEqual(saved["additional_subject_definitions"], [definition])

    def test_beat_progress_is_kept_in_generation_state(self):
        config = minimax.build_run_config(5, 20, 0.5, 4)
        state = minimax.new_generation_state(config)
        state["beat_progress"] = {
            "completed_beat_ids": [1, 2],
            "last_segment_number": 4,
            "newly_completed_beat_ids": [2],
        }

        self.assertEqual(
            state["beat_progress"]["completed_beat_ids"],
            [1, 2],
        )
        self.assertEqual(state["beat_progress"]["last_segment_number"], 4)
        self.assertEqual(state["beat_progress"]["newly_completed_beat_ids"], [2])

    def test_resume_progress_delta_comes_from_checkpoint_cumulative_state(self):
        beats = ["First beat", "Second beat", "Third beat"]
        state = {
            "segments": [
                {"segment_number": 1, "completed_beat_ids": [1]},
                {"segment_number": 2, "completed_beat_ids": [1, 2]}
            ]
        }

        self.assertEqual(
            minimax.get_last_checkpoint_beat_update(state, beats),
            (2, [2])
        )

    def test_parse_args_accepts_one_based_resume_segment(self):
        args = minimax.parse_args(["5", "20", ".5", "--resume", "3"])
        self.assertEqual(args.resume, 3)
        self.assertEqual(args.steps, 6)

    def test_parse_args_accepts_custom_steps(self):
        args = minimax.parse_args(["5", "20", ".5", "--steps", "12"])
        self.assertEqual(args.steps, 12)

    def test_parse_args_defaults_extension_context_to_seven_frames(self):
        args = minimax.parse_args(["5", "20", ".5"])

        self.assertEqual(args.context_frames, 7)

    def test_parse_args_accepts_common_extension_context_sizes(self):
        for context_frames in (2, 4, 8, 12):
            with self.subTest(context_frames=context_frames):
                args = minimax.parse_args([
                    "5",
                    "20",
                    ".5",
                    f"--context-frames={context_frames}",
                ])

                self.assertEqual(args.context_frames, context_frames)

    def test_parse_args_defaults_to_ministral_model(self):
        args = minimax.parse_args(["5", "20", ".5"])

        self.assertEqual(args.model, "ministral")

    def test_parse_args_accepts_qwen_model(self):
        args = minimax.parse_args(["5", "20", ".5", "--model", "qwen"])

        self.assertEqual(args.model, "qwen")

    def test_parse_args_accepts_qwen_equals_syntax(self):
        args = minimax.parse_args(["5", "20", ".5", "--model=qwen"])

        self.assertEqual(args.model, "qwen")

    def test_parse_args_accepts_six_reference_image_overrides(self):
        arguments = ["5", "20", ".5"]
        for image_number in range(1, 7):
            arguments.extend((
                f"--image{image_number}",
                f"H:\\Images\\input\\reference {image_number}.png",
            ))

        args = minimax.parse_args(arguments)

        for image_number in range(1, 7):
            self.assertEqual(
                getattr(args, f"image{image_number}"),
                f"H:\\Images\\input\\reference {image_number}.png",
            )

    def test_parse_args_rejects_unknown_model(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "20", ".5", "--model", "unknown"])

    def test_get_formatter_selects_ministral_formatter(self):
        formatter = minimax.get_formatter("ministral")

        self.assertIs(type(formatter), minimax.MinistralFormatter)

    def test_get_formatter_selects_qwen_formatter(self):
        formatter = minimax.get_formatter("qwen")

        self.assertIs(type(formatter), minimax.QwenFormatter)

    def test_parse_args_accepts_unlimited_ordered_global_loras(self):
        args = minimax.parse_args([
            "5", "20", ".5",
            "--lora", "style.safetensors:0.8",
            "--lora", "motion.safetensors:-0.25",
            "--lora", "detail.safetensors:1.2",
        ])

        self.assertEqual(args.lora, [
            ("style.safetensors", 0.8),
            ("motion.safetensors", -0.25),
            ("detail.safetensors", 1.2),
        ])

    def test_parse_args_requires_name_and_finite_strength_for_every_lora(self):
        for invalid in (
            "style.safetensors",
            ":0.5",
            "style.safetensors:",
            "style.safetensors:not-a-number",
            "style.safetensors:nan",
            "style.safetensors:inf",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(SystemExit):
                minimax.parse_args(["5", "20", ".5", "--lora", invalid])

    def test_parse_args_accepts_first_frame_argument(self):
        args = minimax.parse_args(["5", "20", ".5", "ff"])
        self.assertTrue(args.ff)

        args = minimax.parse_args(["5", "20", ".5", "--ff"])
        self.assertTrue(args.ff)

        args = minimax.parse_args(["5", "20", ".5"])
        self.assertFalse(args.ff)

    def test_parse_args_rejects_nonpositive_steps(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "20", ".5", "--steps", "0"])

    def test_parse_args_rejects_nonpositive_context_frames(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args([
                "5", "20", ".5", "--context-frames", "0"
            ])

    def test_parse_args_rejects_nonpositive_resume_segment(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "20", ".5", "--resume", "0"])

    def test_beat_lora_suffix_is_parsed_and_removed_from_text(self):
        beat = minimax.parse_beat_definition(
            "Show the opening --lora style.safetensors:0.35"
        )

        self.assertEqual(str(beat), "Show the opening")
        self.assertEqual(beat.lora_override, ("style.safetensors", 0.35))
        self.assertNotIn("--lora", str(beat))

    def test_beat_accepts_unlimited_loras_and_removes_them_from_text(self):
        beat = minimax.parse_beat_definition(
            "Show the opening --lora lighting.safetensors:0.6 "
            "--lora motion.safetensors:1.25 --lora detail.safetensors:-0.1"
        )

        self.assertEqual(str(beat), "Show the opening")
        self.assertEqual(beat.loras, (
            ("lighting.safetensors", 0.6),
            ("motion.safetensors", 1.25),
            ("detail.safetensors", -0.1),
        ))

    def test_beat_lora_requires_explicit_strength(self):
        with self.assertRaisesRegex(ValueError, "expected"):
            minimax.parse_beat_definition(
                "Show the opening --lora lighting.safetensors"
            )

    def test_file_level_lora_is_metadata_and_applies_to_existing_beats(self):
        beats, directive = minimax.parse_beats_content(
            "--lora lighting.safetensors:1.0\nOpening event\nClosing event\n"
        )

        self.assertEqual(
            [str(beat) for beat in beats],
            ["Opening event", "Closing event"],
        )
        self.assertEqual(directive, "--lora lighting.safetensors:1.0")
        self.assertEqual(
            [beat.lora_override for beat in beats],
            [("lighting.safetensors", 1.0), ("lighting.safetensors", 1.0)],
        )

    def test_only_one_file_level_lora_is_allowed(self):
        with self.assertRaisesRegex(ValueError, "only one"):
            minimax.parse_beats_content(
                "--lora first.safetensors:1\n--lora second.safetensors:1\n"
            )

    def test_global_loras_are_added_before_beat_loras_without_a_default(self):
        beats = [
            minimax.parse_beat_definition(
                "First beat --lora first.safetensors:0.8"
            ),
            minimax.parse_beat_definition("Second beat"),
        ]

        self.assertEqual(
            minimax.beat_loras(
                beats, 1, [("global.safetensors", 0.4)]
            ),
            [("global.safetensors", 0.4), ("first.safetensors", 0.8)],
        )
        self.assertEqual(
            minimax.beat_loras(beats, 2),
            [],
        )
        self.assertEqual(
            minimax.beat_loras([], None, [("global.safetensors", 0.4)]),
            [("global.safetensors", 0.4)],
        )

    def test_global_loras_participate_in_resume_fingerprint(self):
        first = minimax.build_run_config(
            5, 20, 0.5, 4,
            global_loras=[("one.safetensors", 0.5), ("two.safetensors", 1.0)],
        )
        reordered = minimax.build_run_config(
            5, 20, 0.5, 4,
            global_loras=[("two.safetensors", 1.0), ("one.safetensors", 0.5)],
        )

        self.assertNotEqual(first["source_sha256"], reordered["source_sha256"])

    def test_resume_generates_only_requested_and_later_segments(self):
        self.assertEqual(list(minimax.get_segments_to_generate(3, 5)), [3, 4, 5])
        with self.assertRaisesRegex(ValueError, "exceeds"):
            minimax.get_segments_to_generate(6, 5)

    def test_state_is_written_atomically_and_restores_exact_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimax.build_run_config(
                5, 20, 0.5, 4, "A road story", ["Walk", "Talk"], ""
            )
            state = minimax.new_generation_state(config)
            self.assertEqual(
                state["beat_progress"],
                {
                    "completed_beat_ids": [],
                    "last_segment_number": None,
                    "newly_completed_beat_ids": [],
                },
            )
            paths = []
            for segment in (1, 2):
                path = os.path.join(directory, f"segment_{segment:04d}.mp4")
                with open(path, "wb") as f:
                    f.write(b"video")
                paths.append(os.path.abspath(path))
                minimax.record_completed_segment(
                    state,
                    segment,
                    path,
                    formatted_result(segment),
                    range(1, segment + 1),
                    f"- Summary through segment {segment}",
                )

            checkpoint = os.path.join(directory, "generation_state.json")
            minimax.save_generation_state(state, checkpoint)
            restored = minimax.restore_generation_state(
                3, ["Walk", "Talk"], checkpoint
            )

            self.assertEqual(restored["video_paths"], paths)
            self.assertEqual(restored["previous_video_path"], paths[-1])
            self.assertEqual(
                [number for number, _ in restored["recent_results"]], [2]
            )
            self.assertEqual(restored["completed_beat_ids"], {1, 2})
            self.assertEqual(
                restored["continuity_summary"], "- Summary through segment 2"
            )
            with open(checkpoint, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["segments"][1]["segment_number"], 2)

    def test_resume_slices_later_records_when_restarting_earlier_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimax.build_run_config(5, 20, 0.5, 4)
            state = minimax.new_generation_state(config)
            for segment in (1, 2, 3):
                path = os.path.join(directory, f"segment_{segment:04d}.mp4")
                with open(path, "wb") as f:
                    f.write(b"video")
                minimax.record_completed_segment(
                    state,
                    segment,
                    path,
                    formatted_result(segment),
                    [],
                    f"summary {segment}",
                )
            checkpoint = os.path.join(directory, "generation_state.json")
            minimax.save_generation_state(state, checkpoint)

            restored = minimax.restore_generation_state(
                2, [], checkpoint
            )

            self.assertEqual(len(restored["state"]["segments"]), 1)
            self.assertEqual(len(restored["video_paths"]), 1)
            self.assertEqual(restored["continuity_summary"], "summary 1")

    def test_resume_marks_rendered_segment_with_pending_summary_for_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimax.build_run_config(5, 15, 0.5, 3)
            state = minimax.new_generation_state(config)
            for segment in (1, 2):
                path = os.path.join(directory, f"segment_{segment:04d}.mp4")
                with open(path, "wb") as f:
                    f.write(b"video")
                minimax.record_completed_segment(
                    state,
                    segment,
                    path,
                    formatted_result(segment),
                    [],
                    "- prior summary",
                    continuity_summary_pending=segment == 2,
                )
            checkpoint = os.path.join(directory, "generation_state.json")
            minimax.save_generation_state(state, checkpoint)

            restored = minimax.restore_generation_state(
                3, [], checkpoint
            )

            self.assertTrue(restored["continuity_summary_pending"])
            self.assertEqual(
                [number for number, _ in restored["recent_results"]],
                [2],
            )

    def test_resume_rejects_changed_settings_and_source_material(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            original = minimax.build_run_config(
                5,
                20,
                0.5,
                4,
                "story A",
                ["old beat"],
                "old subjects",
            )
            state = minimax.new_generation_state(original)
            path = os.path.join(directory, "segment_0001.mp4")
            with open(path, "wb") as video_file:
                video_file.write(b"video")
            minimax.record_completed_segment(
                state,
                1,
                path,
                formatted_result(1),
                [1],
                "summary 1",
            )
            minimax.save_generation_state(
                state,
                checkpoint,
            )

            changed = minimax.build_run_config(
                7,
                63,
                0.2,
                9,
                "story B",
                ["new beat 1", "new beat 2"],
                "new subjects",
            )
            restored = minimax.restore_generation_state(
                2,
                ["new beat 1", "new beat 2"],
                checkpoint,
            )

            self.assertEqual(restored["video_paths"], [path])
            self.assertEqual(restored["previous_video_path"], path)

    def test_generated_subject_lines_do_not_change_source_fingerprint(self):
        original_subjects = (
            "<Subject 1> is Amy, referenced in <Picture 1>."
        )
        expanded_subjects = (
            original_subjects
            + "\n<Subject 2> is Jenny, created in generated "
            "video segment 3 and continued from <Video 1>."
        )

        original = minimax.build_run_config(
            5, 20, 0.5, 4, "story", ["beat"], original_subjects
        )
        expanded = minimax.build_run_config(
            5, 20, 0.5, 4, "story", ["beat"], expanded_subjects
        )

        self.assertEqual(
            original["source_sha256"],
            expanded["source_sha256"],
        )

    def test_resume_allows_checkpoint_without_run_config(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            state = {"version": 1, "segments": []}
            minimax.save_generation_state(state, checkpoint)
            config = minimax.build_run_config(5, 10, 0.5, 2)

            restored = minimax.restore_generation_state(1, [], checkpoint)

            self.assertEqual(restored["video_paths"], [])
            self.assertIsNone(restored["previous_video_path"])

    def test_resume_rejects_missing_prior_video_or_director_result(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimax.build_run_config(5, 10, 0.5, 2)
            checkpoint = os.path.join(directory, "generation_state.json")
            state = minimax.new_generation_state(config)
            state["segments"] = [{
                "segment_number": 1,
                "video_path": os.path.join(directory, "missing.mp4"),
                "llm_result": formatted_result(1),
                "completed_beat_ids": [],
            }]
            minimax.save_generation_state(state, checkpoint)

            with self.assertRaisesRegex(RuntimeError, "video for segment 1"):
                minimax.restore_generation_state(2, [], checkpoint)


if __name__ == "__main__":
    unittest.main()
