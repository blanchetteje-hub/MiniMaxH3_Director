import os
import unittest
from unittest import mock

import minimax


class PostmortemRegressionTests(unittest.TestCase):
    def test_director_coherence_requires_end_state_to_match_final_timed_action(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy steps into the courtyard.",
            (
                "At 00:00.000, Amy stands at the counter.\n\n"
                "At 00:02.000, Amy opens the door.\n\n"
                "At 00:04.000, Amy steps through the doorway into the courtyard.\n\n"
                "End continuity state: Amy stands at the counter."
            ),
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("MUST describe the state produced by the final timed action", prompt)
        self.assertIn("explicitly compare", prompt)

    def test_subject_resolver_prefers_explicit_species_over_generic_creature(self):
        messages = minimax.build_director_raw_subject_resolution_messages(
            "At 00:01.000, a dragon shifts outside while a griffin watches Amy."
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("If RAW says dragon, use Dragon1", prompt)
        self.assertIn("if RAW says griffin, use Griffin1", prompt)
        self.assertIn("Use CreatureN only when the type is truly unknown", prompt)

    def test_subject_resolver_reuses_single_known_functional_species(self):
        raw = (
            "At 00:00.000, Griffin waits beside the counter.\n\n"
            "At 00:02.000, Griffin lifts its mug.\n\n"
            "At 00:04.000, Griffin settles beside Amy.\n\n"
            "End continuity state: Griffin remains beside Amy."
        )

        def fake_llm(_messages, **_kwargs):
            return {
                "raw_scene": (
                    "At 00:00.000, Griffin waits beside the counter.\n\n"
                    "At 00:02.000, Griffin lifts its mug.\n\n"
                    "At 00:04.000, Griffin settles beside Amy."
                ),
                "subject_names": ["Griffin"],
            }

        resolved, names = minimax.resolve_director_raw_scene_subjects(
            raw,
            subject_definitions=(
                "<Subject 4> is Griffin1 (S4), continued from <Video 1>."
            ),
            llm_request=fake_llm,
            segment_seconds=5,
        )
        self.assertIn("Griffin1 waits beside the counter", resolved)
        self.assertIn("Griffin1 settles beside Amy", resolved)
        self.assertEqual(names, [])

    def test_new_functional_subject_definition_keeps_semantic_role(self):
        state, added = minimax.register_named_subject_hints(
            minimax.new_continuity_state(),
            "",
            "At 00:01.000, Griffin1 lands beside the counter.",
            ["Griffin1"],
            origin_segment=3,
        )
        self.assertEqual(added, ["Griffin1"])
        definitions = minimax.derive_additional_subject_definitions("", state)
        self.assertEqual(len(definitions), 1)
        self.assertIn("Griffin1 is a griffin.", definitions[0])

    def test_beat_validator_treats_missing_ordinary_prop_as_unknown(self):
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy stands at the bar.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy pours water from a chalice.",
            next_beat_job="Amy serves the next guest.",
            candidate_beat="Amy pours water from a chalice.",
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "ordinary story/staging prop is NOT unavailable merely because CURRENT STATE",
            prompt,
        )
        self.assertIn("Missing state is unknown, not absent", prompt)

    def test_visible_process_does_not_require_invented_completion_endpoint(self):
        finite_messages = minimax.build_beat_finite_endpoint_messages(
            "Amy polishes a crystal goblet by the hearth.",
            "Amy polishes a crystal goblet by the hearth.",
        )
        finite_prompt = finite_messages[-1]["content"]
        self.assertIn(
            "satisfied by visibly performing an activity/process",
            finite_prompt,
        )
        self.assertIn("Do not invent a completion endpoint", finite_prompt)

        validator_messages = minimax.build_beat_validation_messages(
            previous_final_beat="Amy stands by the hearth.",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy polishes a crystal goblet by the hearth.",
            next_beat_job="A guest arrives.",
            candidate_beat="Amy polishes a crystal goblet by the hearth.",
        )
        self.assertIn(
            "visible performance of an activity/process itself",
            validator_messages[-1]["content"],
        )

    def test_story_setting_extractor_does_not_promote_relative_action_labels(self):
        messages = minimax.build_story_setting_description_messages(
            "Amy enters through the front door and later locks the back door.",
            "tavern",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("Relative action wording is not proof of distinct static architecture", prompt)
        self.assertIn("front/back/side door", prompt)
        self.assertIn("entrance door rather than back door", prompt)

    def test_director_prompt_separates_physical_prerequisites(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=3,
            conditioning_mode="continuation",
        )
        self.assertIn("Budget enough visible time for every physical step", rules)
        self.assertIn("give that prerequisite its own earlier timed micro-beat", rules)
        self.assertIn("instead of compressing both steps into one timestamp", rules)

    def test_director_prompt_keeps_invented_staging_economical(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=4,
            conditioning_mode="continuation",
        )
        self.assertIn("Keep invented staging economical", rules)
        self.assertIn("Do not add optional secondary reactions", rules)
        self.assertIn("extra object/substance motion", rules)

    def test_director_transfer_rule_is_generic_and_tracks_source_destination(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=4,
            conditioning_mode="continuation",
        )
        self.assertIn("For any transfer", rules)
        self.assertIn("explicitly identify the source and destination", rules)
        self.assertIn("what is transferred is at the source", rules)
        self.assertNotIn("pouring or transferring between containers", rules)

        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy transfers the drink to the guest.",
            (
                "At 00:00.000, Amy holds a cup.\n\n"
                "At 00:06.500, Amy transfers the drink.\n\n"
                "End continuity state: The guest has the drink."
            ),
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("For any transfer", prompt)
        self.assertIn("explicit source and destination", prompt)
        self.assertIn("transferred material or object", prompt)
        self.assertNotIn("pouring between containers", prompt)

    def test_director_coherence_preserves_assigned_transfer_destination_and_final_prop(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy pours a special brew into a crystal cup and hands it to Dragon1.",
            (
                "At 00:00.000, Amy stands by the shelf.\n\n"
                "At 00:04.000, Amy lifts a crystal cup.\n\n"
                "At 00:06.000, Amy pours the brew onto Dragon1's scales.\n\n"
                "At 00:07.000, Amy hands the crystal cup to Dragon1.\n"
                "End continuity state: Dragon1 sits on the stool."
            ),
            prop_ledger={},
            static_setting_description="Lanterns hang above each table.",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("transfer roles/results are semantic constraints", prompt)
        self.assertIn("different target, body, surface, or container", prompt)
        self.assertIn("movable prop acquired, transferred", prompt)
        self.assertIn("STATIC SETTING AUTHORITY", prompt)
        self.assertIn("Lanterns hang above each table.", prompt)

    def test_director_rules_avoid_source_less_material_and_helper_props(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=5,
            conditioning_mode="continuation",
        )
        self.assertIn("Do not invent source-less liquid", rules)
        self.assertIn("must not redirect that transfer or result", rules)
        self.assertIn(
            "Do not invent an extra support, container, utensil, or other helper prop",
            rules,
        )

    def test_director_request_receives_static_setting_authority(self):
        messages, _tokens, _recent = minimax.build_generation_messages(
            director_rules="rules",
            story="story",
            beats=["Amy turns off a lantern.", "Amy leaves."],
            completed_beat_ids=set(),
            recent_results=[],
            current_segment=1,
            total_segments=2,
            segment_length=8,
            total_length=16,
            static_setting_description="Lanterns hang above each table.",
        )
        prompt = messages[-1]["content"]
        self.assertIn("STATIC SETTING AUTHORITY", prompt)
        self.assertIn("Lanterns hang above each table.", prompt)
        self.assertIn("Do not relocate, duplicate, replace, or restyle", prompt)
        self.assertIn("Do not force off-camera fixtures into the frame", prompt)

    def test_director_timing_validator_is_narrow_and_has_no_fixed_minimum(self):
        messages = minimax.build_director_raw_scene_timing_messages(
            (
                "At 00:00.000, an elf enters through the doorway.\n\n"
                "At 00:01.500, the elf sits at the far table.\n\n"
                "End continuity state: the elf is seated."
            )
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("can visibly occur within the time available", prompt)
        self.assertIn("one continuous shot", prompt)
        self.assertIn("Do not impose a fixed minimum interval", prompt)
        self.assertIn("first clearly compressed transition", prompt)
        self.assertIn("name its two timestamps", prompt)

    def test_director_rules_require_frame_zero_microbeat(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=3,
            conditioning_mode="continuation",
        )
        self.assertIn(
            "first timed micro-beat MUST be at 00:00.000",
            rules,
        )
        self.assertIn("00:00.000 is an inherited-frame anchor", rules)
        self.assertIn("guide—not PREVIOUS SHOT END—owns the visible frame-0 composition", rules)
        self.assertIn("supplied opening guide is the visual authority", rules)
        self.assertIn("Begin CURRENT BEAT at the next natural timestamp", rules)
        self.assertIn("one 8-second video segment", rules)
        self.assertNotIn("8.916", rules)

    def test_director_structure_rejects_nonzero_first_timestamp(self):
        errors = minimax._director_raw_scene_structure_errors(
            (
                "At 00:01.000, Amy stands at the counter.\n\n"
                "At 00:06.500, Amy turns toward the door.\n\n"
                "End continuity state: Amy stands at the counter facing the door."
            ),
            segment_seconds=8,
        )
        self.assertTrue(errors)
        self.assertIn("00:00.000", errors[0])

    def test_frame_zero_state_anchor_is_allowed(self):
        errors = minimax._director_raw_scene_structure_errors(
            (
                "At 00:00.000, Amy remains beside the open door.\n\n"
                "At 00:02.000, Amy turns toward the counter.\n\n"
                "At 00:06.500, Amy walks to the counter.\n\n"
                "End continuity state: Amy stands at the counter."
            ),
            segment_seconds=8,
        )
        self.assertEqual(errors, [])

    def test_director_coherence_receives_previous_shot_end(self):
        messages = minimax.build_director_raw_scene_coherence_messages(
            "Amy opens the tavern door.",
            (
                "At 00:00.000, Amy opens the tavern door.\n\n"
                "At 00:06.500, Amy stands beside the open door.\n\n"
                "End continuity state: Amy stands beside the open door."
            ),
            previous_shot_end="Amy stands at the oak counter.",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("PREVIOUS SHOT END\nAmy stands at the oak counter.", prompt)
        self.assertIn("inherited 00:00.000 frame must be reachable", prompt)
        self.assertIn(
            "Do NOT require a participant introduced by CURRENT BEAT",
            prompt,
        )
        self.assertIn(
            "do not reject a new CURRENT BEAT participant merely because it enters after",
            prompt,
        )

    def test_prop_ledger_copies_forward_and_updates_only_observed_props(self):
        committed = {
            "mug_1": {
                "kind": "mug",
                "owner": "Goblin1",
                "holder": "N/A",
                "location": "on the table in front of Goblin1",
                "contents": "empty",
                "status": "present",
            },
            "basket_1": {
                "kind": "basket",
                "owner": "Amy",
                "holder": "Amy",
                "location": "N/A",
                "contents": "N/A",
                "status": "present",
            },
        }
        observed = {
            "mug_1": {
                "kind": "mug",
                "owner": "Goblin1",
                "holder": "Goblin1",
                "location": "N/A",
                "contents": "beer",
                "status": "present",
            },
        }
        merged = minimax.merge_prop_ledger(committed, observed)
        self.assertEqual(merged["mug_1"]["holder"], "Goblin1")
        self.assertEqual(merged["mug_1"]["contents"], "beer")
        self.assertEqual(merged["basket_1"], committed["basket_1"])

    def test_combined_continuity_schema_accepts_persistent_prop_ledger(self):
        candidate = {
            "props": {
                "glass_1": {
                    "kind": "glass",
                    "owner": "Dragon1",
                    "holder": "N/A",
                    "location": "on the bar",
                    "contents": "empty",
                    "status": "present",
                }
            }
        }
        self.assertIs(
            minimax._validate_combined_continuity_schema(candidate),
            candidate,
        )

    def test_source_owned_item_state_overrides_prop_ledger(self):
        ledger = {
            "flashlight_1": {
                "kind": "flashlight",
                "owner": "Amy",
                "holder": "N/A",
                "location": "on the kitchen table",
                "contents": "N/A",
                "status": "present",
            }
        }
        held = minimax.apply_authoritative_prop_state_effects(
            ledger,
            [{
                "op": "set_item_state",
                "entity": "flashlight",
                "owner": "Amy",
                "value": "held",
            }],
        )
        self.assertEqual(held["flashlight_1"]["holder"], "Amy")
        self.assertEqual(held["flashlight_1"]["location"], "N/A")
        self.assertEqual(held["flashlight_1"]["status"], "present")

        lost = minimax.apply_authoritative_prop_state_effects(
            held,
            [{
                "op": "set_item_state",
                "entity": "flashlight",
                "owner": "Amy",
                "value": "lost",
            }],
        )
        self.assertEqual(lost["flashlight_1"]["holder"], "N/A")
        self.assertEqual(lost["flashlight_1"]["location"], "N/A")
        self.assertEqual(lost["flashlight_1"]["status"], "lost")

    def test_prop_staging_micro_prompt_adds_only_missing_availability(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append((messages, kwargs))
            return {
                "staging": (
                    "A clean mug is already on the table in front of Goblin1."
                )
            }

        staging = minimax.request_director_prop_staging(
            "Amy pours beer into Goblin1's mug.",
            {},
            previous_shot_end="Goblin1 sits at the table.",
            llm_request=fake_llm,
        )
        self.assertEqual(
            staging,
            "A clean mug is already on the table in front of Goblin1.",
        )
        self.assertEqual(
            calls[0][1]["history_metadata"]["purpose"],
            "director_prop_staging",
        )
        prompt = "\n".join(message["content"] for message in calls[0][0])
        self.assertIn("PROP LEDGER", prompt)
        self.assertIn("Do not rewrite the Beat", prompt)
        self.assertIn("do not invent architecture/storage", prompt)
        self.assertIn(
            "owned by or held by another subject does NOT count as generic available",
            prompt,
        )
        self.assertIn(
            "Prefer a distinct ordinary instance over repurposing another subject's owned prop",
            prompt,
        )

    def test_director_owned_prop_is_not_shared_inventory(self):
        rules = minimax.build_director_rules(
            total_length=48,
            segment_length=8,
            total_segments=6,
            subject_definitions="",
            segment_number=3,
            conditioning_mode="continuation",
        )
        self.assertIn(
            "do not treat it as shared inventory or repurpose it for another subject",
            rules,
        )
        self.assertIn(
            "unless CURRENT BEAT explicitly authorizes that use or transfer",
            rules,
        )

    def test_prop_staging_skips_non_prop_beat_without_llm_call(self):
        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("prop staging LLM should not run")

        staging = minimax.request_director_prop_staging(
            "Amy smiles at Goblin1 across the room.",
            {},
            llm_request=fail_if_called,
        )
        self.assertEqual(staging, "")

    def test_dynamic_subject_definition_survives_plain_name_in_malformed_prose(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Creature1 (S2), continued from <Video 1>. "
            "Creature1 is a creature."
        )
        filtered, _description = minimax._filter_h3_subject_definitions(
            definitions,
            {1},
            (
                'At 00:00.000, "Amy stands beside Creature1 at the counter. '
                'At 00:06.500, "Creature1 takes a sip.'
            ),
        )
        self.assertIn("<Subject 2> is Creature1", filtered)

    def test_h3_no_dialogue_constraint_is_natural_language(self):
        constraint = minimax.format_h3_spoken_dialogue_constraint(
            "At 00:00.000, Amy wipes the counter."
        )
        self.assertEqual(
            constraint,
            "No intelligible spoken dialogue is heard in this segment.",
        )
        self.assertNotIn("SPOKEN DIALOGUE", constraint)

    def test_new_dynamic_subject_does_not_claim_previous_video(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Centaur1 (S2), continued from <Video 1>. "
            "Centaur1 is a centaur."
        )
        rendered = minimax._append_video_origin_to_h3_subject_definitions(
            definitions,
            previous_visible_subject_ids={1},
        )
        centaur_line = next(
            line for line in rendered.splitlines()
            if line.startswith("<Subject 2>")
        )
        self.assertNotIn("continued from <Video 1>", centaur_line)
        self.assertIn("Centaur1 is a centaur.", centaur_line)
        self.assertIn(2, minimax.parse_subject_registry(rendered))

        filtered, _ = minimax._filter_h3_subject_definitions(
            rendered,
            {1},
            "At 00:01.000, Centaur1 enters the room.",
        )
        self.assertIn("<Subject 2> is Centaur1", filtered)

    def test_previous_visible_dynamic_subject_has_one_video_origin(self):
        definitions = (
            "<Subject 2> is Dragon1 (S2), continued from <Video 1>. "
            "Dragon1 is a dragon. continued from <Video 1>."
        )
        rendered = minimax._append_video_origin_to_h3_subject_definitions(
            definitions,
            previous_visible_subject_ids={2},
        )
        self.assertEqual(
            rendered.lower().count("continued from <video 1>"),
            1,
        )

    def test_subject_resolver_canonicalizes_functional_end_state(self):
        raw = (
            "At 00:00.000, Amy stands at the counter.\n\n"
            "At 00:01.000, a centaur enters from the left.\n\n"
            "At 00:06.200, the centaur sits on a low stool.\n\n"
            "End continuity state: The tall centaur sits across from Amy."
        )

        def fake_llm(_messages, **_kwargs):
            return {
                "raw_scene": (
                    "At 00:00.000, Amy stands at the counter.\n\n"
                    "At 00:01.000, Centaur1 enters from the left.\n\n"
                    "At 00:06.200, Centaur1 sits on a low stool."
                ),
                "subject_names": ["Centaur1"],
            }

        resolved, names = minimax.resolve_director_raw_scene_subjects(
            raw,
            llm_request=fake_llm,
            segment_seconds=8,
        )
        self.assertEqual(names, ["Centaur1"])
        self.assertIn(
            "End continuity state: The tall Centaur1 sits across from Amy.",
            resolved,
        )

    def test_final_timed_subject_is_carried_into_incomplete_end_state(self):
        raw = (
            "At 00:00.000, Amy stands behind the bar.\n\n"
            "At 00:06.917, Goblin1 sets mug_1 on the counter, nods at Amy, "
            "and steps back toward the hearth.\n"
            "End continuity state: Amy stands behind the bar."
        )
        repaired, carried = minimax._director_carry_forward_final_subjects(
            raw,
            subject_definitions=(
                "<Subject 1> is Amy, referenced in <Picture 1>.\n"
                "<Subject 2> is Goblin1 (S2). Goblin1 is a goblin."
            ),
        )
        self.assertEqual(carried, ["Goblin1"])
        self.assertIn(
            "Goblin1 remains present in the state established by the final timed action",
            repaired,
        )
        self.assertIn("steps back toward the hearth", repaired)
        self.assertEqual(repaired.count("End continuity state:"), 1)

    def test_final_timed_subject_explicit_exit_is_not_carried_forward(self):
        raw = (
            "At 00:00.000, Amy stands behind the bar.\n\n"
            "At 00:06.917, Goblin1 exits through the tavern doorway.\n"
            "End continuity state: Amy stands behind the bar."
        )
        repaired, carried = minimax._director_carry_forward_final_subjects(
            raw,
            subject_definitions=(
                "<Subject 1> is Amy, referenced in <Picture 1>.\n"
                "<Subject 2> is Goblin1 (S2). Goblin1 is a goblin."
            ),
        )
        self.assertEqual(carried, [])
        self.assertEqual(repaired, raw)

    def test_newly_resolved_subject_can_be_carried_before_registry_append(self):
        raw = (
            "At 00:00.000, Amy stands at the counter.\n\n"
            "At 00:06.500, Elf1 sits at the back table.\n"
            "End continuity state: Amy stands at the counter."
        )
        repaired, carried = minimax._director_carry_forward_final_subjects(
            raw,
            subject_definitions="<Subject 1> is Amy, referenced in <Picture 1>.",
            resolved_subject_names=["Elf1"],
        )
        self.assertEqual(carried, ["Elf1"])
        self.assertIn("Elf1 remains present", repaired)

    def test_story_to_beats_preserves_explicit_enumerations(self):
        messages = minimax.build_story_to_beats_messages(
            "A barkeep serves magical patrons.",
            (
                "Amy watches the goblin, centaur, dragon, and unicorn "
                "settle around the room."
            ),
            1,
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("Preserve explicit source enumerations", prompt)
        self.assertIn("do not replace a stated list with", prompt)
        self.assertIn("instead of collapsing them into a", prompt)

        validator = minimax.build_beat_validation_messages(
            previous_final_beat="",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy watches the goblin, centaur, dragon, and unicorn settle.",
            next_beat_job="",
            candidate_beat="Amy watches each magical patron settle.",
        )
        self.assertIn(
            "candidate must preserve each listed identity",
            validator[-1]["content"],
        )

    def test_story_beat_repair_preserves_explicit_enumerations(self):
        messages = minimax.build_story_beat_repair_messages(
            "Amy watches the goblin, centaur, dragon, and unicorn settle.",
            6,
            6,
            "Amy watches each magical patron settle.",
            "The explicit participant list was collapsed.",
            ["Amy finishes counting coins."],
            "",
        )
        prompt = messages[-1]["content"]
        self.assertIn(
            "Preserve any explicit FULL STORY enumeration",
            prompt,
        )
        self.assertIn("do not replace the list with a", prompt)

    def test_empty_phase_two_continuity_skips_llm(self):
        calls = []

        def fake_llm(*args, **kwargs):
            calls.append((args, kwargs))
            return "should not be called"

        opening = minimax.request_continuity_opening_state(
            {"version": 5},
            {},
            llm_request=fake_llm,
        )
        self.assertEqual(opening, "")
        self.assertEqual(calls, [])

    def test_final_h3_prompt_contains_explicit_continuous_take_contract(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 1] At 00:00.000, a lantern glows on the counter. "
                    "At 00:04.000, the camera pans toward the door."
                ),
                "overall_soundscape": "soft room tone",
                "non_diegetic_music": "quiet strings",
            },
            "",
            segment_number=2,
            conditioning_mode="continuation",
        )
        self.assertIn(
            "Stage this segment as one continuous camera take with no cuts or cutaways",
            prompt,
        )
        self.assertIn("reframe only through continuous camera movement", prompt)

    def test_character_reference_numbering_uses_active_picture_count(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Amy"] = minimax.new_subject_continuity_record({
            "subject_id": 1,
            "name": "Amy",
            "picture_ids": [1],
            "picture_id": 1,
            "canonical_description": "Amy is an adult woman wearing a blue dress.",
        })
        state["subjects"]["Amy"]["wardrobe"]["upper"] = "a red blouse"
        definitions = "<Subject 1> is Amy, referenced in <Picture 1>."

        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="amy_identity.png",
        ), mock.patch.object(
            minimax,
            "render_character_reference_image",
            return_value="/tmp/video/state/amy_clothing.png",
        ) as render:
            refs, changed = minimax.ensure_character_reference_images(
                "Amy stands behind the bar.",
                definitions,
                state,
                {},
                1,
                0.5,
                6,
                subject_descriptions={
                    "Amy": "Amy is an adult woman wearing a blue dress."
                },
            )

        self.assertEqual(changed, ["Amy"])
        self.assertEqual(refs["Amy"]["picture_number"], 2)
        self.assertEqual(refs["Amy"]["image_name"], "amy_clothing.png")
        self.assertEqual(
            refs["Amy"]["image_path"],
            "/tmp/video/state/amy_clothing.png",
        )
        self.assertIn(
            "Amy is currently wearing a red blouse",
            render.call_args.args[1],
        )
        self.assertEqual(
            render.call_args.kwargs["identity_image_name"],
            "amy_identity.png",
        )
        self.assertEqual(refs["Amy"]["authority"], "clothing_only")

    def test_dynamic_character_reference_owns_identity_and_current_appearance(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Dragon1"] = minimax.new_subject_continuity_record({
            "subject_id": 4,
            "name": "Dragon1",
            "canonical_description": "Dragon1 is a dragon.",
        })

        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="",
        ), mock.patch.object(
            minimax,
            "render_character_reference_image",
            return_value="/tmp/video/state/dragon_v001.png",
        ) as render:
            refs, changed = minimax.ensure_character_reference_images(
                "Dragon1 enters, scales glittering like obsidian.",
                "<Subject 4> is Dragon1 (S4). Dragon1 is a dragon.",
                state,
                {},
                1,
                0.5,
                6,
            )

        self.assertEqual(changed, ["Dragon1"])
        self.assertEqual(refs["Dragon1"]["authority"], "identity_and_clothing")
        self.assertEqual(render.call_args.kwargs["identity_image_name"], "")
        definitions = minimax.append_character_reference_definitions(
            "<Subject 4> is Dragon1 (S4). Dragon1 is a dragon.",
            refs,
        )
        self.assertIn(
            "Dragon1 is referenced in <Picture 2> for identity and current appearance.",
            definitions,
        )
        self.assertIn(
            "<Picture 2> defines Dragon1's identity, physical appearance",
            definitions,
        )

    def test_dynamic_character_outfit_update_reuses_generated_identity_picture(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Traveler1"] = minimax.new_subject_continuity_record({
            "subject_id": 2,
            "name": "Traveler1",
            "canonical_description": "Traveler1 is a traveler.",
        })
        existing = {
            "Traveler1": {
                "name": "Traveler1",
                "picture_number": 2,
                "image_name": "traveler_v001.png",
                "image_path": "/tmp/video/state/traveler_v001.png",
                "signature": "old",
                "version": 1,
                "description": "Traveler1 is a traveler wearing a brown coat.",
                "wardrobe": {"upper": "a brown coat"},
                "clothing_condition": "",
                "authority": "identity_and_clothing",
            }
        }
        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="",
        ), mock.patch.object(
            minimax,
            "stage_character_reference_image",
            return_value="traveler_v001.png",
        ) as stage, mock.patch.object(
            minimax,
            "render_character_reference_image",
            return_value="/tmp/video/state/traveler_v002.png",
        ) as render:
            refs, changed = minimax.ensure_character_reference_images(
                "Traveler1 keeps walking.",
                "<Subject 2> is Traveler1 (S2). Traveler1 is a traveler.",
                state,
                existing,
                1,
                0.5,
                6,
                prior_detailed_description="Traveler1's brown coat is torn.",
            )

        self.assertEqual(changed, ["Traveler1"])
        stage.assert_called_once()
        self.assertEqual(
            render.call_args.kwargs["identity_image_name"],
            "traveler_v001.png",
        )
        self.assertEqual(refs["Traveler1"]["authority"], "identity_and_clothing")

    def test_prompt_only_reference_planner_versions_without_rendering(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Traveler1"] = minimax.new_subject_continuity_record({
            "subject_id": 2,
            "name": "Traveler1",
            "canonical_description": "Traveler1 is a traveler.",
        })
        jobs = []

        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="",
        ), mock.patch.object(
            minimax,
            "render_character_reference_image",
        ) as render:
            refs, changed = minimax.plan_character_reference_images(
                "Traveler1 enters the room.",
                "<Subject 2> is Traveler1 (S2). Traveler1 is a traveler.",
                state,
                {},
                1,
                0.5,
                6,
                segment_number=1,
                reference_jobs=jobs,
                file_token="testrun",
            )
            refs, changed2 = minimax.plan_character_reference_images(
                "Traveler1 keeps walking.",
                "<Subject 2> is Traveler1 (S2). Traveler1 is a traveler.",
                state,
                refs,
                1,
                0.5,
                6,
                segment_number=2,
                reference_jobs=jobs,
                file_token="testrun",
                prior_detailed_description="Traveler1's coat is torn.",
            )

        render.assert_not_called()
        self.assertEqual(changed, ["Traveler1"])
        self.assertEqual(changed2, ["Traveler1"])
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["version"], 1)
        self.assertEqual(jobs[1]["version"], 2)
        self.assertNotEqual(
            jobs[0]["output_reference"]["image_name"],
            jobs[1]["output_reference"]["image_name"],
        )
        self.assertEqual(
            jobs[1]["identity_source"]["kind"],
            "generated_reference",
        )
        self.assertEqual(
            jobs[1]["identity_source"]["reference"]["version"],
            1,
        )
        self.assertEqual(refs["Traveler1"]["version"], 2)

    def test_character_reference_picture_number_stays_stable_on_outfit_change(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Amy"] = minimax.new_subject_continuity_record({
            "subject_id": 1,
            "name": "Amy",
            "picture_ids": [1],
            "picture_id": 1,
            "canonical_description": "Amy is an adult woman.",
        })
        state["subjects"]["Amy"]["wardrobe"]["upper"] = "a green tunic"
        existing = {
            "Amy": {
                "name": "Amy",
                "picture_number": 2,
                "image_name": "amy_v001.png",
                "signature": "old",
                "version": 1,
                "description": "old",
            }
        }
        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="amy_identity.png",
        ), mock.patch.object(
            minimax,
            "render_character_reference_image",
            return_value="/tmp/video/state/amy_v002.png",
        ):
            refs, changed = minimax.ensure_character_reference_images(
                "Amy enters the room.",
                "<Subject 1> is Amy, referenced in <Picture 1>.",
                state,
                existing,
                1,
                0.5,
                6,
                prior_detailed_description="Amy changes into a green tunic.",
            )
        self.assertEqual(changed, ["Amy"])
        self.assertEqual(refs["Amy"]["picture_number"], 2)
        self.assertEqual(refs["Amy"]["version"], 2)

    def test_visual_wardrobe_drift_does_not_regenerate_clothing_picture(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Amy"] = minimax.new_subject_continuity_record({
            "subject_id": 1,
            "name": "Amy",
            "picture_ids": [1],
            "picture_id": 1,
            "canonical_description": "Amy is an adult woman.",
        })
        state["subjects"]["Amy"]["wardrobe"]["upper"] = "a denim corset"
        state["subjects"]["Amy"]["wardrobe"]["lower"] = "dark jeans"
        existing = {
            "Amy": {
                "name": "Amy",
                "picture_number": 2,
                "image_name": "amy_v001.png",
                "image_path": "/tmp/video/state/amy_v001.png",
                "signature": "stable",
                "version": 1,
                "description": (
                    "Amy is an adult woman. Amy is currently wearing "
                    "a medieval barmaid dress."
                ),
                "wardrobe": {"upper": "a medieval barmaid dress"},
                "clothing_condition": "",
            }
        }
        with mock.patch.object(
            minimax,
            "render_character_reference_image",
        ) as render:
            refs, changed = minimax.ensure_character_reference_images(
                "Amy serves a drink.",
                "<Subject 1> is Amy, referenced in <Picture 1>.",
                state,
                existing,
                1,
                0.5,
                6,
                prior_detailed_description="Amy served a drink at the bar.",
            )
        self.assertEqual(changed, [])
        self.assertEqual(refs["Amy"]["version"], 1)
        render.assert_not_called()

    def test_explicit_clothing_damage_regenerates_from_intended_outfit(self):
        state = minimax.new_continuity_state()
        state["subjects"]["Amy"] = minimax.new_subject_continuity_record({
            "subject_id": 1,
            "name": "Amy",
            "picture_ids": [1],
            "picture_id": 1,
            "canonical_description": "Amy is an adult woman.",
        })
        state["subjects"]["Amy"]["wardrobe"]["upper"] = "a denim corset"
        existing = {
            "Amy": {
                "name": "Amy",
                "picture_number": 2,
                "image_name": "amy_v001.png",
                "image_path": "/tmp/video/state/amy_v001.png",
                "signature": "old",
                "version": 1,
                "description": (
                    "Amy is an adult woman. Amy is currently wearing "
                    "a medieval barmaid dress."
                ),
                "wardrobe": {"upper": "a medieval barmaid dress"},
                "clothing_condition": "",
            }
        }
        with mock.patch.object(
            minimax,
            "subject_identity_reference_image",
            return_value="amy_identity.png",
        ), mock.patch.object(
            minimax,
            "render_character_reference_image",
            return_value="/tmp/video/state/amy_v002.png",
        ) as render:
            refs, changed = minimax.ensure_character_reference_images(
                "Amy keeps moving.",
                "<Subject 1> is Amy, referenced in <Picture 1>.",
                state,
                existing,
                1,
                0.5,
                6,
                prior_detailed_description=(
                    "Amy's medieval barmaid dress is torn and stained."
                ),
            )
        self.assertEqual(changed, ["Amy"])
        self.assertEqual(refs["Amy"]["version"], 2)
        target = render.call_args.args[1]
        self.assertIn("medieval barmaid dress", target)
        self.assertIn("torn and stained", target)
        self.assertNotIn("denim corset", target)

    def test_character_reference_uses_13_by_19_portrait_resolution(self):
        workflow = minimax.prepare_character_reference_workflow(
            "Amy is an adult woman wearing a medieval barmaid dress.",
            0.5,
            steps=6,
            picture_number=2,
        )
        _conditioning_id, conditioning = minimax.find_workflow_node(
            workflow,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            "test character reference workflow",
            "MiniMaxH3ReferenceToVideo",
        )
        width = conditioning["inputs"]["width"]
        height = conditioning["inputs"]["height"]
        self.assertIsInstance(width, int)
        self.assertIsInstance(height, int)
        self.assertLess(width, height)
        self.assertEqual(
            width * minimax.CHARACTER_REFERENCE_ASPECT_HEIGHT,
            height * minimax.CHARACTER_REFERENCE_ASPECT_WIDTH,
        )

        location = minimax.prepare_location_reference_workflow(
            "A medieval tavern.",
            0.5,
            steps=6,
        )
        _location_id, location_conditioning = minimax.find_workflow_node(
            location,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            "test location reference workflow",
            "MiniMaxH3ReferenceToVideo",
        )
        self.assertIsInstance(location_conditioning["inputs"]["width"], list)
        self.assertIsInstance(location_conditioning["inputs"]["height"], list)

    def test_character_reference_can_create_loadimage_above_six(self):
        workflow = {
            "1": {
                "inputs": {},
                "class_type": "MiniMaxH3ReferenceToVideo",
                "_meta": {"title": minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME},
            }
        }
        for number in range(1, 7):
            workflow[str(number + 1)] = {
                "inputs": {"image": "0.png"},
                "class_type": "LoadImage",
                "_meta": {"title": f"Reference Image {number}"},
            }
        with mock.patch.object(
            minimax,
            "stage_character_reference_image",
            return_value="dragon.png",
        ):
            attached = minimax.attach_character_reference_images(
                workflow,
                "test workflow",
                "initial",
                {
                    "Dragon": {
                        "name": "Dragon",
                        "picture_number": 7,
                        "image_name": "dragon.png",
                        "image_path": "/tmp/video/state/dragon.png",
                        "signature": "x",
                        "version": 1,
                        "description": "Dragon is a dragon.",
                    }
                },
            )
        self.assertIn(7, attached)
        generated_id = attached[7]
        self.assertEqual(
            workflow[generated_id]["_meta"]["title"],
            "Generated Reference Image 7",
        )
        conditioner = workflow["1"]["inputs"]
        self.assertEqual(
            conditioner["ref_images.ref_image_6"],
            [generated_id, 0],
        )

    def test_clothing_only_picture_definition_is_kept_for_visible_subject(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Picture 2> references only the clothing that Amy is currently wearing."
        )
        filtered, _description = minimax._filter_h3_subject_definitions(
            definitions,
            {1},
            "Amy stands behind the bar.",
        )
        self.assertIn("<Subject 1> is Amy", filtered)
        self.assertIn(
            "<Picture 2> references only the clothing that Amy is currently wearing.",
            filtered,
        )

    def test_dynamic_identity_picture_definition_is_kept_for_visible_subject(self):
        definitions = (
            "<Subject 4> is Dragon1 (S4). Dragon1 is a dragon. "
            "Dragon1 is referenced in <Picture 5> for identity and current appearance.\n"
            "<Picture 5> defines Dragon1's identity, physical appearance, "
            "species/distinguishing traits, and current clothing."
        )
        filtered, _description = minimax._filter_h3_subject_definitions(
            definitions,
            {4},
            "At 00:01.000, Dragon1 enters through the doorway.",
        )
        self.assertIn("<Subject 4> is Dragon1", filtered)
        self.assertIn(
            "<Picture 5> defines Dragon1's identity, physical appearance",
            filtered,
        )

    def test_state_media_paths_live_under_output_video_state(self):
        self.assertEqual(
            minimax.STATE_MEDIA_OUTPUT,
            os.path.join(minimax.VIDEO_OUTPUT, "state"),
        )
        workflow = minimax.prepare_character_reference_workflow(
            "Amy is an adult woman wearing a red blouse.",
            0.5,
            steps=6,
            picture_number=2,
        )
        _node_id, save = minimax.find_workflow_node(
            workflow,
            minimax.SAVE_VIDEO_NODE_NAME,
            "test character reference workflow",
            "SaveVideo",
        )
        self.assertTrue(
            save["inputs"]["filename_prefix"].startswith(
                "video/state/character_reference"
            )
        )
        location = minimax.prepare_location_reference_workflow(
            "A stone tavern.",
            0.5,
            steps=6,
        )
        _location_id, location_save = minimax.find_workflow_node(
            location,
            minimax.SAVE_VIDEO_NODE_NAME,
            "test location reference workflow",
            "SaveVideo",
        )
        self.assertEqual(
            location_save["inputs"]["filename_prefix"],
            "video/state/location_reference",
        )

    def test_character_reference_workflow_conditions_on_identity_picture(self):
        workflow = minimax.prepare_character_reference_workflow(
            "Amy is an adult woman currently wearing a red blouse.",
            0.5,
            steps=6,
            picture_number=2,
            identity_image_name="amy_identity.png",
        )
        _conditioning_id, conditioning = minimax.find_workflow_node(
            workflow,
            minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
            "test character reference workflow",
            "MiniMaxH3ReferenceToVideo",
        )
        identity_id, identity = minimax.find_workflow_node(
            workflow,
            minimax.REFERENCE_IMAGE_NODE_NAMES[0],
            "test character reference workflow",
            "LoadImage",
        )
        self.assertEqual(identity["inputs"]["image"], "amy_identity.png")
        self.assertEqual(
            conditioning["inputs"]["ref_images.ref_image_0"],
            [identity_id, 0],
        )
        for key in conditioning["inputs"]:
            if key.startswith("ref_images.ref_image_"):
                self.assertEqual(key, "ref_images.ref_image_0")

    def test_character_reference_prompt_separates_identity_from_clothing(self):
        prompt = minimax.build_character_reference_h3_prompt(
            "Amy is an adult woman currently wearing a red blouse."
        )
        self.assertIn(
            "<Picture 1> references only the identity and physical appearance",
            prompt,
        )
        self.assertIn("Do not copy clothing from <Picture 1>", prompt)
        self.assertIn(
            "clothing described in text is authoritative",
            prompt,
        )

    def test_unconditioned_character_reference_prompt_does_not_claim_picture_one(self):
        prompt = minimax.build_character_reference_h3_prompt(
            "Dragon1 is a dragon with obsidian scales.",
            has_identity_reference=False,
        )
        self.assertNotIn("<Picture 1>", prompt)
        self.assertIn(
            "The text description is authoritative for this character's identity",
            prompt,
        )
        self.assertIn("generated Picture will own for later segments", prompt)

    def test_character_reference_prompt_is_front_facing_one_second_not_orbit(self):
        prompt = minimax.build_character_reference_h3_prompt(
            "Amy is an adult woman wearing a red blouse."
        )
        self.assertIn("front-facing", prompt)
        self.assertIn("exactly 1 second", prompt)
        self.assertIn("Do not orbit", prompt)

    def test_reference_binding_window_repacks_generated_pictures(self):
        subjects = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "<Subject 2> is Goblin1 (S2).\n"
            "<Subject 3> is Elf1 (S3)."
        )
        refs = {
            "Goblin1": {
                "name": "Goblin1", "picture_number": 2,
                "image_name": "goblin.png", "image_path": "/tmp/goblin.png",
                "signature": "g", "version": 1,
                "description": "Goblin1 is a goblin.", "wardrobe": {},
                "clothing_condition": "", "authority": "identity_and_clothing",
            },
            "Elf1": {
                "name": "Elf1", "picture_number": 3,
                "image_name": "elf.png", "image_path": "/tmp/elf.png",
                "signature": "e", "version": 1,
                "description": "Elf1 is an elf.", "wardrobe": {},
                "clothing_condition": "", "authority": "identity_and_clothing",
            },
        }
        state = {}
        seg1_refs, _defs, state, snap1 = minimax.build_segment_reference_bindings(
            segment_number=1, total_segments=4,
            detailed_description="Goblin1 and Elf1 stand at the bar.",
            subject_definitions=subjects, character_references=refs,
            base_reference_count=1, binding_state=state,
        )
        self.assertEqual(seg1_refs["Goblin1"]["picture_number"], 2)
        self.assertEqual(seg1_refs["Elf1"]["picture_number"], 3)
        self.assertEqual(snap1["active_subject_ids"], [2, 3])

        _seg2_refs, _defs, state, _snap2 = minimax.build_segment_reference_bindings(
            segment_number=2, total_segments=4,
            detailed_description="Elf1 sits quietly.",
            subject_definitions=subjects, character_references=refs,
            base_reference_count=1, binding_state=state,
        )
        seg3_refs, defs3, state, snap3 = minimax.build_segment_reference_bindings(
            segment_number=3, total_segments=4,
            detailed_description="Elf1 remains at the table.",
            subject_definitions=subjects, character_references=refs,
            base_reference_count=1, binding_state=state,
        )
        self.assertNotIn("Goblin1", seg3_refs)
        self.assertEqual(seg3_refs["Elf1"]["picture_number"], 2)
        self.assertEqual(snap3["removed_subject_ids"], [2])
        self.assertIn("<Picture 2> defines Elf1", defs3)
        self.assertNotIn("Goblin1", defs3)
        self.assertTrue(state["subjects"]["Goblin1"]["eligible_for_removal"])
        self.assertEqual(
            state["subjects"]["Goblin1"]["removal_threshold_segment"], 3
        )

    def test_disable_subject_removal_keeps_seen_subjects_bound(self):
        subjects = "<Subject 2> is Goblin1 (S2).\n<Subject 3> is Elf1 (S3)."
        refs = {
            name: {
                "name": name, "picture_number": number,
                "image_name": name.lower() + ".png",
                "image_path": "/tmp/" + name.lower() + ".png",
                "signature": name, "version": 1,
                "description": name + " description", "wardrobe": {},
                "clothing_condition": "", "authority": "identity_and_clothing",
            }
            for name, number in (("Goblin1", 1), ("Elf1", 2))
        }
        state = {}
        _refs, _defs, state, _snap = minimax.build_segment_reference_bindings(
            segment_number=1, total_segments=4,
            detailed_description="Goblin1 and Elf1 are visible.",
            subject_definitions=subjects, character_references=refs,
            base_reference_count=0, binding_state=state,
            disable_subject_removal=True,
        )
        seg4_refs, defs4, state, snap4 = minimax.build_segment_reference_bindings(
            segment_number=4, total_segments=4,
            detailed_description="Elf1 is visible.",
            subject_definitions=subjects, character_references=refs,
            base_reference_count=0, binding_state=state,
            disable_subject_removal=True,
        )
        self.assertEqual(set(seg4_refs), {"Goblin1", "Elf1"})
        self.assertEqual(snap4["removed_subject_ids"], [])
        self.assertIn("Goblin1", defs4)
        self.assertEqual(
            state["subjects"]["Goblin1"]["binding_reason"],
            "forced_persistent",
        )

    def test_retained_subject_definition_survives_without_current_action(self):
        definitions = (
            "<Subject 2> is Elf1 (S2).\n"
            "<Picture 3> defines Elf1's identity, physical appearance, "
            "species/distinguishing traits, and current clothing."
        )
        filtered, _ = minimax._filter_h3_subject_definitions(
            definitions, set(), "Amy wipes the bar.", retained_subject_ids={2}
        )
        self.assertIn("<Subject 2> is Elf1", filtered)


if __name__ == "__main__":
    unittest.main()
