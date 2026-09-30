import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import minimax


SUBJECTS = (
    "<Subject 1> is Amy, referenced in <Picture 1>.\n"
    "<Subject 2> is Will, referenced in <Picture 2>."
)


def _wardrobe(**overrides):
    values = {field: "N/A" for field in minimax._WARDROBE_FIELDS}
    values.update(overrides)
    return values


class RequestedPromptRegressionTests(unittest.TestCase):

    def test_generate_prompts_cli_defaults_to_self_contained_render_settings(self):
        args = minimax.parse_args(["--generate-prompts", "3"])
        self.assertEqual(args.generate_prompts, 3)
        self.assertEqual(
            args.segment_length,
            minimax.DEFAULT_GENERATED_PROMPT_SEGMENT_LENGTH,
        )
        self.assertEqual(args.total_length, 24.0)
        self.assertEqual(
            args.megapixels,
            minimax.DEFAULT_GENERATED_PROMPT_MEGAPIXELS,
        )

    def test_generated_prompts_file_round_trip(self):
        payload = {
            "version": 1,
            "config": {
                "segment_length": 8.0,
                "total_length": 8.0,
                "megapixels": 0.5,
            },
            "macro_arc": {},
            "prompts": [
                {
                    "segment": 1,
                    "duration": 8.0,
                    "conditioning_mode": "initial",
                    "h3_prompt": "subject_definitions: test",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "generated_prompts.txt")
            minimax.save_generated_prompts_file(payload, path)
            self.assertEqual(
                minimax.load_generated_prompts_file(path),
                payload,
            )

    def test_generate_from_prompts_uses_saved_workflow_schedule_without_llm(self):
        payload = {
            "version": 1,
            "config": {
                "segment_length": 8.0,
                "total_length": 16.0,
                "megapixels": 0.5,
                "steps": 6,
                "trim_frames": 2,
                "refresh_interval": 2,
                "total_segments": 2,
            },
            "macro_arc": {},
            "prompts": [
                {
                    "segment": 1,
                    "duration": 8.0,
                    "conditioning_mode": "initial",
                    "h3_prompt": "subject_definitions: A",
                    "subject_definitions": "",
                    "continuity_state": {},
                    "continuity_summary": "",
                    "loras": [],
                },
                {
                    "segment": 2,
                    "duration": 8.0,
                    "conditioning_mode": "clean_refresh",
                    "h3_prompt": "subject_definitions: B",
                    "subject_definitions": "",
                    "continuity_state": {},
                    "continuity_summary": "",
                    "loras": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "generated_prompts.txt")
            minimax.save_generated_prompts_file(payload, path)
            render_results = [
                ({}, os.path.join(directory, "one.mp4"), 1280, 720, 0.5),
                ({}, os.path.join(directory, "two.mp4"), 1280, 720, 0.5),
            ]
            with (
                patch.object(minimax, "validate_runtime_environment"),
                patch.object(
                    minimax,
                    "render_segment_with_retries",
                    side_effect=render_results,
                ) as render,
                patch.object(minimax, "stitch_videos") as stitch,
            ):
                minimax.render_generated_prompts(
                    SimpleNamespace(steps=6),
                    path,
                )
            self.assertEqual(render.call_count, 2)
            self.assertIsNone(render.call_args_list[0].args[4])
            self.assertEqual(
                render.call_args_list[1].args[4],
                os.path.abspath(render_results[0][1]),
            )
            self.assertEqual(
                render.call_args_list[1].kwargs["refresh_interval"],
                2,
            )
            stitch.assert_called_once()

    def test_continuity_updates_registered_subjects_only(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        candidate = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "subject_id": 1,
                    "position": "beside the window",
                },
                "Transient Figure": {
                    "name": "Transient Figure",
                    "position": "near the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Amy stands beside the window while "
            "a transient figure is visible near the doorway.",
            subjects,
            committed_state=committed,
        )

        self.assertIn("Amy", guarded["subjects"])
        self.assertEqual(
            guarded["subjects"]["Amy"]["position"],
            "beside the window",
        )
        self.assertNotIn("Transient Figure", guarded["subjects"])

    def test_anonymous_subjects_do_not_carry_state_between_scenes(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)

        first = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Unregistered Figure": {
                        "name": "Unregistered Figure",
                        "injuries": ["visible wound"],
                    },
                },
            },
            "detailed_description: [Shot 1] An unregistered figure is visible.",
            subjects,
            committed_state=committed,
        )
        second = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Unregistered Figure": {
                        "name": "Unregistered Figure",
                        "position": "near the door",
                    },
                },
            },
            "detailed_description: [Shot 1] A different unregistered figure is visible.",
            subjects,
            committed_state=first,
        )

        self.assertEqual(set(first["subjects"]), {"Amy"})
        self.assertEqual(set(second["subjects"]), {"Amy"})

    def test_zombie_is_not_created_as_a_durable_subject(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        candidate = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "subject_id": 1,
                    "position": "beside the window",
                },
                "Zombie": {
                    "name": "Zombie",
                    "injuries": ["minor scrape"],
                    "position": "near the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Amy stands beside the window while "
            "a zombie is visible near the doorway.",
            subjects,
            committed_state=committed,
        )

        self.assertEqual(set(guarded["subjects"]), {"Amy"})
        self.assertNotIn("Zombie", guarded["subjects"])

    def test_explicitly_registered_named_subject_can_be_updated(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        candidate = {
            "subjects": {
                "Will": {
                    "name": "Will",
                    "subject_id": 2,
                    "position": "in the doorway",
                },
            },
        }

        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] Will stands in the doorway.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(
            guarded["subjects"]["Will"]["position"],
            "in the doorway",
        )

    def test_merge_boundary_discards_arbitrary_subject_fields(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        guarded = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "subject_id": 1,
                        "position": "beside the window",
                        "made_up_field": "must not persist",
                    },
                },
                "made_up_top_level": "must not persist",
            },
            "detailed_description: Amy stands beside the window.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(
            guarded["subjects"]["Amy"]["position"],
            "beside the window",
        )
        self.assertNotIn("made_up_field", guarded["subjects"]["Amy"])
        self.assertNotIn("made_up_top_level", guarded)

    def test_offscreen_registered_subject_reenters_with_same_identity(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Will"]["position"] = "in the basement"
        committed["subjects"]["Will"]["injuries"] = ["bruise"]

        projected = minimax._phase2_continuity_state_for_scene(
            committed,
            SUBJECTS,
            "detailed_description: [Shot 1] Amy closes and locks the basement door.",
        )
        self.assertNotIn("Will", projected["subjects"])
        self.assertIn("Will", committed["subjects"])

        later = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Will": {
                        "name": "Will",
                        "subject_id": 2,
                        "position": "at the basement doorway",
                    },
                },
            },
            "detailed_description: [Shot 1] Will stands at the basement doorway.",
            SUBJECTS,
            committed_state=committed,
        )

        self.assertEqual(later["subjects"]["Will"]["subject_id"], 2)
        self.assertEqual(later["subjects"]["Will"]["injuries"], ["bruise"])
        self.assertEqual(
            later["subjects"]["Will"]["position"],
            "at the basement doorway",
        )

    def test_phase_two_prunes_empty_and_unknown_values_without_mutating_state(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Amy"].update({
            "position": "by the doorway",
            "held_props": [],
            "injuries": [],
            "physical_condition": "N/A",
        })
        request = Mock(return_value="Amy is by the doorway.")

        minimax.request_continuity_opening_state(
            state,
            {},
            llm_request=request,
            subject_definitions=SUBJECTS,
            ending_scene="End continuity state: Amy stands by the doorway.",
        )

        user_prompt = request.call_args.args[0][1]["content"]
        self.assertIn('"position": "by the doorway"', user_prompt)
        self.assertNotIn("held_props", user_prompt)
        self.assertNotIn("injuries", user_prompt)
        self.assertNotIn("physical_condition", user_prompt)
        self.assertEqual(state["subjects"]["Amy"]["held_props"], [])
        self.assertEqual(state["subjects"]["Amy"]["physical_condition"], "N/A")

    def test_phase_two_keeps_false_and_zero_values(self):
        state = {
            "environment": {"location": "room"},
            "subjects": {
                "Amy": {
                    "position": "by the doorway",
                    "flag": False,
                    "count": 0,
                },
            },
        }
        request = Mock(return_value="Amy is by the doorway.")

        minimax.request_continuity_opening_state(
            state,
            {},
            llm_request=request,
            ending_scene="End continuity state: Amy stands by the doorway.",
        )

        user_prompt = request.call_args.args[0][1]["content"]
        self.assertIn('"flag": false', user_prompt)
        self.assertIn('"count": 0', user_prompt)

    def test_unassigned_prompt_exit_preserves_committed_position(self):
        committed = {
            "version": 5,
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "position": "home",
                    "topology": "N/A",
                    "spatial_relationships": [],
                }
            },
        }
        prompt_state = {
            "version": 5,
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "position": "outside kitchen doorway",
                    "topology": "outside kitchen doorway",
                    "spatial_relationships": ["outside kitchen doorway"],
                }
            },
        }
        merged = minimax._continuity_apply_authoritative_state_effects(
            prompt_state,
            [],
            committed_state=committed,
        )
        self.assertEqual(merged["subjects"]["Amy"]["position"], "home")
        self.assertNotIn(
            "outside",
            str(merged["subjects"]["Amy"].get("topology", "")).casefold(),
        )

    def test_unassigned_internal_room_refinement_is_allowed(self):
        committed = {
            "version": 5,
            "subjects": {"Amy": {"name": "Amy", "position": "kitchen"}},
        }
        prompt_state = {
            "version": 5,
            "subjects": {"Amy": {"name": "Amy", "position": "living room"}},
        }
        merged = minimax._continuity_apply_authoritative_state_effects(
            prompt_state,
            [],
            committed_state=committed,
        )
        self.assertEqual(merged["subjects"]["Amy"]["position"], "living room")

    def test_authorized_location_effect_allows_outside_position(self):
        committed = {
            "version": 5,
            "subjects": {"Amy": {"name": "Amy", "position": "home"}},
        }
        prompt_state = {
            "version": 5,
            "subjects": {"Amy": {"name": "Amy", "position": "outside home"}},
        }
        merged = minimax._continuity_apply_authoritative_state_effects(
            prompt_state,
            [{"op": "set_location", "entity": "Amy", "value": "outside home"}],
            committed_state=committed,
        )
        self.assertEqual(merged["subjects"]["Amy"]["position"], "outside home")

    def test_authoritative_containment_clears_stale_cross_location_relationships(self):
        state = {
            "version": 5,
            "environment": {"location": "kitchen", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {
                "Will": {
                    "name": "Will",
                    "position": "basement",
                    "pose_action": "in arms",
                    "topology": "held by Amy",
                    "wardrobe": {},
                    "held_props": [],
                    "spatial_relationships": ["in Amy's arms", "inside basement"],
                }
            },
        }
        merged = minimax._continuity_apply_authoritative_state_effects(
            state,
            [
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "contained",
                }
            ],
        )
        self.assertEqual(merged["subjects"]["Will"]["position"], "basement")
        self.assertEqual(merged["subjects"]["Will"]["pose_action"], "N/A")
        self.assertEqual(merged["subjects"]["Will"]["topology"], "N/A")
        self.assertEqual(
            merged["subjects"]["Will"]["spatial_relationships"],
            ["inside basement"],
        )

    def test_authoritative_containment_overrides_prompt_continuity_position(self):
        state = {
            "version": 5,
            "environment": {"location": "kitchen", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {
                "Will": {
                    "name": "Will",
                    "position": "kitchen doorway",
                    "wardrobe": {},
                    "held_props": [],
                    "spatial_relationships": ["watching Amy"],
                }
            },
        }
        effects = [
            {
                "op": "set_containment",
                "entity": "Will",
                "container": "basement",
                "value": "contained",
            },
            {
                "op": "set_location",
                "entity": "Will",
                "value": "basement",
            },
        ]
        merged = minimax._continuity_apply_authoritative_state_effects(
            state,
            effects,
        )
        self.assertEqual(merged["subjects"]["Will"]["position"], "basement")
        self.assertIn(
            "inside basement",
            merged["subjects"]["Will"]["spatial_relationships"],
        )

    def test_explicit_shattered_window_rejects_generic_object_damage(self):
        event = "A zombie shatters the kitchen door window and glass falls inward."
        effects = [
            {
                "op": "set_object_state",
                "entity": "kitchen door window",
                "value": "damaged",
            }
        ]
        with self.assertRaisesRegex(ValueError, "set_barrier_state=broken"):
            minimax._validate_required_event_state_effect_grounding(event, effects)

    def test_source_unit_state_extractor_repairs_invalid_barrier_state(self):
        class Unit:
            id = "U1"
            text = "A zombie shatters the kitchen door window."

        class Plan:
            source_units = [Unit()]

        responses = [
            {
                "state_effects": [
                    {
                        "op": "set_object_state",
                        "entity": "kitchen door window",
                        "value": "damaged",
                    }
                ]
            },
            {
                "state_effects": [
                    {
                        "op": "set_barrier_state",
                        "entity": "kitchen door window",
                        "value": "broken",
                    }
                ]
            },
        ]
        seen_messages = []

        def fake_llm(messages, **kwargs):
            seen_messages.append(messages)
            return responses.pop(0)

        effects = minimax.extract_source_span_state_effects(
            Plan(),
            fake_llm,
        )
        self.assertEqual(
            effects["U1"],
            [
                {
                    "op": "set_barrier_state",
                    "entity": "kitchen door window",
                    "value": "broken",
                }
            ],
        )
        self.assertEqual(len(seen_messages), 2)
        self.assertIn(
            "previous state extraction was invalid",
            seen_messages[1][-1]["content"],
        )

    def test_broken_window_does_not_force_locked_basement_door_broken(self):
        event = (
            "A zombie breaks the kitchen door window. "
            "Amy rushes the kids to the basement and locks the basement door."
        )
        effects = [
            {
                "op": "set_barrier_state",
                "entity": "kitchen door window",
                "value": "broken",
            },
            {
                "op": "set_barrier_state",
                "entity": "basement door",
                "value": "locked",
            },
        ]
        self.assertEqual(
            minimax._validate_required_event_state_effect_grounding(event, effects),
            effects,
        )

    def test_explicit_shattered_window_accepts_broken_barrier_state(self):
        event = "A zombie shatters the kitchen door window and glass falls inward."
        effects = [
            {
                "op": "set_barrier_state",
                "entity": "kitchen door window",
                "value": "broken",
            }
        ]
        self.assertEqual(
            minimax._validate_required_event_state_effect_grounding(event, effects),
            effects,
        )

    def test_state_effects_reject_duplicate_clothing_item_state(self):
        with self.assertRaisesRegex(ValueError, "garment represented by set_clothing"):
            minimax._validate_state_effects([
                {
                    "op": "set_clothing",
                    "entity": "Amy",
                    "slot": "upper",
                    "item": "black tank top",
                    "damage": "none",
                },
                {
                    "op": "set_item_state",
                    "entity": "black tank top",
                    "owner": "Amy",
                    "value": "equipped",
                },
            ])

    def test_authoritative_move_clears_stale_location_metadata(self):
        state = {
            "version": 5,
            "environment": {"location": "kitchen", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {
                "Will": {
                    "name": "Will",
                    "position": "at kitchen table",
                    "pose_action": "eating pancakes",
                    "topology": "seated",
                    "wardrobe": {},
                    "held_props": ["pancake"],
                    "spatial_relationships": ["at kitchen table", "eating pancakes"],
                }
            },
        }
        merged = minimax._continuity_apply_authoritative_state_effects(
            state,
            [
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "contained",
                },
                {
                    "op": "set_location",
                    "entity": "Will",
                    "value": "basement",
                },
            ],
        )
        will = merged["subjects"]["Will"]
        self.assertEqual(will["position"], "basement")
        self.assertEqual(will["pose_action"], "N/A")
        self.assertEqual(will["topology"], "N/A")
        self.assertEqual(will["spatial_relationships"], ["inside basement"])
        self.assertEqual(will["held_props"], ["pancake"])

    def test_authoritative_barrier_binding_names_destination_in_continuity(self):
        state = {
            "version": 5,
            "environment": {"location": "kitchen", "persistent_state": "N/A"},
            "camera": "N/A",
            "ongoing_action": "N/A",
            "ongoing_audio": "N/A",
            "subjects": {},
        }
        effects = [
            {
                "op": "set_containment",
                "entity": "Will",
                "container": "basement",
                "value": "contained",
            },
            {
                "op": "set_barrier_state",
                "entity": "door",
                "value": "locked",
            },
        ]
        binding = minimax.build_director_barrier_binding_contract(effects)
        merged = minimax._continuity_apply_authoritative_state_effects(
            state,
            effects,
            barrier_binding=binding,
        )
        self.assertIn(
            "basement door locked",
            merged["environment"]["persistent_state"],
        )

    def test_end_state_projection_does_not_delete_offscreen_registered_subjects(self):
        definitions = (
            "<Subject 1> is Alex, referenced in <Picture 1>.\n"
            "<Subject 2> is Blair, referenced in <Picture 2>.\n"
            "<Subject 3> is Casey, referenced in <Picture 3>."
        )
        state = minimax.continuity_state_for_registry(definitions)
        projected = minimax._phase2_continuity_state_for_scene(
            state,
            definitions,
            "Earlier: Alex, Blair, and Casey are visible.\n"
            "Alex closes a door behind Blair and Casey.\n"
            "End continuity state: Alex stands outside the closed door.",
        )

        self.assertEqual(set(state["subjects"]), {"Alex", "Blair", "Casey"})
        self.assertEqual(set(projected["subjects"]), {"Alex"})

    def test_held_prop_survives_phase_two_and_can_be_cleared_generically(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Amy"]["held_props"] = ["metal tool"]
        request = Mock(return_value="Amy stands by the doorway holding a metal tool.")

        minimax.request_continuity_opening_state(
            committed,
            {},
            llm_request=request,
            subject_definitions=SUBJECTS,
            ending_scene=(
                "End continuity state: Amy stands by the doorway holding a metal tool."
            ),
        )
        self.assertIn("metal tool", request.call_args.args[0][1]["content"])

        cleared = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Amy": {
                        "name": "Amy",
                        "subject_id": 1,
                        "held_props": [],
                    },
                },
            },
            "detailed_description: Amy stands by the doorway.",
            SUBJECTS,
            committed_state=committed,
        )
        self.assertEqual(cleared["subjects"]["Amy"]["held_props"], [])

    def test_continuity_cannot_create_a_new_named_subject(self):
        subjects = "<Subject 1> is Amy, referenced in <Picture 1>."
        committed = minimax.continuity_state_for_registry(subjects)
        guarded = minimax._guard_combined_continuity_subjects(
            {
                "subjects": {
                    "Mara": {
                        "name": "Mara",
                        "position": "at the table",
                    },
                },
            },
            "detailed_description: [Shot 1] Mara stands at the table.",
            subjects,
            committed_state=committed,
        )

        self.assertEqual(set(guarded["subjects"]), {"Amy"})

    def test_dialogue_addressees_are_not_visual_subjects(self):
        description = (
            'Amy calls out to Will and Amber, "Breakfast is ready!"'
        )
        self.assertEqual(
            minimax._subject_ids_referenced_by_description(description, SUBJECTS),
            {1},
        )

    def test_dialogue_only_name_is_not_promoted_by_named_subject_hints(self):
        state, added = minimax.register_named_subject_hints(
            minimax.continuity_state_for_registry(
                "<Subject 1> is Amy, referenced in <Picture 1>."
            ),
            "<Subject 1> is Amy, referenced in <Picture 1>.",
            'Amy calls out "Will! Amber! Breakfast is ready!"',
            ["Will", "Amber"],
            origin_segment=1,
        )
        self.assertEqual(added, [])
        self.assertNotIn("Will", state["subjects"])
        self.assertNotIn("Amber", state["subjects"])

    def test_anonymous_zombie_cannot_take_registered_wills_identity(self):
        committed = minimax.continuity_state_for_registry(SUBJECTS)
        committed["subjects"]["Will"]["position"] = "in the basement"
        candidate = {
            "subjects": {
                "Will": {
                    "subject_id": 2,
                    "name": "Will",
                    "position": "at the top of the stairs",
                },
            },
        }
        guarded = minimax._guard_combined_continuity_subjects(
            candidate,
            "detailed_description: [Shot 1] A zombie crashes through the kitchen window.\n\n"
            "overall_soundscape: glass breaking",
            SUBJECTS,
            committed_state=committed,
        )
        self.assertEqual(
            guarded["subjects"]["Will"]["position"],
            "in the basement",
        )

    def test_explicit_visual_will_can_resolve(self):
        self.assertEqual(
            minimax._subject_ids_referenced_by_description(
                "<Subject 2> Will stands in the doorway.",
                SUBJECTS,
            ),
            {2},
        )

    def test_wardrobe_reconciliation_preserves_adjacent_choreography(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["subjects"]["Amy"]["wardrobe"] = _wardrobe(
            upper="black tank top",
            lower="denim jeans",
        )
        cases = (
            (
                "Amy stands wearing a black tank top and denim jeans, her katana "
                "raised as the camera pans right across the living room.",
                "her katana raised as the camera pans right across the living room.",
            ),
            (
                "Amy prepares breakfast wearing a tight black tank top and denim "
                "jeans, as the camera pans across the scene.",
                "as the camera pans across the scene.",
            ),
            (
                "Amy wears a black tank top and denim jeans while holding a pistol.",
                "while holding a pistol.",
            ),
        )
        for source, preserved in cases:
            with self.subTest(source=source):
                result = minimax.reconcile_h3_wardrobe_with_canonical_state(
                    source,
                    SUBJECTS,
                    state,
                )
                self.assertIn("black tank top and denim jeans", result)
                self.assertIn(preserved, result)

    def test_quoted_speech_uses_actor_not_addressee(self):
        formatted = minimax.format_mistral_prompt(
            {
                "detailed_description": (
                    'Amy calls out to Will and Amber, "Come on up, kids. It\'s safe now."'
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            {"subject_definitions": SUBJECTS},
        )
        description = formatted["detailed_description"]
        self.assertIn(
            "Amy (S1) calls out to Will and Amber: "
            "<d>[English] Come on up, kids. It's safe now.</d>",
            description,
        )
        self.assertNotIn("<Subject 2> Will", description)

    def test_spoken_dialogue_does_not_emit_none_constraint(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    'Amy calls out to Will, "Come on up!"'
                ),
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=1,
        )
        self.assertNotIn("SPOKEN DIALOGUE: None", prompt)

    def test_silent_scene_keeps_none_constraint(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "Amy waits silently.",
                "overall_soundscape": "room tone",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            segment_number=1,
        )
        self.assertIn("SPOKEN DIALOGUE: None", prompt)

    def test_bracketed_director_timestamps_are_rejected(self):
        raw = (
            "At 00:00.000, operator opens the panel.\n"
            "At 00:01.200, operator closes the panel.\n"
            "End continuity state: panel closed."
        )
        formatted = (
            "[Shot 1] At [At 00:00.000, ], operator opens the panel. "
            "[At 00:01.200, ] operator closes the panel."
        )
        issues = minimax._validate_director_timestamp_correspondence(
            raw,
            formatted,
            segment_seconds=8,
        )
        self.assertTrue(
            any("Bracketed or nested timestamp wrappers" in issue for issue in issues)
        )

    def test_continuation_style_prefix_is_unique_and_timed_action_survives(self):
        for description in (
            "[Shot 1] Live-action, cinematic. At 00:00.000 seconds, Amy moves.",
            "[Shot 1] Live-action, cinematic, Amy moves.",
            "[Shot 1] Live-action, cinematic. Live-action, cinematic. Amy moves.",
        ):
            with self.subTest(description=description):
                prompt = minimax.build_h3_prompt(
                    {
                        "detailed_description": description,
                        "overall_soundscape": "room tone",
                        "non_diegetic_music": "N/A",
                    },
                    SUBJECTS,
                    segment_number=2,
                    conditioning_mode="continuation",
                )
                rendered = prompt.split("detailed_description: ", 1)[1].split(
                    "\n\noverall_soundscape:",
                    1,
                )[0]
                self.assertEqual(rendered.count("Live-action, cinematic"), 1)
                self.assertIn("Amy moves", rendered)
                if "00:00.000" in description:
                    self.assertIn("At 00:00.000, Amy moves.", rendered)


    def test_explicit_adjacent_same_hand_conflict_is_rejected(self):
        raw = (
            "At 00:00.000, Amy keeps the tray in her left hand.\n"
            "At 00:02.500, Will takes a pancake; Amy keeps the tray in her left hand.\n"
            "At 00:03.500, Amy extends her left hand to offer Amber another pancake.\n"
            "End continuity state: Amy still holds the tray."
        )
        issues = minimax._director_explicit_limb_conflict_errors(raw)
        self.assertTrue(issues)
        self.assertIn("left hand", issues[0])

    def test_assigned_source_enables_terminal_state_check(self):
        self.assertTrue(
            minimax.director_source_has_terminal_action(
                "The operator permanently disables the failed machine."
            )
        )

    def test_blank_source_skips_terminal_state_check(self):
        self.assertFalse(minimax.director_source_has_terminal_action(""))

    def test_terminal_state_extractor_uses_python_owned_target_and_state(self):
        messages = minimax.build_director_terminal_target_messages(
            "machine A",
            "inactive",
            "At 00:00.000, the operator faces machine A.",
            "machine A is inactive",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("TARGET\nmachine A", prompt)
        self.assertIn("REQUIRED END STATE\ninactive", prompt)
        self.assertIn("MATCH", prompt)
        self.assertIn("NOT_MATCH", prompt)
        self.assertIn("UNKNOWN", prompt)

    def test_terminal_state_contracts_use_only_stateful_object_families(self):
        contracts = minimax.build_director_terminal_state_contracts(
            [
                {"op": "set_threat_state", "entity": "machine A", "value": "inactive"},
                {"op": "set_barrier_state", "entity": "gate B", "value": "closed"},
                {"op": "set_object_state", "entity": "module C", "value": "inactive"},
                {"op": "set_condition", "entity": "room", "value": "quiet"},
                {"op": "set_location", "entity": "operator", "value": "lab"},
                {"op": "set_clothing", "entity": "operator", "slot": "upper", "item": "jacket", "damage": "none"},
            ]
        )
        self.assertEqual(
            contracts,
            [
                {"target": "machine A", "required_end_state": "inactive"},
                {"target": "gate B", "required_end_state": "closed"},
                {"target": "module C", "required_end_state": "inactive"},
            ],
        )

    def test_releasing_contained_subject_preserves_unassigned_locked_barrier(self):
        opening = {
            "characters": {
                "Will": {
                    "containment": "contained",
                    "contained_in": "basement",
                    "location": "basement",
                }
            },
            "environment": {
                "doors": {
                    "door": {"status": "locked"},
                }
            },
        }
        contracts = minimax.build_director_preserved_barrier_state_contracts(
            "SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n"
            + json.dumps(opening),
            [
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "free",
                }
            ],
        )
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["barrier"], "basement door")
        self.assertEqual(contracts[0]["expected"], "LOCKED")
        self.assertEqual(contracts[0]["source_state"], "locked")

    def test_explicit_barrier_effect_replaces_opening_barrier_state(self):
        opening = {
            "characters": {
                "Will": {
                    "containment": "contained",
                    "contained_in": "basement",
                    "location": "basement",
                }
            },
            "environment": {
                "doors": {
                    "door": {"status": "locked"},
                }
            },
        }
        contracts = minimax.build_director_preserved_barrier_state_contracts(
            json.dumps(opening),
            [
                {
                    "op": "set_barrier_state",
                    "entity": "door",
                    "value": "unlocked",
                }
            ],
        )
        self.assertEqual(contracts, [])

    def test_terminal_state_parser_uses_match_contract(self):
        self.assertEqual(
            minimax.parse_director_terminal_target_observation(
                {"status": "MATCH"}
            ),
            "MATCH",
        )
        with self.assertRaises(ValueError):
            minimax.parse_director_terminal_target_observation(
                {"status": "ALREADY_TERMINAL"}
            )

    def test_same_hand_same_object_continuation_is_not_rejected(self):
        raw = (
            "At 00:00.000, Amy holds a pistol in her right hand.\n"
            "At 00:01.000, Amy turns the pistol in her right hand toward the doorway.\n"
            "End continuity state: Amy holds the pistol."
        )
        self.assertEqual(
            minimax._director_explicit_limb_conflict_errors(raw),
            [],
        )

    def test_same_hand_explicit_release_is_not_rejected(self):
        raw = (
            "At 00:00.000, Jon carries a box in his left hand.\n"
            "At 00:01.000, Jon sets down the box, then opens the door with his left hand.\n"
            "End continuity state: Jon stands beside the open door."
        )
        self.assertEqual(
            minimax._director_explicit_limb_conflict_errors(raw),
            [],
        )

    def test_ambiguous_same_hand_motion_without_object_manipulation_is_skipped(self):
        raw = (
            "At 00:00.000, Mara holds a flashlight in her left hand.\n"
            "At 00:01.000, Mara extends her left hand toward the dark hallway.\n"
            "End continuity state: Mara faces the hallway."
        )
        self.assertEqual(
            minimax._director_explicit_limb_conflict_errors(raw),
            [],
        )


    def test_explicit_set_down_then_held_again_is_rejected(self):
        raw = (
            "At 00:00.000, Amy brings the plate and bowl together, sets them side by side on a table.\n"
            "At 00:01.000, Amy stands beside the table, holding the plate and bowl.\n"
            "End continuity state: Amy stands beside the table."
        )
        issues = minimax._director_explicit_object_state_conflict_errors(raw)
        self.assertTrue(issues)
        self.assertIn("held again", issues[0])

    def test_set_down_then_explicit_pickup_is_not_rejected(self):
        raw = (
            "At 00:00.000, Jon places the toolbox on the floor.\n"
            "At 00:01.000, Jon picks up the toolbox and holds it against his chest.\n"
            "End continuity state: Jon holds the toolbox."
        )
        self.assertEqual(
            minimax._director_explicit_object_state_conflict_errors(raw),
            [],
        )

    def test_barrier_binding_qualifies_generic_barrier_for_state_extraction(self):
        effects = [
            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
            {"op": "set_containment", "entity": "Amber", "container": "basement", "value": "contained"},
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
        ]
        binding = minimax.build_director_barrier_binding_contract(effects)
        self.assertEqual(binding["destination"], "basement")
        messages = minimax.build_director_barrier_state_messages(
            f"{binding['entity']} that is the boundary of {binding['destination']}",
            "Amy locks the kitchen door.",
        )
        prompt = messages[-1]["content"]
        self.assertIn("door that is the boundary of basement", prompt)
        self.assertIn("Amy locks the kitchen door.", prompt)

    def test_end_state_cannot_reacquire_plate_after_setting_it_down(self):
        raw = (
            "At 00:00.000, Amy picks up a second plate.\n"
            "At 00:01.000, Amy sets the second plate in front of Amber.\n"
            "End continuity state: Amy stands holding two plates."
        )
        issues = minimax._director_explicit_object_state_conflict_errors(raw)
        self.assertTrue(issues)
        self.assertIn("End continuity state", issues[0])

    def test_unrelated_placed_object_does_not_block_other_held_object(self):
        raw = (
            "At 00:00.000, Mara places the cup on the table beside her backpack.\n"
            "At 00:01.000, Mara stands holding the backpack.\n"
            "End continuity state: Mara holds the backpack."
        )
        self.assertEqual(
            minimax._director_explicit_object_state_conflict_errors(raw),
            [],
        )


    def test_director_topology_keeps_unassigned_helper_outside_destination(self):
        effects = [
            {"op": "set_containment", "entity": "ChildA", "container": "safe room", "value": "contained"},
            {"op": "set_containment", "entity": "ChildB", "container": "safe room", "value": "contained"},
            {"op": "set_barrier_state", "entity": "door", "value": "locked"},
            {"op": "set_location", "entity": "ChildA", "value": "safe room"},
            {"op": "set_location", "entity": "ChildB", "value": "safe room"},
        ]
        contracts = minimax.build_director_barrier_topology_contract(
            effects,
            (
                "<Subject 1> is Caregiver, an adult.\n"
                "<Subject 2> is ChildA, a child.\n"
                "<Subject 3> is ChildB, a child."
            ),
            assigned_source=(
                "Caregiver gets ChildA and ChildB into the safe room, then locks the door."
            ),
            current_beat=(
                "Caregiver rushes ChildA and ChildB into the safe room and locks its door."
            ),
            authoritative_opening_state=(
                'SOURCE-AUTHORIZED CURRENT STATE (authoritative if conflict)\n'
                '{"characters":{"Caregiver":{"location":"home"}}}'
            ),
        )
        self.assertEqual(len(contracts), 1)
        by_name = {
            item["entity"]: item["expected"]
            for item in contracts[0]["subjects"]
        }
        self.assertEqual(by_name["ChildA"], "AT_DESTINATION")
        self.assertEqual(by_name["ChildB"], "AT_DESTINATION")
        self.assertEqual(by_name["Caregiver"], "NOT_AT_DESTINATION")



    def test_source_state_extractor_gets_prior_context_for_anaphora_only(self):
        messages = minimax.build_source_unit_state_effect_messages(
            "She equips the weapons.",
            subject_information=(
                "<Subject 1> is Amy, an adult woman. "
                "<Subject 2> is Will, a child."
            ),
            reference_context=(
                "Amy retrieves her hidden arsenal consisting of a pistol and a katana."
            ),
        )
        prompt = messages[-1]["content"]
        self.assertIn("PREVIOUS SOURCE CONTEXT", prompt)
        self.assertIn("pistol and a katana", prompt)
        self.assertIn('"the weapons"', prompt)
        self.assertIn("reference only", prompt.casefold())

    def test_equipped_item_is_not_projected_as_held_prop(self):
        state = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "held_props": ["pancake tray"],
                }
            },
            "environment": {"location": "home", "persistent_state": "N/A"},
        }
        committed = {
            "subjects": {
                "Amy": {
                    "name": "Amy",
                    "held_props": [],
                }
            },
            "environment": {"location": "home", "persistent_state": "N/A"},
        }
        result = minimax._continuity_apply_authoritative_state_effects(
            state,
            [
                {
                    "op": "set_item_state",
                    "entity": "katana",
                    "owner": "Amy",
                    "value": "equipped",
                }
            ],
            committed_state=committed,
        )
        self.assertEqual(result["subjects"]["Amy"]["held_props"], [])

    def test_held_item_is_projected_as_held_prop(self):
        state = {
            "subjects": {"Amy": {"name": "Amy", "held_props": []}},
            "environment": {"location": "home", "persistent_state": "N/A"},
        }
        result = minimax._continuity_apply_authoritative_state_effects(
            state,
            [
                {
                    "op": "set_item_state",
                    "entity": "pistol",
                    "owner": "Amy",
                    "value": "held",
                }
            ],
            committed_state=state,
        )
        self.assertEqual(result["subjects"]["Amy"]["held_props"], ["pistol"])

    def test_director_item_contract_preserves_held_equipped_stored_distinction(self):
        registry = minimax.new_beat_canonical_state()
        registry["characters"]["Amy"] = {
            "held_objects": ["pistol"],
            "equipped_objects": ["katana"],
            "stored_objects": ["flashlight"],
        }
        lines = minimax.build_director_item_state_contract(registry, [])
        text = "\n".join(lines)
        self.assertIn("HOLDS pistol in a hand", text)
        self.assertIn("katana EQUIPPED on the person; it is NOT held in a hand", text)
        self.assertIn("flashlight STORED", text)

    def test_timed_state_only_restatement_is_rejected(self):
        raw = (
            "At 00:00.000, Amy turns toward the doorway.\n"
            "At 00:06.900, the kitchen window remains broken; the basement door stays locked.\n"
            "End continuity state: the kitchen window is broken and the basement door is locked."
        )
        issues = minimax._director_raw_scene_structure_errors(raw, segment_seconds=8)
        self.assertTrue(issues)
        self.assertIn("not only restate unchanged continuity", issues[0])

    def test_release_from_arsenal_is_rejected_on_retrieval_beat(self):
        issues = minimax._director_unassigned_release_from_storage_errors(
            (
                "At 00:00.000, Amy pulls open the hidden arsenal.\n"
                "At 00:02.000, Amy releases a pistol from the hidden arsenal.\n"
                "End continuity state: Amy has the pistol."
            ),
            "Amy retrieves a pistol from her hidden arsenal and equips it.",
        )
        self.assertTrue(issues)
        self.assertIn("ordinary physical retrieval verb", issues[0])


if __name__ == "__main__":
    unittest.main()
