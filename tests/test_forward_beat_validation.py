import json
import tempfile
import unittest
from pathlib import Path

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
        "state_effects": {"environment": {"barriers": {
            "primary": {"status": "open"}
        }}},
    }],
}]}


class ForwardBeatValidationTests(unittest.TestCase):
    def test_validator_contract_is_immutable_and_minimal(self):
        messages = minimax.build_beat_validation_messages(
            "The operator opens the primary barrier.",
            "Complete the authorized action.",
            "",
            minimax.new_beat_canonical_state(),
            "Operator opens the primary barrier.",
            None,
            "Operator opens the primary barrier.",
        )
        self.assertIn("CURRENT STATE", messages[1]["content"])
        self.assertIn('valid": true', messages[1]["content"])
        self.assertNotIn("state_patch", messages[1]["content"])

    def test_invalid_candidate_regenerates_same_beat_without_state_mutation(self):
        validation_states = []
        candidates = []
        responses = iter([
            {"valid": False, "issue": "The candidate does not perform the current action."},
            {"valid": True, "issue": ""},
        ])

        def validator(messages, **kwargs):
            content = messages[1]["content"]
            marker = "CURRENT STATE — authoritative snapshot before this beat\n"
            state_text = content.split(marker, 1)[1].split("\n\nCURRENT BEAT JOB", 1)[0]
            validation_states.append(json.loads(state_text))
            return next(responses)

        def repair(**kwargs):
            candidates.append(kwargs["beat_number"])
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
        self.assertEqual(validation_states[0], validation_states[1])

    def test_valid_beat_commits_assigned_effects_after_validation(self):
        def validator(messages, **kwargs):
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


if __name__ == "__main__":
    unittest.main()
