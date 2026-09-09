"""Local Grounding DINO subject detection.

This module deliberately has no connection to the H3 generation loop.  It
loads Grounding DINO lazily and keeps the loaded model alive for subsequent
calls, making it suitable for checking a sequence of already-decoded frames.

The detector reuses the vendored ``local_groundingdino`` implementation from
the LayerStyle Advance ComfyUI node when it is available.  It can also use an
installed ``local_groundingdino`` package by putting that package's parent
directory on ``PYTHONPATH``.  If the standard model pair is missing, the
Swin-T config/checkpoint are downloaded once into a local model cache.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Optional, Sequence, Union

from PIL import Image


ImageInput = Union[str, os.PathLike[str], Image.Image]


class GroundingDINOError(RuntimeError):
    """Raised when the local Grounding DINO backend cannot be initialized."""


@dataclass(frozen=True)
class Detection:
    """One Grounding DINO detection in original-image pixel coordinates."""

    confidence: float
    bbox: list[int]
    normalized_bbox: list[float]
    matched_phrase: str

    @property
    def phrase(self) -> str:
        """Short alias useful to callers and CLI output."""

        return self.matched_phrase

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # Keep the human-facing ``phrase`` name available without making it
        # the canonical dataclass field.
        result["phrase"] = self.matched_phrase
        return result


@dataclass(frozen=True)
class DetectionResult:
    """Structured result for one image/query pair."""

    found: bool
    confidence: float
    bbox: Optional[list[int]]
    normalized_bbox: Optional[list[float]]
    matched_phrase: Optional[str]
    image_width: int
    image_height: int
    detections: tuple[Detection, ...]
    best_match: Optional[Detection]

    @property
    def phrase(self) -> Optional[str]:
        return self.matched_phrase

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "found": self.found,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "normalized_bbox": self.normalized_bbox,
            "matched_phrase": self.matched_phrase,
            "phrase": self.matched_phrase,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "detections": [item.to_dict() for item in self.detections],
            "best_match": self.best_match.to_dict() if self.best_match else None,
        }
        return result


@dataclass(frozen=True)
class _RawDetection:
    """Backend-neutral normalized cx/cy/w/h detection."""

    normalized_cxcywh: Sequence[float]
    confidence: float
    phrase: str


def _validate_threshold(name: str, value: float) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}")
    return value


def _preprocess_caption(caption: str) -> str:
    caption = caption.lower().strip()
    if not caption:
        raise ValueError("query must not be empty")
    return caption if caption.endswith(".") else f"{caption}."


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _open_image(image: ImageInput) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")

    image_path = Path(image).expanduser()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with Image.open(image_path) as opened:
        return opened.convert("RGB")


def _to_detection(
    raw: _RawDetection,
    image_width: int,
    image_height: int,
) -> Detection:
    cx, cy, width, height = (float(item) for item in raw.normalized_cxcywh)
    x1 = _clamp(cx - width / 2.0, 0.0, 1.0)
    y1 = _clamp(cy - height / 2.0, 0.0, 1.0)
    x2 = _clamp(cx + width / 2.0, 0.0, 1.0)
    y2 = _clamp(cy + height / 2.0, 0.0, 1.0)
    normalized = [x1, y1, x2, y2]
    pixel = [
        int(round(x1 * image_width)),
        int(round(y1 * image_height)),
        int(round(x2 * image_width)),
        int(round(y2 * image_height)),
    ]
    return Detection(
        confidence=_clamp(float(raw.confidence), 0.0, 1.0),
        bbox=pixel,
        normalized_bbox=normalized,
        matched_phrase=raw.phrase,
    )


def _resolve_device(requested: Optional[str]) -> str:
    """Resolve the DINO device without implicitly selecting the render GPU."""

    requested = (requested or "cpu").lower()
    if requested == "auto":
        # ``auto`` must not claim the render GPU merely because CUDA exists.
        # CUDA remains available only through an explicit ``cuda``/``cuda:N``.
        requested = "cpu"
    if requested.startswith("cuda") and not _cuda_available():
        return "cpu"
    if requested not in {"cpu", "cuda"} and not requested.startswith("cuda:"):
        raise ValueError("device must be 'auto', 'cpu', 'cuda', or 'cuda:N'")
    return requested


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def _candidate_comfy_roots() -> list[Path]:
    roots: list[Path] = []
    for variable in ("MINIMAX_COMFYUI_ROOT", "COMFYUI_ROOT"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value).expanduser())
    roots.extend(
        [
            Path.home() / "AI" / "ComfyUI",
            Path.home() / "ComfyUI",
        ]
    )
    unique: list[Path] = []
    for root in roots:
        root = root.resolve()
        if root not in unique:
            unique.append(root)
    return unique


def _find_model_paths(
    config_path: Optional[Union[str, os.PathLike[str]]],
    checkpoint_path: Optional[Union[str, os.PathLike[str]]],
    auto_download: bool = True,
) -> tuple[Path, Path]:
    """Resolve explicit paths or standard ComfyUI Grounding DINO paths."""

    explicit_config = Path(config_path).expanduser() if config_path else None
    explicit_checkpoint = Path(checkpoint_path).expanduser() if checkpoint_path else None

    if explicit_config and not explicit_config.is_file():
        raise FileNotFoundError(f"Grounding DINO config not found: {explicit_config}")
    if explicit_checkpoint and not explicit_checkpoint.is_file():
        raise FileNotFoundError(
            f"Grounding DINO checkpoint not found: {explicit_checkpoint}"
        )

    known_pairs = (
        ("GroundingDINO_SwinT_OGC.cfg.py", "groundingdino_swint_ogc.pth"),
        ("GroundingDINO_SwinB.cfg.py", "groundingdino_swinb_cogcoor.pth"),
    )
    model_dirs: list[Path] = []
    configured_model_dir = os.environ.get("GROUNDING_DINO_MODEL_DIR")
    if configured_model_dir:
        model_dirs.append(Path(configured_model_dir).expanduser())
    for root in _candidate_comfy_roots():
        model_dirs.extend(
            [
                root / "models" / "grounding-dino",
                root / "models" / "grounding_dino",
                root / "models" / "detection",
            ]
        )

    if explicit_config and explicit_checkpoint:
        return explicit_config.resolve(), explicit_checkpoint.resolve()

    if explicit_config:
        for _, checkpoint_name in known_pairs:
            candidate = explicit_config.parent / checkpoint_name
            if candidate.is_file():
                return explicit_config.resolve(), candidate.resolve()
        raise FileNotFoundError(
            "A Grounding DINO checkpoint is required alongside the supplied "
            f"config: {explicit_config.parent}"
        )

    if explicit_checkpoint:
        for config_name, _ in known_pairs:
            candidate = explicit_checkpoint.parent / config_name
            if candidate.is_file():
                return candidate.resolve(), explicit_checkpoint.resolve()
        raise FileNotFoundError(
            "A Grounding DINO config is required alongside the supplied "
            f"checkpoint: {explicit_checkpoint.parent}"
        )

    for model_dir in model_dirs:
        for config_name, checkpoint_name in known_pairs:
            config_candidate = model_dir / config_name
            checkpoint_candidate = model_dir / checkpoint_name
            if config_candidate.is_file() and checkpoint_candidate.is_file():
                return config_candidate.resolve(), checkpoint_candidate.resolve()

    if auto_download:
        return _download_default_model(model_dirs)

    searched = ", ".join(str(item) for item in model_dirs)
    raise FileNotFoundError(
        "Grounding DINO model files were not found. Supply --config and "
        "--checkpoint, or place a standard pair in one of: "
        f"{searched or 'a ComfyUI/models/grounding-dino directory'}"
    )


_GROUNDING_DINO_DOWNLOADS = {
    "GroundingDINO_SwinT_OGC.cfg.py": (
        "https://huggingface.co/ShilongLiu/GroundingDINO/resolve/main/"
        "GroundingDINO_SwinT_OGC.cfg.py"
    ),
    "groundingdino_swint_ogc.pth": (
        "https://huggingface.co/ShilongLiu/GroundingDINO/resolve/main/"
        "groundingdino_swint_ogc.pth"
    ),
}


def _download_model_directory(model_dirs: list[Path]) -> Path:
    configured = os.environ.get("GROUNDING_DINO_MODEL_DIR")
    if configured:
        return Path(configured).expanduser()

    # Reuse the first existing ComfyUI installation's model area.  This is
    # also where the LayerStyle node expects these exact filenames.
    for root in _candidate_comfy_roots():
        if root.is_dir():
            return root / "models" / "grounding-dino"

    # A user-level cache avoids putting a 700 MB checkpoint in this repository
    # when ComfyUI is not installed yet.
    return Path.home() / ".cache" / "grounding-dino"


def _download_file(url: str, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size > 0:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    print(f"Downloading Grounding DINO model file to {destination}...", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        partial.replace(destination)
    except (OSError, urllib.error.URLError) as error:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise GroundingDINOError(
            f"Could not download Grounding DINO model file from {url}: {error}"
        ) from error


def _download_default_model(model_dirs: list[Path]) -> tuple[Path, Path]:
    """Download the default Swin-T pair only when no local pair exists."""

    model_dir = _download_model_directory(model_dirs)
    config_name = "GroundingDINO_SwinT_OGC.cfg.py"
    checkpoint_name = "groundingdino_swint_ogc.pth"
    config = model_dir / config_name
    checkpoint = model_dir / checkpoint_name
    _download_file(_GROUNDING_DINO_DOWNLOADS[config_name], config)
    _download_file(_GROUNDING_DINO_DOWNLOADS[checkpoint_name], checkpoint)
    return config.resolve(), checkpoint.resolve()


def _find_local_package_parent() -> Optional[Path]:
    package_name = "local_groundingdino"
    for root in _candidate_comfy_roots():
        candidates = [
            root / "custom_nodes" / "ComfyUI_LayerStyle_Advance" / "py",
            root / "custom_nodes (2)" / "ComfyUI_LayerStyle_Advance" / "py",
        ]
        for candidate in candidates:
            # Some ComfyUI custom nodes vendor this implementation as a
            # namespace package without ``local_groundingdino/__init__.py``.
            # Its real package markers are the datasets/models subpackages.
            if (
                (candidate / package_name / "datasets").is_dir()
                and (candidate / package_name / "models").is_dir()
            ):
                return candidate

    installed = importlib.util.find_spec(package_name)
    if installed and installed.origin:
        return Path(installed.origin).parent.parent
    return None


_TORCHVISION_COMPAT_OPERATORS = {
    "nms": "nms(Tensor boxes, Tensor scores, float iou_threshold) -> Tensor",
    "qnms": "qnms(Tensor boxes, Tensor scores, float iou_threshold) -> Tensor",
}


def _torchvision_operator_is_registered(torch: Any, operator: str) -> bool:
    """Check the dispatcher schema without invoking a possibly missing op."""

    try:
        torch._C._dispatch_find_schema_or_throw(
            f"torchvision::{operator}",
            "",
        )
    except (AttributeError, RuntimeError):
        return False
    return True


def _load_torchvision(torch: Any) -> tuple[Any, Any]:
    """Load torchvision, adding schemas only when its native ops are absent.

    torchvision's import registers fake implementations for NMS. Importing it
    first gives its native extension the opportunity to register the real
    operators. The compatibility schemas are created only after a specific
    missing-operator import failure and only for schemas still absent then.
    """

    try:
        return importlib.import_module("torchvision"), None
    except RuntimeError as error:
        error_text = str(error)
        missing_operator_error = any(
            f"operator torchvision::{operator} does not exist" in error_text
            for operator in _TORCHVISION_COMPAT_OPERATORS
        )
        if not missing_operator_error:
            raise
        import_error = error

    missing_operators = [
        operator
        for operator in _TORCHVISION_COMPAT_OPERATORS
        if not _torchvision_operator_is_registered(torch, operator)
    ]
    if not missing_operators:
        # The failed import was not evidence that a replacement schema is
        # needed. In particular, never define over a native operator.
        raise import_error

    compat_library = torch.library.Library("torchvision", "FRAGMENT")
    for operator in missing_operators:
        # Recheck immediately before definition so a concurrent/native loader
        # cannot turn this narrow compatibility path into a duplicate schema.
        if not _torchvision_operator_is_registered(torch, operator):
            compat_library.define(_TORCHVISION_COMPAT_OPERATORS[operator])

    return importlib.import_module("torchvision"), compat_library


class _LocalGroundingDINOBackend:
    """Adapter around the official Python implementation used by ComfyUI."""

    def __init__(
        self,
        config_path: Path,
        checkpoint_path: Path,
        device: str,
        bert_model_path: Optional[Union[str, os.PathLike[str]]] = None,
    ) -> None:
        try:
            import torch
        except ImportError as error:
            raise GroundingDINOError(
                "Grounding DINO requires PyTorch. Install the optional "
                "requirements-grounding-dino.txt dependencies."
            ) from error

        package_parent = _find_local_package_parent()
        if package_parent and str(package_parent) not in sys.path:
            sys.path.insert(0, str(package_parent))

        torchvision, torchvision_compat_library = _load_torchvision(torch)

        try:
            from local_groundingdino.datasets import transforms as transforms
            from local_groundingdino.models import build_model
            from local_groundingdino.util.misc import clean_state_dict
            from local_groundingdino.util.slconfig import SLConfig
            from local_groundingdino.util.utils import get_phrases_from_posmap
        except ImportError as error:
            raise GroundingDINOError(
                "Could not import the local Grounding DINO implementation. "
                "Install requirements-grounding-dino.txt in the Python "
                "environment used to run this script."
            ) from error

        args = SLConfig.fromfile(str(config_path))
        args.device = device
        if (
            getattr(args, "text_encoder_type", None) == "bert-base-uncased"
            and bert_model_path
        ):
            bert_path = Path(bert_model_path).expanduser()
            if not bert_path.exists():
                raise FileNotFoundError(f"BERT model path not found: {bert_path}")
            args.text_encoder_type = str(bert_path)

        model = build_model(args)
        try:
            checkpoint = torch.load(
                str(checkpoint_path), map_location="cpu", weights_only=False
            )
        except TypeError:  # Older PyTorch has no weights_only argument.
            checkpoint = torch.load(str(checkpoint_path), map_location="cpu")
        state_dict = checkpoint.get("model", checkpoint)
        model.load_state_dict(clean_state_dict(state_dict), strict=False)
        self._torch = torch
        self._torchvision_compat_library = torchvision_compat_library
        self._transforms = transforms
        self._get_phrases_from_posmap = get_phrases_from_posmap
        self.model = model.to(device).eval()
        self.device = device

    def predict(
        self,
        image: Image.Image,
        query: str,
        box_threshold: float,
        text_threshold: float,
    ) -> list[_RawDetection]:
        transform = self._transforms.Compose(
            [
                self._transforms.RandomResize([800], max_size=1333),
                self._transforms.ToTensor(),
                self._transforms.Normalize(
                    [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
                ),
            ]
        )
        image_tensor, _ = transform(image, None)
        caption = _preprocess_caption(query)
        with self._torch.inference_mode():
            outputs = self.model(image_tensor[None].to(self.device), captions=[caption])

        logits = outputs["pred_logits"].sigmoid()[0]
        boxes = outputs["pred_boxes"][0]
        mask = logits.max(dim=1).values > box_threshold
        logits = logits[mask].detach().cpu()
        boxes = boxes[mask].detach().cpu()
        tokenizer = self.model.tokenizer
        tokenized = tokenizer(caption)

        detections: list[_RawDetection] = []
        for logit, box in zip(logits, boxes):
            phrase = self._get_phrases_from_posmap(
                logit > text_threshold, tokenized, tokenizer
            ).replace(".", "").strip()
            detections.append(
                _RawDetection(
                    normalized_cxcywh=box.tolist(),
                    confidence=float(logit.max().item()),
                    phrase=phrase or query.strip(),
                )
            )
        return detections


class GroundingDINODetector:
    """Reusable, lazy Grounding DINO detector.

    ``detect`` accepts a filesystem path or a PIL image.  The model backend is
    initialized only at the first call and then reused by the instance.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, os.PathLike[str]]] = None,
        checkpoint_path: Optional[Union[str, os.PathLike[str]]] = None,
        bert_model_path: Optional[Union[str, os.PathLike[str]]] = None,
        device: Optional[str] = None,
        backend: Any = None,
        auto_download: bool = True,
    ) -> None:
        self.config_path = config_path
        self.checkpoint_path = checkpoint_path
        self.bert_model_path = bert_model_path
        self.device = _resolve_device(device)
        self._backend = backend
        self.auto_download = auto_download
        self._load_lock = RLock()

    @property
    def loaded(self) -> bool:
        return self._backend is not None

    def _get_backend(self) -> Any:
        if self._backend is None:
            with self._load_lock:
                if self._backend is None:
                    config, checkpoint = _find_model_paths(
                        self.config_path,
                        self.checkpoint_path,
                        auto_download=self.auto_download,
                    )
                    self._backend = _LocalGroundingDINOBackend(
                        config,
                        checkpoint,
                        self.device,
                        bert_model_path=self.bert_model_path,
                    )
                    print(
                        f"[DINO continuity] detector initialized device={self.device}",
                        flush=True,
                    )
        return self._backend

    def detect(
        self,
        image: ImageInput,
        query: str,
        box_threshold: float = 0.35,
        text_threshold: float = 0.25,
    ) -> DetectionResult:
        box_threshold = _validate_threshold("box_threshold", box_threshold)
        text_threshold = _validate_threshold("text_threshold", text_threshold)
        if not str(query).strip():
            raise ValueError("query must not be empty")

        source = _open_image(image)
        width, height = source.size
        raw_detections: Iterable[_RawDetection] = self._get_backend().predict(
            source, str(query), box_threshold, text_threshold
        )
        detections = tuple(
            sorted(
                (_to_detection(item, width, height) for item in raw_detections),
                key=lambda item: item.confidence,
                reverse=True,
            )
        )
        best_match = detections[0] if detections else None
        return DetectionResult(
            found=best_match is not None,
            confidence=best_match.confidence if best_match else 0.0,
            bbox=best_match.bbox if best_match else None,
            normalized_bbox=best_match.normalized_bbox if best_match else None,
            matched_phrase=best_match.matched_phrase if best_match else None,
            image_width=width,
            image_height=height,
            detections=detections,
            best_match=best_match,
        )


