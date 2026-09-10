import unittest

import minimax


class BeatContinuityValidationTests(unittest.TestCase):
    def test_rejects_pursuer_that_jumps_from_behind_to_ahead(self):
        issues = minimax.validate_generated_beat_continuity([
            "The pursuer remains behind the runner.",
            "The pursuer is suddenly ahead of the runner.",
        ])

        self.assertTrue(issues)
        self.assertIn("spatial relationship", issues[0])

    def test_rejects_event_wording_that_places_pursuer_ahead(self):
        issues = minimax.validate_generated_beat_continuity([
            "The werewolf remains behind Amy.",
            "The werewolf bursts through the trees ahead of Amy.",
        ])

        self.assertTrue(issues)
        self.assertIn("spatial relationship", issues[0])

    def test_allows_explicit_overtaking_transition(self):
        issues = minimax.validate_generated_beat_continuity([
            "The pursuer remains behind the runner.",
            "The pursuer overtakes the runner and is now ahead of the runner.",
        ])

        self.assertEqual(issues, [])

    def test_checks_relationship_across_a_generated_batch_boundary(self):
        issues = minimax.validate_generated_beat_continuity(
            ["The pursuer is suddenly ahead of the runner."],
            beat_start=2,
            previous_beats=["The pursuer remains behind the runner."],
        )

        self.assertTrue(issues)
        self.assertIn("Beat 2", issues[0])

    def test_rejects_lower_body_absent_with_visible_legs(self):
        issues = minimax.validate_generated_beat_continuity([
            "The lower body is absent, but the legs remain visible.",
        ])

        self.assertTrue(issues)
        self.assertIn("lower body", issues[0])

    def test_preserves_lower_body_state_across_beats(self):
        issues = minimax.validate_generated_beat_continuity([
            "The lower body is absent.",
            "The legs remain visible as the figure moves.",
        ])

        self.assertTrue(issues)

    def test_allows_torso_absent_with_visible_legs(self):
        issues = minimax.validate_generated_beat_continuity([
            "The torso is absent while the legs remain visible.",
        ])

        self.assertEqual(issues, [])

    def test_does_not_cross_assign_unrelated_body_states(self):
        issues = minimax.validate_generated_beat_continuity([
            "The lower body is present while the legs are absent.",
        ])

        self.assertEqual(issues, [])

    def test_parse_generated_beats_uses_the_existing_validation_path(self):
        with self.assertRaisesRegex(ValueError, "spatial relationship"):
            minimax.parse_generated_beats(
                {
                    "beats": [
                        "The pursuer is suddenly ahead of the runner.",
                    ]
                },
                1,
                expected_start=2,
                previous_beats=["The pursuer remains behind the runner."],
            )


if __name__ == "__main__":
    unittest.main()
