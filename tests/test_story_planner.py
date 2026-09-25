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



def test_cut_candidates_preserve_exact_mixed_phase_sentence():
    from story_planner import enumerate_cut_candidates

    story = (
        "She spends most of the story repeating measurements, then one final "
        "measurement resolves the problem and she immediately closes the lab."
    )
    unit = enumerate_source_units(story)[0]
    candidates = enumerate_cut_candidates(unit)

    assert [
        (candidate.label, candidate.left_text, candidate.right_text)
        for candidate in candidates
    ] == [
        (
            "A",
            "She spends most of the story repeating measurements,",
            "then one final measurement resolves the problem and she immediately closes the lab.",
        ),
        (
            "B",
            "She spends most of the story repeating measurements, then one final measurement resolves the problem",
            "and she immediately closes the lab.",
        ),
    ]


def test_refine_source_units_only_uses_cut_choice_after_split_gate():
    from story_planner import refine_source_units

    story = (
        "She spends most of the story repeating measurements, then one final "
        "measurement resolves the problem and she immediately closes the lab."
    )
    units = enumerate_source_units(story)
    responses = iter([
        {"decision": "SPLIT", "reason": "ongoing process crosses into resolution"},
        {"choice": "A", "reason": "resolution begins on the right"},
    ])
    purposes = []

    def fake_llm(messages, **kwargs):
        purposes.append(kwargs["history_metadata"]["purpose"])
        return next(responses)

    refined = refine_source_units(story, units, fake_llm)

    assert [unit.text for unit in refined] == [
        "She spends most of the story repeating measurements,",
        "then one final measurement resolves the problem and she immediately closes the lab.",
    ]
    assert purposes == ["source_unit_split_gate", "source_unit_cut_choice"]
    assert all(story[unit.start:unit.end] == unit.text for unit in refined)


def test_refine_source_units_keeps_continuous_unit_without_cut_call():
    from story_planner import refine_source_units

    story = (
        "The operator tests one subsystem, replaces a failed component, and "
        "continues testing the same subsystem."
    )
    units = enumerate_source_units(story)
    calls = []

    def fake_llm(messages, **kwargs):
        calls.append(kwargs["history_metadata"]["purpose"])
        return {"decision": "KEEP_TOGETHER", "reason": "continuous work"}

    refined = refine_source_units(story, units, fake_llm)

    assert [unit.text for unit in refined] == [story]
    assert calls == ["source_unit_split_gate"]



def test_build_story_plan_produces_amy_six_two_and_strict_ownership():
    from story_planner import build_story_plan

    story = (
        "Amy cooks breakfast for Will and Amber. "
        "A zombie breaks the kitchen door window; Amy gets Will and Amber into "
        "the basement and locks the door. "
        "Amy retrieves her hidden pistol and katana and equips them. "
        "The majority of the film is Amy killing zombies as they attack. "
        "Amy kills the last zombie and the house is soaked in blood. "
        "Amy lets Will and Amber out of the basement."
    )

    def fake_llm(messages, **kwargs):
        metadata = kwargs["history_metadata"]
        purpose = metadata["purpose"]
        unit_id = metadata.get("source_unit_id")
        if purpose == "source_unit_split_gate":
            return {"decision": "KEEP_TOGETHER", "reason": "single phase"}
        if purpose == "source_unit_terminal":
            return {
                "decision": "YES" if unit_id == 5 else "NO",
                "reason": "terminal only at the last-zombie unit",
            }
        if purpose == "source_unit_hard_reset":
            return {"decision": "NO", "reason": "continuous story"}
        if purpose == "source_unit_visible_responsibility":
            return {"decision": "YES", "reason": "visible source action"}
        if purpose == "source_unit_local_relation":
            return {"relation": "NEW_TASK"}
        raise AssertionError(purpose)

    plan = build_story_plan(story, 8, fake_llm)

    assert [chapter.source_unit_ids for chapter in plan.chapters] == [
        (1, 2, 3, 4),
        (5, 6),
    ]
    assert [chapter.beat_count for chapter in plan.chapters] == [6, 2]
    assert plan.chapters[0].beat_source_unit_ids == (
        (1,), (2,), (3,), (4,), (4,), (4,)
    )
    assert plan.chapters[1].beat_source_unit_ids == ((5,), (6,))
    assert plan.total_beats == 8


def test_build_story_plan_does_not_invent_repeatability_for_surplus_beats():
    from story_planner import build_story_plan

    story = "A worker inspects the room. The worker closes the door."

    def fake_llm(messages, **kwargs):
        purpose = kwargs["history_metadata"]["purpose"]
        if purpose == "source_unit_split_gate":
            return {"decision": "KEEP_TOGETHER", "reason": "continuous"}
        if purpose == "source_unit_terminal":
            return {"decision": "NO", "reason": "no central terminal distinction"}
        if purpose == "source_unit_hard_reset":
            return {"decision": "NO", "reason": "continuous"}
        if purpose == "source_unit_visible_responsibility":
            return {"decision": "YES", "reason": "visible source action"}
        if purpose == "source_unit_local_relation":
            return {"relation": "NEW_TASK"}
        raise AssertionError(purpose)

    plan = build_story_plan(story, 3, fake_llm)

    assert [chapter.beat_count for chapter in plan.chapters] == [3]
    assert plan.chapters[0].beat_source_unit_ids is None


