import pytest

import minimax
from story_planner import PlannedChapter, SourceUnit, StoryPlan


def _amy_plan():
    texts = [
        "Amy cooks breakfast for Will and Amber.",
        "A zombie breaks the kitchen door window; Amy gets Will and Amber into the basement and locks the door.",
        "Amy retrieves her hidden pistol and katana and equips them.",
        "The majority of the film is Amy killing zombies as they attack.",
        "Amy kills the last zombie and the house is soaked in blood.",
        "Amy lets Will and Amber out of the basement.",
    ]
    units = tuple(
        SourceUnit(id=index, start=index * 10, end=index * 10 + len(text), text=text)
        for index, text in enumerate(texts, start=1)
    )
    return StoryPlan(
        source_units=units,
        chapters=(
            PlannedChapter(
                chapter=1,
                source_unit_ids=(1, 2, 3, 4),
                source_text=" ".join(texts[:4]),
                beat_count=6,
                beat_source_unit_ids=((1,), (2,), (3,), (4,), (4,), (4,)),
            ),
            PlannedChapter(
                chapter=2,
                source_unit_ids=(5, 6),
                source_text=" ".join(texts[4:]),
                beat_count=2,
                beat_source_unit_ids=((5,), (6,)),
            ),
        ),
    )


def test_source_span_adapter_preserves_chapter_ranges_and_source_jobs():
    arc = minimax.source_span_story_plan_to_macro_arc(_amy_plan(), 8)

    assert [(phase["beat_start"], phase["beat_end"]) for phase in arc["phases"]] == [
        (1, 6),
        (7, 8),
    ]
    assert [event["beat_number"] for event in arc["phases"][0]["required_events"]] == [
        1, 2, 3, 4, 5, 6
    ]
    repeated = [
        event["event"] for event in arc["phases"][0]["required_events"][3:]
    ]
    assert repeated == [
        "The majority of the film is Amy killing zombies as they attack.",
        "The majority of the film is Amy killing zombies as they attack.",
        "The majority of the film is Amy killing zombies as they attack.",
    ]
    assert arc["phases"][1]["required_events"][0]["depends_on"] == ["E6"]


def test_source_span_phase_exposes_only_current_chapter_source():
    plan = _amy_plan()
    arc = minimax.source_span_story_plan_to_macro_arc(plan, 8)

    assert minimax.phase_authoritative_source(
        arc["phases"][0],
        "GLOBAL STORY MUST NOT BE USED",
    ) == plan.chapters[0].source_text
    assert minimax.phase_authoritative_source(
        arc["phases"][1],
        "GLOBAL STORY MUST NOT BE USED",
    ) == plan.chapters[1].source_text


def test_source_span_adapter_refuses_ambiguous_surplus_ownership():
    unit = SourceUnit(id=1, start=0, end=12, text="Inspect room.")
    plan = StoryPlan(
        source_units=(unit,),
        chapters=(
            PlannedChapter(
                chapter=1,
                source_unit_ids=(1,),
                source_text="Inspect room.",
                beat_count=2,
                beat_source_unit_ids=None,
            ),
        ),
    )

    with pytest.raises(ValueError, match="no deterministic"):
        minimax.source_span_story_plan_to_macro_arc(plan, 2)
