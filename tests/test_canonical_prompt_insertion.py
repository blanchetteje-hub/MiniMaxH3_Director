import tempfile
import unittest
from pathlib import Path
from unittest import mock

import minimax


class CanonicalPromptInsertionTests(unittest.TestCase):
    def prompt(self, segment, **kwargs):
        return minimax.build_h3_prompt(
            {"detailed_description": "<Subject 1> Amy walks.",
             "overall_soundscape": "Wind.", "non_diegetic_music": "N/A"},
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=segment, **kwargs,
        )

    def test_segment_one_appends_verbatim_after_subject_definitions(self):
        raw = "  **Amy**: red coat.\r\nretention_analysis: keep this verbatim.\r\n\r\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical_data.txt"
            path.write_bytes(raw.encode("utf-8"))
            with mock.patch.object(minimax, "CANONICAL_DATA_FILE", str(path)):
                for ff in (False, True):
                    with self.subTest(ff=ff):
                        prompt = self.prompt(1, ff=ff)
                        self.assertIn(raw + "\n\ndetailed_description:", prompt)
                        self.assertEqual(prompt.count(raw), 1)
                        self.assertLess(prompt.index("subject_definitions:"), prompt.index(raw))
                self.assertNotIn(raw, self.prompt(2))
                self.assertNotIn(raw, self.prompt(None))

    def test_missing_or_empty_file_leaves_prompt_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical_data.txt"
            with mock.patch.object(minimax, "CANONICAL_DATA_FILE", str(path)):
                expected = self.prompt(1)
                path.write_text("", encoding="utf-8")
                self.assertEqual(self.prompt(1), expected)
                self.assertNotIn("CANONICAL_DATA_VERBATIM_INSERTION_POINT", expected)

    def test_segment_one_includes_canon_sentences_using_existing_formatter(self):
        canon = {"characters": [
            {"name": "Amy", "age": "34", "gender": "female", "clothing": "black tank top and jeans"},
            {"name": "Will", "age": "8", "gender": "male", "clothing": "blue shirt"},
        ]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            minimax, "CANONICAL_DATA_FILE", str(Path(directory) / "missing.txt")
        ):
            prompt = self.prompt(1, character_canon=canon)
            subject_section = prompt.split("\n\ndetailed_description:", 1)[0]
            for record in canon["characters"]:
                sentence = minimax.format_canonical_character_sentence(record)
                self.assertIn(sentence, subject_section)
                self.assertEqual(prompt.count(sentence), 1)
                self.assertNotIn(sentence, self.prompt(2, character_canon=canon))

    def test_canon_prose_and_raw_optional_data_are_both_kept(self):
        canon = {"characters": [{"name": "Amy", "age": "34", "gender": "female", "clothing": "red coat"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical_data.txt"
            raw = "  Amy has green eyes.\r\n"
            path.write_bytes(raw.encode("utf-8"))
            with mock.patch.object(minimax, "CANONICAL_DATA_FILE", str(path)):
                prompt = self.prompt(1, character_canon=canon)
            self.assertIn(minimax.format_canonical_character_sentence(canon["characters"][0]), prompt)
            self.assertIn(raw + "\n\ndetailed_description:", prompt)
