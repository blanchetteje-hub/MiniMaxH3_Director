from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import minimax

from dino_continuity import (
    ContinuityReferenceConfig,
    search_and_save_reference,
    update_subject_references,
)
from identity_validator import IdentitySelectionResult, IdentityValidator

FIXTURE_DIR = Path(__file__).parent


class FakeDetector:
    def __init__(self, detections_by_frame):
        self.detections_by_frame = detections_by_frame
        self.calls = []

    def detect(self, image, query, box_threshold, text_threshold):
        frame_index = image.getpixel((0, 0))[0]
        self.calls.append((frame_index, query, box_threshold, text_threshold))
        return SimpleNamespace(
            detections=self.detections_by_frame.get(frame_index, [])
        )


class FakeIdentityValidator:
    def __init__(self, matched=True, candidate_index=1, reason="identity_match"):
        self.matched = matched
        self.candidate_index = candidate_index
        self.reason = reason
        self.prepare_calls = []
        self.selection_calls = []

    def prepare_canonical(self, subject, reference):
        self.prepare_calls.append((subject, reference))
        return SimpleNamespace(
            matched=True,
            reason="canonical_loaded",
            to_dict=lambda: {"reason": "canonical_loaded"},
        )

    def select_candidate(
        self,
        subject,
        reference,
        candidates,
        identity_threshold,
        identity_margin,
    ):
        self.selection_calls.append((subject, reference, tuple(candidates)))
        selected = next(
            (item for item in candidates if item.candidate_index == self.candidate_index),
            candidates[0],
        )
        return IdentitySelectionResult(
            evaluated=True,
            matched=self.matched,
            reason=self.reason,
            canonical_subject=subject,
            identity_similarity=0.82 if self.matched else 0.22,
            identity_threshold=identity_threshold,
            identity_margin=identity_margin,
            candidate_index=selected.candidate_index,
            face_bbox=[20, 10, 40, 40],
            candidates=tuple(),
        )


def detection(confidence, bbox, phrase="woman"):
    return SimpleNamespace(
        confidence=confidence,
        bbox=bbox,
        matched_phrase=phrase,
    )


def marked_image(marker):
    image = Image.new("RGB", (100, 80), "black")
    image.putpixel((0, 0), (marker, 0, 0))
    return image


def run_search(
    tmp_path,
    detections_by_frame,
    config=None,
    fixture_name="sadie.jpg",
    identity_validator=None,
    canonical_reference=None,
):
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")
    output_path = tmp_path / "Amy_current.png"
    detector = FakeDetector(detections_by_frame)

    def frame_count(_video_path):
        return 25

    def extract_frame(_video_path, frame_name, input_directory, frame_index, **_kwargs):
        with Image.open(FIXTURE_DIR / fixture_name) as fixture:
            image = fixture.convert("RGB").resize((100, 80))
        image.putpixel((0, 0), (frame_index % 255, 0, 0))
        image.save(Path(input_directory) / frame_name)
        return frame_name

    result = search_and_save_reference(
        str(video_path),
        "woman",
        str(output_path),
        detector=detector,
        config=config or ContinuityReferenceConfig(
            frame_search_interval=5,
            max_candidate_frames=4,
        ),
        frame_count_fn=frame_count,
        frame_extractor=extract_frame,
        identity_validator=identity_validator,
        canonical_reference=canonical_reference,
        subject_identifier="Amy",
    )
    return result, output_path, detector


def test_newest_usable_candidate_wins_over_older_higher_confidence(tmp_path):
    result, output_path, detector = run_search(
        tmp_path,
        {
            24: [detection(0.81, [20, 10, 60, 70])],
            19: [detection(0.99, [10, 5, 80, 75])],
        },
        fixture_name="sadie.jpg",
    )

    assert result.found is True
    assert result.reason == "accepted"
    assert result.frame_index == 24
    assert result.confidence == 0.81
    assert result.image_width == 100
    assert result.image_height == 80
    assert result.bbox_width == 40
    assert result.bbox_height == 60
    assert detector.calls == [(24, "woman", 0.35, 0.25)]
    assert output_path.is_file()


def test_no_woman_returns_no_detection_failure(tmp_path):
    result, output_path, _ = run_search(tmp_path, {}, fixture_name="test1.png")

    assert result.found is False
    assert result.ambiguous is False
    assert result.reason == "no_detection"
    assert not output_path.exists()


