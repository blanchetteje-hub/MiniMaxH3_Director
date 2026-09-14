import unittest

import minimax


class BeatPlanAuditorTests(unittest.TestCase):
    BEATS = [
        "The protagonist waits outside the locked basement.",
        "The protagonist is suddenly in the living room.",
        "The protagonist walks through the open doorway into the hall.",
        "The protagonist retrieves the pistol from the table.",
        "The protagonist raises the pistol.",
        "The pursuer remains behind the protagonist.",
        "The pursuer is suddenly ahead of the protagonist.",
    ]

    def test_adjacent_windows_overlap_once_and_cover_every_pair(self):
        windows = minimax.build_adjacent_beat_windows(30)
        self.assertEqual(windows, [(1, 7), (7, 13), (13, 19), (19, 25), (25, 30)])
        pairs = []
        for start, end in windows:
            pairs.extend(range(start, end))
        self.assertEqual(pairs, list(range(1, 30)))

    def test_adjacent_prompt_is_narrow_and_excludes_global_context(self):
        messages = minimax.build_adjacent_continuity_audit_messages(self.BEATS, 1, 7)
        system, user = messages[0]["content"], messages[1]["content"]
        self.assertIn("adjacent-beat continuity auditor", system)
        self.assertIn("location", user)
        self.assertIn("held or possessed objects", user)
        self.assertNotIn("SOURCE STORY", user)
        self.assertNotIn("MACRO STORY ARC", user)
        self.assertNotIn("subject definitions", user)

    def test_adjacent_failures_target_the_later_beat(self):
        parsed = minimax.parse_adjacent_continuity_audit({
            "valid": False,
            "issues": [{
                "beat_start": 1, "beat_end": 2,
                "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
                "problem": "Beat 2 assumes an unshown move from the basement.",
            }],
        }, 1, 7)
        self.assertEqual(parsed["blocking_issues"][0]["beat_start"], 2)
        self.assertEqual(parsed["blocking_issues"][0]["beat_end"], 2)

    def test_adjacent_valid_transition_cases_are_accepted(self):
        parsed = minimax.parse_adjacent_continuity_audit({"valid": True, "issues": []}, 1, 7)
        self.assertEqual(parsed["blocking_issues"], [])
        prompt = minimax.build_adjacent_continuity_audit_messages([
            "The subject keeps walking toward the doorway.",
            "The subject continues walking through the doorway.",
        ], 1, 2)[1]["content"]
        self.assertIn("explicitly unfinished movement may continue", prompt)

    def test_overlapping_window_duplicate_is_removed(self):
        issue = {
            "beat_start": 6, "beat_end": 6,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "physical handoff",
            "problem": "The object appears without a handoff.",
        }
        self.assertEqual(minimax.merge_beat_plan_audit_issues([issue], [dict(issue)]), [issue])

    def test_global_prompt_owns_fidelity_and_phase_end_states(self):
        arc = {"phases": [{
            "phase_number": 1, "beat_start": 1, "beat_end": 5,
            "narrative_purpose": "Setup", "broad_progression": "Equip the protagonist",
            "characters_introduced": [], "location": "Basement",
            "required_end_state": "Three weapons are equipped.",
        }]}
        prompt = minimax.build_global_fidelity_audit_messages(
            "The protagonist retrieves three weapons.", self.BEATS[:5], arc
        )[1]["content"]
        self.assertIn("required_end_state", prompt)
        self.assertIn("Explicitly test every phase", prompt)
        self.assertIn("Do not audit ordinary adjacent movement", prompt)
        self.assertNotIn("subject definitions", prompt)

    def test_global_parser_covers_phase_end_prerequisite_and_state_failures(self):
        issue_types = [
            "phase_required_end_state", "missing_prerequisite", "persistent_state_conflict",
            "required_source_event_missing", "source_event_out_of_order",
            "repeated_process_incomplete", "unsupported_major_event",
        ]
        raw = {"valid": False, "issues": [{
            "beat_start": index + 1, "beat_end": index + 1, "type": issue_type,
            "source_requirement": "The source requires this concrete event.",
            "problem": "The definite requirement is not satisfied.",
        } for index, issue_type in enumerate(issue_types)]}
        parsed = minimax.parse_global_fidelity_audit(raw, 7)
        self.assertEqual([issue["type"] for issue in parsed["blocking_issues"]], issue_types)

    def test_global_parser_rejects_adjacent_location_issue(self):
        with self.assertRaises(ValueError):
            minimax.parse_global_fidelity_audit({"valid": False, "issues": [{
                "beat_start": 2, "beat_end": 2,
                "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
                "source_requirement": "movement", "problem": "Location changed.",
            }]}, 7)

    def test_candidate_verifier_is_compact_and_discards_speculation(self):
        issue = {
            "beat_start": 2, "beat_end": 2, "type": "persistent_state_conflict",
            "source_requirement": "The jaw injury remains definitive.",
            "problem": "The injured jaw means the subject cannot walk.",
        }
        messages = minimax.build_candidate_blocker_verification_messages(
            issue, 1, self.BEATS, story="A subject is injured.", macro_arc={}
        )
        self.assertIn("Do not find new issues", messages[0]["content"])
        self.assertIn("SOURCE REQUIREMENT", messages[1]["content"])
        decision = minimax.parse_candidate_blocker_verification(
            {"issue_id": 1, "decision": "DISCARD", "reason": "The claim is speculative."}, 1
        )
        self.assertEqual(decision["decision"], "DISCARD")

    def test_valid_plan_has_no_candidates(self):
        self.assertEqual(minimax.merge_beat_plan_audit_issues([], []), [])
        self.assertEqual(minimax.assign_stable_blocker_ids([]), [])

    def test_adjacent_repair_range_is_later_beat_only(self):
        issue = {
            "beat_start": 2, "beat_end": 3,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "physical reachability",
            "problem": "Beat 3 assumes an unshown move.",
        }
        normalized = minimax.normalize_beat_plan_repair_ranges([issue], 3)
        self.assertEqual(normalized["ranges"][0]["beat_start"], 3)
        self.assertEqual(normalized["ranges"][0]["beat_end"], 3)


if __name__ == "__main__":
    unittest.main()
