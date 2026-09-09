from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import minimax
from dino_continuity import ContinuityReferenceConfig, update_subject_references
from identity_validator import IdentitySelectionResult
from subject_registry import SubjectRegistry


def test_registry_registers_and_retrieves_multiple_subjects_by_stable_id(tmp_path):
    registry = SubjectRegistry()
    registry.register(
        "amy",
        canonical_reference="amy.jpg",
        current_state_reference=str(tmp_path / "amy_current.png"),
        dino_query="woman",
    )
    registry.register(
        "beth",
        canonical_reference="beth.jpg",
        current_state_reference=str(tmp_path / "beth_current.png"),
        dino_query="woman",
    )

    assert registry.get_subject("amy")["subject_id"] == "amy"
    assert registry.get("beth")["canonical_reference"] == "beth.jpg"
    assert registry.keys_for_query("woman") == ("amy", "beth")
    assert set(registry.group_by_query()["woman"]) == {"amy", "beth"}
    assert registry["amy"]["current_state_reference"] != registry["beth"][
        "current_state_reference"
    ]


def test_missing_current_state_is_valid_and_failed_update_preserves_previous(tmp_path):
    current = tmp_path / "amy_current.png"
    registry = SubjectRegistry()
    registry.register("amy", current_state_reference=str(current))

    assert registry.has_valid_current_state("amy") is False

    current.write_bytes(b"not an image")
    assert registry.update_current_state("amy", current) is False
    assert registry["amy"]["current_state_reference"] == str(current)

    Image.new("RGB", (8, 8), "red").save(current)
    assert registry.update_current_state("amy", current) is True
    assert registry.has_valid_current_state("amy") is True


def test_h3_parser_and_continuity_registry_share_the_same_subject_model():
    from minimax import parse_subject_registry

    registry = parse_subject_registry(
        "<Subject 7> is Amy, a woman referenced in <Picture 1>."
    )

    assert isinstance(registry, SubjectRegistry)
    assert registry[7]["subject_id"] == 7
    assert registry[7]["dino_query"] == "woman"


def test_story_only_subject_is_registered_without_visual_references():
    calls = []
    registry = SubjectRegistry.from_definitions(
        "<Subject 7> is Werewolf",
        query_resolver=lambda definition: calls.append(definition) or "werewolf",
    )

    assert registry[7]["name"] == "Werewolf"
    assert registry[7]["picture_ids"] == []
    assert registry[7]["picture_id"] is None
    assert registry[7]["canonical_reference"] is None
    assert registry[7]["current_state_reference"] is None
    assert registry[7]["dino_query"] == "werewolf"
    assert calls


@pytest.mark.parametrize(
    ("definition", "expected_input", "resolved_query"),
    [
        (
            "<Subject 2> is werewolf, lore-defined.",
            "werewolf",
            "werewolf",
        ),
        (
            "<Subject 3> is eldritch monster, lore-defined.",
            "eldritch monster",
            "eldritch-monster",
        ),
        (
            "<Subject 4> is robot dog, story-defined.",
            "robot dog",
            "robot-dog",
        ),
        (
            "<Subject 5> is robot dog, a mechanical canine companion, story-defined.",
            "robot dog, a mechanical canine companion",
            "robot-dog",
        ),
    ],
)
def test_dino_query_llm_input_excludes_definition_provenance(
    definition,
    expected_input,
    resolved_query,
):
    calls = []
    registry = SubjectRegistry.from_definitions(
        definition,
        query_resolver=lambda value: calls.append(value) or resolved_query,
    )

    assert calls == [expected_input]
    assert registry[next(iter(registry))]["dino_query"] == resolved_query
    assert not any(
        marker in registry[next(iter(registry))]["dino_query"]
        for marker in (
            "lore-defined",
            "story-defined",
            "picture-defined",
            "video-defined",
            "generated-defined",
        )
    )


@pytest.mark.parametrize(
    "marker",
    [
        "lore-defined",
        "story-defined",
        "picture-defined",
        "video-defined",
        "generated-defined",
    ],
)
def test_dino_query_resolver_cannot_return_provenance_marker(marker):
    registry = SubjectRegistry.from_definitions(
        f"<Subject 1> is werewolf, {marker}.",
        query_resolver=lambda _value: marker,
    )

    assert registry[1]["dino_query"] == "werewolf"


def test_legacy_provenance_query_is_re_resolved_from_subject_identity():
    calls = []
    registry = SubjectRegistry.from_records(
        {
            "werewolf": {
                "subject_id": 2,
                "name": "werewolf",
                "subject_definition": "<Subject 2> is werewolf, lore-defined.",
                "dino_query": "lore-defined",
                "dino_query_explicit": False,
            }
        },
        query_resolver=lambda value: calls.append(value) or "werewolf",
    )

    assert calls == ["werewolf"]
    assert registry["werewolf"]["dino_query"] == "werewolf"


