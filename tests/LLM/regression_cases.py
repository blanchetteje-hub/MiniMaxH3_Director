from __future__ import annotations

from tests.LLM.cases import BeatCase


def _state() -> dict[str, object]:
    return {
        "characters": {"Amy": {"current_injuries": "none"}},
        "locations": {"Amy": "hallway"},
        "threats": {
            "zombie_1": {"status": "active", "location": "hallway"},
            "zombie_2": {"status": "active", "location": "hallway"},
        },
        "story": {
            "immediate_threat_area_clear": False,
            "terminal_threat_state": "not reached; multiple zombies remain",
        },
    }


REGRESSION_CASES: tuple[BeatCase, ...] = (
    BeatCase(
        story_slug="regression_terminal_last_standing_early",
        story_title="Last Standing Early",
        beat_number=1,
        premise=(
            "Amy must cross the house and survive the last standing zombie before "
            "she can secure the basement."
        ),
        phase_goal="Keep fighting the zombies without ending the threat early.",
        previous_final_beat="Amy is in the hallway; multiple zombies remain active.",
        state_now=_state(),
        beat_job="Amy kills another attacking zombie.",
        next_beat_job="Amy kills the last zombie.",
        candidate_beat=(
            "Amy shoots the last standing zombie in the head, killing it."
        ),
        expected_valid=False,
        expected_issues=("SEQUENCING",),
    ),
    BeatCase(
        story_slug="regression_non_terminal_control",
        story_title="Non-Terminal Control",
        beat_number=2,
        premise="Amy must stop the zombies in the hallway without ending the whole threat early.",
        phase_goal="Keep fighting the zombies without ending the threat early.",
        previous_final_beat="Amy reaches the hallway; multiple zombies remain active.",
        state_now=_state(),
        beat_job="Amy kills another attacking zombie.",
        next_beat_job="Amy kills the last zombie.",
        candidate_beat="Amy shoots another attacking zombie in the head, killing it.",
        expected_valid=True,
        expected_issues=(),
    ),
    BeatCase(
        story_slug="regression_result_for_required_action",
        story_title="Result for Required Action",
        beat_number=1,
        premise="Amy must stop the last standing zombie in the hallway.",
        phase_goal="Complete the final confrontation.",
        previous_final_beat="Amy reaches the hallway; the final zombie is active.",
        state_now=_state(),
        beat_job="Amy kills the final zombie.",
        next_beat_job=None,
        candidate_beat="The final zombie lies dead on the hallway floor.",
        expected_valid=False,
        expected_issues=("JOB",),
    ),
    BeatCase(
        story_slug="regression_explicit_required_action",
        story_title="Explicit Required Action",
        beat_number=1,
        premise="Amy must stop the last standing zombie in the hallway.",
        phase_goal="Complete the final confrontation.",
        previous_final_beat="Amy reaches the hallway; the final zombie is active.",
        state_now=_state(),
        beat_job="Amy kills the final zombie.",
        next_beat_job=None,
        candidate_beat="Amy shoots the final zombie in the head, killing it.",
        expected_valid=True,
        expected_issues=(),
    ),
)
