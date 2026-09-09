from types import SimpleNamespace

from PIL import Image

from dino_continuity import (
    ContinuityReferenceConfig,
    detect_shared_candidates,
)
from subject_registry import SubjectRegistry


def detection(confidence, bbox, phrase="woman"):
    return SimpleNamespace(
        confidence=confidence,
        bbox=bbox,
        normalized_bbox=[0.0, 0.0, 1.0, 1.0],
        matched_phrase=phrase,
    )


def registry_with_queries(*queries):
    registry = SubjectRegistry()
    for index, query in enumerate(queries, start=1):
        registry.register(
            f"subject-{index}",
            registry_key=f"subject-{index}",
            name=f"Subject {index}",
            dino_query=query,
            current_state_reference=f"subject-{index}_current.png",
        )
    return registry


class MockDetector:
    def __init__(self, detections_by_query=None):
        self.detections_by_query = detections_by_query or {}
        self.calls = []

    def detect(self, image, query, box_threshold, text_threshold):
        self.calls.append((image.size, query, box_threshold, text_threshold))
        return SimpleNamespace(
            detections=self.detections_by_query.get(query, []),
        )


def test_shared_query_is_detected_once_for_all_registry_subjects():
    registry = registry_with_queries("woman", "woman", "woman")
    detector = MockDetector({
        "woman": [detection(0.93, [10, 10, 60, 90]), detection(0.91, [70, 5, 120, 95])],
    })

    result = detect_shared_candidates(
        Image.new("RGB", (160, 100)),
        registry,
        detector=detector,
    )

    assert list(result) == ["woman"]
    assert detector.calls == [(
        (160, 100),
        "woman",
        0.35,
        0.25,
    )]
    assert result["woman"].subject_keys == (
        "subject-1",
        "subject-2",
        "subject-3",
    )
    assert [item.candidate_index for item in result["woman"].candidates] == [0, 1]


def test_shared_detection_reports_query_and_candidate_activity(capsys):
    registry = registry_with_queries("woman")
    detector = MockDetector({
        "woman": [detection(0.93, [10, 10, 60, 90])],
    })

    detect_shared_candidates(
        Image.new("RGB", (160, 100)),
        registry,
        detector=detector,
        source_metadata={"frame_index": 17},
    )

    output = capsys.readouterr().out
    assert "Step 3: shared detection start" in output
    assert "query='woman' raw=1 accepted=1" in output
    assert "candidate query='woman' index=0" in output


def test_different_queries_each_run_once_and_share_no_subject_assignment():
    registry = registry_with_queries("woman", "woman", "werewolf")
    detector = MockDetector({
        "woman": [detection(0.93, [10, 10, 60, 90])],
        "werewolf": [detection(0.88, [80, 10, 150, 95], "werewolf")],
    })

    result = detect_shared_candidates(
        Image.new("RGB", (160, 100)),
        registry,
        detector=detector,
    )

    assert [call[1] for call in detector.calls] == ["woman", "werewolf"]
    assert result["woman"].subject_keys == ("subject-1", "subject-2")
    assert result["werewolf"].subject_keys == ("subject-3",)
    assert all(
        "subject_key" not in candidate.to_dict()
        and "subject_id" not in candidate.to_dict()
        for group in result.values()
        for candidate in group.candidates
    )


def test_threshold_and_minimum_area_rejections_are_separate_from_candidates():
    registry = registry_with_queries("woman")
    detector = MockDetector({
        "woman": [
            detection(0.79, [0, 0, 100, 100]),
            detection(0.95, [1, 1, 3, 3]),
            detection(0.92, [20, 10, 80, 90]),
        ],
    })

    result = detect_shared_candidates(
        Image.new("RGB", (100, 100)),
        registry,
        detector=detector,
    )
    group = result["woman"]

    assert len(group.raw_detections) == 3
    assert len(group.candidates) == 1
    assert group.candidates[0].candidate_index == 0
    assert {item["reason"] for item in group.rejections} == {
        "below_confidence_threshold",
        "subject_too_small",
    }


def test_candidate_crop_is_proportionally_padded_and_edge_clamped():
    registry = registry_with_queries("woman")
    detector = MockDetector({
        "woman": [detection(0.90, [0, 0, 20, 30])],
    })

    result = detect_shared_candidates(
        Image.new("RGB", (100, 80)),
        registry,
        detector=detector,
        config=ContinuityReferenceConfig(
            crop_padding_x=0.20,
            crop_padding_y=0.20,
        ),
        source_metadata={"frame_index": 17},
    )
    candidate = result["woman"].candidates[0]

    assert candidate.bbox == [0, 0, 20, 30]
    assert candidate.crop_bbox == [0, 0, 24, 36]
    assert candidate.crop.size == (24, 36)
    assert candidate.touches_frame_edge is True
    assert candidate.source_metadata["frame_index"] == 17
    assert candidate.source_metadata["detection_index"] == 0
    assert candidate.crop_bbox[0] <= candidate.bbox[0]
    assert candidate.crop_bbox[1] <= candidate.bbox[1]
    assert candidate.crop_bbox[2] >= candidate.bbox[2]
    assert candidate.crop_bbox[3] >= candidate.bbox[3]


def test_detection_does_not_mutate_registry_current_state_references():
    registry = registry_with_queries("woman", "woman")
    before = {
        key: dict(record)
        for key, record in registry.items()
    }
    detector = MockDetector({
        "woman": [detection(0.90, [10, 10, 90, 90])],
    })

    detect_shared_candidates(
        Image.new("RGB", (100, 100)),
        registry,
        detector=detector,
    )

    assert {
        key: dict(record)
        for key, record in registry.items()
    } == before