def test_explicit_dino_query_overrides_provenance_and_resolver():
    registry = SubjectRegistry()
    registry.register(
        1,
        name="werewolf",
        definition="<Subject 1> is werewolf, lore-defined.",
        dino_query="wolf",
        query_resolver=lambda _value: (_ for _ in ()).throw(
            AssertionError("explicit dino_query must not invoke the resolver")
        ),
    )

    assert registry[1]["dino_query"] == "wolf"


def test_multiple_story_only_subjects_are_authoritative_registry_entries():
    registry = SubjectRegistry.from_definitions(
        "\n".join([
            "<Subject 1> is Werewolf, a large supernatural creature.",
            "<Subject 2> is Eldritch Monster, an ancient entity.",
            "<Subject 3> is Robot, a service machine.",
            "<Subject 4> is Dog, a black dog.",
        ]),
        query_resolver=lambda _definition: "story-subject",
    )

    assert [registry[index]["name"] for index in range(1, 5)] == [
        "Werewolf", "Eldritch Monster", "Robot", "Dog",
    ]
    assert all(
        registry[index]["canonical_reference"] is None
        and registry[index]["current_state_reference"] is None
        for index in range(1, 5)
    )


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Amy, a young woman", "woman"),
        ("Bob, an older man", "man"),
        ("Casey, a person", "person"),
        ("a massive werewolf", "werewolf"),
        ("an eldritch monster", "eldritch-monster"),
        ("a black dog", "dog"),
    ],
)
def test_definition_dino_query_uses_human_gender_or_nonhuman_type(
    description, expected
):
    resolver = lambda _definition: expected
    registry = SubjectRegistry.from_definitions(
        f"<Subject 1> is {description}, referenced in <Picture 1>.",
        query_resolver=resolver,
    )

    assert registry[1]["dino_query"] == expected


def test_explicit_record_dino_query_is_preserved():
    registry = SubjectRegistry.from_records({
        "wolf": {
            "subject_id": 1,
            "name": "Wolf",
            "gender": "N/A",
            "dino_query": "canine-like creature",
            "definition": "an anthropomorphic wolf",
        }
    }, query_rules={"anthropomorphic wolf": "werewolf"})

    assert registry["wolf"]["dino_query"] == "canine-like creature"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("a damaged robot", "robot"),
    ],
)
def test_nonhuman_query_inference(description, expected):
    registry = SubjectRegistry.from_definitions(
        f"<Subject 1> is {description}, referenced in <Picture 1>.",
        query_resolver=lambda _definition: expected,
    )

    assert registry[1]["dino_query"] == expected


def test_user_query_rule_is_applied_before_definition_inference():
    registry = SubjectRegistry.from_definitions(
        "\n".join([
            "<Subject 1> is an anthropomorphic wolf, referenced in <Picture 1>.",
            "<Subject 2> is a humanoid wolf, referenced in <Picture 2>.",
            "<Subject 3> is a werewolf-like creature, referenced in <Picture 3>.",
        ]),
        query_rules={
            "anthropomorphic wolf": "werewolf",
            "humanoid wolf": "werewolf",
            "werewolf-like creature": "werewolf",
        },
    )

    assert [registry[index]["dino_query"] for index in (1, 2, 3)] == [
        "werewolf", "werewolf", "werewolf"
    ]


def test_multiple_subjects_share_their_resolved_query():
    registry = SubjectRegistry.from_definitions(
        "\n".join([
            "<Subject 1> is Amy, a woman referenced in <Picture 1>.",
            "<Subject 2> is Beth, a young woman referenced in <Picture 2>.",
            "<Subject 3> is a massive werewolf, referenced in <Picture 3>.",
        ]),
        query_resolver=lambda _definition: "werewolf",
    )

    assert registry.keys_for_query("woman") == (1, 2)
    assert tuple(registry.group_by_query()) == ("woman", "werewolf")


def test_minimax_repeatable_query_rule_matches_existing_cli_style():
    arguments = minimax.parse_args([
        "5", "20", ".5",
        "--dino-query-rule", "anthropomorphic wolf=werewolf",
    ])
    previous = minimax.DINO_QUERY_RULES
    try:
        assert minimax.configure_dino_query_rules(arguments) == {
            "anthropomorphic wolf": "werewolf"
        }
        registry = minimax.parse_subject_registry(
            "<Subject 1> is an anthropomorphic wolf, referenced in <Picture 1>."
        )
        assert registry[1]["dino_query"] == "werewolf"
    finally:
        minimax.DINO_QUERY_RULES = previous


