import unittest

import minimax


class BeatPlanAuditorTests(unittest.TestCase):
    BEATS = [
        "4. A man remains outside the locked garage.",
        "5. The family runs upstairs.",
        "6. The man stands inside the upstairs bedroom.",
    ]

    def audit_prompt(self, beats=None):
        messages = minimax.build_beat_plan_audit_messages(
            "A man is outside a garage.",
            len(beats or self.BEATS),
            beats or self.BEATS,
            {},
        )
        return messages[-1]["content"]

    def test_audit_requires_pairwise_end_and_start_state_reasoning(self):
        prompt = self.audit_prompt()

        self.assertIn("Audit every adjacent pair in numeric order, one pair at a time", prompt)
        self.assertIn("physical\nend state actually established by Beat N", prompt)
        self.assertIn("what physical state\nBeat N+1 assumes is already true", prompt)
        self.assertIn("unshown movement", prompt)
        self.assertIn("adjacent physical-transition failure", prompt)

    def test_impossible_location_jump_is_calibrated_as_later_beat_failure(self):
        prompt = self.audit_prompt()

        self.assertIn("outside a locked garage", prompt)
        self.assertIn("inside an upstairs bedroom", prompt)
        self.assertIn("flag Beat 5", prompt)
        self.assertIn("report the smallest later-beat range", prompt)

    def test_spatial_reversal_and_valid_movement_cases_are_distinguished(self):
        prompt = self.audit_prompt()

        self.assertIn("behind a target", prompt)
        self.assertIn("passing or\n  overtaking", prompt)
        self.assertIn("continue through that doorway", prompt)
        self.assertIn("valid continuation", prompt)

    def test_irreversible_completed_transition_replay_is_blocking(self):
        prompt = self.audit_prompt([
            "1. The machine removes the subject's left arm.",
            "2. The subject remains without the left arm.",
            "3. The machine removes the subject's left arm again.",
        ])

        self.assertIn("repeat an irreversible transition", prompt)
        self.assertIn("restoration or replacement", prompt)

    def test_audit_parser_preserves_transition_failure_target(self):
        issue = {
            "beat_start": 6,
            "beat_end": 6,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "Beat 6 must be reachable from Beat 5",
            "problem": (
                "Beat 5 ends outside the garage, but Beat 6 assumes the man is "
                "inside the upstairs bedroom without showing entry or movement."
            ),
        }
        parsed = minimax.parse_beat_plan_audit({
            "valid": False,
            "macro_arc_consistent_with_source": True,
            "blocking_issues": [issue],
            "warnings": [],
        }, total_segments=6)

        self.assertEqual(parsed["blocking_issues"], [issue])
        self.assertEqual(parsed["blocking_issues"][0]["beat_start"], 6)

    def test_adjacent_pair_issue_is_localized_to_later_beat(self):
        issue = {
            "beat_start": 2,
            "beat_end": 3,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "Beat 3 must be reachable from Beat 2",
            "problem": "Beat 3 assumes an unshown move from the earlier location.",
        }

        normalized = minimax.normalize_beat_plan_repair_ranges(
            [issue],
            total_segments=3,
        )

        self.assertEqual(normalized["ranges"], [{"beat_start": 3, "beat_end": 3, "issues": [
            {
                **issue,
                "beat_start": 3,
                "beat_end": 3,
            }
        ]}])

    def test_repair_prompt_keeps_earlier_beat_immutable_and_targets_later_beat(self):
        issue = {
            "beat_start": 3,
            "beat_end": 3,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "The subject must move into the bedroom",
            "problem": "Beat 3 assumes the subject is in the bedroom without entry.",
        }
        prompt = minimax.build_beat_plan_repair_messages(
            "The subject moves into the bedroom.",
            3,
            [
                "1. The subject waits outside.",
                "2. The subject approaches the door.",
                "3. The subject is in the bedroom.",
            ],
            {},
            [issue],
            [{"beat_start": 3, "beat_end": 3}],
        )[-1]["content"]

        self.assertIn("Immutable beat before: Beat 2", prompt)
        self.assertIn("repair the later targeted beat", prompt)
        self.assertIn("showing the smallest authorized movement", prompt)
        self.assertIn("Do not\n  rewrite an earlier valid beat", prompt)


if __name__ == "__main__":
    unittest.main()
