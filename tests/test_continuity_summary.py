import copy
import unittest
from unittest.mock import Mock, call, patch

import minimax


def canonical_candidate(subject_definitions, committed_state=None):
    """Return a complete fresh snapshot carrying stable identities only."""
    identities = minimax.continuity_state_for_registry(
        subject_definitions,
        committed_state,
    )
    candidate = minimax.new_continuity_state()
    candidate["subjects"] = {
        name: minimax.new_subject_continuity_record(copy.deepcopy(record))
        for name, record in identities["subjects"].items()
    }
    return candidate


def complete_new_subject(subject_id, name, **updates):
    record = minimax.new_subject_continuity_record({
        "subject_id": subject_id,
        "name": name,
        "picture_ids": [],
        "picture_id": None,
        "speaker_id": None,
        "origin_segment": None,
    })
    record.update(updates)
    return record


def segment_result(number):
    return {
        "detailed_description": (
            f"[Shot {number}] Camera continues from the previous shot. "
            f"Mark stands beside numbered prop {number}."
        ),
        "overall_soundscape": f"Room tone {number}.",
        "non_diegetic_music": "N/A",
        "completed_beat_ids": [number],
    }


class ContinuitySummaryTests(unittest.TestCase):
    SUBJECTS = (
        "<Subject 1> is Connie, referenced in <Picture 1>.\n"
        "<Subject 2> is Beth, referenced in <Picture 2>."
    )

    def test_structured_state_has_independent_subject_fields(self):
        state = minimax.continuity_state_for_registry(self.SUBJECTS)

        connie = state["subjects"]["Connie"]
        self.assertEqual(connie["picture_id"], 1)
        self.assertIn("position", connie)
        self.assertEqual(connie["body_state"], "N/A")
        self.assertEqual(
            set(connie["wardrobe"]),
            {"upper", "lower", "footwear", "other"},
        )
        self.assertIsInstance(connie["held_props"], list)
        self.assertIsInstance(state["environment"], dict)

    def test_opening_state_prompt_is_rendered_from_structured_state(self):
        state = minimax.continuity_state_for_registry(self.SUBJECTS)
        state["environment"]["location"] = "bedroom"
        state["subjects"]["Connie"]["wardrobe"]["upper"] = "green sweater"
        state["subjects"]["Connie"]["body_state"] = "left horn missing"

        opening = minimax.format_authoritative_opening_state(
            state,
            self.SUBJECTS,
        )

        self.assertTrue(opening.startswith("<Video 1>"))
        self.assertIn("summary:", opening)
        self.assertIn("retention_analysis:", opening)
        self.assertIn("final observable state of <Video 1>", opening)
        self.assertIn("its bedroom, lighting, spatial layout", opening)
        self.assertIn("wearing green sweater", opening)
        self.assertIn("Body state: left horn missing", opening)
        self.assertIn("<Subject 1>: fully_preserved", opening)
        self.assertIn("<Video 1>: fully_preserved", opening)
        self.assertNotIn("wardrobe_upper:", opening)
        self.assertNotIn("N/A", opening)

    def test_legacy_empty_state_rebuilds_subjects_from_definitions(self):
        definitions = (
            "<Subject 1> is Mark, a 40-year-old man referenced in <Picture 1>.\n"
            "<Subject 2> is Jill, a 35-year-old woman referenced in <Picture 2>."
        )

        opening = minimax.format_authoritative_opening_state(
            minimax.new_continuity_state(),
            definitions,
        )

        self.assertIn(
            "<Subject 1>: fully_preserved - Preserve Mark's identity "
            "from <Picture 1>.",
            opening,
        )
        self.assertIn(
            "<Subject 2>: fully_preserved - Preserve Jill's identity "
            "from <Picture 2>.",
            opening,
        )

    def test_opening_state_preserves_video_only_subjects(self):
        state = minimax.continuity_state_for_registry(self.SUBJECTS)
        state["environment"]["location"] = "sterile alien chamber"
        state["subjects"]["spider-alien"] = {
            "subject_id": 3,
            "name": "spider-alien",
            "picture_ids": [],
            "picture_id": None,
            "speaker_id": None,
            "position": "above Connie",
            "pose_action": "moving with unnatural speed",
            "wardrobe": {
                "upper": "N/A",
                "lower": "N/A",
                "footwear": "N/A",
                "other": "N/A",
            },
            "body_state": "segmented body, eight legs, and mandibles",
            "physical_condition": "N/A",
            "held_props": [],
        }

        opening = minimax.format_authoritative_opening_state(
            state,
            self.SUBJECTS,
        )

        self.assertIn(
            "<Subject 3> spider-alien continues from <Video 1>",
            opening,
        )
        self.assertIn(
            "<Subject 3>: fully_preserved - Preserve spider-alien's "
            "established appearance from <Video 1>.",
            opening,
        )
        self.assertIn(
            "Body state: segmented body, eight legs, and mandibles",
            opening,
        )

    def test_continuity_candidate_records_new_subject_creation_segment(self):
        initial_snapshot = canonical_candidate(self.SUBJECTS)
        initial_snapshot["subjects"]["spider-alien"] = complete_new_subject(
            3,
            "spider-alien",
            entity_kind="animate",
            position="above Connie",
            pose_action="crawling forward",
            body_state="segmented body and eight legs",
        )
        candidate = minimax.normalize_structured_continuity_state(
            initial_snapshot,
            self.SUBJECTS,
            origin_segment=2,
            newest_description=(
                "A spider-alien crawls into view above Connie."
            ),
        )

        created = candidate["subjects"]["spider-alien"]
        self.assertEqual(created["subject_id"], 3)
        self.assertEqual(created["picture_ids"], [])
        self.assertEqual(created["origin_segment"], 2)

        next_snapshot = canonical_candidate(self.SUBJECTS, candidate)
        next_snapshot["subjects"]["spider-alien"]["subject_id"] = 99
        next_snapshot["subjects"]["spider-alien"]["origin_segment"] = 99
        next_snapshot["subjects"]["spider-alien"]["position"] = "beside Connie"
        preserved = minimax.normalize_structured_continuity_state(
            next_snapshot,
            self.SUBJECTS,
            candidate,
            origin_segment=3,
            newest_description=(
                "The spider-alien remains beside Connie."
            ),
        )
        self.assertEqual(
            preserved["subjects"]["spider-alien"]["subject_id"],
            3,
        )
        self.assertEqual(
            preserved["subjects"]["spider-alien"]["origin_segment"],
            2,
        )

    def test_new_video_subject_does_not_require_name_evidence_in_prose(self):
        for description in (
            "Terri cradles the baby in her arms.",
            "Terri cradles the newborn in her arms.",
            "Terri cradles the infant in her arms.",
            "Terri cradles the newly arrived figure in her arms.",
        ):
            with self.subTest(description=description):
                snapshot = canonical_candidate(self.SUBJECTS)
                snapshot["subjects"]["Baby Alpha"] = complete_new_subject(
                    3,
                    "Baby Alpha",
                    entity_kind="animate",
                    position="in Terri's arms",
                    body_state="newborn infant",
                )
                candidate = minimax.normalize_structured_continuity_state(
                    snapshot,
                    self.SUBJECTS,
                    origin_segment=2,
                    newest_description=description,
                    active_beat_text="Terri welcomes Baby Alpha.",
                )

                self.assertIn("Baby Alpha", candidate["subjects"])
                self.assertEqual(
                    candidate["subjects"]["Baby Alpha"]["origin_segment"],
                    2,
                )
                additional, added = (
                    minimax.collect_additional_subject_definitions(
                        self.SUBJECTS,
                        [],
                        candidate,
                        2,
                    )
                )
                expected = (
                    "<Subject 3> is Baby Alpha, created in generated "
                    "video segment 2 and continued from <Video 1>."
                )
                self.assertEqual(added, [expected])
                self.assertEqual(additional, [expected])

    def test_new_video_subject_is_accepted_without_current_name_evidence(self):
        snapshot = canonical_candidate(self.SUBJECTS)
        snapshot["subjects"]["Baby Alpha"] = complete_new_subject(
            3,
            "Baby Alpha",
            entity_kind="animate",
            body_state="newborn infant",
        )
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            origin_segment=2,
            newest_description="Connie stands alone in the empty room.",
            active_beat_text="Connie waits.",
        )

        self.assertIn("Baby Alpha", candidate["subjects"])

    def test_future_only_named_subject_is_still_rejected(self):
        snapshot = canonical_candidate(self.SUBJECTS)
        snapshot["subjects"]["Baby Alpha"] = complete_new_subject(
            3,
            "Baby Alpha",
            entity_kind="animate",
            body_state="newly visible subject",
        )
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            origin_segment=2,
            newest_description="Connie stands alone in the empty room.",
            active_beat_text="Connie waits.",
            future_beat_texts=["Baby Alpha arrives in the nursery."],
        )

        self.assertNotIn("Baby Alpha", candidate["subjects"])

    def test_new_inanimate_objects_are_not_created_as_subjects(self):
        for entity_kind in ("inanimate", ""):
            with self.subTest(entity_kind=entity_kind or "missing"):
                snapshot = canonical_candidate(self.SUBJECTS)
                updates = {
                    "position": "beside Connie",
                    "body_state": "red frame and silver handlebars",
                }
                if entity_kind:
                    updates["entity_kind"] = entity_kind
                snapshot["subjects"]["Red Bicycle"] = complete_new_subject(
                    3,
                    "Red Bicycle",
                    **updates,
                )
                candidate = minimax.normalize_structured_continuity_state(
                    snapshot,
                    self.SUBJECTS,
                    origin_segment=2,
                    newest_description=(
                        "Connie leaves a red bicycle beside the doorway."
                    ),
                )

                self.assertNotIn("Red Bicycle", candidate["subjects"])

    def test_speaking_inanimate_entity_is_persisted_as_subject_with_speaker_id(self):
        candidate = minimax.normalize_structured_continuity_state(
            canonical_candidate(self.SUBJECTS),
            self.SUBJECTS,
            origin_segment=2,
            newest_description=(
                "<Subject 3> Red Bicycle (S3) says: "
                "<d>[English] Pedal faster.</d>"
            ),
        )

        bicycle = candidate["subjects"]["Red Bicycle"]
        self.assertEqual(bicycle["subject_id"], 3)
        self.assertEqual(bicycle["speaker_id"], "S3")
        self.assertEqual(bicycle["origin_segment"], 2)

        additional, appended = minimax.collect_additional_subject_definitions(
            self.SUBJECTS,
            [],
            candidate,
            origin_segment=2,
        )
        combined = minimax.combine_subject_definitions(self.SUBJECTS, additional)

        self.assertEqual(len(appended), 1)
        self.assertEqual(minimax.parse_subject_registry(combined)[3]["speaker_id"], "S3")

    def test_continuity_prompt_forbids_inanimate_object_subjects(self):
        messages = minimax.build_structured_continuity_messages(
            [(1, segment_result(1))],
            minimax.continuity_state_for_registry(self.SUBJECTS),
            self.SUBJECTS,
        )

        system_prompt = messages[0]["content"]
        self.assertIn("entity_kind`: `animate", system_prompt)
        self.assertIn("Never create a Subject for an inanimate object", system_prompt)
        self.assertIn("Anything that explicitly speaks", system_prompt)

    def test_structured_candidate_replaces_omitted_old_wardrobe_with_na(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed["subjects"]["Connie"]["wardrobe"]["upper"] = "green sweater"

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["environment"]["location"] = "bedroom"
        snapshot["subjects"]["Connie"]["position"] = "left side"
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
        )

        self.assertEqual(
            candidate["subjects"]["Connie"]["wardrobe"]["upper"],
            "N/A",
        )
        self.assertEqual(candidate["subjects"]["Connie"]["position"], "left side")

    def test_structured_candidate_na_and_empty_lists_clear_known_subject_state(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed_subject = committed["subjects"]["Connie"]
        committed_subject["position"] = "beside the bed"
        committed_subject["wardrobe"] = {
            "upper": "green sweater",
            "lower": "black jeans",
            "footwear": "white sneakers",
            "other": "silver necklace",
        }
        committed_subject["physical_condition"] = "muddy and alert"
        committed_subject["body_state"] = "left horn missing"
        committed_subject["held_props"] = ["flashlight"]

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
        )

        result = candidate["subjects"]["Connie"]
        self.assertEqual(result["position"], "N/A")
        self.assertEqual(
            result["wardrobe"],
            {field: "N/A" for field in ("upper", "lower", "footwear", "other")},
        )
        self.assertEqual(result["physical_condition"], "N/A")
        self.assertEqual(result["body_state"], "N/A")
        self.assertEqual(result["held_props"], [])

    def test_structured_state_rebuilds_name_keys_from_numeric_subject_ids(self):
        committed = minimax.new_continuity_state()
        committed["subjects"] = {
            "1": {
                "position": "left side of the room",
                "pose_action": "standing near the door",
                "wardrobe": {
                    "upper": "green sweater",
                    "lower": "black pants",
                    "footwear": "white sneakers",
                    "other": "silver necklace",
                },
                "physical_condition": "alert",
                "body_state": "left horn missing",
                "held_props": ["flashlight"],
            },
            "2": {
                "position": "right side of the room",
                "pose_action": "holding a map",
                "wardrobe": {
                    "upper": "blue jacket",
                    "lower": "khaki trousers",
                    "footwear": "brown boots",
                    "other": "watch",
                },
                "physical_condition": "calm",
                "body_state": "uninjured",
                "held_props": ["map"],
            },
        }

        state = minimax.continuity_state_for_registry(self.SUBJECTS, committed)

        self.assertEqual(state["subjects"]["Connie"]["position"], "left side of the room")
        self.assertEqual(state["subjects"]["Beth"]["wardrobe"]["upper"], "blue jacket")
        self.assertEqual(state["subjects"]["Connie"]["body_state"], "left horn missing")
        self.assertEqual(state["subjects"]["Connie"]["held_props"], ["flashlight"])

    def test_structured_candidate_fills_unknown_body_state(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["subjects"]["Connie"]["body_state"] = "left horn missing"
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
            newest_description="Connie's left horn is visibly missing.",
        )

        self.assertEqual(
            candidate["subjects"]["Connie"]["body_state"],
            "left horn missing",
        )

    def test_structural_evidence_requires_the_same_neutral_region(self):
        self.assertTrue(
            minimax._structural_change_has_evidence(
                "Connie",
                "left arm remains raised",
                "Connie's left arm remains raised in the final frame.",
            )
        )
        self.assertFalse(
            minimax._structural_change_has_evidence(
                "Connie",
                "left arm remains raised",
                "Connie's left leg remains raised in the final frame.",
            )
        )
        self.assertFalse(
            minimax._structural_change_has_evidence(
                "Connie",
                "cable connected to front port",
                "Connie connects the cable to the rear port.",
            )
        )

    def test_structured_candidate_replaces_explicit_final_frame_state(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed["camera"] = "wide shot of the ridge"
        committed["subjects"]["Connie"]["position"] = "atop the ridge"
        committed["subjects"]["Connie"]["pose_action"] = "running"
        committed["subjects"]["Connie"]["physical_condition"] = "bleeding"

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["camera"] = "medium shot beside Gogol"
        snapshot["subjects"]["Connie"]["position"] = "beside Gogol"
        snapshot["subjects"]["Connie"]["pose_action"] = "standing still"
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
        )

        connie = candidate["subjects"]["Connie"]
        self.assertEqual(candidate["camera"], "medium shot beside Gogol")
        self.assertEqual(connie["position"], "beside Gogol")
        self.assertEqual(connie["pose_action"], "standing still")
        self.assertEqual(connie["physical_condition"], "N/A")

    def test_explicit_held_props_lists_replace_only_the_matching_subject(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed["subjects"]["Connie"]["held_props"] = ["flashlight"]
        committed["subjects"]["Beth"]["held_props"] = ["map"]

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["subjects"]["Connie"]["held_props"] = []
        snapshot["subjects"]["Beth"]["held_props"] = ["silver sword"]
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
            newest_description=(
                "Connie releases the flashlight while Beth holds a silver sword."
            ),
        )

        self.assertEqual(candidate["subjects"]["Connie"]["held_props"], [])
        self.assertEqual(
            candidate["subjects"]["Beth"]["held_props"],
            ["silver sword"],
        )

    def test_registry_identity_fields_override_candidate_values(self):
        snapshot = canonical_candidate(self.SUBJECTS)
        snapshot["subjects"]["Connie"].update({
            "subject_id": 99,
            "picture_ids": [99],
            "picture_id": 99,
            "speaker_id": "S99",
        })
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
        )

        connie = candidate["subjects"]["Connie"]
        self.assertEqual(connie["subject_id"], 1)
        self.assertEqual(connie["picture_ids"], [1])
        self.assertEqual(connie["picture_id"], 1)
        self.assertEqual(connie["speaker_id"], "S1")

    def test_numeric_subject_id_candidates_replace_existing_state_with_na(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed["subjects"]["Connie"]["position"] = "beside the bed"
        committed["subjects"]["Connie"]["wardrobe"]["upper"] = "green sweater"
        committed["subjects"]["Connie"]["physical_condition"] = "alert"
        committed["subjects"]["Connie"]["held_props"] = ["flashlight"]

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["subjects"]["1"] = snapshot["subjects"].pop("Connie")
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
        )

        result = candidate["subjects"]["Connie"]
        self.assertEqual(result["position"], "N/A")
        self.assertEqual(result["wardrobe"]["upper"], "N/A")
        self.assertEqual(result["physical_condition"], "N/A")
        self.assertEqual(result["held_props"], [])

    def test_na_with_implied_note_normalizes_to_na_without_recovery(self):
        committed = minimax.continuity_state_for_registry(self.SUBJECTS)
        committed["subjects"]["Connie"]["position"] = "beside the bed"
        committed["subjects"]["Connie"]["wardrobe"]["upper"] = "N/A"
        committed["subjects"]["Connie"]["physical_condition"] = "N/A"
        committed["subjects"]["Connie"]["held_props"] = []

        snapshot = canonical_candidate(self.SUBJECTS, committed)
        snapshot["subjects"]["Connie"].update({
            "position": "N/A (implied near the doorway)",
            "physical_condition": "N/A (implied startled)",
            "held_props": ["N/A (implied flashlight)"],
        })
        snapshot["subjects"]["Connie"]["wardrobe"]["upper"] = (
            "N/A (implied red shirt)"
        )
        candidate = minimax.normalize_structured_continuity_state(
            snapshot,
            self.SUBJECTS,
            committed,
        )

        result = candidate["subjects"]["Connie"]
        self.assertEqual(result["position"], "N/A")
        self.assertEqual(result["wardrobe"]["upper"], "N/A")
        self.assertEqual(result["physical_condition"], "N/A")
        self.assertEqual(result["held_props"], [])

    def test_background_workers_are_closed_when_generation_raises(self):
        summary_worker = Mock()
        summary_worker.__enter__ = Mock(return_value=summary_worker)
        summary_worker.__exit__ = Mock(return_value=False)
        director_worker = Mock()
        director_worker.__enter__ = Mock(return_value=director_worker)
        director_worker.__exit__ = Mock(return_value=False)
        render_worker = Mock()
        render_worker.__enter__ = Mock(return_value=render_worker)
        render_worker.__exit__ = Mock(return_value=False)
        with patch(
            "minimax.ThreadPoolExecutor",
            side_effect=[summary_worker, director_worker, render_worker],
        ) as factory:
            with patch("minimax._run_main", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    minimax.main()

        self.assertEqual(
            factory.call_args_list,
            [
                call(
                    max_workers=1,
                    thread_name_prefix="continuity-summary",
                ),
                call(
                    max_workers=1,
                    thread_name_prefix="director-prefetch",
                ),
                call(
                    max_workers=1,
                    thread_name_prefix="comfyui-render",
                ),
            ],
        )
        summary_worker.__exit__.assert_called_once()
        director_worker.__exit__.assert_called_once()
        render_worker.__exit__.assert_called_once()

    @patch("minimax.requests.post")
    def test_plain_text_summary_uses_chat_completions_without_schema(
        self, post
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "\n".join(
                        f"- fact {number}" for number in range(1, 6)
                    )
                }
            }]
        }
        post.return_value = response

        result = minimax.ask_llm(
            [{"role": "user", "content": "summarize"}],
            max_retries=1,
            response_format=None,
        )

        self.assertEqual(5, len(result.splitlines()))
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            f"{minimax.LM_STUDIO_URL}/v1/chat/completions",
            url,
        )
        self.assertNotIn("response_format", payload)

    def test_summary_thread_contains_only_the_newest_exact_result(self):
        messages = minimax.build_summary_messages([
            (1, segment_result(1)),
            (2, segment_result(2)),
            (3, segment_result(3)),
        ])

        combined = "\n".join(message["content"] for message in messages)
        self.assertNotIn("numbered prop 1", combined)
        self.assertNotIn("numbered prop 2", combined)
        self.assertIn("numbered prop 3", combined)
        self.assertNotIn("completed_beat_ids", combined)
        self.assertEqual(["system", "user"], [m["role"] for m in messages])

    def test_summary_requires_at_least_one_result(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            minimax.build_summary_messages([])

    def test_first_segment_can_produce_previous_state(self):
        messages = minimax.build_summary_messages([(1, segment_result(1))])
        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("EXACT RECENT SEGMENT 1", combined)
        self.assertNotIn("EXACT RECENT SEGMENT 2", combined)

    def test_summary_subject_speaker_ids_are_normalized_to_subject_tags(self):
        summary = (
            "- Location/environment: The room is quiet.\n"
            "- Character positions: Mark (S1) stands beside Jill (S2).\n"
            "- Character appearance/physical condition: Mark (S1) is alert.\n"
            "- Clothing: Mark (S1) wears a red shirt.\n"
            "- Props/objects: Jill (S2) holds a notebook.\n"
            "- Camera/framing: A medium shot frames Mark (S1) and Jill (S2).\n"
            "- Ongoing physical action: Mark (S1) watches Jill (S2).\n"
            "- Ongoing audio: Footsteps continue."
        )

        normalized = minimax.normalize_summary_subject_references(
            summary,
            "<Subject 1> is Mark, referenced in <Picture 1>.\n"
            "<Subject 2> is Jill, referenced in <Picture 2>.",
        )

        self.assertIn("<Subject 1> Mark", normalized)
        self.assertIn("<Subject 2> Jill", normalized)
        self.assertNotRegex(normalized, r"\(S[12]\)")

    def test_previous_state_em_dash_is_replaced_with_comma(self):
        summary = (
            "- Location/environment: Hallway by the doorway.\n"
            "- Character positions: and <Subject 3> Terri—are clustered near the doorway.\n"
            "- Character appearance/physical condition: Terri is tense.\n"
            "- Clothing: Terri wears a dark coat.\n"
            "- Props/objects: A flashlight rests on the floor.\n"
            "- Camera/framing: Medium shot from chest height.\n"
            "- Ongoing physical action: They hold position.\n"
            "- Ongoing audio: Footsteps echo."
        )

        normalized = minimax.normalize_previous_state(summary)

        self.assertIsNotNone(normalized)
        self.assertIn(
            "- Character positions: and <Subject 3> Terri, are clustered near the doorway.",
            normalized,
        )
        self.assertNotIn("—", normalized)

    def test_numbered_summary_is_normalized_to_exactly_five_bullets(self):
        raw = "\n".join(f"{number}. fact {number}" for number in range(1, 6))
        self.assertEqual(
            "\n".join(f"- fact {number}" for number in range(1, 6)),
            minimax.normalize_five_bullet_summary(raw),
        )

    def test_malformed_summary_is_requeried_in_separate_plain_text_thread(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append((messages, kwargs))
            if len(calls) == 1:
                return "Location/environment: only one field"
            return "\n".join(
                f"{field}: fact {number}"
                for number, field in enumerate(
                    minimax.PREVIOUS_STATE_FIELDS,
                    start=1,
                )
            )

        summary = minimax.request_five_bullet_summary(
            [(1, segment_result(1)), (2, segment_result(2))],
            llm_request=fake_llm,
        )

        self.assertEqual(2, len(calls))
        self.assertEqual(8, len(summary.splitlines()))
        self.assertIsNone(calls[0][1]["response_format"])
        self.assertNotIn("formatter", calls[0][0][0]["content"].lower())
        self.assertEqual(
            [message["role"] for message in calls[1][0]],
            ["system", "user"]
        )
        self.assertIn("prior response", calls[1][0][-1]["content"].lower())

    def test_generation_context_has_summary_and_only_newest_exact_result(self):
        summary = "\n".join(
            f"- {field}: continuity fact {number}"
            for number, field in enumerate(
                minimax.PREVIOUS_STATE_FIELDS,
                start=1,
            )
        )
        messages, _, recent_count = minimax.build_generation_messages(
            director_rules="DIRECTOR",
            story="SOURCE STORY",
            beats=[],
            completed_beat_ids=set(),
            recent_results=[
                (1, segment_result(1)),
                (2, segment_result(2)),
                (3, segment_result(3)),
            ],
            current_segment=4,
            total_segments=6,
            segment_length=6,
            total_length=36,
            continuity_summary=summary,
        )

        user_content = messages[1]["content"]
        self.assertEqual(1, recent_count)
        self.assertIn(summary, user_content)
        self.assertNotIn("numbered prop 1", user_content)
        self.assertNotIn("numbered prop 2", user_content)
        self.assertIn("numbered prop 3", user_content)
        self.assertIn("SOURCE STORY", user_content)

    def test_invalid_summary_fails_after_bounded_content_attempts(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append(messages)
            return "not a five-bullet summary"

        with self.assertRaisesRegex(RuntimeError, "eight-field"):
            minimax.request_five_bullet_summary(
                [(1, segment_result(1)), (2, segment_result(2))],
                llm_request=fake_llm,
                content_attempts=2,
            )
        self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main()
