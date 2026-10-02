import unittest
import json
import re
from unittest import mock

import minimax


def segment_bundle():
    return {
        "segment": 1,
        "active_beat_id": 1,
        "current_duration": 6.0,
        "messages": [{"role": "user", "content": "Direct segment 1."}],
        "conditioning_mode": "initial",
        "opening_state_sha256": "opening-hash",
    }


def formatter_response(description):
    """A Request 2 H3 formatter reply with the required response fields."""
    description = str(description)
    if re.search(r"At 00:\d\d\.\d{3},", description) and not re.search(
        r"At 00:0[4-9]\.\d{3},", description
    ):
        description += " At 00:04.500, The action settles into its final visible state."
    return {
        "subject_genders": {},
        "detailed_description": description,
        "overall_soundscape": "Room tone.",
        "non_diegetic_music": "N/A",
    }


def director_response(raw_scene, beat_complete=True):
    """A structurally valid Request 1 reply for unit tests."""
    scene = str(raw_scene).strip()
    if not scene.startswith("At "):
        scene = "At 00:00.000, " + scene
    if not re.search(r"At 00:0[4-9]\.\d{1,3},", scene):
        scene += "\nAt 00:04.500, The action settles into its final visible state."
    if "End continuity state:" not in scene:
        scene += "\nEnd continuity state: The described action has reached its final visible state."
    return {
        "raw_scene": scene,
        "finite_activity_complete": beat_complete,
        "named_beneficiaries_complete": beat_complete,
        "activity_tools_settled": beat_complete,
        "beat_complete": beat_complete,
    }


def pipeline_llm_side_effect(
    non_audio_responses,
    *,
    soundscape="Room tone.",
    music="N/A",
):
    """Return current Director pipeline responses without coupling unrelated tests."""
    queued = iter(non_audio_responses)

    def respond(*args, **kwargs):
        purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
        if purpose == "director_h3_soundscape":
            return {"overall_soundscape": soundscape}
        if purpose == "director_h3_music":
            return {"non_diegetic_music": music}
        if purpose == "director_raw_scene_pronoun_resolution":
            messages = args[0] if args else []
            user_text = str(messages[-1].get("content", "")) if messages else ""
            raw = user_text.split("RAW SCENE\n", 1)[-1].split(
                "\n\nReturn {", 1
            )[0].strip()
            return {"raw_scene": raw}
        if purpose == "director_raw_scene_subject_resolution":
            messages = args[0] if args else []
            user_text = str(messages[-1].get("content", "")) if messages else ""
            raw = user_text.split("RAW SCENE\n", 1)[-1].split(
                "\n\nReturn raw_scene", 1
            )[0].strip()
            return {"raw_scene": raw, "subject_names": []}
        return next(queued)

    return respond


def non_audio_llm_calls(request):
    """Return request calls except the two independent post-RAW audio jobs."""
    return [
        call
        for call in request.call_args_list
        if str((call.kwargs.get("history_metadata") or {}).get("purpose", ""))
        not in {"director_h3_soundscape", "director_h3_music"}
    ]


