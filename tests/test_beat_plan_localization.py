import unittest

import minimax


class BeatPlanLocalizationTests(unittest.TestCase):
    BEATS = [f"Beat text {number}." for number in range(1, 31)]

    def test_single_beat_repair_assigns_only_requested_source_job(self):
        jobs = [
            "Ren opens the cabinet.",
            "Ren replaces the damaged relay.",
            "Ren closes the cabinet.",
        ]
        phase = {
            "required_events": [
                {"id": f"E{i}", "beat_number": i, "event": job}
                for i, job in enumerate(jobs, 1)
            ],
        }
        for start, end in ((2, 2), (2, 3), (1, 3)):
            with self.subTest(start=start, end=end):
                messages = minimax.build_beat_generation_messages(
                    " ".join(jobs), 3, batch_start=start, batch_end=end,
                    current_phase=phase,
                )
                prompt = messages[1]["content"]
                assignment = prompt.split("REQUIRED EVENTS", 1)[1].split(
                    "\n\nWrite exactly", 1
                )[0]
                for number, job in enumerate(jobs, 1):
                    if start <= number <= end:
                        self.assertIn(f"{number}. {job}", assignment)
                    else:
                        self.assertNotIn(job, assignment)
                self.assertIn("SOURCE STORY:\n" + " ".join(jobs), prompt)

    def test_localizer_prompt_contains_only_reported_range_beats(self):
        issue = {
            "beat_start": 1,
            "beat_end": 5,
            "type": "phase_required_end_state",
            "source_requirement": "The family is safe by the end of the phase.",
            "problem": "The phase ends before the required safety state is established.",
        }
        messages = minimax.build_blocker_localization_messages(
            issue,
            self.BEATS,
            {"phases": [{"phase_number": 1, "beat_start": 1, "beat_end": 5}]},
        )
        user = messages[1]["content"]
        self.assertIn("Beat text 1.", user)
        self.assertIn("Beat text 5.", user)
        self.assertNotIn("Beat text 6.", user)
        self.assertIn("smallest", messages[0]["content"])
        self.assertIn("Do not find new problems", messages[0]["content"])

    def test_localizer_accepts_a_narrower_range(self):
        parsed = minimax.parse_blocker_localization(
            {"beat_start": 4, "beat_end": 5}, 1, 5
        )
        self.assertEqual(parsed, {"beat_start": 4, "beat_end": 5})

    def test_localizer_rejects_expanded_or_reversed_range(self):
        for response in (
            {"beat_start": 1, "beat_end": 6},
            {"beat_start": 5, "beat_end": 4},
            {"beat_start": "4", "beat_end": 5},
        ):
            with self.assertRaises(ValueError):
                minimax.parse_blocker_localization(response, 1, 5)

    def test_broad_ranges_are_not_downgraded(self):
        issue = {
            "beat_start": 1,
            "beat_end": 30,
            "type": "required_source_event_missing",
            "source_requirement": "The source requires the family to be released.",
            "problem": "The required release event is missing.",
        }
        normalized = minimax.normalize_beat_plan_repair_ranges([issue], 30)
        self.assertEqual(normalized["downgraded"], [])
        self.assertEqual(normalized["ranges"][0]["beat_start"], 1)
        self.assertEqual(normalized["ranges"][0]["beat_end"], 30)

    def test_malformed_localizer_response_can_fall_back_to_original_range(self):
        issue = {
            "beat_start": 6,
            "beat_end": 30,
            "type": "missing_prerequisite",
            "source_requirement": "The source requires the weapon to be acquired first.",
            "problem": "Beat 6 assumes the weapon before acquisition.",
        }
        with self.assertRaises(ValueError):
            minimax.parse_blocker_localization({"bad": True}, 6, 30)
        normalized = minimax.normalize_beat_plan_repair_ranges([issue], 30)
        self.assertEqual(normalized["issues"], [issue])


if __name__ == "__main__":
    unittest.main()
