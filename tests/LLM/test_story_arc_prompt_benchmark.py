from __future__ import annotations

import os

import pytest

from tests.LLM.llama_client import call_llama, get_model_settings
from tests.LLM.score_story_arc_prompt import normalize_arc_result
from tests.LLM.story_arc_cases import (
    ALL_CASES,
    HOLDOUT_CASES,
    SMOKE_CASES,
    TRAIN_CASES,
    cases_for_split,
    fixture_contract,
)
from tests.LLM.story_arc_prompt_under_test import build_messages


STATE_EFFECT_FIELDS = {
    "set_location": {"op", "entity", "value"},
    "set_item_state": {"op", "entity", "owner", "value"},
    "set_barrier_state": {"op", "entity", "value"},
    "set_threat_state": {"op", "entity", "value"},
    "set_object_state": {"op", "entity", "value"},
    "set_containment": {"op", "entity", "container", "value"},
    "set_condition": {"op", "entity", "value"},
    "set_clothing": {"op", "entity", "slot", "item", "damage"},
}


def test_story_arc_fixture_contract():
    contract = fixture_contract()

    assert contract["total"] == 100
    assert contract["smoke"] == 10
    assert contract["train"] == 80
    assert contract["holdout"] == 10
    assert contract["unique_ids"] == 100
    assert contract["valid_total"] == 50
    assert contract["invalid_total"] == 50
    assert contract["themes"] == ["high_fantasy", "horror", "scifi"]

    assert contract["smoke_counts"].count(10) == 5
    assert contract["smoke_counts"].count(20) == 5

    train_counts = contract["train_counts"]
    assert len(train_counts) == 80
    assert train_counts.count(50) == 1
    assert min(count for count in train_counts if count != 50) == 10
    assert max(count for count in train_counts if count != 50) == 30
    assert all(10 <= count <= 30 or count == 50 for count in train_counts)

    assert contract["holdout_counts"] == [20] * 8 + [30, 50]

    assert len(SMOKE_CASES) == 10
    assert len(TRAIN_CASES) == 80
    assert len(HOLDOUT_CASES) == 10
    assert len(ALL_CASES) == 100



def test_story_arc_cases_are_structurally_well_formed():
    for case in ALL_CASES:
        phases = case.proposed_arc.get("phases")
        assert isinstance(phases, list) and phases, case.case_id
        expected_start = 1
        event_ids = set()
        dependencies = []
        for phase_number, phase in enumerate(phases, start=1):
            assert phase["phase_number"] == phase_number, case.case_id
            assert phase["beat_start"] == expected_start, case.case_id
            assert phase["beat_end"] >= phase["beat_start"], case.case_id
            assert phase["beat_end"] <= case.beat_count, case.case_id
            for event in phase["required_events"]:
                assert event["id"] not in event_ids, case.case_id
                event_ids.add(event["id"])
                assert phase["beat_start"] <= event["beat_number"] <= phase["beat_end"], case.case_id
                dependencies.extend(event.get("depends_on", []))
                if "state_effects" in event:
                    assert isinstance(event["state_effects"], list), case.case_id
                    for effect in event["state_effects"]:
                        assert isinstance(effect, dict), case.case_id
                        op = effect.get("op")
                        assert op in STATE_EFFECT_FIELDS, case.case_id
                        assert set(effect) == STATE_EFFECT_FIELDS[op], case.case_id
            expected_start = phase["beat_end"] + 1
        assert expected_start == case.beat_count + 1, case.case_id
        assert all(dependency in event_ids for dependency in dependencies), case.case_id

def _selected_cases():
    split = os.environ.get("H3_STORY_ARC_BENCHMARK_SPLIT", "smoke").lower()
    return cases_for_split(split)


CASES = _selected_cases()


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.environ.get("H3_RUN_STORY_ARC_BENCHMARK") != "1",
    reason="set H3_RUN_STORY_ARC_BENCHMARK=1 to contact the configured local LLM",
)
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: case.case_id,
)
def test_story_arc_validator_prompt(case):
    settings = get_model_settings()
    raw = call_llama(build_messages(case, settings))
    valid, issues = normalize_arc_result(raw)

    assert valid == case.expected_valid, (
        f"{case.case_id}: expected valid={case.expected_valid}, got valid={valid}; "
        f"model issues={issues!r}; diagnostics={case.expected_issues}"
    )
