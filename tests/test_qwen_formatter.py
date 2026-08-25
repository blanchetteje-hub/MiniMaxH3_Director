"""Regression coverage derived from the locally loaded Qwen model."""

from __future__ import annotations

import unittest

from formatter_base import BaseFormatter
from qwen_formatter import QwenFormatter


SUBJECTS = (
    "<Subject 1> is Mark, a 40-year-old man referenced in <Picture 1>.\n"
    "<Subject 2> is Jill, a 35-year-old woman referenced in <Picture 2>."
)


def context(segment: int) -> dict:
    return {
        "segment_number": segment,
        "segment_duration": 6.0,
        "subject_definitions": SUBJECTS,
        "completed_beat_ids": list(range(1, segment)),
        "next_beat_id": segment,
        "current_beat_text": "Show Mark and Jill talking.",
        "later_beat_texts": [],
        "beat_deadline_required": False,
        "allow_silence": False,
        "hard_cut_required": segment % 3 == 0,
    }


def result(description: str, soundscape: str, music: str = "N/A") -> dict:
    return {
        "detailed_description": description,
        "overall_soundscape": soundscape,
        "non_diegetic_music": music,
        "completed_beat_ids": [3],
    }


class QwenFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.formatter = QwenFormatter()

    def test_implements_shared_formatter_contract(self) -> None:
        self.assertIsInstance(self.formatter, BaseFormatter)

    def test_repairs_pronoun_dialogue_attribution_from_live_output(self) -> None:
        raw = result(
            "[Shot 3] The camera zooms in on Mark's face as he says: "
            "<d>[English] Did you see that light?</d> At 00:06.000, the "
            "camera pans to Jill's face as she says: "
            "<d>[English] I heard something crash!</d>",
            "Crowds gasp while a low hum fills the park.",
        )

        formatted = self.formatter.format_prompt(raw, context(3))

        self.assertIn("Mark (S1) says:", formatted["detailed_description"])
        self.assertIn("Jill (S2) says:", formatted["detailed_description"])
        self.assertEqual(self.formatter.validate_prompt(formatted, context(3)), [])

    def test_preserves_non_music_soundscape_clauses_from_live_output(self) -> None:
        raw = result(
            "[Shot 3] Mark <Picture 1> and Jill <Picture 2> watch the sky.",
            "The ambient soundscape consists of distant theme park music, "
            "laughter, screams, a low hum, and sudden metallic clangs.",
        )

        formatted = self.formatter.format_prompt(raw, context(3))

        soundscape = formatted["overall_soundscape"]
        self.assertNotIn("music", soundscape.lower())
        self.assertIn("laughter", soundscape.lower())
        self.assertIn("metallic clangs", soundscape.lower())
        self.assertFalse(soundscape.lower().startswith("with "))

    def test_normalizes_qwen_ellipsis_and_abstract_music_words(self) -> None:
        raw = {
            "detailed_description": (
                "[Shot 2] Camera continues from the previous shot... "
                "Several saucers cross overhead."
            ),
            "overall_soundscape": "Engines rumble while crowds gasp.",
            "non_diegetic_music": (
                "A tense, dramatic score uses a throbbing bassline and "
                "high-pitched electronic tones."
            ),
            "completed_beat_ids": [2],
        }

        formatted = self.formatter.format_prompt(raw, context(2))

        self.assertNotIn("shot. ..", formatted["detailed_description"].lower())
        self.assertNotIn("tense", formatted["non_diegetic_music"].lower())
        self.assertNotIn("dramatic", formatted["non_diegetic_music"].lower())
        self.assertEqual(self.formatter.validate_prompt(formatted, context(2)), [])

    def test_clamps_events_at_or_beyond_the_clip_boundary(self) -> None:
        raw = result(
            "[Shot 3] Mark <Picture 1> and Jill <Picture 2> watch the sky. "
            "At 00:06.000, they turn toward a metallic clang.",
            "A metallic clang echoes while crowds gasp.",
        )

        formatted = self.formatter.format_prompt(raw, context(3))

        self.assertIn("At 00:05.999,", formatted["detailed_description"])
        self.assertNotIn("At 00:06.000,", formatted["detailed_description"])

    def test_preserves_terminal_event_order_and_removes_visual_speaker_ids(self) -> None:
        raw = {
            "detailed_description": (
                "[Shot 1] Mark <Picture 1> (S1) and Jill <Picture 2> (S2) "
                "enjoy the park. At 00:06.000, their daughter runs to them. "
                "At 00:08.000, lights cross the sky."
            ),
            "overall_soundscape": (
                "Cheerful theme park music plays in the background with "
                "laughter and ride machinery."
            ),
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }

        formatted = self.formatter.format_prompt(raw, context(1))
        description = formatted["detailed_description"]

        self.assertNotIn("(S1)", description)
        self.assertNotIn("(S2)", description)
        self.assertLess(
            description.index("At 00:05.998,"),
            description.index("At 00:05.999,"),
        )
        self.assertTrue(
            formatted["overall_soundscape"].startswith("Laughter")
        )


if __name__ == "__main__":
    unittest.main()
