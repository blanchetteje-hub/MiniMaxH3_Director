import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import minimax


class CharacterCanonTests(unittest.TestCase):
    def test_parse_character_canon_result(self):
        result = minimax.parse_character_canon_result({
            "characters": [
                {
                    "name": "Amy",
                    "age": "34",
                    "clothing": "tight black tank top, denim jeans",
                }
            ]
        })
        self.assertEqual(result["characters"][0]["name"], "Amy")
        self.assertEqual(result["characters"][0]["age"], "34")
        self.assertIn("black tank top", result["characters"][0]["clothing"])

    def test_character_canon_prompt_preserves_explicit_facts_and_fills_missing(self):
        messages = minimax.build_character_canon_messages(
            "Amy wears a black tank top. Will is Amy's son.",
            "<Subject 1> is Amy, a 34-year-old woman.\n"
            "<Subject 2> is Will, a 10-year-old boy.",
        )
        prompt = messages[-1]["content"]
        self.assertIn("Explicit facts", prompt)
        self.assertIn("do not replace them with an inference", prompt)
        self.assertIn("Amy wears a black tank top", prompt)
        self.assertIn("Will, a 10-year-old boy", prompt)

    def test_source_matched_character_canon_is_reused_without_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            source_hash = minimax._character_canon_source_hash(
                "Amy protects Will.", "<Subject 1> is Amy, a woman."
            )
            minimax.save_character_canon(
                {
                    "characters": [{
                        "name": "Amy",
                        "age": "34",
                        "clothing": "black tank top and denim jeans",
                    }]
                },
                source_hash,
                path=str(path),
            )
            request = Mock(side_effect=AssertionError("LLM should not be called"))
            result = minimax.load_or_generate_character_canon(
                "Amy protects Will.",
                "<Subject 1> is Amy, a woman.",
                path=str(path),
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "34")
            request.assert_not_called()

    def test_stale_character_canon_is_regenerated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            path.write_text(json.dumps({
                "version": 1,
                "source_sha256": "0" * 64,
                "characters": [{
                    "name": "Amy",
                    "age": "99",
                    "clothing": "old outfit",
                }],
            }), encoding="utf-8")
            request = Mock(return_value={
                "characters": [{
                    "name": "Amy",
                    "age": "34",
                    "clothing": "black tank top and denim jeans",
                }]
            })
            result = minimax.load_or_generate_character_canon(
                "Amy protects Will.",
                "<Subject 1> is Amy, a woman.",
                path=str(path),
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "34")
            self.assertEqual(request.call_count, 1)

    def test_canonical_character_facts_are_in_arc_and_beat_prompts(self):
        subject_information = (
            "- Amy is a woman.\n"
            "- Amy canonical age: 34; canonical clothing: "
            "tight black tank top, denim jeans."
        )
        arc = minimax.build_beat_arc_plan_messages(
            "Amy cooks breakfast.", 1, subject_information=subject_information
        )
        self.assertIn("CANONICAL CHARACTER FACTS", arc[-1]["content"])
        self.assertIn("canonical age: 34", arc[-1]["content"])

        phase = {
            "required_events": [{
                "id": "E1",
                "event": "Amy cooks breakfast.",
                "beat_number": 1,
                "state_effects": [],
            }]
        }
        beat = minimax.build_beat_generation_messages(
            "Amy cooks breakfast.",
            1,
            current_phase=phase,
            subject_information=subject_information,
        )
        self.assertIn("CANONICAL CHARACTER FACTS", beat[-1]["content"])
        self.assertIn("tight black tank top", beat[-1]["content"])


if __name__ == "__main__":
    unittest.main()
