import logging
import sys
import types

import numpy as np
from PIL import Image

import identity_validator as identity_module
from identity_validator import (
    IdentityCandidate,
    IdentityValidator,
    compare_face_embeddings,
)


class FakeFace:
    def __init__(self, bbox, embedding, det_score=0.99):
        self.bbox = bbox
        self.embedding = np.asarray(embedding, dtype=np.float32)
        self.det_score = det_score


class FakeInsightBackend:
    def __init__(self, faces_by_marker):
        self.faces_by_marker = faces_by_marker
        self.calls = 0

    def get(self, image):
        self.calls += 1
        marker = int(image[0, 0, 2])
        return self.faces_by_marker.get(marker, [])


def image_with_marker(marker):
    image = Image.new("RGB", (100, 80), "black")
    image.putpixel((0, 0), (marker, 0, 0))
    return image


def candidate(index, marker, dino_confidence=0.9):
    return IdentityCandidate(
        candidate_index=index,
        image=image_with_marker(marker),
        dino_confidence=dino_confidence,
        bbox=[0, 0, 100, 80],
        crop_bbox=[0, 0, 100, 80],
    )


def make_validator(faces_by_marker):
    return IdentityValidator(
        backend=FakeInsightBackend(faces_by_marker),
        providers=("CPUExecutionProvider",),
    )


def test_cosine_similarity_normalizes_embeddings():
    assert compare_face_embeddings([2, 0], [1, 0]) == 1.0
    assert compare_face_embeddings([1, 0], [0, 1]) == 0.0


def test_default_validator_factory_is_lazy_and_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHTFACE_MODEL_ROOT", str(tmp_path))
    first = identity_module.get_identity_validator(model_name="test-model")
    second = identity_module.get_identity_validator(model_name="test-model")

    assert first is second
    assert first.loaded is False
    assert first.root == str(tmp_path)
    assert first.device == "cpu"


def test_default_identity_provider_path_does_not_probe_cuda(monkeypatch):
    events = []
    fake_onnxruntime = types.ModuleType("onnxruntime")
    fake_onnxruntime.get_available_providers = lambda: (
        events.append("providers")
        or ["CUDAExecutionProvider", "CPUExecutionProvider"]
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_onnxruntime)

    validator = IdentityValidator()
    assert validator._available_providers() == ["CPUExecutionProvider"]
    assert events == ["providers"]


def test_onnx_runtime_preloads_python_cuda_libraries_before_provider_discovery(
    monkeypatch,
    caplog,
):
    events = []
    fake_torch = types.ModuleType("torch")
    fake_torch.__version__ = "2.14.0+cu130"
    fake_torch.version = types.SimpleNamespace(cuda="13.0")
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: True)

    fake_onnxruntime = types.ModuleType("onnxruntime")
    fake_onnxruntime.__version__ = "1.29.0"

    def preload_dlls(*, directory):
        events.append(("preload_dlls", directory))

    def get_available_providers():
        events.append(("get_available_providers",))
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    fake_onnxruntime.preload_dlls = preload_dlls
    fake_onnxruntime.get_available_providers = get_available_providers
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_onnxruntime)
    caplog.set_level(logging.DEBUG, logger="identity_validator")

    providers = IdentityValidator(device="cuda")._available_providers()

    assert providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert events == [
        ("preload_dlls", ""),
        ("get_available_providers",),
    ]
    assert "torch=2.14.0+cu130" in caplog.text
    assert "torch_cuda=13.0" in caplog.text
    assert "torch.cuda.is_available=True" in caplog.text
    assert "onnxruntime=1.29.0" in caplog.text
    assert "CUDAExecutionProvider" in caplog.text


def test_canonical_embedding_is_cached_after_one_face_is_found():
    backend = FakeInsightBackend({0: [FakeFace([20, 10, 80, 70], [1, 0])]})
    validator = IdentityValidator(backend=backend)
    reference = image_with_marker(0)

    first = validator.prepare_canonical("Amy", reference)
    second = validator.prepare_canonical("Amy", reference)

    assert first.matched is True
    assert second == first
    assert backend.calls == 1


def test_canonical_zero_or_multiple_faces_are_explicit_failures():
    no_face = make_validator({0: []}).prepare_canonical("Amy", image_with_marker(0))
    multiple = make_validator({
        0: [
            FakeFace([10, 10, 40, 50], [1, 0]),
            FakeFace([50, 10, 90, 50], [0, 1]),
        ]
    }).prepare_canonical("Amy", image_with_marker(0))

    assert no_face.reason == "canonical_face_not_found"
    assert multiple.reason == "ambiguous_canonical_reference"


def test_identity_winner_can_differ_from_dino_confidence_winner():
    validator = make_validator({
        0: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [FakeFace([20, 10, 80, 70], [0.55, 0.835])],
        2: [FakeFace([20, 10, 80, 70], [0.85, 0.526])],
    })
    result = validator.select_candidate(
        "Amy",
        image_with_marker(0),
        [
            candidate(0, 1, dino_confidence=0.99),
            candidate(1, 2, dino_confidence=0.86),
        ],
        identity_threshold=0.48,
        identity_margin=0.05,
    )

    assert result.reason == "identity_match"
    assert result.candidate_index == 1
    assert result.identity_similarity < 1.0
    assert result.candidates[0].dino_confidence == 0.99


