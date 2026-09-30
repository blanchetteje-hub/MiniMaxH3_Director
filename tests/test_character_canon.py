import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import minimax


FIELDS = ("age", "clothing", "gender")


class CharacterCanonTests(unittest.TestCase):
    def test_canonical_data_fields_are_user_configurable(self):
        self.assertEqual(
            minimax.parse_canonical_data_fields(
                "age, clothing, gender\nhair color"
            ),
            ("age", "clothing", "gender", "hair_color"),
        )

    def test_parse_character_canon_result_uses_configured_fields(self):
        result = minimax.parse_character_canon_result(
            {
                "characters": [
                    {
                        "name": "Amy",
                        "age": "34",
                        "clothing": "tight black tank top, denim jeans",
                        "gender": "female",
                    }
                ]
            },
            canonical_fields=FIELDS,
        )
        self.assertEqual(result["fields"], list(FIELDS))
        self.assertEqual(result["characters"][0]["name"], "Amy")
        self.assertEqual(result["characters"][0]["gender"], "female")
        self.assertIn("black tank top", result["characters"][0]["clothing"])

    def test_character_canon_prompt_is_driven_by_configured_fields(self):
        messages = minimax.build_character_canon_messages(
            "Amy wears a black tank top. Will is Amy's son.",
            "<Subject 1> is Amy, a 34-year-old woman.\n"
            "<Subject 2> is Will, a 10-year-old boy.",
            canonical_fields=FIELDS,
        )
        prompt = messages[-1]["content"]
        self.assertIn("- age", prompt)
        self.assertIn("- clothing", prompt)
        self.assertIn("- gender", prompt)
        self.assertIn("Explicit facts", prompt)
        self.assertIn("do not replace them with an inference", prompt)
        self.assertIn("Amy wears a black tank top", prompt)
        self.assertIn("Will, a 10-year-old boy", prompt)
        self.assertIn('"gender": "value"', prompt)

    def test_response_schema_changes_with_canonical_fields(self):
        schema = minimax.build_character_canon_response_format(
            ("age", "eye_color")
        )
        item = schema["json_schema"]["schema"]["properties"]["characters"]["items"]
        self.assertEqual(
            set(item["properties"]),
            {"name", "age", "eye_color"},
        )
        self.assertEqual(
            set(item["required"]),
            {"name", "age", "eye_color"},
        )

    def test_source_matched_character_canon_is_reused_without_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            source_hash = minimax._character_canon_source_hash(
                "Amy protects Will.",
                "<Subject 1> is Amy, a woman.",
                canonical_fields=FIELDS,
            )
            minimax.save_character_canon(
                {
                    "fields": list(FIELDS),
                    "characters": [{
                        "name": "Amy",
                        "age": "34",
                        "clothing": "black tank top and denim jeans",
                        "gender": "female",
                    }],
                },
                source_hash,
                path=str(path),
                canonical_fields=FIELDS,
            )
            request = Mock(side_effect=AssertionError("LLM should not be called"))
            result = minimax.load_or_generate_character_canon(
                "Amy protects Will.",
                "<Subject 1> is Amy, a woman.",
                path=str(path),
                canonical_fields=FIELDS,
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "34")
            self.assertEqual(result["characters"][0]["gender"], "female")
            request.assert_not_called()

    def test_changing_configured_fields_changes_canon_source_hash(self):
        base = minimax._character_canon_source_hash(
            "Amy protects Will.",
            "<Subject 1> is Amy, a woman.",
            canonical_fields=("age", "clothing"),
        )
        changed = minimax._character_canon_source_hash(
            "Amy protects Will.",
            "<Subject 1> is Amy, a woman.",
            canonical_fields=("age", "clothing", "gender"),
        )
        self.assertNotEqual(base, changed)

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
                    "gender": "female",
                }]
            })
            result = minimax.load_or_generate_character_canon(
                "Amy protects Will.",
                "<Subject 1> is Amy, a woman.",
                path=str(path),
                canonical_fields=FIELDS,
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "34")
            self.assertEqual(result["characters"][0]["gender"], "female")
            self.assertEqual(request.call_count, 1)

    def test_character_facts_are_in_arc_and_compact_beat_prompt(self):
        subject_information = (
            "- Amy is a woman.\n"
            "- Amy canonical age: 34; canonical clothing: "
            "tight black tank top, denim jeans; canonical gender: female."
        )
        arc = minimax.build_beat_arc_plan_messages(
            "Amy cooks breakfast.", 1, subject_information=subject_information
        )
        self.assertIn("CANONICAL CHARACTER FACTS", arc[-1]["content"])
        self.assertIn("canonical gender: female", arc[-1]["content"])

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
        prompt = beat[-1]["content"]
        self.assertIn("SOURCE FILM", prompt)
        self.assertIn("CHARACTER FACTS", prompt)
        self.assertIn("canonical gender: female", prompt)
        self.assertIn("Keep spatial awareness at all times.", prompt)
        self.assertIn("Avoid pronouns, use names.", prompt)
        self.assertNotIn("BARRIER NAME RULES", prompt)
        self.assertNotIn("CLOSED BARRIERS AT START", prompt)
        self.assertNotIn("BARRIER STATES REQUIRED AT END", prompt)

    def test_segment_one_director_receives_canonical_starting_facts(self):
        rules = minimax.build_director_rules(
            16, 8, 2, "<Subject 1> is Amy.", 1,
            conditioning_mode="initial",
        )
        messages, _, _ = minimax.build_generation_messages(
            rules,
            "Amy cooks breakfast.",
            ["Amy cooks breakfast.", "Amy leaves the room."],
            set(),
            [],
            1,
            2,
            8,
            16,
            subject_definitions="<Subject 1> is Amy.",
            conditioning_mode="initial",
            canonical_character_facts=(
                "- Amy canonical age: 34; canonical clothing: black tank top; "
                "canonical gender: female."
            ),
        )
        prompt = messages[-1]["content"]
        self.assertIn("CANONICAL STARTING CHARACTER FACTS", prompt)
        self.assertIn("canonical clothing: black tank top", prompt)

        later, _, _ = minimax.build_generation_messages(
            rules,
            "Amy cooks breakfast.",
            ["Amy cooks breakfast.", "Amy leaves the room."],
            {1},
            [],
            2,
            2,
            8,
            16,
            subject_definitions="<Subject 1> is Amy.",
            conditioning_mode="continuation",
            canonical_character_facts=(
                "- Amy canonical age: 34; canonical clothing: black tank top; "
                "canonical gender: female."
            ),
        )
        self.assertNotIn(
            "CANONICAL STARTING CHARACTER FACTS",
            later[-1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
