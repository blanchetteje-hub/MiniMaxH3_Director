import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import minimax


ARC = {"phases": [{
    "phase_number": 1,
    "beat_start": 1,
    "beat_end": 1,
    "narrative_purpose": "Complete the authorized action.",
    "broad_progression": "The operator completes the action.",
    "characters_introduced": ["Operator"],
    "location": "Location X",
    "required_end_state": "The primary barrier is open.",
    "required_events": [{
        "id": "E1",
        "event": "Operator opens the primary barrier.",
        "beat_number": 1,
        "state_effects": [
            {"op": "set_barrier_state", "entity": "primary", "value": "open"}
        ],
    }],
}]}


class ForwardBeatValidationTests(unittest.TestCase):
    def test_coherence_prompt_uses_previous_accepted_beat_when_available(self):
        beats = [
            "Tala opens the gate.",
            "Tala walks through the open gate.",
        ]
        coherence_prompts = []

        def llm_request(messages, **kwargs):
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            if purpose == "beat_finite_endpoint_extract":
                return {"status": "COMPLETE"}
            if purpose == "beat_coherence_validation":
                coherence_prompts.append(messages[-1]["content"])
            return {"valid": True, "issue": ""}

        with tempfile.TemporaryDirectory() as directory:
            minimax._run_forward_beat_validation(
                lambda: beats,
                "Tala opens the gate and walks through it.",
                2,
                {"phases": []},
                str(Path(directory) / "beats.txt"),
                llm_request,
                state_path=str(Path(directory) / "state.json"),
            )

        self.assertEqual(len(coherence_prompts), 2)
        self.assertNotIn("\nPREVIOUS BEAT\n", coherence_prompts[0])
        self.assertIn(
            "PREVIOUS BEAT\nTala opens the gate.\n\nCANDIDATE BEAT\n"
            "Tala walks through the open gate.",
            coherence_prompts[1],
        )

    def test_coherence_validator_is_narrow_and_generic(self):
        messages = minimax.build_beat_coherence_validation_messages(
            {"characters": {"Tala": {"status": "alive"}}},
            "Tala defeats the statue.",
            "Tala hits the statue once and it turns into water.",
        )
        prompt = messages[1]["content"]
        self.assertIn("WITHIN-BEAT PHYSICAL/CAUSAL COHERENCE ONLY", prompt)
        self.assertIn("restoration, regeneration, or reinstallation", prompt)
        self.assertIn("materially", prompt)
        self.assertIn("Do not judge source coverage", prompt)
        self.assertIn("NEXT JOB ownership", prompt)
        self.assertNotIn("STATE EFFECTS IF VALID", prompt)

    def test_validator_contract_is_immutable_and_minimal(self):
        messages = minimax.build_beat_validation_messages(
            "",
            minimax.new_beat_canonical_state(),
            "Operator opens the primary barrier.",
            None,
            "Operator opens the primary barrier.",
        )
        self.assertIn("CURRENT STATE", messages[1]["content"])
        self.assertIn('valid": true', messages[1]["content"])
        self.assertNotIn("state_patch", messages[1]["content"])
        self.assertNotIn("STORY", messages[1]["content"])
        self.assertNotIn("PHASE GOAL", messages[1]["content"])
        self.assertIn("CURRENT JOB", messages[1]["content"])
        self.assertIn("RESERVED FOR LATER", messages[1]["content"])
        self.assertIn("STATE EFFECTS IF VALID", messages[1]["content"])
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("CURRENT JOB is the only required work", prompt)
        self.assertIn("Finite tasks must visibly finish", prompt)
        self.assertIn('wording like "is cooking"', prompt)
        self.assertIn("ongoing/repeated jobs need only a non-terminal instance", prompt)
        self.assertIn("RESERVED FOR LATER is never required now", prompt)
        self.assertIn("new persistent changes require a matching assigned effect", prompt)
        self.assertIn("Do not require effects for new incidental entities", prompt)
        self.assertIn("Work made FOR someone needs no delivery unless required", prompt)
        self.assertLess(len(" ".join(m["content"] for m in messages).split()), 500)

    def test_validator_rejects_completed_state_grammar_for_assigned_action(self):
        messages = minimax.build_beat_validation_messages(
            "Amy kills a zombie.",
            minimax.new_beat_canonical_state(),
            "Amy kills the last zombie and opens the basement.",
            None,
            "With the last zombie slain, Amy opens the basement.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Show every assigned action and result in THIS beat", prompt)
        self.assertIn(
            'PREVIOUS FINAL BEAT or aftermath ("having finished X") cannot '
            'substitute for performing an assigned action now', prompt,
        )
        self.assertIn("repeating an irreversible action without restoration", prompt)


    def test_validator_prompt_rejects_materially_incoherent_staging(self):
        messages = minimax.build_beat_validation_messages(
            "Amy is holding a pistol and katana.",
            minimax.new_beat_canonical_state(),
            "Amy kills the last zombie, leaving the house soaked in blood.",
            "Amy lets the kids out of the basement.",
            "Amy slashes the final zombie's neck with her pistol.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Allow harmless staging", prompt)
        self.assertIn(
            "Tools must suit their actions unless an unusual capability is established",
            prompt,
        )
        self.assertIn("protected/non-hostile participant", prompt)

    def test_compact_validator_state_removes_noise_but_preserves_facts(self):
        state = {
            "version": 1,
            "characters": {
                "Amy": {
                    "location": "home",
                    "held_objects": ["katana"],
                    "equipped_objects": ["pistol"],
                    "injuries": [],
                    "posture": "N/A",
                    "orientation": "N/A",
                    "custom_fact": False,
                    "clothing": {
                        "upper": {"item": "black tank top", "damage": "none"},
                        "lower": {"item": "denim jeans", "damage": "none"},
                    },
                }
            },
            "environment": {
                "doors": {},
                "barriers": {"front": {"status": "locked"}},
            },
            "story_progress": {
                "completed_required_event_ids": ["E1"],
                "pending_required_event_ids": [],
                "persistent_state_effects": {
                    "environment.barriers.front.status": "locked",
                },
            },
        }
        original = json.loads(json.dumps(state))
        compacted = minimax.compact_beat_validation_state(state)

        self.assertEqual(state, original)
        self.assertNotIn("version", compacted)
        self.assertNotIn("injuries", compacted["characters"]["Amy"])
        self.assertNotIn("posture", compacted["characters"]["Amy"])
        self.assertFalse(compacted["characters"]["Amy"]["custom_fact"])
        self.assertEqual(
            compacted["environment"]["barriers"]["front"],
            {"status": "locked"},
        )
        self.assertNotIn("story_progress", compacted)

    def test_validator_prompt_includes_assigned_state_effects(self):
        messages = minimax.build_beat_validation_messages(
            "",
            minimax.new_beat_canonical_state(),
            "Operator opens the primary barrier.",
            None,
            "Operator opens the primary barrier.",
            assigned_state_effects=[
                {
                    "id": "E1",
                    "state_effects": [
                        {"op": "set_barrier_state", "entity": "primary", "value": "open"},
                        {"op": "set_location", "entity": "Operator", "value": "hall"},
                    ],
                }
            ],
        )
        prompt = messages[1]["content"]
        compact_prompt = " ".join(prompt.split())
        self.assertIn("STATE EFFECTS IF VALID", prompt)
        self.assertIn('"id":"E1"', prompt)
        self.assertIn('"value":"hall"', prompt)
        self.assertNotIn('"set_barrier_state"', prompt)
        self.assertIn(
            "Every listed effect must match the candidate's FINAL state after all actions",
            compact_prompt,
        )
        self.assertIn(
            "Do not require effects for new incidental entities",
            compact_prompt,
        )

    def test_invalid_candidate_regenerates_same_beat_without_state_mutation(self):
        validation_states = []
        candidates = []
        responses = iter([
            {"valid": False, "issue": "The candidate does not perform the current action."},
            {"valid": True, "issue": ""},
        ])

        def validator(messages, **kwargs):
            content = messages[1]["content"]
            if "Classify only the finite-activity endpoint" in content:
                return {"status": "COMPLETE"}
            if "WITHIN-BEAT PHYSICAL/CAUSAL COHERENCE ONLY" in content:
                return {"valid": True, "issue": ""}
            marker = "CURRENT STATE\n"
            state_text = content.split(marker, 1)[1].split("\n\nCURRENT JOB", 1)[0]
            validation_states.append(json.loads(state_text))
            return next(responses)

        repairs = []

        def repair(**kwargs):
            candidates.append(kwargs["beat_number"])
            repairs.append(kwargs)
            return "Operator opens the primary barrier."

        with tempfile.TemporaryDirectory() as directory:
            result = minimax._run_forward_beat_validation(
                lambda: ["Operator approaches the primary barrier."],
                "The operator opens the primary barrier.",
                1,
                ARC,
                str(Path(directory) / "beats.txt"),
                validator,
                state_path=str(Path(directory) / "state.json"),
                candidate_factory=repair,
            )

        self.assertEqual(result, ["Operator opens the primary barrier."])
        self.assertEqual(candidates, [1])
        self.assertEqual(
            repairs[0]["rejected_candidate"],
            "Operator approaches the primary barrier.",
        )
        self.assertIn(
            "does not perform the current action",
            repairs[0]["correction"],
        )
        self.assertEqual(validation_states[0], validation_states[1])

    def test_location_effect_seeds_threat_from_arc_typed_role(self):
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 2,
                "required_events": [
                    {
                        "id": "E1",
                        "event": "A zombie breaks into the house.",
                        "beat_number": 1,
                        "state_effects": [
                            {"op": "set_location", "entity": "zombie", "value": "house"},
                        ],
                    },
                    {
                        "id": "E2",
                        "event": "Amy kills the zombies.",
                        "beat_number": 2,
                        "state_effects": [
                            {"op": "set_threat_state", "entity": "zombies", "value": "dead"},
                        ],
                    },
                ],
            }],
        }
        state = minimax._preflight_required_event_state_effects(arc)

        self.assertEqual(state["threats"]["zombie"]["location"], "house")
        self.assertEqual(state["threats"]["zombies"]["status"], "dead")

    def test_unresolvable_location_effect_raises_deterministic_state_error(self):
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 1,
                "required_events": [{
                    "id": "E1",
                    "event": "The parcel moves to the hall.",
                    "beat_number": 1,
                    "state_effects": [
                        {"op": "set_location", "entity": "parcel", "value": "hall"},
                    ],
                }],
            }],
        }

        with self.assertRaisesRegex(
            minimax.RequiredEventStateApplicationError,
            "untracked entity: 'parcel'",
        ):
            minimax._preflight_required_event_state_effects(arc)

    def test_state_preflight_failure_preserves_saved_arc_and_does_not_start_beats(self):
        arc = {
            "planner": {"type": "source_span"},
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 1,
                "required_events": [{
                    "id": "E1",
                    "event": "The parcel moves to the hall.",
                    "beat_number": 1,
                    "state_effects": [
                        {"op": "set_location", "entity": "parcel", "value": "hall"},
                    ],
                }],
            }],
        }
        plan = SimpleNamespace(
            chapters=[SimpleNamespace(chapter=1, beat_count=1)]
        )

        def unexpected_llm(*args, **kwargs):
            self.fail("Beat generation/validation must not start after state preflight fails.")

        with tempfile.TemporaryDirectory() as directory:
            arc_path = Path(directory) / "arc.json"
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "state.json"
            with patch.object(
                minimax,
                "build_source_span_macro_arc_from_story",
                return_value=(plan, arc),
            ):
                with self.assertRaises(minimax.RequiredEventStateApplicationError):
                    minimax.generate_beats_from_story(
                        "The parcel moves to the hall.",
                        1,
                        path=str(beats_path),
                        story_arc_path=str(arc_path),
                        validation_state_path=str(state_path),
                        llm_request=unexpected_llm,
                        reuse_story_arc=False,
                    )

            self.assertTrue(arc_path.exists())
            self.assertTrue(Path(str(arc_path) + ".sha256").exists())
            self.assertFalse(state_path.exists())

    def test_valid_beat_commits_assigned_effects_after_validation(self):
        def validator(messages, **kwargs):
            content = messages[1]["content"]
            if "Classify only the finite-activity endpoint" in content:
                return {"status": "COMPLETE"}
            return {"valid": True, "issue": ""}

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            result = minimax._run_forward_beat_validation(
                lambda: ["Operator opens the primary barrier."],
                "The operator opens the primary barrier.",
                1,
                ARC,
                str(Path(directory) / "beats.txt"),
                validator,
                state_path=str(state_path),
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))

        self.assertEqual(result, ["Operator opens the primary barrier."])
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["barriers"]["primary"]["status"],
            "open",
        )
        self.assertEqual(checkpoint["completed_required_event_ids"], ["E1"])

    def test_invalid_required_event_shape_is_rejected_deterministically(self):
        invalid = json.loads(json.dumps(ARC))
        invalid["phases"][0]["required_events"][0]["state_effects"] = {
            "threats": {"entity_group": True}
        }
        with self.assertRaises(ValueError):
            minimax.parse_beat_arc_plan(invalid, 1)



    def test_planning_metadata_rejects_raw_json_delimiters(self):
        issues = minimax.validate_beat_planning_metadata(
            "Amy closes the basement door.{"
        )
        self.assertIn("final beat contains raw JSON delimiter", issues)

    def test_validator_checks_final_state_for_typed_effects(self):
        messages = minimax.build_beat_validation_messages(
            "None",
            {},
            "The engineer equips the scanner.",
            None,
            "The engineer picks up the scanner, then sets it on the bench.",
            assigned_state_effects=[
                {
                    "id": "E1",
                    "state_effects": [
                        {
                            "op": "set_item_state",
                            "entity": "scanner",
                            "owner": "Engineer",
                            "value": "equipped",
                        }
                    ],
                }
            ],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("candidate's FINAL state", prompt)
        self.assertIn("picked up then set down is", prompt)
        self.assertIn("not held at the end", prompt)
        self.assertIn("Possession is not equipping", prompt)


    def test_validator_requires_assigned_final_location_to_be_visible(self):
        messages = minimax.build_beat_validation_messages(
            "",
            minimax.new_beat_canonical_state(),
            "Amy moves the children to safety and returns to the kitchen.",
            None,
            "Amy moves the children into a closet and closes the door.",
            assigned_state_effects=[
                {
                    "id": "E2",
                    "state_effects": [
                        {"op": "set_location", "entity": "Amy", "value": "kitchen"},
                    ],
                }
            ],
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn(
            "For set_location(entity, place), that entity must visibly end at/in that place",
            prompt,
        )
        self.assertIn(
            "candidate must actually show that return before ending",
            prompt,
        )

    def test_accepted_beat_state_concretizes_abstract_location_and_ledger(self):
        state = minimax.new_beat_canonical_state()
        state["characters"]["Will"] = {"location": "safe location"}
        state["characters"]["Amber"] = {"location": "safe location"}
        state["story_progress"]["persistent_state_effects"] = {
            "characters.Will.location": "safe location",
            "characters.Amber.location": "safe location",
        }
        state = minimax.normalize_beat_canonical_state(state)

        updated = minimax.apply_accepted_beat_state_patch(
            state,
            {
                "characters": {
                    "Will": {"location": "back closet"},
                    "Amber": {"location": "back closet"},
                }
            },
        )

        self.assertEqual(updated["characters"]["Will"]["location"], "back closet")
        self.assertEqual(updated["characters"]["Amber"]["location"], "back closet")
        self.assertEqual(
            updated["story_progress"]["persistent_state_effects"][
                "characters.Will.location"
            ],
            "back closet",
        )
        self.assertEqual(
            updated["story_progress"]["persistent_state_effects"][
                "characters.Amber.location"
            ],
            "back closet",
        )

    def test_accepted_beat_state_keeps_broad_persistent_room_and_object_facts(self):
        state = minimax.new_beat_canonical_state()

        updated = minimax.apply_accepted_beat_state_patch(
            state,
            {
                "environment": {
                    "rooms": {
                        "back closet": {
                            "description": "small storage closet",
                        }
                    },
                    "objects": {
                        "blue vase": {
                            "location": "back closet",
                            "condition": "intact",
                        }
                    },
                }
            },
        )

        self.assertEqual(
            updated["environment"]["rooms"]["back closet"]["description"],
            "small storage closet",
        )
        self.assertEqual(
            updated["environment"]["objects"]["blue vase"]["location"],
            "back closet",
        )
        self.assertEqual(
            updated["story_progress"]["persistent_state_effects"][
                "environment.objects.blue vase.location"
            ],
            "back closet",
        )

    def test_accepted_beat_state_prompt_requests_broad_capture_without_story_progress(self):
        messages = minimax.build_accepted_beat_state_messages(
            minimax.new_beat_canonical_state(),
            "Amy puts Will and Amber in the back closet beside a blue vase.",
        )
        prompt = messages[-1]["content"]
        self.assertIn("Capture persistent world facts broadly", prompt)
        self.assertIn("blue vase", prompt)
        self.assertIn("Do not output story_progress", prompt)
        self.assertIn(
            "These four roots are siblings. Never nest characters, environment, threats, or story inside one another.",
            prompt,
        )
        self.assertIn(
            "Use threats only for hostile or dangerous entities.",
            prompt,
        )

    def test_accepted_beat_state_prompt_requires_distinct_threat_identity(self):
        state = minimax.new_beat_canonical_state()
        state["threats"]["threat_1"] = {
            "type": "raider",
            "status": "dead",
        }
        prompt = minimax.build_accepted_beat_state_messages(
            state,
            "Another raider enters the room.",
        )[-1]["content"]
        normalized = " ".join(prompt.split())
        self.assertIn("another", normalized)
        self.assertIn("new", normalized)
        self.assertIn("second", normalized)
        self.assertIn("third", normalized)
        self.assertIn("emit a separate threat entry", normalized)
        self.assertIn("Python will assign its stable canonical threat ID", normalized)

    def test_accepted_beat_state_normalizes_unambiguous_threat_status_shorthand(self):
        parsed = minimax.parse_accepted_beat_state_patch(
            {"state_patch": {"threats": {"zombies": "active"}}},
            state_before=minimax.new_beat_canonical_state(),
        )
        self.assertEqual(parsed["threats"]["zombies"], {"status": "active"})

        with self.assertRaisesRegex(ValueError, "threats.zombies must be an object"):
            minimax.parse_accepted_beat_state_patch(
                {"state_patch": {"threats": {"zombies": "in the hallway"}}},
                state_before=minimax.new_beat_canonical_state(),
            )

    def test_accepted_beat_state_schema_requires_object_roots(self):
        schema = (
            minimax.build_accepted_beat_state_response_format()
            ["json_schema"]["schema"]["properties"]["state_patch"]
        )
        self.assertFalse(schema["additionalProperties"])
        for root in ("characters", "environment", "threats", "story"):
            self.assertEqual(schema["properties"][root]["type"], "object")
        self.assertEqual(
            schema["properties"]["threats"]["additionalProperties"]["type"],
            "object",
        )
        self.assertIn(
            "story$",
            schema["properties"]["threats"]["propertyNames"]["pattern"],
        )

    def test_validator_preserves_group_beneficiary_roles(self):
        messages = minimax.build_beat_validation_messages(
            "",
            minimax.new_beat_canonical_state(),
            "The parent cooks breakfast for the children.",
            None,
            "The parent finishes breakfast while the children only watch.",
        )
        prompt = messages[1]["content"]
        self.assertIn("every required participant", prompt)
        self.assertIn("beneficiary", prompt)
        normalized = " ".join(prompt.split())
        self.assertIn("labeling or leaving them elsewhere is insufficient", normalized)
        self.assertIn("watching or listening can satisfy a performance/lesson role", normalized)


    def test_beat_generation_uses_compact_creative_prompt(self):
        phase = {
            "required_events": [
                {
                    "id": "E1",
                    "beat_number": 1,
                    "event": "The parent cooks breakfast for the children.",
                }
            ]
        }
        messages = minimax.build_beat_generation_messages(
            "The parent cooks breakfast for the children.",
            1,
            batch_start=1,
            batch_end=1,
            current_phase=phase,
        )
        prompt = messages[1]["content"]
        normalized = " ".join(prompt.split())
        self.assertIn("SOURCE FILM", prompt)
        self.assertIn("ASSIGNED EVENTS 1-1", prompt)
        self.assertIn("Be creative where needed", normalized)
        self.assertIn("Keep spatial awareness at all times", normalized)
        self.assertIn("Avoid pronouns, use names", normalized)
        self.assertNotIn("BARRIER NAME RULES", prompt)
        self.assertNotIn("show that person receive or use it", normalized)
