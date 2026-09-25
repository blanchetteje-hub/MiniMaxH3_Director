import json
from pathlib import Path
import tempfile

import minimax


def test_generate_beats_prefers_source_span_planner_and_scopes_chapter_source():
    story = (
        "Worker inspects the kitchen. "
        "Worker locks the kitchen door. "
        "One year later the worker inspects the laboratory."
    )
    purposes = []
    beat_generation_prompts = []

    def llm(messages, **kwargs):
        metadata = kwargs.get("history_metadata", {})
        purpose = metadata.get("purpose")
        purposes.append(purpose)

        if purpose == "source_unit_split_gate":
            return {"decision": "KEEP_TOGETHER", "reason": "single phase unit"}
        if purpose == "source_unit_terminal":
            return {"decision": "NO", "reason": "not terminal"}
        if purpose == "source_unit_hard_reset":
            unit_id = metadata["source_unit_id"]
            return {
                "decision": "YES" if unit_id == 3 else "NO",
                "reason": "one-year discontinuity only at unit 3",
            }
        if purpose == "source_unit_state_effects":
            return {"state_effects": []}
        if purpose == "beat_generation":
            beat_generation_prompts.append(messages[-1]["content"])
            start = metadata["batch_start"]
            end = metadata["batch_end"]
            source_beats = {
                1: "1. Worker inspects the kitchen.",
                2: "2. Worker locks the kitchen door.",
                3: "3. One year later the worker inspects the laboratory.",
            }
            return {
                "beats": [
                    {"beat_number": number, "beat_text": source_beats[number]}
                    for number in range(start, end + 1)
                ]
            }
        if purpose == "beat_validation":
            return {"valid": True, "issue": ""}

        raise AssertionError(f"unexpected LLM purpose: {purpose}")

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        arc_path = directory / "arc.json"
        result = minimax.generate_beats_from_story(
            story,
            3,
            path=str(directory / "beats.txt"),
            story_arc_path=str(arc_path),
            validation_state_path=str(directory / "state.json"),
            llm_request=llm,
            reuse_story_arc=False,
        )
        saved_arc = json.loads(arc_path.read_text(encoding="utf-8"))

    assert result == [
        "Worker inspects the kitchen.",
        "Worker locks the kitchen door.",
        "One year later the worker inspects the laboratory.",
    ]
    assert "macro_arc_create" not in purposes
    assert "macro_arc_validate" not in purposes
    assert [(phase["beat_start"], phase["beat_end"]) for phase in saved_arc["phases"]] == [
        (1, 2),
        (3, 3),
    ]

    assert len(beat_generation_prompts) == 2
    first_prompt, second_prompt = beat_generation_prompts
    assert "Worker inspects the kitchen." in first_prompt
    assert "Worker locks the kitchen door." in first_prompt
    assert "One year later" not in first_prompt
    assert "One year later the worker inspects the laboratory." in second_prompt
    assert "Worker inspects the kitchen." not in second_prompt
