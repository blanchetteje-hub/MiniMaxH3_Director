import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import minimax


class SummaryToStoryPipelineTests(unittest.TestCase):
    def test_story_pipeline_profiles_match_tuned_settings(self):
        self.assertEqual(
            minimax.STORY_EXPANSION_LLM_PARAMETERS["temperature"],
            0.4,
        )
        self.assertEqual(minimax.STORY_EXPANSION_REASONING_EFFORT, "high")
        self.assertEqual(
            minimax.STORY_EXPANSION_REASONING_BUDGET_TOKENS,
            1024,
        )
        self.assertEqual(
            minimax.STORY_TO_BEATS_LLM_PARAMETERS["temperature"],
            0,
        )
        self.assertEqual(minimax.STORY_TO_BEATS_REASONING_EFFORT, "medium")
        self.assertEqual(
            minimax.STORY_TO_BEATS_REASONING_BUDGET_TOKENS,
            1024,
        )

    def test_story_expansion_prompt_uses_target_runtime_and_source_summary(self):
        messages = minimax.build_story_expansion_messages(
            "A ranger crosses a flooded valley.",
            64,
            total_segments=8,
        )
        self.assertIn("You are a novelist", messages[0]["content"])
        self.assertIn("A ranger crosses a flooded valley.", messages[1]["content"])
        self.assertIn("64-second timeframe", messages[1]["content"])
        self.assertIn("Preserve every explicit event and outcome", messages[1]["content"])
        self.assertIn("must happen visibly", messages[1]["content"])
        normalized = " ".join(messages[1]["content"].split())
        self.assertIn(
            "Do not compress, imply, or skip an explicit transition",
            normalized,
        )
        self.assertIn("location is unambiguous", normalized)
        self.assertIn("support 8 distinct film beats", normalized)
        self.assertIn(
            "The source's final explicit event must also be the expanded story's final event.",
            normalized,
        )
        self.assertIn(
            "Do not continue past it with a new destination, containment, escape, surviving threat, resolution, or aftermath.",
            normalized,
        )

    def test_story_location_extractor_uses_expanded_story_only(self):
        expanded = (
            "Mara begins in the bell tower above the old harbor. "
            "She later crosses the city and reaches the northern gate."
        )
        messages = minimax.build_story_location_messages(expanded)
        prompt = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("complete expanded story", prompt)
        self.assertIn("overall_location", prompt)
        self.assertIn("starting_location", prompt)
        self.assertIn("The scene starts in", prompt)
        self.assertIn(expanded, prompt)

        calls = []

        def llm_request(messages, **kwargs):
            calls.append((messages, kwargs))
            return {
                "overall_location": "the old harbor city",
                "starting_location": "the bell tower above the old harbor",
            }

        result = minimax.extract_story_locations(
            expanded,
            llm_request=llm_request,
            history_metadata={"run_id": "test"},
        )
        self.assertEqual(
            result,
            {
                "overall_location": "the old harbor city",
                "starting_location": "the bell tower above the old harbor",
            },
        )
        self.assertEqual(
            calls[0][1]["history_metadata"]["purpose"],
            "story_location_extract",
        )
        self.assertEqual(
            calls[0][1]["context_token_budget"],
            minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
        )

    def test_story_location_parser_strips_sentence_wrapper(self):
        self.assertEqual(
            minimax.parse_story_location_result({
                "overall_location": "the village",
                "starting_location": "The scene starts in the tavern.",
            }),
            {
                "overall_location": "the village",
                "starting_location": "the tavern",
            },
        )
        self.assertEqual(
            minimax.normalize_story_starting_location(
                "Scene begins in the upper market."
            ),
            "the upper market",
        )

    def test_story_location_parser_rejects_missing_location(self):
        with self.assertRaises(ValueError):
            minimax.parse_story_location_result({
                "overall_location": "the harbor city",
                "starting_location": "",
            })

    def test_story_to_beats_prompt_defers_subject_identity_to_raw(self):
        messages = minimax.build_story_to_beats_messages(
            "Mara must leave the tower and cross the bridge.",
            "Mara leaves the tower. Mara crosses the bridge.",
            8,
        )
        prompt = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertTrue(
            messages[0]["content"].startswith(
                "You are a screenplay writer that converts stories into films using a summary as a final guide."
            )
        )
        self.assertIn("convert it into 8 distinct, concise film beats", prompt)
        self.assertIn("No teleporting", prompt)
        self.assertIn(
            "SUMMARY\nMara must leave the tower and cross the bridge.",
            messages[1]["content"],
        )
        self.assertIn(
            "STORY\nMara leaves the tower. Mara crosses the bridge.",
            messages[1]["content"],
        )
        self.assertIn("exactly 8 sequential beats", prompt)
        self.assertIn("A terminal result belongs to one beat only", prompt)
        self.assertIn("current beat must stop before it", prompt)
        self.assertIn("Subject identity is resolved later", prompt)
        self.assertNotIn("@Guard1", prompt)
        self.assertNotIn("stable marked functional label", prompt)

    def test_timestamp_cleanup_removes_story_clock_times_only(self):
        cases = {
            "At 12:00:32 the front door slams open.": "The front door slams open.",
            "By 12:00:55 the last attackers fall.": "The last attackers fall.",
            "Mara fires at 00:01.500, then runs to the gate.": (
                "Mara fires then runs to the gate."
            ),
            "Mara waits for 5 seconds, then runs.": (
                "Mara waits for 5 seconds, then runs."
            ),
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(
                    minimax.strip_story_beat_timestamps(source),
                    expected,
                )

    def test_story_derived_macro_arc_is_one_event_per_beat(self):
        beats = [
            "Mara opens the gate.",
            "Mara walks through the gate.",
            "Mara closes the gate.",
        ]
        arc = minimax._story_derived_macro_arc(beats)
        phase = arc["phases"][0]
        self.assertEqual((phase["beat_start"], phase["beat_end"]), (1, 3))
        self.assertEqual(
            [event["event"] for event in phase["required_events"]],
            beats,
        )
        self.assertEqual(
            [event["beat_number"] for event in phase["required_events"]],
            [1, 2, 3],
        )
        self.assertEqual(phase["required_events"][1]["depends_on"], ["E1"])
        self.assertTrue(all(
            event["state_effects"] == []
            for event in phase["required_events"]
        ))
        self.assertEqual(phase["characters_introduced"], [])

    def test_two_pass_generation_feeds_timestamp_cleaned_beats_to_validator(self):
        expanded_story = (
            "Mara opens the gate, crosses the bridge, and closes the gate "
            "behind her."
        )
        raw_beats = {
            "beats": [
                {
                    "beat_number": 1,
                    "beat_text": "At 00:00 Mara opens the gate.",
                },
                {
                    "beat_number": 2,
                    "beat_text": "At 00:08 Mara crosses the bridge.",
                },
                {
                    "beat_number": 3,
                    "beat_text": "By 00:16 Mara closes the gate behind her.",
                },
            ]
        }
        calls = []

        def llm_request(messages, **kwargs):
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            calls.append((purpose, kwargs))
            if purpose == "story_expansion":
                return expanded_story
            if purpose == "story_to_beats":
                return raw_beats
            raise AssertionError(f"Unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory:
            beat_path = str(Path(directory) / "beats.txt")
            arc_path = str(Path(directory) / "story_arc.json")
            expanded_path = str(Path(directory) / "expanded_story.txt")
            with patch.object(
                minimax,
                "_run_forward_beat_validation",
                return_value=["validated"],
            ) as forward:
                result = minimax.generate_beats_via_story_expansion(
                    "Mara must open a gate, cross a bridge, and close it.",
                    3,
                    path=beat_path,
                    story_arc_path=arc_path,
                    expanded_story_path=expanded_path,
                    llm_request=llm_request,
                    duration_seconds=24,
                )

            self.assertEqual(result, ["validated"])
            framework_factory = forward.call_args.args[0]
            self.assertEqual(
                framework_factory(),
                [
                    "Mara opens the gate.",
                    "Mara crosses the bridge.",
                    "Mara closes the gate behind her.",
                ],
            )
            self.assertEqual(Path(expanded_path).read_text().strip(), expanded_story)
            self.assertEqual(
                [purpose for purpose, _kwargs in calls],
                ["story_expansion", "story_to_beats"],
            )
            for _purpose, kwargs in calls:
                self.assertEqual(
                    kwargs["context_token_budget"],
                    minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
                )


if __name__ == "__main__":
    unittest.main()