def test_detection_below_default_confidence_is_rejected(tmp_path):
    result, output_path, _ = run_search(
        tmp_path,
        {24: [detection(0.79, [10, 10, 80, 70])]},
        fixture_name="test2.png",
    )

    assert result.found is False
    assert result.reason == "below_confidence_threshold"
    assert not output_path.exists()


def test_two_high_confidence_women_are_ambiguous(tmp_path):
    result, output_path, _ = run_search(
        tmp_path,
        {
            24: [
                detection(0.91, [10, 10, 40, 70]),
                detection(0.88, [55, 10, 90, 70]),
            ]
        },
        fixture_name="test2.png",
    )

    assert result.found is False
    assert result.ambiguous is True
    assert result.reason == "multiple_matching_subjects"
    assert not output_path.exists()


def test_edge_bbox_is_reported_and_padding_is_clamped(tmp_path):
    result, output_path, _ = run_search(
        tmp_path,
        {24: [detection(0.90, [0, 0, 20, 30])]},
        ContinuityReferenceConfig(
            frame_search_interval=5,
            max_candidate_frames=1,
            crop_padding_x=0.20,
            crop_padding_y=0.20,
        ),
        fixture_name="test3.png",
    )

    assert result.found is True
    assert result.bbox == [0, 0, 20, 30]
    assert result.crop_bbox == [0, 0, 24, 36]
    assert result.touches_frame_edge is True
    assert result.crop_width == 24
    assert result.crop_height == 36
    with Image.open(output_path) as image:
        assert image.size == (24, 36)


def test_bottom_right_bbox_padding_is_clamped(tmp_path):
    result, output_path, _ = run_search(
        tmp_path,
        {24: [detection(0.90, [80, 50, 100, 80])]},
        ContinuityReferenceConfig(
            frame_search_interval=5,
            max_candidate_frames=1,
            crop_padding_x=0.20,
            crop_padding_y=0.20,
        ),
        fixture_name="test1.png",
    )

    assert result.found is True
    assert result.crop_bbox == [76, 44, 100, 80]
    assert result.touches_frame_edge is True
    with Image.open(output_path) as image:
        assert image.size == (24, 36)


def test_identity_selects_candidate_by_similarity_not_dino_confidence(tmp_path):
    identity = FakeIdentityValidator(matched=True, candidate_index=1)
    result, output_path, _ = run_search(
        tmp_path,
        {
            24: [
                detection(0.99, [5, 5, 45, 75]),
                detection(0.81, [55, 5, 95, 75]),
            ]
        },
        config=ContinuityReferenceConfig(
            frame_search_interval=5,
            max_candidate_frames=1,
            identity_confidence=0.48,
            identity_margin=0.05,
        ),
        identity_validator=identity,
        canonical_reference="sadie.jpg",
    )

    assert result.found is True
    assert result.identity_status == "identity_match"
    assert result.identity_candidate_index == 1
    assert result.confidence == 0.81
    assert output_path.is_file()
    assert identity.prepare_calls == [("Amy", "sadie.jpg")]
    assert len(identity.selection_calls) == 1


def test_identity_mismatch_preserves_existing_reference(tmp_path):
    identity = FakeIdentityValidator(
        matched=False,
        candidate_index=0,
        reason="identity_mismatch",
    )
    output_path = tmp_path / "Amy_current.png"
    previous_bytes = b"previous-valid-reference"
    output_path.write_bytes(previous_bytes)

    result, _, _ = run_search(
        tmp_path,
        {24: [detection(0.91, [10, 10, 90, 70])]},
        identity_validator=identity,
        canonical_reference="sadie.jpg",
    )

    assert result.found is False
    assert result.reason == "identity_mismatch"
    assert output_path.read_bytes() == previous_bytes


