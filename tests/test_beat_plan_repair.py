import os
import tempfile
import unittest

import minimax


STORY = "The team performs a rescue, then returns home."
HARD_REQUIREMENT = "The team performs a rescue, then returns home."


def blocker(
    start,
    end,
    problem="The required event order is reversed.",
    source_requirement=HARD_REQUIREMENT,
    issue_type="chronology",
):
    return {
        "beat_start": start,
        "beat_end": end,
        "type": issue_type,
        "source_requirement": source_requirement,
        "problem": problem,
    }


def audit_result(*issues, macro_consistent=True, warnings=None):
    return {
        "valid": not issues,
        "macro_arc_consistent_with_source": macro_consistent,
        "blocking_issues": list(issues),
        "warnings": list(warnings or []),
    }


class PurposeDispatchLLM:
    def __init__(self, total_segments, audits, repairs=None):
        self.total_segments = total_segments
        self.audits = list(audits)
        self.repairs = list(repairs or [])
        self.calls = []
        self.generation_count = 0
        self.macro_count = 0

    def __call__(self, messages, **kwargs):
        metadata = kwargs["history_metadata"]
        purpose = metadata["purpose"]
        self.calls.append((purpose, messages, kwargs))
        if purpose == "beat_arc_plan":
            self.macro_count += 1
            return {
                "phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": self.total_segments,
                    "narrative_purpose": "Complete the source story.",
                    "broad_progression": "The rescue precedes the return.",
                    "characters_introduced": ["The team"],
                    "location": "The rescue site and homeward route.",
                    "required_end_state": "The team is home.",
                }]
            }
        if purpose == "beat_arc_fidelity":
            return {"valid": True, "issues": []}
        if purpose == "beat_generation":
            self.generation_count += 1
            generation = self.generation_count
            return {
                "beats": [
                    f"Plan {generation} event {beat_id} advances the rescue."
                    for beat_id in range(
                        metadata["batch_start"],
                        metadata["batch_end"] + 1,
                    )
                ]
            }
        if purpose == "beat_phase_validation":
            return {"valid": True, "issues": []}
        if purpose == "beat_plan_audit":
            if not self.audits:
                raise AssertionError("Unexpected extra global audit.")
            return self.audits.pop(0)
        if purpose == "beat_plan_repair":
            if not self.repairs:
                raise AssertionError("Unexpected extra repair response.")
            response = self.repairs.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response
        raise AssertionError(f"Unexpected LLM purpose: {purpose}")


