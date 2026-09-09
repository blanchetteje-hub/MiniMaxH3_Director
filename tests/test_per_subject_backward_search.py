from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import dino_continuity
from dino_continuity import (
    ContinuityReferenceConfig,
    DinoCandidate,
    IdentityScoreMatrix,
    IdentityScorePair,
    SharedQueryCandidates,
    SubjectReferenceUpdateResult,
    _backward_frame_indices,
    filter_candidates_to_state_recency_window,
    search_and_update_current_states,
)
from minimax import resolve_unresolved_subjects_with_vision
from subject_registry import SubjectRegistry


def _registry(*names, backend="insightface"):
    registry = SubjectRegistry()
    for name in names:
        registry.register(
            name,
            name=name,
            dino_query="woman",
            canonical_reference=Image.new("RGB", (8, 8), "white"),
            identity_backend=backend,
        )
    return registry


def _stable_id_registry(*names, backend="future_backend"):
    return SubjectRegistry.from_records({
        name: {
            "subject_id": index,
            "name": name,
            "dino_query": "woman",
            "identity_backend": backend,
        }
        for index, name in enumerate(names, start=1)
    })


def _candidate(index, frame_index):
    crop = Image.new("RGB", (12, 12), (frame_index, index, 0))
    return DinoCandidate(
        candidate_index=index,
        dino_query="woman",
        confidence=0.9,
        bbox=[0, 0, 12, 12],
        crop_bbox=[0, 0, 12, 12],
        bbox_area_ratio=1.0,
        touches_frame_edge=False,
        image_width=12,
        image_height=12,
        crop=crop,
        source_metadata={"frame_index": frame_index},
    )


def _matrix(subject_keys, candidates, scores, query="woman"):
    return IdentityScoreMatrix(
        dino_query=query,
        subject_keys=tuple(subject_keys),
        candidate_indices=tuple(candidate.candidate_index for candidate in candidates),
        scores={
            subject: {
                candidate.candidate_index: IdentityScorePair(
                    subject_key=subject,
                    candidate_index=candidate.candidate_index,
                    evaluated=True,
                    identity_similarity=score,
                    status="identity_score",
                    identity_backend="insightface",
                )
                for candidate, score in zip(candidates, scores[subject])
            }
            for subject in subject_keys
        },
        identity_threshold=0.48,
    )


def _frame_functions(tmp_path, frame_count=3):
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")
    extracted_frames = []

    def frame_count_fn(_video_path):
        return frame_count

    def frame_extractor(_video_path, frame_name, input_directory, frame_index, **_kwargs):
        extracted_frames.append(frame_index)
        image = Image.new("RGB", (20, 20), (frame_index, 0, 0))
        image.save(Path(input_directory) / frame_name)
        return frame_name

    return video_path, extracted_frames, frame_count_fn, frame_extractor


def test_state_recency_window_allows_recent_candidates_and_rejects_old_ones():
    # Frame end timestamps are used for the boundary: with a 241-frame,
    # 24-fps segment the final frame ends at 10.0417s.
    config = ContinuityReferenceConfig(
        frame_search_interval=1,
        max_candidate_frames=500,
        max_state_age_seconds=1.0,
    )

    planned, limited = _backward_frame_indices(
        241,
        config.frame_search_interval,
        config.max_candidate_frames,
        config.frame_rate,
        config.max_state_age_seconds,
    )

    assert limited is False
    assert 235 in planned  # approximately 0.2s before the segment end
    assert 219 in planned  # approximately 0.9s before the segment end
    assert 211 not in planned  # approximately 1.2s before the segment end


def test_older_identity_perfect_candidate_cannot_override_recency_window(
    tmp_path,
    monkeypatch,
):
    registry = _registry("amy")
    video_path, extracted, frame_count_fn, frame_extractor = _frame_functions(
        tmp_path,
        frame_count=241,
    )
    seen_frames = []

    def detect(frame, registry, **_kwargs):
        frame_index = frame.getpixel((0, 0))[0]
        seen_frames.append(frame_index)
        candidates = (_candidate(0, frame_index),) if frame_index == 211 else ()
        return {"woman": SharedQueryCandidates(
            dino_query="woman",
            subject_keys=tuple(registry),
            candidates=candidates,
        )}

    def build(shared, registry, **_kwargs):
        candidates = shared["woman"].candidates
        return {"woman": _matrix(
            tuple(registry),
            candidates,
            {"amy": [0.99] if candidates else []},
        )}

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)

    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=500,
            max_state_age_seconds=1.0,
            crop_padding_x=0,
            crop_padding_y=0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )["amy"]

    assert result.updated is False
    assert min(extracted) >= 216
    assert 211 not in seen_frames


