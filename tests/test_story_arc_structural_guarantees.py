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

    def test_arc_validator_requires_explicit_source_timeline_coverage(self):
        story = (
            "Amy is at home on a normal day, cooking breakfast for her kids. "
            "Suddenly, a zombie breaks the kitchen door window."
        )
        arc = make_arc([
            (
                1,
                2,
                [
                    {
                        "id": "E1",
                        "event": "A zombie breaks the kitchen door window.",
                        "beat_number": 1,
                    },
                    {
                        "id": "E2",
                        "event": "Amy reacts to the zombie.",
                        "beat_number": 2,
                        "depends_on": ["E1"],
                    },
                ],
            ),
        ])

        messages = minimax.build_macro_arc_validation_messages(story, arc)
        prompt = "\n".join(message["content"] for message in messages)
        normalized = " ".join(prompt.split())

        self.assertIn(
            "Every explicit visible action or visible state that establishes "
            "a distinct point in the source timeline",
            normalized,
        )
        self.assertIn(
            "Do not dismiss an explicit source action merely because it is calm, "
            "introductory, mundane, or outside the main conflict.",
            normalized,
        )
        self.assertIn(
            "only AFTER all explicit source timeline actions/states are represented",
            normalized,
        )
        self.assertIn(
            "One required_event may cover multiple adjacent, causally continuous "
            "source actions",
            normalized,
        )
        self.assertIn(
            "SOURCE COVERAGE IS THE FIRST SEMANTIC CHECK",
            normalized,
        )
        self.assertLess(
            normalized.index("SOURCE COVERAGE IS THE FIRST SEMANTIC CHECK"),
            normalized.index("SOURCE EMPHASIS IS MANDATORY"),
        )

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

        self.assertIn(
            "set_condition requires the event/source to actually establish that condition",
            create_prompt,
        )
        self.assertIn(
            "Cooking or serving food does not establish hunger",
            create_prompt,
        )
        self.assertIn(
            "Reject unsupported optional state effects as well as missing required ones",
            validate_prompt,
        )
        self.assertIn(
            "Cooking or serving food does not establish hunger",
            validate_prompt,
        )

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

    def test_arc_validator_requests_majority_evidence_from_required_events(self):
        story = (
            "The majority of the film is Amy killing zombies. "
            "Amy kills the last zombie and lets her kids out."
        )
        arc = make_arc([(1, 3, self.events)])
        messages = minimax.build_macro_arc_validation_messages(story, arc)
        normalized = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn(
            "majority_checks is semantic evidence for deterministic counting",
            normalized,
        )
        self.assertIn(
            "matching_phases must contain ONLY macro phase numbers whose ENTIRE "
            "beat_start..beat_end span may safely be counted",
            normalized,
        )
        self.assertIn(
            "that mixed phase is NOT safe to count in full",
            normalized,
        )
        self.assertIn(
            "Python will expand each returned matching phase to its Python-owned "
            "beat_start..beat_end span",
            normalized,
        )

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
        create_messages = minimax.build_beat_arc_plan_messages(story, 8)
        create_prompt = " ".join(
            "\n".join(message["content"] for message in create_messages).split()
        )
        self.assertIn(
            "strict majority requires at least 5 beats allocated to the broad "
            "source-emphasized narrative sequence",
            create_prompt,
        )
        self.assertIn(
            "At most 3 beats may sit outside the emphasized sequence",
            create_prompt,
        )
        self.assertIn(
            "do NOT each need to literally repeat the emphasized verb",
            create_prompt,
        )
        self.assertIn(
            "Standalone preparation before the emphasized conflict/process begins "
            "does NOT count toward the majority sequence",
            create_prompt,
        )
        self.assertIn(
            "terminal result and immediate resolution in the SAME final sequence beat",
            create_prompt,
        )

        arc = make_arc([(1, 3, self.events)])
        repair_messages = minimax.build_macro_arc_repair_messages(
            story,
            arc,
            ["Majority is under-allocated."],
            8,
        )
        repair_prompt = " ".join(
            "\n".join(message["content"] for message in repair_messages).split()
        )
        self.assertIn(
            "majority requires at least 5 beats allocated to the broad emphasized "
            "narrative sequence",
            repair_prompt,
        )
        self.assertIn(
            "leaving at most 3 beats outside that sequence",
            repair_prompt,
        )

    def test_arc_planner_prefers_clip_scale_handoffs_when_budget_allows(self):
        messages = minimax.build_beat_arc_plan_messages(
            "Amy runs to the safe room, gets the kids inside, locks the door, "
            "then retrieves and equips her weapons.",
            3,
        )
        normalized = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn(
            "split a long adjacent source action chain across consecutive beat jobs",
            normalized,
        )
        self.assertIn(
            "not automatically one whole source sentence",
            normalized,
        )
        self.assertIn(
            "Choose boundaries for executable clip-sized story progression",
            normalized,
        )

    def test_arc_planner_allows_coherent_setpieces_inside_authorized_process(self):
        story = (
            "Amy fights zombies in her house. The majority of the film is Amy "
            "killing zombies as they attack her. Amy kills the last zombie."
        )
        messages = minimax.build_beat_arc_plan_messages(story, 8)
        normalized = " ".join(
            "\n".join(message["content"] for message in messages).split()
        )
        self.assertIn(
            "PLAN A COHERENT ESCALATION inside that authorized process",
            normalized,
        )
        self.assertIn("weapon running empty", normalized)
        self.assertIn("enemy surviving one beat", normalized)
        self.assertIn("temporary obstacle, contamination", normalized)
        self.assertIn(
            "do not make every invented complication self-contained",
            normalized,
        )
        self.assertIn(
            "remains unresolved at the end of one beat and is continued/resolved "
            "in the next",
            normalized,
        )

        validator = minimax.build_macro_arc_validation_messages(
            story,
            make_arc([(1, 3, self.events)]),
        )
        validation_prompt = " ".join(
            "\n".join(message["content"] for message in validator).split()
        )
        self.assertIn(
            "do NOT reject local setpiece developments merely because the source "
            "did not dictate their exact choreography",
            validation_prompt,
        )

    def test_arc_prompts_preserve_baseline_to_inciting_contrast(self):
        story = (
            "Amy is at home on a normal day cooking breakfast for her kids. "
            "Suddenly, a zombie breaks the kitchen door window."
        )
        arc = make_arc([
            (
                1,
                2,
                [
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
                ],
            ),
        ])

        plan_messages = minimax.build_beat_arc_plan_messages(story, 2)
        validation_messages = minimax.build_macro_arc_validation_messages(story, arc)
        plan_prompt = " ".join(
            "\n".join(message["content"] for message in plan_messages).split()
        )
        validation_prompt = " ".join(
            "\n".join(message["content"] for message in validation_messages).split()
        )

        self.assertIn("PRESERVE EXPLICIT CONTRAST BOUNDARIES", plan_prompt)
        self.assertIn(
            "ordinary/baseline activity and then marks a sudden disruptive or inciting change",
            plan_prompt,
        )
        self.assertIn("PRESERVE EXPLICIT CONTRAST BOUNDARIES", validation_prompt)
        self.assertIn(
            "ordinary baseline activity and then explicitly introduces a sudden disruptive/inciting change",
            validation_prompt,
        )

    def test_rejects_missing_immediate_dependency_but_accepts_extra_dependency(self):
        invalid = copy.deepcopy(self.events)
        invalid[2]["depends_on"] = ["E1"]
        with self.assertRaisesRegex(ValueError, "immediately preceding required event E2"):
            minimax.parse_beat_arc_plan(make_arc([(1, 3, invalid)]), 3)


if __name__ == "__main__":
    unittest.main()
