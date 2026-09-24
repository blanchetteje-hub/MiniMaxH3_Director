import unittest

import minimax
from gpt_formatter import GPTFormatter


class GPTFormatterTests(unittest.TestCase):
    def test_gpt_formatter_is_available_and_is_default_runtime_formatter(self):
        self.assertIsInstance(minimax.get_formatter("gpt"), GPTFormatter)
        self.assertIsInstance(minimax.ACTIVE_FORMATTER, GPTFormatter)

    def test_gpt_formatter_preserves_copied_baseline_behavior(self):
        formatter = GPTFormatter()
        raw = {
            "detailed_description": (
                "[Shot 1] Live-action, cinematic. "
                "At 00:00.000, Amy sets a plate on the table."
            ),
            "overall_soundscape": "A plate clinks against the table.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }
        context = {
            "segment_number": 1,
            "next_beat_id": 1,
            "segment_duration": 8,
        }
        formatted = formatter.format_prompt(raw, context)
        self.assertEqual(formatted["completed_beat_ids"], [1])
        self.assertIn("Amy sets a plate on the table", formatted["detailed_description"])
        self.assertEqual(formatter.validate_prompt(formatted, context), [])


if __name__ == "__main__":
    unittest.main()