def test_no_match_preserves_previous_current_state(tmp_path, monkeypatch):
    registry = _registry("amy")
    previous = tmp_path / "previous.png"
    Image.new("RGB", (8, 8), "blue").save(previous)
    registry.update_current_state("amy", previous)
    video_path, _extracted, frame_count_fn, frame_extractor = _frame_functions(
        tmp_path,
        frame_count=241,
    )

    def detect(_frame, registry, **_kwargs):
        return {"woman": SharedQueryCandidates(
            dino_query="woman",
            subject_keys=tuple(registry),
            candidates=(),
        )}

    def build(shared, registry, **_kwargs):
        return {"woman": _matrix(tuple(registry), (), {"amy": []})}

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)

    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=500,
            max_state_age_seconds=1.0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )["amy"]

    assert result.updated is False
    assert registry["amy"]["current_state_reference"] == str(previous)
    assert previous.read_bytes() == (tmp_path / "previous.png").read_bytes()


def test_no_match_without_previous_state_leaves_reference_absent(tmp_path, monkeypatch):
    registry = _registry("amy")
    video_path, _extracted, frame_count_fn, frame_extractor = _frame_functions(
        tmp_path,
        frame_count=241,
    )

    monkeypatch.setattr(
        dino_continuity,
        "detect_shared_candidates",
        lambda _frame, registry, **_kwargs: {
            "woman": SharedQueryCandidates(
                dino_query="woman",
                subject_keys=tuple(registry),
                candidates=(),
            )
        },
    )
    monkeypatch.setattr(
        dino_continuity,
        "build_identity_score_matrix",
        lambda shared, registry, **_kwargs: {
            "woman": _matrix(tuple(registry), (), {"amy": []})
        },
    )

    search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=500,
            max_state_age_seconds=1.0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )

    assert registry["amy"].get("current_state_reference") is None


def test_max_candidate_frames_cannot_extend_past_recency_boundary():
    config = ContinuityReferenceConfig(
        frame_search_interval=1,
        max_candidate_frames=500,
        max_state_age_seconds=1.0,
    )
    planned, limited = _backward_frame_indices(
        241,
        config.frame_search_interval,
        2,
        config.frame_rate,
        config.max_state_age_seconds,
    )

    assert planned == (240, 239)
    assert limited is True
    assert all(frame >= 217 for frame in planned)


def test_longer_segment_does_not_create_wider_temporal_search():
    config = ContinuityReferenceConfig(
        frame_search_interval=1,
        max_candidate_frames=500,
        max_state_age_seconds=1.0,
    )
    short, _ = _backward_frame_indices(121, 1, 500, 24, 1.0)
    long, _ = _backward_frame_indices(241, 1, 500, 24, 1.0)

    assert len(short) == 25
    assert len(long) == 25


def test_step7_rejects_stale_reused_evidence(tmp_path):
    registry = SubjectRegistry()
    registry.register(
        "Amy",
        name="Amy",
        dino_query="woman",
        identity_backend="insightface",
        canonical_reference=Image.new("RGB", (8, 8), "white"),
    )
    stale = _candidate(0, 211)
    extracted = []

    def frame_count(_video_path):
        return 241

    def extract(_video_path, frame_name, input_directory, frame_index, **_kwargs):
        extracted.append(frame_index)
        image = Image.new("RGB", (20, 20), (frame_index, 0, 0))
        image.save(Path(input_directory) / frame_name)
        return frame_name

    class EmptyDetector:
        def detect(self, *_args, **_kwargs):
            return SimpleNamespace(detections=[])

    result = resolve_unresolved_subjects_with_vision(
        "segment.mp4",
        registry,
        ("Amy",),
        {"Amy": SubjectReferenceUpdateResult(
            subject_key="Amy",
            updated=False,
            status="not_found_in_segment",
            dino_query="woman",
            identity_backend="insightface",
        )},
        tmp_path / "references",
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=500,
            max_state_age_seconds=1.0,
        ),
        fallback_evidence={"woman": [stale]},
        frame_count_fn=frame_count,
        frame_extractor=extract,
        detector=EmptyDetector(),
    )["Amy"]

    assert result.updated is False
    assert result.status == "vision_fallback_no_candidates"
    assert extracted
    assert min(extracted) >= 216
    assert 211 not in extracted


