import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import minimax


def _empty_patch(beat_number):
    return {
        "beat_number": beat_number,
        "patch": {},
    }


def _state_with_amy(clothing=None):
    state = minimax.new_beat_canonical_state()
    state["characters"]["Amy"] = {
        "location": "kitchen",
        "clothing": clothing if clothing is not None else [
            "black tank top",
            "denim jeans",
        ],
        "held_objects": [],
    }
    return minimax.normalize_beat_canonical_state(state)


def _message_text(messages):
    return "\n".join(
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict)
    )


class ForwardBeatValidationTests(unittest.TestCase):
    def test_windows_are_pairs_with_the_previous_beat_as_anchor(self):
        windows = minimax.build_beat_validation_windows(20)
        self.assertEqual(
            [(item["window_start"], item["window_end"]) for item in windows],
            [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10),
             (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)],
        )
        self.assertEqual(
            [item["anchor_beat_number"] for item in windows],
            [None, 2, 4, 6, 8, 10, 12, 14, 16, 18],
        )
        self.assertEqual(
            [(item["mutable_start"], item["mutable_end"]) for item in windows],
            [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10),
             (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)],
        )

    def test_partial_final_window_is_supported(self):
        windows = minimax.build_beat_validation_windows(10)
        self.assertEqual(
            [(item["window_start"], item["window_end"]) for item in windows],
            [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)],
        )

    def test_finalizer_uses_repairs_only_text_contract(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [{
                    "beat_number": 2,
                    "beat_text": "Repaired beat 2.",
                }],
                "state_updates": [_empty_patch(number) for number in range(1, 3)],
            },
            1,
            2,
        )
        self.assertEqual(
            parsed["repairs"],
            [{"beat_number": 2, "beat_text": "Repaired beat 2."}],
        )
        self.assertEqual(
            [item["beat_number"] for item in parsed["state_updates"]],
            [1, 2],
        )
        self.assertNotIn("changed", parsed)
        self.assertNotIn("state_after", parsed)
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization({"beats": []}, 1, 3)

    def test_missing_mutable_state_update_is_rejected(self):
        response = {
            "repairs": [],
            "state_updates": [_empty_patch(5)],
        }
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(response, 5, 6)

    def test_immutable_repair_target_is_rejected(self):
        response = {
            "repairs": [{
                "beat_number": 4,
                "beat_text": "Rewritten finalized anchor.",
            }],
            "state_updates": [_empty_patch(number) for number in range(5, 7)],
        }
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(response, 5, 6)

    def test_empty_patch_is_accepted_and_normalized(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [],
                "state_updates": [{
                    "beat_number": 5,
                    "patch": {},
                }],
            },
            5,
            5,
        )
        self.assertEqual(parsed["state_updates"], [_empty_patch(5)])

    def test_finalizer_proposal_has_no_goal_or_event_ids(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [],
                "state_updates": [{
                    "beat_number": 5,
                    "patch": {},
                }],
            },
            5,
            5,
        )
        self.assertNotIn("beat_completes_job", parsed["state_updates"][0])
        self.assertNotIn("completed_event_ids", parsed["state_updates"][0])
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(
                {"repairs": [], "state_updates": [{
                    "beat_number": 5,
                    "patch": {},
                    "beat_completes_job": True,
                }]},
                5,
                5,
            )

    def test_event_completion_requires_explicit_final_beat_action(self):
        event = "The visitor enters the shelter and locks the entrance."
        self.assertFalse(
            minimax.required_event_is_grounded_in_beat_text(
                event, "The visitor runs toward the shelter."
            )
        )
        self.assertTrue(
            minimax.required_event_is_grounded_in_beat_text(
                event, "The visitor enters the shelter and locks the entrance."
            )
        )

    def test_finalizer_makes_repaired_beat_authoritative_for_the_next_beat(self):
        messages = minimax.build_local_beat_finalizer_messages(
            [
                "Amy opens the door.",
                "Amy steps through the door.",
            ],
            5,
            6,
            minimax.new_beat_canonical_state(),
            fidelity_issues=[{
                "beat_number": 5,
                "type": "story_local_beat_fidelity",
                "problem": "Beat 5 must open the door.",
            }],
            continuity_issues=[],
        )
        prompt_text = _message_text(messages).casefold()
        self.assertIn("repaired", prompt_text)
        self.assertIn("beat n", prompt_text)
        self.assertIn("beat n+1", prompt_text)
        self.assertIn("authoritative", prompt_text)
        self.assertIn("superseded provisional text", prompt_text)

    def test_finalizer_schema_hides_python_owned_event_ids(self):
        schema = minimax.build_local_beat_finalizer_response_format(5, 6)
        update = schema["json_schema"]["schema"]["properties"]["state_updates"]
        properties = update["items"]["properties"]
        self.assertNotIn("beat_completes_job", properties)
        self.assertNotIn("completed_event_ids", properties)

    def test_verifier_contract_is_small_and_free_of_internal_ids(self):
        messages = minimax.build_local_beat_verification_messages(
            "Amy unlocks and opens the basement door.",
            "- The basement door's status ends the beat open.",
            "Amy opens the basement door.",
        )
        prompt_text = _message_text(messages)
        self.assertIn("Amy unlocks and opens", prompt_text)
        self.assertIn("basement door", prompt_text)
        self.assertNotIn("E4", prompt_text)
        self.assertNotIn("completed_required_event_ids", prompt_text)
        schema = minimax.build_local_beat_verification_response_format()
        self.assertEqual(
            schema["json_schema"]["schema"]["required"],
            [
                "beat_supports_state_changes",
                "beat_completes_job",
                "change_notes",
                "verification_notes",
            ],
        )

    def test_verifier_parses_only_boolean_flags_and_notes(self):
        parsed = minimax.parse_local_beat_verification({
            "beat_supports_state_changes": True,
            "beat_completes_job": False,
            "change_notes": "N/A",
            "verification_notes": " The beat does not complete the job. ",
        })
        self.assertEqual(
            parsed["verification_notes"],
            "The beat does not complete the job.",
        )
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_verification({
                "beat_supports_state_changes": True,
                "beat_completes_job": True,
                "change_notes": "N/A",
                "verification_notes": "",
                "event_id": "E4",
            })

    def test_proposal_contract_returns_text_and_partial_state_only(self):
        parsed = minimax.parse_local_beat_proposal({
            "beat_number": 4,
            "beat_text": "Amy opens the basement door.",
            "state_patch": {
                "environment": {
                    "doors": {"basement_door": {"status": "open"}}
                }
            },
        }, 4)
        self.assertEqual(parsed["beat_number"], 4)
        self.assertEqual(
            parsed["state_patch"]["environment"]["doors"]["basement_door"]["status"],
            "open",
        )
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_proposal({
                "beat_number": 4,
                "beat_text": "Amy opens the basement door.",
                "state_patch": {},
                "beat_completes_job": True,
            }, 4)

    def test_invalid_event_ids_are_dropped_and_reported(self):
        valid, diagnostics = minimax.validate_completed_event_ids(
            ["E99"],
            4,
            "The visitor enters the shelter.",
            {"phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 4,
                "required_events": [{"id": "E1", "event": "The visitor enters the shelter."}],
            }]},
        )
        self.assertEqual(valid, [])
        self.assertIn("unknown required event ID E99", diagnostics)

    def test_independent_required_event_can_complete_while_another_is_pending(self):
        valid, diagnostics = minimax.validate_completed_event_ids(
            ["E7"],
            7,
            "Amy opens the window for fresh air.",
            {"phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 8,
                "required_events": [
                    {"id": "E6", "event": "Amy loads the rifle."},
                    {"id": "E7", "event": "Amy opens the window."},
                ],
            }]},
        )
        self.assertEqual(valid, ["E7"])
        self.assertEqual(diagnostics, [])

    def test_planning_metadata_is_safely_stripped_but_embedded_metadata_is_rejected(self):
        cleaned, removed = minimax.sanitize_beat_planning_metadata(
            "The package drops onto the platform. This fulfills E5."
        )
        self.assertEqual(cleaned, "The package drops onto the platform")
        self.assertEqual(removed, ["This fulfills E5."])
        self.assertTrue(
            minimax.validate_beat_planning_metadata(
                "The package drops, required_event: E5, onto the platform."
            )
        )

    def test_metadata_sanitizer_preserves_ordinary_prose(self):
        ordinary = (
            "The empty room is clear. The final state is complete, and the event "
            "ends there."
        )
        self.assertEqual(minimax.sanitize_beat_planning_metadata(ordinary)[0], ordinary)
        self.assertEqual(
            minimax.sanitize_beat_planning_metadata(
                "Amy closes the door. Macro phase 2."
            )[0],
            "Amy closes the door",
        )

    def test_local_prompts_hide_event_ids_and_future_goals(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Amy prepares the house.",
                    "required_events": [{
                        "id": "EVT-CURRENT",
                        "event": "Amy opens the wall safe.",
                    }],
                },
                {
                    "phase_number": 2,
                    "beat_start": 3,
                    "beat_end": 4,
                    "narrative_purpose": "Amy retrieves the rifle.",
                    "required_events": [{
                        "id": "EVT-FUTURE",
                        "event": "Amy retrieves the rifle.",
                    }],
                },
            ],
        }
        fidelity = minimax.build_local_beat_fidelity_messages(
            "Amy protects the house.",
            macro_arc,
            ["Amy reaches the safe.", "Amy opens the wall safe."],
            1,
            2,
            completed_required_event_ids=["EVT-OLD"],
            pending_required_event_ids=["EVT-CURRENT", "EVT-FUTURE"],
            beat_instructions=(
                "Beat 1 should accomplish: Amy reaches the wall safe.\n"
                "Beat 2 should accomplish: Amy opens the wall safe."
            ),
        )
        continuity = minimax.build_local_beat_continuity_messages(
            ["Amy reaches the safe.", "Amy opens the wall safe."],
            1,
            2,
            minimax.new_beat_canonical_state(),
            opening_context="Amy protects the house.",
        )
        finalizer = minimax.build_local_beat_finalizer_messages(
            ["Amy reaches the safe.", "Amy opens the wall safe."],
            1,
            2,
            minimax.new_beat_canonical_state(),
            macro_arc=macro_arc,
            required_event_context=macro_arc["phases"][0]["required_events"],
            fidelity_issues=[],
            continuity_issues=[],
        )
        prompt_text = _message_text(fidelity + continuity + finalizer)
        for event_id in ("EVT-OLD", "EVT-CURRENT", "EVT-FUTURE"):
            self.assertNotIn(event_id, prompt_text)
        self.assertIn("Amy opens the wall safe", prompt_text)
        self.assertNotIn("Amy retrieves the rifle", prompt_text)

    def test_python_maps_unique_current_goals_without_exposing_ids(self):
        arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 2,
            "required_events": [
                {"id": "E1", "event": "Amy retrieves the handgun.", "beat_number": 1},
                {"id": "E2", "event": "Amy loads the handgun.", "beat_number": 2},
            ],
        }]}
        goals = minimax.build_local_beat_goals(
            arc,
            ["Amy retrieves the handgun.", "Amy loads the handgun."],
            1,
            2,
            all_framework_beats=[
                "Amy retrieves the handgun.", "Amy loads the handgun."
            ],
        )
        self.assertEqual([goal["event_ids"] for goal in goals], [["E1"], ["E2"]])
        prompt = _message_text(minimax.build_local_beat_finalizer_messages(
            [goal["goal"] for goal in goals], 1, 2,
            minimax.new_beat_canonical_state(), goals=goals,
        ))
        self.assertNotIn("E1", prompt)
        self.assertNotIn("E2", prompt)

    def test_filtered_state_context_keeps_relevant_facts_only(self):
        state = _state_with_amy()
        state["characters"]["Bob"] = {
            "location": "remote_station",
            "clothing": ["coat"],
            "held_objects": ["rifle"],
        }
        state["environment"]["doors"] = {
            "wall_safe": {"status": "closed"},
            "remote_vault": {"status": "locked"},
        }
        state["environment"]["objects"] = {
            "handgun": {"location": "wall_safe", "condition": "ready"},
            "rifle": {"location": "remote_vault", "condition": "ready"},
        }
        state["threats"] = {
            "threat_7": {
                "name": "the stalker",
                "location": "hallway",
                "status": "alive",
            },
            "threat_8": {
                "name": "the distant raider",
                "location": "remote_station",
                "status": "alive",
            },
        }
        state["story_progress"]["completed_required_event_ids"] = ["EVT-OLD"]
        state = minimax.normalize_beat_canonical_state(state)
        beats = [
            "Amy opens the wall safe while the stalker waits in the hallway.",
            "Amy takes the handgun.",
        ]
        goals = [
            "Amy opens the wall safe.",
            "Amy takes the handgun.",
        ]
        filtered = minimax.filter_beat_canonical_state(state, beats, goals)
        self.assertIn("Amy", filtered["characters"])
        self.assertNotIn("Bob", filtered["characters"])
        self.assertIn("handgun", filtered["environment"]["objects"])
        self.assertNotIn("rifle", filtered["environment"]["objects"])
        self.assertIn("wall_safe", filtered["environment"]["doors"])
        self.assertNotIn("remote_vault", filtered["environment"]["doors"])
        self.assertIn("threat_7", filtered["threats"])
        self.assertNotIn("threat_8", filtered["threats"])
        self.assertNotIn("EVT-OLD", _message_text(
            minimax.build_local_beat_continuity_messages(
                beats, 1, 2, filtered
            )
        ))

    def test_persistent_patch_drops_scene_details_and_unchanged_facts(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["relationships"] = ["siblings with Bob"]
        state = minimax.normalize_beat_canonical_state(state)
        patch = minimax.persistent_beat_state_patch({
            "characters": {
                "Amy": {
                    "location": "kitchen",
                    "clothing": ["black tank top", "denim jeans"],
                    "relationships": ["siblings with Bob"],
                    "current_action": "pours syrup",
                    "physical_position": {"x": 0.3, "y": 1.5, "z": 0.8},
                },
            },
            "environment": {
                "persistent_effects": ["The room smells like toast."],
            },
        }, state)
        self.assertEqual(patch, {})

    def test_persistent_patch_keeps_real_continuity_changes(self):
        patch = minimax.persistent_beat_state_patch({
            "characters": {
                "Amy": {
                    "location": "locked_basement",
                    "contained_in": "locked_basement",
                    "injuries": ["deep shoulder wound"],
                    "held_objects": ["important key"],
                },
            },
            "environment": {
                "doors": {"basement_door": {"status": "locked"}},
            },
            "threats": {
                "threat_1": {"status": "dead"},
            },
        })
        self.assertEqual(
            patch["characters"]["Amy"]["contained_in"], "locked_basement"
        )
        self.assertEqual(
            patch["environment"]["doors"]["basement_door"]["status"], "locked"
        )
        self.assertEqual(patch["threats"]["threat_1"]["status"], "dead")

    def test_ordinary_furniture_is_not_containment(self):
        patch = minimax.persistent_beat_state_patch({
            "characters": {
                "Will": {
                    "contained_in": "dining_table",
                    "posture": "seated",
                },
            },
        })
        self.assertEqual(patch, {})

    def test_persistent_patch_compares_string_and_list_collections(self):
        state = minimax.normalize_beat_canonical_state({
            "characters": {
                "Amy": {
                    "clothing": ["blue shirt"],
                    "relationships": ["siblings with Bob"],
                },
            },
        })
        patch = minimax.persistent_beat_state_patch({
            "characters": {
                "Amy": {
                    "clothing": "blue shirt",
                    "relationships": "siblings with Bob",
                },
            },
        }, state)
        self.assertEqual(patch, {})

    def test_environment_display_labels_resolve_to_existing_ids(self):
        state = minimax.normalize_beat_canonical_state({
            "environment": {
                "doors": {
                    "basement_door": {"name": "Basement Door", "status": "closed"},
                },
                "objects": {
                    "key_1": {"name": "Old Key", "condition": "usable"},
                },
            },
        })
        resolved = minimax._resolve_llm_state_patch_names({
            "environment": {
                "doors": {"Basement Door": {"status": "open"}},
                "objects": {"Old Key": {"condition": "used"}},
            },
        }, state)
        self.assertIn("basement_door", resolved["environment"]["doors"])
        self.assertNotIn("Basement Door", resolved["environment"]["doors"])
        self.assertIn("key_1", resolved["environment"]["objects"])
        self.assertNotIn("Old Key", resolved["environment"]["objects"])

    def test_call_three_names_incoming_state_and_final_beat(self):
        prompt = _message_text(minimax.build_local_beat_proposal_messages(
            1,
            "Amber pours syrup into Will's bowl.",
            minimax.new_beat_canonical_state(),
        ))
        self.assertIn("INCOMING STATE", prompt)
        self.assertIn("FINAL BEAT", prompt)
        self.assertIn("It is valid to return no state changes", prompt)
        self.assertIn("PYTHON-OWNED CANONICAL STATE CONTRACT", prompt)
        self.assertIn('"environment": {', prompt)
        self.assertIn("Python deep-merges the patch", prompt)

    def test_macro_arc_prompt_explains_canonical_state_effect_shape(self):
        prompt = _message_text(minimax.build_beat_arc_plan_messages(
            "Amy locks the basement door.",
            2,
        ))
        self.assertIn("STATE_EFFECTS JSON CONTRACT", prompt)
        self.assertIn('"environment": {"doors"', prompt)
        self.assertIn('"basement_locked": true', prompt)

    def test_invalid_required_event_effect_root_is_rejected_during_arc_parse(self):
        with self.assertRaisesRegex(
            ValueError,
            "must target canonical state",
        ):
            minimax.parse_beat_arc_plan({
                "phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 1,
                    "narrative_purpose": "Advance.",
                    "broad_progression": "Continue.",
                    "characters_introduced": [],
                    "location": "House",
                    "required_end_state": "The door is locked.",
                    "required_events": [{
                        "id": "E1",
                        "event": "Amy locks the basement door.",
                        "beat_number": 1,
                        "state_effects": {"basement_locked": True},
                    }],
                }],
            }, 1)

    def test_empty_state_changes_are_explicit_for_call_four(self):
        prompt = _message_text(minimax.build_local_beat_verification_messages(
            "Amber pours syrup into Will's bowl.",
            minimax.format_state_patch_claims({}),
            "Amber pours syrup into Will's bowl.",
        ))
        self.assertIn("STATE CHANGES:\nNone.", prompt)

    def test_state_metadata_and_coordinates_are_not_beat_prose(self):
        issues = minimax.validate_beat_planning_metadata(
            "The bottle sits at (x: 0.3, y: 1.5, z: 0.8)."
        )
        self.assertIn("final beat contains coordinate metadata", issues)

    def test_repeat_detection_allows_unfinished_continuation(self):
        repeated = minimax._repeated_adjacent_action_issues(
            [
                "The courier pushes the gate open and steps into the courtyard.",
                "The courier pushes the gate open and steps into the courtyard, then approaches the fountain.",
            ],
            1,
        )
        self.assertEqual(repeated[0]["beat_number"], 2)
        self.assertEqual(
            minimax._repeated_adjacent_action_issues(
                [
                    "The climber begins pulling themself onto the ledge.",
                    "The climber finishes pulling themself onto the ledge and stands.",
                ],
                1,
            ),
            [],
        )

    def test_entity_history_requires_canonical_support(self):
        self.assertTrue(
            minimax._unsupported_entity_history_issues(
                "A guard enters with a shoulder wound from an earlier fight.",
                minimax.new_beat_canonical_state(),
                3,
            )
        )
        self.assertEqual(
            minimax._unsupported_entity_history_issues(
                "A guard enters clutching a bleeding shoulder.",
                minimax.new_beat_canonical_state(),
                3,
            ),
            [],
        )

    def test_partial_patch_contract_rejects_legacy_mutation_fields(self):
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(
                {
                    "repairs": [],
                    "state_updates": [{
                        "beat_number": 5,
                        "set": {},
                    }],
                },
                5,
                5,
            )

    def test_partial_patch_preserves_unknown_leaves_and_nested_siblings(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["current_action"] = "watching hallway"
        state["threats"]["zombie_1"] = {
            "location": "kitchen",
            "path": "toward Amy",
        }
        state = minimax.normalize_beat_canonical_state(state)
        original_state = copy.deepcopy(state)
        updated = minimax.apply_state_patch(state, {
            "characters": {
                "Amy": {"location": "hallway"},
            },
            "threats": {
                "zombie_1": {"path": "moving from kitchen window toward Amy"},
            },
            "environment": {
                "basement_door": {"status": "locked"},
            },
        })
        self.assertEqual(updated["characters"]["Amy"]["location"], "hallway")
        self.assertEqual(
            updated["characters"]["Amy"]["current_action"], "watching hallway"
        )
        self.assertEqual(
            updated["threats"]["zombie_1"]["path"],
            "moving from kitchen window toward Amy",
        )
        self.assertEqual(
            updated["environment"]["basement_door"]["status"], "locked"
        )
        self.assertEqual(state, original_state)

    def test_partial_patch_null_clears_and_arrays_replace(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["current_action"] = "running"
        state["characters"]["Amy"]["held_objects"] = ["pistol", "katana"]
        state = minimax.normalize_beat_canonical_state(state)
        updated = minimax.apply_state_patch(state, {
            "characters": {
                "Amy": {
                    "current_action": None,
                    "held_objects": ["pistol"],
                },
            },
        })
        self.assertIsNone(updated["characters"]["Amy"]["current_action"])
        self.assertEqual(updated["characters"]["Amy"]["held_objects"], ["pistol"])

    def test_partial_patch_normalizes_scalar_collections_and_clothing(self):
        updated = minimax.apply_state_patch(
            minimax.new_beat_canonical_state(),
            {
                "characters": {
                    "Amy": {
                        "clothing": "black tank top and denim jeans",
                        "held_objects": "pistol",
                    },
                },
            },
        )
        self.assertEqual(
            updated["characters"]["Amy"]["clothing"],
            ["black tank top", "denim jeans"],
        )
        self.assertEqual(updated["characters"]["Amy"]["held_objects"], ["pistol"])

    def test_clothing_string_and_legacy_object_are_normalized(self):
        string_state = minimax.normalize_beat_canonical_state({
            "characters": {
                "Amy": {"clothing": "black tank top and denim jeans"},
            },
        })
        self.assertEqual(
            string_state["characters"]["Amy"]["clothing"],
            ["black tank top", "denim jeans"],
        )

        legacy_state = minimax.normalize_beat_canonical_state({
            "characters": {
                "Amy": {
                    "clothing": {
                        "upper": "black tank top",
                        "lower": "denim jeans",
                    },
                },
            },
        })
        self.assertEqual(
            legacy_state["characters"]["Amy"]["clothing"],
            ["black tank top", "denim jeans"],
        )

    def test_state_schema_tracks_persistent_entities_and_progress(self):
        state = minimax.normalize_beat_canonical_state({
            "version": 1,
            "characters": {
                "Amy": {
                    "location": "kitchen",
                    "clothing": ["black tank top", "jeans"],
                    "held_objects": ["pistol"],
                }
            },
            "environment": {"doors": {"basement": "locked"}},
            "threats": {
                "threat_1": {
                    "location": "kitchen",
                    "status": "alive",
                    "injuries": ["right arm severed"],
                }
            },
            "story_progress": {
                "completed_required_event_ids": ["E1"],
                "pending_required_event_ids": ["E2"],
            },
        })
        self.assertEqual(state["characters"]["Amy"]["location"], "kitchen")
        self.assertEqual(state["threats"]["threat_1"]["status"], "alive")
        self.assertEqual(
            state["story_progress"]["completed_required_event_ids"], ["E1"]
        )

    def test_python_owns_required_event_collections_in_state_patches(self):
        patch = minimax._python_owned_state_patch({
            "story_progress": {
                "completed_required_event_ids": ["E99"],
                "pending_required_event_ids": [],
                "phase_end_states": {"1": "complete"},
                "current_macro_phase": 1,
            },
        })
        self.assertEqual(
            patch,
            {},
        )

    def test_new_threats_receive_python_owned_stable_ids(self):
        state = minimax.apply_state_patch(
            minimax.new_beat_canonical_state(),
            {"threats": {
                "zombie_a": {"type": "zombie", "status": "alive"},
                "zombie_b": {"type": "zombie", "status": "alive"},
            }},
        )
        self.assertEqual(sorted(state["threats"]), ["threat_1", "threat_2"])
        continued = minimax.apply_state_patch(
            state,
            {"threats": {
                "threat_1": {"injuries": ["left arm severed"]},
            }},
        )
        self.assertEqual(
            continued["threats"]["threat_1"]["injuries"],
            ["left arm severed"],
        )
        self.assertEqual(sorted(continued["threats"]), ["threat_1", "threat_2"])

    def test_canonical_continuity_rejects_duplicate_and_unprepared_weapon_use(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["held_objects"] = ["AR-15"]
        state["characters"]["Amy"]["weapon_state"] = "jammed and dropped"
        issues = minimax._canonical_continuity_issues(
            "Amy retrieves the AR-15 and fires it.", state, 7
        )
        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(all(issue["beat_number"] == 7 for issue in issues))

    def test_canonical_continuity_rejects_equipped_retrieval_and_occupied_hand(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["equipped_objects"] = ["katana"]
        issues = minimax._canonical_continuity_issues(
            "Amy retrieves the katana from the closet while gripping it with both hands and opens the window with her free hand.",
            state,
            8,
        )
        self.assertGreaterEqual(len(issues), 2)

    def test_canonical_continuity_rejects_threat_from_locked_basement(self):
        state = _state_with_amy()
        state["environment"]["doors"] = {"basement": {"status": "locked"}}
        issues = minimax._canonical_continuity_issues(
            "Two zombies crawl out of the basement.", state, 9
        )
        self.assertEqual(len(issues), 1)

    def test_local_continuity_treats_missing_facts_as_unknown(self):
        state = _state_with_amy()
        self.assertEqual(
            minimax._canonical_continuity_issues(
                "Amy retrieves her hidden arsenal from a wall safe.", state, 1
            ),
            [],
        )
        self.assertEqual(
            minimax._canonical_continuity_issues(
                "A zombie crashes through the kitchen window.", state, 2
            ),
            [],
        )
        self.assertEqual(
            minimax._canonical_continuity_issues(
                "Amy opens the unlisted wall safe beside the window.", state, 3
            ),
            [],
        )
        prompt = _message_text(
            minimax.build_local_beat_continuity_messages(
                [
                    "Amy retrieves her hidden arsenal from a wall safe.",
                    "A zombie crashes through the kitchen window.",
                ],
                1,
                2,
                state,
                goals=[
                    {"beat_number": 1, "goal": "Amy retrieves her hidden arsenal."},
                    {"beat_number": 2, "goal": "A zombie enters."},
                ],
            )
        )
        self.assertIn("unknown, not false", prompt)
        self.assertIn("not a complete inventory", prompt)
        self.assertIn("may introduce a new object, threat", prompt)

    def test_local_continuity_still_rejects_hard_known_contradictions(self):
        state = _state_with_amy()
        state["characters"]["Amy"]["location"] = "yard"
        state["environment"]["doors"] = {
            "basement_door": {"status": "locked"},
        }
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "Amy enters the basement without opening the locked basement door.",
                state,
                4,
            )
        )
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "Amy is suddenly inside the basement.", state, 4
            )
        )

        dead_state = minimax.normalize_beat_canonical_state({
            "threats": {
                "threat_1": {"name": "the zombie", "status": "dead"},
            },
        })
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "The zombie gets up and resumes fighting.", dead_state, 5
            )
        )
        destroyed_state = minimax.normalize_beat_canonical_state({
            "threats": {
                "threat_1": {"name": "the zombie", "status": "destroyed"},
            },
        })
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "The zombie returns and attacks again.", destroyed_state, 5
            )
        )

        location_state = _state_with_amy()
        location_state["characters"]["Amy"]["location"] = "kitchen"
        prompt = _message_text(
            minimax.build_local_beat_continuity_messages(
                ["Amy is suddenly inside the basement."],
                6,
                6,
                location_state,
            )
        )
        self.assertIn(
            "contradict an injury, damage, escape, movement, or location",
            prompt,
        )
        self.assertIn("impossible physical transition", prompt)

    def test_terminal_state_and_containment_conflicts_are_deterministic(self):
        state = minimax.new_beat_canonical_state()
        state["story"]["terminal_states"]["threat_area_cleared"] = True
        state["characters"]["PersonB"] = {
            "location": "storage_room",
            "contained_in": "storage_room",
        }
        state["environment"]["doors"] = {
            "storage_room_door": {"status": "locked"},
        }
        state = minimax.normalize_beat_canonical_state(state)
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "Another pursuer charges from the cleared area.", state, 8
            )
        )
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "PersonB stands in the hallway.", state, 9
            )
        )
        self.assertEqual(
            minimax._canonical_continuity_issues(
                "A new breach opens in the outer wall.", state, 10
            ),
            [],
        )

    def test_irreversible_entity_status_and_internal_ids_are_preserved(self):
        state = minimax.normalize_beat_canonical_state({
            "threats": {"threat_1": {"status": "dead", "type": "attacker"}},
        })
        updated = minimax.apply_state_patch(
            state, {"threats": {"threat_1": {"status": "alive"}}}
        )
        self.assertEqual(updated["threats"]["threat_1"]["status"], "dead")
        self.assertTrue(
            minimax._canonical_continuity_issues(
                "The attacker gets up and resumes fighting.", state, 12
            )
        )
        self.assertEqual(
            minimax.sanitize_beat_planning_metadata("The room is now empty.")[0],
            "The room is now empty.",
        )
        self.assertTrue(
            minimax.validate_beat_planning_metadata("The room contains threat_4.")
        )

    def test_finalized_jammed_drop_cannot_remain_ready(self):
        before = minimax.normalize_beat_canonical_state({
            "characters": {"Amy": {"held_objects": ["AR-15"]}},
            "environment": {"objects": {"AR-15": {"condition": "jammed"}}},
        })
        after = minimax.apply_state_patch(before, {
            "characters": {"Amy": {"held_objects": []}},
            "environment": {"objects": {
                "AR-15": {
                    "location": "floor",
                    "condition": "jammed and ready",
                    "loaded": False,
                },
            }},
        })
        self.assertTrue(
            minimax.validate_finalized_beat_state_consistency(
                "Amy drops the jammed AR-15 onto the floor.",
                before,
                after,
                {},
            )
        )
        after["environment"]["objects"]["AR-15"]["condition"] = "jammed"
        self.assertEqual(
            minimax.validate_finalized_beat_state_consistency(
                "Amy drops the jammed AR-15 onto the floor.",
                before,
                after,
                {},
            ),
            [],
        )

    def test_finalized_drop_requires_dropped_weapon_state(self):
        before = _state_with_amy()
        before["characters"]["Amy"]["held_objects"] = ["AR-15"]
        after = copy.deepcopy(before)
        self.assertTrue(
            minimax.validate_finalized_beat_state_consistency(
                "Amy drops the AR-15 onto the floor.",
                before,
                after,
                {},
            )
        )
        after["characters"]["Amy"]["held_objects"] = []
        after["environment"]["objects"]["AR-15"] = {
            "location": "floor",
            "held": False,
            "equipped": False,
        }
        self.assertEqual(
            minimax.validate_finalized_beat_state_consistency(
                "Amy drops the AR-15 onto the floor.",
                before,
                after,
                {"characters": {"Amy": {"held_objects": []}}},
            ),
            [],
        )

    def test_phase_boundary_requires_canonical_end_state(self):
        phase = {
            "phase_number": 1,
            "required_end_state": "Will and Amber are inside locked basement",
            "required_events": [
                {"id": "E1", "event": "Will and Amber enter the basement."},
            ],
        }
        state = minimax.new_beat_canonical_state()
        state["characters"] = {
            "Will": {"location": "basement", "containment": "inside"},
            "Amber": {"location": "basement", "containment": "inside"},
        }
        state["environment"]["doors"] = {"basement": {"status": "locked"}}
        self.assertEqual(
            minimax._phase_required_end_state_issues(phase, state), []
        )