def test_shared_query_runs_dino_once_and_updates_subjects_independently(tmp_path):
    video_path = tmp_path / "segment.mp4"
    video_path.write_bytes(b"video")
    class SharedDetector:
        def __init__(self):
            self.calls = []

        def detect(self, image, query, box_threshold, text_threshold):
            self.calls.append((image.getpixel((0, 0))[0], query, box_threshold, text_threshold))
            return SimpleNamespace(detections=[
                detection(0.91, [0, 0, 50, 80]),
                detection(0.89, [50, 0, 100, 80]),
            ])

    detector = SharedDetector()
    identity_backend = FakeDetector({})
    identity_backend.get = lambda image: [SimpleNamespace(
        bbox=[10, 10, 40, 60],
        embedding=(
            [1, 0]
            if image[0, 0, 2] in {1, 10}
            else [0, 1]
        ),
    )]
    identity = IdentityValidator(backend=identity_backend)
    canonical_amy = marked_image(10)
    canonical_beth = marked_image(20)

    def frame_count(_video_path):
        return 1

    def extract_frame(_video_path, frame_name, input_directory, **_kwargs):
        image = Image.new("RGB", (100, 80), "black")
        image.putpixel((0, 0), (1, 0, 0))
        image.putpixel((50, 0), (2, 0, 0))
        image.save(Path(input_directory) / frame_name)
        return frame_name

    results = update_subject_references(
        str(video_path),
        {
            "amy": {
                "name": "amy",
                "gender": "female",
                "canonical_reference": canonical_amy,
            },
            "beth": {
                "name": "beth",
                "gender": "female",
                "canonical_reference": canonical_beth,
            },
        },
        str(tmp_path / "references"),
        detector=detector,
        identity_validator=identity,
        config=ContinuityReferenceConfig(
            crop_padding_x=0,
            crop_padding_y=0,
            max_candidate_frames=1,
        ),
        frame_count_fn=frame_count,
        frame_extractor=extract_frame,
    )

    assert detector.calls == [(1, "woman", 0.35, 0.25)]
    assert results["amy"].found is True
    assert results["amy"].identity_candidate_index == 0
    assert results["beth"].found is True
    assert results["beth"].identity_candidate_index == 1
    assert Path(results["amy"].output_path).is_file()
    assert Path(results["beth"].output_path).is_file()


def test_tiny_distant_subject_is_rejected(tmp_path):
    result, output_path, _ = run_search(
        tmp_path,
        {24: [detection(0.90, [40, 30, 45, 35])]},
        fixture_name="test1.png",
    )

    assert result.found is False
    assert result.reason == "subject_too_small"
    assert not output_path.exists()


def test_failed_search_preserves_previous_current_reference(tmp_path):
    result, output_path, _ = run_search(tmp_path, {}, fixture_name="sadie.jpg")
    assert result.found is False

    previous_bytes = b"previous-valid-reference"
    output_path.write_bytes(previous_bytes)
    result, _, _ = run_search(tmp_path, {}, fixture_name="test3.png")

    assert result.found is False
    assert output_path.read_bytes() == previous_bytes


def test_minimax_exposes_separate_dino_configuration_values():
    args = minimax.parse_args([
        "5",
        "20",
        ".5",
        "--dino-confidence",
        ".86",
        "--dino-box-threshold",
        ".31",
        "--dino-text-threshold",
        ".21",
        "--dino-frame-interval",
        "6",
        "--dino-max-candidates",
        "9",
        "--dino-crop-padding-x",
        ".14",
        "--dino-crop-padding-y",
        ".11",
        "--dino-min-bbox-area-ratio",
        ".02",
    ])

    assert args.dino_confidence == 0.86
    assert args.dino_box_threshold == 0.31
    assert args.dino_text_threshold == 0.21
    assert args.dino_frame_interval == 6
    assert args.dino_max_candidates == 9
    assert args.dino_crop_padding_x == 0.14
    assert args.dino_crop_padding_y == 0.11
    assert args.dino_min_bbox_area_ratio == 0.02


def test_minimax_can_skip_dino_entirely():
    args = minimax.parse_args(["5", "20", ".5", "--dino-skip"])

    assert args.dino_skip is True


def test_minimax_exposes_identity_threshold_margin_and_reference_mapping():
    args = minimax.parse_args([
        "5",
        "20",
        ".5",
        "--identity-confidence",
        ".52",
        "--identity-margin",
        ".07",
        "--identity-reference",
        "Amy=/tmp/Amy.jpg",
    ])

    assert args.identity_confidence == 0.52
    assert args.identity_margin == 0.07
    assert args.identity_reference == ["Amy=/tmp/Amy.jpg"]