_DEFAULT_DETECTORS: dict[
    tuple[Optional[str], Optional[str], Optional[str], str, bool], GroundingDINODetector
] = {}
_DEFAULT_DETECTORS_LOCK = RLock()


def get_detector(
    config_path: Optional[Union[str, os.PathLike[str]]] = None,
    checkpoint_path: Optional[Union[str, os.PathLike[str]]] = None,
    bert_model_path: Optional[Union[str, os.PathLike[str]]] = None,
    device: Optional[str] = None,
    auto_download: bool = True,
) -> GroundingDINODetector:
    """Return a persistent detector for the supplied model/device settings."""

    resolved_device = _resolve_device(device)
    key = (
        str(Path(config_path).expanduser()) if config_path else None,
        str(Path(checkpoint_path).expanduser()) if checkpoint_path else None,
        str(Path(bert_model_path).expanduser()) if bert_model_path else None,
        resolved_device,
        auto_download,
    )
    with _DEFAULT_DETECTORS_LOCK:
        detector = _DEFAULT_DETECTORS.get(key)
        if detector is None:
            detector = GroundingDINODetector(
                config_path=config_path,
                checkpoint_path=checkpoint_path,
                bert_model_path=bert_model_path,
                device=resolved_device,
                auto_download=auto_download,
            )
            _DEFAULT_DETECTORS[key] = detector
        return detector


