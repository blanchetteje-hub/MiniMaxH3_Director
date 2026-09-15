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

    def test_batch_response_format_declares_issue_id_results(self):
        response_format = minimax.build_candidate_blocker_verification_response_format(
            [1, 2, 3, 4]
        )
        schema = response_format["json_schema"]["schema"]
        self.assertEqual(schema["required"], ["results"])
        self.assertEqual(schema["properties"]["results"]["type"], "array")
        item_schema = schema["properties"]["results"]["items"]
        self.assertEqual(
            item_schema["required"], ["issue_id", "decision", "reason"]
        )
        self.assertEqual(
            item_schema["properties"]["decision"]["enum"], ["BLOCK", "DISCARD"]
        )

    def test_batch_parser_accepts_one_result_for_each_requested_id(self):
        parsed = minimax.parse_candidate_blocker_verification_batch(
            {
                "results": [
                    {"issue_id": 1, "decision": "BLOCK", "reason": "Directly shown."},
                    {"issue_id": 2, "decision": "DISCARD", "reason": "Unsupported."},
                ]
            },
            [1, 2],
        )
        self.assertEqual(
            [result["issue_id"] for result in parsed["results"]], [1, 2]
        )

    def test_batch_parser_rejects_missing_duplicate_and_unknown_ids(self):
        cases = (
            [
                {"issue_id": 1, "decision": "BLOCK", "reason": "Directly shown."},
            ],
            [
                {"issue_id": 1, "decision": "BLOCK", "reason": "First."},
                {"issue_id": 1, "decision": "DISCARD", "reason": "Duplicate."},
                {"issue_id": 2, "decision": "BLOCK", "reason": "Directly shown."},
            ],
            [
                {"issue_id": 1, "decision": "BLOCK", "reason": "Directly shown."},
                {"issue_id": 3, "decision": "DISCARD", "reason": "Unknown."},
            ],
        )
        for results in cases:
            with self.subTest(results=results), self.assertRaises(ValueError):
                minimax.parse_candidate_blocker_verification_batch(
                    {"results": results}, [1, 2]
                )

    def test_batch_parser_rejects_invalid_decisions(self):
        with self.assertRaises(ValueError):
            minimax.parse_candidate_blocker_verification_batch(
                {
                    "results": [
                        {"issue_id": 1, "decision": "MAYBE", "reason": "Unclear."},
                    ]
                },
                [1],
            )

    def test_batch_prompt_contains_only_relevant_beat_context(self):
        beats = [
            "UNRELATED beat one.",
            "Relevant locked-room transition.",
            "Relevant door state.",
            "UNRELATED beat four.",
            "UNRELATED beat five.",
            "UNRELATED beat six.",
            "UNRELATED beat seven.",
            "Relevant source-required ending.",
        ]
        candidates = [
            {
                "issue_id": 1,
                "beat_start": 2,
                "beat_end": 3,
                "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
                "source_requirement": "The next beat must be reachable.",
                "problem": "Beat 3 starts after an unshown transition.",
                "end_state_before": "The subject is outside.",
                "opening_state_after": "The subject is inside.",
                "missing_transition": "No entry is shown.",
            },
            {
                "issue_id": 2,
                "beat_start": 8,
                "beat_end": 8,
                "type": "phase_required_end_state",
                "source_requirement": "The phase must end with the family safe.",
                "problem": "The required ending state is absent.",
            },
        ]
        messages = minimax.build_candidate_blocker_verification_batch_messages(
            candidates,
            beats,
            story="UNRELATED source material that is not needed for either issue.",
            macro_arc={
                "phases": [
                    {"phase_number": 1, "beat_start": 1, "beat_end": 4},
                    {"phase_number": 2, "beat_start": 5, "beat_end": 8},
                ]
            },
        )
        user_content = messages[1]["content"]
        self.assertIn("Relevant locked-room transition.", user_content)
        self.assertIn("Relevant door state.", user_content)
        self.assertIn("Relevant source-required ending.", user_content)
        self.assertIn("END_STATE_BEFORE", user_content)
        self.assertIn("OPENING_STATE_AFTER", user_content)
        self.assertNotIn("UNRELATED beat one.", user_content)
        self.assertNotIn("UNRELATED beat four.", user_content)
        self.assertNotIn("UNRELATED beat seven.", user_content)
        self.assertNotIn("UNRELATED source material", user_content)

    def test_candidates_fit_one_batch_when_within_token_budget(self):
        candidates = [
            {
                "issue_id": index,
                "beat_start": index,
                "beat_end": index,
                "type": "persistent_state_conflict",
                "source_requirement": f"Requirement {index}.",
                "problem": f"Problem {index}.",
            }
            for index in range(1, 6)
        ]
        batches = minimax.build_candidate_blocker_verification_batches(
            candidates,
            beats=self.BEATS,
            token_budget=100000,
        )
        self.assertEqual([len(batch) for batch in batches], [5])

    def test_candidates_split_only_when_token_budget_requires_it(self):
        candidates = [
            {
                "issue_id": index,
                "beat_start": index,
                "beat_end": index,
                "type": "persistent_state_conflict",
                "source_requirement": f"Requirement {index}.",
                "problem": f"Problem {index}.",
            }
            for index in range(1, 6)
        ]
        batches = minimax.build_candidate_blocker_verification_batches(
            candidates,
            beats=self.BEATS,
            token_budget=1,
        )
        self.assertEqual(len(batches), 5)

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

    def test_semantic_issue_types_never_bypass_verification_by_type_alone(self):
        for issue_type in (
            "phase_required_end_state",
            "missing_prerequisite",
            "required_source_event_missing",
        ):
            with self.subTest(issue_type=issue_type):
                self.assertFalse(
                    minimax.issue_can_bypass_verification(
                        {
                            "beat_start": 1,
                            "beat_end": 5,
                            "type": issue_type,
                            "source_requirement": (
                                "The source explicitly requires the family to be safe."
                            ),
                            "problem": "The required state is absent by the reported beat.",
                        }
                    )
                )

    def test_python_proven_structural_facts_can_bypass_verification(self):
        structural_candidates = (
            {
                "type": "invalid_beat_range",
                "beat_start": 0,
                "beat_end": 5,
            },
            {
                "type": "nonexistent_phase",
                "phase_number": 9,
                "known_phase_numbers": [1, 2],
            },
            {
                "type": "duplicate_beat_id",
                "beat_ids": [3, 3],
            },
            {
                "type": "required_count_mismatch",
                "expected_count": 4,
                "actual_count": 3,
            },
            {
                "type": "malformed_structure",
                "structural_proof": "parser rejected the required object shape",
            },
        )
        for issue in structural_candidates:
            with self.subTest(issue_type=issue["type"]):
                self.assertTrue(minimax.issue_can_bypass_verification(issue))

    def test_semantic_issue_does_not_bypass_even_with_concrete_wording(self):
        self.assertFalse(
            minimax.issue_can_bypass_verification(
                {
                    "beat_start": 2,
                    "beat_end": 2,
                    "type": "phase_required_end_state",
                    "source_requirement": "Phase 2 must end with the door locked.",
                    "problem": "Beat 2 does not state that the door is locked.",
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
