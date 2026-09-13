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
            "The werewolf remains behind Elias.",
            "The werewolf bursts through the trees ahead of Elias.",
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