def detect_subject(
    image: ImageInput,
    query: str,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    *,
    config_path: Optional[Union[str, os.PathLike[str]]] = None,
    checkpoint_path: Optional[Union[str, os.PathLike[str]]] = None,
    bert_model_path: Optional[Union[str, os.PathLike[str]]] = None,
    device: Optional[str] = None,
    auto_download: bool = True,
) -> DetectionResult:
    """Detect a text-described subject using a persistent local model."""

    return get_detector(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        bert_model_path=bert_model_path,
        device=device,
        auto_download=auto_download,
    ).detect(image, query, box_threshold, text_threshold)


def _print_result(result: DetectionResult) -> None:
    print(f"found: {'true' if result.found else 'false'}")
    print(f"confidence: {result.confidence:.2f}")
    print(f"bbox: {result.bbox}")
    print(f"normalized_bbox: {result.normalized_bbox}")
    print(f"phrase: {result.matched_phrase}")
    print(f"image_size: {result.image_width}x{result.image_height}")
    print(f"detections: {len(result.detections)}")
    for index, detection in enumerate(result.detections, start=1):
        print(
            f"  {index}. confidence={detection.confidence:.2f} "
            f"bbox={detection.bbox} phrase={detection.matched_phrase}"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run local Grounding DINO detection")
    parser.add_argument("--image", required=True, help="Path to an image")
    parser.add_argument("--query", required=True, help="Text subject query")
    parser.add_argument("--box-threshold", type=float, default=0.35)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--config", help="Grounding DINO .cfg.py path")
    parser.add_argument("--checkpoint", help="Grounding DINO .pth path")
    parser.add_argument("--bert-model", help="Optional local bert-base-uncased path")
    parser.add_argument(
        "--device", default="cpu", help="cpu, cuda, or cuda:N (default: cpu)"
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Fail when model files are missing instead of downloading them",
    )
    args = parser.parse_args(argv)

    try:
        result = detect_subject(
            args.image,
            args.query,
            args.box_threshold,
            args.text_threshold,
            config_path=args.config,
            checkpoint_path=args.checkpoint,
            bert_model_path=args.bert_model,
            device=args.device,
            auto_download=not args.no_download,
        )
    except (FileNotFoundError, GroundingDINOError, OSError, ValueError) as error:
        parser.error(str(error))
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
