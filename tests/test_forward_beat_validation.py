import copy
import tempfile
import unittest
from pathlib import Path

import minimax


def _empty_patch(beat_number, completed_event_ids=None):
    return {
        "beat_number": beat_number,
        "patch": {},
        "completed_event_ids": list(completed_event_ids or []),
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


class ForwardBeatValidationTests(unittest.TestCase):
    def test_windows_are_small_and_overlap_at_the_finalized_anchor(self):
        windows = minimax.build_beat_validation_windows(20)
        self.assertEqual(
            [(item["window_start"], item["window_end"]) for item in windows],
            [(1, 4), (4, 8), (8, 12), (12, 16), (16, 20)],
        )
        self.assertEqual(
            [item["anchor_beat_number"] for item in windows],
            [None, 4, 8, 12, 16],
        )
        self.assertEqual(
            [(item["mutable_start"], item["mutable_end"]) for item in windows],
            [(1, 4), (5, 8), (9, 12), (13, 16), (17, 20)],
        )

    def test_partial_final_window_is_supported(self):
        windows = minimax.build_beat_validation_windows(10)
        self.assertEqual(
            [(item["window_start"], item["window_end"]) for item in windows],
            [(1, 4), (4, 8), (8, 10)],
        )

    def test_finalizer_uses_repairs_only_text_contract(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [{
                    "beat_number": 2,
                    "beat_text": "Repaired beat 2.",
                }],
                "state_updates": [_empty_patch(number) for number in range(1, 4)],
            },
            1,
            3,
        )
        self.assertEqual(
            parsed["repairs"],
            [{"beat_number": 2, "beat_text": "Repaired beat 2."}],
        )
        self.assertEqual(
            [item["beat_number"] for item in parsed["state_updates"]],
            [1, 2, 3],
        )
        self.assertNotIn("changed", parsed)
        self.assertNotIn("state_after", parsed)
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization({"beats": []}, 1, 3)

    def test_missing_mutable_state_update_is_rejected(self):
        response = {
            "repairs": [],
            "state_updates": [_empty_patch(number) for number in (5, 6, 8)],
        }
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(response, 5, 8)

    def test_immutable_repair_target_is_rejected(self):
        response = {
            "repairs": [{
                "beat_number": 4,
                "beat_text": "Rewritten finalized anchor.",
            }],
            "state_updates": [_empty_patch(number) for number in range(5, 9)],
        }
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(response, 5, 8)

    def test_empty_patch_is_accepted_and_normalized(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [],
                "state_updates": [{
                    "beat_number": 5,
                    "patch": {},
                    "completed_event_ids": [],
                }],
            },
            5,
            5,
        )
        self.assertEqual(parsed["state_updates"], [_empty_patch(5)])

    def test_finalizer_requires_separate_completed_event_ids(self):
        parsed = minimax.parse_local_beat_finalization(
            {
                "repairs": [],
                "state_updates": [{
                    "beat_number": 5,
                    "patch": {},
                    "completed_event_ids": ["E3"],
                }],
            },
            5,
            5,
        )
        self.assertEqual(parsed["state_updates"][0]["completed_event_ids"], ["E3"])
        with self.assertRaises(ValueError):
            minimax.parse_local_beat_finalization(
                {"repairs": [], "state_updates": [{"beat_number": 5, "patch": {}}]},
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
            {"story_progress": {"current_macro_phase": 1}},
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
    ):
        self.repairs = dict(repairs or {})
        self.state_updates = dict(state_updates or {})
        self.omit_state_update = omit_state_update
        self.text_retries = dict(text_retries or {})
        self.calls = []
        self.finalizer_calls = 0

    def __call__(self, messages, **kwargs):
        metadata = kwargs.get("history_metadata", {})
        purpose = metadata.get("purpose")
        self.calls.append(metadata)
        start = metadata.get("mutable_start", 1)
        end = metadata.get("mutable_end", 1)
        if purpose in {"beat_local_fidelity", "beat_local_continuity"}:
            return {"valid": True, "issues": []}
        if purpose == "beat_local_regeneration":
            return {"beats": [{
                "beat_number": metadata["beat_number"],
                "beat_text": f"Replacement beat {metadata['beat_number']}.",
            }]}
        if purpose == "beat_local_text_retry":
            beat_number = metadata["beat_number"]
            return {"beats": [{
                "beat_number": beat_number,
                "beat_text": self.text_retries.get(
                    beat_number, f"Locally repaired beat {beat_number}."
                ),
            }]}
        if purpose == "beat_local_finalize":
            self.finalizer_calls += 1
            updates = []
            for beat_number in range(start, end + 1):
                if beat_number == self.omit_state_update:
                    continue
                update = copy.deepcopy(
                    self.state_updates.get(beat_number, _empty_patch(beat_number))
                )
                update.setdefault("completed_event_ids", [])
                updates.append(update)
            return {
                "repairs": [
                    {"beat_number": beat_number, "beat_text": text}
                    for beat_number, text in sorted(self.repairs.items())
                    if start <= beat_number <= end
                ],
                "state_updates": updates,
            }
        raise AssertionError(f"Unexpected LLM purpose: {purpose}")


class _BoundaryFinalizerStub(_LocalValidationStub):
    def __call__(self, messages, **kwargs):
        metadata = kwargs.get("history_metadata", {})
        if metadata.get("purpose") != "beat_local_finalize":
            return super().__call__(messages, **kwargs)
        self.finalizer_calls += 1
        start = metadata.get("mutable_start", 1)
        end = metadata.get("mutable_end", 1)
        if self.finalizer_calls == 1:
            return {
                "repairs": [],
                "state_updates": [_empty_patch(number) for number in range(start, end + 1)],
            }
        return {
            "repairs": [{
                "beat_number": 4,
                "beat_text": "Will and Amber enter the basement and Amy locks the door.",
            }],
            "state_updates": [
                _empty_patch(1),
                _empty_patch(2),
                _empty_patch(3),
                {
                    "beat_number": 4,
                    "patch": {
                        "characters": {
                            "Will": {"location": "basement", "containment": "inside"},
                            "Amber": {"location": "basement", "containment": "inside"},
                        },
                        "environment": {
                            "doors": {"basement": {"status": "locked"}},
                        },
                    },
                    "completed_event_ids": ["E1"],
                },
            ],
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
            "version": 1,
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
            "next_window_start": finalized_through,
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
            self.assertEqual(stub.finalizer_calls, 1)

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
                    }],
                }],
            }
            checkpoint = {
                "version": 1,
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
            self.assertEqual(stub.finalizer_calls, 2)
            saved = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(saved["finalized_through"], 4)
            self.assertEqual(saved["beat_state_after"]["4"]["environment"]["doors"]["basement"]["status"], "locked")

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
            self.assertEqual(purposes.count("beat_local_finalize"), 1)
            self.assertEqual(purposes.count("beat_local_text_retry"), 1)
            checkpoint = minimax.load_beat_validation_state(str(state_path))
            self.assertEqual(
                checkpoint["beat_state_after"]["7"]["characters"]["Amy"]["location"],
                "hallway",
            )
            self.assertEqual(
                checkpoint["beat_state_after"]["8"]["threats"]["threat_1"]["status"],
                "alive",
            )

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
