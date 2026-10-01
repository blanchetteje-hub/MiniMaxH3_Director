import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import minimax


class SummaryToStoryPipelineTests(unittest.TestCase):
    def test_story_pipeline_profiles_match_tuned_settings(self):
        self.assertEqual(
            minimax.STORY_EXPANSION_LLM_PARAMETERS["temperature"],
            0.6,
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
        self.assertIn(
            "When the summary does not specify a new location, route, barrier, or container, keep the action in the nearest already-established location rather than inventing one.",
            normalized,
        )
        self.assertIn("support 8 distinct film beats", normalized)

    def test_story_to_beats_prompt_keeps_full_story_and_continuity_rule(self):
        messages = minimax.build_story_to_beats_messages(
            "Mara leaves the tower. Mara crosses the bridge.",
            8,
        )
        prompt = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("convert it into 8 distinct, concise film beats", prompt)
        self.assertIn("No teleporting", prompt)
        self.assertIn("Mara leaves the tower. Mara crosses the bridge.", prompt)
        self.assertIn("exactly 8 sequential beats", prompt)

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
