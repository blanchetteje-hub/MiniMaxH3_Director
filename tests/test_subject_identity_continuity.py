import copy
import json
import tempfile
import unittest

import minimax


SUBJECTS = (
    "<Subject 1> is Elias, a man referenced in <Picture 1>.\n"
    "<Subject 2> is Werewolf, N/A (S2), continued from <Video 1>."
)


def wardrobe(**overrides):
    values = {field: "N/A" for field in minimax._WARDROBE_FIELDS}
    values.update(overrides)
    return values


def visual_subject(name, clothing, visible=True):
    return {
        "name": name,
        "visible": visible,
        "wardrobe": wardrobe(**clothing),
    }


class SubjectIdentityContinuityTests(unittest.TestCase):
    def test_registry_assigns_stable_werewolf_subject_id_and_picture_metadata(self):
        registry = minimax.parse_subject_registry(SUBJECTS)

        self.assertEqual(registry[1]["name"], "Elias")
        self.assertEqual(registry[1]["picture_ids"], [1])
        self.assertEqual(registry[2]["name"], "Werewolf")
        self.assertEqual(registry[2]["picture_ids"], [])
        self.assertEqual(registry[2]["speaker_id"], "S2")

    def test_raw_and_angle_aliases_resolve_without_allocating_duplicate_subject(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        subjects = state["subjects"]

        self.assertEqual(
            minimax._find_existing_subject_name(subjects, "Werewolf"),
            "Werewolf",
        )
        self.assertEqual(
            minimax._find_existing_subject_name(subjects, "<Werewolf>"),
            "Werewolf",
        )
        self.assertIsNone(
            minimax._find_existing_subject_name(subjects, "<Unrelated Creature>")
        )

        registered, added = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "<Werewolf> enters the room.",
            ["Werewolf"],
            origin_segment=4,
        )
        self.assertEqual(added, [])
        self.assertEqual(
            [record["subject_id"] for record in registered["subjects"].values()],
            [1, 2],
        )

    def test_h3_normalizes_raw_name_alias_without_adding_subject_tag(self):
        definitions, description = minimax._filter_h3_subject_definitions(
            SUBJECTS,
            {1},
            "Werewolf chases Elias.",
        )

        self.assertIn("<Subject 2>", definitions)
        self.assertEqual(description, "Werewolf chases Elias.")
        self.assertNotIn("<Werewolf>", description)

    def test_h3_does_not_insert_canonical_tag_inside_angle_bracket_alias(self):
        _definitions, description = minimax._filter_h3_subject_definitions(
            SUBJECTS,
            {1},
            "<Werewolf> chases Elias.",
        )

        self.assertEqual(description, "Werewolf chases Elias.")
        self.assertNotIn("<Subject 2>", description)

    def test_h3_refresh_propagates_registered_subject_two(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Werewolf enters.",
                "overall_soundscape": "wind",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=2,
            conditioning_mode="clean_refresh",
        )

        definitions = prompt.split("subject_definitions: ", 1)[1].split(
            "\n\nretention_analysis:", 1
        )[0]
        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:", 1
        )[0]
        self.assertIn("<Subject 2>", definitions)
        self.assertNotIn("<Subject 1>", definitions)
        self.assertIn("Werewolf enters", description)
        self.assertNotIn("<Subject 2> Werewolf", description)
        self.assertIn("retention_analysis:", prompt)
        self.assertNotIn("fully_preserved", prompt)

    def test_continuation_keeps_dynamic_subject_registry_marker(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Werewolf enters.",
                "overall_soundscape": "wind",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=2,
            conditioning_mode="continuation",
            previous_visible_subject_ids={1},
        )

        self.assertIn("<Subject 2> is Werewolf", prompt)
        self.assertIn("Werewolf enters", prompt)
        self.assertNotIn("<Subject 2> Werewolf", prompt)
        self.assertNotIn("retention_analysis:", prompt)

    def test_identity_repair_adds_missing_dynamic_speaker_id_after_registration(self):
        definitions = (
            "<Subject 1> is Amy, female (S1), referenced in <Picture 1>.\n"
            "<Subject 4> is Zombie1, unknown (S4), continued from <Video 1>."
        )
        repaired = minimax.repair_h3_subject_identity(
            "Zombie1 says <d>[English]BRAINS!</d>",
            definitions,
        )
        self.assertEqual(
            repaired,
            "Zombie1 (S4) says <d>[English]BRAINS!</d>",
        )

    def test_continuation_adds_video_origin_to_visible_subject_definitions(self):
        definitions = (
            "<Subject 1> is Elias, a man referenced in <Picture 1>.\n"
            "<Subject 2> is Stranger, male (S2), created in generated video "
            "segment 1."
        )
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 2] <Subject 1> Elias and <Subject 2> Stranger "
                    "stand together."
                ),
                "overall_soundscape": "wind",
                "non_diegetic_music": "N/A",
            },
            definitions,
            segment_number=2,
            conditioning_mode="continuation",
            previous_visible_subject_ids={1, 2},
        )

        subject_text = prompt.split("subject_definitions: ", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn(
            "Elias's pose, clothing condition, position, and physical state at "
            "the beginning of the target video come from <Video 1>.",
            subject_text,
        )
        self.assertIn(
            "<Subject 2> is Stranger, male (S2), created in generated video "
            "segment 1. continued from <Video 1>.",
            subject_text,
        )

    def test_continuation_does_not_add_video_origin_to_absent_subjects(self):
        definitions = (
            "<Subject 1> is Elias, a man referenced in <Picture 1>.\n"
            "<Subject 2> is Stranger, male (S2), created in generated video "
            "segment 1."
        )
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Elias stands alone.",
                "overall_soundscape": "wind",
                "non_diegetic_music": "N/A",
            },
            definitions,
            segment_number=2,
            conditioning_mode="continuation",
            previous_visible_subject_ids={1},
        )

        subject_text = prompt.split("subject_definitions: ", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("<Subject 1>", subject_text)
        self.assertNotIn("<Subject 2>", subject_text)
        self.assertNotIn("Stranger's pose", subject_text)

    def test_refresh_does_not_add_video_origin_to_visible_subject_definitions(self):
        definitions = (
            "<Subject 1> is Elias, a man referenced in <Picture 1>.\n"
            "<Subject 2> is Stranger, male (S2), continued from <Video 1>."
        )
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] Stranger stands alone.",
                "overall_soundscape": "wind",
                "non_diegetic_music": "N/A",
            },
            definitions,
            segment_number=2,
            conditioning_mode="clean_refresh",
        )

        subject_text = prompt.split("subject_definitions: ", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("<Subject 2> is Stranger, male (S2).", subject_text)
        self.assertNotIn("continued from <Video 1>", subject_text)
        self.assertNotIn("Stranger's pose", subject_text)

    def test_subject_alias_after_canonical_tag_is_not_duplicated(self):
        _definitions, description = minimax._filter_h3_subject_definitions(
            SUBJECTS,
            {2},
            "<Subject 2> <Werewolf> waits.",
        )

        self.assertEqual(description.count("<Subject 2>"), 1)
        self.assertIn("<Subject 2> Werewolf waits.", description)

    def test_visual_raw_name_and_angle_alias_map_to_canonical_subject(self):
        for alias in ("Werewolf", "<Werewolf>"):
            with self.subTest(alias=alias):
                normalized = minimax.normalize_visual_end_state(
                    {"subjects": [visual_subject(alias, {"upper": "black fur"})]},
                    SUBJECTS,
                )
                self.assertEqual(normalized["subjects"][0]["name"], "Werewolf")

    def test_picture_references_persist_and_are_not_reassigned_to_dynamic_subject(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Elias"]["wardrobe"]["upper"] = "blue shirt"
        state["subjects"]["Werewolf"]["position"] = "behind Elias"

        resumed = minimax.continuity_state_for_registry(SUBJECTS, state)
        self.assertEqual(resumed["subjects"]["Elias"]["picture_ids"], [1])
        self.assertEqual(resumed["subjects"]["Werewolf"]["picture_ids"], [])
        self.assertEqual(resumed["subjects"]["Werewolf"]["position"], "behind Elias")
        self.assertEqual(resumed["subjects"]["Elias"]["wardrobe"]["upper"], "blue shirt")

    def test_shared_picture_references_remain_shared(self):
        definitions = (
            "<Subject 1> is Elias, referenced in <Picture 1>.\n"
            "<Subject 2> is Werewolf, referenced in <Picture 1>."
        )
        state = minimax.continuity_state_for_registry(definitions)

        self.assertEqual(state["subjects"]["Elias"]["picture_ids"], [1])
        self.assertEqual(state["subjects"]["Werewolf"]["picture_ids"], [1])

    def test_dynamic_subject_survives_disappearance_and_reappearance(self):
        initial = minimax.continuity_state_for_registry(SUBJECTS)
        initial["subjects"]["Werewolf"]["position"] = "near the doorway"
        initial["subjects"]["Werewolf"]["wardrobe"] = wardrobe(upper="gray coat")

        disappeared = copy.deepcopy(initial)
        disappeared["subjects"]["Werewolf"]["position"] = "N/A"
        reappeared = minimax.continuity_state_for_registry(SUBJECTS, disappeared)

        record = reappeared["subjects"]["Werewolf"]
        self.assertEqual(record["subject_id"], 2)
        self.assertEqual(record["speaker_id"], "(S2)")
        self.assertEqual(record["wardrobe"]["upper"], "gray coat")
        self.assertEqual(list(reappeared["subjects"]).count("Werewolf"), 1)

    def test_dynamic_ids_are_allocated_above_registered_subjects(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state, added = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "The Stranger enters.",
            ["Stranger"],
            origin_segment=3,
        )

        self.assertEqual(added, ["Stranger"])
        self.assertEqual(state["subjects"]["Stranger"]["subject_id"], 3)
        self.assertEqual(state["subjects"]["Stranger"]["picture_ids"], [])
        self.assertEqual(
            minimax.derive_additional_subject_definitions(SUBJECTS, state),
            ["<Subject 3> is Stranger, N/A (S3), continued from <Video 1>."]
            if state["subjects"]["Stranger"]["gender"] == "N/A"
            else minimax.derive_additional_subject_definitions(SUBJECTS, state),
        )

    def test_dynamic_subject_gender_comes_from_formatter_for_explicit_male(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state, added = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "The Captain enters; she raises a hand.",
            ["Captain"],
            origin_segment=3,
            subject_genders={"Captain": "male"},
        )

        self.assertEqual(added, ["Captain"])
        self.assertEqual(state["subjects"]["Captain"]["gender"], "male")
        self.assertEqual(
            minimax.derive_additional_subject_definitions(SUBJECTS, state)[-1],
            "<Subject 3> is Captain, male (S3), continued from <Video 1>.",
        )

    def test_dynamic_subject_gender_comes_from_formatter_for_explicit_female(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state, added = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "The Captain enters; he raises a hand.",
            ["Captain"],
            origin_segment=3,
            subject_genders={"Captain": "female"},
        )

        self.assertEqual(added, ["Captain"])
        self.assertEqual(state["subjects"]["Captain"]["gender"], "female")
        self.assertEqual(
            minimax.derive_additional_subject_definitions(SUBJECTS, state)[-1],
            "<Subject 3> is Captain, female (S3), continued from <Video 1>.",
        )

    def test_dynamic_subject_unknown_gender_ignores_prose_and_omits_clause(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state, added = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "The Oracle enters; she watches the doorway.",
            ["The Oracle"],
            origin_segment=3,
            subject_genders={"The Oracle": "unknown"},
        )

        self.assertEqual(added, ["The Oracle"])
        self.assertEqual(state["subjects"]["The Oracle"]["gender"], "unknown")
        self.assertEqual(
            minimax.derive_additional_subject_definitions(SUBJECTS, state)[-1],
            "<Subject 3> is The Oracle (S3), continued from <Video 1>.",
        )

    def test_subject_gender_normalization_keeps_unspecified_values_unknown(self):
        for value in ("unknown", "unspecified", "", None):
            with self.subTest(value=value):
                self.assertEqual(minimax.normalize_subject_gender(value), "unknown")

    def test_two_distinct_subjects_keep_independent_wardrobes(self):
        prompt = {
            "subjects": {
                "Elias": {"name": "Elias", "wardrobe": wardrobe(upper="requested shirt")},
                "Werewolf": {"name": "Werewolf", "wardrobe": wardrobe(upper="requested fur")},
            }
        }
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            {"subjects": [
                visual_subject("Elias", {"upper": "red shirt"}),
                visual_subject("Werewolf", {"upper": "black fur"}),
            ]},
        )

        self.assertEqual(merged["subjects"]["Elias"]["wardrobe"]["upper"], "red shirt")
        self.assertEqual(merged["subjects"]["Werewolf"]["wardrobe"]["upper"], "black fur")

    def test_wardrobe_updates_follow_canonical_subject_after_alias_reappears(self):
        prompt = {
            "subjects": {
                "Werewolf": {
                    "name": "Werewolf",
                    "subject_id": 2,
                    "wardrobe": wardrobe(upper="old coat"),
                }
            }
        }
        cleared = minimax.merge_prompt_and_visual_end_state(
            prompt,
            {"subjects": [visual_subject("Werewolf", {"upper": "unknown"})]},
        )
        updated = minimax.merge_prompt_and_visual_end_state(
            cleared,
            {"subjects": [visual_subject("<Werewolf>", {"upper": "new coat"})]},
        )

        self.assertEqual(updated["subjects"]["Werewolf"]["wardrobe"]["upper"], "new coat")
        self.assertEqual(list(updated["subjects"]), ["Werewolf"])

    def test_wardrobe_is_preserved_by_missing_visual_observation(self):
        prompt = {
            "subjects": {
                "Werewolf": {
                    "name": "Werewolf",
                    "wardrobe": wardrobe(upper="old coat"),
                }
            }
        }
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            {"subjects": [visual_subject("Werewolf", {"upper": "unknown"})]},
        )
        merged = minimax.merge_prompt_and_visual_end_state(
            merged,
            {"subjects": []},
        )

        self.assertNotIn("wardrobe", merged["subjects"]["Werewolf"])

    def test_phase_derived_definitions_preserve_dynamic_subject_mapping(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state, _ = minimax.register_named_subject_hints(
            state,
            SUBJECTS,
            "Stranger enters.",
            ["Stranger"],
            origin_segment=3,
        )
        next_phase = minimax.continuity_state_for_registry(SUBJECTS, state)
        definitions = minimax.derive_additional_subject_definitions(SUBJECTS, next_phase)

        self.assertIn("Stranger", next_phase["subjects"])
        self.assertEqual(next_phase["subjects"]["Stranger"]["subject_id"], 3)
        self.assertTrue(any("<Subject 3>" in line for line in definitions))

    def test_checkpoint_round_trip_preserves_registry_mapping(self):
        state = minimax.new_generation_state({"subject_definitions": SUBJECTS})
        registry_state = minimax.continuity_state_for_registry(SUBJECTS)
        registry_state["subjects"]["Werewolf"]["wardrobe"]["upper"] = "gray coat"
        result = {
            "detailed_description": "[Shot 1] <Subject 2> Werewolf waits.",
            "overall_soundscape": "wind",
            "non_diegetic_music": "N/A",
        }
        minimax.record_completed_segment(
            state,
            1,
            "/tmp/segment-1.mp4",
            result,
            completed_beat_ids=set(),
            continuity_state=registry_state,
            subject_registry_state=registry_state,
        )

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json") as checkpoint:
            minimax.save_generation_state(state, checkpoint.name)
            loaded = minimax.load_generation_state(checkpoint.name)

        saved = loaded["segments"][0]["subject_registry_state"]
        self.assertEqual(saved["subjects"]["Elias"]["picture_ids"], [1])
        self.assertEqual(saved["subjects"]["Werewolf"]["subject_id"], 2)
        self.assertEqual(saved["subjects"]["Werewolf"]["wardrobe"]["upper"], "gray coat")
        self.assertEqual(
            loaded["segments"][0]["continuity_state"]["subjects"]["Werewolf"]["subject_id"],
            2,
        )

    def test_checkpoint_stores_recent_dialogue_exclusions(self):
        state = minimax.new_generation_state({"subject_definitions": SUBJECTS})
        result = {
            "detailed_description": (
                "[Shot 1] <Subject 1> Elias says: "
                "<d>[English] We need to leave.</d>"
            ),
            "overall_soundscape": "wind",
            "non_diegetic_music": "N/A",
        }

        minimax.record_completed_segment(
            state,
            1,
            "/tmp/segment-1.mp4",
            result,
            completed_beat_ids=set(),
        )

        self.assertEqual(
            state["recent_dialogue_exclusions"],
            ["We need to leave."],
        )

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json") as checkpoint:
            minimax.save_generation_state(state, checkpoint.name)
            loaded = minimax.load_generation_state(checkpoint.name)

        self.assertEqual(
            loaded["recent_dialogue_exclusions"],
            ["We need to leave."],
        )

    def test_structured_hard_cut_emits_one_canonical_subject_clause(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Elias"]["position"] = "beside the door"
        state["subjects"]["Elias"]["wardrobe"] = wardrobe(upper="blue shirt")
        current = {
            "detailed_description": "[Shot 1] <Subject 1> Elias stands beside the door.",
        }
        hard_cut = minimax.build_hard_cut_subject_continuity_from_state(
            SUBJECTS,
            current,
            state,
        )

        self.assertEqual(hard_cut.count("<Subject 1>"), 1)
        self.assertEqual(hard_cut.count("blue shirt"), 1)

    def test_h3_hard_cut_reminder_is_not_duplicated_when_authoritative_summary_exists(self):
        result = {
            "detailed_description": "[Shot 2] Elias crosses the room.",
            "overall_soundscape": "footsteps",
            "non_diegetic_music": "N/A",
        }
        summary = "Elias is wearing a blue shirt."
        prompt = minimax.build_h3_prompt(
            result,
            SUBJECTS,
            hard_cut_clothing_reiteration="Hard-cut subject continuity: Elias is wearing a blue shirt.",
            previous_state=summary,
            segment_number=2,
            conditioning_mode="clean_refresh",
        )

        description = prompt.split("detailed_description: ", 1)[1].split(
            "\n\noverall_soundscape:", 1
        )[0]
        self.assertEqual(description.count("blue shirt"), 1)
        self.assertNotIn("Hard-cut subject continuity", description)

    def test_feature_one_first_frame_anchor_remains_exact(self):
        result = {
            "detailed_description": "[Shot 1] Elias stands still.",
            "overall_soundscape": "quiet room",
            "non_diegetic_music": "N/A",
        }
        prompt = minimax.build_h3_prompt(
            result,
            SUBJECTS,
            segment_number=1,
            ff=True,
        )

        self.assertIn(
            "At 00:00.000, begin with the composition established by <Picture 1>.",
            prompt,
        )
        self.assertIn(
            "The opening frame should visually match <Picture 1> as closely as possible.",
            prompt,
        )

    def test_feature_two_rendered_wardrobe_updates_only_observed_slots(self):
        prompt = {
            "subjects": {
                "Werewolf": {
                    "name": "Werewolf",
                    "wardrobe": wardrobe(upper="requested red shirt", lower="requested jeans"),
                }
            }
        }
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            {"subjects": [visual_subject("Werewolf", {"upper": "torn black coat", "lower": "unknown"})]},
        )

        self.assertEqual(
            merged["subjects"]["Werewolf"]["wardrobe"],
            wardrobe(upper="torn black coat", lower="requested jeans"),
        )
        self.assertNotIn("clothing", merged["subjects"]["Werewolf"])

    def test_prompt_clothing_condition_cannot_bypass_canonical_wardrobe(self):
        prompt_state = {
            "subjects": {
                "Werewolf": {
                    "name": "Werewolf",
                    "wardrobe": wardrobe(),
                    "clothing_condition": (
                        "her torn sleeve snagged on a thorn and trousers stained with soil"
                    ),
                }
            }
        }

        merged = minimax.merge_prompt_and_visual_end_state(
            prompt_state,
            {"subjects": []},
        )

        self.assertNotIn("clothing_condition", merged["subjects"]["Werewolf"])
        self.assertNotIn("wardrobe", merged["subjects"]["Werewolf"])

    def test_checkpoint_canonicalizes_array_aliases_to_frozen_subject_identity(self):
        definitions = (
            "<Subject 1> is Daniel, a man referenced in <Picture 1>.\n"
            "<Subject 2> is Fred, referenced in <Picture 2>."
        )
        state = minimax.new_generation_state(
            minimax.build_run_config(5, 10, 0.5, 2, subject_definitions=definitions)
        )
        state["subject_registry_state"] = minimax.continuity_state_for_registry(
            definitions
        )
        state["continuity_state"] = {
            "subjects": [
                {"id": "<Subject 1> Daniel", "name": "Daniel", "speaker_id": "S1", "gender": "male"},
                {"id": "S1", "position": "near the door"},
                {"id": "<Subject 2> Fred", "name": "Fred", "speaker_id": "S2"},
            ],
            "subject_genders": {"Daniel": "female"},
        }

        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/generation_state.json"
            minimax.save_generation_state(state, path)
            saved = minimax.load_generation_state(path)

        subjects = saved["continuity_state"]["subjects"]
        self.assertIsInstance(subjects, list)
        self.assertEqual(len(subjects), 2)
        by_id = {subject["subject_id"]: subject for subject in subjects}
        self.assertEqual(by_id[1]["id"], "Subject 1")
        self.assertEqual(by_id[1]["name"], "Daniel")
        self.assertEqual(by_id[1]["speaker_id"], "(S1)")
        self.assertEqual(saved["continuity_state"]["subject_genders"]["Daniel"], "male")

    def test_subject_reference_id_accepts_speaker_and_display_name_forms(self):
        self.assertEqual(minimax._subject_reference_id("S1"), 1)
        self.assertEqual(minimax._subject_reference_id("Subject 1 Daniel"), 1)
        self.assertEqual(minimax._subject_reference_id("<Subject 1> Daniel"), 1)

    def test_malformed_nested_subject_alias_is_unwrapped(self):
        state = minimax.continuity_state_for_registry(
            "<Subject 1> is Daniel, referenced in <Picture 1>.",
            {"subjects": [{"Daniel": {"position": "by the door"}}]},
        )
        self.assertEqual(list(state["subjects"]), ["Daniel"])
        self.assertEqual(state["subjects"]["Daniel"]["subject_id"], 1)

    def test_final_h3_prompt_rejects_subject_tag_name_mismatch(self):
        definitions = (
            "<Subject 1> is Mark, referenced in <Picture 1>.\n"
            "<Subject 2> is Jill, referenced in <Picture 2>."
        )
        prompt = "<Subject 1> Jill waits."
        issues = minimax.validate_h3_subject_identity(prompt, definitions)
        self.assertTrue(any("paired with name 'Jill'" in issue for issue in issues))

        repaired = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 1] <Subject 1> Jill waits.",
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            definitions,
            segment_number=1,
            conditioning_mode="initial",
        )
        self.assertIn("<Subject 1> Mark waits.", repaired)

    def test_final_h3_prompt_rejects_name_speaker_mismatch(self):
        definitions = "<Subject 1> is Mark, referenced in <Picture 1>."
        issues = minimax.validate_h3_subject_identity(
            "Mark (S2) says: <d>[English] hello</d>",
            definitions,
        )
        self.assertTrue(any("not registered" in issue for issue in issues))

    def test_final_h3_prompt_repairs_swapped_speaker_ids_without_aborting(self):
        definitions = (
            "<Subject 1> is Alice, referenced in <Picture 1>.\n"
            "<Subject 2> is Beth, referenced in <Picture 2> (S2).\n"
            "<Subject 3> is Terri, referenced in <Picture 3> (S3)."
        )
        repaired = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 1] Beth (S1) enters the room. "
                    "Terri (S2) follows behind her."
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            definitions,
            segment_number=1,
            conditioning_mode="initial",
        )

        self.assertIn("Beth (S2)", repaired)
        self.assertIn("Terri (S3)", repaired)
        self.assertEqual(
            minimax.validate_h3_subject_identity(repaired, definitions),
            [],
        )

    def test_final_h3_prompt_separates_generic_timed_sentences(self):
        raw = (
            "Mark waits. At 00:02.800, Mark turns. "
            "At 01:03.125 seconds, Mark sits."
        )

        formatted = minimax.separate_h3_timed_sentences(raw)

        self.assertEqual(
            formatted,
            "Mark waits.\n\nAt 00:02.800, Mark turns.\n\n"
            "At 01:03.125 seconds, Mark sits.",
        )

    def test_final_h3_prompt_puts_every_at_timestamp_on_its_own_line(self):
        raw = (
            "[Shot 1] At 00:00.000, Mark waits."
            " Mark turns At 00:02.800, then sits At 01:03.125 seconds, quietly."
        )

        formatted = minimax.separate_h3_timed_sentences(raw)

        self.assertEqual(
            formatted,
            "[Shot 1]\n\nAt 00:00.000, Mark waits. Mark turns\n\n"
            "At 00:02.800, then sits\n\nAt 01:03.125 seconds, quietly.",
        )

    def test_final_h3_prompt_applies_timed_sentence_formatting_at_output(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 1] Mark waits. At 00:02.800, Mark turns."
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            "<Subject 1> is Mark, referenced in <Picture 1>.",
            segment_number=1,
            conditioning_mode="initial",
        )

        self.assertIn("waits.\n\nAt 00:02.800,", prompt)


if __name__ == "__main__":
    unittest.main()