def test_below_threshold_is_identity_mismatch():
    validator = make_validator({
        0: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [FakeFace([20, 10, 80, 70], [0, 1])],
    })
    result = validator.select_candidate(
        "Amy",
        image_with_marker(0),
        [candidate(0, 1)],
        identity_threshold=0.48,
    )

    assert result.evaluated is True
    assert result.matched is False
    assert result.reason == "identity_mismatch"


def test_close_identity_scores_are_ambiguous():
    validator = make_validator({
        0: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [FakeFace([20, 10, 80, 70], [0.95, 0.312])],
        2: [FakeFace([20, 10, 80, 70], [0.94, 0.341])],
    })
    result = validator.select_candidate(
        "Amy",
        image_with_marker(0),
        [candidate(0, 1), candidate(1, 2)],
        identity_threshold=0.48,
        identity_margin=0.05,
    )

    assert result.reason == "ambiguous_identity"
    assert result.matched is False


def test_no_candidate_face_is_not_classified_as_identity_mismatch():
    validator = make_validator({
        0: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [],
    })
    result = validator.select_candidate(
        "Amy",
        image_with_marker(0),
        [candidate(0, 1)],
    )

    assert result.evaluated is False
    assert result.matched is False
    assert result.reason == "not_evaluated_no_face"


def test_multiple_candidate_faces_are_accepted_only_when_one_is_inside_person_bbox():
    validator = make_validator({
        0: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [
            FakeFace([25, 20, 50, 55], [1, 0]),
            FakeFace([90, 10, 120, 40], [0, 1]),
        ],
        2: [
            FakeFace([20, 20, 50, 55], [1, 0]),
            FakeFace([55, 20, 85, 55], [0, 1]),
        ],
    })
    canonical = image_with_marker(0)
    accepted = validator.select_candidate("Amy", canonical, [candidate(0, 1)])
    ambiguous = validator.select_candidate("Amy", canonical, [candidate(0, 2)])

    assert accepted.reason == "identity_match"
    assert ambiguous.reason == "ambiguous_candidate_faces"


def test_three_subjects_and_three_candidates_are_assigned_one_to_one():
    validator = make_validator({
        10: [FakeFace([20, 10, 80, 70], [1, 0])],
        20: [FakeFace([20, 10, 80, 70], [0, 1])],
        30: [FakeFace([20, 10, 80, 70], [-1, 0])],
        1: [FakeFace([20, 10, 80, 70], [1, 0])],
        2: [FakeFace([20, 10, 80, 70], [0, 1])],
        3: [FakeFace([20, 10, 80, 70], [-1, 0])],
    })
    result = validator.select_candidates_for_subjects(
        {
            "amy": image_with_marker(10),
            "beth": image_with_marker(20),
            "claire": image_with_marker(30),
        },
        [candidate(0, 1), candidate(1, 2), candidate(2, 3)],
    )

    assert {name: item.candidate_index for name, item in result.items()} == {
        "amy": 0,
        "beth": 1,
        "claire": 2,
    }
    assert all(item.reason == "identity_match" for item in result.values())


def test_one_candidate_cannot_be_owned_by_two_subjects():
    validator = make_validator({
        10: [FakeFace([20, 10, 80, 70], [1, 0])],
        20: [FakeFace([20, 10, 80, 70], [1, 0])],
        1: [FakeFace([20, 10, 80, 70], [1, 0])],
    })
    result = validator.select_candidates_for_subjects(
        {"amy": image_with_marker(10), "beth": image_with_marker(20)},
        [candidate(0, 1)],
    )

    assert sum(item.matched for item in result.values()) == 1
    assert result["amy"].candidate_index == 0
    assert result["beth"].reason == "candidate_already_assigned"


def test_wrong_unregistered_candidate_is_not_forced_onto_subject():
    validator = make_validator({
        10: [FakeFace([20, 10, 80, 70], [1, 0])],
        9: [FakeFace([20, 10, 80, 70], [0, 1])],
    })
    result = validator.select_candidates_for_subjects(
        {"amy": image_with_marker(10)},
        [candidate(0, 9)],
    )

    assert result["amy"].matched is False
    assert result["amy"].reason == "identity_mismatch"


def test_canonical_cache_is_independent_per_subject():
    backend = FakeInsightBackend({
        10: [FakeFace([20, 10, 80, 70], [1, 0])],
        20: [FakeFace([20, 10, 80, 70], [0, 1])],
    })
    validator = IdentityValidator(backend=backend)
    validator.prepare_canonical("amy", image_with_marker(10))
    validator.prepare_canonical("beth", image_with_marker(20))
    validator.prepare_canonical("amy", image_with_marker(10))
    validator.prepare_canonical("beth", image_with_marker(20))

    assert backend.calls == 2
