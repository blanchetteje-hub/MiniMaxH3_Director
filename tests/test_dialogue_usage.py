import json
import os
import tempfile
import unittest
from unittest import mock

import minimax


SUBJECTS = "<Subject 1> is Ada.\n<Subject 2> is Ben."


def result_with_dialogues(*lines):
    blocks = []
    for index, line in enumerate(lines):
        subject = index % 2 + 1
        name = "Ada" if subject == 1 else "Ben"
        blocks.append(
            f"<Subject {subject}> {name} (S{subject}) says: "
            f"<d>[English] {line}</d>"
        )
    description = "[Shot 1] " + " ".join(blocks or ["They walk silently."])
    return {
        "detailed_description": description,
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [],
    }


def contains_line(dialogues, line):
    return any(line in str(dialogue) for dialogue in dialogues)


class DialogueUsageStateTests(unittest.TestCase):
    def test_new_state_starts_with_an_empty_dialogue_array(self):
        state = minimax.new_generation_state(
            minimax.build_run_config(5, 30, 0.5, 6)
        )

        self.assertEqual(state["recent_dialogues"], [])

    def test_checkpoint_keeps_every_line_from_each_of_the_last_five_segments(self):
        state = minimax.new_generation_state(
            minimax.build_run_config(5, 30, 0.5, 6)
        )
        segment_lines = {
            1: ["old alpha", "old beta"],
            2: ["second gamma"],
            3: [],
            4: ["fourth delta", "fourth epsilon", "fourth zeta"],
            5: [],
            6: ["sixth eta"],
        }

        for segment, lines in segment_lines.items():
            record = minimax.record_completed_segment(
                state,
                segment,
                f"segment_{segment:04d}.mp4",
                result_with_dialogues(*lines),
                [],
            )
            self.assertEqual(len(record["dialogues"]), len(lines))
            for line in lines:
                self.assertTrue(contains_line(record["dialogues"], line))

        recent = state["recent_dialogues"]
        self.assertFalse(contains_line(recent, "old alpha"))
        self.assertFalse(contains_line(recent, "old beta"))
        for line in (
            "second gamma",
            "fourth delta",
            "fourth epsilon",
            "fourth zeta",
            "sixth eta",
        ):
            self.assertTrue(contains_line(recent, line))

    def test_silent_segments_age_dialogue_out_of_the_five_segment_window(self):
        state = minimax.new_generation_state(
            minimax.build_run_config(5, 30, 0.5, 6)
        )
        for segment in range(1, 7):
            lines = ["only in segment one"] if segment == 1 else []
            minimax.record_completed_segment(
                state,
                segment,
                f"segment_{segment:04d}.mp4",
                result_with_dialogues(*lines),
                [],
            )

        self.assertEqual(state["recent_dialogues"], [])

    def test_dialogue_history_is_written_to_generation_state_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "generation_state.json")
            state = minimax.new_generation_state(
                minimax.build_run_config(5, 5, 0.5, 1)
            )
            minimax.record_completed_segment(
                state,
                1,
                "segment_0001.mp4",
                result_with_dialogues("persist this line"),
                [],
            )
            minimax.save_generation_state(state, path)

            with open(path, "r", encoding="utf-8") as checkpoint:
                saved = json.load(checkpoint)

        self.assertTrue(
            contains_line(saved["recent_dialogues"], "persist this line")
        )
        self.assertTrue(
            contains_line(saved["segments"][0]["dialogues"], "persist this line")
        )

    def test_old_records_without_dialogue_field_are_migrated_from_llm_result(self):
        records = [{
            "segment_number": 1,
            "llm_result": result_with_dialogues("recover this old line"),
        }]

        recent = minimax.collect_recent_dialogues(records)

        self.assertTrue(contains_line(recent, "recover this old line"))
        self.assertTrue(
            contains_line(records[0]["dialogues"], "recover this old line")
        )

    def test_resume_rebuilds_dialogues_from_only_the_retained_records(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = os.path.join(directory, "generation_state.json")
            state = minimax.new_generation_state(
                minimax.build_run_config(5, 30, 0.5, 6)
            )
            latent_paths = {}
            for segment in range(1, 7):
                video_path = os.path.join(directory, f"segment_{segment:04d}.mp4")
                latent_path = os.path.join(directory, f"latent_{segment:04d}.safetensors")
                with open(video_path, "wb") as video:
                    video.write(b"video")
                with open(latent_path, "wb") as latent:
                    latent.write(b"latent")
                latent_paths[segment] = latent_path
                minimax.record_completed_segment(
                    state,
                    segment,
                    video_path,
                    result_with_dialogues(f"line from segment {segment}"),
                    [],
                )
            minimax.save_generation_state(state, checkpoint)

            with mock.patch(
                "minimax.get_h3_latent_path",
                side_effect=lambda segment: latent_paths[segment],
            ):
                restored = minimax.restore_generation_state(4, [], checkpoint)

        recent = restored["state"]["recent_dialogues"]
        for segment in (1, 2, 3):
            self.assertTrue(contains_line(recent, f"line from segment {segment}"))
        for segment in (4, 5, 6):
            self.assertFalse(contains_line(recent, f"line from segment {segment}"))


class DialogueUsagePromptTests(unittest.TestCase):
    def test_formatter_does_not_insert_subject_tags_inside_dialogue(self):
        definitions = (
            "<Subject 1> is Mark, referenced in <Picture 1>.\n"
            "<Subject 2> is Amy, referenced in <Picture 2>."
        )
        context = minimax.build_ministral_context(
            segment_number=10,
            segment_duration=5,
            beats=[],
            completed_beat_ids=set(),
            subject_definitions=definitions,
            story="",
        )
        raw = {
            "detailed_description": (
                "[Shot 10] Amy (S2) asks: "
                "<d>[English] Mark? Are you down there?</d>"
            ),
            "overall_soundscape": "Water drips in the cavern.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }

        formatted = minimax.format_ministral_prompt(raw, context)

        self.assertIn(
            "<d>[English] Mark? Are you down there?</d>",
            formatted["detailed_description"],
        )
        self.assertNotIn(
            "<d>[English] <Subject 1>",
            formatted["detailed_description"],
        )
        self.assertEqual(
            minimax.validate_h3_dialogue_format(formatted, context),
            [],
        )

    def test_dialogue_gate_accepts_multiple_tagged_lines_and_visible_text(self):
        valid = {
            "detailed_description": (
                "[Shot 2] Ada (S1) says: <d>[English] Go now.</d> "
                "Ben (S2) replies: <d>[English] I am coming.</d> "
                "A sign says \"EXIT\" above them."
            ),
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }

        self.assertEqual(
            minimax.validate_h3_dialogue_format(valid, {}),
            [],
        )

    def test_director_retries_subject_tagged_quoted_dialogue(self):
        malformed = {
            "detailed_description": (
                "[Shot 10] <Subject 2> Amy peers through a crevice. "
                "His voice carries through the tunnel in a whisper: "
                "\u2018<Subject 1> Mark? Are you down there?\u2019"
            ),
            "overall_soundscape": "Water drips in the cavern.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }
        corrected = {
            **malformed,
            "detailed_description": (
                "[Shot 10] Amy (S2) asks: "
                "<d>[English] Mark? Are you down there?</d>"
            ),
        }
        bundle = {
            "segment": 10,
            "active_beat_id": None,
            "conditioning_mode": "latent_continuation",
            "messages": [{"role": "user", "content": "Direct segment 10."}],
            "ministral_context": {},
            "dialogue_exclusions": [],
            "opening_state_sha256": "state-hash",
        }

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=[malformed, corrected],
        ) as director:
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(director.call_count, 2)
        correction_prompt = director.call_args_list[1].args[0][-1]["content"]
        self.assertIn("DIRECTOR DIALOGUE FORMAT CORRECTION", correction_prompt)
        self.assertEqual(payload["llm_result"], corrected)

    def test_director_uses_latest_malformed_dialogue_without_exiting(self):
        malformed = {
            "detailed_description": (
                "[Shot 2] Ada's voice calls: \u2018<Subject 2> Ben?\u2019"
            ),
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }
        bundle = {
            "segment": 2,
            "active_beat_id": None,
            "conditioning_mode": "latent_continuation",
            "messages": [{"role": "user", "content": "Direct segment 2."}],
            "ministral_context": {},
            "dialogue_exclusions": [],
            "opening_state_sha256": "state-hash",
        }

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            return_value=malformed,
        ) as director, mock.patch("builtins.print") as output:
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(
            director.call_count,
            minimax.DIRECTOR_BEAT_COMPLETION_ATTEMPTS,
        )
        self.assertEqual(payload["llm_result"], malformed)
        self.assertTrue(any(
            "latest best-effort response and moving on" in str(call)
            for call in output.call_args_list
        ))

    def test_director_rules_distinguish_subject_tags_from_speaker_ids(self):
        rules = minimax.build_director_rules(
            total_length=10,
            segment_length=5,
            total_segments=2,
            subject_definitions=SUBJECTS,
            segment_number=2,
            conditioning_mode="latent_continuation",
        )

        self.assertIn("NEVER put `<Subject N>` inside spoken words", rules)
        self.assertIn("Amy (S2) asks: <d>[English] Mark?", rules)

    def test_repeated_dialogue_is_rejected_and_director_is_retried(self):
        repeated = result_with_dialogues("Do not repeat me!")
        fresh = result_with_dialogues("A genuinely new line.")
        bundle = {
            "segment": 2,
            "active_beat_id": None,
            "conditioning_mode": "latent_continuation",
            "messages": [],
            "ministral_context": {},
            "dialogue_exclusions": ["do not repeat me."],
            "opening_state_sha256": "state-hash",
        }

        with mock.patch(
            "minimax.request_valid_ministral_prompt",
            side_effect=[repeated, fresh],
        ) as director:
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(director.call_count, 2)
        self.assertEqual(payload["llm_result"], fresh)

    def test_director_prompt_marks_json_dialogue_array_as_forbidden(self):
        exclusions = ['Ada said "go".', "Caf\u00e9 rendezvous."]

        messages, _, _ = minimax.build_generation_messages(
            director_rules="Director rules.",
            story="Ada and Ben continue their walk.",
            beats=[],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=2,
            total_segments=2,
            segment_length=5,
            total_length=10,
            subject_definitions=SUBJECTS,
            dialogue_exclusions=exclusions,
        )

        user_prompt = messages[1]["content"]
        self.assertIn("DIALOGUE EXCLUSIONS", user_prompt)
        self.assertIn("must not be spoken", user_prompt.lower())
        self.assertIn(json.dumps(exclusions, ensure_ascii=False), user_prompt)

    def test_exclusions_reach_formatter_context_but_not_final_h3_prompt(self):
        exclusions = ["Do not repeat me.", "Nor me."]

        context = minimax.build_ministral_context(
            segment_number=2,
            segment_duration=5,
            beats=[],
            completed_beat_ids=set(),
            subject_definitions=SUBJECTS,
            story="Ada and Ben walk.",
            dialogue_exclusions=exclusions,
        )
        prompt = minimax.build_h3_prompt(
            result_with_dialogues("A completely new line."),
            SUBJECTS,
            segment_number=2,
        )

        self.assertEqual(context["dialogue_exclusions"], exclusions)
        self.assertNotIn("dialogue_exclusions", prompt)
        self.assertNotIn("none may be spoken", prompt.lower())

    def test_h3_prompt_has_no_dialogue_exclusion_metadata(self):
        prompt = minimax.build_h3_prompt(
            result_with_dialogues(),
            SUBJECTS,
        )

        self.assertNotIn("dialogue_exclusions", prompt)
        self.assertNotIn("dialogue_exclusion_rule", prompt)

    def test_final_h3_prompt_forbids_spoken_language_without_dialogue_blocks(self):
        result = result_with_dialogues()
        result["overall_soundscape"] = (
            "Rain taps the roof while a loose shutter knocks in the wind."
        )

        prompt = minimax.build_h3_prompt(result, SUBJECTS)

        self.assertIn(result["overall_soundscape"], prompt)
        self.assertTrue(prompt.endswith(
            "SPOKEN DIALOGUE: None. No intelligible spoken words, vocalized "
            "language, or singing occur in this segment."
        ))

    def test_dialogue_constraint_is_upstream_not_in_final_h3_prompt(self):
        result = result_with_dialogues("Keep the existing formatting intact.")
        original_description = result["detailed_description"]

        prompt = minimax.build_h3_prompt(result, SUBJECTS)
        rules = minimax.build_director_rules(
            total_length=10,
            segment_length=5,
            total_segments=2,
            subject_definitions=SUBJECTS,
            segment_number=1,
        )

        self.assertIn(original_description, prompt)
        constraint = (
            "SPOKEN DIALOGUE: English only. Only the exact words inside "
            "<d>...</d> are spoken. Do not generate additional dialogue."
        )
        self.assertNotIn(constraint, prompt)
        self.assertIn(constraint, rules)

    def test_director_rules_do_not_invent_background_speech_like_ambience(self):
        rules = minimax.build_director_rules(
            total_length=10,
            segment_length=5,
            total_segments=2,
            subject_definitions=SUBJECTS,
            segment_number=1,
        )

        self.assertIn(
            "Do not invent background murmur, chatter, conversation, or voices",
            rules,
        )
        self.assertIn("ACTIVE beat or IMPORTANT generation rules", rules)
        self.assertIn("legitimate ambient non-speech audio", rules)


if __name__ == "__main__":
    unittest.main()