def test_visible_source_responsibility_classifier_filters_framing_only_units():
    from story_planner import classify_visible_source_unit_ids

    story = (
        "A grounded drama about a pilot trying to reunite with her family. "
        "Mara stands in the hangar wearing a red coat. "
        "Mara remembers the previous winter."
    )
    units = enumerate_source_units(story)
    responses = iter([
        {"decision": "NO", "reason": "premise only"},
        {"decision": "YES", "reason": "visible state"},
        {"decision": "NO", "reason": "internal thought only"},
    ])
    purposes = []

    def fake_llm(messages, **kwargs):
        purposes.append(kwargs["history_metadata"]["purpose"])
        return next(responses)

    assert classify_visible_source_unit_ids(units, fake_llm) == [2]
    assert purposes == ["source_unit_visible_responsibility"] * 3


def test_visible_source_responsibility_prompt_keeps_repeated_action_visible():
    from story_planner import build_visible_responsibility_messages

    unit = enumerate_source_units(
        "For most of the night, Mara repeatedly repairs damaged radios."
    )[0]
    prompt = build_visible_responsibility_messages(unit)[-1]["content"]

    assert "on-screen action or visible state" in prompt
    assert "genre/premise/summary framing" in prompt


def test_local_relation_prompt_distinguishes_mechanical_completion_from_later_use():
    from story_planner import build_local_relation_messages

    units = enumerate_source_units(
        "Mara retrieves a wrench. Mara later uses the wrench while repairing a different assembly."
    )
    prompt = build_local_relation_messages(units[0], units[1])[-1]["content"]

    assert "immediate next mechanical step" in prompt
    assert "Merely using equipment later" in prompt
    assert "Starting a fresh item/test" in prompt


def test_local_relation_parser_and_grouping_keep_repeatables_isolated():
    from story_planner import (
        build_chapter_spans,
        group_chapter_source_responsibilities,
    )

    story = (
        "An alarm sounds. The worker immediately closes the valve. "
        "The worker retrieves a tool. The worker equips the tool. "
        "For most of the shift, the worker repeatedly checks the system."
    )
    units = enumerate_source_units(story)
    chapter = build_chapter_spans(story, units)[0]
    relations = iter([
        {"relation": "IMMEDIATE_REACTION"},
        {"relation": "NEW_TASK"},
        {"relation": "DIRECT_COMPLETION"},
    ])

    def fake_llm(messages, **kwargs):
        return next(relations)

    groups = group_chapter_source_responsibilities(
        units,
        chapter,
        visible_source_unit_ids=[1, 2, 3, 4, 5],
        repeatable_source_unit_ids=[5],
        llm_request=fake_llm,
    )

    assert groups == ((1, 2), (3, 4), (5,))


def test_real_amy_story_groups_to_three_finite_beats_plus_repeated_process():
    from story_planner import build_story_plan

    story = (
        "A realistic action film about a woman, Amy, protecting her two kids "
        "(Will and Amber) from a zombie apocalypse.\n"
        "Amy is at home on a normal day, wearing a tight, black tank top and "
        "denim jeans, cooking breakfast for her young kids.\n"
        "Suddenly, a zombie breaks the kitchen door window and Amy sees the danger. "
        "She rushes her kids to the basement, gets them inside, and then locks the door.\n"
        "She retrieves her hidden arsenal consisting of a pistol and a katana. "
        "She equips the weapons.\n\n"
        "The majority of the film is Amy killing (dismembering, decapitating, etc.) "
        "zombies as they try and attack her.\n"
        "Amy kills the last of the zombies, her house now soaked in blood. "
        "She lets her kids out of the basement."
    )

    relation_by_pair = {
        (2, 3): "NEW_TASK",
        (3, 4): "IMMEDIATE_REACTION",
        (4, 5): "NEW_TASK",
        (5, 6): "DIRECT_COMPLETION",
        (8, 9): "NEW_TASK",
    }

    def fake_llm(messages, **kwargs):
        metadata = kwargs["history_metadata"]
        purpose = metadata["purpose"]
        unit_id = metadata.get("source_unit_id")
        if purpose == "source_unit_split_gate":
            return {"decision": "KEEP_TOGETHER", "reason": "one source phase"}
        if purpose == "source_unit_terminal":
            return {
                "decision": "YES" if unit_id == 8 else "NO",
                "reason": "only the last-zombie unit is terminal",
            }
        if purpose == "source_unit_hard_reset":
            return {"decision": "NO", "reason": "continuous story"}
        if purpose == "source_unit_visible_responsibility":
            return {
                "decision": "NO" if unit_id == 1 else "YES",
                "reason": "premise only" if unit_id == 1 else "visible action/state",
            }
        if purpose == "source_unit_local_relation":
            pair = (
                metadata["left_source_unit_id"],
                metadata["right_source_unit_id"],
            )
            return {"relation": relation_by_pair[pair]}
        raise AssertionError(purpose)

    plan = build_story_plan(story, 8, fake_llm)

    assert [chapter.source_unit_ids for chapter in plan.chapters] == [
        (1, 2, 3, 4, 5, 6, 7),
        (8, 9),
    ]
    assert [chapter.beat_count for chapter in plan.chapters] == [6, 2]
    assert plan.chapters[0].beat_source_unit_ids == (
        (2,),
        (3, 4),
        (5, 6),
        (7,),
        (7,),
        (7,),
    )
    assert plan.chapters[1].beat_source_unit_ids == ((8,), (9,))
