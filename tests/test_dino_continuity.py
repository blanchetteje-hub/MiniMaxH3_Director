from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import minimax

from dino_continuity import (
    ContinuityReferenceConfig,
    search_and_save_reference,
)

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


def detection(confidence, bbox, phrase="woman"):
    return SimpleNamespace(
        confidence=confidence,
        bbox=bbox,
        matched_phrase=phrase,
    )


def run_search(tmp_path, detections_by_frame, config=None, fixture_name="sadie.jpg"):
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
