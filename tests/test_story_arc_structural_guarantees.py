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

    def test_majority_evidence_is_counted_deterministically(self):
        invalid = {
            "valid": True,
            "issues": [],
            "majority_checks": [{
                "source_requirement": "The majority of the film is Amy killing zombies.",
                "matching_beats": [4, 5, 6, 7],
            }],
        }
        parsed = minimax.parse_macro_arc_validation_result(
            invalid,
            total_segments=8,
            require_majority_checks=True,
        )
        self.assertFalse(parsed["valid"])
        self.assertIn("4/8 beats belong to the emphasized sequence", parsed["issues"][0])

        valid = copy.deepcopy(invalid)
        valid["majority_checks"][0]["matching_beats"] = [3, 4, 5, 6, 7]
        parsed = minimax.parse_macro_arc_validation_result(
            valid,
            total_segments=8,
            require_majority_checks=True,
        )
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["issues"], [])

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
            "matching_beats must contain ONLY global beat numbers that materially "
            "belong to the broad emphasized narrative sequence",
            normalized,
        )

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

    def test_rejects_missing_immediate_dependency_but_accepts_extra_dependency(self):
        invalid = copy.deepcopy(self.events)
        invalid[2]["depends_on"] = ["E1"]
        with self.assertRaisesRegex(ValueError, "immediately preceding required event E2"):
            minimax.parse_beat_arc_plan(make_arc([(1, 3, invalid)]), 3)


if __name__ == "__main__":
    unittest.main()
