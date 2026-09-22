import json
import tempfile
import unittest
from pathlib import Path

import minimax


class BeatAtATimeValidatorTests(unittest.TestCase):
    def test_validator_treats_named_beneficiaries_as_material(self):
        messages = minimax.build_beat_validation_messages(
            previous_final_beat="None",
            current_state=minimax.new_beat_canonical_state(),
            beat_job="Amy cooks breakfast for Will and Amber.",
            next_beat_job="A zombie breaks the window.",
            candidate_beat="Amy cooks breakfast.",
        )
        prompt = " ".join(messages[1]["content"].split())
        self.assertIn("Named relational participants are material", prompt)
        self.assertIn(
            "Reject a solo rewrite that drops named beneficiaries or participants",
            prompt,
        )

    def _run(
        self,
        framework,
        responses,
        candidate_factory=None,
        macro_arc=None,
        validator=None,
    ):
        calls = []

        def llm_request(messages, **kwargs):
            calls.append((messages, kwargs))
            response = (
                validator(messages, **kwargs)
                if validator is not None
                else responses.pop(0)
            )
            return response

        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            result = minimax._run_forward_beat_validation(
                lambda: list(framework),
                "A source story.",
                len(framework),
                macro_arc or {"phases": []},
                str(beats_path),
                llm_request,
                state_path=str(state_path),
                candidate_factory=candidate_factory,
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))
        return result, checkpoint, calls

    @staticmethod
    def _prompt_section(messages, heading, next_heading):
        prompt = messages[1]["content"]
        return prompt.split(heading, 1)[1].split(next_heading, 1)[0].strip()

    @staticmethod
    def _required_event_arc(event_count=4, state_effects=None):
        events = []
        for number in range(1, event_count + 1):
            event = {
                "id": f"E{number}",
                "beat_number": number,
                "event": f"Amy completes required action {number}.",
            }
            if state_effects and number in state_effects:
                event["state_effects"] = state_effects[number]
            events.append(event)
        return {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": event_count,
                "narrative_purpose": "Advance the story.",
                "characters_introduced": ["Amy"],
                "location": "the house",
                "required_events": events,
            }],
        }

    @staticmethod
    def _canonical_state_regression_arc():
        return {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 4,
                "narrative_purpose": "Resolve the basement threat.",
                "broad_progression": "Contain the survivor, secure the barrier, equip the weapon, and end the threat.",
                "characters_introduced": ["Will", "Amy"],
                "location": "the basement",
                "required_end_state": "Will is contained, the basement door is locked, Amy has the pistol equipped, and the final threat is destroyed.",
                "required_events": [
                    {
                        "id": "E1",
                        "beat_number": 1,
                        "event": "Will enters and is contained in the basement.",
                        "state_effects": [
                            {"op": "set_location", "entity": "Will", "value": "basement"},
                            {"op": "set_containment", "entity": "Will", "container": "basement", "value": "contained"},
                        ],
                    },
                    {
                        "id": "E2",
                        "beat_number": 2,
                        "event": "Amy locks the basement door.",
                        "state_effects": [
                            {"op": "set_barrier_state", "entity": "basement_door", "value": "locked"},
                        ],
                    },
                    {
                        "id": "E3",
                        "beat_number": 3,
                        "event": "Amy equips the pistol.",
                        "state_effects": [
                            {"op": "set_item_state", "entity": "pistol", "owner": "Amy", "value": "equipped"},
                        ],
                    },
                    {
                        "id": "E4",
                        "beat_number": 4,
                        "event": "Amy destroys the final threat.",
                        "state_effects": [
                            {"op": "set_location", "entity": "threat_1", "value": "basement"},
                            {"op": "set_threat_state", "entity": "threat_1", "value": "dead"},
                        ],
                    },
                ],
            }],
        }

    def test_required_events_map_each_beat_to_its_event_job_and_next_job(self):
        macro_arc = self._required_event_arc()
        framework = [
            f"Amy completes required action {number}."
            for number in range(1, 5)
        ]
        result, checkpoint, calls = self._run(
            framework,
            [{"valid": True, "issue": ""} for _ in framework],
            macro_arc=macro_arc,
        )

        self.assertEqual(result, framework)
        self.assertEqual(checkpoint["completed_required_event_ids"], ["E1", "E2", "E3", "E4"])
        self.assertEqual(checkpoint["pending_required_event_ids"], [])
        self.assertEqual(
            [
                self._prompt_section(
                    call[0], "CURRENT JOB\n", "\n\nNEXT JOB"
                )
                for call in calls
            ],
            [f"Amy completes required action {number}." for number in range(1, 5)],
        )
        self.assertEqual(
            [
                self._prompt_section(
                    call[0], "NEXT JOB\n", "\n\nSTATE EFFECTS IF VALID"
                )
                for call in calls
            ],
            [
                "Amy completes required action 2.",
                "Amy completes required action 3.",
                "Amy completes required action 4.",
                "None; this is the final beat.",
            ],
        )

    def test_repeated_process_does_not_invent_distinct_next_job(self):
        calls = []

        def validator(messages, **kwargs):
            calls.append(messages)
            return {"valid": True, "issue": ""}

        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            minimax._run_forward_beat_validation(
                lambda: [
                    "Amy continues the authorized process at station one.",
                    "Amy continues the authorized process at station two.",
                ],
                "A source story.",
                2,
                {"phases": [{
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "narrative_purpose": "Continue the process.",
                    "broad_progression": "Continue the process.",
                    "characters_introduced": ["Amy"],
                    "location": "the house",
                    "required_end_state": "The process continues.",
                    "required_events": [
                        {
                            "id": "E1",
                            "beat_number": 1,
                            "event": "Amy continues the authorized process.",
                        },
                        {
                            "id": "E2",
                            "beat_number": 2,
                            "event": "Amy continues the authorized process.",
                        },
                    ],
                }]},
                str(beats_path),
                validator,
                state_path=str(state_path),
            )

        next_job = self._prompt_section(
            calls[0],
            "NEXT JOB\n",
            "\n\nSTATE EFFECTS IF VALID",
        )
        self.assertEqual(next_job, "Amy continues the authorized process.")

    def test_accepted_required_event_is_committed_at_phase_boundary(self):
        macro_arc = self._required_event_arc(event_count=1, state_effects={
            1: [{"op": "set_barrier_state", "entity": "basement", "value": "open"}],
        })
        result, checkpoint, _ = self._run(
            ["Amy completes required action 1."],
            [{"valid": True, "issue": ""}],
            macro_arc=macro_arc,
        )

        self.assertEqual(result, ["Amy completes required action 1."])
        self.assertEqual(checkpoint["finalized_through"], 1)
        self.assertEqual(checkpoint["completed_required_event_ids"], ["E1"])
        self.assertEqual(checkpoint["pending_required_event_ids"], [])
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["barriers"]["basement"]["status"],
            "open",
        )

    def test_valid_commits_all_assigned_events_without_second_semantic_check(self):
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 1,
                "narrative_purpose": "Advance the story.",
                "broad_progression": "Amy survives the encounter.",
                "characters_introduced": ["Amy"],
                "location": "the street",
                "required_end_state": "Amy remains outside.",
                "required_events": [
                    {
                        "id": "E7",
                        "beat_number": 1,
                        "event": "Amy keeps fighting and kills additional zombies.",
                        "state_effects": [
                            {"op": "set_condition", "entity": "horde", "value": "reduced"},
                        ],
                    },
                    {
                        "id": "E8",
                        "beat_number": 1,
                        "event": "Amy reaches the safe room.",
                    },
                ],
            }],
        }
        result, checkpoint, _ = self._run(
            ["A quiet shot shows Amy looking at the rain."],
            [{"valid": True, "issue": ""}],
            macro_arc=macro_arc,
        )

        self.assertEqual(result, ["A quiet shot shows Amy looking at the rain."])
        self.assertEqual(checkpoint["completed_required_event_ids"], ["E7", "E8"])
        self.assertEqual(checkpoint["pending_required_event_ids"], [])
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["objects"]["horde"]["condition"],
            "reduced",
        )

    def test_rejected_candidate_does_not_change_completed_pending_state_or_history(self):
        macro_arc = self._required_event_arc(event_count=2, state_effects={
            1: [{"op": "set_condition", "entity": "first_action", "value": "done"}],
            2: [{"op": "set_condition", "entity": "second_action", "value": "done"}],
        })
        snapshots = []

        def validator(messages, **kwargs):
            prompt = messages[1]["content"]
            state = json.loads(
                self._prompt_section(
                    messages,
                    "CURRENT STATE\n",
                    "\n\nCURRENT JOB",
                )
            )
            previous = self._prompt_section(
                messages, "PREVIOUS FINAL BEAT\n", "\n\nCURRENT STATE"
            )
            snapshots.append({
                "beat": kwargs["history_metadata"]["beat_number"],
                "state": state,
                "previous": previous,
                "prompt": prompt,
            })
            if len(snapshots) == 2:
                return {"valid": False, "issue": "Reject this candidate."}
            return {"valid": True, "issue": ""}

        def candidate_factory(**kwargs):
            return "Amy completes required action 2."

        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            result = minimax._run_forward_beat_validation(
                lambda: [
                    "Amy completes required action 1.",
                    "Rejected candidate for action 2.",
                ],
                "A source story.",
                2,
                macro_arc,
                str(beats_path),
                validator,
                state_path=str(state_path),
                candidate_factory=candidate_factory,
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))

        self.assertEqual(
            result,
            [
                "Amy completes required action 1.",
                "Amy completes required action 2.",
            ],
        )
        self.assertEqual(len(snapshots), 3)
        first_beat_state = snapshots[0]["state"]
        rejected_state = snapshots[1]["state"]
        accepted_retry_state = snapshots[2]["state"]
        self.assertEqual(rejected_state, accepted_retry_state)
        self.assertNotIn("completed_required_event_ids", rejected_state.get("story_progress", {}))
        self.assertNotIn("pending_required_event_ids", rejected_state.get("story_progress", {}))
        self.assertEqual(snapshots[1]["previous"], snapshots[2]["previous"])
        self.assertEqual(snapshots[1]["previous"], "Amy completes required action 1.")
        self.assertNotIn("Rejected candidate", checkpoint["finalized_beats"][1]["beat_text"])
        self.assertEqual(checkpoint["completed_required_event_ids"], ["E1", "E2"])
        self.assertEqual(checkpoint["pending_required_event_ids"], [])
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["objects"]["first_action"]["condition"],
            "done",
        )
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["objects"]["second_action"]["condition"],
            "done",
        )
        self.assertNotEqual(first_beat_state, rejected_state)

    def test_nested_required_event_state_effect_persists_into_next_beat(self):
        macro_arc = self._required_event_arc(event_count=2, state_effects={
            1: [{"op": "set_barrier_state", "entity": "basement", "value": "open"}],
        })
        states = []

        def validator(messages, **kwargs):
            states.append(json.loads(
                self._prompt_section(
                    messages,
                    "CURRENT STATE\n",
                    "\n\nCURRENT JOB",
                )
            ))
            return {"valid": True, "issue": ""}

        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            result = minimax._run_forward_beat_validation(
                lambda: [
                    "Amy completes required action 1.",
                    "Amy completes required action 2.",
                ],
                "A source story.",
                2,
                macro_arc,
                str(beats_path),
                validator,
                state_path=str(state_path),
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))

        self.assertEqual(len(states), 2)
        self.assertEqual(
            states[1]["environment"]["barriers"]["basement"],
            {"status": "open"},
        )
        self.assertEqual(
            checkpoint["current_beat_state"]["story_progress"]["persistent_state_effects"],
            {"environment.barriers.basement.status": "open"},
        )

    def test_four_event_arc_carries_canonical_facts_into_each_next_snapshot(self):
        macro_arc = self._canonical_state_regression_arc()
        framework = [
            "Will enters and is contained in the basement.",
            "Amy locks the basement door.",
            "Amy equips the pistol.",
            "Amy destroys the final threat.",
        ]
        validator_states = []

        def validator(messages, **kwargs):
            validator_states.append(json.loads(
                self._prompt_section(
                    messages,
                    "CURRENT STATE\n",
                    "\n\nCURRENT JOB",
                )
            ))
            return {"valid": True, "issue": ""}

        result, checkpoint, _ = self._run(
            framework,
            [],
            macro_arc=macro_arc,
            validator=validator,
        )

        self.assertEqual(result, framework)
        self.assertEqual(len(validator_states), 4)

        self.assertNotIn("location", validator_states[0]["characters"]["Will"])
        self.assertEqual(
            validator_states[1]["characters"]["Will"]["location"],
            "basement",
        )
        self.assertEqual(
            validator_states[1]["characters"]["Will"]["containment"],
            "contained",
        )
        self.assertEqual(
            validator_states[1]["characters"]["Will"]["contained_in"],
            "basement",
        )
        self.assertFalse(validator_states[1]["characters"]["Will"]["accessible"])

        self.assertEqual(
            validator_states[2]["environment"]["barriers"]["basement_door"]["status"],
            "locked",
        )
        self.assertEqual(
            validator_states[2]["characters"]["Will"]["contained_in"],
            "basement",
        )

        self.assertEqual(
            validator_states[3]["characters"]["Amy"]["equipped_objects"],
            ["pistol"],
        )
        self.assertEqual(
            validator_states[3]["environment"]["barriers"]["basement_door"]["status"],
            "locked",
        )

        final_state = checkpoint["current_beat_state"]
        self.assertEqual(final_state["threats"]["threat_1"]["status"], "dead")
        self.assertEqual(
            final_state["story_progress"]["completed_required_event_ids"],
            ["E1", "E2", "E3", "E4"],
        )

        changed = minimax.apply_state_patch(
            final_state,
            {
                "environment": {
                    "paths": {"stairwell": {"status": "clear"}},
                },
                "story": {"persistent_facts": {"unrelated_note": "preserved"}},
            },
        )
        self.assertEqual(
            changed["characters"]["Will"]["contained_in"], "basement"
        )
        self.assertFalse(changed["characters"]["Will"]["accessible"])
        self.assertEqual(
            changed["environment"]["barriers"]["basement_door"]["status"],
            "locked",
        )
        self.assertEqual(changed["characters"]["Amy"]["equipped_objects"], ["pistol"])
        self.assertEqual(changed["threats"]["threat_1"]["status"], "dead")
        self.assertEqual(
            changed["environment"]["paths"]["stairwell"]["status"], "clear"
        )
        self.assertEqual(
            changed["story"]["persistent_facts"]["unrelated_note"], "preserved"
        )

    def test_rejected_candidate_regenerates_same_beat(self):
        generated = []

        def candidate_factory(**kwargs):
            generated.append(kwargs)
            return "Replacement beat 1."

        result, checkpoint, calls = self._run(
            ["Initial beat 1.", "Beat 2."],
            [
                {"valid": False, "issue": "Use the assigned action."},
                {"valid": True, "issue": ""},
                {"valid": True, "issue": ""},
            ],
            candidate_factory=candidate_factory,
        )

        self.assertEqual(result, ["Replacement beat 1.", "Beat 2."])
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["beat_number"], 1)
        self.assertIn("Use the assigned action.", generated[0]["correction"])
        self.assertEqual(
            [call[1]["history_metadata"]["beat_number"] for call in calls],
            [1, 1, 2],
        )
        self.assertEqual(checkpoint["finalized_through"], 2)

    def test_revised_beat_becomes_previous_final_beat_for_next_validation(self):
        previous_beats = []

        def validator(messages, **kwargs):
            previous_beats.append(
                self._prompt_section(messages, "PREVIOUS FINAL BEAT\n", "\n\nCURRENT STATE")
            )
            if len(previous_beats) == 1:
                return {"valid": False, "issue": "Revise Beat 1."}
            return {"valid": True, "issue": ""}

        def candidate_factory(**kwargs):
            return "Revised accepted Beat 1."

        self._run(
            ["Original Beat 1.", "Beat 2."],
            [],
            candidate_factory=candidate_factory,
            validator=validator,
        )

        self.assertEqual(previous_beats[0], "None; this is the first beat.")
        self.assertEqual(previous_beats[-1], "Revised accepted Beat 1.")

    def test_rejected_candidate_does_not_contaminate_state(self):
        macro_arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 1,
                "narrative_purpose": "Open the door.",
                "characters_introduced": ["Amy"],
                "location": "the house",
                "required_events": [{
                    "id": "E1",
                    "beat_number": 1,
                    "event": "Amy opens the basement door.",
                    "state_effects": [
                        {"op": "set_barrier_state", "entity": "basement_door", "value": "open"},
                    ],
                }],
            }],
        }
        validator_states = []

        def candidate_factory(**kwargs):
            return "Amy opens the basement door."

        def validator(messages, **kwargs):
            state_start = messages[1]["content"].split(
                "CURRENT STATE\n", 1
            )[1].split("\n\nCURRENT JOB", 1)[0]
            validator_states.append(json.loads(state_start))
            return (
                {"valid": False, "issue": "Revise the door action."}
                if len(validator_states) == 1
                else {"valid": True, "issue": ""}
            )

        with tempfile.TemporaryDirectory() as directory:
            beats_path = Path(directory) / "beats.txt"
            state_path = Path(directory) / "beat_validation_state.json"
            result = minimax._run_forward_beat_validation(
                lambda: ["Amy opens the basement door."],
                "A source story.",
                1,
                macro_arc,
                str(beats_path),
                validator,
                state_path=str(state_path),
                candidate_factory=candidate_factory,
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))

        self.assertEqual(result, ["Amy opens the basement door."])
        self.assertEqual(len(validator_states), 2)
        self.assertEqual(validator_states[0], validator_states[1])
        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["barriers"][
                "basement_door"
            ]["status"],
            "open",
        )

    def test_malformed_validator_response_is_not_repaired(self):
        with self.assertRaises(ValueError):
            minimax.parse_beat_validation_result(
                '{"valid": true, "issue": "",}'
            )

        with self.assertRaises(ValueError):
            minimax.parse_beat_validation_result(
                '{"valid": true, "issue": "", "extra": "field"}'
            )

    def test_phase_retry_prefix_truncation_discards_failed_and_later_phases(self):
        macro_arc = {
            "phases": [
                {
                    "phase_number": 1,
                    "beat_start": 1,
                    "beat_end": 2,
                    "required_events": [],
                },
                {
                    "phase_number": 2,
                    "beat_start": 3,
                    "beat_end": 4,
                    "required_events": [],
                },
                {
                    "phase_number": 3,
                    "beat_start": 5,
                    "beat_end": 6,
                    "required_events": [],
                },
            ],
        }
        state_one = minimax.new_beat_canonical_state()
        state_one["story_progress"]["completed_required_event_ids"] = ["E1"]
        state_two = minimax.new_beat_canonical_state()
        state_two["story_progress"]["completed_required_event_ids"] = ["E1", "E2"]
        checkpoint = {
            "version": minimax.BEAT_VALIDATION_STATE_VERSION,
            "framework_beats": [f"Old beat {number}." for number in range(1, 7)],
            "finalized_beats": [
                {"beat_number": number, "beat_text": f"Old beat {number}."}
                for number in range(1, 5)
            ],
            "beat_state_after": {"1": state_one, "2": state_two},
            "current_beat_state": state_two,
            "completed_required_event_ids": ["E1", "E2"],
            "pending_required_event_ids": [],
            "finalized_through": 4,
        }

        result = minimax._truncate_beat_validation_checkpoint_to_phase_prefix(
            checkpoint,
            2,
            [f"New beat {number}." for number in range(1, 7)],
            macro_arc,
        )

        self.assertEqual(result["finalized_through"], 2)
        self.assertEqual(
            [record["beat_text"] for record in result["finalized_beats"]],
            ["Old beat 1.", "Old beat 2."],
        )
        self.assertEqual(set(result["beat_state_after"]), {"1", "2"})
        self.assertEqual(
            result["framework_beats"],
            [f"New beat {number}." for number in range(1, 7)],
        )


if __name__ == "__main__":
    unittest.main()
