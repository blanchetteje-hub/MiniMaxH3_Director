import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import minimax


class BeatGenerationTests(unittest.TestCase):
    def test_prompt_requests_one_creative_progressive_beat_per_segment(self):
        extra = "Make beat 4 a silent reveal; preserve Jack’s exact motivation."
        subjects = "- Marc is a 40-year-old man.\n- Elena is a skilled pilot."
        messages = minimax.build_beat_generation_messages(
            "A courier must return a stolen star before sunrise.",
            10,
            beat_instructions=extra,
            subject_information=subjects,
        )
        prompt = messages[1]["content"]

        self.assertEqual([item["role"] for item in messages], ["system", "user"])
        self.assertIn("exactly 10 ordered story beats", prompt)
        self.assertIn("one beat for each of the 10 video segments", prompt)
        self.assertIn("exactly one complete sentence", prompt)
        self.assertIn("bold, surprising, story-specific", prompt)
        self.assertIn("several substantially different story arcs", prompt)
        self.assertIn("Avoid generic filler events", prompt)
        self.assertIn("Be creative", prompt)
        self.assertIn("materially move the story forward", prompt)
        self.assertIn("Never repeat, recap, restage", prompt)
        self.assertIn("final beat must conclusively resolve and conclude", prompt)
        self.assertIn("A courier must return a stolen star", prompt)
        self.assertIn("ADDITIONAL BEAT INSTRUCTIONS FROM STORY.TXT", prompt)
        self.assertIn(extra, prompt)
        self.assertIn("copy it character-for-character", prompt)
        self.assertIn("silently audit every beat", prompt)
        self.assertIn("MAIN CHARACTERS FROM SUBJECTS.TXT", prompt)
        self.assertIn(subjects, prompt)
        self.assertIn("keep them central", prompt)

        schema = minimax.build_beats_response_format(10)["json_schema"]["schema"]
        beat_array = schema["properties"]["beats"]
        self.assertEqual(beat_array["minItems"], 10)
        self.assertEqual(beat_array["maxItems"], 10)
        self.assertTrue(beat_array["uniqueItems"])
        self.assertIn("Exactly one", beat_array["items"]["description"])

    def test_subject_registry_descriptions_are_formatted_for_beat_generation(self):
        definitions = (
            "<Subject 1> is Marc, a 40-year-old man referenced in <Picture 1>.\n"
            "<Subject 2> is Elena, a skilled pilot with a scar referenced in "
            "<Picture 2> and <Picture 3>.\n"
            "<Subject 3> is June, referenced in <Picture 4>."
        )

        information = minimax.format_beat_generation_subjects(definitions)

        self.assertEqual(
            information,
            "- Marc is a 40-year-old man.\n"
            "- Elena is a skilled pilot with a scar.\n"
            "- June is a main character.",
        )
        self.assertNotIn("Picture", information)

    def test_malformed_subject_line_reports_its_line_number(self):
        definitions = (
            "<Subject 1> is Marc, a mechanic referenced in <Picture 1>.\n"
            "Elena is missing the required subject and picture mapping.\n"
        )

        with self.assertRaisesRegex(
            ValueError,
            r"Could not parse subjects\.txt line 2.*Expected '<Subject N>",
        ):
            minimax.format_beat_generation_subjects(definitions)

    def test_duplicate_subject_mapping_returns_subjects_file_error(self):
        definitions = (
            "<Subject 1> is Marc, referenced in <Picture 1>.\n"
            "<Subject 1> is Elena, referenced in <Picture 2>.\n"
        )

        with self.assertRaisesRegex(
            ValueError,
            r"Invalid subjects\.txt: Duplicate subject ID: 1",
        ):
            minimax.format_beat_generation_subjects(definitions)

    def test_subject_prompt_verification_rejects_dropped_subjects(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "subjects.txt information was not included",
        ):
            minimax.verify_subjects_in_beat_messages(
                [{"role": "user", "content": "Generate two beats."}],
                "- Marc is a main character.",
            )

    def test_subjects_are_in_initial_and_compliance_review_prompts(self):
        subjects = "- Marc is a mechanic.\n- Elena is a main character."
        initial = minimax.build_beat_generation_messages(
            "A rescue story.",
            2,
            subject_information=subjects,
        )
        review = minimax.build_beat_instruction_review_messages(
            "A rescue story.",
            2,
            ["Marc finds the beacon.", "Elena guides everyone home."],
            "Keep the rescue grounded.",
            subject_information=subjects,
        )

        for messages in (initial, review):
            self.assertIn(subjects, messages[1]["content"])
            minimax.verify_subjects_in_beat_messages(messages, subjects)

    def test_story_beat_instructions_are_extracted_verbatim(self):
        instructions = "Make beat 2 surreal.  Keep  double spaces and punctuation!"
        narrative, parsed = minimax.parse_story_beat_instructions(
            "Opening premise.\n"
            f"beat_instructions: [{instructions}]\n"
            "The protagonist returns home."
        )

        self.assertEqual(parsed, instructions)
        self.assertEqual(
            narrative,
            "Opening premise.\nThe protagonist returns home.",
        )
        self.assertNotIn("beat_instructions", narrative)

    def test_numbered_plain_text_beats_are_parsed_and_normalized(self):
        raw = "\n".join(
            f"B{number:03d}: Distinct event {number} moves the story forward."
            for number in range(1, 4)
        )

        self.assertEqual(
            minimax.parse_generated_beats(raw, 3),
            [
                "Distinct event 1 moves the story forward.",
                "Distinct event 2 moves the story forward.",
                "Distinct event 3 moves the story forward.",
            ],
        )

    def test_parser_rejects_wrong_count_and_duplicate_beats(self):
        with self.assertRaisesRegex(ValueError, "exactly 3"):
            minimax.parse_generated_beats({"beats": ["First", "Second"]}, 3)
        with self.assertRaisesRegex(ValueError, "duplicates"):
            minimax.parse_generated_beats(
                {"beats": ["First.", "Second.", "first."]},
                3,
            )

    def test_parser_requires_one_complete_sentence_per_beat(self):
        with self.assertRaisesRegex(ValueError, "exactly one sentence"):
            minimax.parse_generated_beats(
                {
                    "beats": [
                        "The vault opens. The alarm sounds.",
                        "The guard catches the thief.",
                    ]
                },
                2,
            )
        with self.assertRaisesRegex(ValueError, "fragments"):
            minimax.parse_generated_beats(
                {"beats": ["The unfinished opening", "The story concludes."]},
                2,
            )

        self.assertEqual(
            minimax.parse_generated_beats(
                {
                    "beats": [
                        "Dr. Reyes discovers the hidden transmitter.",
                        'She shouts "Run!" before sealing the tunnel.',
                    ]
                },
                2,
            ),
            [
                "Dr. Reyes discovers the hidden transmitter.",
                'She shouts "Run!" before sealing the tunnel.',
            ],
        )

    def test_generated_beats_are_printed_as_a_numbered_list(self):
        with mock.patch("builtins.print") as print_mock:
            minimax.print_generated_beats(
                ["The journey begins.", "The conflict is resolved."]
            )

        self.assertEqual(
            print_mock.call_args_list,
            [
                mock.call(),
                mock.call("Generated story beats:"),
                mock.call("  1. The journey begins."),
                mock.call("  2. The conflict is resolved."),
                mock.call(),
            ],
        )

    def test_explicit_instruction_constraints_are_validated_locally(self):
        instructions = (
            'Include the exact phrase "silver token" once, in beat 2 only. '
            'Do not use the word "ghost" in any beat. The entire story must '
            'end with the exact sentence "The mystery is resolved."'
        )
        valid = [
            "The search begins.",
            "She finds the SILVER TOKEN.",
            "The mystery is resolved.",
        ]
        invalid = [
            "The silver token appears beside a ghost.",
            "She finds nothing.",
            "The search continues.",
        ]

        self.assertEqual(
            minimax.validate_generated_beat_instructions(valid, instructions),
            [],
        )
        issues = minimax.validate_generated_beat_instructions(
            invalid,
            instructions,
        )
        self.assertTrue(any("beat 2" in issue for issue in issues), issues)
        self.assertTrue(any("Prohibited word" in issue for issue in issues), issues)
        self.assertTrue(any("Final beat" in issue for issue in issues), issues)

    def test_invalid_response_is_retried_then_saved_and_loaded(self):
        valid_beats = [
            "The explorer discovers a sealed observatory.",
            "She deciphers its star map and opens the dome.",
            "She redirects the falling comet and saves the city.",
        ]
        llm_request = mock.Mock(
            side_effect=[
                {
                    "beats": [
                        valid_beats[0] + " A second sentence is not allowed.",
                        valid_beats[1],
                        valid_beats[2],
                    ]
                },
                {"beats": valid_beats},
                {"beats": valid_beats},
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            beats = minimax.generate_beats_from_story(
                "An explorer races to stop a comet.",
                3,
                path=path,
                llm_request=llm_request,
                beat_instructions="Make the observatory feel ancient.",
                subject_information="- Priya is an experienced explorer.",
            )
            with open(path, "r", encoding="utf-8") as beat_file:
                saved = beat_file.read()

            self.assertEqual([str(beat) for beat in beats], valid_beats)
            self.assertEqual(saved, "\n".join(valid_beats) + "\n")
            self.assertEqual(
                [name for name in os.listdir(directory) if name.endswith(".tmp")],
                [],
            )

        self.assertEqual(llm_request.call_count, 3)
        for call in llm_request.call_args_list:
            for name, value in minimax.BEAT_LLM_SAMPLING_PARAMETERS.items():
                self.assertEqual(call.kwargs[name], value)
        retry_prompt = llm_request.call_args_list[1].args[0][1]["content"]
        self.assertIn("PREVIOUS RESPONSE WAS INVALID", retry_prompt)
        self.assertIn("multiple sentences are not allowed", retry_prompt)
        self.assertIn("Make the observatory feel ancient.", retry_prompt)
        self.assertIn("Priya is an experienced explorer", retry_prompt)
        review_prompt = llm_request.call_args_list[2].args[0][1]["content"]
        self.assertIn("meticulous", llm_request.call_args_list[2].args[0][0]["content"])
        self.assertIn("ADDITIONAL INSTRUCTIONS START", review_prompt)
        self.assertIn("Make the observatory feel ancient.", review_prompt)
        self.assertIn("Priya is an experienced explorer", review_prompt)
        self.assertIn("resolve the story's central conflict", review_prompt)
        self.assertIn("cliffhanger", review_prompt)
        response_format = llm_request.call_args_list[0].kwargs["response_format"]
        beat_array = response_format["json_schema"]["schema"]["properties"][
            "beats"
        ]
        self.assertEqual((beat_array["minItems"], beat_array["maxItems"]), (3, 3))

    def test_more_than_twenty_beats_are_generated_in_batches(self):
        calls = []

        def llm_request(messages, **kwargs):
            metadata = kwargs["history_metadata"]
            calls.append((messages, kwargs))
            return {
                "beats": [
                    f"Global event {number} visibly advances the story."
                    for number in range(
                        metadata["batch_start"],
                        metadata["batch_end"] + 1,
                    )
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            beats = minimax.generate_beats_from_story(
                "A long journey unfolds across many connected events.",
                25,
                path=path,
                llm_request=llm_request,
            )

        self.assertEqual(len(beats), 25)
        self.assertEqual(
            [
                (
                    call[1]["history_metadata"]["batch_start"],
                    call[1]["history_metadata"]["batch_end"],
                    call[1]["response_format"]["json_schema"]["schema"]
                    ["properties"]["beats"]["maxItems"],
                )
                for call in calls
            ],
            [(1, 20, 20), (21, 25, 5)],
        )
        second_prompt = calls[1][0][1]["content"]
        self.assertIn("global beat positions\n21 through 25", second_prompt)
        self.assertIn("PREVIOUSLY GENERATED BEATS", second_prompt)
        self.assertIn("B001: Global event 1", second_prompt)
        self.assertIn("B020: Global event 20", second_prompt)

    def test_batched_instruction_review_never_requests_over_twenty_beats(self):
        calls = []

        def llm_request(messages, **kwargs):
            metadata = kwargs["history_metadata"]
            calls.append((messages, kwargs))
            return {
                "beats": [
                    f"Global event {number} visibly advances the story."
                    for number in range(
                        metadata["batch_start"],
                        metadata["batch_end"] + 1,
                    )
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            minimax.generate_beats_from_story(
                "A long journey unfolds across many connected events.",
                25,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
                beat_instructions="Keep the complete progression coherent.",
            )

        self.assertEqual(
            [call[1]["history_metadata"]["purpose"] for call in calls],
            [
                "beat_generation",
                "beat_generation",
                "beat_instruction_review",
                "beat_instruction_review",
            ],
        )
        requested_sizes = [
            call[1]["response_format"]["json_schema"]["schema"]
            ["properties"]["beats"]["maxItems"]
            for call in calls
        ]
        self.assertEqual(requested_sizes, [20, 5, 20, 5])
        review_prompt = calls[3][0][1]["content"]
        self.assertIn("global beats 21 through 25", review_prompt)
        self.assertIn("COMPLETE PLAN CONTEXT OUTSIDE THIS BATCH", review_prompt)

    def test_nonempty_beats_file_is_preserved_without_an_llm_request(self):
        llm_request = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            original = "Opening event\nConcluding event\n"
            with open(path, "w", encoding="utf-8") as beat_file:
                beat_file.write(original)

            beats = minimax.load_or_generate_beats(
                path,
                "A source story.",
                2,
                llm_request=llm_request,
            )
            with open(path, "r", encoding="utf-8") as beat_file:
                preserved = beat_file.read()

        self.assertEqual([str(beat) for beat in beats], ["Opening event", "Concluding event"])
        self.assertEqual(preserved, original)
        llm_request.assert_not_called()

    def test_comment_only_beats_file_triggers_generation(self):
        generated = ["A distinct opening.", "A conclusive ending."]
        llm_request = mock.Mock(return_value={"beats": generated})
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            with open(path, "w", encoding="utf-8") as beat_file:
                beat_file.write("# Generate these automatically.\n\n")

            beats = minimax.load_or_generate_beats(
                path,
                "A very short complete story.",
                2,
                llm_request=llm_request,
            )
            with open(path, "r", encoding="utf-8") as beat_file:
                saved = beat_file.read()

        self.assertEqual([str(beat) for beat in beats], generated)
        self.assertEqual(saved, "\n".join(generated) + "\n")
        llm_request.assert_called_once()

    def test_lora_only_beats_file_triggers_generation_and_tags_every_beat(self):
        generated = [
            "A mechanic discovers a message inside an antique radio.",
            "She follows its warning and prevents the station fire.",
        ]
        directive = "--lora minimax_h3_lighting.safetensors:1.0"
        llm_request = mock.Mock(return_value={"beats": generated})
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            with open(path, "w", encoding="utf-8") as beat_file:
                beat_file.write(directive + "\n")

            beats = minimax.load_or_generate_beats(
                path,
                "A mechanic hears a warning from the future.",
                2,
                llm_request=llm_request,
            )
            with open(path, "r", encoding="utf-8") as beat_file:
                saved = beat_file.read()

        expected_saved = "\n".join(
            f"{beat} {directive}" for beat in generated
        ) + "\n"
        self.assertEqual(saved, expected_saved)
        self.assertEqual([str(beat) for beat in beats], generated)
        self.assertEqual(
            [beat.lora_override for beat in beats],
            [
                ("minimax_h3_lighting.safetensors", 1.0),
                ("minimax_h3_lighting.safetensors", 1.0),
            ],
        )
        llm_request.assert_called_once()

    def test_blank_beats_are_generated_before_runtime_validation(self):
        args = SimpleNamespace(
            segment_length=5.0,
            total_length=15.0,
            megapixels=0.5,
            resume=1,
            steps=6,
            ff=False,
        )
        calls = mock.Mock()
        generated = mock.Mock(return_value=["Beat 1", "Beat 2", "Beat 3"])
        runtime = mock.Mock(side_effect=RuntimeError("stop after ordering check"))
        calls.attach_mock(generated, "generate_beats")
        calls.attach_mock(runtime, "validate_runtime")

        def fake_load(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return (
                    "beat_instructions: [Make the middle beat surprising.]\n"
                    "A three-part story."
                )
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return (
                    "<Subject 1> is Marc, a 40-year-old man referenced in "
                    "<Picture 1>."
                )
            return ""

        with mock.patch("minimax.parse_args", return_value=args), mock.patch(
            "minimax.load_text_file",
            side_effect=fake_load,
        ), mock.patch("minimax.reset_prompt_history"), mock.patch(
            "minimax.load_or_generate_beats",
            generated,
        ), mock.patch("minimax.validate_runtime_environment", runtime):
            with self.assertRaisesRegex(RuntimeError, "ordering check"):
                minimax._run_main(mock.Mock())

        self.assertEqual(
            [item[0] for item in calls.mock_calls],
            ["generate_beats", "validate_runtime"],
        )
        generated.assert_called_once()
        self.assertEqual(generated.call_args.args[2], 3)
        self.assertEqual(generated.call_args.args[1], "A three-part story.")
        self.assertEqual(
            generated.call_args.kwargs["beat_instructions"],
            "Make the middle beat surprising.",
        )
        self.assertEqual(
            generated.call_args.kwargs["subject_information"],
            "- Marc is a 40-year-old man.",
        )

    def test_invalid_subjects_stop_startup_before_beat_generation(self):
        args = SimpleNamespace(
            segment_length=5.0,
            total_length=10.0,
            megapixels=0.5,
            resume=1,
            steps=6,
            ff=False,
        )
        generated = mock.Mock()

        def fake_load(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "A two-part story."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "Marc is a mechanic."
            return ""

        with mock.patch("minimax.parse_args", return_value=args), mock.patch(
            "minimax.load_text_file",
            side_effect=fake_load,
        ), mock.patch("minimax.load_or_generate_beats", generated):
            with self.assertRaisesRegex(
                ValueError,
                r"Could not parse subjects\.txt line 1",
            ):
                minimax._run_main(mock.Mock())

        generated.assert_not_called()


if __name__ == "__main__":
    unittest.main()