class DirectorMicroPromptPipelineTests(unittest.TestCase):

    def test_h3_soundscape_prompt_is_extraction_only(self):
        messages = minimax.build_h3_soundscape_messages(
            "At 00:01.000, Amy closes the door."
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Extract only the overall soundscape", text)
        self.assertIn("only sounds a microphone could hear", text)
        self.assertIn("Omit lighting", text)
        self.assertIn("Do not invent optional or merely plausible sounds", text)
        self.assertIn("Do not rewrite", text)
        self.assertNotIn("non_diegetic_music", text)
        self.assertIn("Return exactly overall_soundscape", text)

    def test_h3_music_prompt_is_generation_only(self):
        messages = minimax.build_h3_music_messages(
            "At 00:01.000, Amy closes the door.",
            conditioning_mode="continuation",
            previous_music="Soft warm piano, calm and understated.",
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Generate only the non-diegetic music", text)
        self.assertIn("PREVIOUS MUSIC", text)
        self.assertIn("Soft warm piano, calm and understated.", text)
        self.assertIn("Continue the previous musical state", text)
        self.assertIn("Do not name characters, narrate scene actions", text)
        self.assertIn("or synchronize the score to specific actions", text)
        self.assertIn("Return one musical cue sentence", text)
        self.assertIn("at most 24", text)
        self.assertIn("Do not name characters", text)
        self.assertNotIn("overall_soundscape", text)
        self.assertIn("continues from <Video 1>", text)
        self.assertIn("Return exactly non_diegetic_music", text)

    def test_h3_soundscape_prompt_rejects_visual_only_facts(self):
        messages = minimax.build_h3_soundscape_messages(
            "At 00:01.000, sunlight crosses the table while Mira looks left."
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("only sounds a microphone could hear", text)
        self.assertIn("Omit lighting", text)
        self.assertIn("silent gestures", text)
        self.assertIn("pistol still fired", text)
        self.assertIn("Each listed item must itself name an audible event", text)
        self.assertIn("Do not turn motion verbs into sounds", text)
        self.assertIn("rising steam", text)

    @mock.patch("minimax.ask_llm")
    def test_audio_contract_retries_malformed_soundscape(self, ask_llm):
        ask_llm.side_effect = [
            director_response("Mark closes a door with a thud."),
            {"overall_soundscape": ":["},
            {"overall_soundscape": "door thud"},
            {"non_diegetic_music": "Sparse piano."},
        ]
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "door thud")
        sound_calls = [
            call for call in ask_llm.call_args_list
            if call.kwargs["history_metadata"]["purpose"] == "director_h3_soundscape"
        ]
        self.assertEqual(
            [call.kwargs["history_metadata"]["attempt"] for call in sound_calls],
            [1, 2],
        )

    def test_h3_soundscape_parser_rejects_na_when_raw_has_explicit_audio(self):
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result(
                {"overall_soundscape": "N/A"},
                raw_scene=(
                    "At 00:01.000, footsteps echo down the corridor. "
                    "At 00:03.000, a groan rattles the door."
                ),
            )

    def test_h3_soundscape_parser_allows_na_without_audio_cues(self):
        self.assertEqual(
            minimax.parse_h3_soundscape_result(
                {"overall_soundscape": "N/A"},
                raw_scene="At 00:01.000, Mira silently turns toward the window.",
            ),
            "N/A",
        )

    def test_h3_soundscape_parser_rejects_punctuation_only_output(self):
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result({
                "overall_soundscape": ":[",
            })

    def test_h3_music_parser_rejects_overlong_cue(self):
        overlong = " ".join(["music"] * 33)
        with self.assertRaises(ValueError):
            minimax.parse_h3_music_result({
                "non_diegetic_music": overlong,
            })

    def test_h3_audio_parsers_accept_only_their_single_field(self):
        soundscape = minimax.parse_h3_soundscape_result({
            "overall_soundscape": "Door slam.",
        })
        music = minimax.parse_h3_music_result({
            "non_diegetic_music": "Low strings.",
        })
        self.assertEqual(soundscape, "Door slam.")
        self.assertEqual(music, "Low strings.")
        with self.assertRaises(ValueError):
            minimax.parse_h3_soundscape_result({
                "overall_soundscape": "Door slam.",
                "non_diegetic_music": "Low strings.",
            })
        with self.assertRaises(ValueError):
            minimax.parse_h3_music_result({
                "overall_soundscape": "Door slam.",
                "non_diegetic_music": "Low strings.",
            })

    def test_raw_subject_resolution_prompt_is_post_raw_and_narrow(self):
        messages = minimax.build_director_raw_subject_resolution_messages(
            (
                "At 00:01.000, a guard enters.\n"
                "At 00:04.000, another guard blocks the door."
            ),
            "<Subject 1> is Mara.\n<Subject 2> is Guard1, continued from <Video 1>.",
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("unnamed foreground animate identities", text)
        self.assertIn("finalized timed RAW scene", text)
        self.assertIn("Keep already-named Subjects unchanged", text)
        self.assertIn("Guard1 or Creature1", text)
        self.assertIn("Reuse a KNOWN SUBJECT name", text)
        self.assertIn("Do not label interchangeable background crowds/groups", text)
        self.assertIn("KNOWN SUBJECTS", text)

    def test_raw_subject_resolution_accepts_only_identity_labeling(self):
        original = (
            "At 00:01.000, a guard enters the room.\n"
            "At 00:04.000, another guard blocks the door.\n"
            "End continuity state: both guards remain in the room."
        )
        resolved = (
            "At 00:01.000, Guard1 enters the room.\n"
            "At 00:04.000, Guard2 blocks the door.\n"
            "End continuity state: Guard1 and Guard2 remain in the room."
        )
        request = mock.Mock(return_value={
            "raw_scene": resolved,
            "subject_names": ["Guard1", "Guard2"],
        })
        result, names = minimax.resolve_director_raw_scene_subjects(
            original,
            "<Subject 1> is Mara.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(result, resolved)
        self.assertEqual(names, ["Guard1", "Guard2"])
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "director_raw_scene_subject_resolution",
        )

    def test_raw_subject_resolution_rejects_timestamp_drift(self):
        original = (
            "At 00:01.000, a guard enters.\n"
            "At 00:04.000, another guard blocks the door."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:01.000, Guard1 enters.\n"
                "At 00:05.000, Guard2 blocks the door."
            ),
            "subject_names": ["Guard1", "Guard2"],
        })
        with self.assertRaisesRegex(ValueError, "changed timestamps"):
            minimax.resolve_director_raw_scene_subjects(
                original,
                "",
                llm_request=request,
                segment_seconds=6.0,
            )

    def test_raw_pronoun_resolution_prompt_is_narrow(self):
        messages = minimax.build_director_pronoun_resolution_messages(
            (
                "At 00:01.000, Amy pushes Will and Amber toward the closet.\n"
                "At 00:04.000, she pushes them inside.\n"
                "End continuity state: they are inside the closet."
            ),
            (
                "<Subject 1> is Amy.\n"
                "<Subject 2> is Will.\n"
                "<Subject 3> is Amber."
            ),
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Change only the pronoun itself", text)
        self.assertIn("especially she, he, they, him, her, them", text)
        self.assertIn("replace only clear personal subject/object pronouns", text)
        self.assertIn("Prefer names for standalone they/them", text)
        self.assertIn("keep 'her hand', 'his collar', and 'their bowls' as written", text)
        self.assertIn("Do not add, remove, combine, split, or reinterpret actions", text)

    def test_raw_pronoun_resolution_accepts_name_only_rewrite(self):
        original = (
            "At 00:01.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, she pushes them into the closet.\n"
            "End continuity state: they are inside the closet."
        )
        resolved_timed = (
            "At 00:01.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, Amy pushes Will and Amber into the closet."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            resolved_timed + "\nEnd continuity state: they are inside the closet.",
        )
        self.assertEqual(
            request.call_args.kwargs["history_metadata"]["purpose"],
            "director_raw_scene_pronoun_resolution",
        )

    def test_raw_pronoun_resolution_preserves_clear_local_possessives(self):
        original = (
            "At 00:01.000, she looks at Will and touches her palm.\n"
            "At 00:04.500, Will gives her their bowls.\n"
            "End continuity state: Amy stands beside Will."
        )
        resolved_timed = (
            "At 00:01.000, Amy looks at Will and touches her palm.\n"
            "At 00:04.500, Will gives Amy their bowls."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertEqual(
            result,
            resolved_timed + "\nEnd continuity state: Amy stands beside Will.",
        )

    def test_raw_pronoun_resolution_logs_replacements(self):
        original = (
            "At 00:01.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, she pushes them into the closet.\n"
            "End continuity state: they are inside the closet."
        )
        resolved_timed = (
            "At 00:01.000, Amy grabs Will and Amber.\n"
            "At 00:04.500, Amy pushes Will and Amber into the closet."
        )
        request = mock.Mock(return_value={"raw_scene": resolved_timed})
        with mock.patch("builtins.print") as printer:
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy. <Subject 2> is Will. <Subject 3> is Amber.",
                llm_request=request,
                segment_seconds=6.0,
            )
        output = "\n".join(
            str(call.args[0]) for call in printer.call_args_list if call.args
        )
        self.assertIn("Checking pronouns segment:", output)
        self.assertIn("replaced", output)
        self.assertIn("Amy pushes Will and Amber", output)

    def test_raw_pronoun_resolution_preserves_end_state_exactly(self):
        original = (
            "At 00:01.000, Amy looks at Will.\n"
            "At 00:04.500, she waves to him.\n"
            "End continuity state: she stands beside him."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:01.000, Amy looks at Will.\n"
                "At 00:04.500, Amy waves to Will."
            )
        })
        result = minimax.resolve_director_raw_scene_pronouns(
            original,
            "<Subject 1> is Amy. <Subject 2> is Will.",
            llm_request=request,
            segment_seconds=6.0,
        )
        self.assertTrue(
            result.endswith("End continuity state: she stands beside him.")
        )
        sent = request.call_args.args[0][-1]["content"]
        self.assertNotIn("End continuity state:", sent)

    def test_raw_pronoun_resolution_rejects_timestamp_drift(self):
        original = (
            "At 00:01.000, Amy grabs Will.\n"
            "At 00:04.500, she pushes him into the closet.\n"
            "End continuity state: Will is inside."
        )
        request = mock.Mock(return_value={
            "raw_scene": (
                "At 00:01.000, Amy grabs Will.\n"
                "At 00:05.000, Amy pushes Will into the closet."
            )
        })
        with self.assertRaisesRegex(ValueError, "changed timestamps"):
            minimax.resolve_director_raw_scene_pronouns(
                original,
                "<Subject 1> is Amy. <Subject 2> is Will.",
                llm_request=request,
                segment_seconds=6.0,
            )

    def test_raw_scene_coherence_prompt_allows_staging_but_checks_order(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy pushes Will into the closet and closes the door.",
            (
                "At 00:02.000, Amy closes the closet door.\n"
                "At 00:04.000, Will enters the closet."
            ),
        )
        text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("Harmless invented staging is allowed", text)
        self.assertIn("closing a barrier before someone passes through it", text)
        self.assertIn("Read the timed actions literally in order", text)


    def test_request_one_retries_physically_incoherent_raw_scene(self):
        bundle = segment_bundle()
        bundle["current_beat_text"] = (
            "Amy pushes Will into the closet and closes the door behind him."
        )
        bad = director_response(
            "At 00:01.000, Amy closes the closet door.\n"
            "At 00:04.500, Will steps into the closet."
        )
        good = director_response(
            "At 00:01.000, Will steps into the closet.\n"
            "At 00:04.500, Amy closes the closet door behind him."
        )
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            bad,
            good,
        ]))
        coherence = mock.Mock(side_effect=[
            {"valid": False, "issue": "The door closes before Will enters."},
            {"valid": True, "issue": ""},
        ])
        with (
            mock.patch("minimax.ask_llm", request),
            mock.patch(
                "minimax.validate_director_raw_scene_coherence",
                coherence,
            ),
            mock.patch("builtins.print"),
        ):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        semantic_calls = non_audio_llm_calls(request)
        self.assertEqual(len(semantic_calls), 2)
        self.assertEqual(coherence.call_count, 2)
        self.assertIn("Will steps into the closet", payload["raw_scene"])
        request_prompts = [
            call.args[0][-1]["content"]
            for call in semantic_calls
            if call.args and isinstance(call.args[0], list) and call.args[0]
            and isinstance(call.args[0][-1], dict)
        ]
        self.assertTrue(any(
            "Fix this physical/action-order problem" in prompt
            and "door closes before Will enters" in prompt
            for prompt in request_prompts
        ))

    def test_request_one_completion_self_report_is_non_blocking(self):
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("Mark starts the action.", beat_complete=False),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 1)
        self.assertFalse(payload["request1_result"]["beat_complete"])
        self.assertIn("Mark starts the action.", payload["raw_scene"])


    def test_request_one_retries_only_when_raw_scene_is_unusable(self):
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            {"raw_scene": ""},
            director_response("Mark completes the action."),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 2)
        self.assertIn("Mark completes the action.", payload["raw_scene"])

    def test_request_one_retries_missing_end_state_marker(self):
        malformed = {
            "raw_scene": (
                "At 00:00.000, Mark reaches for the latch.\n"
                "At 00:04.500, Mark closes the hatch."
            ),
            "finite_activity_complete": True,
            "named_beneficiaries_complete": True,
            "activity_tools_settled": True,
            "beat_complete": True,
        }
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            malformed,
            director_response("Mark closes the hatch."),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 2)
        self.assertIn("End continuity state:", payload["raw_scene"])

    def test_request_one_does_not_repair_semantic_omission_during_baseline(self):
        bundle = segment_bundle()
        bundle["messages"] = [{
            "role": "user",
            "content": (
                "CURRENT BEAT: Amy opens a hidden panel and retrieves three tools.\n"
                "NEXT BEAT: Amy exits the room."
            ),
        }]
        omitted_scene = "Amy opens the panel and retrieves only two tools."
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response(omitted_scene, beat_complete=False),
        ]))
        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle, [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(len(non_audio_llm_calls(request)), 1)
        self.assertIn("only two tools", payload["raw_scene"])

    def test_request_two_result_does_not_contain_completion_metadata(self):
        parsed = minimax.parse_h3_formatter_result(formatter_response("[Shot 1] Mark waits."))
        self.assertNotIn("completed_beat_ids", parsed)

    def test_missing_reported_completion_does_not_advance_beat_plan(self):
        with self.assertRaisesRegex(RuntimeError, "refusing to advance"):
            minimax.apply_reported_beat_completions(
                ["Mark completes the action."],
                set(),
                [],
                1,
            )

    def test_h3_action_preservation_prompt_ignores_harmless_incidental_detail(self):
        messages = minimax.build_h3_action_preservation_messages(
            (
                "A deep thud sounds from the front door as it opens slightly; "
                "a small crack appears at the gap."
            ),
            "A deep thud sounds from the front door as it opens slightly.",
            current_beat="A thud at the front door interrupts the kitchen.",
        )
        prompt = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("CURRENT BEAT", prompt)
        self.assertIn("Do not fail harmless decorative clauses", prompt)
        self.assertIn("small crack appears", prompt)

    def test_h3_formatter_repairs_named_dialogue_speaker_id(self):
        parsed = minimax.parse_h3_formatter_result(
            {
                "subject_genders": {},
                "detailed_description": (
                    '[Shot 1] Will calls out (S1) <d>[English] Amy!</d>'
                ),
                "overall_soundscape": "Will calls out.",
                "non_diegetic_music": "N/A",
            },
            subject_definitions=(
                "<Subject 1> is Amy, a woman.\n"
                "<Subject 2> is Will, a boy."
            ),
        )
        self.assertIn("Will calls out (S2) <d>[English] Amy!</d>", parsed["detailed_description"])
        self.assertNotIn("Will calls out (S1)", parsed["detailed_description"])

    def test_h3_formatter_parses_subject_genders(self):
        parsed = minimax.parse_h3_formatter_result(
            "subject_genders: {\"Werewolf\": \"unknown\", "
            "\"Captain\": \"male\"}\n\n"
            "detailed_description: [Shot 1] Captain enters.\n\n"
            "overall_soundscape: Footsteps.\n\n"
            "non_diegetic_music: N/A"
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Werewolf": "unknown", "Captain": "male"},
        )

    def test_subject_gender_aliases_collapse_to_one_canonical_name(self):
        parsed = minimax.parse_h3_formatter_result(
            {
                "subject_genders": {
                    "<Subject 1>": "female",
                    "<Subject 2>": "male",
                    "<Subject 3>": "male",
                    "Jill": "female",
                    "Ben": "male",
                    "Frank": "male",
                },
                "detailed_description": "[Shot 1] Jill, Ben, and Frank enter.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            subject_definitions=(
                "<Subject 1> is Jill, a woman referenced in <Picture 1>.\n"
                "<Subject 2> is Ben, a man referenced in <Picture 2>.\n"
                "<Subject 3> is Frank, a man referenced in <Picture 3>."
            ),
        )

        self.assertEqual(
            parsed["subject_genders"],
            {"Jill": "female", "Ben": "male", "Frank": "male"},
        )

    def test_h3_formatter_parses_json_text_response(self):
        parsed = minimax.parse_h3_formatter_result(
            json.dumps({
                "subject_genders": {"Werewolf": "unknown"},
                "detailed_description": "[Shot 1] Werewolf enters.",
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            })
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["subject_genders"], {"Werewolf": "unknown"})

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_does_not_add_non_speaking_subject_ids(
        self, ask_llm
    ):
        bundle = segment_bundle()
        bundle["subject_definitions"] = (
            "<Subject 1> is Alice, referenced in <Picture 1>."
        )
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response("Alice walks over to the window."),
        ])

        payload = minimax.request_segment_llm(
            bundle,
            [],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        description = payload["llm_result"]["detailed_description"]
        self.assertIn("Alice walks over to the window.", description)
        self.assertNotIn("Alice (S1)", description)

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_h3_response_format_repairs_malformed_json(self, post, _history):
        malformed = mock.Mock()
        malformed.status_code = 200
        malformed.raise_for_status.return_value = None
        malformed.json.return_value = {
            "choices": [{
                "message": {
                    "content": (
                        '{"subject_genders": {}, '
                        '"detailed_description": "[Shot 1] Amy enters.", '
                        '"overall_soundscape": "Footsteps.", '
                        '"non_diegetic_music": "N/A"'
                    )
                }
            }]
        }
        repaired = mock.Mock()
        repaired.status_code = 200
        repaired.raise_for_status.return_value = None
        repaired.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "subject_genders": {"Amy": "female"},
                        "detailed_description": "[Shot 1] Amy enters.",
                        "overall_soundscape": "Footsteps.",
                        "non_diegetic_music": "N/A",
                    })
                }
            }]
        }
        post.side_effect = [malformed, repaired]

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            retry_delay=0,
            response_format=minimax.H3_FORMATTER_RESPONSE_FORMAT,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertEqual(result["subject_genders"], {"Amy": "female"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["response_format"],
            minimax.H3_FORMATTER_RESPONSE_FORMAT,
        )
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])

    def test_h3_formatter_parses_markdown_labels(self):
        parsed = minimax.parse_h3_formatter_result(
            "### subject_genders: {}\n\n"
            "### Detailed Description: [Shot 1] Werewolf enters.\n\n"
            "### Overall Soundscape: Footsteps.\n\n"
            "### Non-Diegetic Music: N/A"
        )

        self.assertEqual(parsed["detailed_description"], "[Shot 1] Werewolf enters.")
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")

    def test_append_h3_description_has_one_opener_and_no_leading_camera_move(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 2] Live-action, cinematic, The camera pushes in "
                    "toward Mark as Mark opens the door. At 00:02.000, the "
                    "camera pans right as Jill enters."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Mark, referenced in <Picture 1>.",
            segment_number=2,
            conditioning_mode="continuation",
        )

        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:",
            1,
        )[0]
        self.assertTrue(
            description.startswith(
                "[Shot 1] Live-action, cinematic, continues from <Video 1>."
                " Mark opens the door."
            )
        )
        self.assertEqual(description.count("Live-action, cinematic"), 1)
        self.assertNotIn("camera pushes in", description.lower())
        self.assertIn("camera pans right", description.lower())

    def test_formatter_metadata_never_reaches_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "**subject_genders:**\n"
                    "{\n"
                    '  "Amy": "female"\n'
                    "}\n\n"
                    "[Shot 1] Amy walks."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "reference_alignment": (
                    'subject_genders: {"Amy": "female"}\n'
                    "Reference Image 1 establishes Amy's identity."
                ),
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("subject_genders", prompt)
        self.assertNotIn('{"Amy": "female"}', prompt)
        self.assertIn("[Shot 1] Amy walks.", prompt)
        self.assertIn("Reference Image 1 establishes Amy's identity.", prompt)

    def test_mistral_asterisks_never_reach_final_h3_prompt(self):
        formatted = minimax.format_mistral_prompt(
            {
                "detailed_description": "*[Shot 1]* **Amy** walks.",
                "overall_soundscape": "*Footsteps* echo.",
                "non_diegetic_music": "**N/A**",
                "completed_beat_ids": [1],
            },
            {
                "segment_number": 1,
                "segment_duration": 6.0,
                "completed_beat_ids": [],
            },
        )
        prompt = minimax.build_h3_prompt(
            formatted,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("*", prompt)

    def test_mistral_asterisks_in_continuity_never_reach_final_h3_prompt(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Amy waits by the door.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            previous_state="*Amy remains by the door.*",
            segment_number=2,
            conditioning_mode="clean_refresh",
            continuity_state={
                "subjects": {
                    "Amy": {
                        "subject_id": 1,
                        "name": "Amy",
                        "position": "*by the door*",
                        "wardrobe": ["**blue coat**"],
                    },
                },
            },
        )

        self.assertNotIn("*", prompt)

    def test_h3_formatter_parses_json_metadata_followed_by_markdown_fields(self):
        parsed = minimax.parse_h3_formatter_result(
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )

        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["overall_soundscape"], "Footsteps.")
        self.assertEqual(parsed["non_diegetic_music"], "N/A")
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})

    def test_multiple_fenced_formatter_blocks_do_not_reach_final_h3_prompt(self):
        raw = (
            "```ALIGNMENT\n"
            "Reference alignment: Amy's identity and the cabin remain consistent.\n"
            "```\n\n"
            "```H3\n"
            "detailed_description: [Shot 1] Amy enters the cabin.\n"
            "```\n\n"
            "```SOUND\n"
            "overall_soundscape: Footsteps on the wooden floor.\n"
            "```\n\n"
            "```MUSIC\n"
            "non_diegetic_music: Soft piano undercurrent.\n"
            "```"
        )

        parsed = minimax.parse_h3_formatter_result(raw)
        prompt = minimax.build_h3_prompt(
            parsed,
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            segment_number=1,
        )

        self.assertNotIn("```", prompt)
        self.assertIn("Reference alignment: Amy's identity and the cabin remain consistent.", prompt)
        self.assertIn("[Shot 1] Amy enters the cabin.", prompt)
        self.assertIn("Footsteps on the wooden floor.", prompt)
        self.assertIn("non_diegetic_music: Soft piano undercurrent.", prompt)

    def test_h3_component_sanitizer_removes_standalone_fence_lines_only(self):
        value = "Before\n```JSON\nInside\n```\nafter"

        self.assertEqual(
            minimax.sanitize_h3_prompt_component(value),
            "Before\nInside\nafter",
        )

    @mock.patch("minimax.append_prompt_history")
    @mock.patch("minimax.requests.post")
    def test_ask_llm_preserves_mixed_h3_response(self, post, _history):
        mixed = (
            "```json\n"
            '{\n  "subject_genders": {"Amy": "female"}\n}\n'
            "```\n\n"
            "---\n"
            "**detailed_description:**\n"
            "[Shot 1] Live-action, cinematic, Amy runs.\n\n"
            "---\n"
            "**overall_soundscape:**\n"
            "Footsteps.\n\n"
            "---\n"
            "**non_diegetic_music:** N/A"
        )
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": mixed}}]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "format this scene"}],
            max_retries=1,
            response_format=None,
            history_metadata={"purpose": "director_h3_formatter"},
        )

        self.assertIsInstance(result, str)
        parsed = minimax.parse_h3_formatter_result(result)
        self.assertEqual(
            parsed["detailed_description"],
            "[Shot 1] Live-action, cinematic, Amy runs.",
        )
        self.assertEqual(parsed["subject_genders"], {"Amy": "female"})


    def test_director_prompt_is_compact_creative_contract(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
        )
        self.assertIn("You are the creative director", prompt)
        self.assertIn("ASSIGNED SOURCE is the story authority", prompt)
        self.assertIn("CURRENT BEAT is the scene to stage", prompt)
        self.assertIn("Harmless local route or prop details are allowed", prompt)
        self.assertIn("Python will normalize minor timestamp formatting differences", prompt)
        self.assertNotIn("AUTHORITATIVE FINAL STATE CONTRACT", prompt)
        self.assertIn("finite_activity_complete", prompt)
        self.assertIn("beat_complete", prompt)
        self.assertLess(len(prompt), 3500)
    def test_director_raw_scene_rejects_early_timeline_completion(self):
        raw_scene = (
            "At 00:00.000, Alex reaches for the latch.\n"
            "At 00:01.300, Alex closes the hatch.\n"
            "End continuity state: Alex stands beside the closed hatch."
        )
        errors = minimax._director_raw_scene_structure_errors(
            raw_scene,
            segment_seconds=8,
        )
        self.assertTrue(errors)
        self.assertIn("too early", errors[0])
        self.assertIn("at or after 6s", errors[0])

    def test_director_raw_scene_accepts_final_quarter_timeline(self):
        raw_scene = (
            "At 00:00.000, Alex reaches for the latch.\n"
            "At 00:06.200, Alex closes the hatch.\n"
            "End continuity state: Alex stands beside the closed hatch."
        )
        self.assertEqual(
            minimax._director_raw_scene_structure_errors(
                raw_scene,
                segment_seconds=8,
            ),
            [],
        )

    def test_preserved_barrier_unspecified_means_unchanged(self):
        issue = minimax.compare_director_barrier_state(
            {
                "barrier": "kitchen door window",
                "expected": "BROKEN",
                "source_state": "broken",
                "preserved": True,
            },
            "UNSPECIFIED",
        )
        self.assertEqual(issue, "")

    def test_director_final_state_contract_allows_small_route_details(self):
        base_messages = [
            {"role": "system", "content": "director"},
            {"role": "user", "content": "base"},
        ]
        bundle = {
            "segment": 2,
            "current_duration": 8,
            "conditioning_mode": "continuation",
            "messages": base_messages,
            "current_beat_text": "Amy moves Will and Amber into the basement.",
            "assigned_source": "Amy gets Will and Amber into the basement.",
            "assigned_state_effects": [
                {"op": "set_location", "entity": "Will", "value": "basement"},
                {"op": "set_location", "entity": "Amber", "value": "basement"},
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "contained",
                },
                {
                    "op": "set_containment",
                    "entity": "Amber",
                    "container": "basement",
                    "value": "contained",
                },
                {"op": "set_barrier_state", "entity": "door", "value": "locked"},
            ],
            "opening_state": (
                'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
                '{"characters":{"Amy":{"location":"home"},'
                '"Will":{"location":"home"},"Amber":{"location":"home"}},'
                '"environment":{"barriers":{"door":{"status":"open"}}}}'
            ),
            "registry_state": {"subjects": {}},
            "subject_definitions": "",
        }
        topology = minimax.build_director_barrier_topology_contract(
            bundle["assigned_state_effects"],
            "",
            bundle["assigned_source"],
            bundle["current_beat_text"],
            bundle["opening_state"],
        )
        binding = minimax.build_director_barrier_binding_contract(
            bundle["assigned_state_effects"]
        )
        self.assertTrue(topology)
        self.assertEqual(binding["destination"], "basement")
        route_line = (
            f"- People entering {binding['destination']} must use that "
            f"{binding['entity']}. Small route details are okay."
        )
        self.assertIn("Small route details are okay", route_line)

    def test_assigned_barrier_unspecified_still_fails(self):
        issue = minimax.compare_director_barrier_state(
            {
                "barrier": "kitchen door window",
                "expected": "BROKEN",
                "source_state": "broken",
            },
            "UNSPECIFIED",
        )
        self.assertIn("must end broken", issue)

    def test_validation_prompt_checks_scope_creep_into_exact_next_beat(self):
        messages = minimax.build_director_continuity_validation_messages(
            opening_state={},
            active_beat_text="Amy opens the gate.",
            detailed_description="Amy opens the gate and enters the vault.",
            segment_number=1,
            next_beat_text="Amy enters the vault.",
        )

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("NEXT BEAT\nAmy enters the vault.", combined)
        self.assertIn("next_beat_scope_creep", combined)
        self.assertIn("materially performs, begins, reveals", combined)

        parsed = minimax.parse_director_continuity_validation({
            "valid": False,
            "issues": [{
                "type": "next_beat_scope_creep",
                "problem": "The candidate enters the vault one beat early.",
            }],
        })
        self.assertEqual(parsed["issues"][0]["type"], "next_beat_scope_creep")

    @mock.patch("minimax.validate_mistral_prompt")
    @mock.patch("minimax.format_mistral_prompt")
    @mock.patch("minimax.request_valid_mistral_prompt", create=True)
    @mock.patch("minimax.ask_llm")

    def test_segment_llm_runs_raw_soundscape_music_without_legacy_seams(
        self,
        ask_llm,
        legacy_director,
        formatter,
        validator,
    ):
        raw_scene = (
            "Mark enters—quietly in a white T-shirt—and reacts to the environment."
        )
        ask_llm.side_effect = pipeline_llm_side_effect(
            [director_response(raw_scene)],
            soundscape="Quiet room tone.",
            music="Low restrained strings.",
        )

        payload = minimax.request_segment_llm(
            segment_bundle(),
            ["Mark confronts the Duchess, Cook, piglets, and Cheshire Cat."],
            "run-id",
            {"source_sha256": "source-hash"},
        )

        self.assertEqual(ask_llm.call_count, 3)
        legacy_director.assert_not_called()
        formatter.assert_not_called()
        validator.assert_not_called()

        purposes = [
            call.kwargs["history_metadata"]["purpose"]
            for call in ask_llm.call_args_list
        ]
        self.assertEqual(
            purposes,
            [
                "director_raw_scene",
                "director_h3_soundscape",
                "director_h3_music",
            ],
        )
        self.assertEqual(
            ask_llm.call_args_list[1].kwargs["response_format"],
            minimax.H3_SOUNDSCAPE_RESPONSE_FORMAT,
        )
        self.assertEqual(
            ask_llm.call_args_list[2].kwargs["response_format"],
            minimax.H3_MUSIC_RESPONSE_FORMAT,
        )
        self.assertIn(
            "enters—quietly in a white T-shirt",
            payload["llm_result"]["detailed_description"],
        )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Quiet room tone.")
        self.assertEqual(
            payload["llm_result"]["non_diegetic_music"],
            "Low restrained strings.",
        )
        self.assertEqual(payload["h3_mode"], "T2VA")

    def test_combined_continuity_avoids_llm_host_schema_rejection(self):
        llm_request = mock.Mock(side_effect=[
            {"subject": {"name": "Amy"}},
        ])

        minimax.request_combined_continuity(
            "A full scene description.",
            {"environment": {"location": "bedroom"}},
            llm_request=llm_request,
            history_metadata={"run_id": "r1"},
            content_attempts=1,
            defer_opening=True,
        )

        combined_call = llm_request.call_args_list[0]
        self.assertIsNone(combined_call.kwargs["response_format"])


    def test_segment_llm_carries_request_one_completion_claim(self):
        bundle = segment_bundle()
        bundle["active_beat_id"] = None
        request = mock.Mock(side_effect=pipeline_llm_side_effect([
            director_response("A quiet scene."),
        ]))

        with mock.patch("minimax.ask_llm", request), mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertNotIn("completed_beat_ids", payload["llm_result"])
        self.assertTrue(payload["request1_result"]["beat_complete"])

    @mock.patch("minimax.ask_llm")

    def test_audio_field_failures_fall_back_independently(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return {"unexpected": "bad field"}
            if purpose == "director_h3_music":
                return {"non_diegetic_music": "Soft low strings."}
            return director_response(raw_scene)

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(),
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(payload["llm_result"]["overall_soundscape"], "N/A")
        self.assertEqual(
            payload["llm_result"]["non_diegetic_music"],
            "Soft low strings.",
        )
        self.assertIn(
            "Mark enters the room quietly.",
            payload["llm_result"]["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_uses_canonical_raw_timestamps(self, ask_llm):
        raw_scene = (
            "At 00:00.0, Mark enters the room.\n"
            "At 00:04.500, Mark looks toward the window."
        )
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response(raw_scene),
        ])
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        description = payload["llm_result"]["detailed_description"]
        self.assertIn("At 00:00.000, Mark enters the room.", description)
        self.assertIn("At 00:04.500, Mark looks toward the window.", description)

    @mock.patch("minimax.ask_llm")

    def test_python_h3_copy_preserves_raw_timestamps(self, ask_llm):
        raw_scene = "At 00:00.000, Mark enters the room."
        ask_llm.side_effect = pipeline_llm_side_effect([
            director_response(raw_scene),
        ])
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertIn(
            "At 00:00.000, Mark enters the room.",
            payload["llm_result"]["detailed_description"],
        )

    @mock.patch("minimax.ask_llm")

    def test_audio_generation_never_rewrites_raw_actions(self, ask_llm):
        raw_scene = (
            "At 00:00.000, Mark enters the room.\n"
            "At 00:04.500, Mark looks toward the window."
        )
        ask_llm.side_effect = pipeline_llm_side_effect(
            [director_response(raw_scene)],
            soundscape="Footsteps and quiet room tone.",
            music="Sparse strings.",
        )
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        description = payload["llm_result"]["detailed_description"]
        self.assertIn("Mark enters the room.", description)
        self.assertIn("Mark looks toward the window.", description)
        self.assertNotIn("Footsteps and quiet room tone.", description)

    @mock.patch("minimax.ask_llm")

    def test_soundscape_failure_does_not_block_music(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return ""
            if purpose == "director_h3_music":
                return {"non_diegetic_music": "Sparse piano."}
            return director_response(raw_scene)

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "N/A")
        self.assertEqual(payload["llm_result"]["non_diegetic_music"], "Sparse piano.")

    @mock.patch("minimax.ask_llm")

    def test_music_failure_does_not_block_soundscape(self, ask_llm):
        raw_scene = "Mark enters the room quietly."

        def respond(*args, **kwargs):
            purpose = str((kwargs.get("history_metadata") or {}).get("purpose", ""))
            if purpose == "director_h3_soundscape":
                return {"overall_soundscape": "Quiet room tone."}
            if purpose == "director_h3_music":
                return ""
            return director_response(raw_scene)

        ask_llm.side_effect = respond
        with mock.patch("builtins.print"):
            payload = minimax.request_segment_llm(
                segment_bundle(), [], "run-id", {"source_sha256": "source-hash"}
            )
        self.assertEqual(payload["llm_result"]["overall_soundscape"], "Quiet room tone.")
        self.assertEqual(payload["llm_result"]["non_diegetic_music"], "N/A")

    def test_wrong_bound_guard_allows_small_route_details_with_correct_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        raw = (
            "At 00:04.000, Will and Amber run down a short hall and stairs, "
            "then go through the basement door into the basement."
        )
        self.assertEqual(
            minimax._director_wrong_bound_barrier_errors(raw, binding),
            [],
        )

    def test_deterministic_crossing_guard_rejects_unauthorized_helper(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Amy, Will, and Amber rush into the basement.",
            contracts,
        )
        self.assertTrue(any("Amy" in issue for issue in issues))

    def test_deterministic_crossing_guard_rejects_ambiguous_follow_pronoun(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Will and Amber step inside as she follows.",
            contracts,
        )
        self.assertTrue(any("follow-pronoun" in issue for issue in issues))

    def test_deterministic_crossing_guard_rejects_following_into_destination(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = (
            "At 00:04.000, Will and Amber enter the basement while Amy follows closely behind.\n"
            "At 00:05.200, Amy locks the basement door.\n"
            "At 00:07.700, Amy steps out of the basement."
        )
        issues = minimax._director_unauthorized_destination_crossing_errors(
            raw, contracts
        )
        self.assertTrue(any("Amy is not authorized to follow" in issue for issue in issues))

    def test_deterministic_crossing_guard_allows_staying_outside_destination(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = (
            "At 00:04.000, Will and Amber enter the basement while Amy remains outside.\n"
            "At 00:05.200, Amy locks the basement door."
        )
        self.assertEqual(
            minimax._director_unauthorized_destination_crossing_errors(raw, contracts),
            [],
        )

    def test_deterministic_crossing_guard_rejects_unauthorized_dash(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        raw = "At 00:04.000, Amy and the kids dash through the broken window into the basement."
        issues = minimax._director_unauthorized_destination_crossing_errors(raw, contracts)
        self.assertTrue(any("Amy is not authorized to cross" in issue for issue in issues))

    def test_containment_crossing_requires_visible_entry_not_just_final_state(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"location":"kitchen"},'
            '"Amber":{"location":"kitchen"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
        ]
        raw = (
            "At 00:03.000, Amy pushes them into the basement door.\n"
            "At 00:04.000, Will and Amber reach the basement door; Amy shuts it.\n"
            "End continuity state: Will and Amber are inside the basement."
        )
        issues = minimax._director_missing_containment_crossing_errors(raw, effects, opening)
        self.assertTrue(any(issue.startswith("Will must visibly cross") for issue in issues))
        self.assertTrue(any(issue.startswith("Amber must visibly cross") for issue in issues))

    def test_containment_crossing_accepts_named_entry(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
        ]
        raw = (
            "At 00:04.000, Will and Amber step into the basement through its door.\n"
            "End continuity state: Will and Amber are inside the basement."
        )
        self.assertEqual(
            minimax._director_missing_containment_crossing_errors(raw, effects, ""),
            [],
        )

    def test_opening_held_prop_cannot_end_unassigned_on_belt(self):
        registry = {"subjects": {"Amy": {"held_props": ["pistol", "katana"]}}}
        raw = (
            "At 00:00.000, Amy swings her katana and fires her pistol.\n"
            "At 00:07.000, Amy stands with the katana hanging on her belt.\n"
            "End continuity state: Amy holds a pistol with a katana on her belt."
        )
        issues = minimax._director_opening_held_unassigned_stow_errors(
            raw, registry, "Amy cuts the target with the katana and fires the pistol."
        )
        self.assertTrue(any("katana" in issue for issue in issues))
        self.assertFalse(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_may_be_stowed_when_source_assigns_it(self):
        registry = {"subjects": {"Amy": {"held_props": ["katana"]}}}
        raw = (
            "At 00:06.000, Amy places the katana on her belt.\n"
            "End continuity state: Amy stands with the katana on her belt."
        )
        self.assertEqual(
            minimax._director_opening_held_unassigned_stow_errors(
                raw, registry, "Amy clips the katana to her belt."
            ),
            [],
        )

    def test_both_hands_action_requires_release_of_opening_held_prop(self):
        registry = {"subjects": {"Amy": {"held_props": ["pistol", "katana"]}}}
        raw = (
            "At 00:00.000, Amy holds a pistol and katana.\n"
            "At 00:04.000, Amy lifts the arm with both hands and throws it away.\n"
            "End continuity state: Amy holds both weapons."
        )
        issues = minimax._director_occupied_hands_errors(raw, registry)
        self.assertTrue(any("cannot use both hands" in issue for issue in issues))

        released = raw.replace(
            "At 00:04.000, Amy lifts",
            "At 00:03.000, Amy sets down the pistol.\nAt 00:04.000, Amy lifts",
        )
        self.assertEqual(minimax._director_occupied_hands_errors(released, registry), [])

    def test_opening_held_prop_cannot_be_reacquired_without_release(self):
        registry = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol", "katana"],
                },
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            (
                "At 00:00.000, Amy holds a pistol and katana.\n"
                "At 00:01.000, Amy pulls pistol from holster and aims it.\n"
                "End continuity state: Amy holds pistol and katana."
            ),
            registry,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_use_is_not_reacquisition(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:00.000, Amy pulls the trigger on her pistol and fires.",
            "At 00:00.000, Amy shoots the zombie with her pistol.",
            "At 00:00.000, Amy raises her pistol toward the zombie.",
        ):
            self.assertEqual(
                minimax._director_opening_held_reacquire_errors(
                    raw_scene,
                    registry,
                ),
                [],
            )

    def test_opening_held_prop_lift_from_surface_is_rejected(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:02.200, Amy lifts the pistol from a nearby table.",
            "At 00:02.200, Amy raises her pistol off the counter.",
        ):
            issues = minimax._director_opening_held_reacquire_errors(
                raw_scene,
                registry,
            )
            self.assertTrue(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_raise_to_use_is_not_reacquisition(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        for raw_scene in (
            "At 00:02.200, Amy lifts her pistol toward the zombie.",
            "At 00:02.200, Amy raises her pistol to eye level.",
        ):
            self.assertEqual(
                minimax._director_opening_held_reacquire_errors(
                    raw_scene,
                    registry,
                ),
                [],
            )

    def test_opening_held_prop_pronoun_requires_unique_holder(self):
        state = {
            "subjects": {
                "Amy": {"held_props": ["pistol"]},
                "Riley": {"held_props": ["pistol"]},
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, She pulls the pistol from her belt and fires.",
            state,
        )
        self.assertEqual(issues, [])

    def test_opening_held_prop_pull_from_belt_reacquire_is_rejected(self):
        state = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                }
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, She pulls the pistol from her belt and fires.",
            state,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_pull_out_reacquire_is_rejected(self):
        state = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                }
            }
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:04.000, Amy pulls out her pistol and aims at the body.",
            state,
        )
        self.assertTrue(any("already begins the segment holding" in issue for issue in issues))

    def test_opening_held_prop_direct_reacquire_is_rejected(self):
        registry = {
            "subjects": {
                "Amy": {"held_props": ["pistol", "katana"]},
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            "At 00:00.000, Amy pulls the pistol from a holster.",
            registry,
        )
        self.assertTrue(any("pistol" in issue for issue in issues))

    def test_opening_held_prop_can_be_reacquired_after_release(self):
        registry = {
            "subjects": {
                "Amy": {
                    "held_props": ["pistol"],
                },
            },
        }
        issues = minimax._director_opening_held_reacquire_errors(
            (
                "At 00:00.000, Amy holsters the pistol.\n"
                "At 00:01.000, Amy draws the pistol from the holster.\n"
                "End continuity state: Amy holds the pistol."
            ),
            registry,
        )
        self.assertEqual(issues, [])


    def test_deterministic_crossing_guard_allows_authorized_children(self):
        contracts = [{
            "destination": "basement",
            "subjects": [
                {"entity": "Amy", "expected": "NOT_AT_DESTINATION"},
                {"entity": "Will", "expected": "AT_DESTINATION"},
                {"entity": "Amber", "expected": "AT_DESTINATION"},
            ],
        }]
        issues = minimax._director_unauthorized_destination_crossing_errors(
            "At 00:00.000, Will and Amber rush into the basement while Amy stays outside.",
            contracts,
        )
        self.assertEqual(issues, [])


    def test_bound_generic_barrier_rejects_wrong_qualified_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        issues = minimax._director_wrong_bound_barrier_errors(
            "At 00:05.000, Amy slams the kitchen door shut.",
            binding,
        )
        self.assertTrue(any("kitchen door" in issue for issue in issues))

    def test_bound_generic_barrier_rejects_wrong_crossing_doorway(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        issues = minimax._director_wrong_bound_barrier_errors(
            "At 00:02.000, they sprint through the broken kitchen doorway directly into the basement.",
            binding,
        )
        self.assertTrue(any("kitchen doorway" in issue for issue in issues))

    def test_bound_generic_barrier_allows_destination_or_generic_door(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        for raw_scene in (
            "At 00:05.000, Amy slams the basement door shut.",
            "At 00:05.000, Amy locks the door.",
            "At 00:01.000, a zombie shatters the kitchen door window.",
        ):
            self.assertEqual(
                minimax._director_wrong_bound_barrier_errors(raw_scene, binding),
                [],
            )

    def test_bound_basement_door_rejects_window_route_into_basement(self):
        binding = {"entity": "door", "destination": "basement", "state": "locked"}
        raw = "At 00:04.000, Amy and the kids dash through the broken window into the basement."
        issues = minimax._director_wrong_bound_barrier_errors(raw, binding)
        self.assertTrue(any("through a window" in issue for issue in issues))

    def test_preserved_containment_rejects_visual_relocation(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"},'
            '"Amber":{"containment":"contained","contained_in":"basement"}}}'
        )
        raw = (
            "At 00:06.000, through the broken kitchen door window, "
            "Will and Amber look up at the scene."
        )
        issues = minimax._director_preserved_containment_errors(raw, opening, [])
        self.assertTrue(any(issue.startswith("Will is canonically contained") for issue in issues))
        self.assertTrue(any(issue.startswith("Amber is canonically contained") for issue in issues))

    def test_preserved_containment_allows_subject_still_in_container(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}}}'
        )
        raw = "At 00:06.000, Will stands inside the basement looking toward the door."
        issues = minimax._director_preserved_containment_errors(raw, opening, [])
        self.assertEqual(issues, [])

    def test_preserved_containment_allows_explicit_release_effect(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Will":{"containment":"contained","contained_in":"basement"}}}'
        )
        effects = [
            {"op":"set_containment","entity":"Will","value":"free","container":"basement"}
        ]
        raw = "At 00:04.000, Will steps into the living room."
        issues = minimax._director_preserved_containment_errors(raw, opening, effects)
        self.assertEqual(issues, [])

    def test_unassigned_external_end_rejects_helper_following_outside(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"},"Will":{"location":"basement"},'
            '"Amber":{"location":"basement"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "value": "free", "container": "basement"},
            {"op": "set_containment", "entity": "Amber", "value": "free", "container": "basement"},
        ]
        subjects = (
            "<Subject 1> is Amy, a woman.\n"
            "<Subject 2> is Will, a boy.\n"
            "<Subject 3> is Amber, a girl."
        )
        raw = (
            "At 00:07.500, all three stand outside in sunlight.\n"
            "End continuity state: Amy, Will, and Amber stand on the sunny patio outside the house."
        )
        issues = minimax._director_unassigned_external_end_errors(
            raw, opening, effects, subjects
        )
        self.assertTrue(any(issue.startswith("Amy ends outside") for issue in issues))
        self.assertFalse(any(issue.startswith("Will ends outside") for issue in issues))
        self.assertFalse(any(issue.startswith("Amber ends outside") for issue in issues))

    def test_unassigned_external_end_allows_outside_containment_boundary(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"}}}'
        )
        effects = [
            {"op": "set_containment", "entity": "Will", "value": "contained", "container": "basement"},
            {"op": "set_containment", "entity": "Amber", "value": "contained", "container": "basement"},
        ]
        subjects = "<Subject 1> is Amy, a woman."
        for ending in (
            "Amy is outside the basement; Will and Amber are inside.",
            "Amy stands outside the basement door while Will and Amber are inside.",
            "Amy stands outside the kitchen doorway beside the basement door.",
        ):
            raw = "At 00:07.000, Amy locks the basement door.\nEnd continuity state: " + ending
            self.assertEqual(
                minimax._director_unassigned_external_end_errors(
                    raw, opening, effects, subjects
                ),
                [],
            )

    def test_authorized_external_end_is_allowed(self):
        opening = (
            'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
            '{"characters":{"Amy":{"location":"home"}}}'
        )
        effects = [
            {"op": "set_location", "entity": "Amy", "value": "outside home"},
        ]
        raw = (
            "At 00:05.000, Amy steps outside.\n"
            "End continuity state: Amy stands outside the house."
        )
        issues = minimax._director_unassigned_external_end_errors(
            raw, opening, effects, "<Subject 1> is Amy, a woman."
        )
        self.assertEqual(issues, [])


    def test_director_prompt_allows_small_route_details(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
        )
        self.assertIn("Harmless local route or prop details are allowed", prompt)
        self.assertIn("natural physical staging", prompt)
        self.assertNotIn("Do not invent structural geography", prompt)
    def test_completion_prompt_allows_small_route_details(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy gets Will and Amber into the basement and locks the door.",
            (
                "At 00:00.000, Amy grabs Will and Amber.\n"
                "At 00:01.000, Will and Amber descend the kitchen stairs.\n"
                "At 00:02.000, Will and Amber enter the basement.\n"
                "At 00:03.000, Amy locks the basement door.\n"
                "End continuity state: Will and Amber are in the basement; Amy is outside."
            ),
            assigned_source=(
                "Amy rushes Will and Amber to the basement, gets them inside, "
                "and locks the door."
            ),
            authoritative_opening_state="Amy, Will, and Amber are in the kitchen.",
            assigned_state_effects=[
                {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            ],
        )
        prompt = messages[-1]["content"]
        self.assertIn("harmless staging detail", prompt)
        self.assertIn("may NOT replace a concrete SOURCE action", prompt)


    def test_completion_prompt_rejects_ambiguous_collective_crossing(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Amy moves Will and Amber into the basement and locks the door.",
            (
                "At 00:00.000, Amy grabs Will and Amber.\n"
                "At 00:01.000, They descend into the basement.\n"
                "At 00:02.000, Amy locks the basement door.\n"
                "End continuity state: Will and Amber are inside the basement; Amy is outside."
            ),
            assigned_source=(
                "Amy rushes Will and Amber to the basement, gets them inside, "
                "and locks the door."
            ),
            authoritative_opening_state="Amy, Will, and Amber are outside the basement.",
            assigned_state_effects=[
                {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            ],
        )
        prompt = messages[-1]["content"]
        self.assertIn('collective language such as "they"', prompt)
        self.assertIn("explicitly name only the authorized crossers", prompt)



    def test_director_prompt_keeps_source_and_current_beat_as_authority(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
        )
        self.assertIn("ASSIGNED SOURCE is the story authority", prompt)
        self.assertIn("CURRENT BEAT is the scene to stage", prompt)
    def test_completion_prompt_rejects_concrete_action_substitution(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "A parent grabs two children and rushes them into the shelter.",
            (
                "At 00:00.000, the parent lifts both children.\n"
                "At 00:02.000, the parent carries them toward the shelter.\n"
                "End continuity state: the children are inside the shelter."
            ),
            assigned_source=(
                "A parent grabs two children and rushes them into the shelter."
            ),
            authoritative_opening_state=(
                "The parent and both children begin outside the shelter."
            ),
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "may NOT replace a concrete SOURCE action or participant interaction",
            prompt,
        )


    def test_director_prompt_does_not_encode_terminal_target_rules(self):
        prompt = minimax.DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
            segment_seconds=8,
            segment_min_beats=4,
            final_quarter_start=6,
            beat_number=1,
            story_segment_ending_rules="",
        )
        self.assertNotIn("already terminal target", prompt)
        self.assertNotIn("new, another, or incoming target", prompt)
    def test_completion_prompt_preserves_new_target_distinction(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "The operator repeatedly disables incoming drones.",
            (
                "At 00:00.000, the operator cuts an arm from the disabled drone on the floor.\n"
                "End continuity state: the disabled drone remains on the floor."
            ),
            assigned_source="The operator repeatedly disables incoming drones.",
            authoritative_opening_state="A disabled drone lies on the floor.",
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "may not satisfy the action by reusing a target already dead, destroyed, or terminal",
            prompt,
        )

    def test_completion_prompt_rejects_unassigned_terminal_outcome(self):
        messages = minimax.build_director_raw_scene_completion_messages(
            "Operator damages the machine's outer panel.",
            (
                "At 00:00.000, Operator dents the machine's outer panel.\n"
                "At 00:01.000, The machine collapses permanently and stops.\n"
                "End continuity state: The machine is motionless and permanently stopped."
            ),
            assigned_source="Operator damages the machine's outer panel.",
            authoritative_opening_state="N/A",
            assigned_state_effects=[],
        )
        prompt = messages[-1]["content"]
        self.assertIn("non-terminal injury/damage/change", prompt)
        self.assertIn("motionless/collapsed", prompt)



if __name__ == "__main__":
    unittest.main()