class _LocalValidationStub:
    def __init__(
        self,
        repairs=None,
        state_updates=None,
        omit_state_update=None,
        text_retries=None,
        verification_results=None,
        proposal_sequences=None,
        continuity_recheck_results=None,
    ):
        self.repairs = dict(repairs or {})
        self.state_updates = dict(state_updates or {})
        self.omit_state_update = omit_state_update
        self.text_retries = dict(text_retries or {})
        self.verification_results = dict(verification_results or {})
        self.proposal_sequences = {
            beat_number: list(sequence)
            for beat_number, sequence in (proposal_sequences or {}).items()
        }
        self.continuity_recheck_results = {
            beat_number: list(results)
            for beat_number, results in (continuity_recheck_results or {}).items()
        }
        self.calls = []
        self.messages_by_purpose = {}
        self.finalizer_calls = 0
        self.verification_calls = 0
        self.proposal_counts = {}
        self.continuity_recheck_counts = {}

    def __call__(self, messages, **kwargs):
        metadata = kwargs.get("history_metadata", {})
        purpose = metadata.get("purpose")
        self.calls.append(metadata)
        self.messages_by_purpose.setdefault(purpose, []).append(messages)
        if purpose == "beat_local_fidelity":
            records = []
            in_current_beats = False
            for line in str(messages[1]["content"]).splitlines():
                line = line.strip()
                if line == "CURRENT BEATS":
                    in_current_beats = True
                    continue
                if line == "CHECK ONLY THESE QUESTIONS":
                    break
                if not in_current_beats:
                    continue
                if not line.startswith("Beat ") or ": " not in line:
                    continue
                number_text, beat_text = line[5:].split(": ", 1)
                if not number_text.isdigit():
                    continue
                records.append({
                    "beat_number": int(number_text),
                    "unedited_beat": beat_text,
                    "edited_beat": beat_text,
                    "edited": False,
                })
            return {"beats": records}
        if purpose == "beat_local_continuity":
            result = {"valid": True, "issues": []}
            if metadata.get("continuity_recheck"):
                beat_number = metadata["beat_number"]
                count = self.continuity_recheck_counts.get(beat_number, 0)
                self.continuity_recheck_counts[beat_number] = count + 1
                results = self.continuity_recheck_results.get(beat_number, [])
                if results:
                    result = copy.deepcopy(results[min(count, len(results) - 1)])
            if set(result) == {"beats"}:
                return result
            records = []
            in_beats = False
            for line in str(messages[1]["content"]).splitlines():
                line = line.strip()
                if line == "BEATS TO CHECK":
                    in_beats = True
                    continue
                if line == "RULES":
                    break
                if not in_beats or not line.startswith("Beat ") or ": " not in line:
                    continue
                number_text, beat_text = line[5:].split(": ", 1)
                if not number_text.isdigit():
                    continue
                edited = not result.get("valid", True)
                records.append({
                    "beat_number": int(number_text),
                    "unedited_beat": beat_text,
                    "edited_beat": (
                        f"{beat_text} Continuity repair."
                        if edited else beat_text
                    ),
                    "reason_for_edit": (
                        result.get("issues", [{}])[0].get(
                            "problem", "Continuity test repair"
                        )
                        if edited else "N/A"
                    ),
                    "edited": edited,
                })
            return {"beats": records}
        if purpose == "beat_local_regeneration":
            return {"beats": [{
                "beat_number": metadata["beat_number"],
                "beat_text": f"Replacement beat {metadata['beat_number']}.",
            }]}
        if purpose == "beat_state_extrator":
            self.finalizer_calls += 1
            beat_number = metadata["beat_number"]
            self.proposal_counts[beat_number] = self.proposal_counts.get(beat_number, 0) + 1
            update = copy.deepcopy(
                self.state_updates.get(beat_number, _empty_patch(beat_number))
            )
            sequence = self.proposal_sequences.get(beat_number)
            if sequence:
                text = sequence[min(
                    self.proposal_counts[beat_number] - 1,
                    len(sequence) - 1,
                )]
            else:
                text = self.repairs.get(beat_number, f"Framework beat {beat_number}.")
            if beat_number in self.text_retries and self.proposal_counts[beat_number] > 1:
                text = self.text_retries[beat_number]
            return {
                "beat_number": beat_number,
                "beat_text": text,
                "state_patch": update.get("patch", {}),
            }
        if purpose == "beat_finalizer":
            self.verification_calls += 1
            beat_number = metadata["beat_number"]
            result = self.verification_results.get(
                beat_number, {
                    "beat_supports_state_changes": True,
                    "beat_completes_job": True,
                    "change_notes": "N/A",
                    "verification_notes": "N/A",
                }
            )
            if isinstance(result, list):
                index = min(self.verification_calls - 1, len(result) - 1)
                result = result[index]
            return copy.deepcopy(result)
        raise AssertionError(f"Unexpected LLM purpose: {purpose}")


