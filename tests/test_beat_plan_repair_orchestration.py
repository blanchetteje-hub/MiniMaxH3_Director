import unittest

import minimax


class BeatPlanRepairOrchestrationTests(unittest.TestCase):
    MACRO_ARC = {
        "phases": [
            {"phase_number": 1, "beat_start": 1, "beat_end": 4},
            {"phase_number": 2, "beat_start": 5, "beat_end": 8},
        ]
    }

    @staticmethod
    def issue(start, end=None):
        end = start if end is None else end
        return {
            "beat_start": start,
            "beat_end": end,
            "type": minimax.ADJACENT_PHYSICAL_TRANSITION_ISSUE_TYPE,
            "source_requirement": "The transition must be shown.",
            "problem": "The transition is not shown.",
        }

    def test_scope_policy_accepts_clean_plan(self):
        self.assertEqual(
            minimax.classify_verified_blocker_scope([], self.MACRO_ARC),
            {"action": "accept", "phase_number": None},
        )

    def test_scope_policy_targets_only_small_local_blocker_sets(self):
        scope = minimax.classify_verified_blocker_scope(
            [self.issue(2), self.issue(3)],
            self.MACRO_ARC,
        )
        self.assertEqual(scope["action"], "targeted_repair")
        self.assertEqual(scope["phase_number"], 1)

    def test_three_blockers_in_one_phase_regenerate_that_phase(self):
        scope = minimax.classify_verified_blocker_scope(
            [self.issue(1), self.issue(2), self.issue(3)],
            self.MACRO_ARC,
        )
        self.assertEqual(scope, {"action": "regenerate_phase", "phase_number": 1})

    def test_wide_single_phase_blocker_regenerates_that_phase(self):
        scope = minimax.classify_verified_blocker_scope(
            [self.issue(1, 4)],
            self.MACRO_ARC,
        )
        self.assertEqual(scope, {"action": "regenerate_phase", "phase_number": 1})

    def test_cross_phase_blockers_regenerate_independently(self):
        scope = minimax.classify_verified_blocker_scope(
            [self.issue(2), self.issue(6)],
            self.MACRO_ARC,
        )
        self.assertEqual(scope["action"], "regenerate_phases")
        self.assertEqual(scope["phase_numbers"], [1, 2])

        independent = minimax.classify_verified_blocker_scopes(
            [self.issue(2), self.issue(6)],
            self.MACRO_ARC,
        )
        self.assertEqual(independent["action"], "recover_phases")
        self.assertEqual(
            [(item["phase_number"], item["action"]) for item in independent["decisions"]],
            [(1, "targeted_repair"), (2, "targeted_repair")],
        )

    def test_regeneration_scope_uses_phase_even_for_one_small_blocker(self):
        scope = minimax.classify_regeneration_scope(
            [self.issue(2)],
            self.MACRO_ARC,
        )
        self.assertEqual(scope, {"action": "regenerate_phase", "phase_number": 1})

    def test_convergence_gate_requires_strict_count_improvement(self):
        previous = [self.issue(2), self.issue(3)]
        self.assertTrue(
            minimax.targeted_repair_improved(
                previous,
                [self.issue(2)],
                self.MACRO_ARC,
            )
        )
        self.assertFalse(
            minimax.targeted_repair_improved(
                previous,
                [self.issue(1), self.issue(4)],
                self.MACRO_ARC,
            )
        )


if __name__ == "__main__":
    unittest.main()
