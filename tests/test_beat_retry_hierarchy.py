import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import minimax


ARC = {"phases": [{
    "phase_number": 1,
    "beat_start": 1,
    "beat_end": 1,
    "narrative_purpose": "Complete the action.",
    "broad_progression": "The operator completes the action.",
    "characters_introduced": [],
    "location": "Location X",
    "required_end_state": "Action X is complete.",
    "required_events": [{
        "id": "E1", "event": "Operator completes action X.", "beat_number": 1
    }],
}]}


class BeatRetryHierarchyTests(unittest.TestCase):
    def test_failed_beat_is_repaired_before_commit(self):
        purposes = []
        story_validation_count = 0
        state_validation_count = 0

        def llm(messages, **kwargs):
            nonlocal story_validation_count, state_validation_count
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            purposes.append(purpose)
            if purpose == "source_unit_split_gate":
                return {"decision": "KEEP_TOGETHER", "reason": "single finite action"}
            if purpose == "source_unit_terminal":
                return {"decision": "YES", "reason": "the source action completes"}
            if purpose == "source_unit_hard_reset":
                return {"decision": "NO", "reason": "single continuous source unit"}
            if purpose == "source_unit_visible_responsibility":
                return {"decision": "YES", "reason": "visible action"}
            if purpose == "source_unit_local_relation":
                return {"relation": "NEW_TASK"}
            if purpose == "source_unit_state_effects":
                return {"state_effects": []}
            if purpose == "beat_generation":
                return {"beats": ["Operator completes action X."]}
            if purpose == "beat_repair":
                repair_prompt = messages[-1]["content"]
                self.assertIn("Make the smallest textual change", repair_prompt)
                self.assertIn("Preserve wording that is not part of the problem", repair_prompt)
                self.assertIn("do not reintroduce it", repair_prompt)
                self.assertIn("Story validator: Story fidelity issue.", repair_prompt)
                self.assertIn("State validator: Physical state issue.", repair_prompt)
                return {"beats": ["Operator completes action X."]}
            if purpose == "beat_story_validation":
                story_validation_count += 1
                if story_validation_count == 1:
                    return {"valid": False, "issue": "Story fidelity issue."}
                return {"valid": True, "issue": ""}
            if purpose == "beat_state_validation":
                state_validation_count += 1
                if state_validation_count == 1:
                    return {"valid": False, "issue": "Physical state issue."}
                return {"valid": True, "issue": ""}
            if purpose == "beat_finite_endpoint_extract":
                return {"status": "COMPLETE"}
            if purpose == "beat_coherence_validation":
                return {"valid": True, "issue": ""}
            raise AssertionError(purpose)

        with tempfile.TemporaryDirectory() as directory, patch("builtins.print") as printed:
            result = minimax.generate_beats_from_story(
                "The operator completes action X.", 1,
                path=str(Path(directory) / "beats.txt"),
                story_arc_path=str(Path(directory) / "arc.json"),
                validation_state_path=str(Path(directory) / "state.json"),
                llm_request=llm,
                reuse_story_arc=False,
            )

        self.assertEqual(result, ["Operator completes action X."])
        messages = [call.args[0] for call in printed.call_args_list if call.args]
        diagnostic_log = "\n".join(messages)
        self.assertIn("story validator attempt 1/10: INVALID; issue: Story fidelity issue.", diagnostic_log)
        self.assertIn("state validator attempt 1/10: INVALID; issue: Physical state issue.", diagnostic_log)
        self.assertEqual(
            messages.count("Beat 1 created: Operator completes action X."), 2
        )
        self.assertEqual(
            messages.count("Beat 1 accepted: Operator completes action X."), 1
        )
        self.assertNotIn("macro_arc_create", purposes)
        self.assertNotIn("macro_arc_validate", purposes)
        self.assertEqual(purposes.count("beat_generation"), 1)
        self.assertEqual(purposes.count("beat_repair"), 1)
        first_validation = min(
            purposes.index("beat_story_validation"),
            purposes.index("beat_state_validation"),
        )
        repair = purposes.index("beat_repair")
        second_validation = max(
            purposes.index("beat_story_validation", first_validation + 1),
            purposes.index("beat_state_validation", first_validation + 1),
        )
        self.assertLess(first_validation, repair)
        self.assertLess(repair, second_validation)
        self.assertEqual(purposes.count("beat_story_validation"), 2)
        self.assertEqual(purposes.count("beat_state_validation"), 2)
        self.assertNotIn("beat_validation", purposes)
        self.assertNotIn("macro_state_preparation", purposes)
        self.assertNotIn("macro_state_semantic_validation", purposes)


if __name__ == "__main__":
    unittest.main()
