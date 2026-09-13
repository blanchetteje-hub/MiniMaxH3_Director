"""Tests for formatting repairs shared by all model formatters."""

from __future__ import annotations

import unittest

from formatter_base import BaseFormatter
from ministral_formatter import MinistralFormatter
from qwen_formatter import QwenFormatter


class _TestFormatter(BaseFormatter):
    def format_prompt(self, llm_result, context):
        del context
        return dict(llm_result)

    def validate_prompt(self, result, context):
        del result, context
        return []


def _result(description: str) -> dict[str, object]:
    return {
        "detailed_description": description,
        "overall_soundscape": "Footsteps echo.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [],
    }


class BaseFormatterTests(unittest.TestCase):
    def test_removes_subject_references_only_inside_dialogue(self) -> None:
        raw = _result(
            "<Subject 1> Amy says: <d>Hi Subject 1 Amy, Subject 2!</d> "
            "<Subject 2> remains outside."
        )

        formatted = _TestFormatter().format_prompt(raw, None)

        self.assertEqual(
            formatted["detailed_description"],
            "<Subject 1> Amy says: <d>Hi Amy!</d> <Subject 2> remains outside.",
        )
        self.assertEqual(
            raw["detailed_description"],
            "<Subject 1> Amy says: <d>Hi Subject 1 Amy, Subject 2!</d> "
            "<Subject 2> remains outside.",
        )

    def test_runs_for_each_concrete_formatter(self) -> None:
        raw = _result("Amy says: <d>Hi Subject 1 Amy.</d>")
        context = {"segment_number": 1}

        for formatter in (MinistralFormatter(), QwenFormatter()):
            with self.subTest(formatter=type(formatter).__name__):
                formatted = formatter.format_prompt(raw, context)
                self.assertNotRegex(
                    formatted["detailed_description"],
                    r"<d>.*?Subject\s+1.*?</d>",
                )


if __name__ == "__main__":
    unittest.main()
