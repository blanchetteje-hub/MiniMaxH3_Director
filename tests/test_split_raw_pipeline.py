"""Focused regressions for sequential creative, timing, and camera RAW stages."""

import unittest
from unittest import mock

import minimax


STATIC_TAVERN = (
    "The counter is fixed along the east side of the hall. "
    "The barrel is beside the hearth on the west wall."
)


def _bundle(beat, *, duration=8.0):
    user_context = (
        "SUBJECTS:\n- <Subject 1> Amy; <Picture 1>\n"
        "SUBJECT LOCATIONS (WorldState):\n- Amy: on tavern floor\n"
        "WARDROBE (current WorldState):\n- Amy: tunic and apron\n"
        "STATIC SETTING AUTHORITY\n" + STATIC_TAVERN + "\n"
        "PROPS:\n- chipped mug: held by Goblin\n\n"
        "CURRENT BEAT\n" + beat
    )
    return {
        "segment": 1,
        "active_beat_id": 1,
        "current_duration": duration,
        "messages": [{"role": "user", "content": user_context}],
        "current_beat_text": beat,
        "assigned_source": beat,
        "static_setting_description": STATIC_TAVERN,
        "subject_definitions": "<Subject 1> is Amy. <Subject 2> is Goblin.",
        "conditioning_mode": "initial",
        "opening_state_sha256": "split-raw-opening",
    }


def _timed_scene(lines, timestamps=None):
    if timestamps is None:
        timestamps = [index * 2 for index in range(len(lines))]
    return "\n".join(
        f"At 00:{second:02d}.000, {line}"
        for second, line in zip(timestamps, lines)
    )


def _accepted_raw(timed_scene):
    return minimax._normalize_director_end_continuity_marker(timed_scene)


def _timing_response_from_scene(timed_scene):
    timestamps = []
    for line in str(timed_scene or "").splitlines():
        match = minimax._DIRECTOR_TIMESTAMP_RE.match(line)
        if match:
            timestamps.append(match.group(0).removeprefix("At ").removesuffix(","))
    return {"status": "ok", "timestamps": timestamps}