class _BoundaryFinalizerStub(_LocalValidationStub):
    def __call__(self, messages, **kwargs):
        metadata = kwargs.get("history_metadata", {})
        if metadata.get("purpose") != "beat_state_extrator":
            return super().__call__(messages, **kwargs)
        self.finalizer_calls += 1
        beat_number = metadata["beat_number"]
        if beat_number != 4:
            return {
                "beat_number": beat_number,
                "beat_text": f"Framework beat {beat_number}.",
                "state_patch": {},
            }
        return {
            "beat_number": beat_number,
            "beat_text": "Will and Amber enter the basement and Amy locks the door.",
            "state_patch": {
                "characters": {
                    "Will": {"location": "basement", "containment": "inside"},
                    "Amber": {"location": "basement", "containment": "inside"},
                },
                "environment": {
                    "doors": {"basement": {"status": "locked"}},
                },
            },
        }


class ForwardCoordinatorTests(unittest.TestCase):
    @staticmethod
    def _seed_checkpoint(state_path, total_segments=8, finalized_through=4,
                         state=None, phrase_exclusions=()):
        framework = [
            f"Framework beat {number}."
            for number in range(1, total_segments + 1)
        ]
        state = copy.deepcopy(state or minimax.new_beat_canonical_state())
        fingerprint = minimax.beat_validation_fingerprint(
            "A source story.", total_segments, {"phases": []},
            phrase_exclusions=phrase_exclusions,
        )
        checkpoint = {
            "version": minimax.BEAT_VALIDATION_STATE_VERSION,
            "fingerprint": fingerprint,
            "total_beats": total_segments,
            "framework_beats": framework,
            "finalized_beats": [
                {"beat_number": number, "beat_text": framework[number - 1]}
                for number in range(1, finalized_through + 1)
            ],
            "beat_state_after": {
                str(number): copy.deepcopy(state)
                for number in range(1, finalized_through + 1)
            },
            "current_beat_state": copy.deepcopy(state),
            "completed_required_event_ids": [],
            "pending_required_event_ids": [],
            "finalized_through": finalized_through,
            "next_window_start": finalized_through + 1,
        }
        minimax.save_beat_validation_state(checkpoint, str(state_path))

    @staticmethod
    def _run_from_checkpoint(directory, stub, state=None, phrase_exclusions=()):
        beats_path = Path(directory) / "beats.txt"
        state_path = Path(directory) / "beat_validation_state.json"
        ForwardCoordinatorTests._seed_checkpoint(
            state_path, state=state, phrase_exclusions=phrase_exclusions
        )

        def must_not_generate_framework():
            raise AssertionError("framework was regenerated during resume")

        result = minimax._run_forward_beat_validation(
            must_not_generate_framework,
            "A source story.",
            8,
            {"phases": []},
            str(beats_path),
            stub,
            state_path=str(state_path),
            phrase_exclusions=phrase_exclusions,
        )
        return result, state_path

    def test_event_completion_never_calls_prose_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            macro_arc = {
                "phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 1,
                    "required_events": [{
                        "id": "E1",
                        "event": "Amy unlocks and opens the basement door.",
                        "beat_number": 1,
                    }],
                }],
            }
            checkpoint = {
                "version": minimax.BEAT_VALIDATION_STATE_VERSION,
                "fingerprint": minimax.beat_validation_fingerprint(
                    "A source story.", 1, macro_arc,
                ),
                "total_beats": 1,
                "framework_beats": ["Amy unlocks and opens the basement door."],
                "finalized_beats": [],
                "beat_state_after": {},
                "current_beat_state": minimax.new_beat_canonical_state(),
                "completed_required_event_ids": [],
                "pending_required_event_ids": ["E1"],
                "finalized_through": 0,
                "next_window_start": 1,
            }
            minimax.save_beat_validation_state(checkpoint, str(state_path))
            with mock.patch.object(
                minimax,
                "required_event_is_grounded_in_beat_text",
                side_effect=AssertionError("event completion parsed prose"),
            ):
                minimax._run_forward_beat_validation(
                    lambda: (_ for _ in ()).throw(
                        AssertionError("unexpected generation")
                    ),
                    "A source story.",
                    1,
                    macro_arc,
                    str(beats_path),
                    _LocalValidationStub(),
                    state_path=str(state_path),
                )
            saved = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(saved["completed_required_event_ids"], ["E1"])

    def test_unchanged_text_is_preserved_when_repair_is_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub()
            result, _ = self._run_from_checkpoint(directory, stub)
            self.assertEqual(result[4:], [
                "Framework beat 5.",
                "Framework beat 6.",
                "Framework beat 7.",
                "Framework beat 8.",
            ])
            self.assertEqual(stub.finalizer_calls, 4)

    def test_phase_three_changes_never_trigger_continuity_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(
                proposal_sequences={
                    5: [
                        "Amy moves to the hallway.",
                        "Amy remains in the kitchen.",
                    ],
                },
                continuity_recheck_results={
                    5: [
                        {
                            "valid": False,
                            "issues": [{
                                "beat_number": 5,
                                "type": "location",
                                "problem": "Amy cannot be in the hallway from the accepted state.",
                            }],
                        },
                        {"valid": True, "issues": []},
                    ],
                },
            )
            result, _ = self._run_from_checkpoint(
                directory, stub, _state_with_amy()
            )

            self.assertEqual(result[4], "Amy moves to the hallway.")
            self.assertEqual(stub.continuity_recheck_counts, {})
            continuity_prompts = stub.messages_by_purpose["beat_local_continuity"]
            self.assertEqual(len(continuity_prompts), 2)
            finalize_prompts = stub.messages_by_purpose["beat_state_extrator"]
            self.assertEqual(len(finalize_prompts), 4)

    def test_phase_three_changes_never_trigger_barrier_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            state = minimax.new_beat_canonical_state()
            state["environment"]["doors"] = {
                "barrier": {"status": "locked"},
            }
            state = minimax.normalize_beat_canonical_state(state)
            stub = _LocalValidationStub(
                proposal_sequences={
                    5: [
                        "The barrier is unlocked.",
                        "The barrier remains locked.",
                    ],
                },
                continuity_recheck_results={
                    5: [
                        {
                            "valid": False,
                            "issues": [{
                                "beat_number": 5,
                                "type": "barrier",
                                "problem": "The accepted canonical state says the barrier is locked.",
                            }],
                        },
                        {"valid": True, "issues": []},
                    ],
                },
            )
            result, _ = self._run_from_checkpoint(directory, stub, state)

            self.assertEqual(result[4], "The barrier is unlocked.")
            self.assertEqual(stub.continuity_recheck_counts, {})
            continuity_prompts = stub.messages_by_purpose["beat_local_continuity"]
            self.assertEqual(len(continuity_prompts), 2)
            finalize_prompts = stub.messages_by_purpose["beat_state_extrator"]
            self.assertEqual(len(finalize_prompts), 4)

    def test_verification_retry_stays_forward_only_after_phase_three(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(
                proposal_sequences={
                    5: [
                        "Amy crosses the room.",
                        "Amy reaches the window.",
                    ],
                },
                continuity_recheck_results={
                    5: [
                        {"valid": True, "issues": []},
                        {"valid": True, "issues": []},
                    ],
                },
                verification_results={
                    5: [
                        {
                            "beat_supports_state_changes": False,
                            "beat_completes_job": True,
                            "change_notes": "N/A",
                            "verification_notes": "The proposed state is unsupported.",
                        },
                        {
                            "beat_supports_state_changes": True,
                            "beat_completes_job": True,
                            "change_notes": "N/A",
                            "verification_notes": "N/A",
                        },
                    ],
                },
            )
            self._run_from_checkpoint(directory, stub)

            beat_five_calls = [
                call for call in stub.calls if call.get("beat_number") == 5
            ]
            self.assertEqual(
                [call["purpose"] for call in beat_five_calls],
                [
                    "beat_state_extrator",
                    "beat_finalizer",
                    "beat_state_extrator",
                    "beat_finalizer",
                ],
            )
            self.assertEqual(
                [call.get("continuity_recheck", False) for call in beat_five_calls],
                [False, False, False, False],
            )

    def test_unchanged_beat_does_not_trigger_continuity_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub()
            self._run_from_checkpoint(directory, stub)

            rechecks = [
                call for call in stub.calls
                if call.get("continuity_recheck")
            ]
            self.assertEqual(rechecks, [])
            self.assertEqual(
                sum(call.get("purpose") == "beat_local_continuity" for call in stub.calls),
                2,
            )

    def test_phase_boundary_is_repaired_before_any_beat_is_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            framework = [
                "Amy guides Will and Amber toward the basement.",
                "The children continue toward the basement.",
                "Amy reaches the basement door.",
                "Amy begins retrieving a weapon.",
            ]
            macro_arc = {
                "phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 4,
                    "required_end_state": "Will and Amber are inside locked basement",
                    "required_events": [{
                        "id": "E1",
                        "event": "Will and Amber enter the basement.",
                        "beat_number": 4,
                    }],
                }],
            }
            checkpoint = {
                "version": minimax.BEAT_VALIDATION_STATE_VERSION,
                "fingerprint": minimax.beat_validation_fingerprint(
                    "A source story.", 4, macro_arc,
                ),
                "total_beats": 4,
                "framework_beats": framework,
                "finalized_beats": [],
                "beat_state_after": {},
                "current_beat_state": minimax.new_beat_canonical_state(),
                "completed_required_event_ids": [],
                "pending_required_event_ids": ["E1"],
                "finalized_through": 0,
                "next_window_start": 1,
            }
            minimax.save_beat_validation_state(checkpoint, str(state_path))
            stub = _BoundaryFinalizerStub()
            result = minimax._run_forward_beat_validation(
                lambda: (_ for _ in ()).throw(AssertionError("unexpected generation")),
                "A source story.",
                4,
                macro_arc,
                str(beats_path),
                stub,
                state_path=str(state_path),
            )
            self.assertEqual(result[3], "Will and Amber enter the basement and Amy locks the door.")
            self.assertEqual(stub.finalizer_calls, 4)
            saved = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(saved["finalized_through"], 4)
            self.assertEqual(saved["beat_state_after"]["4"]["environment"]["doors"]["basement"]["status"], "locked")

    def test_uncompleted_assigned_goal_retries_ten_times(self):
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            macro_arc = {
                "phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 4,
                    "required_events": [{
                        "id": "E1",
                        "event": "Will and Amber enter the basement.",
                        "beat_number": 4,
                    }],
                }],
            }
            checkpoint = {
                "version": minimax.BEAT_VALIDATION_STATE_VERSION,
                "fingerprint": minimax.beat_validation_fingerprint(
                    "A source story.", 4, macro_arc,
                ),
                "total_beats": 4,
                "framework_beats": [
                    f"Framework beat {number}." for number in range(1, 5)
                ],
                "finalized_beats": [],
                "beat_state_after": {},
                "current_beat_state": minimax.new_beat_canonical_state(),
                "completed_required_event_ids": [],
                "pending_required_event_ids": ["E1"],
                "finalized_through": 0,
                "next_window_start": 1,
            }
            minimax.save_beat_validation_state(checkpoint, str(state_path))

            stub = _LocalValidationStub(
                verification_results={
                    4: {
                        "beat_supports_state_changes": True,
                        "beat_completes_job": False,
                        "change_notes": "N/A",
                        "verification_notes": "The beat does not complete the assigned entry.",
                    },
                },
            )
            with self.assertRaisesRegex(
                ValueError,
                r"Beat 4 could not pass local semantic verification",
            ):
                minimax._run_forward_beat_validation(
                    lambda: (_ for _ in ()).throw(
                        AssertionError("unexpected generation")
                    ),
                    "A source story.",
                    4,
                    macro_arc,
                    str(beats_path),
                    stub,
                    state_path=str(state_path),
                )
            self.assertEqual(stub.finalizer_calls, 13)

    def test_exhausted_single_beat_restarts_with_a_new_story_arc(self):
        macro_arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Advance the story.",
            "broad_progression": "Continue.",
            "characters_introduced": [],
            "location": "unknown",
            "required_events": [],
            "required_end_state": "Continue.",
        }]}
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            arc_path = Path(directory) / "story_arc.json"
            state_path = Path(directory) / "beat_validation_state.json"
            with mock.patch.object(minimax, "BEAT_PROCESS_ATTEMPTS", 1), \
                 mock.patch.object(minimax, "load_story_arc", return_value=None), \
                 mock.patch.object(
                     minimax, "parse_beat_arc_plan", return_value=macro_arc
                 ) as parse_arc, \
                 mock.patch.object(
                     minimax,
                     "parse_beat_arc_fidelity",
                     return_value={"valid": True, "issues": []},
                 ), \
                 mock.patch.object(
                     minimax,
                     "_run_forward_beat_validation",
                     side_effect=[
                         minimax.BeatValidationExhaustedError(1),
                         ["Beat 1"],
                     ],
                 ) as run_validation:
                result = minimax.generate_beats_from_story(
                    "A source story.",
                    1,
                    path=str(beats_path),
                    llm_request=lambda *args, **kwargs: {},
                    story_arc_path=str(arc_path),
                    validation_state_path=str(state_path),
                    reuse_story_arc=False,
                )

            self.assertEqual(result, ["Beat 1"])
            self.assertEqual(run_validation.call_count, 2)
            self.assertEqual(parse_arc.call_count, 2)
            self.assertTrue(arc_path.exists())
            self.assertFalse(state_path.exists())

    def test_non_beat_failure_does_not_restart_with_a_new_story_arc(self):
        macro_arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Advance the story.",
            "broad_progression": "Continue.",
            "characters_introduced": [],
            "location": "unknown",
            "required_events": [],
            "required_end_state": "Continue.",
        }]}
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            arc_path = Path(directory) / "story_arc.json"
            state_path = Path(directory) / "beat_validation_state.json"
            with mock.patch.object(minimax, "load_story_arc", return_value=None), \
                 mock.patch.object(
                     minimax, "parse_beat_arc_plan", return_value=macro_arc
                 ) as parse_arc, \
                 mock.patch.object(
                     minimax,
                     "parse_beat_arc_fidelity",
                     return_value={"valid": True, "issues": []},
                 ), \
                 mock.patch.object(
                     minimax,
                     "_run_forward_beat_validation",
                     side_effect=ValueError("checkpoint is corrupted"),
                 ) as run_validation:
                with self.assertRaisesRegex(ValueError, "checkpoint is corrupted"):
                    minimax.generate_beats_from_story(
                        "A source story.",
                        1,
                        path=str(beats_path),
                        llm_request=lambda *args, **kwargs: {},
                        story_arc_path=str(arc_path),
                        validation_state_path=str(state_path),
                        reuse_story_arc=False,
                    )

            self.assertEqual(run_validation.call_count, 1)
            self.assertEqual(parse_arc.call_count, 1)

    def test_completed_checkpoint_recovers_from_handoff_index_error(self):
        macro_arc = {"phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 1,
            "narrative_purpose": "Advance the story.",
            "broad_progression": "Continue.",
            "characters_introduced": [],
            "location": "unknown",
            "required_events": [],
            "required_end_state": "Continue.",
        }]}
        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            arc_path = Path(directory) / "story_arc.json"
            state_path = Path(directory) / "beat_validation_state.json"
            state = minimax.new_beat_canonical_state()
            checkpoint = {
                "version": minimax.BEAT_VALIDATION_STATE_VERSION,
                "fingerprint": minimax.beat_validation_fingerprint(
                    "A source story.", 1, macro_arc,
                ),
                "total_beats": 1,
                "framework_beats": ["Framework beat 1."],
                "finalized_beats": [{
                    "beat_number": 1,
                    "beat_text": "Accepted beat 1.",
                }],
                "beat_state_after": {"1": copy.deepcopy(state)},
                "current_beat_state": copy.deepcopy(state),
                "completed_required_event_ids": [],
                "pending_required_event_ids": [],
                "finalized_through": 1,
                "next_window_start": None,
            }
            minimax.save_beat_validation_state(checkpoint, str(state_path))
            with mock.patch.object(minimax, "load_story_arc", return_value=None), \
                 mock.patch.object(
                     minimax, "parse_beat_arc_plan", return_value=macro_arc
                 ), \
                 mock.patch.object(
                     minimax,
                     "parse_beat_arc_fidelity",
                     return_value={"valid": True, "issues": []},
                 ), \
                 mock.patch.object(
                     minimax,
                     "_run_forward_beat_validation",
                     side_effect=IndexError("list index out of range"),
                 ) as run_validation:
                result = minimax.generate_beats_from_story(
                    "A source story.",
                    1,
                    path=str(beats_path),
                    llm_request=lambda *args, **kwargs: {},
                    story_arc_path=str(arc_path),
                    validation_state_path=str(state_path),
                    reuse_story_arc=False,
                )

            self.assertEqual([str(beat) for beat in result], ["Accepted beat 1."])
            self.assertEqual(run_validation.call_count, 1)
            self.assertEqual(
                [str(beat) for beat in minimax.load_beats(str(beats_path))],
                ["Accepted beat 1."],
            )

    def test_repaired_beat_does_not_rewrite_adjacent_beats(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(repairs={6: "Repaired beat 6."})
            result, _ = self._run_from_checkpoint(directory, stub)
            self.assertEqual(result[4:], [
                "Framework beat 5.",
                "Repaired beat 6.",
                "Framework beat 7.",
                "Framework beat 8.",
            ])

    def test_prohibited_phrase_retries_only_the_invalid_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(
                repairs={8: "The zombie is twitching."},
                state_updates={
                    5: {
                        "beat_number": 5,
                        "patch": {
                            "characters": {"Amy": {"location": "hallway"}},
                        },
                    },
                    7: {
                        "beat_number": 7,
                        "patch": {
                            "threats": {
                                "zombie_1": {"status": "alive"},
                            },
                        },
                    },
                },
                text_retries={8: "The zombie advances toward Amy."},
            )
            result, state_path = self._run_from_checkpoint(
                directory,
                stub,
                phrase_exclusions=["twitching"],
            )
            self.assertEqual(result[4:], [
                "Framework beat 5.",
                "Framework beat 6.",
                "Framework beat 7.",
                "The zombie advances toward Amy.",
            ])
            purposes = [call.get("purpose") for call in stub.calls]
            self.assertEqual(purposes.count("beat_state_extrator"), 5)
            self.assertEqual(purposes.count("beat_local_text_retry"), 0)
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(
                checkpoint["beat_state_after"]["7"]["characters"]["Amy"]["location"],
                "hallway",
            )
            self.assertEqual(
                checkpoint["beat_state_after"]["8"]["threats"]["threat_1"]["status"],
                "alive",
            )

    def test_embedded_internal_id_retries_only_that_beat(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(
                repairs={8: "The room contains threat_4."},
                text_retries={8: "The room is empty."},
            )
            result, _ = self._run_from_checkpoint(directory, stub)
            self.assertEqual(result[7], "The room is empty.")
            purposes = [call.get("purpose") for call in stub.calls]
            self.assertEqual(purposes.count("beat_local_text_retry"), 0)

    def test_state_text_mismatch_is_delegated_to_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            state = _state_with_amy()
            state["characters"]["Amy"]["held_objects"] = ["AR-15"]
            state = minimax.normalize_beat_canonical_state(state)
            stub = _LocalValidationStub(
                repairs={5: "Amy drops the AR-15 onto the floor."},
                verification_results={
                    5: [
                        {
                            "beat_supports_state_changes": False,
                            "beat_completes_job": True,
                            "change_notes": "N/A",
                            "verification_notes": "The proposed state does not show the rifle on the floor.",
                        },
                        {
                            "beat_supports_state_changes": True,
                            "beat_completes_job": True,
                            "change_notes": "N/A",
                            "verification_notes": "N/A",
                        },
                    ]
                },
            )
            result, _ = self._run_from_checkpoint(directory, stub, state)
            self.assertEqual(result[4], "Amy drops the AR-15 onto the floor.")
            purposes = [call.get("purpose") for call in stub.calls]
            self.assertEqual(purposes.count("beat_finalizer"), 5)

    def test_sequential_state_patches_accumulate_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            initial = _state_with_amy()
            stub = _LocalValidationStub(state_updates={
                5: {
                    "beat_number": 5,
                    "patch": {
                        "characters": {
                            "Amy": {"held_objects": ["pistol"]},
                        },
                    },
                },
                6: {
                    "beat_number": 6,
                    "patch": {
                        "characters": {
                            "Amy": {"location": "hallway"},
                        },
                    },
                },
            })
            _, state_path = self._run_from_checkpoint(directory, stub, initial)
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            state_after_5 = checkpoint["beat_state_after"]["5"]
            state_after_6 = checkpoint["beat_state_after"]["6"]
            self.assertEqual(
                state_after_5["characters"]["Amy"]["held_objects"], ["pistol"]
            )
            self.assertEqual(
                state_after_6["characters"]["Amy"]["held_objects"], ["pistol"]
            )
            self.assertEqual(
                state_after_6["characters"]["Amy"]["location"], "hallway"
            )

    def test_clothing_persists_without_repeated_clothing_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub()
            _, state_path = self._run_from_checkpoint(
                directory, stub, _state_with_amy()
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(
                checkpoint["beat_state_after"]["8"]["characters"]["Amy"]["clothing"],
                ["black tank top", "denim jeans"],
            )

    def test_threat_persists_then_is_explicitly_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = _LocalValidationStub(state_updates={
                5: {
                    "beat_number": 5,
                    "patch": {"threats": {"threat_1": {
                        "location": "kitchen",
                        "status": "alive",
                        "has_exited": False,
                    }}},
                },
                7: {
                    "beat_number": 7,
                    "patch": {"threats": {"threat_1": {
                        "status": "dead",
                        "has_exited": True,
                    }}},
                },
            })
            _, state_path = self._run_from_checkpoint(directory, stub)
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(
                checkpoint["beat_state_after"]["6"]["threats"]["threat_1"]["status"],
                "alive",
            )
            self.assertEqual(
                checkpoint["beat_state_after"]["8"]["threats"]["threat_1"]["status"],
                "dead",
            )
            self.assertTrue(
                checkpoint["beat_state_after"]["8"]["threats"]["threat_1"]["has_exited"]
            )

    def test_finalized_prefix_remains_immutable_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            initial = _state_with_amy()
            stub = _LocalValidationStub(repairs={6: "Repaired beat 6."})
            _, state_path = self._run_from_checkpoint(directory, stub, initial)
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(
                [record["beat_text"] for record in checkpoint["finalized_beats"][:4]],
                [f"Framework beat {number}." for number in range(1, 5)],
            )
            for number in range(1, 5):
                self.assertEqual(
                    checkpoint["beat_state_after"][str(number)],
                    initial,
                )
            self.assertNotIn(
                "beat_global_fidelity_audit",
                {call.get("purpose") for call in stub.calls},
            )


if __name__ == "__main__":
    unittest.main()
