import pytest

from story_planner import (
    allocate_chapter_beats,
    assign_source_units_to_beats,
    build_chapter_spans,
    derive_chapter_boundaries,
    enumerate_source_units,
)


def _flag(units, unit_id, *, terminal=False, hard_reset=False):
    return [
        unit.with_flags(
            terminal=terminal if unit.id == unit_id else unit.terminal,
            hard_reset=hard_reset if unit.id == unit_id else unit.hard_reset,
        )
        for unit in units
    ]


def test_enumerate_source_units_preserves_exact_source_spans():
    story = "First sentence.  Second sentence!\nThird sentence?"
    units = enumerate_source_units(story)

    assert [unit.text for unit in units] == [
        "First sentence.",
        "Second sentence!",
        "Third sentence?",
    ]
    assert all(story[unit.start:unit.end] == unit.text for unit in units)


def test_amy_terminal_plus_closure_creates_gold_boundary_and_exact_spans():
    story = (
        "Amy cooks breakfast for Will and Amber. "
        "A zombie breaks the kitchen door window; Amy gets Will and Amber into "
        "the basement and locks the door. "
        "Amy retrieves her hidden pistol and katana and equips them. "
        "The majority of the story is Amy fighting attacking zombies. "
        "Amy kills the last zombie and the house is soaked in blood. "
        "Amy lets Will and Amber out of the basement."
    )
    units = enumerate_source_units(story)
    units = _flag(units, 5, terminal=True)

    boundaries = derive_chapter_boundaries(units)
    chapters = build_chapter_spans(story, units, boundaries)

    assert boundaries == [4]
    assert [chapter.source_unit_ids for chapter in chapters] == [
        (1, 2, 3, 4),
        (5, 6),
    ]
    assert chapters[0].source_text == story[units[0].start:units[3].end]
    assert chapters[1].source_text == story[units[4].start:units[5].end]
    assert allocate_chapter_beats(
        chapters,
        8,
        emphasized_source_unit_ids=[4],
    ) == [6, 2]


def test_final_terminal_stays_in_current_chapter():
    story = (
        "Diagnose the engine. Test it. Replace the sensor. "
        "Confirm the repair is complete."
    )
    units = enumerate_source_units(story)
    units = _flag(units, 4, terminal=True)

    assert derive_chapter_boundaries(units) == []


def test_terminal_before_hard_reset_stays_with_prior_phase():
    story = (
        "Begin analysis. Continue analysis. The final test resolves the question. "
        "One year later the team begins a new field phase."
    )
    units = enumerate_source_units(story)
    units = _flag(units, 3, terminal=True)
    units = _flag(units, 4, hard_reset=True)

    assert derive_chapter_boundaries(units) == [3]


def test_hard_resets_create_boundaries_before_reset_units():
    story = (
        "Field work ends. Three months later analysis begins. Analysis continues. "
        "The final test resolves the question. One year later field work resumes."
    )
    units = enumerate_source_units(story)
    units = _flag(units, 2, hard_reset=True)
    units = _flag(units, 4, terminal=True)
    units = _flag(units, 5, hard_reset=True)

    assert derive_chapter_boundaries(units) == [1, 4]


def test_continuous_story_has_no_boundary_without_terminal_closure_or_reset():
    story = "Inspect engine. Test electrical system. Replace sensor. Continue testing."
    units = enumerate_source_units(story)

    assert derive_chapter_boundaries(units) == []


def test_strict_beat_assignment_matches_proven_amy_shape():
    assert assign_source_units_to_beats(
        [1, 2, 3, 4, 5],
        6,
        repeatable_source_unit_ids=[4],
    ) == [(1,), (2,), (3,), (4,), (4,), (5,)]


def test_extra_beats_require_explicit_repeatable_source_unit():
    with pytest.raises(ValueError, match="repeatable"):
        assign_source_units_to_beats([1, 2], 3)



def test_binary_classifier_builders_keep_questions_narrow():
    from story_planner import (
        build_hard_reset_messages,
        build_terminal_messages,
    )

    story = "Breakfast happens. An alarm sounds."
    units = enumerate_source_units(story)

    terminal_prompt = build_terminal_messages(story, units[0])[-1]["content"]
    reset_prompt = build_hard_reset_messages(units[0], units[1])[-1]["content"]

    assert "decisively end" in terminal_prompt
    assert "HARD RESET" in reset_prompt
    assert "Immediate cause-and-effect" in reset_prompt


def test_parse_binary_decision_is_strict():
    from story_planner import parse_binary_decision

    assert parse_binary_decision({"decision": "YES", "reason": "done"}) is True
    assert parse_binary_decision('{"decision":"NO","reason":"continues"}') is False

    with pytest.raises(ValueError):
        parse_binary_decision({"decision": "MAYBE", "reason": "unclear"})


def test_classify_source_units_uses_terminal_and_hard_reset_calls():
    from story_planner import classify_source_units

    story = "Work begins. Work completes. One year later, new work begins."
    units = enumerate_source_units(story)
    responses = iter([
        {"decision": "NO", "reason": "setup"},
        {"decision": "YES", "reason": "completion"},
        {"decision": "NO", "reason": "continuous into completion"},
        {"decision": "NO", "reason": "later phase"},
        {"decision": "YES", "reason": "explicit one-year jump"},
    ])
    calls = []

    def fake_llm(messages, **kwargs):
        calls.append((messages, kwargs))
        return next(responses)

    classified = classify_source_units(story, units, fake_llm)

    assert [(unit.terminal, unit.hard_reset) for unit in classified] == [
        (False, False),
        (True, False),
        (False, True),
    ]
    assert [call[1]["history_metadata"]["purpose"] for call in calls] == [
        "source_unit_terminal",
        "source_unit_terminal",
        "source_unit_hard_reset",
        "source_unit_terminal",
        "source_unit_hard_reset",
    ]