def test_newer_valid_match_wins_without_searching_older_frames(tmp_path, monkeypatch):
    registry = _registry("amy")
    video_path, extracted, frame_count_fn, frame_extractor = _frame_functions(tmp_path)
    detector_calls = []
    current_frame = {"value": None}

    def detect(frame, registry, **_kwargs):
        query = "woman"
        current_frame["value"] = frame.getpixel((0, 0))[0]
        detector_calls.append((current_frame["value"], query, tuple(registry)))
        candidate = _candidate(0, current_frame["value"])
        return {query: SharedQueryCandidates(
            dino_query=query,
            subject_keys=tuple(registry),
            candidates=(candidate,),
        )}

    def build(shared, registry, **_kwargs):
        score = 0.62 if current_frame["value"] == 2 else 0.96
        return {"woman": _matrix(tuple(registry), shared["woman"].candidates, {"amy": [score]})}

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)

    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=10,
            crop_padding_x=0,
            crop_padding_y=0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )["amy"]

    assert isinstance(result, SubjectReferenceUpdateResult)
    assert result.updated is True
    assert result.frame_index == 2
    assert result.identity_similarity == 0.62
    assert extracted == [2]
    assert [call[0] for call in detector_calls] == [2]
    with Image.open(result.output_path) as saved:
        assert saved.getpixel((0, 0)) == (2, 0, 0)


def test_successful_match_saves_crop_with_segment_subject_and_frame(
    tmp_path,
    monkeypatch,
):
    registry = _registry("amy")
    registry["amy"]["subject_id"] = 1
    video_path, _extracted, frame_count_fn, frame_extractor = _frame_functions(tmp_path)
    current_frame = {"value": None}

    def detect(frame, registry, **_kwargs):
        query = "woman"
        current_frame["value"] = frame.getpixel((0, 0))[0]
        candidate = _candidate(0, current_frame["value"])
        return {query: SharedQueryCandidates(
            dino_query=query,
            subject_keys=tuple(registry),
            candidates=(candidate,),
        )}

    def build(shared, registry, **_kwargs):
        return {"woman": _matrix(
            tuple(registry),
            shared["woman"].candidates,
            {"amy": [0.9]},
        )}

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)

    vision_directory = tmp_path / "videos" / "vision_frames"
    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=10,
            crop_padding_x=0,
            crop_padding_y=0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
        segment_number=7,
        vision_frame_output_directory=vision_directory,
    )["amy"]

    expected = vision_directory / (
        "segment_0007_subject_0001_frame_00000002.png"
    )
    assert result.vision_frame_path == str(expected.resolve())
    with Image.open(expected) as saved:
        assert saved.size == (12, 12)
        assert saved.getpixel((0, 0)) == (2, 0, 0)


def test_resolved_subject_remains_in_later_shared_identity_context(tmp_path, monkeypatch):
    registry = _registry("amy", "beth", "claire")
    video_path, _extracted, frame_count_fn, frame_extractor = _frame_functions(tmp_path)
    current_frame = {"value": None}
    matrix_contexts = []

    def detect(frame, registry, **_kwargs):
        query = "woman"
        current_frame["value"] = frame.getpixel((0, 0))[0]
        count = 2 if current_frame["value"] == 1 else 1
        candidates = tuple(_candidate(index, current_frame["value"]) for index in range(count))
        return {query: SharedQueryCandidates(
            dino_query=query,
            subject_keys=tuple(registry),
            candidates=candidates,
        )}

    def build(shared, registry, **_kwargs):
        keys = tuple(registry)
        matrix_contexts.append(keys)
        candidates = shared["woman"].candidates
        if current_frame["value"] == 2:
            values = {
                "amy": [0.9], "beth": [0.2], "claire": [0.2],
            }
        elif current_frame["value"] == 1:
            values = {
                "amy": [0.9, 0.1],
                "beth": [0.85, 0.2],
                "claire": [0.1, 0.9],
            }
        else:
            values = {
                "amy": [0.9], "beth": [0.85], "claire": [0.2],
            }
        return {"woman": _matrix(keys, candidates, values)}

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)

    results = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(
            frame_search_interval=1,
            max_candidate_frames=10,
            crop_padding_x=0,
            crop_padding_y=0,
        ),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )

    assert matrix_contexts[0] == ("amy", "beth", "claire")
    # Amy is already resolved, but remains in the later matrix with Beth and
    # Claire; only unresolved subjects are eligible to commit.
    assert matrix_contexts[1] == ("amy", "beth", "claire")
    assert results["amy"].frame_index == 2
    assert results["claire"].frame_index == 1
    assert results["beth"].updated is False
    assert results["beth"].status == "not_found_in_segment"


