"""Focused regressions for split creative RAW and physical repair stages."""

import unittest
from unittest import mock

import minimax


STATIC_TAVERN = (
    "The counter is fixed along the east side of the hall. "
    "The barrel is beside the hearth on the west wall."
)


def _bundle(beat):
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
        "current_duration": 8.0,
        "messages": [{"role": "user", "content": user_context}],
        "current_beat_text": beat,
        "assigned_source": beat,
        "static_setting_description": STATIC_TAVERN,
        "subject_definitions": "<Subject 1> is Amy. <Subject 2> is Goblin.",
        "conditioning_mode": "initial",
        "opening_state_sha256": "split-raw-opening",
    }


def _timed_raw(lines, ending="Amy stands on the tavern floor."):
    return "\n".join(
        [f"At 00:{index * 2:02d}.000, {line}" for index, line in enumerate(lines)]
        + [f"End continuity state: {ending}"]
    )


def _formatted(raw_scene):
    return {
        "raw_scene": raw_scene,
        "finite_activity_complete": True,
        "named_beneficiaries_complete": True,
        "activity_tools_settled": True,
        "beat_complete": True,
    }


class SplitRawDirectorPipelineTests(unittest.TestCase):
    def _run_pipeline(
        self,
        beat,
        creative_scene,
        formatted_scene,
        *,
        repair_scenes=(),
        physical_verdicts=(),
        other_validator_verdicts=(),
    ):
        bundle = _bundle(beat)
        repair_iter = iter(repair_scenes)
        llm_calls = []

        def fake_ask_llm(messages, **kwargs):
            metadata = kwargs.get("history_metadata") or {}
            purpose = metadata.get("purpose")
            llm_calls.append((purpose, messages, kwargs))
            if purpose == "director_raw_scene_creative":
                return creative_scene
            if purpose == "director_raw_scene_repair":
                return next(repair_iter)
            if purpose == "director_raw_scene":
                return _formatted(formatted_scene)
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
            try:
                return next(physical_iter)
            except StopIteration:
                return {"valid": True, "issue": ""}

        other_iter = iter(other_validator_verdicts)

        def fake_other_validator(*args, **kwargs):
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
                side_effect=fake_other_validator,
            ),
            mock.patch(
                "minimax.validate_director_raw_scene_timing",
                side_effect=fake_other_validator,
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

    def test_creative_stage_is_untimed_and_feeds_downstream_formatter(self):
        creative = (
            "Amy walks from the counter to the barrel.\n"
            "She fills Goblin's chipped mug and returns to the counter."
        )
        timed = _timed_raw(
            [
                "Amy leaves the east counter and walks west toward the hearth.",
                "Amy draws ale from the barrel into Goblin's chipped mug.",
                "Amy carries the mug back toward Goblin at the counter.",
                "Amy sets the refilled mug before Goblin.",
            ],
            "Amy stands beside the east counter.",
        )
        payload, calls, physical_candidates, physical_contexts = self._run_pipeline(
            "Amy refills Goblin's chipped mug from the barrel beside the hearth.",
            creative,
            timed,
            physical_verdicts=[{"valid": True, "issue": ""}],
        )

        creative_call = next(
            call for call in calls if call[0] == "director_raw_scene_creative"
        )
        self.assertIsNone(creative_call[2].get("response_format"))
        self.assertEqual(creative_call[1][0]["role"], "system")
        self.assertIn("Sentences of actions", creative_call[1][0]["content"])
        self.assertNotIn("timestamp", creative_call[1][0]["content"].lower())
        self.assertNotIn("end continuity state", creative_call[1][0]["content"].lower())
        self.assertEqual(physical_candidates[0], creative)

        formatter_call = next(call for call in calls if call[0] == "director_raw_scene")
        creative_prompt = "\n".join(
            str(message.get("content", "")) for message in creative_call[1]
        )
        self.assertIn("<Subject 1>", creative_prompt)
        self.assertIn("<Picture 1>", creative_prompt)
        self.assertIn("SUBJECT LOCATIONS (WorldState)", creative_prompt)
        self.assertIn("STATIC SETTING AUTHORITY", creative_prompt)
        self.assertEqual(
            physical_contexts[0]["static_setting_description"], STATIC_TAVERN
        )
        formatter_prompt = "\n".join(
            str(message.get("content", "")) for message in formatter_call[1]
        )
        self.assertIn(creative, formatter_prompt)
        self.assertIn("Goblin", formatter_prompt)
        self.assertEqual(payload["raw_scene"], timed)

    def test_stage_prompts_and_profile_match_the_split_contract(self):
        self.assertEqual(
            minimax.LLM_PURPOSE_PROFILES["director_raw_scene_creative"],
            minimax.SMART_CREATIVE_LLM_SETTINGS,
        )
        self.assertEqual(
            minimax.DIRECTOR_RAW_SCENE_CREATIVE_SYSTEM_TEMPLATE.format(
                segment_length="8"
            ),
            (
                "You are to expand on a single BEAT.  The actions must be able "
                "to fit within an 8 second video clip.\n\n"
                "JOB\n"
                "- CURRENT BEAT is the story authority for what happens now and the scene to stage in this clip.\n"
                "- PREVIOUS SHOT END is frame-0 context for continuation shots. Start there without replaying it; if it conflicts with CURRENT BEAT, CURRENT BEAT wins.\n"
                "- CANONICAL STARTING CHARACTER FACTS, when provided, are authoritative identity/appearance facts. Establish applicable visible facts for characters already present in CURRENT BEAT or ASSIGNED SOURCE; never introduce a character only to show a canonical fact.\n\n"
                "WRITE THE SCENE\n"
                "- Show CURRENT BEAT clearly with concrete visible/audible action.\n"
                "- Complete every finite action explicitly assigned by CURRENT BEAT, including the required result for every named person or target, before the final continuity state.\n"
                "- Add only details needed to physically connect or clearly show CURRENT BEAT.\n\n"
                "RETURN\n"
                "Sentences of actions that occur in the scene separated by new lines.\n"
            ),
        )
        validator_messages = minimax.build_director_raw_scene_physical_messages(
            "Amy crosses the room.", "Amy crosses the room."
        )
        self.assertEqual(
            validator_messages[0]["content"],
            "Validate only subject movement in the RAW SCENE.  Update subject "
            "positions after each sentence internally and determine if the "
            "following sentence's actions, whether movement or not, can occur "
            "spatially.\n\nReturn only one JSON object with boolean valid and "
            "string issue. Report only the first concrete problem.",
        )

    def test_west_wall_barrel_route_is_repaired_before_timed_formatting(self):
        beat = "Amy refills Goblin's chipped mug from the barrel beside the hearth."
        impossible = (
            "Amy remains at the east counter and reaches across the room to pour "
            "from the barrel on the west wall into Goblin's mug."
        )
        corrected = (
            "Amy leaves the east counter, walks to the west-wall barrel beside "
            "the hearth, refills Goblin's mug, then carries it back to the counter."
        )
        issue = "Amy cannot pour from the west-wall barrel while remaining at the east counter."
        final_timed = _timed_raw(
            [
                "Amy leaves the east counter and walks west toward the hearth.",
                "Amy refills Goblin's mug from the west-wall barrel.",
                "Amy carries the mug east back to the counter.",
                "Amy sets the refilled mug before Goblin.",
            ]
        )
        payload, calls, physical_candidates, physical_contexts = self._run_pipeline(
            beat,
            impossible,
            final_timed,
            repair_scenes=[corrected],
            physical_verdicts=[
                {"valid": False, "issue": issue},
                {"valid": True, "issue": ""},
                {"valid": True, "issue": ""},
            ],
        )
        self.assertEqual(physical_candidates[:3], [impossible, corrected, final_timed])
        self.assertTrue(all(
            context["static_setting_description"] == STATIC_TAVERN
            for context in physical_contexts
        ))
        repair_call = next(
            call for call in calls if call[0] == "director_raw_scene_repair"
        )
        repair_prompt = "\n".join(
            str(message.get("content", "")) for message in repair_call[1]
        )
        self.assertIn(impossible, repair_prompt)
        self.assertIn(issue, repair_prompt)
        self.assertIn("west wall", repair_prompt.lower())
        self.assertEqual(payload["raw_scene"], final_timed)

    def test_ladle_transfer_repair_preserves_prop_identity(self):
        beat = "Amy uses a ladle to refill Goblin's chipped mug from the barrel."
        bad = (
            "Amy lifts the cleaning cloth and uses it as a ladle to scoop ale "
            "from the barrel into Goblin's mug."
        )
        corrected = (
            "Amy keeps the cleaning cloth in her other hand, takes the ladle "
            "from beside the barrel, and pours ale into Goblin's mug."
        )
        issue = "The cleaning cloth changes identity into the ladle; preserve both props."
        timed = _timed_raw(
            [
                "Amy takes the ladle beside the barrel.",
                "Amy dips the ladle into the barrel and refills Goblin's mug.",
                "Amy returns the ladle beside the barrel.",
                "Amy keeps the cleaning cloth in her hand.",
            ]
        )
        payload, calls, physical_candidates, _physical_contexts = self._run_pipeline(
            beat,
            bad,
            timed,
            repair_scenes=[corrected],
            physical_verdicts=[
                {"valid": False, "issue": issue},
                {"valid": True, "issue": ""},
                {"valid": True, "issue": ""},
            ],
        )
        self.assertEqual(physical_candidates[:3], [bad, corrected, timed])
        repair_call = next(
            call for call in calls if call[0] == "director_raw_scene_repair"
        )
        repair_prompt = "\n".join(
            str(message.get("content", "")) for message in repair_call[1]
        )
        self.assertIn("cleaning cloth", repair_prompt)
        self.assertIn("ladle", repair_prompt)
        self.assertIn(issue, repair_prompt)
        self.assertNotIn("uses it as a ladle", payload["raw_scene"])

    def test_gratuitous_furniture_climb_is_repaired_away(self):
        beat = "Amy wipes the counter with a damp cloth."
        bad = "Amy climbs onto a stool to wipe the counter."
        corrected = "Amy stands on the floor beside the counter and wipes it."
        issue = "The climb is unnecessary; the counter is reachable from the floor."
        timed = _timed_raw(
            [
                "Amy stands on the floor beside the counter.",
                "Amy wipes the counter with a damp cloth.",
                "Amy continues wiping its surface.",
                "Amy lowers the cloth beside the counter.",
            ]
        )
        payload, _calls, physical_candidates, _physical_contexts = self._run_pipeline(
            beat,
            bad,
            timed,
            repair_scenes=[corrected],
            physical_verdicts=[
                {"valid": False, "issue": issue},
                {"valid": True, "issue": ""},
                {"valid": True, "issue": ""},
            ],
        )
        self.assertEqual(physical_candidates[:3], [bad, corrected, timed])
        self.assertNotIn("climbs onto a stool", payload["raw_scene"])

    def test_downstream_formatter_physical_error_is_repaired_and_revalidated(self):
        beat = "Amy wipes the counter from the floor beside it."
        accepted_creative = "Amy stands on the floor and wipes the counter."
        formatter_error = _timed_raw(
            [
                "Amy climbs onto the stool to reach the counter.",
                "Amy wipes the counter.",
                "Amy leans over the counter to finish wiping.",
                "Amy remains standing on the stool.",
            ],
            "Amy stands on the stool beside the counter.",
        )
        repaired_formatted = _timed_raw(
            [
                "Amy remains on the floor beside the counter.",
                "Amy wipes the counter from the floor.",
                "Amy moves along the counter while wiping.",
                "Amy finishes wiping and lowers the cloth.",
            ]
        )
        issue = "The formatted scene adds an unnecessary stool climb absent from accepted RAW."
        payload, calls, physical_candidates, _physical_contexts = self._run_pipeline(
            beat,
            accepted_creative,
            formatter_error,
            repair_scenes=[repaired_formatted],
            physical_verdicts=[
                {"valid": True, "issue": ""},
                {"valid": False, "issue": issue},
                {"valid": True, "issue": ""},
            ],
        )
        self.assertEqual(
            physical_candidates[:3],
            [accepted_creative, formatter_error, repaired_formatted],
        )
        self.assertEqual(payload["raw_scene"], repaired_formatted)
        repair_call = next(
            call for call in calls if call[0] == "director_raw_scene_repair"
        )
        repair_prompt = "\n".join(
            str(message.get("content", "")) for message in repair_call[1]
        )
        self.assertIn(formatter_error, repair_prompt)
        self.assertIn(issue, repair_prompt)


if __name__ == "__main__":
    unittest.main()
