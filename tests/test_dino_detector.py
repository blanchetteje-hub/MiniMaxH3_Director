import subprocess
import sys
from types import SimpleNamespace

from PIL import Image

import dino_detector
from dino_detector import (
    GroundingDINODetector,
    _RawDetection,
)


class FakeBackend:
    def __init__(self, detections):
        self.detections = detections
        self.calls = []

    def predict(self, image, query, box_threshold, text_threshold):
        self.calls.append((image.size, query, box_threshold, text_threshold))
        return self.detections


def test_returns_all_detections_and_best_match_in_pixel_coordinates():
    backend = FakeBackend(
        [
            _RawDetection((0.5, 0.5, 0.2, 0.4), 0.62, "woman"),
            _RawDetection((0.25, 0.25, 0.3, 0.2), 0.91, "woman wearing a red dress"),
        ]
    )
    detector = GroundingDINODetector(device="cpu", backend=backend)

    result = detector.detect(
        Image.new("RGB", (1000, 800)),
        "Amy, a woman wearing a red dress",
        box_threshold=0.4,
        text_threshold=0.2,
    )

    assert result.found is True
    assert result.confidence == 0.91
    assert result.bbox == [100, 120, 400, 280]
    assert result.normalized_bbox == [0.1, 0.15, 0.4, 0.35]
    assert result.matched_phrase == "woman wearing a red dress"
    assert result.best_match == result.detections[0]
    assert len(result.detections) == 2
    assert backend.calls == [
        ((1000, 800), "Amy, a woman wearing a red dress", 0.4, 0.2)
    ]


def test_no_match_has_stable_structured_output():
    detector = GroundingDINODetector(device="cpu", backend=FakeBackend([]))
    result = detector.detect(Image.new("RGB", (320, 240)), "woman")

    assert result.to_dict() == {
        "found": False,
        "confidence": 0.0,
        "bbox": None,
        "normalized_bbox": None,
        "matched_phrase": None,
        "phrase": None,
        "image_width": 320,
        "image_height": 240,
        "detections": [],
        "best_match": None,
    }


def test_model_backend_is_lazy_and_reused():
    backend = FakeBackend([])
    detector = GroundingDINODetector(device="cpu", backend=backend)
    assert detector.loaded is True
    detector.detect(Image.new("RGB", (32, 32)), "person")
    detector.detect(Image.new("RGB", (32, 32)), "person")
    assert len(backend.calls) == 2


def test_dino_default_device_is_cpu_and_factory_reuses_one_detector(tmp_path):
    first = dino_detector.get_detector(
        config_path=tmp_path / "config.py",
        checkpoint_path=tmp_path / "checkpoint.pth",
        device=None,
        auto_download=False,
    )
    second = dino_detector.get_detector(
        config_path=tmp_path / "config.py",
        checkpoint_path=tmp_path / "checkpoint.pth",
        device="cpu",
        auto_download=False,
    )

    assert first is second
    assert first.device == "cpu"


def test_thresholds_are_validated():
    detector = GroundingDINODetector(device="cpu", backend=FakeBackend([]))
    for name, value in (("box_threshold", -0.1), ("text_threshold", 1.1)):
        try:
            detector.detect(Image.new("RGB", (10, 10)), "person", **{name: value})
        except ValueError as error:
            assert name in str(error)
        else:
            raise AssertionError("invalid threshold was accepted")


def test_torchvision_loader_does_not_define_an_existing_native_operator(monkeypatch):
    definitions = []

    class FakeLibrary:
        def __init__(self, namespace, kind):
            assert namespace == "torchvision"
            assert kind == "FRAGMENT"

        def define(self, schema):
            definitions.append(schema)

    fake_torch = SimpleNamespace(
        library=SimpleNamespace(Library=FakeLibrary),
    )
    availability = {"nms": True, "qnms": False}
    imports = iter([
        RuntimeError("operator torchvision::qnms does not exist"),
        SimpleNamespace(ops=SimpleNamespace(nms=object())),
    ])

    def import_module(_name):
        result = next(imports)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(
        dino_detector,
        "_torchvision_operator_is_registered",
        lambda _torch, operator: availability[operator],
    )
    monkeypatch.setattr(
        dino_detector.importlib,
        "import_module",
        import_module,
    )

    _torchvision, _compatibility_library = dino_detector._load_torchvision(
        fake_torch
    )

    assert definitions == [dino_detector._TORCHVISION_COMPAT_OPERATORS["qnms"]]
    assert dino_detector._TORCHVISION_COMPAT_OPERATORS["nms"] not in definitions


def test_torchvision_import_and_nms_smoke_in_a_clean_process():
    script = """
import torch
import dino_detector

torchvision, _compatibility_library = dino_detector._load_torchvision(torch)
assert callable(torchvision.ops.nms)
assert dino_detector._torchvision_operator_is_registered(torch, "nms")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_missing_standard_model_downloads_into_configured_cache(tmp_path, monkeypatch):
    downloaded = []

    def fake_download(url, destination):
        downloaded.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"model")

    monkeypatch.setenv("GROUNDING_DINO_MODEL_DIR", str(tmp_path / "dino"))
    monkeypatch.setattr(dino_detector, "_candidate_comfy_roots", lambda: [])
    monkeypatch.setattr(dino_detector, "_download_file", fake_download)

    config, checkpoint = dino_detector._find_model_paths(None, None)

    assert config.name == "GroundingDINO_SwinT_OGC.cfg.py"
    assert checkpoint.name == "groundingdino_swint_ogc.pth"
    assert len(downloaded) == 2
    assert all(destination.parent == tmp_path / "dino" for _, destination in downloaded)


def test_configured_existing_model_pair_is_reused_without_download(tmp_path, monkeypatch):
    model_dir = tmp_path / "dino"
    model_dir.mkdir()
    config = model_dir / "GroundingDINO_SwinT_OGC.cfg.py"
    checkpoint = model_dir / "groundingdino_swint_ogc.pth"
    config.write_text("config")
    checkpoint.write_bytes(b"checkpoint")
    monkeypatch.setenv("GROUNDING_DINO_MODEL_DIR", str(model_dir))

    resolved_config, resolved_checkpoint = dino_detector._find_model_paths(
        None, None, auto_download=False
    )

    assert resolved_config == config.resolve()
    assert resolved_checkpoint == checkpoint.resolve()
