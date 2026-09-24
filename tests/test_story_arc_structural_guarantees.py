import copy
import unittest

import minimax


def make_arc(events_by_phase):
    phases = []
    for phase_number, (beat_start, beat_end, events) in enumerate(
        events_by_phase, start=1
    ):
        phases.append({
            "phase_number": phase_number,
            "beat_start": beat_start,
            "beat_end": beat_end,
            "narrative_purpose": "Advance the story.",
            "broad_progression": "Advance the story.",
            "characters_introduced": ["Amy"],
            "location": "the house",
            "required_end_state": "The story reaches the requested outcome.",
            "required_events": events,
        })
    return {"phases": phases}


class StoryArcStructuralGuaranteeTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {"id": "E1", "event": "Amy acts.", "beat_number": 1},
            {
                "id": "E2",
                "event": "Amy continues.",
                "beat_number": 2,
                "depends_on": ["E1"],
            },
            {
                "id": "E3",
                "event": "Amy reaches the next room.",
                "beat_number": 3,
                "depends_on": ["E2", "E1"],
            },
        ]

    def test_accepts_one_event_per_beat_and_cross_phase_chain(self):
        arc = make_arc([
            (1, 2, self.events[:2]),
            (3, 3, self.events[2:]),
        ])
        parsed = minimax.parse_beat_arc_plan(arc, 3)
        self.assertEqual(
            parsed["phases"][1]["required_events"][0]["depends_on"],
            ["E2", "E1"],
        )

    def test_rejects_missing_beat_assignment(self):
        arc = make_arc([(1, 3, [self.events[0], self.events[2]])])
        with self.assertRaisesRegex(ValueError, "no required event for beat.*2"):
            minimax.parse_beat_arc_plan(arc, 3)

    def test_rejects_duplicate_beat_assignment(self):
        duplicate = copy.deepcopy(self.events[1])
        duplicate["id"] = "E4"
        duplicate["depends_on"] = ["E1"]
        arc = make_arc([(1, 3, [self.events[0], self.events[1], duplicate, self.events[2]])])
        with self.assertRaisesRegex(ValueError, "duplicate required-event assignments"):
            minimax.parse_beat_arc_plan(arc, 3)

    def test_flat_arc_parser_makes_phase_bookkeeping_python_owned(self):
        flat_events = [
            {**copy.deepcopy(event), "state_effects": []}
            for event in self.events
        ]
        parsed = minimax.parse_flat_arc_plan(
            {"events": flat_events},
            3,
        )
        self.assertEqual(len(parsed["phases"]), 3)
        self.assertEqual(
            [
                (phase["phase_number"], phase["beat_start"], phase["beat_end"])
                for phase in parsed["phases"]
            ],
            [(1, 1, 1), (2, 2, 2), (3, 3, 3)],
        )
        self.assertEqual(
            [
                phase["required_events"][0]["beat_number"]
                for phase in parsed["phases"]
            ],
            [1, 2, 3],
        )
        self.assertEqual(
            [
                phase["required_events"][0].get("depends_on")
                for phase in parsed["phases"]
            ],
            [None, ["E1"], ["E2"]],
        )

    def test_flat_arc_parser_rejects_duplicate_or_missing_beat_jobs(self):
        duplicate = [
            {**copy.deepcopy(event), "state_effects": []}
            for event in self.events
        ]
        duplicate[2]["beat_number"] = 2
        with self.assertRaisesRegex(
            ValueError,
            "duplicate required-event assignments",
        ):
            minimax.parse_flat_arc_plan({"events": duplicate}, 3)

    def test_fresh_flat_arc_requires_explicit_state_effect_arrays(self):
        missing = [
            {**copy.deepcopy(event), "state_effects": []}
            for event in self.events
        ]
        missing[1].pop("state_effects")
        with self.assertRaisesRegex(
            ValueError,
            "must include state_effects",
        ):
            minimax.parse_flat_arc_plan({"events": missing}, 3)

        schema = minimax.build_flat_arc_response_format(3)
        required = (
            schema["json_schema"]["schema"]["properties"]["events"]
            ["items"]["required"]
        )
        self.assertIn("state_effects", required)
        event_properties = (
            schema["json_schema"]["schema"]["properties"]["events"]
            ["items"]["properties"]
        )
        self.assertNotIn("depends_on", event_properties)

    def test_arc_create_and_repair_keep_phase_arithmetic_out_of_the_llm(self):
        story = "Amy cooks breakfast. Then Amy opens the door."
        arc = make_arc([(1, 3, self.events)])
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 3)
            ).split()
        )
        repair_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_repair_messages(
                    story,
                    arc,
                    ["The second source action is missing."],
                    3,
                )
            ).split()
        )
        self.assertIn("Do not create phases or phase ranges", create_prompt)
        self.assertIn("Python owns that deterministic bookkeeping", create_prompt)
        self.assertIn(
            "finite source activity is assigned wholly to one beat",
            create_prompt,
        )
        self.assertIn("natural visible endpoint", create_prompt)
        self.assertIn("Do not create phases or phase ranges", repair_prompt)
        self.assertIn(
            "finite source activity assigned wholly to one beat",
            repair_prompt,
        )
        self.assertIn("natural visible endpoint", repair_prompt)
        self.assertIn("Python owns the deterministic dependency chain", create_prompt)
        self.assertIn("Python assigns the deterministic dependency chain", repair_prompt)
        self.assertIn('"events":[', repair_prompt)
        schema = minimax.build_flat_arc_response_format(3)
        events_schema = schema["json_schema"]["schema"]["properties"]["events"]
        self.assertEqual(events_schema["minItems"], 3)
        self.assertEqual(events_schema["maxItems"], 3)
        event_schema = events_schema["items"]["properties"]["event"]
        self.assertIn("executable clip job", event_schema["description"])
        self.assertIn("natural visible endpoint", event_schema["description"])
        self.assertIn("extended/repeated process", event_schema["description"])

    def test_arc_create_expands_explicit_majority_process_to_numeric_budget(self):
        story = (
            "Amy cooks breakfast. The majority of the film is Amy fighting zombies. "
            "Amy defeats the last zombie and lets her kids out."
        )
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 8)
            ).split()
        )
        self.assertIn("allocate that process to the required numeric majority of beats", create_prompt)
        self.assertIn("do not compress the whole process into one or two summary events", create_prompt)
        self.assertIn("distinct coherent source-authorized moments", create_prompt)
        self.assertIn("never add a new major plot, character, location, or outcome", create_prompt)

    def test_arc_validator_requires_explicit_source_timeline_coverage(self):
        story = (
            "Amy is at home on a normal day, cooking breakfast for her kids. "
            "Suddenly, a zombie breaks the kitchen door window."
        )
        arc = make_arc([(1, 2, [
            {"id": "E1", "event": "A zombie breaks the kitchen door window.", "beat_number": 1},
            {"id": "E2", "event": "Amy reacts to the zombie.", "beat_number": 2, "depends_on": ["E1"]},
        ])])
        normalized = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(story, arc)
            ).split()
        )
        self.assertIn("SOURCE COVERAGE FIRST", normalized)
        self.assertIn("every explicit visible source action/state", normalized)
        self.assertIn("Calm/mundane setup still counts", normalized)
        self.assertIn("do not join distant story stages or drop a source action", normalized)

    def test_arc_validator_uses_flat_events_and_allows_source_authorized_process(self):
        story = (
            "Amy protects her kids. The majority of the film is Amy killing "
            "zombies as they attack her."
        )
        arc = make_arc([(1, 3, self.events)])
        messages = minimax.build_macro_arc_validation_messages(
            story,
            arc,
            subject_information=(
                "<Subject 1> is Amy, an adult woman.\n"
                "<Subject 2> is Will, a child.\n"
                "<Subject 3> is Amber, a child."
            ),
        )
        normalized = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn('"events":[', normalized)
        self.assertNotIn('"phases":[', normalized)
        self.assertIn("<Subject 1> = Amy", normalized)
        self.assertIn("<Subject 2> = Will", normalized)
        self.assertIn("<Subject 3> = Amber", normalized)
        self.assertIn("extended or repeated process", normalized)
        self.assertIn("multiple beats may continue", normalized)
        self.assertIn("phase bookkeeping is intentionally not part", normalized)

    def test_arc_validator_is_narrow_source_fidelity_check(self):
        story = (
            "Amy cooks breakfast for her kids. She retrieves a pistol and katana "
            "and equips the weapons."
        )
        arc = make_arc([(1, 3, self.events)])
        messages = minimax.build_macro_arc_validation_messages(story, arc)
        system_prompt = " ".join(messages[0]["content"].split())
        user_prompt = " ".join(messages[1]["content"].split())

        self.assertIn(
            "covers the explicit source actions/states without source-order contradiction",
            system_prompt,
        )
        self.assertIn(
            "Do not critique pacing, bundling, detail level, style, or beat allocation",
            system_prompt,
        )
        self.assertIn(
            "Do not require clothing, appearance, names, or other descriptive facts "
            "that the source does not provide",
            user_prompt,
        )
        self.assertIn(
            "Adjacent sequential source actions may share one required_event",
            user_prompt,
        )
        self.assertIn(
            "not an error when their source order is preserved inside the event",
            user_prompt,
        )
        self.assertNotIn(
            "A defined human Subject must have concrete clothing when first shown",
            user_prompt,
        )

    def test_arc_prompts_keep_clothing_out_of_set_condition(self):
        story = "Amy wears a black tank top and cooks breakfast."
        arc = make_arc([(1, 3, self.events)])

        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 3)
            ).split()
        )
        validate_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(story, arc)
            ).split()
        )
        repair_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_repair_messages(
                    story,
                    arc,
                    ["Clothing used the wrong state operation."],
                    3,
                )
            ).split()
        )

        for prompt in (create_prompt, validate_prompt, repair_prompt):
            self.assertIn("Clothing must use set_clothing", prompt)
            self.assertIn("set_condition", prompt)
            self.assertIn("set_clothing.entity is the wearer", prompt)
            self.assertIn("Never put the garment itself in set_clothing.entity", prompt)

    def test_arc_prompts_reject_inferred_internal_state_effects(self):
        story = "Amy cooks breakfast for Will and Amber."
        arc = make_arc([(1, 3, self.events)])
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 3)
            ).split()
        )
        validate_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(story, arc)
            ).split()
        )
        for prompt in (create_prompt, validate_prompt):
            self.assertIn("state_effects", prompt)
            self.assertIn("persistent facts directly established", prompt)
            self.assertIn("set_condition", prompt)
            self.assertRegex(prompt, r"temporary|inferred")
            self.assertIn("set_clothing", prompt)
        self.assertIn("CHECK PERSISTENT STATE COVERAGE", validate_prompt)
        self.assertIn("persistent change or result", validate_prompt)
        self.assertIn("held/equipped objects", validate_prompt)
        self.assertIn("terminal threats", validate_prompt)
        self.assertIn("Temporary actions", validate_prompt)

    def test_majority_evidence_is_counted_deterministically(self):
        invalid_arc = {
            "phases": [
                {"phase_number": 1, "beat_start": 1, "beat_end": 2},
                {"phase_number": 2, "beat_start": 3, "beat_end": 4},
                {"phase_number": 3, "beat_start": 5, "beat_end": 8},
            ]
        }
        evidence = {
            "valid": True,
            "issues": [],
            "majority_checks": [{
                "source_requirement": "The majority of the film is Amy killing zombies.",
                "matching_phases": [3],
            }],
        }
        parsed = minimax.parse_macro_arc_validation_result(
            evidence,
            total_segments=8,
            require_majority_checks=True,
            macro_arc=invalid_arc,
        )
        self.assertFalse(parsed["valid"])
        self.assertIn("4/8 beats; more than half is required", parsed["issues"][0])
        self.assertEqual(parsed["majority_checks"][0]["matching_beats"], [5, 6, 7, 8])

        valid_arc = {
            "phases": [
                {"phase_number": 1, "beat_start": 1, "beat_end": 1},
                {"phase_number": 2, "beat_start": 2, "beat_end": 3},
                {"phase_number": 3, "beat_start": 4, "beat_end": 8},
            ]
        }
        parsed = minimax.parse_macro_arc_validation_result(
            evidence,
            total_segments=8,
            require_majority_checks=True,
            macro_arc=valid_arc,
        )
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["issues"], [])
        self.assertEqual(parsed["majority_checks"][0]["matching_beats"], [4, 5, 6, 7, 8])

    def test_majority_source_requires_validator_evidence(self):
        with self.assertRaisesRegex(ValueError, "returned no majority_checks evidence"):
            minimax.parse_macro_arc_validation_result(
                {"valid": True, "issues": [], "majority_checks": []},
                total_segments=8,
                require_majority_checks=True,
            )

    def test_broad_arc_validator_delegates_majority_to_focused_check(self):
        story = (
            "The majority of the film is Amy killing zombies. "
            "Amy kills the last zombie and lets her kids out."
        )
        arc = make_arc([(1, 3, self.events)])
        normalized = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(story, arc)
            ).split()
        )
        self.assertIn("Do NOT judge majority/relative-duration allocation", normalized)
        self.assertIn("separate focused check inside ARC VALIDATE", normalized)
        self.assertIn("Return majority_checks as [] here", normalized)
        self.assertNotIn("matching_phases contains only", normalized)

    def test_focused_majority_evidence_classifies_exact_beats(self):
        story = (
            "Amy cooks breakfast, gets her kids safe, and equips weapons. "
            "The majority of the film is Amy killing zombies as they attack her. "
            "Amy kills the last zombie and lets her kids out."
        )
        arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "required_events": [
                        {"id": "E1", "event": "Amy cooks breakfast.", "beat_number": 1},
                        {
                            "id": "E2",
                            "event": "Amy gets her kids to the basement.",
                            "beat_number": 2,
                        },
                    ],
                },
                {
                    "phase_number": 2,
                    "beat_start": 3,
                    "beat_end": 5,
                    "required_events": [
                        {
                            "id": "E3",
                            "event": "Amy locks the basement door.",
                            "beat_number": 3,
                        },
                        {
                            "id": "E4",
                            "event": "Amy retrieves her weapons.",
                            "beat_number": 4,
                        },
                        {
                            "id": "E5",
                            "event": "Amy equips her weapons.",
                            "beat_number": 5,
                        },
                    ],
                },
                {
                    "phase_number": 3,
                    "beat_start": 6,
                    "beat_end": 8,
                    "required_events": [
                        {
                            "id": "E6",
                            "event": "Amy fights and kills several zombies.",
                            "beat_number": 6,
                        },
                        {
                            "id": "E7",
                            "event": "Amy survives another zombie wave.",
                            "beat_number": 7,
                        },
                        {
                            "id": "E8",
                            "event": "Amy kills the last zombie and lets her kids out.",
                            "beat_number": 8,
                        },
                    ],
                },
            ]
        }
        messages = minimax.build_macro_arc_majority_evidence_messages(story, arc)
        normalized = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn(
            "matching_beats may contain only beat numbers whose required event "
            "materially belongs",
            normalized,
        )
        self.assertIn(
            "Standalone setup, escape, retrieval, equipping, travel, or preparation "
            "BEFORE the emphasized process begins does NOT belong",
            normalized,
        )
        self.assertIn("5. Amy equips her weapons.", normalized)
        self.assertIn(
            "A beat containing a terminal emphasized action DOES belong",
            normalized,
        )

        parsed = minimax.parse_macro_arc_majority_evidence_result(
            {
                "majority_checks": [
                    {
                        "source_requirement": (
                            "The majority of the film is Amy killing zombies "
                            "as they attack her."
                        ),
                        "matching_beats": [6, 7, 8],
                    }
                ],
            },
            total_segments=8,
        )
        self.assertFalse(parsed["valid"])
        self.assertIn("3/8 beats; more than half is required", parsed["issues"][0])
        self.assertEqual(
            parsed["majority_checks"][0]["matching_beats"],
            [6, 7, 8],
        )

    def test_focused_majority_evidence_accepts_strict_majority(self):
        parsed = minimax.parse_macro_arc_majority_evidence_result(
            {
                "majority_checks": [
                    {
                        "source_requirement": (
                            "The majority of the film is Amy killing zombies."
                        ),
                        "matching_beats": [4, 5, 6, 7, 8],
                    }
                ],
            },
            total_segments=8,
        )
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["issues"], [])

    def test_majority_story_gets_exact_sequence_budget(self):
        story = "The majority of the film is Amy killing zombies."
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 8)
            ).split()
        )
        self.assertIn("strict majority of 8 beats means at least 5 beats", create_prompt)
        self.assertIn("at most 3 beats before/outside it", create_prompt)
        self.assertIn("Preparation before the sequence does not count", create_prompt)
        self.assertIn("must therefore begin no later than Beat 4", create_prompt)
        self.assertIn("first 3 beats by bundling adjacent source actions", create_prompt)
        self.assertIn(
            "combine the terminal action and resolution in the final global beat",
            create_prompt,
        )

        arc = make_arc([(1, 3, self.events)])
        repair_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_repair_messages(
                    story, arc, ["Majority is under-allocated."], 8
                )
            ).split()
        )
        self.assertIn("At least 5/8 beats", repair_prompt)
        self.assertIn("at most 3 beats", repair_prompt)
        self.assertIn("must begin no later than Beat 4", repair_prompt)
        self.assertIn("calm baseline", repair_prompt)
        self.assertIn("combine both in the final global beat", repair_prompt)

        non_majority = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_repair_messages(
                    story, arc, ["Amy's clothing was missing on first show"], 8
                )
            ).split()
        )
        self.assertIn("MAJORITY REPAIR BUDGET N/A", non_majority)

    def test_majority_tail_repair_localizes_only_resolution_tail(self):
        validation = {
            "valid": False,
            "issues": ["majority under-allocated"],
            "majority_checks": [{
                "source_requirement": "The majority is Amy fighting zombies.",
                "matching_beats": [4, 5, 6, 7],
            }],
        }
        spec = minimax._macro_arc_majority_tail_repair_spec(validation, 8)
        self.assertEqual(spec["tail_beats"], [7, 8])
        self.assertEqual(spec["matching_beats"], [4, 5, 6, 7])

        validation["majority_checks"][0]["matching_beats"] = [5, 6, 7]
        self.assertIsNone(
            minimax._macro_arc_majority_tail_repair_spec(validation, 8)
        )

    def test_majority_tail_repair_moves_existing_effect_without_losing_it(self):
        events = []
        for beat in range(1, 9):
            event = {
                "id": f"E{beat}",
                "event": f"Amy completes event {beat}.",
                "beat_number": beat,
            }
            if beat > 1:
                event["depends_on"] = [f"E{beat - 1}"]
            events.append(event)
        events[6]["event"] = "Amy kills the last zombie."
        events[6]["state_effects"] = [{
            "op": "set_threat_state",
            "entity": "zombie_horde",
            "value": "dead",
        }]
        events[7]["event"] = "Amy lets the kids out of the basement."
        arc = make_arc([(1, 8, events)])
        parsed_arc = minimax.parse_beat_arc_plan(arc, 8)
        expected_tail = [
            minimax._macro_arc_event_for_beat(parsed_arc, 7),
            minimax._macro_arc_event_for_beat(parsed_arc, 8),
        ]
        raw_repair = {
            "events": [
                {
                    "id": "E7",
                    "event": "Amy continues fighting the remaining zombies.",
                    "beat_number": 7,
                    "depends_on": ["E6"],
                },
                {
                    "id": "E8",
                    "event": (
                        "Amy kills the last zombie and immediately lets the kids "
                        "out of the basement."
                    ),
                    "beat_number": 8,
                    "depends_on": ["E7"],
                    "state_effects": [{
                        "op": "set_threat_state",
                        "entity": "zombie_horde",
                        "value": "dead",
                    }],
                },
            ]
        }
        replacements = minimax.parse_macro_arc_majority_tail_repair_result(
            raw_repair,
            expected_tail,
        )
        repaired = minimax.apply_macro_arc_event_replacements(
            parsed_arc,
            replacements,
            8,
        )
        beat7 = minimax._macro_arc_event_for_beat(repaired, 7)
        beat8 = minimax._macro_arc_event_for_beat(repaired, 8)
        self.assertNotIn("last zombie", beat7["event"])
        self.assertIn("last zombie", beat8["event"])
        self.assertEqual(
            beat8["state_effects"],
            [{
                "op": "set_threat_state",
                "entity": "zombie_horde",
                "value": "dead",
            }],
        )
        self.assertEqual(
            repaired["phases"][0]["required_end_state"],
            beat8["event"],
        )

    def test_majority_tail_repair_rejects_dropped_persistent_effect(self):
        events = [
            {
                "id": "E7",
                "event": "Amy kills the last zombie.",
                "beat_number": 7,
                "depends_on": ["E6"],
                "state_effects": [{
                    "op": "set_threat_state",
                    "entity": "zombie_horde",
                    "value": "dead",
                }],
            },
            {
                "id": "E8",
                "event": "Amy lets the kids out.",
                "beat_number": 8,
                "depends_on": ["E7"],
            },
        ]
        with self.assertRaisesRegex(ValueError, "conserve"):
            minimax.parse_macro_arc_majority_tail_repair_result(
                {
                    "events": [
                        {
                            "id": "E7",
                            "event": "Amy keeps fighting zombies.",
                            "beat_number": 7,
                            "depends_on": ["E6"],
                        },
                        {
                            "id": "E8",
                            "event": "Amy kills the last zombie and lets the kids out.",
                            "beat_number": 8,
                            "depends_on": ["E7"],
                        },
                    ]
                },
                events,
            )

    def test_arc_planner_prefers_clip_scale_handoffs_when_budget_allows(self):
        normalized = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(
                    "Amy runs to the safe room, gets the kids inside, locks the door, "
                    "then retrieves and equips her weapons.",
                    3,
                )
            ).split()
        )
        self.assertIn("one executable clip job", normalized)
        self.assertIn("split long source chains at natural handoffs", normalized)
        self.assertIn("bundle only adjacent actions when necessary", normalized)

    def test_arc_planner_allows_coherent_setpieces_inside_authorized_process(self):
        story = (
            "Amy fights zombies in her house. The majority of the film is Amy "
            "killing zombies as they attack her. Amy kills the last zombie."
        )
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 8)
            ).split()
        )
        self.assertIn("distinct coherent source-authorized moments", create_prompt)
        self.assertIn("never add a new major plot", create_prompt)

        validate_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(
                    story, make_arc([(1, 3, self.events)])
                )
            ).split()
        )
        self.assertIn("unsupported major plot events", validate_prompt)

    def test_arc_prompts_preserve_baseline_to_inciting_contrast(self):
        story = (
            "Amy is at home on a normal day cooking breakfast for her kids. "
            "Suddenly, a zombie breaks the kitchen door window."
        )
        arc = make_arc([(1, 2, [
            {
                "id": "E1",
                "event": "Amy cooks breakfast and a zombie breaks the kitchen door window.",
                "beat_number": 1,
            },
            {
                "id": "E2",
                "event": "Amy reacts to the zombie.",
                "beat_number": 2,
                "depends_on": ["E1"],
            },
        ])])
        plan_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages(story, 2)
            ).split()
        )
        validation_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_macro_arc_validation_messages(story, arc)
            ).split()
        )
        self.assertIn("calm/ordinary baseline", plan_prompt)
        self.assertIn("sudden inciting threat or change", plan_prompt)
        self.assertIn("ordinary baseline", validation_prompt)
        self.assertIn("sudden inciting threat/change", validation_prompt)

    def test_arc_prompts_fit_current_local_input_budget(self):
        story = (
            "Amy cooks breakfast. A zombie attacks. Amy protects her kids. "
            "The majority of the film is Amy fighting zombies. Amy wins."
        )
        arc = make_arc([(1, 3, self.events)])
        for messages in (
            minimax.build_beat_arc_plan_messages(story, 8),
            minimax.build_macro_arc_validation_messages(story, arc),
            minimax.build_macro_arc_repair_messages(
                story, arc, ["Majority is under-allocated."], 8
            ),
        ):
            self.assertLess(
                minimax.estimate_message_tokens(messages),
                minimax.LLM_INPUT_TOKEN_BUDGET,
            )

    def test_legacy_required_end_state_is_not_authoritative(self):
        arc = make_arc([(1, 3, self.events)])
        arc["phases"][0]["required_end_state"] = "Unsupported later event happens."
        parsed = minimax.parse_beat_arc_plan(arc, 3)
        self.assertEqual(
            parsed["phases"][0]["required_end_state"],
            self.events[-1]["event"],
        )
        create_prompt = " ".join(
            "\n".join(
                message["content"]
                for message in minimax.build_beat_arc_plan_messages("Amy acts.", 1)
            ).split()
        )
        self.assertIn("Do not return required_end_state", create_prompt)

    def test_rejects_missing_immediate_dependency_but_accepts_extra_dependency(self):
        invalid = copy.deepcopy(self.events)
        invalid[2]["depends_on"] = ["E1"]
        with self.assertRaisesRegex(ValueError, "immediately preceding required event E2"):
            minimax.parse_beat_arc_plan(make_arc([(1, 3, invalid)]), 3)


if __name__ == "__main__":
    unittest.main()
