"""Opt-in integration tests that execute the real Grounding DINO backend.

These tests intentionally are not part of the fast fake-backend unit tests.
Run them with:

    RUN_REAL_DINO_TESTS=1 python -m pytest -m real_dino -s

The detector may download its configured model files on the first run. The
tests use ``sadie.jpg`` as the canonical reference passed to the future
identity hook, but do not compare image identity yet.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from dino_continuity import ContinuityReferenceConfig, search_and_save_reference
from dino_detector import GroundingDINOError, get_detector


pytestmark = pytest.mark.real_dino

FIXTURE_DIR = Path(__file__).parent
IMAGE_NAMES = ("sadie.jpg", "test1.png", "test2.png", "test3.png")

if os.environ.get("RUN_REAL_DINO_TESTS") != "1":
    pytest.skip(
        "set RUN_REAL_DINO_TESTS=1 to run real Grounding DINO inference",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def real_detector():
    """Load one real detector for all image cases in this module."""

    detector = get_detector(
        device=os.environ.get("DINO_TEST_DEVICE", "cpu"),
        auto_download=True,
    )
    try:
        # Force lazy model initialization here so missing optional runtime
        # dependencies produce a clear integration-test skip.
        detector.detect(FIXTURE_DIR / "sadie.jpg", "woman")
    except (FileNotFoundError, GroundingDINOError, ImportError, OSError, RuntimeError) as error:
        pytest.skip(f"real Grounding DINO runtime unavailable: {error}")
    return detector


@pytest.mark.parametrize("image_name", IMAGE_NAMES)
def test_real_grounding_dino_scores_woman_in_each_fixture(real_detector, image_name):
    """Run the actual model and expose each fixture's measured confidence."""

    result = real_detector.detect(
        FIXTURE_DIR / image_name,
        "woman",
        box_threshold=0.35,
        text_threshold=0.25,
    )

    assert result.found is True
    assert result.best_match is not None
    assert result.best_match == result.detections[0]
    assert 0.0 <= result.confidence <= 1.0
    assert result.matched_phrase
    assert result.image_width > 0
    assert result.image_height > 0
    print(
        f"{image_name}: confidence={result.confidence:.6f}, "
        f"detections={len(result.detections)}, "
        f"bbox={result.bbox}, phrase={result.matched_phrase}"
    )


@pytest.mark.parametrize(
    ("image_name", "expected_high_confidence"),
    (
        ("sadie.jpg", True),
        ("test1.png", False),
        ("test2.png", False),
        ("test3.png", True),
    ),
)
def test_real_high_confidence_path_uses_sadie_as_future_canonical_reference(
    real_detector,
    image_name,
    expected_high_confidence,
    tmp_path,
):
    """Exercise real DINO detection while keeping identity comparison disabled."""

    video_path = tmp_path / f"{image_name}.mp4"
    video_path.write_bytes(b"test video placeholder")
    output_path = tmp_path / f"{image_name}_current.png"
    canonical_reference = str(FIXTURE_DIR / "sadie.jpg")
    identity_calls = []

    def frame_count(_video_path):
        return 1

    def extract_frame(_video_path, frame_name, input_directory, **_kwargs):
        shutil.copyfile(
            FIXTURE_DIR / image_name,
            Path(input_directory) / frame_name,
        )
        return frame_name

    def identity_hook(candidate_crop, canonical):
        identity_calls.append((candidate_crop.size, canonical))
        return "not_evaluated"

    result = search_and_save_reference(
        str(video_path),
        "woman",
        str(output_path),
        detector=real_detector,
        config=ContinuityReferenceConfig(
            dino_confidence=0.80,
            box_threshold=0.35,
            text_threshold=0.25,
            max_candidate_frames=1,
        ),
        frame_count_fn=frame_count,
        frame_extractor=extract_frame,
        identity_validator=identity_hook,
        canonical_reference=canonical_reference,
    )

    assert result.found is expected_high_confidence
    if expected_high_confidence:
        assert result.confidence >= 0.80
        assert result.output_path == str(output_path.resolve())
        assert output_path.is_file()
        assert len(identity_calls) == 1
        assert identity_calls[0][1] == canonical_reference
    else:
        assert result.reason == "below_confidence_threshold"
        assert not output_path.exists()
        assert identity_calls == []