def test_llm_query_is_resolved_once_and_persisted_in_the_record():
    calls = []
    registry = SubjectRegistry.from_definitions(
        "<Subject 1> is a damaged biomechanical entity, referenced in <Picture 1>.",
        query_resolver=lambda definition: calls.append(definition) or "robot",
    )

    assert registry[1]["dino_query"] == "robot"
    assert len(calls) == 1

    SubjectRegistry.from_records(
        registry,
        query_resolver=lambda _definition: (_ for _ in ()).throw(
            AssertionError("persisted dino_query should not be resolved again")
        ),
    )
    assert len(calls) == 1


def test_minimax_uses_existing_local_llm_shape_for_query_resolution(monkeypatch):
    calls = []

    def fake_ask_llm(messages, **kwargs):
        calls.append((messages, kwargs))
        return "eldritch-monster"

    monkeypatch.setattr(minimax, "ask_llm", fake_ask_llm)
    state = minimax.continuity_state_for_registry(
        "<Subject 1> is an eldritch tentacled creature, referenced in <Picture 1>.",
        minimax.new_continuity_state(),
        query_resolver=minimax._resolve_dino_query_with_llm,
    )

    assert state["subjects"]["an eldritch tentacled creature"]["dino_query"] == (
        "eldritch-monster"
    )
    assert calls[0][0] == [{
        "role": "user",
            "content": (
                "In the most minimal, succinct sense, what is this definition in "
                "one word (or two words hyphenated)? Note: If the subject name itself is already a concise, "
                "common visual object/category description, return it unchanged. Do not replace it with synonyms.\n"
                "'an eldritch tentacled creature'.\n"
                "Return a one-word response."
        ),
    }]
    assert calls[0][1]["response_format"] is None


def test_continuity_rebuild_loads_persisted_dino_query_without_second_llm_call():
    calls = []
    definitions = "<Subject 1> is Werewolf."

    state = minimax.continuity_state_for_registry(
        definitions,
        minimax.new_continuity_state(),
        query_resolver=lambda value: calls.append(value) or "werewolf",
    )
    assert state["subjects"]["Werewolf"]["dino_query"] == "werewolf"
    assert calls == ["Werewolf"]

    restored = minimax.continuity_state_for_registry(
        definitions,
        state,
        query_resolver=lambda _value: (_ for _ in ()).throw(
            AssertionError("persisted dino_query must not invoke the LLM")
        ),
    )

    assert restored["subjects"]["Werewolf"]["dino_query"] == "werewolf"
    assert calls == ["Werewolf"]


class _RegistryIdentity:
    def __init__(self):
        self.prepare_calls = []

    def prepare_canonical(self, subject, reference):
        self.prepare_calls.append((subject, reference))
        return SimpleNamespace(matched=True, reason="canonical_loaded")

    def select_candidates_for_subjects(
        self, subjects, candidates, *, identity_threshold, identity_margin
    ):
        return {
            subject_id: IdentitySelectionResult(
                evaluated=True,
                matched=True,
                reason="identity_match",
                canonical_subject=subject_id,
                identity_similarity=0.9,
                identity_threshold=identity_threshold,
                identity_margin=identity_margin,
                candidate_index=candidates[0].candidate_index,
            )
            for subject_id in subjects
        }


def test_dino_uses_registry_query_and_stable_id(tmp_path):
    video = tmp_path / "segment.mp4"
    video.write_bytes(b"video")
    registry = SubjectRegistry()
    registry.register(
        "subject-7",
        registry_key="amy-key",
        name="Amy",
        canonical_reference="amy.jpg",
        current_state_reference=str(tmp_path / "amy_current.png"),
        dino_query="woman",
    )

    class Detector:
        def __init__(self):
            self.queries = []

        def detect(self, image, query, box_threshold, text_threshold):
            self.queries.append(query)
            return SimpleNamespace(detections=[
                SimpleNamespace(
                    confidence=0.9,
                    bbox=[10, 10, 70, 70],
                    matched_phrase="woman",
                )
            ])

    detector = Detector()
    identity = _RegistryIdentity()

    def extract_frame(_video, frame_name, input_directory, **_kwargs):
        path = Path(input_directory) / frame_name
        Image.new("RGB", (100, 80), "black").save(path)
        return frame_name

    results = update_subject_references(
        str(video),
        registry,
        str(tmp_path),
        detector=detector,
        identity_validator=identity,
        config=ContinuityReferenceConfig(max_candidate_frames=1),
        frame_count_fn=lambda _path: 1,
        frame_extractor=extract_frame,
    )

    assert detector.queries == ["woman"]
    assert identity.prepare_calls == [("subject-7", "amy.jpg")]
    assert results["amy-key"].found is True
    assert registry.has_valid_current_state("amy-key") is True
