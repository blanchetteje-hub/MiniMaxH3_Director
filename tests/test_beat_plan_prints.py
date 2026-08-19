"""Focused tests for the per-prompt story-beat console plan."""

import io
import unittest
from contextlib import redirect_stdout

import minimax


BEATS = [
    "Introduce Mark and Jill.",
    "Show the saucers overhead.",
    "Have Mark and Jill discuss the saucers.",
    "Show the family's abduction.",
]


class BeatPlanPrintTests(unittest.TestCase):
    def capture_plan(self, beats, completed, reported):
        output = io.StringIO()
        with redirect_stdout(output):
            result = minimax.print_minimax_beat_plan(
                beats,
                completed,
                reported,
            )
        return result, output.getvalue()

    def test_prints_all_beats_completed_by_prompt_and_the_following_beat(self):
        result, output = self.capture_plan(BEATS, {1}, [2, 3])

        self.assertEqual(result, ([2, 3], 4))
        self.assertIn("Completing in this prompt:", output)
        self.assertIn("B002: Show the saucers overhead.", output)
        self.assertIn("B003: Have Mark and Jill discuss the saucers.", output)
        self.assertIn("Next required after this prompt:", output)
        self.assertIn("B004: Show the family's abduction.", output)

    def test_out_of_order_claim_is_not_printed_as_a_completion(self):
        result, output = self.capture_plan(BEATS, {1}, [3])

        self.assertEqual(result, ([], 2))
        self.assertIn("None reported complete by the formatted prompt.", output)
        self.assertIn("Still targeting B002: Show the saucers overhead.", output)
        self.assertIn("Next required after this prompt:", output)
        self.assertNotIn("B003:", output)

    def test_last_completion_prints_that_all_beats_would_be_complete(self):
        result, output = self.capture_plan(BEATS, {1, 2, 3}, [4])

        self.assertEqual(result, ([4], None))
        self.assertIn("B004: Show the family's abduction.", output)
        self.assertIn("All required beats would be complete.", output)

    def test_blank_beats_print_nothing(self):
        result, output = self.capture_plan([], set(), [1])

        self.assertEqual(result, ([], None))
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
