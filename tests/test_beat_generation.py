import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import minimax


class BeatGenerationTests(unittest.TestCase):
    def test_macro_arc_prompt_lists_only_subject_names(self):
        subjects = (
            "- Marc is a 40-year-old man.\n"
            "- Elena is a skilled pilot with a scar.\n"
            "- June is a main character."
        )

        messages = minimax.build_beat_arc_plan_messages(
            "A courier must return a stolen star before sunrise.",
            10,
            subject_information=subjects,
        )
        prompt = messages[1]["content"]
        subject_section = prompt.split("MAIN CHARACTER(S):\n", 1)[1].split(
            "\n\nSOURCE STORY", 1
        )[0]

        self.assertEqual(subject_section, "Marc, Elena, June")
        minimax.verify_subjects_in_beat_messages(
            messages,
            "Marc, Elena, June",
        )

    def test_macro_arc_prompt_and_schema_use_phase_beat_contract(self):
        messages = minimax.build_beat_arc_plan_messages(
            "Amy escapes a pursuit and reaches safety.",
            12,
            subject_information="- Amy is the protagonist.",
        )
        self.assertEqual(
            messages[0]["content"],
            "You are a conservative story editor planning a sequential video. "
            "The supplied source story, subjects, and macro arc are binding "
            "authorities. Return only the requested JSON object.",
        )
        prompt = messages[1]["content"]
        self.assertIn("Use ~5 phases", prompt)
        self.assertIn("beat 1 through beat\n12 exactly once", prompt)
        self.assertIn("beat_start and beat_end for each phase", prompt)
        self.assertIn("Phases do NOT need the same number of", prompt)
        self.assertIn("characters_introduced", prompt)
        self.assertIn("location", prompt)
        self.assertIn("phase_number", prompt)

        phase_schema = (
            minimax.build_beat_arc_response_format(12)["json_schema"]["schema"]
            ["properties"]["phases"]["items"]
        )
        self.assertEqual(
            set(phase_schema["required"]),
            {
                "phase_number",
                "beat_start",
                "beat_end",
                "narrative_purpose",
                "broad_progression",
                "characters_introduced",
                "location",
                "required_end_state",
            },
        )
        self.assertNotIn("segment_start", phase_schema["properties"])

    def test_macro_arc_parser_and_batches_preserve_phase_boundaries(self):
        arc = minimax.parse_beat_arc_plan(
            {
                "phases": [
                    {
                        "phase_number": 1,
                        "beat_start": 1,
                        "beat_end": 4,
                        "narrative_purpose": "Establish the pursuit.",
                        "broad_progression": "Amy is forced to flee.",
                        "characters_introduced": ["Amy"],
                        "location": "City streets",
                        "required_end_state": "Amy is cornered.",
                    },
                    {
                        "phase_number": 2,
                        "beat_start": 5,
                        "beat_end": 9,
                        "narrative_purpose": "Resolve the pursuit.",
                        "broad_progression": "Amy finds a route to safety.",
                        "characters_introduced": [],
                        "location": "Riverside warehouse",
                        "required_end_state": "Amy is safe.",
                    },
                ]
            },
            9,
        )
        batches = minimax.build_phase_generation_batches(arc, max_batch_size=3)

        self.assertEqual(
            [
                (
                    batch["phase"]["phase_number"],
                    batch["batch_start"],
                    batch["batch_end"],
                )
                for batch in batches
            ],
            [(1, 1, 3), (1, 4, 4), (2, 5, 7), (2, 8, 9)],
        )

        phase_batches = minimax.build_phase_generation_batches(arc)
        self.assertEqual(
            [
                (batch["batch_start"], batch["batch_end"])
                for batch in phase_batches
            ],
            [(1, 4), (5, 9)],
        )

    def test_phase_characters_introduced_are_selected_by_beat_range(self):
        macro_arc = {
            "phases": [
                {
                    "beat_start": 1,
                    "beat_end": 3,
                    "characters_introduced": ["Amy"],
                },
                {
                    "beat_start": 4,
                    "beat_end": 7,
                    "characters_introduced": ["The pilot", "Ben"],
                },
            ]
        }

        self.assertEqual(
            minimax.phase_characters_introduced_for_beat(macro_arc, 5),
            ["The pilot", "Ben"],
        )
        self.assertEqual(
            minimax.phase_characters_introduced_for_beat(macro_arc, 8),
            [],
        )

    def test_generated_phase_markers_round_trip_with_beats(self):
        macro_arc = {
            "phases": [
                {"phase_number": 1, "beat_start": 1, "beat_end": 2},
                {"phase_number": 2, "beat_start": 3, "beat_end": 4},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            minimax.save_generated_beats(
                ["Beat one.", "Beat two.", "Beat three.", "Beat four."],
                path,
                macro_arc=macro_arc,
            )
            beats = minimax.load_beats(path)
            with open(path, "r", encoding="utf-8") as beat_file:
                saved = beat_file.read()

        self.assertEqual(
            saved,
            "# Phase 1\n1. Beat one.\n2. Beat two.\n"
            "# Phase 2\n3. Beat three.\n4. Beat four.\n",
        )
        self.assertEqual([beat.phase_number for beat in beats], [1, 1, 2, 2])
        self.assertEqual(
            [beat.phase_start for beat in beats],
            [True, False, True, False],
        )
        self.assertFalse(minimax.is_new_phase_start(beats, 1))
        self.assertTrue(minimax.is_new_phase_start(beats, 3))

    def test_saved_beats_number_lines_with_file_level_lora(self):
        directive = "--lora lighting.safetensors:0.75"
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "beats.txt")
            minimax.save_generated_beats(
                ["Opening event.", "Concluding event."],
                path,
                lora_directive=directive,
            )
            with open(path, "r", encoding="utf-8") as beat_file:
                saved = beat_file.read()

        self.assertEqual(
            saved,
            "1. Opening event. --lora lighting.safetensors:0.75\n"
            "2. Concluding event. --lora lighting.safetensors:0.75\n",
        )

    def test_manual_phase_markers_are_supported(self):
        beats, _ = minimax.parse_beats_content(
            "Opening.\n# Phase 2\nA new phase begins.\nThe phase continues.\n"
        )

        self.assertIsNone(beats[0].phase_number)
        self.assertEqual(beats[1].phase_number, 2)
        self.assertTrue(beats[1].phase_start)
        self.assertFalse(beats[2].phase_start)

    def test_numbered_beats_are_parsed_without_number_prefixes(self):
        beats, _ = minimax.parse_beats_content(
            "# Phase 1\n"
            "1. Opening event.\n"
            "2. Rising action. --lora motion.safetensors:0.5\n"
            "# Phase 2\n"
            "3. Concluding event.\n"
        )

        self.assertEqual(
            [str(beat) for beat in beats],
            ["Opening event.", "Rising action.", "Concluding event."],
        )
        self.assertEqual(beats[1].lora_override, ("motion.safetensors", 0.5))
        self.assertEqual([beat.phase_number for beat in beats], [1, 1, 2])

    def test_numbered_beats_must_be_consecutive_and_ordered(self):
        with self.assertRaisesRegex(
            ValueError,
            "expected beat 2, found 3",
        ):
            minimax.parse_beats_content(
                "1. Opening event.\n3. Concluding event.\n"
            )

    def test_generation_requests_follow_macro_phase_ranges(self):
        calls = []

        def llm_request(messages, **kwargs):
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            calls.append((purpose, messages, metadata))
            if purpose == "beat_arc_plan":
                return {
                    "phases": [
                        {
                            "phase_number": 1,
                            "beat_start": 1,
                            "beat_end": 3,
                            "narrative_purpose": "Set up the rescue.",
                            "broad_progression": "The team locates the victim.",
                            "characters_introduced": ["The team"],
                            "location": "Mountain trail",
                            "required_end_state": "The victim is found.",
                        },
                        {
                            "phase_number": 2,
                            "beat_start": 4,
                            "beat_end": 7,
                            "narrative_purpose": "Complete the rescue.",
                            "broad_progression": "The team brings the victim home.",
                            "characters_introduced": ["The victim"],
                            "location": "Mountain shelter",
                            "required_end_state": "Everyone is safe.",
                        },
                    ]
                }
            if purpose == "beat_arc_fidelity":
                return {"valid": True, "issues": []}
            if purpose == "beat_generation":
                return {
                    "beats": [
                        {
                            "beat_number": beat_id,
                            "beat_text": (
                                f"Rescue event {beat_id} visibly advances the story."
                            ),
                        }
                        for beat_id in range(
                            metadata["batch_start"],
                            metadata["batch_end"] + 1,
                        )
                    ]
                }
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            story_source = (
                "A mountain team finds a victim and brings them safely home."
            )
            beats_path = os.path.join(directory, "beats.txt")
            beats = minimax.generate_beats_from_story(
                story_source,
                7,
                path=beats_path,
                llm_request=llm_request,
                content_attempts=1,
                audit_attempts=1,
            )
            with open(
                os.path.join(directory, "story_arc.txt"),
                "r",
                encoding="utf-8",
            ) as arc_file:
                saved_arc = json.load(arc_file)
            with open(
                os.path.join(directory, "story_arc.txt.sha256"),
                "r",
                encoding="utf-8",
            ) as hash_file:
                saved_source_hash = hash_file.read().strip()

        generation_calls = [call for call in calls if call[0] == "beat_generation"]
        self.assertEqual(
            [
                (
                    call[2]["phase_number"],
                    call[2]["batch_start"],
                    call[2]["batch_end"],
                )
                for call in generation_calls
            ],
            [(1, 1, 3), (2, 4, 7)],
        )
        self.assertIn(
            '"phase_number": 2',
            generation_calls[1][1][1]["content"],
        )
        self.assertEqual(len(beats), 7)
        self.assertEqual(saved_arc["phases"][1]["beat_start"], 4)
        self.assertEqual(
            saved_source_hash,
            minimax.hash_story_arc_source(story_source),
        )

    def test_existing_story_arc_is_used_without_requesting_a_new_arc(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Complete the delivery.",
                    "broad_progression": "The courier reaches the destination.",
                    "characters_introduced": ["The courier"],
                    "location": "Mountain road",
                    "required_end_state": "The package is delivered.",
                }
            ]
        }
        purposes = []

        def llm_request(messages, **kwargs):
            del messages
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            purposes.append(purpose)
            if purpose == "beat_generation":
                return {
                    "beats": [
                        {
                            "beat_number": 1,
                            "beat_text": "The courier climbs the mountain road.",
                        },
                        {
                            "beat_number": 2,
                            "beat_text": "The courier delivers the package safely.",
                        },
                    ]
                }
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            story_source = "A courier completes a mountain delivery."
            beats_path = os.path.join(directory, "beats.txt")
            arc_path = os.path.join(directory, "story_arc.txt")
            with open(beats_path, "w", encoding="utf-8") as beat_file:
                beat_file.write("")
            minimax.save_story_arc(macro_arc, story_source, arc_path)
            with open(arc_path, "r", encoding="utf-8") as arc_file:
                original_arc_text = arc_file.read()

            beats = minimax.load_or_generate_beats(
                beats_path,
                story_source,
                2,
                llm_request=llm_request,
            )
            with open(arc_path, "r", encoding="utf-8") as arc_file:
                preserved_arc_text = arc_file.read()

        self.assertEqual(
            [str(beat) for beat in beats],
            [
                "The courier climbs the mountain road.",
                "The courier delivers the package safely.",
            ],
        )
        self.assertEqual(
            purposes,
            ["beat_generation", "beat_phase_validation", "beat_plan_audit"],
        )
        self.assertEqual(preserved_arc_text, original_arc_text)

    def test_story_arc_hash_mismatch_regenerates_and_overwrites_arc(self):
        old_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Follow the old journey.",
                    "broad_progression": "A sailor crosses the sea.",
                    "characters_introduced": ["The sailor"],
                    "location": "Open sea",
                    "required_end_state": "The sailor reaches port.",
                }
            ]
        }
        new_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Complete the new delivery.",
                    "broad_progression": "A pilot reaches the airfield.",
                    "characters_introduced": ["The pilot"],
                    "location": "Mountain airfield",
                    "required_end_state": "The medicine is delivered.",
                }
            ]
        }
        purposes = []

        def llm_request(messages, **kwargs):
            del messages
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            purposes.append(purpose)
            if purpose == "beat_arc_plan":
                return new_arc
            if purpose == "beat_arc_fidelity":
                return {"valid": True, "issues": []}
            if purpose == "beat_generation":
                return {
                    "beats": [
                        {
                            "beat_number": 1,
                            "beat_text": "The pilot lands at the mountain airfield.",
                        },
                        {
                            "beat_number": 2,
                            "beat_text": "The pilot delivers the medicine safely.",
                        },
                    ]
                }
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            old_story = "A sailor completes a sea voyage."
            new_story = "A pilot delivers medicine to a mountain airfield."
            beats_path = os.path.join(directory, "beats.txt")
            arc_path = os.path.join(directory, "story_arc.txt")
            with open(beats_path, "w", encoding="utf-8") as beat_file:
                beat_file.write("")
            minimax.save_story_arc(old_arc, old_story, arc_path)

            minimax.load_or_generate_beats(
                beats_path,
                new_story,
                2,
                llm_request=llm_request,
            )
            with open(arc_path, "r", encoding="utf-8") as arc_file:
                saved_arc = json.load(arc_file)
            with open(
                minimax.get_story_arc_hash_path(arc_path),
                "r",
                encoding="utf-8",
            ) as hash_file:
                saved_hash = hash_file.read().strip()

        self.assertEqual(
            purposes,
            [
                "beat_arc_plan",
                "beat_arc_fidelity",
                "beat_generation",
                "beat_phase_validation",
                "beat_plan_audit",
            ],
        )
        self.assertEqual(saved_arc, new_arc)
        self.assertEqual(saved_hash, minimax.hash_story_arc_source(new_story))

    def test_future_macro_introduction_retries_the_phase(self):
        generation_calls = []
        phase_one_attempts = 0

        def llm_request(messages, **kwargs):
            nonlocal phase_one_attempts
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            if purpose == "beat_arc_plan":
                return {
                    "phases": [
                        {
                            "phase_number": 1,
                            "beat_start": 1,
                            "beat_end": 2,
                            "narrative_purpose": "Amy begins her search.",
                            "broad_progression": "Amy searches the city.",
                            "characters_introduced": ["Amy"],
                            "location": "City streets",
                            "required_end_state": "Amy finds a clue.",
                        },
                        {
                            "phase_number": 2,
                            "beat_start": 3,
                            "beat_end": 4,
                            "narrative_purpose": "Amy finds Jim.",
                            "broad_progression": "Jim helps Amy finish the search.",
                            "characters_introduced": ["Jim"],
                            "location": "Jim's House",
                            "required_end_state": "Amy and Jim are safe.",
                        },
                    ]
                }
            if purpose == "beat_arc_fidelity":
                return {"valid": True, "issues": []}
            if purpose == "beat_generation":
                generation_calls.append(messages)
                phase_number = metadata["phase_number"]
                if phase_number == 1:
                    phase_one_attempts += 1
                    second_text = (
                        "Amy sees Jim outside Jim's House."
                        if phase_one_attempts == 1
                        else "Amy finds a clue beside the city fountain."
                    )
                    return {
                        "beats": [
                            {
                                "beat_number": 1,
                                "beat_text": "Amy searches the city streets.",
                            },
                            {"beat_number": 2, "beat_text": second_text},
                        ]
                    }
                return {
                    "beats": [
                        {
                            "beat_number": 3,
                            "beat_text": "Jim welcomes Amy into Jim's House.",
                        },
                        {
                            "beat_number": 4,
                            "beat_text": "Amy and Jim complete the search safely.",
                        },
                    ]
                }
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            beats = minimax.generate_beats_from_story(
                "Amy searches for Jim and eventually finds him safely at home.",
                4,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
                content_attempts=2,
                audit_attempts=1,
            )

        self.assertEqual(phase_one_attempts, 2)
        retry_prompt = generation_calls[1][1]["content"]
        self.assertIn("PREVIOUS RESPONSE WAS INVALID", retry_prompt)
        self.assertIn("future location \"Jim's House\"", retry_prompt)
        self.assertIn("future character 'Jim'", retry_prompt)
        self.assertEqual(
            [str(beat) for beat in beats],
            [
                "Amy searches the city streets.",
                "Amy finds a clue beside the city fountain.",
                "Jim welcomes Amy into Jim's House.",
                "Amy and Jim complete the search safely.",
            ],
        )

    def test_beat_generation_retries_past_former_limits_until_valid(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Complete the rescue.",
                    "broad_progression": "Amy finds and rescues Ben.",
                    "characters_introduced": ["Amy", "Ben"],
                    "location": "Mountain trail",
                    "required_end_state": "Ben is safe.",
                }
            ]
        }
        generation_attempts = 0

        def llm_request(_messages, **kwargs):
            nonlocal generation_attempts
            purpose = kwargs["history_metadata"]["purpose"]
            if purpose == "beat_generation":
                generation_attempts += 1
                if generation_attempts <= 5:
                    return {"beats": ["Only one beat is returned."]}
                return {
                    "beats": [
                        {
                            "beat_number": 1,
                            "beat_text": "Amy finds Ben on the mountain trail.",
                        },
                        {
                            "beat_number": 2,
                            "beat_text": "Amy brings Ben safely home.",
                        },
                    ]
                }
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            beats_path = os.path.join(directory, "beats.txt")
            arc_path = os.path.join(directory, "story_arc.txt")
            with open(arc_path, "w", encoding="utf-8") as arc_file:
                json.dump(macro_arc, arc_file)
            beats = minimax.generate_beats_from_story(
                "Amy rescues Ben from a mountain trail.",
                2,
                path=beats_path,
                llm_request=llm_request,
                content_attempts=1,
                audit_attempts=1,
            )

        self.assertEqual(generation_attempts, 6)
        self.assertEqual(
            [str(beat) for beat in beats],
            [
                "Amy finds Ben on the mountain trail.",
                "Amy brings Ben safely home.",
            ],
        )

    def test_user_interrupt_escapes_unlimited_beat_generation(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ), self.assertRaises(KeyboardInterrupt):
            minimax.generate_beats_from_story(
                "Amy begins a rescue.",
                2,
                path=os.path.join(directory, "beats.txt"),
                llm_request=mock.Mock(side_effect=KeyboardInterrupt),
            )

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
        self.assertEqual(
            messages[0]["content"],
            "You are a movie director planning a sequential video. The supplied "
            "MACRO STORY ARC is the authoritative Bible and drives the story. "
            "Return only the requested JSON object.",
        )
        self.assertIn("exactly 10 ordered story beats for phase 1", prompt)
        self.assertIn("follow the MACRO STORY ARC's phase 1", prompt)
        self.assertIn("Each beat must be one complete sentence", prompt)
        self.assertIn("Beat 10 must conclusively satisfy", prompt)
        self.assertIn("Never repeat, recap, restage", prompt)
        self.assertIn("A courier must return a stolen star", prompt)
        self.assertIn("ADDITIONAL BEAT INSTRUCTIONS FROM STORY.TXT", prompt)
        self.assertIn(extra, prompt)
        self.assertIn("copy it character-for-character", prompt)
        self.assertIn("silently audit every beat", prompt)
        self.assertIn("Main Character(s):\nMarc, Elena", prompt)
        self.assertNotIn("40-year-old", prompt)
        self.assertIn("PREVIOUS BEATS: N/A", prompt)

        schema = minimax.build_beats_response_format(10)["json_schema"]["schema"]
        beat_array = schema["properties"]["beats"]
        self.assertEqual(beat_array["minItems"], 10)
        self.assertEqual(beat_array["maxItems"], 10)
        self.assertTrue(beat_array["uniqueItems"])
        item = beat_array["items"]
        self.assertEqual(set(item["required"]), {"beat_number", "beat_text"})
        self.assertIn(
            "One concise, complete sentence",
            item["properties"]["beat_text"]["description"],
        )

    def test_later_phase_prompt_includes_all_earlier_beats_as_state_authority(self):
        phase = {
            "phase_number": 2,
            "beat_start": 8,
            "beat_end": 10,
            "characters_introduced": ["Elena"],
            "location": "Observatory",
        }
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 7,
                    "characters_introduced": ["Marc"],
                    "location": "Harbor",
                },
                phase,
            ]
        }

        messages = minimax.build_beat_generation_messages(
            "A courier must return a stolen star before sunrise.",
            10,
            subject_information="- Marc is a courier.\n- Elena is a pilot.",
            batch_start=8,
            batch_end=10,
            previous_beats=[f"Previous event {number}." for number in range(1, 8)],
            macro_arc=macro_arc,
            current_phase=phase,
        )
        prompt = messages[1]["content"]

        self.assertIn("exactly 3 ordered story beats for phase 2", prompt)
        self.assertIn("Beat 1: Previous event 1.", prompt)
        self.assertIn("Beat 2: Previous event 2.", prompt)
        self.assertIn("Beat 3: Previous event 3.", prompt)
        self.assertIn("Beat 7: Previous event 7.", prompt)
        self.assertIn("PERSISTENT STATE AUTHORITY", prompt)
        self.assertIn('"phase_number": 2', prompt)
        schema = minimax.build_beats_response_format(3, beat_start=8)[
            "json_schema"
        ]["schema"]
        number_schema = schema["properties"]["beats"]["items"]["properties"][
            "beat_number"
        ]
        self.assertEqual((number_schema["minimum"], number_schema["maximum"]), (8, 10))

    def test_generation_prompt_stops_at_current_phase_end_state(self):
        prompt = minimax.build_beat_generation_messages(
            "Amy follows a two-phase route.",
            2,
        )[1]["content"]

        self.assertIn(
            "The final beat should reach the **current phase end state**, but "
            "it should **not automatically perform Beat 1 of the next phase**.",
            prompt,
        )

    def test_phase_validation_prompt_checks_end_state_and_next_phase_leakage(self):
        current_phase = {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 2,
            "narrative_purpose": "Find the missing map.",
            "broad_progression": "Amy searches the harbor.",
            "characters_introduced": ["Amy"],
            "location": "Harbor",
            "required_end_state": "Amy has the map.",
        }
        next_phase = {
            "phase_number": 2,
            "beat_start": 3,
            "beat_end": 4,
            "narrative_purpose": "Use the map to enter the lighthouse.",
            "broad_progression": "Amy reaches and enters the lighthouse.",
            "characters_introduced": ["The keeper"],
            "location": "Lighthouse",
            "required_end_state": "Amy meets the keeper.",
        }

        messages = minimax.build_beat_phase_validation_messages(
            ["Amy searches the docks.", "Amy recovers the missing map."],
            current_phase,
            next_phase,
        )
        prompt = messages[1]["content"]

        self.assertIn("required_end_state", prompt)
        self.assertIn("Amy has the map.", prompt)
        self.assertIn("next_phase_scope_creep", prompt)
        self.assertIn("bad_opening_continuity", prompt)
        self.assertIn("Amy reaches and enters the lighthouse.", prompt)
        self.assertIn("Beat 2: Amy recovers the missing map.", prompt)
        self.assertNotIn("\nSOURCE STORY\n", prompt)
        schema = minimax.build_beat_phase_validation_response_format()
        self.assertEqual(
            schema["json_schema"]["name"],
            "story_beat_phase_validation",
        )
        issue_schema = schema["json_schema"]["schema"]["properties"]["issues"][
            "items"
        ]
        self.assertEqual(issue_schema["type"], "object")
        self.assertEqual(
            set(issue_schema["required"]),
            {"beat_id", "type", "problem"},
        )
        self.assertFalse(issue_schema["additionalProperties"])
        self.assertEqual(
            issue_schema["properties"]["type"]["enum"],
            [
                "missing_end_state",
                "next_phase_scope_creep",
                "future_character",
                "future_location",
                "bad_opening_continuity",
                "persistent_state_conflict",
            ],
        )

    def test_phase_validation_parser_requires_structured_typed_issues(self):
        parsed = minimax.parse_beat_phase_validation(
            {
                "valid": False,
                "issues": [
                    {
                        "beat_id": 20,
                        "type": "missing_end_state",
                        "problem": "  Mark has not   reached the park exit. ",
                    },
                    {
                        "beat_id": 19,
                        "type": "next_phase_scope_creep",
                        "problem": "The alien abduction begins too early.",
                    },
                ],
            },
            beat_start=11,
            beat_end=20,
        )

        self.assertEqual(
            parsed["issues"][0],
            {
                "beat_id": 20,
                "type": "missing_end_state",
                "problem": "Mark has not reached the park exit.",
            },
        )
        invalid_issues = [
            "Beat 20 is invalid.",
            {"beat_id": True, "type": "missing_end_state", "problem": "Bad."},
            {"beat_id": 20, "type": "unknown", "problem": "Bad."},
            {"beat_id": 20, "type": "missing_end_state", "problem": " "},
            {
                "beat_id": 20,
                "type": "missing_end_state",
                "problem": "Bad.",
                "extra": True,
            },
        ]
        for issue in invalid_issues:
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                minimax.parse_beat_phase_validation(
                    {"valid": False, "issues": [issue]}
                )

    def test_phase_validation_keeps_previously_passed_beats_accepted(self):
        passed_beat_ids = set()
        first, ignored = minimax.reconcile_beat_phase_validation(
            {
                "valid": False,
                "issues": [{
                    "beat_id": 5,
                    "type": "missing_end_state",
                    "problem": "Beat 5 misses the required end state.",
                }],
            },
            4,
            5,
            passed_beat_ids,
        )

        self.assertEqual(passed_beat_ids, {4})
        self.assertEqual([issue["beat_id"] for issue in first["issues"]], [5])
        self.assertEqual(ignored, [])

        second, ignored = minimax.reconcile_beat_phase_validation(
            {
                "valid": False,
                "issues": [
                    {
                        "beat_id": 4,
                        "type": "bad_opening_continuity",
                        "problem": "The validator changed its opinion about Beat 4.",
                    },
                    {
                        "beat_id": 5,
                        "type": "missing_end_state",
                        "problem": "Beat 5 still misses the required end state.",
                    },
                ],
            },
            4,
            5,
            passed_beat_ids,
        )

        self.assertFalse(second["valid"])
        self.assertEqual([issue["beat_id"] for issue in second["issues"]], [5])
        self.assertEqual([issue["beat_id"] for issue in ignored], [4])

        third, ignored = minimax.reconcile_beat_phase_validation(
            {
                "valid": False,
                "issues": [{
                    "beat_id": 4,
                    "type": "bad_opening_continuity",
                    "problem": "Only the previously passed beat is challenged.",
                }],
            },
            4,
            5,
            passed_beat_ids,
        )

        self.assertTrue(third["valid"])
        self.assertEqual(third["issues"], [])
        self.assertEqual([issue["beat_id"] for issue in ignored], [4])
        self.assertEqual(passed_beat_ids, {4, 5})

    def test_phase_repair_targets_each_unique_violating_id_only(self):
        current_phase = {
            "phase_number": 2,
            "beat_start": 5,
            "beat_end": 7,
            "narrative_purpose": "Recover the map.",
            "broad_progression": "Amy searches the harbor and finds the map.",
            "characters_introduced": [],
            "location": "Harbor",
            "required_end_state": "Amy has the map.",
        }
        validation = {
            "valid": False,
            "issues": [
                {
                    "beat_id": 7,
                    "type": "missing_end_state",
                    "problem": "Amy does not recover the map.",
                },
                {
                    "beat_id": 5,
                    "type": "bad_opening_continuity",
                    "problem": "Amy begins in the wrong location.",
                },
                {
                    "beat_id": 7,
                    "type": "next_phase_scope_creep",
                    "problem": "Amy begins the next journey too early.",
                },
            ],
        }

        repair_ranges = minimax.beat_phase_validation_repair_ranges(validation)
        messages = minimax.build_beat_phase_repair_messages(
            ["Wrong opening.", "Amy searches the pier.", "Wrong ending."],
            current_phase,
            validation,
            previous_beats=[f"Prior event {number}." for number in range(1, 5)],
        )
        schema = minimax.build_beat_plan_repair_response_format(repair_ranges)
        beat_array = schema["json_schema"]["schema"]["properties"]["beats"]

        self.assertEqual(
            repair_ranges,
            [
                {"beat_start": 5, "beat_end": 5},
                {"beat_start": 7, "beat_end": 7},
            ],
        )
        self.assertEqual((beat_array["minItems"], beat_array["maxItems"]), (2, 2))
        self.assertEqual(
            beat_array["items"]["properties"]["beat_id"]["enum"],
            [5, 7],
        )
        self.assertIn("Repair only violating Beat IDs 5, 7", messages[1]["content"])
        self.assertIn("Beat 6: Amy searches the pier.", messages[1]["content"])
        self.assertIn("and no others", messages[1]["content"])

    def test_phase_validation_rejection_repairs_only_violating_beats(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Find the missing map.",
                    "broad_progression": "Amy searches the harbor.",
                    "characters_introduced": ["Amy"],
                    "location": "Harbor",
                    "required_end_state": "Amy has the map.",
                },
                {
                    "phase_number": 2,
                    "beat_start": 3,
                    "beat_end": 4,
                    "narrative_purpose": "Decode the missing map.",
                    "broad_progression": "Amy identifies the lighthouse route.",
                    "characters_introduced": [],
                    "location": "Harbor office",
                    "required_end_state": "Amy knows the lighthouse route.",
                },
            ]
        }
        purposes = []
        phase_one_generations = 0
        phase_one_validations = 0

        def llm_request(messages, **kwargs):
            nonlocal phase_one_generations, phase_one_validations
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            purposes.append(purpose)
            if purpose == "beat_generation":
                if metadata["phase_number"] == 1:
                    phase_one_generations += 1
                    return {"beats": [
                        "Amy searches the harbor for the missing map.",
                        "Amy identifies the lighthouse route from a copied symbol without finding the map.",
                    ]}
                return {"beats": [
                    "Amy carries the recovered map into the harbor office.",
                    "Amy deciphers the map and identifies the lighthouse route.",
                ]}
            if purpose == "beat_phase_validation":
                if metadata["phase_number"] == 1:
                    phase_one_validations += 1
                if metadata["phase_number"] == 1 and phase_one_validations == 1:
                    return {
                        "valid": False,
                        "issues": [
                            {
                                "beat_id": 2,
                                "type": "missing_end_state",
                                "problem": "The final beat does not recover the missing map.",
                            },
                            {
                                "beat_id": 2,
                                "type": "next_phase_scope_creep",
                                "problem": "The lighthouse route is identified before phase 2.",
                            },
                        ],
                    }
                if metadata["phase_number"] == 1 and phase_one_validations == 2:
                    return {
                        "valid": False,
                        "issues": [{
                            "beat_id": 1,
                            "type": "bad_opening_continuity",
                            "problem": (
                                "A new seed now disputes the already accepted "
                                "opening beat."
                            ),
                        }],
                    }
                return {"valid": True, "issues": []}
            if purpose == "beat_phase_repair":
                self.assertEqual(metadata["repair_beat_ids"], [2])
                beat_array = kwargs["response_format"]["json_schema"]["schema"][
                    "properties"
                ]["beats"]
                self.assertEqual((beat_array["minItems"], beat_array["maxItems"]), (1, 1))
                self.assertEqual(
                    beat_array["items"]["properties"]["beat_id"]["enum"],
                    [2],
                )
                repair_prompt = messages[1]["content"]
                self.assertIn("Repair only violating Beat IDs 2", repair_prompt)
                self.assertIn(
                    "Do not rewrite, paraphrase, or return any non-violating beat.",
                    repair_prompt,
                )
                self.assertIn(
                    "Beat 1: Amy searches the harbor for the missing map.",
                    repair_prompt,
                )
                self.assertNotIn("Regenerate this entire phase", repair_prompt)
                return {
                    "beats": [{
                        "beat_id": 2,
                        "text": "Amy recovers the map from beneath the pier.",
                    }]
                }
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ), mock.patch("minimax.load_story_arc", return_value=macro_arc):
            beats = minimax.generate_beats_from_story(
                "Amy finds a map, then deciphers its route to a lighthouse.",
                4,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(phase_one_generations, 1)
        self.assertEqual(phase_one_validations, 2)
        self.assertEqual(
            purposes,
            [
                "beat_generation",
                "beat_phase_validation",
                "beat_phase_repair",
                "beat_phase_validation",
                "beat_generation",
                "beat_phase_validation",
                "beat_plan_audit",
            ],
        )
        self.assertEqual(
            [str(beat) for beat in beats],
            [
                "Amy searches the harbor for the missing map.",
                "Amy recovers the map from beneath the pier.",
                "Amy carries the recovered map into the harbor office.",
                "Amy deciphers the map and identifies the lighthouse route.",
            ],
        )

    def test_subsequent_repair_requests_exclude_previously_passed_beats(self):
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 2,
                "narrative_purpose": "Find the missing map.",
                "broad_progression": "Amy searches the harbor for the map.",
                "characters_introduced": ["Amy"],
                "location": "Harbor",
                "required_end_state": "Amy has the map.",
            }]
        }
        validation_attempt = 0
        repair_calls = []

        def issue(beat_id, issue_type, problem):
            return {
                "beat_id": beat_id,
                "type": issue_type,
                "problem": problem,
            }

        def llm_request(messages, **kwargs):
            nonlocal validation_attempt
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            if purpose == "beat_generation":
                return {
                    "beats": [
                        "Amy searches the harbor warehouses.",
                        "Amy leaves the harbor without finding the map.",
                    ]
                }
            if purpose == "beat_phase_validation":
                validation_attempt += 1
                if validation_attempt == 1:
                    return {
                        "valid": False,
                        "issues": [issue(
                            2,
                            "missing_end_state",
                            "Amy still does not have the map.",
                        )],
                    }
                if validation_attempt == 2:
                    return {
                        "valid": False,
                        "issues": [
                            issue(
                                1,
                                "bad_opening_continuity",
                                "A new seed disputes the already passed opening.",
                            ),
                            issue(
                                2,
                                "missing_end_state",
                                "Amy still does not have the map.",
                            ),
                        ],
                    }
                return {
                    "valid": False,
                    "issues": [issue(
                        1,
                        "bad_opening_continuity",
                        "A third seed disputes only the passed opening.",
                    )],
                }
            if purpose == "beat_phase_repair":
                repair_calls.append((messages, kwargs))
                repair_number = len(repair_calls)
                return {
                    "beats": [{
                        "beat_id": 2,
                        "text": (
                            "Amy finds a clue pointing to the map beneath the pier."
                            if repair_number == 1
                            else "Amy recovers the map from beneath the pier."
                        ),
                    }]
                }
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ), mock.patch(
            "minimax.load_story_arc",
            return_value=macro_arc,
        ):
            beats = minimax.generate_beats_from_story(
                "Amy searches the harbor and recovers a missing map.",
                2,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(validation_attempt, 3)
        self.assertEqual(len(repair_calls), 2)
        for messages, kwargs in repair_calls:
            self.assertEqual(
                kwargs["history_metadata"]["repair_beat_ids"],
                [2],
            )
            beat_id_schema = kwargs["response_format"]["json_schema"]["schema"][
                "properties"
            ]["beats"]["items"]["properties"]["beat_id"]
            self.assertEqual(beat_id_schema["enum"], [2])
            self.assertIn(
                "Repair only violating Beat IDs 2",
                messages[1]["content"],
            )
            self.assertNotIn('"beat_id": 1', messages[1]["content"])
            self.assertNotIn(
                "A new seed disputes the already passed opening.",
                messages[1]["content"],
            )
        self.assertEqual(
            [str(beat) for beat in beats],
            [
                "Amy searches the harbor warehouses.",
                "Amy recovers the map from beneath the pier.",
            ],
        )

    def test_targeted_phase_repairs_stop_after_round_ten(self):
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 2,
                "narrative_purpose": "Find the missing map.",
                "broad_progression": "Amy searches the harbor for the map.",
                "characters_introduced": ["Amy"],
                "location": "Harbor",
                "required_end_state": "Amy has the map.",
            }]
        }
        validation_attempts = 0
        repair_rounds = []

        def llm_request(_messages, **kwargs):
            nonlocal validation_attempts
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            if purpose == "beat_generation":
                return {
                    "beats": [
                        "Amy searches the harbor warehouses.",
                        "Amy leaves without finding the map.",
                    ]
                }
            if purpose == "beat_phase_validation":
                validation_attempts += 1
                return {
                    "valid": False,
                    "issues": [{
                        "beat_id": 2,
                        "type": "missing_end_state",
                        "problem": "The seeded validator continues to reject Beat 2.",
                    }],
                }
            if purpose == "beat_phase_repair":
                repair_round = metadata["repair_round"]
                repair_rounds.append(repair_round)
                return {
                    "beats": [{
                        "beat_id": 2,
                        "text": (
                            f"Amy follows map clue revision {repair_round} along "
                            "the pier."
                        ),
                    }]
                }
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ) as print_mock, mock.patch(
            "minimax.load_story_arc",
            return_value=macro_arc,
        ):
            beats = minimax.generate_beats_from_story(
                "Amy searches the harbor for a missing map.",
                2,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(repair_rounds, list(range(1, 11)))
        self.assertEqual(validation_attempts, 11)
        self.assertEqual(
            str(beats[1]),
            "Amy follows map clue revision 10 along the pier.",
        )
        rendered_output = "\n".join(
            str(call.args[0]) for call in print_mock.call_args_list if call.args
        )
        self.assertNotIn("repair round 11", rendered_output)
        self.assertIn(
            "reached the 10-round targeted-repair limit",
            rendered_output,
        )

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
            subject_information=subjects,
        )

        self.assertIn("Main Character(s):\nMarc, Elena", initial[1]["content"])
        self.assertNotIn("Marc is a mechanic", initial[1]["content"])
        minimax.verify_subjects_in_beat_messages(initial, "Marc, Elena")
        self.assertIn(subjects, review[1]["content"])
        minimax.verify_subjects_in_beat_messages(review, subjects)

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

    def test_ministral_asterisks_are_removed_from_generated_beats(self):
        formatter = minimax.MinistralFormatter()
        beats = minimax.parse_generated_beats(
            {
                "beats": [
                    "**The courier** opens the *sealed* vault.",
                    "The *stolen star* returns before sunrise.*",
                ]
            },
            2,
            formatter=formatter,
        )

        self.assertEqual(
            beats,
            [
                "The courier opens the sealed vault.",
                "The stolen star returns before sunrise.",
            ],
        )
        self.assertTrue(all("*" not in beat for beat in beats))

        self.assertEqual(
            minimax.parse_generated_beats(
                "**Beats:**\n* **The courier** opens the vault.\n"
                "* The stolen star *returns* before sunrise.",
                2,
                formatter=formatter,
            ),
            [
                "The courier opens the vault.",
                "The stolen star returns before sunrise.",
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

    def test_parser_accepts_numbered_single_sentences_and_rejects_two(self):
        with self.assertRaisesRegex(ValueError, "exactly one complete sentence"):
            minimax.parse_generated_beats(
                {
                    "beats": [
                        {
                            "beat_number": 8,
                            "beat_text": "The vault opens and the alarm sounds.",
                        },
                        {
                            "beat_number": 9,
                            "beat_text": "The guards arrive. They catch the thief.",
                        },
                    ]
                },
                2,
                expected_start=8,
            )
        with self.assertRaisesRegex(ValueError, "exactly one complete sentence"):
            minimax.parse_generated_beats(
                {"beats": ["The unfinished opening", "The story concludes."]},
                2,
            )

        self.assertEqual(
            minimax.parse_generated_beats(
                {
                    "beats": [
                        {
                            "beat_number": 8,
                            "beat_text": (
                                "Dr. Reyes discovers and activates the hidden "
                                "transmitter."
                            ),
                        },
                        {
                            "beat_number": 9,
                            "beat_text": 'She shouts "Run!" before sealing the tunnel.',
                        },
                    ]
                },
                2,
                expected_start=8,
            ),
            [
                "Dr. Reyes discovers and activates the hidden transmitter.",
                'She shouts "Run!" before sealing the tunnel.',
            ],
        )

        with self.assertRaisesRegex(ValueError, "beat_number 8"):
            minimax.parse_generated_beats(
                {
                    "beats": [
                        {"beat_number": 1, "beat_text": "The vault opens."},
                        {"beat_number": 9, "beat_text": "The guard arrives."},
                    ]
                },
                2,
                expected_start=8,
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

    def test_macro_introduction_validator_rejects_future_locations_and_characters(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "characters_introduced": ["Amy"],
                    "location": "City streets",
                },
                {
                    "phase_number": 2,
                    "beat_start": 3,
                    "beat_end": 4,
                    "characters_introduced": ["Jim"],
                    "location": "Jim's House",
                },
            ]
        }

        issues = minimax.validate_generated_beat_macro_introductions(
            [
                "Amy searches the city streets.",
                "Amy sees Jim waiting outside Jim's House.",
            ],
            macro_arc,
        )

        self.assertEqual(len(issues), 2)
        self.assertTrue(
            any("future location \"Jim's House\"" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("future character 'Jim'" in issue for issue in issues), issues)

        self.assertEqual(
            minimax.validate_generated_beat_macro_introductions(
                [
                    "Jim welcomes Amy into Jim's House.",
                    "Amy and Jim secure the front door.",
                ],
                macro_arc,
                beat_start=3,
            ),
            [],
        )

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
                        valid_beats[0] + " A second sentence is allowed. A third is not.",
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
            self.assertEqual(
                saved,
                "\n".join(
                    f"{number}. {beat}"
                    for number, beat in enumerate(valid_beats, start=1)
                ) + "\n",
            )
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
        self.assertIn("exactly one complete sentence", retry_prompt)
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

    def test_duplicate_failure_keeps_retrying_until_valid(self):
        invalid_beats = [
            f"Visible story event {number} advances the plot."
            for number in range(1, 21)
        ]
        invalid_beats[18] = invalid_beats[17]
        valid_beats = list(invalid_beats)
        valid_beats[18] = "The gate opens and everyone runs inside."
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 20,
                "narrative_purpose": "Complete the chase.",
                "broad_progression": "The group crosses the city.",
                "characters_introduced": [],
                "location": "The city",
                "required_end_state": "The group reaches safety.",
            }]
        }
        llm_request = mock.Mock(
            side_effect=(
                [{"beats": list(invalid_beats)} for _ in range(5)]
                + [
                    {"beats": valid_beats},
                    {"valid": True, "issues": []},
                    {
                        "valid": True,
                        "macro_arc_consistent_with_source": True,
                        "blocking_issues": [],
                        "warnings": [],
                    },
                ]
            )
        )

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ), mock.patch("minimax.load_story_arc", return_value=macro_arc):
            beats = minimax.generate_beats_from_story(
                "A group races through a dangerous city.",
                20,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
                content_attempts=1,
            )

        self.assertEqual([str(beat) for beat in beats], valid_beats)
        self.assertEqual(llm_request.call_count, 8)

    def test_tenth_phase_generation_failure_uses_tenth_response(self):
        invalid_beats = [
            "The group enters the city.",
            "The group enters the city.",
            "The group reaches the safe house.",
        ]
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 3,
                "narrative_purpose": "Complete the escape.",
                "broad_progression": "The group crosses the city to safety.",
                "characters_introduced": [],
                "location": "The city",
                "required_end_state": "The group reaches safety.",
            }]
        }
        generation_attempts = []

        def llm_request(_messages, **kwargs):
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            if purpose == "beat_generation":
                generation_attempts.append(metadata["attempt"])
                return {"beats": list(invalid_beats)}
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ) as print_mock, mock.patch(
            "minimax.load_story_arc",
            return_value=macro_arc,
        ):
            beats = minimax.generate_beats_from_story(
                "A group escapes through a dangerous city.",
                3,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(generation_attempts, list(range(1, 11)))
        self.assertEqual([str(beat) for beat in beats], invalid_beats)
        rendered_output = "\n".join(
            str(call.args[0]) for call in print_mock.call_args_list if call.args
        )
        self.assertIn(
            "using the beats returned on that attempt",
            rendered_output,
        )

    def test_unusable_tenth_response_waits_for_next_usable_beat_list(self):
        usable_beats = [
            "The group enters the city.",
            "The group enters the city.",
            "The group reaches the safe house.",
        ]
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 3,
                "narrative_purpose": "Complete the escape.",
                "broad_progression": "The group crosses the city to safety.",
                "characters_introduced": [],
                "location": "The city",
                "required_end_state": "The group reaches safety.",
            }]
        }
        generation_attempts = []

        def llm_request(_messages, **kwargs):
            metadata = kwargs["history_metadata"]
            purpose = metadata["purpose"]
            if purpose == "beat_generation":
                generation_attempts.append(metadata["attempt"])
                if metadata["attempt"] <= 10:
                    return {"beats": ["Only one beat is returned."]}
                return {"beats": list(usable_beats)}
            if purpose == "beat_phase_validation":
                return {"valid": True, "issues": []}
            if purpose == "beat_plan_audit":
                return {
                    "valid": True,
                    "macro_arc_consistent_with_source": True,
                    "blocking_issues": [],
                    "warnings": [],
                }
            raise AssertionError(f"Unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ) as print_mock, mock.patch(
            "minimax.load_story_arc",
            return_value=macro_arc,
        ):
            beats = minimax.generate_beats_from_story(
                "A group escapes through a dangerous city.",
                3,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(generation_attempts, list(range(1, 12)))
        self.assertEqual([str(beat) for beat in beats], usable_beats)
        rendered_output = "\n".join(
            str(call.args[0]) for call in print_mock.call_args_list if call.args
        )
        self.assertIn(
            "Continuing until the next usable beat list is returned.",
            rendered_output,
        )
        self.assertIn(
            "attempt 11; waiting for the next structurally usable beat list",
            rendered_output,
        )

    def test_wrong_beat_count_keeps_requesting_until_interrupt(self):
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 2,
                "narrative_purpose": "Complete the story.",
                "broad_progression": "The story advances.",
                "characters_introduced": [],
                "location": "A location",
                "required_end_state": "The story concludes.",
            }]
        }
        calls = 0

        def llm_request(_messages, **_kwargs):
            nonlocal calls
            calls += 1
            if calls > 5:
                raise KeyboardInterrupt
            return {"beats": ["Only one returned beat."]}

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ), mock.patch(
            "minimax.load_story_arc",
            return_value=macro_arc,
        ), self.assertRaises(KeyboardInterrupt):
            minimax.generate_beats_from_story(
                "A two-part story.",
                2,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
                content_attempts=1,
            )

        self.assertEqual(calls, 6)

    def test_generation_requests_no_more_than_twenty_beats_per_batch(self):
        requested_ranges = []

        def llm_request(messages, **kwargs):
            del messages
            metadata = kwargs["history_metadata"]
            batch_start = metadata["batch_start"]
            batch_end = metadata["batch_end"]
            requested_ranges.append((batch_start, batch_end))
            return {
                "beats": [
                    f"Visible event {number} advances the story."
                    for number in range(batch_start, batch_end + 1)
                ]
            }

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "builtins.print"
        ):
            beats = minimax.generate_beats_from_story(
                "A long journey unfolds.",
                45,
                path=os.path.join(directory, "beats.txt"),
                llm_request=llm_request,
            )

        self.assertEqual(requested_ranges, [(1, 20), (21, 40), (41, 45)])
        self.assertEqual(len(beats), 45)

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
        self.assertEqual(
            saved,
            "\n".join(
                f"{number}. {beat}"
                for number, beat in enumerate(generated, start=1)
            ) + "\n",
        )
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
            f"{number}. {beat} {directive}"
            for number, beat in enumerate(generated, start=1)
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
        self.assertEqual(
            generated.call_args.kwargs["story_arc_path"],
            minimax.STORY_ARC_FILE,
        )
        self.assertEqual(
            generated.call_args.kwargs["story_arc_source"],
            "beat_instructions: [Make the middle beat surprising.]\n"
            "A three-part story.",
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