class SplitRawDirectorPipelineTests(unittest.TestCase):
    def _run_pipeline(
        self,
        beat,
        creative_scene,
        timed_scene,
        *,
        camera_scene=None,
        creative_scenes=None,
        timing_responses=None,
        camera_responses=None,
        repair_scenes=(),
        physical_verdicts=(),
        other_validator_verdicts=(),
        validator_events=None,
    ):
        bundle = _bundle(beat)
        creative_iter = iter(creative_scenes or [creative_scene])
        timing_iter = iter(timing_responses or [
            _timing_response_from_scene(timed_scene)
        ])
        camera_iter = iter(camera_responses or [
            timed_scene if camera_scene is None else camera_scene
        ])
        repair_iter = iter(repair_scenes)
        llm_calls = []

        def fake_ask_llm(messages, **kwargs):
            metadata = kwargs.get("history_metadata") or {}
            purpose = metadata.get("purpose")
            llm_calls.append((purpose, messages, kwargs))
            if validator_events is not None:
                validator_events.append(f"llm:{purpose}")
            if purpose == "director_raw_scene_creative":
                return next(creative_iter)
            if purpose == "director_raw_scene_repair":
                return next(repair_iter)
            if purpose == "add_scene_timing_refiner":
                return next(timing_iter)
            if purpose == "add_camera_refiner":
                return next(camera_iter)
            if purpose == "director_h3_soundscape":
                return {"overall_soundscape": "Quiet tavern ambience."}
            if purpose == "director_h3_music":
                return {"non_diegetic_music": "N/A"}
            if purpose == "director_state_actions":
                return {"state_actions": []}
            raise AssertionError(f"Unexpected LLM purpose: {purpose!r}")

        physical_iter = iter(physical_verdicts)
        physical_candidates = []
        physical_contexts = []

        def fake_physical(beat_text, raw_text, **kwargs):
            physical_candidates.append(raw_text)
            physical_contexts.append(kwargs)
            if validator_events is not None:
                validator_events.append("validator:physical")
            try:
                return next(physical_iter)
            except StopIteration:
                return {"valid": True, "issue": ""}

        other_iter = iter(other_validator_verdicts)

        def fake_prop_validator(*args, **kwargs):
            if validator_events is not None:
                validator_events.append("validator:prop")
            try:
                return next(other_iter)
            except StopIteration:
                return {"valid": True, "issue": ""}

        def fake_timing_validator(*args, **kwargs):
            if validator_events is not None:
                validator_events.append("validator:timing")
            try:
                return next(other_iter)
            except StopIteration:
                return {"valid": True, "issue": ""}

        with (
            mock.patch("minimax.ask_llm", side_effect=fake_ask_llm),
            mock.patch(
                "minimax.validate_director_raw_scene_physical",
                side_effect=fake_physical,
            ),
            mock.patch(
                "minimax.validate_director_raw_scene_prop_state",
                side_effect=fake_prop_validator,
            ),
            mock.patch(
                "minimax.validate_director_raw_scene_timing",
                side_effect=fake_timing_validator,
            ),
            mock.patch(
                "minimax.resolve_director_raw_scene_pronouns",
                side_effect=lambda raw, *args, **kwargs: raw,
            ),
            mock.patch("minimax.console_log"),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "split-run", {"source_sha256": "split-source"}
            )
        return payload, llm_calls, physical_candidates, physical_contexts

    def test_creative_timing_camera_and_h3_contracts(self):
        creative = (
            "Amy walks from the east counter to the west-wall barrel.\n"
            "Amy pours ale from the barrel into Goblin's chipped mug."
        )
        timed = _timed_scene(
            creative.splitlines(),
            timestamps=[0, 4],
        )
        camera = timed.replace(
            "At 00:04.000, ",
            "At 00:04.000, [CAMERA: tracks Amy toward the barrel] ",
        )
        payload, calls, physical_candidates, physical_contexts = self._run_pipeline(
            "Amy pours ale into Goblin's chipped mug from the west-wall barrel.",
            creative,
            timed,
            camera_scene=camera,
        )

        purposes = [call[0] for call in calls]
        self.assertEqual(
            purposes[:4],
            [
                "director_raw_scene_creative",
                "add_scene_timing_refiner",
                "add_camera_refiner",
                "director_h3_soundscape",
            ],
        )
        creative_call = calls[0]
        self.assertIsNone(creative_call[2].get("response_format"))
        self.assertIn("<Subject 1>", creative_call[1][1]["content"])
        self.assertIn("<Picture 1>", creative_call[1][1]["content"])
        timing_call = calls[1]
        self.assertEqual(
            timing_call[2]["response_format"],
            minimax.ADD_SCENE_TIMING_REFINER_RESPONSE_FORMAT,
        )
        self.assertIn("1. Amy walks from the east counter", timing_call[1][1]["content"])
        self.assertIn("2. Amy pours ale", timing_call[1][1]["content"])
        self.assertEqual(
            timing_call[1][0]["content"],
            minimax.ADD_SCENE_TIMING_REFINER_SYSTEM_TEMPLATE.format(
                segment_length="8"
            ),
        )
        camera_call = calls[2]
        self.assertEqual(camera_call[1][0]["content"], minimax.ADD_CAMERA_REFINER_SYSTEM)
        self.assertIn("CURRENT BEAT", camera_call[1][1]["content"])
        self.assertIn(timed, camera_call[1][1]["content"])
        self.assertEqual(physical_candidates, [creative])
        self.assertEqual(physical_contexts[0]["static_setting_description"], STATIC_TAVERN)
        self.assertEqual(
            payload["raw_scene"],
            _accepted_raw(camera),
        )
        self.assertTrue(payload["request1_result"]["beat_complete"])
        self.assertEqual(
            minimax._director_strip_camera_instructions(payload["raw_scene"]),
            _accepted_raw(timed),
        )

    def test_content_validators_run_before_refiners_without_repeating(self):
        action = "Amy sets the mug on the counter."
        timed = _timed_scene([action], timestamps=[0])
        events = []
        payload, _calls, physical_candidates, _contexts = self._run_pipeline(
            action,
            action,
            timed,
            validator_events=events,
        )
        self.assertEqual(physical_candidates, [action])
        self.assertEqual(events.count("validator:physical"), 1)
        self.assertEqual(events.count("validator:prop"), 1)
        self.assertEqual(events.count("validator:timing"), 1)
        self.assertLess(events.index("validator:physical"), events.index("validator:prop"))
        self.assertLess(events.index("validator:prop"), events.index("llm:add_scene_timing_refiner"))
        self.assertLess(events.index("llm:add_scene_timing_refiner"), events.index("validator:timing"))
        self.assertLess(events.index("validator:timing"), events.index("llm:add_camera_refiner"))
        self.assertEqual(payload["raw_scene"], _accepted_raw(timed))

    def test_timestamp_validator_and_python_assembly_preserve_action_text(self):
        source = "Amy opens the door.\nAmy steps through it."
        actions = minimax._normalize_timing_refiner_action_lines(source)
        timestamps = ["00:00.000", "00:02.000"]
        self.assertEqual(
            minimax._timing_refiner_timestamp_error(actions, timestamps, 8),
            "",
        )
        self.assertEqual(
            minimax._assemble_timed_scene(actions, timestamps),
            "At 00:00.000, Amy opens the door.\nAt 00:02.000, Amy steps through it.",
        )
        with self.assertRaises(ValueError):
            minimax._parse_add_scene_timing_refiner_result({"raw_scene": source})

    def test_timing_numbering_omits_blank_lines_and_assembly_preserves_source(self):
        source = "  Amy opens the door.  \n\n \t\nAmy steps through it."
        actions = minimax._normalize_timing_refiner_action_lines(source)
        self.assertEqual(actions, ["  Amy opens the door.  ", "Amy steps through it."])
        messages = minimax.build_add_scene_timing_refiner_messages(source, 8)
        self.assertIn("1.   Amy opens the door.  ", messages[1]["content"])
        self.assertIn("2. Amy steps through it.", messages[1]["content"])
        self.assertNotIn("3.", messages[1]["content"])
        self.assertEqual(
            minimax._assemble_timed_scene(actions, ["00:00.000", "00:01.000"]),
            "At 00:00.000,   Amy opens the door.  \nAt 00:01.000, Amy steps through it.",
        )

    def test_timestamp_validation_rejects_malformed_count_order_and_duration(self):
        actions = ["Amy opens the door.", "Amy steps through it."]
        self.assertIn("malformed", minimax._timing_refiner_timestamp_error(
            actions, ["0:00.000", "00:02.000"], 8
        ))
        self.assertIn("wrong number", minimax._timing_refiner_timestamp_error(
            actions, ["00:00.000"], 8
        ))
        self.assertIn("increase strictly", minimax._timing_refiner_timestamp_error(
            actions, ["00:00.000", "00:00.000"], 8
        ))
        self.assertIn("increase strictly", minimax._timing_refiner_timestamp_error(
            [*actions, "Amy closes the door."],
            ["00:00.000", "00:02.000", "00:01.000"],
            8,
        ))
        self.assertIn("outside", minimax._timing_refiner_timestamp_error(
            actions, ["00:00.000", "00:08.000"], 8
        ))

    def test_timing_refiner_normalizes_unambiguous_timestamp_spellings(self):
        actions = ["Subject A opens the panel.", "Subject A closes it."]
        parsed = minimax._parse_add_scene_timing_refiner_result({
            "status": "ok",
            "timestamps": ["At 0:0.0,", "00:02:817"],
        })
        self.assertEqual(
            parsed["timestamps"],
            ["00:00.000", "00:02.817"],
        )
        self.assertEqual(
            minimax._timing_refiner_timestamp_error(
                actions,
                parsed["timestamps"],
                8,
            ),
            "",
        )
        self.assertEqual(
            minimax._assemble_timed_scene(actions, parsed["timestamps"]),
            "At 00:00.000, Subject A opens the panel.\n"
            "At 00:02.817, Subject A closes it.",
        )

    def test_timing_refiner_rejects_ambiguous_or_invalid_timestamp_values(self):
        for timestamp in ("00:08.1234", "00:08..8", "eight seconds"):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(ValueError, "malformed or ambiguous"):
                    minimax._parse_add_scene_timing_refiner_result({
                        "status": "ok",
                        "timestamps": [timestamp],
                    })
        actions = ["Subject A starts."]
        normalized_invalid = minimax._parse_add_scene_timing_refiner_result({
            "status": "ok",
            "timestamps": ["00:60.0"],
        })["timestamps"]
        self.assertIn(
            "seconds must be below 60",
            minimax._timing_refiner_timestamp_error(
                actions,
                normalized_invalid,
                70,
            ),
        )

    def test_pipeline_uses_normalized_timing_without_an_extra_llm_attempt(self):
        creative = "Subject A opens the panel.\nSubject A closes it."
        canonical_timed = (
            "At 00:00.000, Subject A opens the panel.\n"
            "At 00:02.817, Subject A closes it."
        )
        payload, calls, *_ = self._run_pipeline(
            creative,
            creative,
            canonical_timed,
            timing_responses=[{
                "status": "ok",
                "timestamps": ["0:0.0", "00:02:817"],
            }],
        )
        timing_calls = [
            call for call in calls if call[0] == "add_scene_timing_refiner"
        ]
        self.assertEqual(len(timing_calls), 1)
        self.assertIn(canonical_timed, payload["raw_scene"])

    def test_not_enough_time_regenerates_creative_without_raw_repair(self):
        first = "Amy crosses the room and pours the drink."
        second = "Amy walks to the barrel."
        timed = _timed_scene([second], timestamps=[0])
        payload, calls, _candidates, _contexts = self._run_pipeline(
            "Amy walks to the barrel.",
            first,
            timed,
            creative_scenes=[first, second],
            timing_responses=[
                {"status": "not_enough_time", "timestamps": []},
                _timing_response_from_scene(timed),
            ],
        )
        creative_calls = [call for call in calls if call[0] == "director_raw_scene_creative"]
        timing_calls = [call for call in calls if call[0] == "add_scene_timing_refiner"]
        self.assertEqual(len(creative_calls), 2)
        self.assertEqual(len(timing_calls), 2)
        self.assertFalse(any(call[0] == "director_raw_scene_repair" for call in calls))
        self.assertIn("TIMING INFEASIBLE", creative_calls[1][1][-1]["content"])
        self.assertEqual(payload["raw_scene"], _accepted_raw(timed))

    def test_timing_malformed_output_retries_only_timing_then_fails_closed(self):
        creative = "Amy walks to the door."
        altered = {"status": "ok", "timestamps": ["not-a-time"]}
        bundle = _bundle(creative)
        calls = []

        def fake_ask_llm(messages, **kwargs):
            purpose = kwargs["history_metadata"]["purpose"]
            calls.append(purpose)
            if purpose == "director_raw_scene_creative":
                return creative
            if purpose == "add_scene_timing_refiner":
                return altered
            raise AssertionError(f"Unexpected call after timing failure: {purpose}")

        with (
            mock.patch("minimax.ask_llm", side_effect=fake_ask_llm),
            mock.patch(
                "minimax.validate_director_raw_scene_physical",
                return_value={"valid": True, "issue": ""},
            ),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch(
                "minimax.resolve_director_raw_scene_pronouns",
                side_effect=lambda raw, *args, **kwargs: raw,
            ),
            mock.patch("minimax.console_log"),
            mock.patch("builtins.print"),
        ):
            with self.assertRaisesRegex(minimax.BeatGenerationError, "failed to preserve"):
                minimax.request_segment_llm(
                    bundle, [], "split-run", {"source_sha256": "split-source"}
                )

        self.assertEqual(calls.count("director_raw_scene_creative"), 1)
        self.assertEqual(
            calls.count("add_scene_timing_refiner"),
            minimax.DIRECTOR_RAW_REFINER_ATTEMPTS,
        )
        self.assertNotIn("add_camera_refiner", calls)
        self.assertNotIn("director_raw_scene_repair", calls)

    def test_timing_infeasibility_cannot_exceed_director_attempt_limit(self):
        creative = "Amy walks to the door."
        calls = []

        def fake_ask_llm(messages, **kwargs):
            purpose = kwargs["history_metadata"]["purpose"]
            calls.append((purpose, messages, kwargs["history_metadata"]))
            if purpose == "director_raw_scene_creative":
                return creative
            if purpose == "add_scene_timing_refiner":
                return {"status": "not_enough_time", "timestamps": []}
            raise AssertionError(f"Unexpected call: {purpose}")

        bundle = _bundle(creative)
        with (
            mock.patch("minimax.ask_llm", side_effect=fake_ask_llm),
            mock.patch("minimax.validate_director_raw_scene_physical", return_value={"valid": True, "issue": ""}),
            mock.patch("minimax.validate_director_raw_scene_prop_state", return_value={"valid": True, "issue": ""}),
            mock.patch(
                "minimax.resolve_director_raw_scene_pronouns",
                side_effect=lambda raw, *args, **kwargs: raw,
            ),
            mock.patch("minimax.console_log"),
            mock.patch("builtins.print"),
        ):
            with self.assertRaisesRegex(minimax.BeatGenerationError, "remained infeasible"):
                minimax.request_segment_llm(
                    bundle, [], "split-run", {"source_sha256": "split-source"}
                )

        creative_calls = [x for x in calls if x[0] == "director_raw_scene_creative"]
        timing_calls = [x for x in calls if x[0] == "add_scene_timing_refiner"]
        self.assertEqual(len(creative_calls), minimax.DIRECTOR_RAW_SCENE_ATTEMPTS)
        self.assertEqual(len(timing_calls), minimax.DIRECTOR_RAW_SCENE_ATTEMPTS)
        self.assertEqual(
            [call[2]["attempt"] for call in creative_calls],
            list(range(1, minimax.DIRECTOR_RAW_SCENE_ATTEMPTS + 1)),
        )

    def test_camera_tag_preserves_timestamps_actions_and_no_camera_is_valid(self):
        timed = _timed_scene(["Amy walks to the door."], timestamps=[0])
        camera = timed.replace(
            ", Amy walks", ", [CAMERA: slow push toward the doorway] Amy walks"
        )
        self.assertEqual(minimax._camera_refiner_content_error(timed, camera), "")
        self.assertEqual(minimax._camera_refiner_content_error(timed, timed), "")
        changed = timed.replace("Amy walks", "Amy runs")
        self.assertIn("changed action text", minimax._camera_refiner_content_error(timed, changed))
        moved_time = timed.replace("00:00.000", "00:01.000")
        self.assertIn("changed timestamp", minimax._camera_refiner_content_error(timed, moved_time))

    def test_camera_refiner_retries_bad_output_then_falls_back_to_timed_scene(self):
        creative = "Amy walks to the door."
        timed = _timed_scene([creative], timestamps=[0])
        altered = timed.replace("Amy walks", "Amy runs")
        payload, calls, _candidates, _contexts = self._run_pipeline(
            creative,
            creative,
            timed,
            camera_responses=[altered, "", altered],
        )
        camera_calls = [call for call in calls if call[0] == "add_camera_refiner"]
        self.assertEqual(len(camera_calls), minimax.DIRECTOR_RAW_REFINER_ATTEMPTS)
        self.assertEqual(payload["raw_scene"], _accepted_raw(timed))

    def test_west_wall_route_repairs_creative_before_timing(self):
        beat = "Amy refills Goblin's chipped mug from the barrel beside the hearth."
        impossible = (
            "Amy remains at the east counter and reaches across the room to pour "
            "from the barrel on the west wall into Goblin's mug."
        )
        corrected = (
            "Amy leaves the east counter and walks west to the barrel.\n"
            "Amy pours from the barrel into Goblin's mug."
        )
        timed = _timed_scene(corrected.splitlines(), timestamps=[0, 4])
        issue = "Amy cannot pour from the west-wall barrel while remaining at the east counter."
        payload, calls, physical_candidates, physical_contexts = self._run_pipeline(
            beat,
            impossible,
            timed,
            repair_scenes=[corrected],
            physical_verdicts=[
                {"valid": False, "issue": issue},
                {"valid": True, "issue": ""},
                {"valid": True, "issue": ""},
            ],
        )
        self.assertEqual(
            physical_candidates[:3],
            [impossible, corrected],
        )
        self.assertTrue(all(
            context["static_setting_description"] == STATIC_TAVERN
            for context in physical_contexts
        ))
        repair_call = next(call for call in calls if call[0] == "director_raw_scene_repair")
        self.assertIn(issue, "\n".join(str(message.get("content", "")) for message in repair_call[1]))
        self.assertEqual(payload["raw_scene"], _accepted_raw(timed))

    def test_single_action_timing_remains_valid_and_final_raw_is_downstream_ready(self):
        creative = "Amy sets the mug on the counter."
        timed = _timed_scene([creative], timestamps=[0])
        self.assertEqual(
            minimax._timing_refiner_timestamp_error(
                [creative], ["00:00.000"], 8
            ),
            "",
        )
        payload, _calls, _candidates, _contexts = self._run_pipeline(
            "Amy sets the mug on the counter.", creative, timed
        )
        self.assertEqual(
            minimax._director_raw_scene_structure_errors(payload["raw_scene"], 8),
            [],
        )
        self.assertIn("End continuity state:", payload["raw_scene"])


if __name__ == "__main__":
    unittest.main()
