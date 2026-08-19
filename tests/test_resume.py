import json
import os
import tempfile
import unittest

import minimax


def formatted_result(shot):
    return {
        "integrated_multimodal_description": (
            f"[Shot {shot}] Live-action, cinematic, two friends keep walking."
        ),
        "overall_soundscape": "Footsteps and a light breeze.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [shot],
    }


class ResumeTests(unittest.TestCase):
    def test_parse_args_accepts_one_based_resume_segment(self):
        args = minimax.parse_args(["5", "20", ".5", "--resume", "3"])
        self.assertEqual(args.resume, 3)

    def test_parse_args_rejects_nonpositive_resume_segment(self):
        with self.assertRaises(SystemExit):
            minimax.parse_args(["5", "20", ".5", "--resume", "0"])

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
                3, config, ["Walk", "Talk"], checkpoint
            )

            self.assertEqual(restored["video_paths"], paths)
            self.assertEqual(restored["previous_video_path"], paths[-1])
            self.assertEqual(
                [number for number, _ in restored["recent_results"]], [1, 2]
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
                2, config, [], checkpoint
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
                3, config, [], checkpoint
            )

            self.assertTrue(restored["continuity_summary_pending"])
            self.assertEqual(
                [number for number, _ in restored["recent_results"]],
                [1, 2],
            )

    def test_resume_rejects_changed_settings_or_source_material(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            original = minimax.build_run_config(5, 20, 0.5, 4, "story A")
            minimax.save_generation_state(
                minimax.new_generation_state(original), checkpoint
            )

            changed = minimax.build_run_config(5, 20, 0.5, 4, "story B")
            with self.assertRaisesRegex(RuntimeError, "settings or source inputs"):
                minimax.restore_generation_state(2, changed, [], checkpoint)

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
                minimax.restore_generation_state(2, config, [], checkpoint)


if __name__ == "__main__":
    unittest.main()
