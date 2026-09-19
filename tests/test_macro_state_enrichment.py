import tempfile
import unittest
from pathlib import Path

import minimax


def neutral_arc(event_text="Operator opens the primary barrier.", effects=None):
    event = {"id": "E1", "event": event_text, "beat_number": 1}
    if effects is not None:
        event["state_effects"] = effects
    return {"phases": [{
        "phase_number": 1,
        "beat_start": 1,
        "beat_end": 1,
        "narrative_purpose": "Resolve the authorized action.",
        "broad_progression": "The operator completes the required action.",
        "characters_introduced": ["Operator"],
        "location": "Location X",
        "required_end_state": "The primary barrier is open.",
        "required_events": [event],
    }]}


class MacroArcPipelineTests(unittest.TestCase):
    def test_arc_parser_rejects_invalid_canonical_entity_shape(self):
        arc = neutral_arc(effects={"threats": {"entity_group": True}})
        with self.assertRaises(ValueError):
            minimax.parse_beat_arc_plan(arc, 1)

    def test_arc_validator_prompt_owns_end_state_and_effect_semantics(self):
        prompt = "\\n".join(
            message["content"]
            for message in minimax.build_macro_arc_validation_messages(
                "The operator opens the primary barrier.", neutral_arc()
            )
        ).casefold()
        self.assertIn("required_end_state", prompt)
        self.assertIn("state_effects", prompt)
        self.assertIn("established by its own event", prompt)
        self.assertNotIn("state preparation", prompt)
        self.assertNotIn("coverage inventory", prompt)

    def test_repaired_arc_is_validated_before_beats_start(self):
        initial = neutral_arc("Operator approaches the primary barrier.")
        repaired = neutral_arc("Operator opens the primary barrier.")
        purposes = []

        def llm(messages, **kwargs):
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            purposes.append(purpose)
            if purpose == "macro_arc_create":
                return initial
            if purpose == "macro_arc_validate":
                if purposes.count("macro_arc_validate") == 1:
                    return {"valid": False, "issues": [
                        "The required end state is not established by the event."
                    ]}
                return {"valid": True, "issues": []}
            if purpose == "macro_arc_repair":
                return repaired
            if purpose == "beat_generation":
                return {"beats": ["Operator opens the primary barrier."]}
            if purpose == "beat_validation":
                return {"valid": True, "issue": ""}
            raise AssertionError(f"unexpected LLM purpose: {purpose}")

        with tempfile.TemporaryDirectory() as directory:
            result = minimax.generate_beats_from_story(
                "The operator opens the primary barrier.", 1,
                path=str(Path(directory) / "beats.txt"),
                story_arc_path=str(Path(directory) / "story_arc.json"),
                validation_state_path=str(Path(directory) / "state.json"),
                llm_request=llm,
                reuse_story_arc=False,
            )

        self.assertEqual(result, ["Operator opens the primary barrier."])
        self.assertEqual(
            purposes,
            [
                "macro_arc_create", "macro_arc_validate", "macro_arc_repair",
                "macro_arc_validate", "beat_generation", "beat_validation",
            ],
        )

    def test_arc_state_effects_are_applied_only_after_valid_beat(self):
        arc = neutral_arc(effects={"environment": {"barriers": {
            "primary": {"status": "open"}
        }}})
        purposes = []

        def llm(messages, **kwargs):
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            purposes.append(purpose)
            if purpose == "macro_arc_create":
                return arc
            if purpose == "macro_arc_validate":
                return {"valid": True, "issues": []}
            if purpose == "beat_generation":
                return {"beats": ["Operator opens the primary barrier."]}
            if purpose == "beat_validation":
                return {"valid": True, "issue": ""}
            raise AssertionError(purpose)

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            minimax.generate_beats_from_story(
                "The operator opens the primary barrier.", 1,
                path=str(Path(directory) / "beats.txt"),
                story_arc_path=str(Path(directory) / "story_arc.json"),
                validation_state_path=str(state_path),
                llm_request=llm,
                reuse_story_arc=False,
            )
            checkpoint = minimax.load_beat_validation_state(str(state_path))

        self.assertEqual(
            checkpoint["current_beat_state"]["environment"]["barriers"]["primary"]["status"],
            "open",
        )
        self.assertEqual(purposes.count("macro_arc_validate"), 1)

    def test_arc_creation_failure_restarts_creation_without_escaping(self):
        arc = neutral_arc()
        create_count = 0

        def llm(messages, **kwargs):
            nonlocal create_count
            purpose = kwargs.get("history_metadata", {}).get("purpose")
            if purpose == "macro_arc_create":
                create_count += 1
                if create_count == 1:
                    raise RuntimeError("transient model failure")
                return arc
            if purpose == "macro_arc_validate":
                return {"valid": True, "issues": []}
            if purpose == "beat_generation":
                return {"beats": ["Operator opens the primary barrier."]}
            if purpose == "beat_validation":
                return {"valid": True, "issue": ""}
            raise AssertionError(purpose)

        with tempfile.TemporaryDirectory() as directory:
            result = minimax.generate_beats_from_story(
                "The operator opens the primary barrier.", 1,
                path=str(Path(directory) / "beats.txt"),
                story_arc_path=str(Path(directory) / "story_arc.json"),
                validation_state_path=str(Path(directory) / "state.json"),
                llm_request=llm,
                reuse_story_arc=False,
            )

        self.assertEqual(result, ["Operator opens the primary barrier."])
        self.assertEqual(create_count, 2)


if __name__ == "__main__":
    unittest.main()
