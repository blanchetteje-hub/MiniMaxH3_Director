import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import minimax


CANONICAL_DATA = "age, clothing, gender"
STORY = (
    "Amy is wearing a tight, black tank-top and denim jeans, she is female and 30-years-old.\n"
    "Will is male and 8-years-old.\n"
    "Amber is female and 5-years-old."
)
SUBJECTS = "<Subject 1> is Amy.\n<Subject 2> is Will.\n<Subject 3> is Amber."


def character_result(age="30", clothing="black tank top and jeans", gender="female", other_facts=None):
    return {"characters": [{
        "name": "Amy", "age": age, "clothing": clothing,
        "gender": gender, "other_facts": other_facts or [],
    }]}


class CharacterCanonTests(unittest.TestCase):
    def test_canonical_data_is_loaded_as_configured_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical_data.txt"
            path.write_text(CANONICAL_DATA, encoding="utf-8")
            self.assertEqual(minimax.load_canonical_data(str(path)), CANONICAL_DATA)

    def test_parse_character_canon_result_uses_required_and_extra_fields(self):
        result = minimax.parse_character_canon_result(
            character_result(other_facts=[{"field": "eye color", "value": "brown"}]),
        )
        self.assertEqual(result["fields"], ["age", "clothing", "gender", "eye_color"])
        self.assertEqual(result["characters"][0]["name"], "Amy")
        self.assertEqual(result["characters"][0]["gender"], "female")
        self.assertEqual(result["characters"][0]["eye_color"], "brown")

    def test_character_canon_prompt_uses_configured_fields_story_and_subjects(self):
        messages = minimax.build_character_canon_messages(
            CANONICAL_DATA,
            STORY,
            SUBJECTS,
        )
        prompt = messages[-1]["content"]
        self.assertIn(CANONICAL_DATA, prompt)
        self.assertIn(STORY, prompt)
        self.assertIn(SUBJECTS, prompt)
        self.assertIn("If a configured value is missing, invent one reasonable value once.", prompt)
        self.assertIn("Do not invent characters.", prompt)

    def test_response_schema_requires_three_fields_and_allows_extra_facts(self):
        schema = minimax.build_character_canon_response_format()
        item = schema["json_schema"]["schema"]["properties"]["characters"]["items"]
        self.assertEqual(
            set(item["properties"]),
            {"name", "age", "clothing", "gender", "other_facts"},
        )
        self.assertEqual(set(item["required"]), set(item["properties"]))
        self.assertIn(
            "age|clothing|gender",
            item["properties"]["other_facts"]["items"]["properties"]["field"]["pattern"],
        )

    def test_source_matched_character_canon_is_regenerated_by_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            source_hash = minimax._character_canon_source_hash(
                CANONICAL_DATA,
                STORY,
                SUBJECTS,
            )
            minimax.save_character_canon(
                {
                    "fields": ["age", "clothing", "gender"],
                    "characters": [{
                        "name": "Amy",
                        "age": "30",
                        "clothing": "black tank top and denim jeans",
                        "gender": "female",
                    }],
                },
                source_hash,
                path=str(path),
            )
            request = Mock(return_value=character_result(age="31"))
            result = minimax.load_or_generate_character_canon(
                CANONICAL_DATA,
                story=STORY,
                subject_definitions=SUBJECTS,
                path=str(path),
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "31")
            self.assertEqual(result["characters"][0]["gender"], "female")
            request.assert_called_once()
            self.assertEqual(json.loads(path.read_text())["characters"][0]["age"], "31")

    def test_canonical_character_sentence_is_deterministic(self):
        self.assertEqual(
            minimax.format_canonical_character_sentence({
                "name": "Amber",
                "age": "5",
                "clothing": {
                    "top": "pink dress",
                    "bottom": "pink dress",
                },
                "gender": "female",
            }),
            "Amber is a 5-year-old female wearing a pink dress.",
        )
        self.assertEqual(
            minimax.format_canonical_character_sentence({
                "name": "Will",
                "age": "8-years-old",
                "clothing": "blue T-shirt and shorts",
                "gender": "male",
            }),
            "Will is an 8-year-old male wearing a blue T-shirt and shorts.",
        )

    def test_canonical_subject_descriptions_are_keyed_by_name(self):
        canon = {
            "characters": [
                {
                    "name": "Amber",
                    "age": "5",
                    "clothing": "pink dress",
                    "gender": "female",
                }
            ]
        }
        self.assertEqual(
            minimax.canonical_character_subject_descriptions(canon),
            {
                "Amber": (
                    "Amber is a 5-year-old female wearing a pink dress."
                )
            },
        )

    def test_character_canon_hash_tracks_fields_story_and_subjects(self):
        base = minimax._character_canon_source_hash(CANONICAL_DATA, STORY, SUBJECTS)
        self.assertNotEqual(
            base,
            minimax._character_canon_source_hash(
                "age, clothing, gender, hair color",
                STORY,
                SUBJECTS,
            ),
        )
        self.assertNotEqual(
            base,
            minimax._character_canon_source_hash(
                CANONICAL_DATA,
                STORY + "\nAmy has brown eyes.",
                SUBJECTS,
            ),
        )
        self.assertNotEqual(
            base,
            minimax._character_canon_source_hash(
                CANONICAL_DATA,
                STORY,
                SUBJECTS + "\n<Subject 4> is Mara.",
            ),
        )

    def test_stale_character_canon_is_regenerated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            path.write_text(json.dumps({
                "version": 3,
                "source_sha256": "0" * 64,
                "characters": [{
                    "name": "Amy",
                    "age": "99",
                    "clothing": "old outfit",
                }],
            }), encoding="utf-8")
            request = Mock(return_value=character_result())
            result = minimax.load_or_generate_character_canon(
                CANONICAL_DATA,
                story=STORY,
                subject_definitions=SUBJECTS,
                path=str(path),
                llm_request=request,
            )
            self.assertEqual(result["characters"][0]["age"], "30")
            self.assertEqual(result["characters"][0]["gender"], "female")
            self.assertEqual(request.call_count, 1)

    def test_canonical_wardrobe_extraction_covers_every_character_canon_subject(self):
        canon = {
            "fields": ["age", "clothing", "gender"],
            "characters": [
                {"name": "Subject Alpha", "age": "adult", "gender": "female", "clothing": "N/A"},
                {"name": "Subject Beta", "age": "adult", "gender": "male", "clothing": "N/A"},
                {"name": "Subject Gamma", "age": "adult", "gender": "unknown", "clothing": "N/A"},
            ],
        }

        def wardrobe_request(messages, **kwargs):
            name = messages[-1]["content"].split("SUBJECT\n", 1)[1].split("\n", 1)[0]
            return {"clothing": f"{name} simple clothes"}

        request = Mock(side_effect=wardrobe_request)
        with tempfile.TemporaryDirectory() as directory:
            result = minimax.canonicalize_defined_subject_wardrobes(
                canon,
                "A generic story with three Subjects.",
                "<Subject 1> is Subject Alpha.\n<Subject 2> is Subject Beta.",
                path=str(Path(directory) / "character_canon.json"),
                llm_request=request,
            )

        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            [call.kwargs["history_metadata"]["subject"] for call in request.call_args_list],
            ["Subject Alpha", "Subject Beta", "Subject Gamma"],
        )
        self.assertEqual(
            [call.kwargs["history_metadata"]["subject_id"] for call in request.call_args_list],
            [1, 2, None],
        )
        self.assertEqual(
            [record["clothing"] for record in result["characters"]],
            ["Subject Alpha simple clothes", "Subject Beta simple clothes", "Subject Gamma simple clothes"],
        )
        prompt = minimax.build_story_subject_wardrobe_messages(
            "story", "Subject Gamma"
        )[0]["content"]
        self.assertIn("any subject with a humanoid physical form must wear clothing", prompt)

    def test_subject_name_returned_as_clothing_retries_narrowly(self):
        request = Mock(side_effect=[
            {"clothing": "Subject Alpha"},
            {"clothing": "linen shirt and wool trousers"},
        ])
        clothing = minimax.extract_subject_canonical_wardrobe(
            "A generic story.",
            "Subject Alpha",
            llm_request=request,
        )
        self.assertEqual(clothing, "linen shirt and wool trousers")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in request.call_args_list],
            [1, 2],
        )

    def test_file_facts_become_json_and_only_missing_core_facts_are_invented(self):
        response = {"characters": [
            {"name": "Amy", "age": "30", "clothing": "tight black tank top and denim jeans",
             "gender": "female", "other_facts": [{"field": "eye color", "value": "brown"}]},
            {"name": "Will", "age": "8", "clothing": "blue T-shirt and shorts",
             "gender": "male", "other_facts": []},
            {"name": "Amber", "age": "5", "clothing": "yellow dress",
             "gender": "female", "other_facts": []},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character_canon.json"
            request = Mock(return_value=response)
            result = minimax.load_or_generate_character_canon(
                CANONICAL_DATA,
                story=STORY + "\nAmy has brown eyes.",
                subject_definitions=SUBJECTS,
                path=str(path), llm_request=request,
            )
            self.assertEqual(len(result["characters"]), 3)
            self.assertEqual(result["characters"][0]["eye_color"], "brown")
            self.assertEqual(result["characters"][1]["clothing"], "blue T-shirt and shorts")
            self.assertEqual(result["fields"], ["age", "clothing", "gender", "eye_color"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
            prompt = request.call_args.args[0][-1]["content"]
            self.assertIn(CANONICAL_DATA, prompt)
            self.assertIn(STORY, prompt)
            self.assertIn(SUBJECTS, prompt)

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
            canonical_data=CANONICAL_DATA,
        )
        prompt = messages[-1]["content"]
        self.assertIn("CANONICAL STARTING CHARACTER FACTS", prompt)
        self.assertIn("Amy canonical age: 34", prompt)
        self.assertIn("canonical clothing: black tank top", prompt)
        self.assertIn("canonical gender: female", prompt)

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
            canonical_data=CANONICAL_DATA,
        )
        self.assertNotIn(
            "CANONICAL STARTING CHARACTER FACTS",
            later[-1]["content"],
        )
        self.assertNotIn("Amy canonical age: 34", later[-1]["content"])



    def test_prepare_source_film_uses_full_story_and_merges_canonical_clothing(self):
        story = (
            "Amy cooks breakfast. A zombie attacks. She lets her kids out of the basement.\n\n"
            "Character information:\n"
            "Amy is wearing a tight, black tank-top and denim jeans, she is female and 30-years-old.\n"
            "Will is male and 8-years-old.\n"
            "Amber is female and 5-years-old."
        )
        subject_information = (
            "- Amy canonical age: 30; canonical clothing: tight black tank-top and denim jeans; canonical gender: female.\n"
            "- Will canonical age: 8; canonical clothing: t-shirt and shorts; canonical gender: male.\n"
            "- Amber canonical age: 5; canonical clothing: dress; canonical gender: female."
        )
        prepared = minimax.prepare_source_film_for_beats(
            story,
            subject_information,
        )
        self.assertIn("Amy cooks breakfast. A zombie attacks.", prepared)
        self.assertIn("She lets her kids out of the basement.", prepared)
        self.assertIn("CHARACTER INFORMATION:", prepared)
        self.assertNotIn("Character information:", prepared)
        self.assertIn(
            "Will is wearing t-shirt and shorts, and is male and 8-years-old.",
            prepared,
        )
        self.assertIn(
            "Amber is wearing dress, and is female and 5-years-old.",
            prepared,
        )
        self.assertEqual(prepared.count("Amy is wearing"), 1)

    def test_compact_beat_prompt_uses_prepared_full_source_film(self):
        story = (
            "Amy cooks breakfast. A zombie attacks. She lets her kids out of the basement.\n\n"
            "Character information:\n"
            "Will is male and 8-years-old."
        )
        subject_information = (
            "- Will canonical age: 8; canonical clothing: t-shirt and shorts; "
            "canonical gender: male."
        )
        phase = {
            "required_events": [{
                "id": "E7",
                "event": "She lets her kids out of the basement.",
                "beat_number": 7,
                "state_effects": [],
            }]
        }
        messages = minimax.build_beat_generation_messages(
            story,
            7,
            current_phase=phase,
            subject_information=subject_information,
            batch_start=7,
            batch_end=7,
        )
        prompt = messages[-1]["content"]
        self.assertIn("Amy cooks breakfast. A zombie attacks.", prompt)
        self.assertIn("CHARACTER INFORMATION:", prompt)
        self.assertIn("Will is wearing t-shirt and shorts", prompt)


if __name__ == "__main__":
    unittest.main()
