import unittest

import minimax


class BlockerVerificationTests(unittest.TestCase):
    BEATS = [
        "The children move toward the basement.",
        "The basement door is locked from outside.",
        "The protagonist stands outside the locked room.",
        "The protagonist is suddenly inside the locked room.",
        "The pistol rests holstered at the protagonist's hip.",
        "The protagonist is suddenly holding the pistol.",
        "The enemy loses an arm but remains alive.",
        "The scene later declares every enemy dead.",
    ]

    def test_verifier_prompt_forbids_offscreen_explanations(self):
        issue = {
            "beat_start": 3,
            "beat_end": 4,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "The next beat must be physically reachable.",
            "problem": "The subject crosses the locked room boundary without an entry.",
        }
        system, user = minimax.build_candidate_blocker_verification_messages(
            issue, 1, self.BEATS, story="A locked room.", macro_arc={}
        )
        self.assertIn("Do not invent off-screen", system["content"])
        self.assertIn("could have", system["content"])
        self.assertIn("missing transition remains missing", system["content"])
        self.assertIn('"decision": "BLOCK"', user["content"])

    def test_verifier_accepts_compact_decision_and_reason(self):
        parsed = minimax.parse_candidate_blocker_verification(
            {"decision": "BLOCK", "reason": "Beat 4 starts inside without an entry."},
            1,
        )
        self.assertEqual(parsed["decision"], "BLOCK")

    def test_legacy_issue_id_response_remains_parseable(self):
        parsed = minimax.parse_candidate_blocker_verification(
            {
                "issue_id": 1,
                "decision": "DISCARD",
                "reason": "The proposed effect was never established.",
            },
            1,
        )
        self.assertEqual(parsed["decision"], "DISCARD")

    def test_deterministic_factual_types_bypass(self):
        for issue_type in (
            "phase_required_end_state",
            "missing_prerequisite",
            "required_source_event_missing",
        ):
            self.assertTrue(
                minimax.issue_can_bypass_verification(
                    {
                        "beat_start": 1,
                        "beat_end": 5,
                        "type": issue_type,
                        "source_requirement": "The source explicitly requires the family to be safe.",
                        "problem": "The required state is absent by the reported beat.",
                    }
                )
            )

    def test_ambiguous_types_still_use_verification(self):
        for issue_type in (
            minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "persistent_state_conflict",
            "unsupported_major_event",
            "repeated_process_incomplete",
        ):
            self.assertFalse(
                minimax.issue_can_bypass_verification(
                    {
                        "beat_start": 2,
                        "beat_end": 3,
                        "type": issue_type,
                        "source_requirement": "A concrete supplied requirement.",
                        "problem": "The supplied beats conflict.",
                    }
                )
            )

    def test_vague_deterministic_candidate_does_not_bypass(self):
        self.assertFalse(
            minimax.issue_can_bypass_verification(
                {
                    "beat_start": 1,
                    "beat_end": 2,
                    "type": "missing_prerequisite",
                    "source_requirement": "unknown",
                    "problem": "Something is wrong.",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
