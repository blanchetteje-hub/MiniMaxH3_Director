from pathlib import Path

import pytest

from minimax import (
    BeatDefinition,
    expected_visible_subjects_for_segment,
    load_or_generate_beats,
    normalize_beat_subject_metadata,
    populate_story_subject_definitions,
    parse_beats_content,
    save_generated_beats,
    scene_presence_state_after_beat,
    scene_presence_transition,
    validate_beat_subject_metadata,
)
from subject_registry import SubjectRegistry, parse_subject_registry


def _registry(*names):
    registry = SubjectRegistry()
    for name in names:
        registry.register(name, name=name, dino_query="woman")
    return registry


def test_visibility_and_scene_presence_are_distinct():
    registry = _registry("Amy", "Beth")
    beats = normalize_beat_subject_metadata(
        [
            BeatDefinition(
                "Amy enters.",
                visible_subjects=["Amy"],
                enters=["Amy"],
                exits=[],
            ),
            BeatDefinition(
                "Amy acts while Beth remains offscreen.",
                visible_subjects=["Amy"],
                enters=[],
                exits=[],
            ),
        ],
        registry,
    )

    assert expected_visible_subjects_for_segment(beats, 2) == ("Amy",)
    assert scene_presence_transition(("Amy",), beats[1]) == {
        "before": ("Amy",),
        "during": ("Amy",),
        "after": ("Amy",),
    }


def test_scene_present_context_can_include_non_visible_competitor():
    registry = _registry("Amy", "Beth")
    beat = BeatDefinition(
        "Amy acts while Beth waits offscreen.",
        visible_subjects=["Amy"],
        enters=[],
        exits=[],
    )
    normalized, issues = validate_beat_subject_metadata(
        [beat],
        registry,
        initial_scene_present_subjects=["Beth"],
    )

    assert issues == []
    assert normalized[0].visible_subjects == ("Amy",)
    assert scene_presence_state_after_beat(
        {"scene_present_subjects": ["Beth"], "last_processed_beat_id": 1},
        normalized[0],
        2,
    ) == {
        "scene_present_subjects": ["Beth"],
        "last_processed_beat_id": 2,
    }


def test_story_only_subject_resolves_case_insensitively_on_first_visible_beat():
    subject_definitions = populate_story_subject_definitions(
        "<Subject 1> is Amy, a woman referenced in <Picture 1>.",
        "Amy encounters a werewolf in the forest.",
        [
            BeatDefinition(
                "The Werewolf enters.",
                visible_subjects=["Werewolf"],
                enters=["Werewolf"],
                exits=[],
            )
        ],
    )
    registry = parse_subject_registry(subject_definitions)

    beats = normalize_beat_subject_metadata(
        [
            BeatDefinition(
                "The Werewolf enters.",
                visible_subjects=["Werewolf"],
                enters=["Werewolf"],
                exits=[],
            ),
            BeatDefinition(
                "The werewolf watches.",
                visible_subjects=["werewolf"],
                enters=[],
                exits=[],
            ),
        ],
        registry,
    )

    assert registry[2]["name"] == "Werewolf"
    assert registry[2]["canonical_reference"] is None
    assert registry[2]["current_state_reference"] is None
    assert beats[0].visible_subjects == (2,)
    assert beats[0].enters == (2,)
    assert beats[1].visible_subjects == (2,)


def test_unknown_story_subject_still_fails_metadata_validation():
    subject_definitions = populate_story_subject_definitions(
        "<Subject 1> is Amy, a woman referenced in <Picture 1>.",
        "Amy walks through the forest.",
        [
            BeatDefinition(
                "An unknown creature appears.",
                visible_subjects=["Unknown Creature"],
                enters=["Unknown Creature"],
                exits=[],
            )
        ],
    )
    registry = parse_subject_registry(subject_definitions)

    with pytest.raises(ValueError, match="unknown subject"):
        normalize_beat_subject_metadata(
            [BeatDefinition(
                "An unknown creature appears.",
                visible_subjects=["Unknown Creature"],
                enters=["Unknown Creature"],
                exits=[],
            )],
            registry,
        )


def test_existing_beats_can_register_story_subject_before_validation(tmp_path):
    beats_path = tmp_path / "beats.txt"
    beats_path.write_text(
        '# BeatMetadata 1 {"visible_subjects":["Werewolf"],'
        '"enters":["Werewolf"],"exits":[]}\n'
        "1. The Werewolf enters.\n",
        encoding="utf-8",
    )

    beats = load_or_generate_beats(
        beats_path,
        "Amy encounters a werewolf in the forest.",
        1,
        subject_definitions=(
            "<Subject 1> is Amy, a woman referenced in <Picture 1>."
        ),
    )

    assert beats[0].visible_subjects == (2,)
    assert beats[0].enters == (2,)