class BeatPlanRepairHelperTests(unittest.TestCase):
    def test_audit_parser_discards_bad_ranges_but_keeps_valid_siblings(self):
        parsed = minimax.parse_beat_plan_audit(
            audit_result(
                "legacy blocker",
                blocker(0, 2),
                blocker(3, 4, problem="  A real   problem remains. "),
                blocker(9, 10),
            ),
            total_segments=8,
        )

        self.assertEqual(len(parsed["blocking_issues"]), 1)
        self.assertEqual(parsed["blocking_issues"][0]["beat_start"], 3)
        self.assertEqual(
            parsed["blocking_issues"][0]["problem"],
            "A real problem remains.",
        )
        self.assertEqual(parsed["discarded_blocking_issues"], 3)
        schema = minimax.build_beat_plan_audit_response_format(8)
        issue_schema = (
            schema["json_schema"]["schema"]["properties"]["blocking_issues"]
            ["items"]
        )
        self.assertEqual(issue_schema["properties"]["beat_end"]["maximum"], 8)

    def test_ranges_merge_through_two_intervening_beats_only(self):
        normalized = minimax.normalize_beat_plan_repair_ranges(
            [
                blocker(20, 22),
                blocker(15, 17),
                blocker(10, 12),
                blocker(4, 5),
                blocker(1, 3),
                blocker(0, 1),
            ],
            25,
        )

        self.assertEqual(
            [
                (item["beat_start"], item["beat_end"])
                for item in normalized["ranges"]
            ],
            [(1, 5), (10, 22)],
        )
        self.assertEqual(len(normalized["discarded"]), 1)
        distant = minimax.normalize_beat_plan_repair_ranges(
            [blocker(10, 12), blocker(20, 22)],
            25,
        )
        self.assertEqual(
            [
                (item["beat_start"], item["beat_end"])
                for item in distant["ranges"]
            ],
            [(10, 12), (20, 22)],
        )

    def test_persistent_state_conflict_remains_repairable_after_prior_repair(self):
        issue = blocker(
            6,
            6,
            problem="The later beat repeats a completed irreversible transition.",
            source_requirement=(
                "Definitive persistent state established earlier remains true."
            ),
            issue_type="persistent_state_conflict",
        )

        normalized = minimax.normalize_beat_plan_repair_ranges(
            [issue],
            8,
            repaired_beat_ids={6},
            story=STORY,
        )

        self.assertEqual(normalized["issues"], [issue])
        self.assertEqual(normalized["downgraded"], [])

    def test_multirange_response_and_splice_use_exact_id_union(self):
        ranges = [
            {"beat_start": 2, "beat_end": 3},
            {"beat_start": 7, "beat_end": 8},
        ]
        original = [f"Original event {beat_id} happens." for beat_id in range(1, 10)]
        replacement = minimax.parse_beat_plan_repair(
            {
                "beats": [
                    {"beat_id": 8, "text": "Repaired event eight happens."},
                    {"beat_id": 2, "text": "Repaired event two happens."},
                    {"beat_id": 7, "text": "Repaired event seven happens."},
                    {"beat_id": 3, "text": "Repaired event three happens."},
                ]
            },
            ranges,
        )
        repaired = minimax.splice_beat_plan_repair(
            original,
            ranges,
            replacement,
        )

        self.assertEqual(set(replacement), {2, 3, 7, 8})
        for beat_id in (1, 4, 5, 6, 9):
            self.assertEqual(repaired[beat_id - 1], original[beat_id - 1])
        schema = minimax.build_beat_plan_repair_response_format(ranges)
        beat_array = schema["json_schema"]["schema"]["properties"]["beats"]
        self.assertEqual((beat_array["minItems"], beat_array["maxItems"]), (4, 4))
        self.assertEqual(
            beat_array["items"]["properties"]["beat_id"]["enum"],
            [2, 3, 7, 8],
        )
        with self.assertRaisesRegex(ValueError, "Unexpected repaired beat ID 4"):
            minimax.parse_beat_plan_repair(
                {
                    "beats": [
                        {"beat_id": 2, "text": "Replacement two happens."},
                        {"beat_id": 3, "text": "Replacement three happens."},
                        {"beat_id": 4, "text": "Gap replacement happens."},
                        {"beat_id": 7, "text": "Replacement seven happens."},
                    ]
                },
                ranges,
            )

    def test_prompts_include_all_ranges_boundaries_and_repaired_ids(self):
        beats = [f"Event {beat_id} happens." for beat_id in range(1, 10)]
        ranges = [
            {"beat_start": 2, "beat_end": 3},
            {"beat_start": 7, "beat_end": 8},
        ]
        repair_prompt = minimax.build_beat_plan_repair_messages(
            STORY,
            9,
            beats,
            {"phases": []},
            [blocker(2, 3), blocker(7, 8)],
            ranges,
            subject_information="- Amy is the rescuer.",
        )[1]["content"]
        audit_prompt = minimax.build_beat_plan_audit_messages(
            STORY,
            9,
            beats,
            {"phases": []},
            repaired_beat_ids={2, 3, 7, 8},
        )[1]["content"]

        self.assertIn("Beats 2-3, 7-8", repair_prompt)
        self.assertIn("Beat 1: Event 1 happens.", repair_prompt)
        self.assertIn("Beat 4: Event 4 happens.", repair_prompt)
        self.assertIn("Beat 6: Event 6 happens.", repair_prompt)
        self.assertIn("Beat 9: Event 9 happens.", repair_prompt)
        self.assertIn("outside those ranges is immutable", repair_prompt)
        self.assertIn("PREVIOUSLY REPAIRED BEAT IDS", audit_prompt)
        self.assertIn("2, 3, 7, 8", audit_prompt)
        self.assertIn("not inherently suspicious", audit_prompt)


