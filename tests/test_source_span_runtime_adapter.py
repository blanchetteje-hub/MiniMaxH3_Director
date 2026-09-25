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



def test_source_span_chapter_starts_drive_refresh_modes():
    arc = minimax.source_span_story_plan_to_macro_arc(_amy_plan(), 8)

    assert minimax.source_span_refresh_segments(arc) == (7,)
    assert [
        minimax.conditioning_mode_for_segment(
            segment,
            refresh_interval=2,
            macro_arc=arc,
        )
        for segment in range(1, 9)
    ] == [
        "initial",
        "continuation",
        "continuation",
        "continuation",
        "continuation",
        "continuation",
        "clean_refresh",
        "continuation",
    ]
    assert minimax.is_refresh_segment(7, refresh_interval=2, macro_arc=arc)
    assert not minimax.is_refresh_segment(2, refresh_interval=2, macro_arc=arc)
    assert not minimax.is_refresh_segment(8, refresh_interval=2, macro_arc=arc)


def test_legacy_refresh_interval_remains_fallback_without_source_span_arc():
    legacy_arc = {
        "phases": [{
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 4,
            "narrative_purpose": "Legacy phase",
            "broad_progression": "Legacy progression",
            "characters_introduced": [],
            "location": "Legacy location",
            "required_events": [],
        }]
    }

    assert minimax.source_span_refresh_segments(legacy_arc) == ()
    assert minimax.is_refresh_segment(2, refresh_interval=2, macro_arc=legacy_arc)
    assert not minimax.is_refresh_segment(3, refresh_interval=2, macro_arc=legacy_arc)



def test_repeated_source_unit_state_commits_only_on_last_owned_beat():
    plan = _amy_plan()
    arc = minimax.source_span_story_plan_to_macro_arc(
        plan,
        8,
        state_effects_by_unit={
            4: [{
                "op": "set_threat_state",
                "entity": "zombies",
                "value": "active",
            }],
        },
    )

    first_phase = arc["phases"][0]
    assert first_phase["required_events"][3]["state_effects"] == []
    assert first_phase["required_events"][4]["state_effects"] == []
    assert first_phase["required_events"][5]["state_effects"] == [{
        "op": "set_threat_state",
        "entity": "zombies",
        "value": "active",
    }]


def test_source_unit_state_parser_rejects_invented_location_destination():
    with pytest.raises(ValueError, match="not explicitly grounded"):
        minimax.parse_source_unit_state_effects(
            {
                "state_effects": [{
                    "op": "set_location",
                    "entity": "Will",
                    "value": "outside",
                }],
            },
            "Amy lets Will out of the basement.",
        )


def test_source_unit_state_parser_accepts_explicit_containment_release():
    assert minimax.parse_source_unit_state_effects(
        {
            "state_effects": [{
                "op": "set_containment",
                "entity": "Will",
                "container": "basement",
                "value": "free",
            }],
        },
        "Amy lets Will out of the basement.",
    ) == [{
        "op": "set_containment",
        "entity": "Will",
        "container": "basement",
        "value": "free",
    }]



def test_chapter_refresh_replays_source_authorized_current_state():
    plan = _amy_plan()
    arc = minimax.source_span_story_plan_to_macro_arc(
        plan,
        8,
        state_effects_by_unit={
            2: [
                {"op": "set_location", "entity": "Will", "value": "basement"},
                {"op": "set_location", "entity": "Amber", "value": "basement"},
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "contained",
                },
                {
                    "op": "set_containment",
                    "entity": "Amber",
                    "container": "basement",
                    "value": "contained",
                },
                {
                    "op": "set_barrier_state",
                    "entity": "basement door",
                    "value": "locked",
                },
            ],
            3: [
                {
                    "op": "set_item_state",
                    "entity": "pistol",
                    "owner": "Amy",
                    "value": "equipped",
                },
                {
                    "op": "set_item_state",
                    "entity": "katana",
                    "owner": "Amy",
                    "value": "equipped",
                },
            ],
        },
    )

    opening = minimax.format_source_authorized_opening_state(arc, 7)

    assert "SOURCE-AUTHORIZED CURRENT STATE" in opening
    assert '"containment":"contained"' in opening
    assert '"contained_in":"basement"' in opening
    assert "basement door" in opening
    assert '"status":"locked"' in opening
    assert "pistol" in opening
    assert "katana" in opening



def test_source_unit_state_effects_attach_only_to_final_assigned_beat():
    plan = _amy_plan()
    arc = minimax.source_span_story_plan_to_macro_arc(
        plan,
        8,
        state_effects_by_unit={
            4: [
                {
                    "op": "set_condition",
                    "entity": "zombies",
                    "value": "attacking",
                }
            ],
            5: [
                {
                    "op": "set_threat_state",
                    "entity": "last zombie",
                    "value": "dead",
                }
            ],
        },
    )

    chapter1 = arc["phases"][0]["required_events"]
    assert chapter1[3]["state_effects"] == []
    assert chapter1[4]["state_effects"] == []
    assert chapter1[5]["state_effects"] == [
        {
            "op": "set_condition",
            "entity": "zombies",
            "value": "attacking",
        }
    ]
    assert arc["phases"][1]["required_events"][0]["state_effects"] == [
        {
            "op": "set_threat_state",
            "entity": "last zombie",
            "value": "dead",
        }
    ]


def test_source_unit_state_parser_rejects_invented_location_destination():
    with pytest.raises(ValueError, match="not explicitly grounded"):
        minimax.parse_source_unit_state_effects(
            {
                "state_effects": [
                    {
                        "op": "set_location",
                        "entity": "Will",
                        "value": "outside",
                    }
                ]
            },
            "Amy lets Will out of the basement.",
        )


def test_source_unit_state_parser_allows_explicit_containment_release():
    effects = minimax.parse_source_unit_state_effects(
        {
            "state_effects": [
                {
                    "op": "set_containment",
                    "entity": "Will",
                    "container": "basement",
                    "value": "free",
                }
            ]
        },
        "Amy lets Will out of the basement.",
    )

    assert effects == [
        {
            "op": "set_containment",
            "entity": "Will",
            "container": "basement",
            "value": "free",
        }
    ]