def test_unsupported_backend_is_deferred_without_detection(tmp_path, monkeypatch):
    registry = _registry("robot", backend="future_backend")
    video_path, extracted, frame_count_fn, frame_extractor = _frame_functions(tmp_path)
    calls = []

    def detect(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("unsupported subject must not reach DINO")

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        config=ContinuityReferenceConfig(max_candidate_frames=2),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )["robot"]

    assert result.status == "identity_backend_unavailable"
    assert result.updated is False
    assert calls == []
    assert extracted == []


def test_staged_save_failure_preserves_existing_current_state(tmp_path, monkeypatch):
    registry = _registry("amy")
    old_path = Path(registry.current_state_path("amy", tmp_path / "references"))
    old_path.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "blue").save(old_path)
    old_bytes = old_path.read_bytes()
    video_path, _extracted, frame_count_fn, frame_extractor = _frame_functions(tmp_path)

    candidate = _candidate(0, 2)

    def detect(frame, registry, **_kwargs):
        query = "woman"
        return {query: SharedQueryCandidates(
            dino_query=query,
            subject_keys=tuple(registry),
            candidates=(candidate,),
        )}

    def build(shared, registry, **_kwargs):
        return {"woman": _matrix(("amy",), (candidate,), {"amy": [0.9]})}

    def fail_save(*_args, **_kwargs):
        raise OSError("cannot stage image")

    monkeypatch.setattr(dino_continuity, "detect_shared_candidates", detect)
    monkeypatch.setattr(dino_continuity, "build_identity_score_matrix", build)
    monkeypatch.setattr(dino_continuity, "_save_crop_atomically", fail_save)

    result = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        detector=object(),
        identity_validator=object(),
        config=ContinuityReferenceConfig(max_candidate_frames=1),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
    )["amy"]

    assert result.status == "current_state_save_failed"
    assert result.updated is False
    assert old_path.read_bytes() == old_bytes
    assert registry["amy"].get("current_state_reference") is None


def test_step6_resolves_stable_id_against_name_mapping_key(tmp_path):
    registry = _stable_id_registry("Amy")
    video_path, extracted, frame_count_fn, frame_extractor = _frame_functions(
        tmp_path,
        frame_count=1,
    )

    results = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        config=ContinuityReferenceConfig(max_candidate_frames=1),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
        update_subject_keys=(1,),
        identity_context_subject_keys=(1,),
    )

    assert tuple(results) == ("Amy",)
    assert results["Amy"].status == "identity_backend_unavailable"
    assert extracted == []


def test_step6_resolves_multiple_stable_ids_against_name_mapping_keys(tmp_path):
    registry = _stable_id_registry("Amy", "Beth")
    video_path, extracted, frame_count_fn, frame_extractor = _frame_functions(
        tmp_path,
        frame_count=1,
    )

    results = search_and_update_current_states(
        video_path,
        registry,
        tmp_path / "references",
        config=ContinuityReferenceConfig(max_candidate_frames=1),
        frame_count_fn=frame_count_fn,
        frame_extractor=frame_extractor,
        update_subject_keys=(1, 2),
        identity_context_subject_keys=(1, 2),
    )

    assert tuple(results) == ("Amy", "Beth")
    assert all(
        result.status == "identity_backend_unavailable"
        for result in results.values()
    )
    assert extracted == []


def test_step7_resolves_expected_stable_id_against_name_mapping_key(tmp_path):
    registry = _stable_id_registry("Amy")
    video_path, _extracted, _frame_count_fn, _frame_extractor = _frame_functions(
        tmp_path,
        frame_count=1,
    )
    step6_result = SubjectReferenceUpdateResult(
        subject_key="Amy",
        updated=True,
        status="updated",
        dino_query="woman",
        identity_backend="future_backend",
    )

    results = resolve_unresolved_subjects_with_vision(
        video_path,
        registry,
        (1,),
        {"Amy": step6_result},
        tmp_path / "references",
    )

    assert tuple(results) == ("Amy",)
    assert results["Amy"].updated is True
