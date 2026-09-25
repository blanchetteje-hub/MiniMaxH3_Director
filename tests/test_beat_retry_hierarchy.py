import tempfile
import unittest
from pathlib import Path

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
        validation_count = 0

        def llm(messages, **kwargs):
            nonlocal validation_count
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
            if purpose == "beat_validation":
                validation_count += 1
                if validation_count == 1:
                    return {"valid": False, "issue": "Regenerate the current beat."}
                return {"valid": True, "issue": ""}
            raise AssertionError(purpose)

        with tempfile.TemporaryDirectory() as directory:
            result = minimax.generate_beats_from_story(
                "The operator completes action X.", 1,
                path=str(Path(directory) / "beats.txt"),
                story_arc_path=str(Path(directory) / "arc.json"),
                validation_state_path=str(Path(directory) / "state.json"),
                llm_request=llm,
                reuse_story_arc=False,
            )

        self.assertEqual(result, ["Operator completes action X."])
        self.assertNotIn("macro_arc_create", purposes)
        self.assertNotIn("macro_arc_validate", purposes)
        self.assertEqual(purposes.count("beat_validation"), 2)
        self.assertNotIn("macro_state_preparation", purposes)
        self.assertNotIn("macro_state_semantic_validation", purposes)


if __name__ == "__main__":
    unittest.main()
