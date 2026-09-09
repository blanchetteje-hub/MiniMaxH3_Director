from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from dino_continuity import (
    ContinuityReferenceConfig,
    DinoCandidate,
    SubjectReferenceUpdateResult,
)
import minimax
from minimax import resolve_unresolved_subjects_with_vision
from subject_registry import SubjectRegistry


def _registry(tmp_path, *names, with_references=False):
    registry = SubjectRegistry()
    for index, name in enumerate(names):
        kwargs = {
            "name": name,
            "dino_query": "woman" if name != "Werewolf" else "werewolf",
            "identity_backend": "insightface" if name != "Werewolf" else "dino",
        }
        if with_references:
            canonical = Image.new("RGB", (8, 8), (10 + index, 10, 10))
            current_path = tmp_path / f"{name}_existing.png"
            Image.new("RGB", (8, 8), (20 + index, 20, 20)).save(current_path)
            kwargs.update(
                canonical_reference=canonical,
                current_state_reference=str(current_path),
            )
        registry.register(name, **kwargs)
    return registry


def _step6_result(key, registry, status="no_eligible_candidate", updated=False):
    record = registry.get_subject(key)
    return SubjectReferenceUpdateResult(
        subject_key=key,
        updated=updated,
        status=status,
        dino_query=record["dino_query"],
        identity_backend=record["identity_backend"],
    )


def _candidate(
    frame_index,
    candidate_index=0,
    query="woman",
    color=(80, 1, 2),
    crop_size=(8, 8),
):
    return DinoCandidate(
        candidate_index=candidate_index,
        dino_query=query,
        confidence=0.40,
        bbox=[2, 2, 8, 8],
        crop_bbox=[1, 1, 9, 9],
        bbox_area_ratio=0.36,
        touches_frame_edge=False,
        image_width=10,
        image_height=10,
        crop=Image.new("RGB", crop_size, color),
        source_metadata={
            "frame_index": frame_index,
            "timestamp": frame_index / 24.0,
        },
    )


def _config():
    return ContinuityReferenceConfig(
        frame_search_interval=1,
        max_candidate_frames=3,
        min_bbox_area_ratio=0.01,
    )


def test_non_visible_and_step6_resolved_subjects_do_not_call_fallback(tmp_path):
    registry = _registry(tmp_path, "Amy", "Beth")
    calls = []

    def vision_client(**_kwargs):
        calls.append(True)
        return {"matched": False, "frame_index": None, "candidate_index": None}

    results = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy"],
        {
            "Amy": _step6_result("Amy", registry, updated=True, status="updated"),
            "Beth": _step6_result("Beth", registry),
        },
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
    )

    assert calls == []
    assert results["Amy"].status == "updated"
    assert results["Beth"].status == "no_eligible_candidate"


def test_low_confidence_retained_evidence_commits_exact_crop(
    tmp_path,
    capsys,
    monkeypatch,
):
    registry = _registry(tmp_path, "Amy", with_references=True)
    candidate = _candidate(118, color=(231, 4, 5))
    calls = []
    sent_paths = []

    def capture_image_path(path):
        sent_paths.append(Path(path))
        return "data:image/png;base64,"

    monkeypatch.setattr(minimax, "_vision_image_data_url", capture_image_path)
    capture_directory = tmp_path / "step7_frames"

    def vision_client(**kwargs):
        calls.append(kwargs)
        return {"matched": True, "frame_index": 118, "candidate_index": 0}

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy"],
        {"Amy": _step6_result("Amy", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"woman": [candidate]},
        segment_number=4,
        step7_frame_output_directory=capture_directory,
    )["Amy"]

    assert result.updated is True
    assert result.status == "vision_fallback_updated"
    assert result.frame_index == 118
    assert result.resolution_method == "vision_fallback"
    with Image.open(result.output_path) as image:
        assert image.getpixel((0, 0)) == (231, 4, 5)
    assert len(calls) == 1
    assert len(sent_paths) == 4
    assert all(path.parent == capture_directory for path in sent_paths)
    assert all(path.is_file() for path in sent_paths)
    assert any(path.name.endswith("contact_sheet.png") for path in sent_paths)
    assert sorted(path.name for path in capture_directory.iterdir()) == sorted(
        path.name for path in sent_paths
    )
    content = calls[0]["messages"][1]["content"]
    assert len([item for item in content if item.get("type") == "image_url"]) == 4
    output = capsys.readouterr().out
    assert "Step 7: queries=('woman',)" in output
    assert "Step 7: contact sheet written" in output
    assert "Step 7: subject='Amy' updated from fallback" in output