class BeatPlanRepairFlowTests(unittest.TestCase):
    def run_generation(self, fake, total_segments, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        result = minimax.generate_beats_from_story(
            STORY,
            total_segments,
            path=os.path.join(temporary.name, "beats.txt"),
            llm_request=fake,
            content_attempts=1,
            audit_attempts=kwargs.pop("audit_attempts", 1),
            repair_response_attempts=kwargs.pop("repair_response_attempts", 2),
            repair_rounds=kwargs.pop("repair_rounds", 2),
            subject_information="- Amy is the rescuer.",
            **kwargs,
        )
        return [str(beat) for beat in result]

    def test_all_distant_ranges_are_repaired_in_one_call_then_audited_once(self):
        fake = PurposeDispatchLLM(
            8,
            audits=[
                audit_result(blocker(2, 2), blocker(6, 6)),
                audit_result(),
            ],
            repairs=[{
                "beats": [
                    {"beat_id": 6, "text": "The team begins its return home."},
                    {"beat_id": 2, "text": "Amy completes the rescue."},
                ]
            }],
        )

        beats = self.run_generation(fake, 8)

        self.assertEqual(beats[1], "Amy completes the rescue.")
        self.assertEqual(beats[5], "The team begins its return home.")
        repair_calls = [call for call in fake.calls if call[0] == "beat_plan_repair"]
        audit_calls = [call for call in fake.calls if call[0] == "beat_plan_audit"]
        self.assertEqual((len(repair_calls), len(audit_calls)), (1, 2))
        metadata = repair_calls[0][2]["history_metadata"]
        self.assertEqual(
            metadata["repair_ranges"],
            [
                {"beat_start": 2, "beat_end": 2},
                {"beat_start": 6, "beat_end": 6},
            ],
        )
        self.assertEqual(metadata["repair_beat_ids"], [2, 6])

    def test_invalid_response_retries_inside_round_without_intermediate_audit(self):
        fake = PurposeDispatchLLM(
            5,
            audits=[audit_result(blocker(2, 2)), audit_result()],
            repairs=[
                {"beats": [{"beat_id": 3, "text": "Wrong ID is returned."}]},
                {"beats": [{"beat_id": 2, "text": "Amy completes the rescue."}]},
            ],
        )

        self.run_generation(fake, 5)

        purposes = [
            purpose for purpose, _, _ in fake.calls
            if purpose in {"beat_plan_audit", "beat_plan_repair"}
        ]
        self.assertEqual(
            purposes,
            [
                "beat_plan_audit",
                "beat_plan_repair",
                "beat_plan_repair",
                "beat_plan_audit",
            ],
        )
        repair_metadata = [
            kwargs["history_metadata"]
            for purpose, _, kwargs in fake.calls
            if purpose == "beat_plan_repair"
        ]
        self.assertEqual(
            [
                (item["repair_round"], item["response_attempt"])
                for item in repair_metadata
            ],
            [(1, 1), (1, 2)],
        )

    def test_two_rounds_allow_two_new_audits_and_one_final_audit(self):
        fake = PurposeDispatchLLM(
            8,
            audits=[
                audit_result(blocker(2, 2)),
                audit_result(blocker(6, 6)),
                audit_result(),
            ],
            repairs=[
                {"beats": [{"beat_id": 2, "text": "Amy completes the rescue."}]},
                {"beats": [{"beat_id": 6, "text": "The team returns home."}]},
            ],
        )

        self.run_generation(fake, 8)

        purposes = [
            purpose for purpose, _, _ in fake.calls
            if purpose in {"beat_plan_audit", "beat_plan_repair"}
        ]
        self.assertEqual(
            purposes,
            [
                "beat_plan_audit",
                "beat_plan_repair",
                "beat_plan_audit",
                "beat_plan_repair",
                "beat_plan_audit",
            ],
        )

    def test_ungrounded_repeat_on_repaired_ids_is_downgraded(self):
        fake = PurposeDispatchLLM(
            5,
            audits=[
                audit_result(blocker(2, 2)),
                audit_result(
                    blocker(
                        2,
                        2,
                        source_requirement="Macro phase pacing should be stronger.",
                    )
                ),
            ],
            repairs=[
                {"beats": [{"beat_id": 2, "text": "Amy completes the rescue."}]}
            ],
        )

        beats = self.run_generation(fake, 5)

        self.assertEqual(beats[1], "Amy completes the rescue.")
        self.assertEqual(
            sum(1 for purpose, _, _ in fake.calls if purpose == "beat_plan_repair"),
            1,
        )

    def test_grounded_repeat_on_repaired_ids_can_use_round_two(self):
        fake = PurposeDispatchLLM(
            5,
            audits=[
                audit_result(blocker(2, 2)),
                audit_result(
                    blocker(
                        2,
                        2,
                        problem="The hard source order is still unsatisfied.",
                    )
                ),
                audit_result(),
            ],
            repairs=[
                {"beats": [{"beat_id": 2, "text": "Amy attempts the rescue."}]},
                {"beats": [{"beat_id": 2, "text": "Amy completes the rescue."}]},
            ],
        )

        beats = self.run_generation(fake, 5)

        self.assertEqual(beats[1], "Amy completes the rescue.")
        self.assertEqual(
            sum(1 for purpose, _, _ in fake.calls if purpose == "beat_plan_repair"),
            2,
        )

    def test_repair_rounds_continue_past_former_limit(self):
        fake = PurposeDispatchLLM(
            8,
            audits=[
                audit_result(blocker(2, 2)),
                audit_result(blocker(5, 5)),
                audit_result(blocker(8, 8)),
                audit_result(),
            ],
            repairs=[
                {"beats": [{"beat_id": 2, "text": "Amy completes the rescue."}]},
                {"beats": [{"beat_id": 5, "text": "The team starts home."}]},
                {"beats": [{"beat_id": 8, "text": "The team arrives home."}]},
            ],
        )

        beats = self.run_generation(fake, 8, audit_attempts=1, repair_rounds=1)

        self.assertEqual(beats[1], "Amy completes the rescue.")
        self.assertEqual(beats[4], "The team starts home.")
        self.assertEqual(beats[7], "The team arrives home.")
        self.assertEqual(fake.generation_count, 1)
        self.assertEqual(
            sum(1 for purpose, _, _ in fake.calls if purpose == "beat_plan_repair"),
            3,
        )

    def test_all_malformed_ranges_trigger_full_plan_fallback(self):
        fake = PurposeDispatchLLM(
            4,
            audits=[
                audit_result("not a structured blocker"),
                audit_result(),
            ],
        )

        beats = self.run_generation(fake, 4, audit_attempts=2)

        self.assertTrue(all(beat.startswith("Plan 2 event") for beat in beats))
        self.assertEqual(fake.generation_count, 2)
        self.assertFalse(
            any(purpose == "beat_plan_repair" for purpose, _, _ in fake.calls)
        )

    def test_repair_responses_continue_past_former_attempt_limit(self):
        fake = PurposeDispatchLLM(
            4,
            audits=[
                audit_result(blocker(2, 2)),
                audit_result(),
            ],
            repairs=[
                RuntimeError("first malformed response"),
                RuntimeError("second malformed response"),
                RuntimeError("third malformed response"),
                {
                    "beats": [
                        {
                            "beat_id": 2,
                            "text": "Amy completes the rescue.",
                        }
                    ]
                },
            ],
        )

        beats = self.run_generation(
            fake,
            4,
            audit_attempts=1,
            repair_response_attempts=1,
        )

        self.assertEqual(beats[1], "Amy completes the rescue.")
        repair_calls = [call for call in fake.calls if call[0] == "beat_plan_repair"]
        self.assertEqual(len(repair_calls), 4)
        self.assertEqual(
            {
                call[2]["history_metadata"]["repair_round"]
                for call in repair_calls
            },
            {1},
        )

    def test_macro_inconsistency_still_skips_targeted_repair(self):
        fake = PurposeDispatchLLM(
            4,
            audits=[
                audit_result(
                    blocker(1, 4, issue_type="unsupported_premise"),
                    macro_consistent=False,
                ),
                audit_result(),
            ],
        )

        beats = self.run_generation(fake, 4, audit_attempts=2)

        self.assertTrue(all(beat.startswith("Plan 2 event") for beat in beats))
        self.assertEqual((fake.generation_count, fake.macro_count), (2, 2))
        self.assertFalse(
            any(purpose == "beat_plan_repair" for purpose, _, _ in fake.calls)
        )


if __name__ == "__main__":
    unittest.main()
