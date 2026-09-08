"""Opt-in real InsightFace/ArcFace tests.

Run with:

    RUN_REAL_IDENTITY_TESTS=1 python -m pytest -m real_identity -s -q

InsightFace downloads the selected model pack lazily if it is not already in
its local cache. These tests avoid exact floating-point assertions because
provider/model versions can change the scores slightly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from identity_validator import (
    IdentityCandidate,
    IdentityModelError,
    IdentityValidator,
)


pytestmark = pytest.mark.real_identity
FIXTURE_DIR = Path(__file__).parent

if os.environ.get("RUN_REAL_IDENTITY_TESTS") != "1":
    pytest.skip(
        "set RUN_REAL_IDENTITY_TESTS=1 to run real InsightFace inference",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def real_identity_validator():
    validator = IdentityValidator(
        model_name=os.environ.get("IDENTITY_TEST_MODEL", "buffalo_l"),
        root=os.environ.get("INSIGHTFACE_MODEL_ROOT"),
    )
    try:
        canonical = validator.prepare_canonical(
            "Amy",
            FIXTURE_DIR / "sadie.jpg",
        )
    except (FileNotFoundError, IdentityModelError, ImportError, OSError, RuntimeError) as error:
        pytest.skip(f"real InsightFace runtime unavailable: {error}")
    if not canonical.matched:
        pytest.skip(f"canonical reference was not usable: {canonical.reason}")
    return validator


def _candidate(image_name, index=0):
    from PIL import Image

    with Image.open(FIXTURE_DIR / image_name) as opened:
        image = opened.convert("RGB")
    return IdentityCandidate(
        candidate_index=index,
        image=image,
        dino_confidence=0.9,
        bbox=[0, 0, image.width, image.height],
        crop_bbox=[0, 0, image.width, image.height],
    )


def test_real_canonical_reference_produces_one_embedding(real_identity_validator):
    result = real_identity_validator.prepare_canonical(
        "Amy",
        FIXTURE_DIR / "sadie.jpg",
    )

    assert result.matched is True
    assert result.reason == "canonical_loaded"
    assert result.face_bbox is not None


def test_real_canonical_image_scores_above_unrelated_fixture(real_identity_validator):
    same_image = real_identity_validator.select_candidate(
        "Amy",
        FIXTURE_DIR / "sadie.jpg",
        [_candidate("sadie.jpg")],
    )
    unrelated = real_identity_validator.select_candidate(
        "Amy",
        FIXTURE_DIR / "sadie.jpg",
        [_candidate("test3.png")],
    )

    assert same_image.evaluated is True
    assert same_image.identity_similarity is not None
    assert unrelated.identity_similarity is not None
    assert same_image.identity_similarity > unrelated.identity_similarity
    print(
        f"sadie.jpg similarity={same_image.identity_similarity:.6f}; "
        f"test3.png similarity={unrelated.identity_similarity:.6f}"
    )