def test_step7_sends_full_size_newest_candidate_and_readable_sheet(
    tmp_path,
    monkeypatch,
):
    registry = _registry(tmp_path, "Amy", with_references=True)
    registry.get_subject("Amy")["canonical_reference"] = Image.new(
        "RGB",
        (96, 128),
        (220, 180, 160),
    )
    newest = _candidate(120, color=(231, 4, 5), crop_size=(160, 240))
    older = _candidate(119, color=(12, 34, 56), crop_size=(140, 210))
    sent_paths = []
    calls = []

    def capture_image_path(path):
        sent_paths.append(Path(path))
        return "data:image/png;base64,"

    monkeypatch.setattr(minimax, "_vision_image_data_url", capture_image_path)

    def vision_client(**kwargs):
        calls.append(kwargs)
        return {"matched": True, "frame_index": 120, "candidate_index": 0}

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy"],
        {"Amy": _step6_result("Amy", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"woman": [newest, older]},
        segment_number=7,
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Amy"]

    assert result.updated is True
    assert len(calls) == 1
    assert len(sent_paths) == 4  # canonical, current, newest crop, sheet
    with Image.open(sent_paths[0]) as image:
        assert image.size == (96, 128)
    newest_paths = [
        path for path in sent_paths if "newest_candidate_F120-C0" in path.name
    ]
    assert len(newest_paths) == 1
    with Image.open(newest_paths[0]) as image:
        assert image.size == (160, 240)
        assert image.getpixel((0, 0)) == (231, 4, 5)

    sheet_paths = [path for path in sent_paths if path.name.endswith("contact_sheet.png")]
    assert len(sheet_paths) == 1
    with Image.open(sheet_paths[0]) as image:
        assert image.size == (1024, 512)

    prompt = calls[0]["messages"][1]["content"][0]["text"]
    assert "REFERENCE IMAGE" in prompt
    assert "CURRENT STATE IMAGE" in prompt
    assert "NEWEST CANDIDATE" in prompt
    assert "CONTACT SHEET" in prompt
    assert "First determine whether the separately supplied newest candidate" in prompt
    assert "If it is a usable match, return that candidate." in prompt
    assert "Only consider older candidates if the newest candidate is not a usable identity" in prompt

    with Image.open(result.output_path) as image:
        assert image.size == (160, 240)
        assert image.getpixel((0, 0)) == (231, 4, 5)


def test_no_reference_subject_bootstraps_from_category_and_commits_crop(
    tmp_path,
    capsys,
):
    registry = _registry(tmp_path, "Werewolf")
    candidate = _candidate(123, query="werewolf", color=(231, 4, 5))
    calls = []

    def vision_client(**kwargs):
        calls.append(kwargs)
        return {"matched": True, "frame_index": 123, "candidate_index": 0}

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Werewolf"],
        {"Werewolf": _step6_result("Werewolf", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"werewolf": [candidate]},
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Werewolf"]

    assert result.updated is True
    assert result.status == "vision_fallback_updated"
    assert result.resolution_method == "vision_bootstrap"
    assert Path(result.output_path).name == "Werewolf_current.png"
    assert registry["Werewolf"]["current_state_reference"] == result.output_path
    prompt = calls[0]["messages"][1]["content"][0]["text"]
    assert "No visual reference images are supplied" in prompt
    assert "actually depicts the story subject" in prompt
    assert len(
        [item for item in calls[0]["messages"][1]["content"]
         if item.get("type") == "image_url"]
    ) == 2
    output = capsys.readouterr().out
    assert "mode=category_bootstrap visual_references=0" in output
    assert "bootstrap selected frame=123 candidate=0" in output


def test_category_bootstrap_no_match_does_not_create_state_image(tmp_path):
    registry = _registry(tmp_path, "Werewolf")
    calls = []

    def vision_client(**kwargs):
        calls.append(kwargs)
        return {"matched": False, "frame_index": None, "candidate_index": None}

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Werewolf"],
        {"Werewolf": _step6_result("Werewolf", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"werewolf": [_candidate(123, query="werewolf")]},
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Werewolf"]

    assert result.updated is False
    assert result.status == "vision_fallback_no_match"
    assert calls
    assert not (tmp_path / "references" / "Werewolf_current.png").exists()
    assert registry["Werewolf"]["current_state_reference"] is None


def test_blank_step7_frames_are_skipped_before_dino_and_vision(tmp_path):
    registry = _registry(tmp_path, "Woman")
    detector_calls = []
    vision_calls = []

    class Detector:
        def detect(self, image, query, _box_threshold, _text_threshold):
            detector_calls.append(image.getpixel((0, 0)))
            return SimpleNamespace(
                detections=[SimpleNamespace(
                    confidence=0.95,
                    bbox=[2, 2, 8, 8],
                    matched_phrase=query,
                )]
            )

    def extract(_video, frame_name, input_directory, frame_index, **_kwargs):
        color = (0, 0, 0) if frame_index == 2 else (80, 1, 2)
        Image.new("RGB", (10, 10), color).save(
            Path(input_directory) / frame_name
        )
        return frame_name

    def vision_client(**kwargs):
        vision_calls.append(kwargs)
        return {"matched": True, "frame_index": 1, "candidate_index": 0}

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Woman"],
        {"Woman": _step6_result("Woman", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        frame_count_fn=lambda _path: 3,
        frame_extractor=extract,
        detector=Detector(),
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Woman"]

    assert result.updated is True
    assert result.frame_index == 1
    assert detector_calls == [(80, 1, 2), (80, 1, 2)]
    assert len(vision_calls) == 1


def test_successful_bootstrap_switches_later_step7_calls_to_identity_mode(
    tmp_path,
):
    registry = _registry(tmp_path, "Werewolf")
    calls = []

    def vision_client(**kwargs):
        calls.append(kwargs)
        frame_index = 123 + len(calls) - 1
        return {"matched": True, "frame_index": frame_index, "candidate_index": 0}

    first = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Werewolf"],
        {"Werewolf": _step6_result("Werewolf", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"werewolf": [_candidate(123, query="werewolf")]},
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Werewolf"]
    second = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Werewolf"],
        {"Werewolf": _step6_result("Werewolf", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={"werewolf": [_candidate(124, query="werewolf")]},
        step7_frame_output_directory=tmp_path / "step7_frames",
    )["Werewolf"]

    assert first.resolution_method == "vision_bootstrap"
    assert second.resolution_method == "vision_fallback"
    assert "No visual reference images are supplied" in calls[0]["messages"][1]["content"][0]["text"]
    assert "No visual reference images are supplied" not in calls[1]["messages"][1]["content"][0]["text"]
    assert "same tracked subject" in calls[1]["messages"][1]["content"][0]["text"]


def test_same_query_no_reference_subjects_remain_unresolved(tmp_path):
    registry = _registry(tmp_path, "Werewolf A", "Werewolf B")
    calls = []

    def vision_client(**kwargs):
        calls.append(kwargs)
        return {"matched": True, "frame_index": 123, "candidate_index": 0}

    results = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Werewolf A", "Werewolf B"],
        {
            "Werewolf A": _step6_result("Werewolf A", registry),
            "Werewolf B": _step6_result("Werewolf B", registry),
        },
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        fallback_evidence={
            "werewolf": [
                _candidate(123, query="werewolf"),
                _candidate(122, candidate_index=1, query="werewolf"),
            ]
        },
        step7_frame_output_directory=tmp_path / "step7_frames",
    )

    assert calls == []
    assert all(
        result.status == "vision_fallback_ambiguous"
        for result in results.values()
    )
    assert not list((tmp_path / "references").glob("*_current.png"))


def test_missing_query_uses_one_shared_backward_dino_traversal(tmp_path):
    registry = _registry(tmp_path, "Amy", "Beth")
    registry["Amy"]["subject_definition"] = "a tall woman"
    registry["Beth"]["subject_definition"] = "a short woman"
    frame_calls = []
    detector_calls = []
    vision_calls = []

    def frame_count(_path):
        return 2

    def extract(_path, frame_name, input_directory, frame_index, **_kwargs):
        frame_calls.append(frame_index)
        image = Image.new("RGB", (10, 10), (frame_index, 0, 0))
        image.putpixel((1, 1), (32, 0, 0))
        image.save(Path(input_directory) / frame_name)
        return frame_name

    class Detector:
        def detect(self, _image, query, _box_threshold, _text_threshold):
            detector_calls.append(query)
            return SimpleNamespace(
                detections=[SimpleNamespace(
                    confidence=0.40,
                    bbox=[2, 2, 8, 8],
                    matched_phrase=query,
                )]
            )

    def vision_client(**kwargs):
        vision_calls.append(kwargs)
        text = kwargs["messages"][1]["content"][0]["text"]
        name = "Amy" if "'Amy'" in text else "Beth"
        return {
            "matched": True,
            "frame_index": 1 if name == "Amy" else 0,
            "candidate_index": 0,
        }

    results = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy", "Beth"],
        {
            "Amy": _step6_result("Amy", registry),
            "Beth": _step6_result("Beth", registry),
        },
        tmp_path / "references",
        config=_config(),
        vision_client=vision_client,
        frame_count_fn=frame_count,
        frame_extractor=extract,
        detector=Detector(),
    )

    assert frame_calls == [1, 0]
    assert detector_calls == ["woman", "woman"]
    assert len(vision_calls) == 2
    assert results["Amy"].updated is True
    assert results["Beth"].updated is True


def test_minimax_step7_receives_the_step6_detector_instance(monkeypatch, tmp_path):
    registry = _registry(tmp_path, "Amy")
    detector = object()
    seen = {}

    def fake_step6(*_args, **kwargs):
        seen["step6"] = kwargs["detector"]
        return {"Amy": _step6_result("Amy", registry)}

    def fake_step7(*_args, **kwargs):
        seen["step7"] = kwargs["detector"]
        return {"Amy": _step6_result("Amy", registry)}

    monkeypatch.setattr(minimax, "search_and_update_current_states", fake_step6)
    monkeypatch.setattr(minimax, "resolve_unresolved_subjects_with_vision", fake_step7)

    minimax.update_dino_continuity_references(
        "segment.mp4",
        {"subjects": {"Amy": registry["Amy"]}},
        _config(),
        tmp_path / "references",
        expected_visible_subjects=("Amy",),
        detector=detector,
        identity_validator=object(),
    )

    assert seen == {"step6": detector, "step7": detector}


def test_invalid_selection_does_not_commit(tmp_path):
    registry = _registry(tmp_path, "Amy")
    existing = tmp_path / "Amy_current.png"
    Image.new("RGB", (8, 8), (9, 9, 9)).save(existing)
    registry.update_current_state("Amy", existing)
    candidate = _candidate(118)

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy"],
        {"Amy": _step6_result("Amy", registry)},
        tmp_path / "references",
        config=_config(),
        vision_client=lambda **_kwargs: {
            "matched": True,
            "frame_index": 999,
            "candidate_index": 0,
        },
        fallback_evidence={"woman": [candidate]},
    )["Amy"]

    assert result.updated is False
    assert result.status == "vision_fallback_error"
    assert registry.get_subject("Amy")["current_state_reference"] == str(existing)
    with Image.open(existing) as image:
        assert image.getpixel((0, 0)) == (9, 9, 9)


def test_duplicate_fallback_selection_commits_neither_subject(tmp_path):
    registry = _registry(tmp_path, "Amy", "Beth")
    candidate = _candidate(118)

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ["Amy", "Beth"],
        {
            "Amy": _step6_result("Amy", registry),
            "Beth": _step6_result("Beth", registry),
        },
        tmp_path / "references",
        config=_config(),
        vision_client=lambda **_kwargs: {
            "matched": True,
            "frame_index": 118,
            "candidate_index": 0,
        },
        fallback_evidence={"woman": [candidate]},
    )

    assert result["Amy"].status == "vision_fallback_ambiguous"
    assert result["Beth"].status == "vision_fallback_ambiguous"
    assert not (tmp_path / "references" / "Amy_current.png").exists()
    assert not (tmp_path / "references" / "Beth_current.png").exists()