def test_legacy_numeric_beats_recover_story_subject_name_before_validation(tmp_path):
    beats_path = tmp_path / "legacy_beats.txt"
    beats_path.write_text(
        '# BeatMetadata 1 {"visible_subjects":[2],'
        '"enters":[2],"exits":[]}\n'
        "1. The Werewolf enters.\n",
        encoding="utf-8",
    )

    beats = load_or_generate_beats(
        beats_path,
        "Amy encounters a werewolf in the forest.",
        1,
        subject_definitions=(
            "<Subject 1> is Amy, a woman referenced in <Picture 1>."
        ),
    )

    assert beats[0].visible_subjects == (2,)
    assert beats[0].enters == (2,)


@pytest.mark.parametrize(
    ("beat_text", "story", "registered_name"),
    [
        (
            "The werewolf enters.",
            "Amy sees The werewolf enter the forest.",
            "werewolf",
        ),
        (
            "The camera holds.",
            "Amy watches as The camera holds on the forest.",
            None,
        ),
        (
            "The forest floor remains.",
            "Amy looks down at The forest floor.",
            None,
        ),
    ],
)
def test_story_subject_discovery_drops_articles_and_incidental_scene_nouns(
    beat_text,
    story,
    registered_name,
):
    definitions = populate_story_subject_definitions(
        "<Subject 1> is Amy, a woman referenced in <Picture 1>.",
        story,
        [BeatDefinition(beat_text, visible_subjects=[2])],
    )
    names = {
        record["name"]
        for record in parse_subject_registry(definitions).values()
    }

    assert "The" not in names
    if registered_name is None:
        assert names == {"Amy"}
    else:
        assert registered_name in {name.casefold() for name in names}


def test_enter_must_be_visible_and_exit_must_be_present():
    registry = _registry("Amy", "Beth", "Claire")
    beats = [
        BeatDefinition(
            "Amy enters.",
            visible_subjects=["Amy"],
            enters=["Amy"],
            exits=[],
        ),
        BeatDefinition(
            "Beth is mentioned.",
            visible_subjects=[],
            enters=["Beth"],
            exits=["Claire"],
        ),
    ]
    _normalized, issues = validate_beat_subject_metadata(beats, registry)
    assert any("enters subjects not in visible_subjects" in issue for issue in issues)
    assert any("exits subjects that are not scene-present" in issue for issue in issues)


def test_unknown_and_duplicate_references_are_reported_without_registry_mutation():
    registry = _registry("Amy")
    before = dict(registry["Amy"])
    normalized, issues = validate_beat_subject_metadata(
        [
            BeatDefinition(
                "Amy appears.",
                visible_subjects=[" amy ", "Amy", "Unknown"],
                enters=["amy"],
                exits=[],
            )
        ],
        registry,
    )
    assert normalized[0].visible_subjects == ("Amy",)
    assert normalized[0].enters == ("Amy",)
    assert any("unknown subject" in issue.casefold() for issue in issues)
    assert dict(registry["Amy"]) == before


def test_beats_text_round_trip_preserves_metadata(tmp_path):
    beats_path = Path(tmp_path) / "beats.txt"
    beats = [
        BeatDefinition(
            "Amy enters.",
            visible_subjects=["Amy"],
            enters=["Amy"],
            exits=[],
        ),
        BeatDefinition(
            "Amy leaves.",
            visible_subjects=["Amy"],
            enters=[],
            exits=["Amy"],
        ),
    ]
    save_generated_beats(beats, beats_path)
    parsed, directive = parse_beats_content(beats_path.read_text())

    assert directive == ""
    assert [(beat.visible_subjects, beat.enters, beat.exits) for beat in parsed] == [
        (("Amy",), ("Amy",), ()),
        (("Amy",), (), ("Amy",)),
    ]
    assert all(beat.subject_metadata_present for beat in parsed)


def test_legacy_text_only_beats_do_not_claim_visibility_metadata():
    beats, _directive = parse_beats_content("1. Amy acts.\n2. Beth waits.\n")
    assert expected_visible_subjects_for_segment(beats, 1) is None


def test_invalid_subject_registry_type_is_clear():
    with pytest.raises(TypeError, match="subject_registry"):
        validate_beat_subject_metadata(
            [BeatDefinition("Amy acts.", visible_subjects=["Amy"])],
            object(),
        )
