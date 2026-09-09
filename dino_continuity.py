"""Grounding DINO continuity-reference extraction with optional identity checks.

Grounding DINO finds text-conditioned person candidates. When a canonical
reference and an identity validator are supplied, InsightFace chooses which
candidate belongs to that subject. The saved output remains the padded,
whole-person DINO crop.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

from PIL import Image

from dino_detector import get_detector
from identity_validator import (
    IdentityCandidate,
    IdentityModelError,
    _maximum_weight_assignment,
    get_identity_validator,
)
from subject_registry import SubjectRegistry


DEFAULT_DINO_CONFIDENCE = 0.80
DEFAULT_DINO_BOX_THRESHOLD = 0.35
DEFAULT_DINO_TEXT_THRESHOLD = 0.25
DEFAULT_FRAME_SEARCH_INTERVAL = 8
DEFAULT_MAX_CANDIDATE_FRAMES = 12
DEFAULT_MAX_STATE_AGE_SECONDS = 1.0
DEFAULT_CROP_PADDING_X = 0.12
DEFAULT_CROP_PADDING_Y = 0.12
DEFAULT_MIN_BBOX_AREA_RATIO = 0.01
DEFAULT_FRAME_RATE = 24.0
DEFAULT_IDENTITY_CONFIDENCE = 0.48
DEFAULT_IDENTITY_MARGIN = 0.05


def _continuity_log(message: str) -> None:
    """Write one concise continuity-pipeline event to the runtime console."""

    print(f"[DINO continuity] {message}", flush=True)


@dataclass(frozen=True)
class ContinuityReferenceConfig:
    """Tunable settings for the high-confidence reference path."""

    # Rendering owns the single GPU in the normal H3 pipeline.  Continuity
    # inference is CPU-first and only uses CUDA when explicitly configured.
    dino_device: str = "cpu"
    identity_device: str = "cpu"
    dino_confidence: float = DEFAULT_DINO_CONFIDENCE
    box_threshold: float = DEFAULT_DINO_BOX_THRESHOLD
    text_threshold: float = DEFAULT_DINO_TEXT_THRESHOLD
    frame_search_interval: int = DEFAULT_FRAME_SEARCH_INTERVAL
    max_candidate_frames: int = DEFAULT_MAX_CANDIDATE_FRAMES
    crop_padding_x: float = DEFAULT_CROP_PADDING_X
    crop_padding_y: float = DEFAULT_CROP_PADDING_Y
    min_bbox_area_ratio: float = DEFAULT_MIN_BBOX_AREA_RATIO
    frame_rate: float = DEFAULT_FRAME_RATE
    identity_confidence: float = DEFAULT_IDENTITY_CONFIDENCE
    identity_margin: float = DEFAULT_IDENTITY_MARGIN
    max_state_age_seconds: float = DEFAULT_MAX_STATE_AGE_SECONDS

    def __post_init__(self) -> None:
        dino_device = str(self.dino_device).strip().lower()
        if dino_device == "auto":
            # ``auto`` is retained as an explicit compatibility choice, but
            # is never the default for continuity.
            dino_device = "cpu"
        if dino_device != "cpu" and dino_device != "cuda" and not dino_device.startswith("cuda:"):
            raise ValueError("dino_device must be 'cpu', 'cuda', or 'cuda:N'")
        identity_device = str(self.identity_device).strip().lower()
        if identity_device not in {"cpu", "cuda"}:
            raise ValueError("identity_device must be 'cpu' or 'cuda'")
        for name in (
            "dino_confidence",
            "box_threshold",
            "text_threshold",
            "crop_padding_x",
            "crop_padding_y",
            "min_bbox_area_ratio",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
        if not -1.0 <= float(self.identity_confidence) <= 1.0:
            raise ValueError("identity_confidence must be between -1.0 and 1.0")
        if not 0.0 <= float(self.identity_margin) <= 2.0:
            raise ValueError("identity_margin must be between 0.0 and 2.0")
        if int(self.frame_search_interval) <= 0:
            raise ValueError("frame_search_interval must be greater than zero")
        if int(self.max_candidate_frames) <= 0:
            raise ValueError("max_candidate_frames must be greater than zero")
        if not math.isfinite(float(self.max_state_age_seconds)) or float(
            self.max_state_age_seconds
        ) <= 0.0:
            raise ValueError("max_state_age_seconds must be greater than zero")
        if float(self.frame_rate) <= 0.0:
            raise ValueError("frame_rate must be greater than zero")


@dataclass(frozen=True)
class DinoCandidate:
    """One qualifying, whole-subject crop from a single frame/query."""

    candidate_index: int
    dino_query: str
    confidence: float
    bbox: list[int]
    crop_bbox: list[int]
    bbox_area_ratio: float
    touches_frame_edge: bool
    image_width: int
    image_height: int
    crop: Image.Image = field(repr=False, compare=False)
    source_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return serializable candidate metadata without the PIL crop."""

        return {
            "candidate_index": self.candidate_index,
            "dino_query": self.dino_query,
            "confidence": self.confidence,
            "bbox": list(self.bbox),
            "crop_bbox": list(self.crop_bbox),
            "bbox_area_ratio": self.bbox_area_ratio,
            "touches_frame_edge": self.touches_frame_edge,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "crop_width": self.crop.width,
            "crop_height": self.crop.height,
            "source_metadata": dict(self.source_metadata),
        }


@dataclass(frozen=True)
class SharedQueryCandidates:
    """All raw, rejected, and qualifying detections for one DINO query."""

    dino_query: str
    subject_keys: tuple[Any, ...]
    candidates: tuple[DinoCandidate, ...]
    raw_detections: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    rejections: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    fallback_candidates: tuple[DinoCandidate, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dino_query": self.dino_query,
            "subject_keys": list(self.subject_keys),
            "candidates": [item.to_dict() for item in self.candidates],
            "raw_detections": [dict(item) for item in self.raw_detections],
            "rejections": [dict(item) for item in self.rejections],
            "fallback_candidates": [
                item.to_dict() for item in self.fallback_candidates
            ],
        }


@dataclass(frozen=True)
class IdentityScorePair:
    """Analytical identity result for one subject/candidate pair."""

    subject_key: Any
    candidate_index: int
    evaluated: bool
    identity_similarity: Optional[float]
    status: str
    face_bbox: Optional[list[float]] = None
    face_detection_score: Optional[float] = None
    canonical_face_bbox: Optional[list[float]] = None
    canonical_face_detection_score: Optional[float] = None
    identity_backend: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "candidate_index": self.candidate_index,
            "evaluated": self.evaluated,
            "identity_similarity": self.identity_similarity,
            "status": self.status,
            "face_bbox": self.face_bbox,
            "face_detection_score": self.face_detection_score,
            "canonical_face_bbox": self.canonical_face_bbox,
            "canonical_face_detection_score": self.canonical_face_detection_score,
            "identity_backend": self.identity_backend,
            "error": self.error,
        }


@dataclass(frozen=True)
class IdentityScoreMatrix:
    """Complete subject-by-candidate identity score matrix for one query."""

    dino_query: str
    subject_keys: tuple[Any, ...]
    candidate_indices: tuple[int, ...]
    scores: Mapping[Any, Mapping[int, IdentityScorePair]]
    identity_threshold: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dino_query": self.dino_query,
            "subject_keys": list(self.subject_keys),
            "candidate_indices": list(self.candidate_indices),
            "scores": {
                str(subject_key): {
                    str(candidate_index): pair.to_dict()
                    for candidate_index, pair in row.items()
                }
                for subject_key, row in self.scores.items()
            },
            "identity_threshold": self.identity_threshold,
        }


@dataclass(frozen=True)
class SubjectCandidateAssignment:
    """Ownership-only result for one subject within one query group."""

    subject_key: Any
    dino_query: str
    assigned: bool
    candidate_index: Optional[int]
    identity_similarity: Optional[float]
    status: str
    identity_backend: Optional[str] = None
    unresolved_statuses: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "dino_query": self.dino_query,
            "assigned": self.assigned,
            "candidate_index": self.candidate_index,
            "identity_similarity": self.identity_similarity,
            "status": self.status,
            "identity_backend": self.identity_backend,
            "unresolved_statuses": list(self.unresolved_statuses),
        }


@dataclass(frozen=True)
class SubjectReferenceUpdateResult:
    """Per-subject result from the shared Step 6 backward search."""

    subject_key: Any
    updated: bool
    status: str
    frame_index: Optional[int] = None
    timestamp_seconds: Optional[float] = None
    dino_query: Optional[str] = None
    candidate_index: Optional[int] = None
    identity_similarity: Optional[float] = None
    output_path: Optional[str] = None
    vision_frame_path: Optional[str] = None
    identity_backend: Optional[str] = None
    last_identity_status: Optional[str] = None
    resolution_method: Optional[str] = None
    attempted_frames: int = 0
    error: Optional[str] = None

    @property
    def found(self) -> bool:
        """Compatibility spelling used by the older reference result."""

        return self.updated

    @property
    def reason(self) -> str:
        """Compatibility spelling used by the older reference result."""

        return self.status

    @property
    def identity_status(self) -> Optional[str]:
        return self.last_identity_status

    @property
    def timestamp(self) -> Optional[float]:
        return self.timestamp_seconds

    @property
    def identity_candidate_index(self) -> Optional[int]:
        return self.candidate_index

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "updated": self.updated,
            "found": self.updated,
            "ambiguous": self.status == "ambiguous_identity",
            "status": self.status,
            "reason": self.status,
            "confidence": None,
            "bbox": None,
            "crop_bbox": None,
            "frame_index": self.frame_index,
            "timestamp_seconds": self.timestamp_seconds,
            "timestamp": self.timestamp_seconds,
            "image_width": None,
            "image_height": None,
            "bbox_width": None,
            "bbox_height": None,
            "bbox_area_ratio": None,
            "touches_frame_edge": None,
            "crop_width": None,
            "crop_height": None,
            "matched_phrase": None,
            "dino_query": self.dino_query,
            "candidate_index": self.candidate_index,
            "identity_candidate_index": self.candidate_index,
            "identity_status": self.last_identity_status,
            "identity_similarity": self.identity_similarity,
            "identity_threshold": None,
            "identity_margin": None,
            "identity_face_bbox": None,
            "identity_candidates": [],
            "output_path": self.output_path,
            "vision_frame_path": self.vision_frame_path,
            "identity_backend": self.identity_backend,
            "last_identity_status": self.last_identity_status,
            "resolution_method": self.resolution_method,
            "attempted_frames": self.attempted_frames,
            "error": self.error,
            "attempts": [],
        }


@dataclass(frozen=True)
class ContinuityReferenceResult:
    """Success or non-destructive failure from one reference search."""

    found: bool
    ambiguous: bool
    reason: str
    confidence: Optional[float] = None
    bbox: Optional[list[int]] = None
    crop_bbox: Optional[list[int]] = None
    frame_index: Optional[int] = None
    timestamp: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    bbox_width: Optional[int] = None
    bbox_height: Optional[int] = None
    bbox_area_ratio: Optional[float] = None
    touches_frame_edge: Optional[bool] = None
    crop_width: Optional[int] = None
    crop_height: Optional[int] = None
    matched_phrase: Optional[str] = None
    output_path: Optional[str] = None
    identity_status: Optional[str] = None
    identity_similarity: Optional[float] = None
    identity_threshold: Optional[float] = None
    identity_margin: Optional[float] = None
    identity_candidate_index: Optional[int] = None
    identity_face_bbox: Optional[list[float]] = None
    identity_candidates: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    attempts: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "ambiguous": self.ambiguous,
            "reason": self.reason,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "crop_bbox": self.crop_bbox,
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "bbox_width": self.bbox_width,
            "bbox_height": self.bbox_height,
            "bbox_area_ratio": self.bbox_area_ratio,
            "touches_frame_edge": self.touches_frame_edge,
            "crop_width": self.crop_width,
            "crop_height": self.crop_height,
            "matched_phrase": self.matched_phrase,
            "output_path": self.output_path,
            "identity_status": self.identity_status,
            "identity_similarity": self.identity_similarity,
            "identity_threshold": self.identity_threshold,
            "identity_margin": self.identity_margin,
            "identity_candidate_index": self.identity_candidate_index,
            "identity_face_bbox": self.identity_face_bbox,
            "identity_candidates": list(self.identity_candidates),
            "attempts": list(self.attempts),
        }


def validate_subject_identity(
    candidate_crop: Image.Image,
    canonical_reference: Any = None,
) -> str:
    """Future identity hook; identity is deliberately not evaluated yet."""

    del candidate_crop, canonical_reference
    return "not_evaluated"


def subject_query(subject: dict[str, Any], fallback: str = "person") -> str:
    """Read the query resolved by SubjectRegistry; never infer downstream."""

    del fallback
    return str(subject.get("dino_query") or "person")


def current_reference_path(
    output_directory: os.PathLike[str] | str,
    subject_name: str,
) -> str:
    """Build a deterministic, safe ``<subject>_current.png`` path."""

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(subject_name).strip())
    safe_name = safe_name.strip("._") or "subject"
    return os.path.abspath(
        os.path.join(os.fspath(output_directory), f"{safe_name}_current.png")
    )


def subject_current_reference_path(
    output_directory: os.PathLike[str] | str,
    subject_name: str,
    subject: Any,
) -> str:
    """Resolve an optional per-subject current-state path."""

    configured = (
        subject.get("current_state_reference")
        if isinstance(subject, dict)
        else None
    )
    if configured:
        configured = os.path.expanduser(os.path.expandvars(os.fspath(configured)))
        if not os.path.isabs(configured):
            configured = os.path.join(os.fspath(output_directory), configured)
        return os.path.abspath(configured)
    return current_reference_path(output_directory, subject_name)


def _as_subject_registry(subjects: Any) -> SubjectRegistry:
    if isinstance(subjects, SubjectRegistry):
        return subjects
    return SubjectRegistry.from_records(subjects)


def _canonical_subject_key(
    registry: SubjectRegistry,
    subject_reference: Any,
) -> Any:
    """Resolve an alias or stable ID to the registry's actual mapping key."""

    record = registry.get_subject(subject_reference)
    if record is None:
        return None
    for key, candidate in registry.items():
        if candidate is record:
            return key
    # ``get_subject`` normally returns the exact stored dictionary. Keep a
    # value-based fallback for callers that provide mapping-like records.
    subject_id = record.get("subject_id") if isinstance(record, Mapping) else None
    for key, candidate in registry.items():
        if (
            isinstance(candidate, Mapping)
            and subject_id is not None
            and str(candidate.get("subject_id")) == str(subject_id)
        ):
            return key
    return None


def _canonical_subject_keys(
    registry: SubjectRegistry,
    subject_references: Optional[Sequence[Any]],
    label: str,
) -> Optional[set[Any]]:
    """Resolve requested subject aliases before Step 6/7 membership checks."""

    if subject_references is None:
        return None
    canonical = set()
    unknown = []
    for reference in subject_references:
        key = _canonical_subject_key(registry, reference)
        if key is None:
            unknown.append(reference)
        else:
            canonical.add(key)
    if unknown:
        raise ValueError(
            f"{label} contains unknown subject key(s): "
            + ", ".join(repr(key) for key in sorted(unknown, key=str))
        )
    return canonical


def _identity_key(record: Mapping[str, Any], fallback: Any) -> str:
    return str(record.get("subject_id", fallback))


def _result_detections(result: Any) -> list[Any]:
    if isinstance(result, dict):
        detections = result.get("detections", [])
    else:
        detections = getattr(result, "detections", [])
    return list(detections or [])


def _detection_value(detection: Any, name: str, default: Any = None) -> Any:
    if isinstance(detection, dict):
        return detection.get(name, default)
    return getattr(detection, name, default)


def _frame_image(frame: Image.Image | os.PathLike[str] | str) -> Image.Image:
    """Load one frame as an independent RGB PIL image."""

    if isinstance(frame, Image.Image):
        return frame.convert("RGB")
    path = Path(os.fspath(frame)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Frame image is missing: {path!s}")
    with Image.open(path) as opened:
        return opened.convert("RGB")


def _detection_metadata(detection: Any) -> dict[str, Any]:
    """Copy detector metadata into a debug-friendly mapping."""

    to_dict = getattr(detection, "to_dict", None)
    if callable(to_dict):
        metadata = to_dict()
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {}
    elif isinstance(detection, Mapping):
        metadata = dict(detection)
    else:
        metadata = {
            name: _detection_value(detection, name)
            for name in ("confidence", "bbox", "normalized_bbox", "matched_phrase", "phrase")
            if _detection_value(detection, name) is not None
        }
    if "bbox" in metadata and metadata["bbox"] is not None:
        try:
            metadata["bbox"] = list(metadata["bbox"])
        except TypeError:
            pass
    if "normalized_bbox" in metadata and metadata["normalized_bbox"] is not None:
        try:
            metadata["normalized_bbox"] = list(metadata["normalized_bbox"])
        except TypeError:
            pass
    return metadata


def _padded_crop_bbox(
    bbox: Sequence[int | float],
    image_width: int,
    image_height: int,
    padding_x: float,
    padding_y: float,
) -> list[int]:
    """Pad an xyxy bbox proportionally and clamp it to image bounds."""

    x1, y1, x2, y2 = (float(value) for value in bbox)
    bbox_width = max(0.0, x2 - x1)
    bbox_height = max(0.0, y2 - y1)
    crop = [
        max(0, int(math.floor(x1 - bbox_width * padding_x))),
        max(0, int(math.floor(y1 - bbox_height * padding_y))),
        min(image_width, int(math.ceil(x2 + bbox_width * padding_x))),
        min(image_height, int(math.ceil(y2 + bbox_height * padding_y))),
    ]
    # Rounding/clamping must never make the crop smaller than the DINO box.
    crop[0] = min(crop[0], max(0, int(math.floor(x1))))
    crop[1] = min(crop[1], max(0, int(math.floor(y1))))
    crop[2] = max(crop[2], min(image_width, int(math.ceil(x2))))
    crop[3] = max(crop[3], min(image_height, int(math.ceil(y2))))
    return crop


def _save_crop_atomically(crop: Image.Image, output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        crop.save(temporary_path, format="PNG")
        # Validate the staged image before replacing the existing current
        # state.  The destination is untouched if encoding or validation
        # fails.
        with Image.open(temporary_path) as staged:
            staged.verify()
        os.replace(temporary_path, output)
        _continuity_log(
            f"state commit: atomically replaced current image path={output}"
        )
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _frame_path(extracted: Any, temporary_directory: str) -> str:
    path = os.fspath(extracted)
    return path if os.path.isabs(path) else os.path.join(temporary_directory, path)


def _prepare_candidates(
    candidate_image: Image.Image,
    detections: Sequence[Any],
    config: ContinuityReferenceConfig,
    frame_index: int,
    timestamp: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    """Prepare valid padded DINO crops once for a shared query group."""

    image_width, image_height = candidate_image.size
    prepared = []
    attempts = []
    reasons: set[str] = set()
    for candidate_index, detection in enumerate(detections):
        raw_bbox = _detection_value(detection, "bbox")
        try:
            bbox = [int(round(float(value))) for value in raw_bbox]
        except (TypeError, ValueError):
            bbox = []
        if len(bbox) != 4:
            attempts.append({
                "frame_index": frame_index,
                "timestamp": timestamp,
                "candidate_index": candidate_index,
                "reason": "frame_unusable",
                "error": "detector returned an invalid bbox",
            })
            continue
        bbox = [
            max(0, min(image_width, bbox[0])),
            max(0, min(image_height, bbox[1])),
            max(0, min(image_width, bbox[2])),
            max(0, min(image_height, bbox[3])),
        ]
        x1, y1, x2, y2 = bbox
        bbox_width = max(0, x2 - x1)
        bbox_height = max(0, y2 - y1)
        area_ratio = (bbox_width * bbox_height) / float(image_width * image_height)
        if area_ratio < config.min_bbox_area_ratio:
            reasons.add("subject_too_small")
            attempts.append({
                "frame_index": frame_index,
                "timestamp": timestamp,
                "candidate_index": candidate_index,
                "reason": "subject_too_small",
                "confidence": float(_detection_value(detection, "confidence", 0.0)),
                "bbox_area_ratio": area_ratio,
            })
            continue
        crop_bbox = _padded_crop_bbox(
            bbox,
            image_width,
            image_height,
            config.crop_padding_x,
            config.crop_padding_y,
        )
        crop_width = crop_bbox[2] - crop_bbox[0]
        crop_height = crop_bbox[3] - crop_bbox[1]
        if crop_width <= 0 or crop_height <= 0:
            attempts.append({
                "frame_index": frame_index,
                "timestamp": timestamp,
                "candidate_index": candidate_index,
                "reason": "frame_unusable",
                "error": "padded crop has no area",
            })
            continue
        prepared.append({
            "candidate_index": candidate_index,
            "detection": detection,
            "bbox": bbox,
            "crop_bbox": crop_bbox,
            "crop": candidate_image.crop(tuple(crop_bbox)),
            "bbox_width": bbox_width,
            "bbox_height": bbox_height,
            "area_ratio": area_ratio,
            "touches_edge": (
                x1 <= 0 or y1 <= 0 or x2 >= image_width or y2 >= image_height
            ),
            "crop_width": crop_width,
            "crop_height": crop_height,
        })
    return prepared, attempts, reasons


def _prepare_shared_candidates(
    candidate_image: Image.Image,
    query: str,
    detections: Sequence[Any],
    config: ContinuityReferenceConfig,
    source_metadata: Mapping[str, Any],
    minimum_confidence: Optional[float] = None,
) -> tuple[
    list[DinoCandidate],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Filter and crop one query's detections without assigning identities."""

    image_width, image_height = candidate_image.size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("frame image must have positive dimensions")

    raw_metadata: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    candidates: list[DinoCandidate] = []
    for detection_index, detection in enumerate(detections):
        metadata = _detection_metadata(detection)
        metadata.update({
            "dino_query": query,
            "detection_index": detection_index,
        })
        raw_metadata.append(metadata)

        try:
            confidence = float(_detection_value(detection, "confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "invalid_detection",
                "confidence": confidence,
            })
            continue
        confidence_threshold = (
            config.dino_confidence
            if minimum_confidence is None
            else float(minimum_confidence)
        )
        if confidence < confidence_threshold:
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "below_confidence_threshold",
                "confidence": confidence,
                "threshold": confidence_threshold,
            })
            continue

        raw_bbox = _detection_value(detection, "bbox")
        try:
            bbox = [int(round(float(value))) for value in raw_bbox]
        except (TypeError, ValueError):
            bbox = []
        if len(bbox) != 4:
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "invalid_bbox",
                "confidence": confidence,
            })
            continue

        bbox = [
            max(0, min(image_width, bbox[0])),
            max(0, min(image_height, bbox[1])),
            max(0, min(image_width, bbox[2])),
            max(0, min(image_height, bbox[3])),
        ]
        x1, y1, x2, y2 = bbox
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        if bbox_width <= 0 or bbox_height <= 0:
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "invalid_bbox",
                "confidence": confidence,
                "bbox": bbox,
            })
            continue

        bbox_area_ratio = (bbox_width * bbox_height) / float(
            image_width * image_height
        )
        if bbox_area_ratio < config.min_bbox_area_ratio:
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "subject_too_small",
                "confidence": confidence,
                "bbox": bbox,
                "bbox_area_ratio": bbox_area_ratio,
                "minimum_bbox_area_ratio": config.min_bbox_area_ratio,
            })
            continue

        crop_bbox = _padded_crop_bbox(
            bbox,
            image_width,
            image_height,
            config.crop_padding_x,
            config.crop_padding_y,
        )
        if (
            crop_bbox[0] > x1
            or crop_bbox[1] > y1
            or crop_bbox[2] < x2
            or crop_bbox[3] < y2
            or crop_bbox[2] <= crop_bbox[0]
            or crop_bbox[3] <= crop_bbox[1]
        ):
            rejections.append({
                "dino_query": query,
                "detection_index": detection_index,
                "reason": "frame_unusable",
                "confidence": confidence,
                "bbox": bbox,
                "crop_bbox": crop_bbox,
            })
            continue

        candidate_metadata = dict(source_metadata)
        candidate_metadata["detection_index"] = detection_index
        candidates.append(DinoCandidate(
            candidate_index=len(candidates),
            dino_query=query,
            confidence=confidence,
            bbox=bbox,
            crop_bbox=crop_bbox,
            bbox_area_ratio=bbox_area_ratio,
            touches_frame_edge=(
                x1 <= 0 or y1 <= 0 or x2 >= image_width or y2 >= image_height
            ),
            image_width=image_width,
            image_height=image_height,
            crop=candidate_image.crop(tuple(crop_bbox)),
            source_metadata=MappingProxyType(candidate_metadata),
        ))

    return candidates, raw_metadata, rejections


def detect_shared_candidates(
    frame: Image.Image | os.PathLike[str] | str,
    registry: SubjectRegistry | Mapping[Any, Mapping[str, Any]],
    *,
    detector: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    source_metadata: Mapping[str, Any] | None = None,
    retain_fallback_evidence: bool = False,
) -> dict[str, SharedQueryCandidates]:
    """Detect reusable, subject-agnostic candidates in one frame."""

    config = config or ContinuityReferenceConfig()
    registry = _as_subject_registry(registry)
    if not registry:
        _continuity_log("Step 3: no subjects supplied; skipping shared detection")
        return {}

    frame_image = _frame_image(frame)
    detector = detector or get_detector(device=config.dino_device)
    metadata = dict(source_metadata or {})
    results: dict[str, SharedQueryCandidates] = {}

    _continuity_log(
        "Step 3: shared detection start "
        f"frame={metadata.get('frame_index', 'unknown')} "
        f"queries={len(registry.group_by_query())} "
        f"subjects={len(registry)} "
        f"fallback_evidence={'on' if retain_fallback_evidence else 'off'}"
    )

    for query, query_registry in registry.group_by_query().items():
        query = str(query).strip()
        if not query:
            continue
        _continuity_log(
            f"Step 3: querying {query!r} for {len(query_registry)} subject(s)"
        )
        try:
            detector_result = detector.detect(
                frame_image,
                query,
                config.box_threshold,
                config.text_threshold,
            )
        except Exception as error:
            _continuity_log(
                f"Step 3: detector failed query={query!r}: {error}"
            )
            raise
        detections = _result_detections(detector_result)
        candidates, raw_detections, rejections = _prepare_shared_candidates(
            frame_image,
            query,
            detections,
            config,
            metadata,
        )
        fallback_candidates = ()
        if retain_fallback_evidence:
            fallback_candidates, _ignored_raw, _ignored_rejections = (
                _prepare_shared_candidates(
                    frame_image,
                    query,
                    detections,
                    config,
                    metadata,
                    minimum_confidence=0.0,
                )
            )
        _continuity_log(
            f"Step 3: query={query!r} raw={len(detections)} "
            f"accepted={len(candidates)} rejected={len(rejections)} "
            f"fallback_usable={len(fallback_candidates)}"
        )
        for candidate in candidates:
            _continuity_log(
                f"Step 3: candidate query={query!r} "
                f"index={candidate.candidate_index} "
                f"confidence={candidate.confidence:.3f} "
                f"bbox={candidate.bbox}"
            )
        for rejection in rejections:
            _continuity_log(
                f"Step 3: rejected query={query!r} "
                f"detection={rejection.get('detection_index', 'unknown')} "
                f"reason={rejection.get('reason', 'unknown')}"
            )
        results[query] = SharedQueryCandidates(
            dino_query=query,
            subject_keys=tuple(query_registry.keys()),
            candidates=tuple(candidates),
            raw_detections=tuple(
                MappingProxyType(item) for item in raw_detections
            ),
            rejections=tuple(
                MappingProxyType(item) for item in rejections
            ),
            fallback_candidates=tuple(fallback_candidates),
        )
    return results


def _shared_group_value(group: Any, name: str, default: Any = None) -> Any:
    if isinstance(group, Mapping):
        return group.get(name, default)
    return getattr(group, name, default)


def _identity_candidate_from_dino(candidate: Any) -> IdentityCandidate:
    """Adapt one Step 3 candidate without copying its crop image."""

    if isinstance(candidate, DinoCandidate):
        return IdentityCandidate(
            candidate_index=candidate.candidate_index,
            image=candidate.crop,
            dino_confidence=candidate.confidence,
            bbox=list(candidate.bbox),
            crop_bbox=list(candidate.crop_bbox),
        )
    if not isinstance(candidate, Mapping):
        raise TypeError("shared candidate must be a DinoCandidate or mapping")
    image = candidate.get("crop")
    if image is None:
        image = candidate.get("image")
    if not isinstance(image, Image.Image):
        raise TypeError("shared candidate must contain a PIL crop image")
    return IdentityCandidate(
        candidate_index=int(candidate["candidate_index"]),
        image=image,
        dino_confidence=float(
            candidate.get("confidence", candidate.get("dino_confidence", 0.0))
        ),
        bbox=list(candidate["bbox"]),
        crop_bbox=list(candidate["crop_bbox"]),
    )


def _identity_candidate_label(candidate: Any) -> str:
    """Return the stable frame/candidate label used by identity diagnostics."""

    frame_index = None
    if isinstance(candidate, Mapping):
        metadata = candidate.get("source_metadata", {}) or {}
        candidate_index = candidate.get("candidate_index", -1)
    else:
        metadata = getattr(candidate, "source_metadata", {}) or {}
        candidate_index = getattr(candidate, "candidate_index", -1)
    try:
        frame_index = int(metadata.get("frame_index"))
    except (TypeError, ValueError):
        pass
    candidate_index = int(candidate_index)
    if frame_index is None:
        return f"C{candidate_index}"
    return f"F{frame_index}-C{candidate_index}"


def build_identity_score_matrix(
    shared_candidates: Mapping[str, SharedQueryCandidates],
    registry: SubjectRegistry | Mapping[Any, Mapping[str, Any]],
    *,
    identity_validator: Any = None,
    identity_threshold: Optional[float] = None,
) -> dict[str, IdentityScoreMatrix]:
    """Build complete, non-assigning identity matrices for Step 3 groups."""

    registry = _as_subject_registry(registry)
    results: dict[str, IdentityScoreMatrix] = {}
    for query_key, group in (shared_candidates or {}).items():
        query = str(
            _shared_group_value(group, "dino_query", query_key)
        ).strip()
        subject_keys = tuple(_shared_group_value(group, "subject_keys", ()))
        dino_candidates = tuple(_shared_group_value(group, "candidates", ()))
        identity_candidates = tuple(
            _identity_candidate_from_dino(candidate)
            for candidate in dino_candidates
        )
        candidate_indices = tuple(
            candidate.candidate_index for candidate in identity_candidates
        )

        _continuity_log(
            f"Step 4: identity score matrix start query={query!r} "
            f"subjects={len(subject_keys)} candidates={len(candidate_indices)}"
        )

        rows: dict[Any, dict[int, IdentityScorePair]] = {}
        supported_subjects: dict[str, Mapping[str, Any]] = {}
        subject_identity_keys: dict[Any, str] = {}
        subject_backends: dict[Any, Optional[str]] = {}
        for subject_key in subject_keys:
            record = registry.get_subject(subject_key)
            if record is None:
                raise KeyError(
                    f"Step 3 candidate group references unknown subject: {subject_key!r}"
                )
            raw_backend = record.get("identity_backend", "insightface")
            backend = (
                str(raw_backend).strip()
                if raw_backend is not None
                else None
            )
            subject_backends[subject_key] = backend
            if backend is None or backend.casefold() != "insightface":
                rows[subject_key] = {
                    candidate.candidate_index: IdentityScorePair(
                        subject_key=subject_key,
                        candidate_index=candidate.candidate_index,
                        evaluated=False,
                        identity_similarity=None,
                        status="identity_backend_unavailable",
                        identity_backend=backend,
                    )
                    for candidate in identity_candidates
                }
                continue
            identity_key = _identity_key(record, subject_key)
            reference = (
                record.get("canonical_reference")
                or record.get("identity_reference")
            )
            supported_subjects[identity_key] = {
                "canonical_reference": reference,
            }
            subject_identity_keys[subject_key] = identity_key

        scored: dict[str, tuple[Any, ...]] = {}
        if supported_subjects:
            _continuity_log(
                f"Step 4: scoring {len(supported_subjects)} subject(s) x "
                f"{len(identity_candidates)} candidate(s) in one batch "
                f"for query={query!r}"
            )
            identity_validator = identity_validator or get_identity_validator(
                device=config.identity_device
            )
            try:
                scored = identity_validator.score_candidates_for_subjects(
                    supported_subjects,
                    identity_candidates,
                )
            except Exception as error:
                _continuity_log(
                    f"Step 4: identity scoring failed query={query!r}: {error}"
                )
                raise
        else:
            _continuity_log(
                f"Step 4: no supported identity backend for query={query!r}; "
                "recording unresolved pairs"
            )

        for subject_key in subject_keys:
            if subject_key not in subject_identity_keys:
                continue
            identity_key = subject_identity_keys[subject_key]
            score_items = {
                item.candidate_index: item
                for item in scored.get(identity_key, ())
            }
            backend = subject_backends[subject_key]
            rows[subject_key] = {
                candidate.candidate_index: IdentityScorePair(
                    subject_key=subject_key,
                    candidate_index=candidate.candidate_index,
                    evaluated=bool(
                        score_items.get(candidate.candidate_index)
                        and score_items[candidate.candidate_index].evaluated
                    ),
                    identity_similarity=(
                        score_items[candidate.candidate_index].identity_similarity
                        if candidate.candidate_index in score_items
                        else None
                    ),
                    status=(
                        (
                            "identity_score"
                            if score_items[candidate.candidate_index].reason
                            == "identity_evaluated"
                            else score_items[candidate.candidate_index].reason
                        )
                        if candidate.candidate_index in score_items
                        else "identity_model_error"
                    ),
                    face_bbox=(
                        score_items[candidate.candidate_index].face_bbox
                        if candidate.candidate_index in score_items
                        else None
                    ),
                    face_detection_score=(
                        getattr(
                            score_items[candidate.candidate_index],
                            "face_detection_score",
                            None,
                        )
                        if candidate.candidate_index in score_items
                        else None
                    ),
                    canonical_face_bbox=(
                        getattr(
                            score_items[candidate.candidate_index],
                            "canonical_face_bbox",
                            None,
                        )
                        if candidate.candidate_index in score_items
                        else None
                    ),
                    canonical_face_detection_score=(
                        getattr(
                            score_items[candidate.candidate_index],
                            "canonical_face_detection_score",
                            None,
                        )
                        if candidate.candidate_index in score_items
                        else None
                    ),
                    identity_backend=backend,
                    error=(
                        score_items[candidate.candidate_index].error
                        if candidate.candidate_index in score_items
                        else "identity validator returned no result"
                    ),
                )
                for candidate in identity_candidates
            }

        for subject_key in subject_keys:
            row = rows[subject_key]
            evaluated = sum(1 for pair in row.values() if pair.evaluated)
            scored_values = [
                pair.identity_similarity
                for pair in row.values()
                if pair.identity_similarity is not None
            ]
            statuses = sorted({pair.status for pair in row.values()})
            _continuity_log(
                f"Step 4: subject={subject_key!r} query={query!r} "
                f"evaluated={evaluated}/{len(row)} "
                f"scores={len(scored_values)} statuses={statuses}"
            )
            threshold = (
                DEFAULT_IDENTITY_CONFIDENCE
                if identity_threshold is None
                else float(identity_threshold)
            )
            for candidate in dino_candidates:
                pair = row[candidate.candidate_index]
                if pair.identity_similarity is None:
                    continue
                similarity = float(pair.identity_similarity)
                eligible = (
                    pair.evaluated
                    and pair.status in _IDENTITY_SCORE_STATUSES
                    and similarity >= threshold
                )
                diagnostic = (
                    f"[InsightFace] subject={subject_key!r} "
                    f"candidate={_identity_candidate_label(candidate)} "
                    f"similarity={similarity:.3f} "
                    f"threshold={threshold:.3f} eligible={str(eligible).lower()}"
                )
                if pair.face_detection_score is not None:
                    diagnostic += (
                        f" candidate_face_detection_score="
                        f"{float(pair.face_detection_score):.3f}"
                    )
                if pair.face_bbox is not None:
                    diagnostic += f" candidate_face_bbox={pair.face_bbox}"
                    face_width = float(pair.face_bbox[2]) - float(pair.face_bbox[0])
                    face_height = float(pair.face_bbox[3]) - float(pair.face_bbox[1])
                    diagnostic += (
                        f" detected_face_width={face_width:.1f}"
                        f" detected_face_height={face_height:.1f}"
                    )
                if pair.canonical_face_detection_score is not None:
                    diagnostic += (
                        f" canonical_face_detection_score="
                        f"{float(pair.canonical_face_detection_score):.3f}"
                    )
                if pair.canonical_face_bbox is not None:
                    diagnostic += f" canonical_face_bbox={pair.canonical_face_bbox}"
                print(diagnostic, flush=True)
            errors = sorted({
                str(pair.error)
                for pair in row.values()
                if pair.error
            })
            if errors:
                _continuity_log(
                    f"Step 4: subject={subject_key!r} query={query!r} "
                    f"identity errors={errors}"
                )

        rows_proxy = MappingProxyType({
            subject_key: MappingProxyType(row)
            for subject_key, row in rows.items()
        })
        results[query] = IdentityScoreMatrix(
            dino_query=query,
            subject_keys=subject_keys,
            candidate_indices=candidate_indices,
            scores=rows_proxy,
            identity_threshold=identity_threshold,
        )
        _continuity_log(
            f"Step 4: identity score matrix complete query={query!r}"
        )
    return results


build_identity_score_matrices = build_identity_score_matrix


_IDENTITY_SCORE_STATUSES = frozenset({
    "identity_score",
    "identity_evaluated",
})
_IDENTITY_UNRESOLVED_STATUSES = frozenset({
    "not_evaluated_no_face",
    "ambiguous_candidate_faces",
    "canonical_face_not_found",
    "identity_model_error",
    "identity_backend_unavailable",
})


def _matrix_value(matrix: Any, name: str, default: Any = None) -> Any:
    if isinstance(matrix, Mapping):
        return matrix.get(name, default)
    return getattr(matrix, name, default)


def _pair_value(pair: Any, name: str, default: Any = None) -> Any:
    if isinstance(pair, Mapping):
        return pair.get(name, default)
    return getattr(pair, name, default)


def _validated_assignment_value(
    value: Any,
    *,
    name: str,
    lower: float,
    upper: float,
) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(
            f"{name} must be between {lower} and {upper}"
        )
    return value


def _row_unresolved_statuses(
    pairs: Sequence[Any],
) -> tuple[str, ...]:
    statuses = tuple(sorted({
        str(_pair_value(pair, "status", ""))
        for pair in pairs
        if str(_pair_value(pair, "status", ""))
        in _IDENTITY_UNRESOLVED_STATUSES
    }))
    if (
        len(statuses) == 1
        and pairs
        and all(
            str(_pair_value(pair, "status", "")) == statuses[0]
            for pair in pairs
        )
    ):
        return statuses
    return statuses


def _assignment_backend(
    pairs: Sequence[Any],
    registry: Optional[SubjectRegistry],
    subject_key: Any,
) -> Optional[str]:
    for pair in pairs:
        backend = _pair_value(pair, "identity_backend")
        if backend is not None:
            return str(backend)
    if registry is not None:
        record = registry.get_subject(subject_key)
        if record is not None:
            backend = record.get("identity_backend")
            if backend is not None:
                return str(backend)
    return None


def _make_assignment_result(
    subject_key: Any,
    query: str,
    pairs: Sequence[Any],
    *,
    assigned: bool,
    candidate_index: Optional[int] = None,
    identity_similarity: Optional[float] = None,
    status: str,
    registry: Optional[SubjectRegistry],
    unresolved_statuses: Sequence[str] = (),
) -> SubjectCandidateAssignment:
    return SubjectCandidateAssignment(
        subject_key=subject_key,
        dino_query=query,
        assigned=assigned,
        candidate_index=candidate_index,
        identity_similarity=identity_similarity,
        status=status,
        identity_backend=_assignment_backend(pairs, registry, subject_key),
        unresolved_statuses=tuple(unresolved_statuses),
    )


def _validate_assignment_uniqueness(
    assignments: Mapping[Any, int],
) -> None:
    assigned_candidates = list(assignments.values())
    if len(assigned_candidates) != len(set(assigned_candidates)):
        raise AssertionError("one-to-one assignment reused a candidate")
    if len(assignments) != len(set(assignments)):
        raise AssertionError("one-to-one assignment reused a subject")


def assign_subject_candidates(
    identity_matrices: Mapping[str, IdentityScoreMatrix],
    registry: SubjectRegistry | Mapping[Any, Mapping[str, Any]] | None = None,
    *,
    identity_threshold: Optional[float] = None,
    identity_margin: Optional[float] = None,
) -> dict[Any, SubjectCandidateAssignment]:
    """Assign eligible identity scores one-to-one within each query group.

    This function consumes only Step 4 results. It performs no model calls,
    score computation, candidate mutation, or registry state update.
    """

    if identity_matrices is None:
        return {}
    if not isinstance(identity_matrices, Mapping):
        raise TypeError("identity_matrices must be a mapping")

    normalized_registry = (
        _as_subject_registry(registry)
        if registry is not None
        else None
    )
    explicit_threshold = (
        _validated_assignment_value(
            identity_threshold,
            name="identity_threshold",
            lower=-1.0,
            upper=1.0,
        )
        if identity_threshold is not None
        else None
    )
    effective_margin = _validated_assignment_value(
        DEFAULT_IDENTITY_MARGIN if identity_margin is None else identity_margin,
        name="identity_margin",
        lower=0.0,
        upper=2.0,
    )

    results: dict[Any, SubjectCandidateAssignment] = {}
    seen_subjects: set[Any] = set()
    for query_key, matrix in identity_matrices.items():
        query = str(_matrix_value(matrix, "dino_query", query_key)).strip()
        if not query:
            raise ValueError("identity matrix query must not be empty")

        subject_keys = tuple(_matrix_value(matrix, "subject_keys", ()))
        candidate_indices = tuple(
            _matrix_value(matrix, "candidate_indices", ())
        )
        if len(subject_keys) != len(set(subject_keys)):
            raise ValueError(
                f"duplicate subject keys in identity matrix {query!r}"
            )
        if len(candidate_indices) != len(set(candidate_indices)):
            raise ValueError(
                f"duplicate candidate indices in identity matrix {query!r}"
            )
        duplicate_subjects = seen_subjects.intersection(subject_keys)
        if duplicate_subjects:
            raise ValueError(
                "subject appears in multiple identity query groups: "
                f"{sorted(map(str, duplicate_subjects))}"
            )
        seen_subjects.update(subject_keys)

        if normalized_registry is not None:
            for subject_key in subject_keys:
                if normalized_registry.get_subject(subject_key) is None:
                    raise KeyError(
                        f"identity matrix references unknown subject: {subject_key!r}"
                    )

        scores = _matrix_value(matrix, "scores", {})
        if not isinstance(scores, Mapping):
            raise ValueError(f"identity matrix {query!r} has invalid scores")

        pairs_by_subject: dict[Any, list[Any]] = {}
        eligible_by_subject: dict[Any, dict[int, float]] = {}
        pair_by_subject_candidate: dict[Any, dict[int, Any]] = {}
        for subject_key in subject_keys:
            if subject_key not in scores:
                raise ValueError(
                    f"identity matrix {query!r} is missing subject row "
                    f"{subject_key!r}"
                )
            row = scores[subject_key]
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"identity matrix {query!r} has invalid row "
                    f"{subject_key!r}"
                )
            if set(row) != set(candidate_indices):
                raise ValueError(
                    f"identity matrix {query!r} row {subject_key!r} "
                    "does not match candidate columns"
                )
            row_pairs = []
            eligible: dict[int, float] = {}
            pair_lookup: dict[int, Any] = {}
            for candidate_index in candidate_indices:
                pair = row[candidate_index]
                pair_subject = _pair_value(pair, "subject_key")
                pair_candidate = _pair_value(pair, "candidate_index")
                if (
                    pair_subject is not None
                    and pair_subject != subject_key
                ):
                    raise ValueError(
                        f"identity pair subject mismatch for {subject_key!r}"
                    )
                if (
                    pair_candidate is not None
                    and pair_candidate != candidate_index
                ):
                    raise ValueError(
                        f"identity pair candidate mismatch for {candidate_index!r}"
                    )
                row_pairs.append(pair)
                pair_lookup[candidate_index] = pair
                status = str(_pair_value(pair, "status", ""))
                similarity = _pair_value(pair, "identity_similarity")
                evaluated = bool(_pair_value(pair, "evaluated", False))
                try:
                    numeric_similarity = float(similarity)
                except (TypeError, ValueError):
                    numeric_similarity = math.nan
                if (
                    evaluated
                    and status in _IDENTITY_SCORE_STATUSES
                    and similarity is not None
                    and math.isfinite(numeric_similarity)
                ):
                    eligible[candidate_index] = numeric_similarity
            pairs_by_subject[subject_key] = row_pairs
            eligible_by_subject[subject_key] = eligible
            pair_by_subject_candidate[subject_key] = pair_lookup

        threshold = explicit_threshold
        if threshold is None:
            matrix_threshold = _matrix_value(matrix, "identity_threshold")
            threshold = _validated_assignment_value(
                DEFAULT_IDENTITY_CONFIDENCE
                if matrix_threshold is None
                else matrix_threshold,
                name="identity_threshold",
                lower=-1.0,
                upper=1.0,
            )
        thresholded_edges = {
            subject_key: {
                candidate_index: score
                for candidate_index, score in eligible.items()
                if score >= threshold
            }
            for subject_key, eligible in eligible_by_subject.items()
        }
        eligible_edge_count = sum(
            len(edges) for edges in thresholded_edges.values()
        )
        _continuity_log(
            f"Step 5: assignment start query={query!r} "
            f"subjects={len(subject_keys)} candidates={len(candidate_indices)} "
            f"eligible_edges={eligible_edge_count} "
            f"threshold={threshold:.3f} margin={effective_margin:.3f}"
        )

        subject_tokens = {
            subject_key: f"subject_{index}"
            for index, subject_key in enumerate(subject_keys)
        }
        token_subjects = {
            token: subject_key
            for subject_key, token in subject_tokens.items()
        }
        token_edges = {
            subject_tokens[subject_key]: edges
            for subject_key, edges in thresholded_edges.items()
            if edges
        }
        token_assignments = _maximum_weight_assignment(
            tuple(token_edges),
            token_edges,
        )
        assignments = {
            token_subjects[token]: candidate_index
            for token, candidate_index in token_assignments.items()
        }
        _validate_assignment_uniqueness(assignments)
        _continuity_log(
            f"Step 5: global one-to-one assignment query={query!r} "
            f"selected={len(assignments)}"
        )
        for subject_key, candidate_index in assignments.items():
            _continuity_log(
                f"Step 5: provisional ownership subject={subject_key!r} "
                f"candidate={candidate_index} "
                f"similarity={thresholded_edges[subject_key][candidate_index]:.3f}"
            )
        assigned_subject_by_candidate = {
            candidate_index: subject_key
            for subject_key, candidate_index in assignments.items()
        }

        # Margin checks happen only after global assignment. Alternatives that
        # are already occupied by another assigned subject/candidate do not
        # count as still-available competing ownership decisions.
        ambiguous_subjects: set[Any] = set()
        for subject_key, candidate_index in assignments.items():
            selected_score = thresholded_edges[subject_key][candidate_index]
            free_row_alternatives = [
                score
                for alternative_index, score in thresholded_edges[
                    subject_key
                ].items()
                if (
                    alternative_index != candidate_index
                    and alternative_index not in assigned_subject_by_candidate
                )
            ]
            if free_row_alternatives and (
                selected_score - max(free_row_alternatives)
                < effective_margin
            ):
                ambiguous_subjects.add(subject_key)

            free_candidate_alternatives = [
                (alternative_subject, score)
                for alternative_subject, edges in thresholded_edges.items()
                for alternative_index, score in edges.items()
                if (
                    alternative_index == candidate_index
                    and alternative_subject != subject_key
                    and alternative_subject not in assignments
                )
            ]
            if free_candidate_alternatives:
                best_alternative_subject, best_alternative_score = max(
                    free_candidate_alternatives,
                    key=lambda item: item[1],
                )
                if selected_score - best_alternative_score < effective_margin:
                    ambiguous_subjects.add(subject_key)
                    ambiguous_subjects.add(best_alternative_subject)

        for subject_key in subject_keys:
            row_pairs = pairs_by_subject[subject_key]
            if subject_key in assignments and subject_key not in ambiguous_subjects:
                candidate_index = assignments[subject_key]
                pair = pair_by_subject_candidate[subject_key][candidate_index]
                results[subject_key] = _make_assignment_result(
                    subject_key,
                    query,
                    row_pairs,
                    assigned=True,
                    candidate_index=candidate_index,
                    identity_similarity=float(
                        _pair_value(pair, "identity_similarity")
                    ),
                    status="identity_assigned",
                    registry=normalized_registry,
                )
                _continuity_log(
                    f"Step 5: assigned subject={subject_key!r} "
                    f"candidate={candidate_index} query={query!r}"
                )
                continue
            if subject_key in ambiguous_subjects:
                results[subject_key] = _make_assignment_result(
                    subject_key,
                    query,
                    row_pairs,
                    assigned=False,
                    status="ambiguous_identity",
                    registry=normalized_registry,
                )
                _continuity_log(
                    f"Step 5: ambiguous ownership subject={subject_key!r} "
                    f"query={query!r}; assignment rejected after margin check"
                )
                continue

            unresolved_statuses = _row_unresolved_statuses(row_pairs)
            if len(unresolved_statuses) == 1 and all(
                str(_pair_value(pair, "status", "")) == unresolved_statuses[0]
                for pair in row_pairs
            ):
                status = unresolved_statuses[0]
                preserved_statuses: tuple[str, ...] = ()
            else:
                status = "no_eligible_candidate"
                preserved_statuses = unresolved_statuses
            results[subject_key] = _make_assignment_result(
                subject_key,
                query,
                row_pairs,
                assigned=False,
                status=status,
                registry=normalized_registry,
                unresolved_statuses=preserved_statuses,
            )
            _continuity_log(
                f"Step 5: unresolved subject={subject_key!r} "
                f"query={query!r} status={status}"
            )

    return results


def _backward_frame_indices(
    frame_count: int,
    interval: int,
    maximum: int,
    frame_rate: float = DEFAULT_FRAME_RATE,
    max_state_age_seconds: Optional[float] = None,
) -> tuple[tuple[int, ...], bool]:
    """Return newest-first frame indices and whether a cap truncated them.

    A frame is treated as covering the interval ending at ``(index + 1) /
    frame_rate``.  This makes a one-second window at 24 fps include frames
    ``final_frame - 24`` through ``final_frame``, matching the rendered
    segment's end boundary.
    """

    frame_count = int(frame_count)
    interval = int(interval)
    maximum = int(maximum)
    frame_rate = float(frame_rate)
    if frame_count <= 0:
        return tuple(), False
    if interval <= 0:
        raise ValueError("frame_search_interval must be greater than zero")
    if maximum <= 0:
        raise ValueError("max_candidate_frames must be greater than zero")
    if frame_rate <= 0.0:
        raise ValueError("frame_rate must be greater than zero")

    indices = list(range(frame_count - 1, -1, -interval))
    if max_state_age_seconds is not None:
        max_state_age_seconds = float(max_state_age_seconds)
        if not math.isfinite(max_state_age_seconds) or max_state_age_seconds <= 0.0:
            raise ValueError("max_state_age_seconds must be greater than zero")
        video_end = frame_count / frame_rate
        oldest_allowed = video_end - max_state_age_seconds
        indices = [
            index
            for index in indices
            if (index + 1) / frame_rate >= oldest_allowed - 1e-9
        ]
    elif indices[-1] != 0:
        indices.append(0)
    limited = len(indices) > maximum
    return tuple(indices[:maximum]), limited


def state_recency_boundary(
    frame_count: int,
    config: ContinuityReferenceConfig,
) -> tuple[float, float]:
    """Return the rendered segment end and oldest permitted state times."""

    video_end = int(frame_count) / float(config.frame_rate)
    return video_end, video_end - float(config.max_state_age_seconds)


def filter_candidates_to_state_recency_window(
    candidates: Sequence[Any],
    config: ContinuityReferenceConfig,
    *,
    frame_count: Optional[int] = None,
) -> list[Any]:
    """Drop fallback candidates older than the shared rendered-state window.

    Step 6 annotates candidates with the exact boundary it used.  The
    ``frame_count`` fallback also validates externally supplied evidence when
    the caller can provide the rendered segment length.
    """

    fallback_oldest = None
    if frame_count is not None:
        _video_end, fallback_oldest = state_recency_boundary(frame_count, config)

    filtered = []
    for candidate in candidates or ():
        metadata = getattr(candidate, "source_metadata", {})
        if isinstance(candidate, Mapping):
            metadata = candidate.get("source_metadata", metadata)
        metadata = metadata or {}
        try:
            frame_index = metadata.get("frame_index")
            if frame_index is not None:
                oldest_allowed = fallback_oldest
                if oldest_allowed is None:
                    oldest_allowed = metadata.get(
                        "state_recency_oldest_allowed_seconds"
                    )
                if oldest_allowed is not None:
                    candidate_end = (int(frame_index) + 1) / float(
                        config.frame_rate
                    )
                    if candidate_end < float(oldest_allowed) - 1e-9:
                        continue
            elif fallback_oldest is not None:
                timestamp = metadata.get("timestamp")
                if timestamp is not None and float(timestamp) < fallback_oldest:
                    continue
        except (TypeError, ValueError):
            # Malformed evidence cannot be used to bypass the recency limit.
            continue
        filtered.append(candidate)
    return filtered


class _CurrentStateRegistryUpdateError(RuntimeError):
    """The image was written but registry path commit failed."""


def _commit_current_state_crop(
    registry: SubjectRegistry,
    subject_key: Any,
    crop: Image.Image,
    output_directory: os.PathLike[str] | str,
) -> str:
    """Persist one validated crop, then commit its registry path."""

    output_path = registry.current_state_path(subject_key, output_directory)
    _continuity_log(
        f"state commit: subject={subject_key!r} destination={output_path}"
    )
    # _save_crop_atomically validates the staged PNG before os.replace, so a
    # failed encode or invalid image cannot damage the existing destination.
    _save_crop_atomically(crop, output_path)
    try:
        updated = registry.update_current_state(subject_key, output_path)
    except Exception as error:
        raise _CurrentStateRegistryUpdateError(
            f"registry current-state update failed for {subject_key!r}: {error}"
        ) from error
    if not updated:
        raise _CurrentStateRegistryUpdateError(
            f"registry current-state update failed for {subject_key!r}"
        )
    _continuity_log(
        f"state commit: registry current-state reference updated "
        f"subject={subject_key!r}"
    )
    return os.path.abspath(output_path)


def _save_detected_vision_frame(
    crop: Image.Image,
    registry: SubjectRegistry,
    subject_key: Any,
    segment_number: int,
    frame_index: int,
    output_directory: str | os.PathLike[str],
) -> str:
    """Save the accepted DINO crop using stable segment/subject/frame IDs."""

    record = registry.get_subject(subject_key) or {}
    subject_number = record.get("subject_id", subject_key)
    try:
        subject_number = f"{int(subject_number):04d}"
    except (TypeError, ValueError):
        subject_number = re.sub(
            r"[^A-Za-z0-9_-]+", "_", str(subject_number)
        ).strip("._") or "unknown"
    output_path = os.path.abspath(os.path.join(
        os.fspath(output_directory),
        (
            f"segment_{int(segment_number):04d}_"
            f"subject_{subject_number}_"
            f"frame_{int(frame_index):08d}.png"
        ),
    ))
    _save_crop_atomically(crop, output_path)
    _continuity_log(
        f"vision frame saved subject={subject_key!r} "
        f"segment={int(segment_number)} frame={int(frame_index)} "
        f"path={output_path}"
    )
    return output_path


def _step6_result(
    subject_key: Any,
    *,
    updated: bool,
    status: str,
    dino_query: Optional[str] = None,
    frame_index: Optional[int] = None,
    timestamp_seconds: Optional[float] = None,
    candidate_index: Optional[int] = None,
    identity_similarity: Optional[float] = None,
    output_path: Optional[str] = None,
    vision_frame_path: Optional[str] = None,
    identity_backend: Optional[str] = None,
    last_identity_status: Optional[str] = None,
    attempted_frames: int = 0,
    error: Optional[str] = None,
) -> SubjectReferenceUpdateResult:
    return SubjectReferenceUpdateResult(
        subject_key=subject_key,
        updated=updated,
        status=status,
        frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        dino_query=dino_query,
        candidate_index=candidate_index,
        identity_similarity=identity_similarity,
        output_path=output_path,
        vision_frame_path=vision_frame_path,
        identity_backend=identity_backend,
        last_identity_status=last_identity_status,
        attempted_frames=attempted_frames,
        error=error,
    )


def search_and_update_current_states(
    video_path: str | os.PathLike[str],
    registry: SubjectRegistry | Mapping[Any, Mapping[str, Any]],
    output_directory: str | os.PathLike[str],
    *,
    detector: Any = None,
    identity_validator: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    frame_count_fn: Optional[Callable[[str], int]] = None,
    frame_extractor: Optional[Callable[..., Any]] = None,
    update_subject_keys: Optional[Sequence[Any]] = None,
    identity_context_subject_keys: Optional[Sequence[Any]] = None,
    segment_number: Optional[int] = None,
    vision_frame_output_directory: Optional[str | os.PathLike[str]] = None,
    fallback_evidence: Optional[
        MutableMapping[str, list[DinoCandidate]]
    ] = None,
) -> dict[Any, SubjectReferenceUpdateResult]:
    """Find each subject's latest valid rendered state in one shared search.

    Frames are processed newest-to-oldest. A subject is committed immediately
    after its first valid Step 5 assignment; later frames cannot replace it.
    Resolved subjects remain in the same-query identity context until every
    subject in that query is resolved or terminal, but only unresolved subjects
    can be committed.

    ``frame_count_fn`` and ``frame_extractor`` are injectable so this function
    can be tested without FFmpeg. When omitted, they are imported lazily from
    ``minimax`` to avoid a module import cycle.

    When fallback_evidence is supplied, each evaluated query also retains
    valid low-confidence whole-subject candidates in that in-memory mapping.
    This never changes deterministic Step 3/4/5 eligibility or assignment.
    """

    config = config or ContinuityReferenceConfig()
    normalized_registry = _as_subject_registry(registry)
    if not normalized_registry:
        return {}

    if frame_count_fn is None or frame_extractor is None:
        # minimax imports this module, so this import must remain inside the
        # call rather than at module scope.
        from minimax import extract_video_frame, get_video_frame_count

        frame_count_fn = frame_count_fn or get_video_frame_count
        frame_extractor = frame_extractor or extract_video_frame

    requested_updates = _canonical_subject_keys(
        normalized_registry,
        update_subject_keys,
        "update_subject_keys",
    )
    requested_context = _canonical_subject_keys(
        normalized_registry,
        identity_context_subject_keys,
        "identity_context_subject_keys",
    )

    _continuity_log(
        "Step 6: rendered-state search start "
        f"subjects={len(normalized_registry)} "
        f"update_targets={len(requested_updates) if requested_updates is not None else 'all'} "
        f"identity_context={len(requested_context) if requested_context is not None else 'all'}"
    )

    # Keep identity-context membership independent from commit eligibility.
    # Unsupported backends are deferred before any DINO work.
    identity_context: set[Any] = set()
    unresolved: set[Any] = set()
    deferred_results: dict[Any, SubjectReferenceUpdateResult] = {}
    query_by_subject: dict[Any, str] = {}
    backend_by_subject: dict[Any, Optional[str]] = {}
    grouped_context: dict[str, list[Any]] = {}
    for subject_key, record in normalized_registry.items():
        query = subject_query(record)
        query_by_subject[subject_key] = query
        raw_backend = record.get("identity_backend", "insightface")
        backend = str(raw_backend).strip() if raw_backend is not None else None
        backend_by_subject[subject_key] = backend
        if backend is None or backend.casefold() != "insightface":
            if requested_updates is not None and subject_key not in requested_updates:
                deferred_results[subject_key] = _step6_result(
                    subject_key,
                    updated=False,
                    status="not_expected_visible",
                    dino_query=query,
                    identity_backend=backend,
                    last_identity_status="not_expected_visible",
                )
                continue
            deferred_results[subject_key] = _step6_result(
                subject_key,
                updated=False,
                status="identity_backend_unavailable",
                dino_query=query,
                identity_backend=backend,
                last_identity_status="identity_backend_unavailable",
            )
            _continuity_log(
                f"Step 6: subject={subject_key!r} query={query!r} "
                f"deferred status={deferred_results[subject_key].status} "
                f"backend={backend!r}"
            )
            continue
        is_update_target = (
            requested_updates is None or subject_key in requested_updates
        )
        is_context_subject = (
            (
                requested_updates is None
                if requested_context is None
                else subject_key in requested_context
            )
        )
        if is_context_subject or is_update_target:
            identity_context.add(subject_key)
            grouped_context.setdefault(query, []).append(subject_key)
        if is_update_target:
            unresolved.add(subject_key)
        else:
            deferred_results[subject_key] = _step6_result(
                subject_key,
                updated=False,
                status="not_expected_visible",
                dino_query=query,
                identity_backend=backend,
                last_identity_status="not_expected_visible",
            )
            _continuity_log(
                f"Step 6: subject={subject_key!r} query={query!r} "
                "retained as identity context but is not an update target"
            )

    results: dict[Any, SubjectReferenceUpdateResult] = dict(deferred_results)
    if not unresolved:
        _continuity_log("Step 6: no supported unresolved update targets")
        return results

    frame_count = int(frame_count_fn(os.fspath(video_path)))
    video_end_seconds, oldest_allowed_seconds = state_recency_boundary(
        frame_count,
        config,
    )
    _continuity_log(
        f"Step 6: state recency window={config.max_state_age_seconds:.3f}s"
    )
    _continuity_log(
        f"Step 6: video_end={video_end_seconds:.3f}s "
        f"oldest_allowed={oldest_allowed_seconds:.3f}s"
    )
    frame_indices, search_limited = _backward_frame_indices(
        frame_count,
        config.frame_search_interval,
        config.max_candidate_frames,
        config.frame_rate,
        config.max_state_age_seconds,
    )
    _continuity_log(
        f"Step 6: planned newest-first frames={frame_indices}"
    )
    if search_limited:
        _continuity_log(
            f"Step 6: max_candidate_frames={config.max_candidate_frames} "
            "limited the recency-window plan"
        )
    attempted_frames: dict[Any, int] = {key: 0 for key in unresolved}
    last_status: dict[Any, Optional[str]] = {
        key: None for key in unresolved
    }

    if not frame_indices:
        for subject_key in unresolved:
            results[subject_key] = _step6_result(
                subject_key,
                updated=False,
                status="not_found_in_segment",
                dino_query=query_by_subject[subject_key],
                identity_backend=backend_by_subject[subject_key],
            )
        _continuity_log("Step 6: no frames available; backward search complete")
        return results

    # Keep model construction lazy.  The concrete Step 3/4 functions cache
    # their default detector/validator, while tests can replace those stages
    # without importing either optional model runtime.
    shared_detector = detector
    shared_identity_validator = identity_validator

    with tempfile.TemporaryDirectory(prefix="dino_continuity_step6_") as temporary_directory:
        for ordinal, frame_index in enumerate(frame_indices):
            active_queries = tuple(
                query
                for query, subject_keys in grouped_context.items()
                if any(subject_key in unresolved for subject_key in subject_keys)
            )
            if not active_queries:
                _continuity_log(
                    f"Step 6: stopping traversal at frame={frame_index}; "
                    "all update targets resolved or terminal"
                )
                break

            active_subjects = {
                subject_key
                for query in active_queries
                for subject_key in grouped_context[query]
                if subject_key in unresolved
            }
            for subject_key in active_subjects:
                attempted_frames[subject_key] += 1

            timestamp = frame_index / float(config.frame_rate)
            frame_name = f"step6_{ordinal:04d}_frame_{frame_index:08d}.png"
            _continuity_log(
                f"Step 6: decode frame={frame_index} timestamp={timestamp:.3f} "
                f"active_queries={active_queries} active_subjects={len(active_subjects)}"
            )
            try:
                extracted = frame_extractor(
                    os.fspath(video_path),
                    frame_name,
                    input_directory=temporary_directory,
                    frame_index=frame_index,
                    temporary_prefix=".dino_step6_",
                    error_label=f"Grounding DINO Step 6 frame {frame_index}",
                )
                if isinstance(extracted, Image.Image):
                    frame_image = extracted.convert("RGB")
                else:
                    frame_image = _frame_image(
                        _frame_path(extracted, temporary_directory)
                    )
            except Exception as error:
                _continuity_log(
                    f"Step 6: frame={frame_index} extraction failed: {error}"
                )
                for subject_key in tuple(unresolved):
                    results[subject_key] = _step6_result(
                        subject_key,
                        updated=False,
                        status="search_error",
                        dino_query=query_by_subject[subject_key],
                        identity_backend=backend_by_subject[subject_key],
                        last_identity_status=last_status[subject_key],
                        attempted_frames=attempted_frames[subject_key],
                        error=str(error),
                    )
                    unresolved.discard(subject_key)
                break

            for query in active_queries:
                context_keys = tuple(
                    subject_key
                    for subject_key in grouped_context[query]
                    if subject_key in identity_context
                )
                if not context_keys:
                    continue
                context_registry = normalized_registry.subset(context_keys)
                source_metadata = {
                    "video_path": os.fspath(video_path),
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "state_recency_video_end_seconds": video_end_seconds,
                    "state_recency_oldest_allowed_seconds": oldest_allowed_seconds,
                }
                try:
                    shared_candidates = detect_shared_candidates(
                        frame_image,
                        context_registry,
                        detector=shared_detector,
                        config=config,
                        source_metadata=source_metadata,
                        retain_fallback_evidence=(
                            fallback_evidence is not None
                        ),
                    )
                    identity_matrices = build_identity_score_matrix(
                        shared_candidates,
                        context_registry,
                        identity_validator=shared_identity_validator,
                        identity_threshold=config.identity_confidence,
                    )
                    assignments = assign_subject_candidates(
                        identity_matrices,
                        context_registry,
                        identity_threshold=config.identity_confidence,
                        identity_margin=config.identity_margin,
                    )
                    query_candidates_for_log = shared_candidates.get(query)
                    _continuity_log(
                        f"Step 6: frame={frame_index} query={query!r} "
                        f"detection_candidates={len(getattr(query_candidates_for_log, 'candidates', ())) if query_candidates_for_log is not None else 0} "
                        f"assignments={sum(1 for item in assignments.values() if item.assigned)}"
                    )
                except (IdentityModelError, OSError, RuntimeError) as error:
                    _continuity_log(
                        f"Step 6: frame={frame_index} query={query!r} "
                        f"identity/search failed: {error}"
                    )
                    for subject_key in tuple(unresolved):
                        if query_by_subject[subject_key] != query:
                            continue
                        results[subject_key] = _step6_result(
                            subject_key,
                            updated=False,
                            status="search_error",
                            dino_query=query,
                            identity_backend=backend_by_subject[subject_key],
                            last_identity_status=last_status[subject_key],
                            attempted_frames=attempted_frames[subject_key],
                            error=str(error),
                        )
                        unresolved.discard(subject_key)
                        identity_context.discard(subject_key)
                    continue

                query_candidates = shared_candidates.get(query)
                if query_candidates is None:
                    raise ValueError(
                        f"Step 3 did not return active query group {query!r}"
                    )
                if fallback_evidence is not None:
                    retained = list(
                        getattr(query_candidates, "fallback_candidates", ())
                    )
                    if retained:
                        fallback_evidence.setdefault(query, []).extend(retained)
                        _continuity_log(
                            f"Step 6: retained fallback evidence query={query!r} "
                            f"frame={frame_index} candidates={len(retained)}"
                        )
                candidates_by_index = {
                    candidate.candidate_index: candidate
                    for candidate in query_candidates.candidates
                }
                if len(candidates_by_index) != len(query_candidates.candidates):
                    raise ValueError(
                        f"duplicate Step 3 candidate index in query {query!r}"
                    )

                terminal_statuses = {
                    "identity_backend_unavailable",
                    "canonical_face_not_found",
                    "identity_model_error",
                }
                for subject_key in tuple(unresolved):
                    if query_by_subject[subject_key] != query:
                        continue
                    assignment = assignments.get(subject_key)
                    if assignment is None:
                        raise ValueError(
                            f"Step 5 returned no result for subject {subject_key!r}"
                        )
                    last_status[subject_key] = assignment.status
                    if assignment.assigned:
                        candidate_index = assignment.candidate_index
                        if candidate_index not in candidates_by_index:
                            raise ValueError(
                                "Step 5 assigned a candidate absent from Step 3 "
                                f"query {query!r}: {candidate_index!r}"
                            )
                        candidate = candidates_by_index[candidate_index]
                        vision_frame_path = None
                        try:
                            output_path = _commit_current_state_crop(
                                normalized_registry,
                                subject_key,
                                candidate.crop,
                                output_directory,
                            )
                            if (
                                segment_number is not None
                                and vision_frame_output_directory is not None
                            ):
                                vision_frame_path = _save_detected_vision_frame(
                                    candidate.crop,
                                    normalized_registry,
                                    subject_key,
                                    segment_number,
                                    frame_index,
                                    vision_frame_output_directory,
                                )
                        except Exception as error:
                            _continuity_log(
                                f"Step 6: subject={subject_key!r} frame={frame_index} "
                                f"candidate={candidate_index} commit failed: {error}"
                            )
                            results[subject_key] = _step6_result(
                                subject_key,
                                updated=False,
                                status=(
                                    "current_state_registry_update_failed"
                                    if isinstance(
                                        error,
                                        _CurrentStateRegistryUpdateError,
                                    )
                                    else "current_state_save_failed"
                                ),
                                dino_query=query,
                                frame_index=frame_index,
                                timestamp_seconds=timestamp,
                                candidate_index=candidate_index,
                                identity_similarity=assignment.identity_similarity,
                                identity_backend=assignment.identity_backend,
                                last_identity_status=assignment.status,
                                attempted_frames=attempted_frames[subject_key],
                                error=str(error),
                            )
                            unresolved.discard(subject_key)
                            identity_context.discard(subject_key)
                            continue
                        results[subject_key] = _step6_result(
                            subject_key,
                            updated=True,
                            status="updated",
                            dino_query=query,
                            frame_index=frame_index,
                            timestamp_seconds=timestamp,
                            candidate_index=candidate_index,
                            identity_similarity=assignment.identity_similarity,
                            output_path=output_path,
                            vision_frame_path=vision_frame_path,
                            identity_backend=assignment.identity_backend,
                            last_identity_status=assignment.status,
                            attempted_frames=attempted_frames[subject_key],
                        )
                        _continuity_log(
                            f"Step 6: subject={subject_key!r} resolved at first valid "
                            f"frame={frame_index} candidate={candidate_index} "
                            f"similarity={assignment.identity_similarity:.3f}"
                        )
                        unresolved.discard(subject_key)
                        # Keep the resolved subject in identity_context while
                        # other subjects in the same query remain unresolved.
                        continue
                    if assignment.status in terminal_statuses:
                        results[subject_key] = _step6_result(
                            subject_key,
                            updated=False,
                            status=assignment.status,
                            dino_query=query,
                            identity_backend=assignment.identity_backend,
                            last_identity_status=assignment.status,
                            attempted_frames=attempted_frames[subject_key],
                        )
                        _continuity_log(
                            f"Step 6: subject={subject_key!r} terminal status="
                            f"{assignment.status} at frame={frame_index}"
                        )
                        unresolved.discard(subject_key)
                        identity_context.discard(subject_key)

            if not unresolved:
                break

    for subject_key in tuple(unresolved):
        status = "search_limit_reached" if search_limited else "not_found_in_segment"
        results[subject_key] = _step6_result(
            subject_key,
            updated=False,
            status=status,
            dino_query=query_by_subject[subject_key],
            identity_backend=backend_by_subject[subject_key],
            last_identity_status=last_status[subject_key],
            attempted_frames=attempted_frames[subject_key],
        )
        _continuity_log(
            f"Step 6: subject={subject_key!r} search complete status={status} "
            f"attempted_frames={attempted_frames[subject_key]}"
        )
        _continuity_log(
            f"Step 6: subject={subject_key!r} no usable state within final "
            f"{config.max_state_age_seconds:.3f}s; preserving previous state"
        )

    _continuity_log(
        f"Step 6: rendered-state search complete results={len(results)}"
    )
    return results


# Descriptive compatibility alias for callers that name the operation after
# the subject-level reference update rather than the registry state it writes.
search_and_update_subject_references = search_and_update_current_states


def _accepted_result(
    selected: dict[str, Any],
    candidate_image: Image.Image,
    frame_index: int,
    timestamp: float,
    output_path: str,
    query: str,
    attempts: Sequence[dict[str, Any]],
    identity_selection: Any = None,
) -> ContinuityReferenceResult:
    detection = selected["detection"]
    matched_phrase = str(
        _detection_value(
            detection,
            "matched_phrase",
            _detection_value(detection, "phrase", query),
        )
    )
    return ContinuityReferenceResult(
        found=True,
        ambiguous=False,
        reason="accepted",
        confidence=float(_detection_value(detection, "confidence", 0.0)),
        bbox=selected["bbox"],
        crop_bbox=selected["crop_bbox"],
        frame_index=frame_index,
        timestamp=timestamp,
        image_width=candidate_image.width,
        image_height=candidate_image.height,
        bbox_width=selected["bbox_width"],
        bbox_height=selected["bbox_height"],
        bbox_area_ratio=selected["area_ratio"],
        touches_frame_edge=selected["touches_edge"],
        crop_width=selected["crop_width"],
        crop_height=selected["crop_height"],
        matched_phrase=matched_phrase,
        output_path=os.path.abspath(output_path),
        identity_status=(identity_selection.reason if identity_selection else None),
        identity_similarity=(
            identity_selection.identity_similarity if identity_selection else None
        ),
        identity_threshold=(
            identity_selection.identity_threshold if identity_selection else None
        ),
        identity_margin=(
            identity_selection.identity_margin if identity_selection else None
        ),
        identity_candidate_index=(
            identity_selection.candidate_index if identity_selection else None
        ),
        identity_face_bbox=(
            identity_selection.face_bbox if identity_selection else None
        ),
        identity_candidates=(
            tuple(item.to_dict() for item in identity_selection.candidates)
            if identity_selection else tuple()
        ),
        attempts=tuple(attempts),
    )


def _failure_reason(reasons: set[str]) -> str:
    for reason in (
        "identity_backend_unavailable",
        "identity_model_error",
        "canonical_face_not_found",
        "ambiguous_canonical_reference",
        "ambiguous_identity",
        "identity_mismatch",
        "ambiguous_candidate_faces",
        "not_evaluated_no_face",
    ):
        if reason in reasons:
            return reason
    if "multiple_matching_subjects" in reasons:
        return "multiple_matching_subjects"
    if "subject_too_small" in reasons:
        return "subject_too_small"
    if "below_confidence_threshold" in reasons:
        return "below_confidence_threshold"
    if "no_detection" in reasons:
        return "no_detection"
    return "no_usable_candidate_frame"


def search_and_save_reference(
    video_path: str,
    query: str,
    output_path: str,
    *,
    detector: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    frame_count_fn: Callable[[str], int],
    frame_extractor: Callable[..., Any],
    identity_validator: Any = None,
    canonical_reference: Any = None,
    subject_identifier: Optional[str] = None,
) -> ContinuityReferenceResult:
    """Find and save the newest high-confidence, identity-valid subject crop."""

    config = config or ContinuityReferenceConfig()
    detector = detector or get_detector(device=config.dino_device)
    query = str(query).strip()
    if not query:
        raise ValueError("query must not be empty")
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"Rendered video is missing: {video_path!r}")

    frame_count = int(frame_count_fn(video_path))
    if frame_count <= 0:
        return ContinuityReferenceResult(
            found=False,
            ambiguous=False,
            reason="no_usable_candidate_frame",
        )

    identity_engine = (
        identity_validator is not None
        and hasattr(identity_validator, "select_candidate")
        and canonical_reference is not None
    )
    canonical_subject = str(subject_identifier or query)
    canonical_result = None
    if identity_engine:
        try:
            canonical_result = identity_validator.prepare_canonical(
                canonical_subject,
                canonical_reference,
            )
        except (FileNotFoundError, IdentityModelError, OSError, ValueError) as error:
            return ContinuityReferenceResult(
                found=False,
                ambiguous=False,
                reason="identity_model_error",
                identity_status="identity_model_error",
                attempts=({"reason": "identity_model_error", "error": str(error)},),
            )
        if not canonical_result.matched:
            return ContinuityReferenceResult(
                found=False,
                ambiguous=canonical_result.reason == "ambiguous_canonical_reference",
                reason=canonical_result.reason,
                identity_status=canonical_result.reason,
                identity_threshold=config.identity_confidence,
                identity_margin=config.identity_margin,
                attempts=(canonical_result.to_dict(),),
            )

    attempts: list[dict[str, Any]] = []
    reasons: set[str] = set()
    last_identity_selection = None
    with tempfile.TemporaryDirectory(prefix="dino_continuity_") as temporary_directory:
        for ordinal in range(config.max_candidate_frames):
            frame_index = frame_count - 1 - ordinal * config.frame_search_interval
            if frame_index < 0:
                break
            timestamp = frame_index / config.frame_rate
            frame_name = f"candidate_{ordinal:03d}_{frame_index:08d}.png"
            try:
                extracted = frame_extractor(
                    video_path,
                    frame_name,
                    input_directory=temporary_directory,
                    frame_index=frame_index,
                    temporary_prefix=".dino_",
                    error_label=f"Grounding DINO candidate frame {frame_index}",
                )
                candidate_path = _frame_path(extracted, temporary_directory)
                with Image.open(candidate_path) as opened:
                    candidate_image = opened.convert("RGB")
            except Exception as error:
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": "frame_unusable",
                    "error": str(error),
                })
                continue

            # Detector/model errors are not frame-quality failures. Let them
            # reach update_subject_references so a missing dependency or a
            # failed model download is reported once instead of being retried
            # for every older candidate frame.
            detector_result = detector.detect(
                candidate_image,
                query,
                config.box_threshold,
                config.text_threshold,
            )

            detections = _result_detections(detector_result)
            qualifying = [
                detection
                for detection in detections
                if float(_detection_value(detection, "confidence", 0.0))
                >= config.dino_confidence
            ]
            if not qualifying:
                reason = "below_confidence_threshold" if detections else "no_detection"
                reasons.add(reason)
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": reason,
                    "detection_count": len(detections),
                })
                continue
            if len(qualifying) >= 2 and not identity_engine:
                reasons.add("multiple_matching_subjects")
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": "multiple_matching_subjects",
                    "detection_count": len(qualifying),
                })
                continue

            image_width, image_height = candidate_image.size
            prepared = []
            for candidate_index, detection in enumerate(qualifying):
                raw_bbox = _detection_value(detection, "bbox")
                try:
                    bbox = [int(round(float(value))) for value in raw_bbox]
                except (TypeError, ValueError):
                    bbox = []
                if len(bbox) != 4:
                    attempts.append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "candidate_index": candidate_index,
                        "reason": "frame_unusable",
                        "error": "detector returned an invalid bbox",
                    })
                    continue
                # The reusable detector already returns clamped pixel boxes,
                # but keep adapter/test implementations inside image bounds.
                bbox = [
                    max(0, min(image_width, bbox[0])),
                    max(0, min(image_height, bbox[1])),
                    max(0, min(image_width, bbox[2])),
                    max(0, min(image_height, bbox[3])),
                ]
                x1, y1, x2, y2 = bbox
                bbox_width = max(0, x2 - x1)
                bbox_height = max(0, y2 - y1)
                area_ratio = (bbox_width * bbox_height) / float(image_width * image_height)
                if area_ratio < config.min_bbox_area_ratio:
                    reasons.add("subject_too_small")
                    attempts.append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "candidate_index": candidate_index,
                        "reason": "subject_too_small",
                        "confidence": float(_detection_value(detection, "confidence", 0.0)),
                        "bbox_area_ratio": area_ratio,
                    })
                    continue
                crop_bbox = _padded_crop_bbox(
                    bbox,
                    image_width,
                    image_height,
                    config.crop_padding_x,
                    config.crop_padding_y,
                )
                crop_width = crop_bbox[2] - crop_bbox[0]
                crop_height = crop_bbox[3] - crop_bbox[1]
                if crop_width <= 0 or crop_height <= 0:
                    attempts.append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "candidate_index": candidate_index,
                        "reason": "frame_unusable",
                        "error": "padded crop has no area",
                    })
                    continue
                prepared.append({
                    "candidate_index": candidate_index,
                    "detection": detection,
                    "bbox": bbox,
                    "crop_bbox": crop_bbox,
                    "crop": candidate_image.crop(tuple(crop_bbox)),
                    "bbox_width": bbox_width,
                    "bbox_height": bbox_height,
                    "area_ratio": area_ratio,
                    "touches_edge": (
                        x1 <= 0 or y1 <= 0 or x2 >= image_width or y2 >= image_height
                    ),
                    "crop_width": crop_width,
                    "crop_height": crop_height,
                })

            if not prepared:
                continue

            identity_selection = None
            if identity_engine:
                identity_candidates = tuple(
                    IdentityCandidate(
                        candidate_index=item["candidate_index"],
                        image=item["crop"],
                        dino_confidence=float(
                            _detection_value(item["detection"], "confidence", 0.0)
                        ),
                        bbox=item["bbox"],
                        crop_bbox=item["crop_bbox"],
                    )
                    for item in prepared
                )
                try:
                    identity_selection = identity_validator.select_candidate(
                        canonical_subject,
                        canonical_reference,
                        identity_candidates,
                        identity_threshold=config.identity_confidence,
                        identity_margin=config.identity_margin,
                    )
                except (IdentityModelError, OSError, ValueError) as error:
                    reasons.add("identity_model_error")
                    attempts.append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "reason": "identity_model_error",
                        "error": str(error),
                    })
                    continue
                last_identity_selection = identity_selection
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": identity_selection.reason,
                    "identity": identity_selection.to_dict(),
                })
                if not identity_selection.matched:
                    reasons.add(identity_selection.reason)
                    continue
                selected_index = identity_selection.candidate_index
                selected = next(
                    item for item in prepared
                    if item["candidate_index"] == selected_index
                )
            else:
                if len(prepared) >= 2:
                    reasons.add("multiple_matching_subjects")
                    continue
                selected = prepared[0]
                if identity_validator:
                    identity_status = identity_validator(
                        selected["crop"],
                        canonical_reference,
                    )
                    if identity_status is False:
                        reasons.add("identity_mismatch")
                        attempts.append({
                            "frame_index": frame_index,
                            "timestamp": timestamp,
                            "reason": "identity_mismatch",
                        })
                        continue

            detection = selected["detection"]
            bbox = selected["bbox"]
            crop_bbox = selected["crop_bbox"]
            crop = selected["crop"]

            _save_crop_atomically(crop, output_path)
            confidence = float(_detection_value(detection, "confidence", 0.0))
            matched_phrase = str(
                _detection_value(
                    detection,
                    "matched_phrase",
                    _detection_value(detection, "phrase", query),
                )
            )
            return ContinuityReferenceResult(
                found=True,
                ambiguous=False,
                reason="accepted",
                confidence=confidence,
                bbox=bbox,
                crop_bbox=crop_bbox,
                frame_index=frame_index,
                timestamp=timestamp,
                image_width=image_width,
                image_height=image_height,
                bbox_area_ratio=selected["area_ratio"],
                bbox_width=selected["bbox_width"],
                bbox_height=selected["bbox_height"],
                touches_frame_edge=selected["touches_edge"],
                crop_width=selected["crop_width"],
                crop_height=selected["crop_height"],
                matched_phrase=matched_phrase,
                output_path=os.path.abspath(output_path),
                identity_status=(
                    identity_selection.reason if identity_selection else None
                ),
                identity_similarity=(
                    identity_selection.identity_similarity
                    if identity_selection else None
                ),
                identity_threshold=(
                    identity_selection.identity_threshold
                    if identity_selection else None
                ),
                identity_margin=(
                    identity_selection.identity_margin
                    if identity_selection else None
                ),
                identity_candidate_index=(
                    identity_selection.candidate_index
                    if identity_selection else None
                ),
                identity_face_bbox=(
                    identity_selection.face_bbox if identity_selection else None
                ),
                identity_candidates=(
                    tuple(item.to_dict() for item in identity_selection.candidates)
                    if identity_selection else tuple()
                ),
                attempts=tuple(attempts),
            )

    return ContinuityReferenceResult(
        found=False,
        ambiguous=bool(
            reasons.intersection({
                "multiple_matching_subjects",
                "ambiguous_identity",
                "ambiguous_candidate_faces",
                "ambiguous_canonical_reference",
            })
        ),
        reason=_failure_reason(reasons),
        identity_status=(
            last_identity_selection.reason if last_identity_selection else None
        ),
        identity_similarity=(
            last_identity_selection.identity_similarity
            if last_identity_selection else None
        ),
        identity_threshold=(
            last_identity_selection.identity_threshold
            if last_identity_selection else None
        ),
        identity_margin=(
            last_identity_selection.identity_margin
            if last_identity_selection else None
        ),
        identity_candidate_index=(
            last_identity_selection.candidate_index
            if last_identity_selection else None
        ),
        identity_face_bbox=(
            last_identity_selection.face_bbox if last_identity_selection else None
        ),
        identity_candidates=(
            tuple(item.to_dict() for item in last_identity_selection.candidates)
            if last_identity_selection else tuple()
        ),
        attempts=tuple(attempts),
    )


def search_and_save_references(
    video_path: str,
    subjects: SubjectRegistry | Mapping[Any, Mapping[str, Any]],
    output_directory: str,
    query: str,
    *,
    detector: Any = None,
    identity_validator: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    frame_count_fn: Callable[[str], int],
    frame_extractor: Callable[..., Any],
) -> dict[Any, ContinuityReferenceResult]:
    """Search one shared DINO query and assign candidates to subjects once.

    Subjects that remain unresolved continue searching older frames
    independently within this query group. DINO is still invoked once per
    query/frame, and identity assignment is one-to-one for that frame.
    """

    config = config or ContinuityReferenceConfig()
    registry = _as_subject_registry(subjects)
    if not registry:
        return {}
    detector = detector or get_detector(device=config.dino_device)
    query = str(query).strip()
    if not query:
        raise ValueError("query must not be empty")
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"Rendered video is missing: {video_path!r}")

    output_paths = {
        name: registry.current_state_path(name, output_directory)
        for name in registry
    }
    identity_key_to_subject_key = {
        _identity_key(record, name): name
        for name, record in registry.items()
    }
    identity_subjects = {}
    canonical_failures: dict[Any, ContinuityReferenceResult] = {}
    if identity_validator is not None:
        for name, record in registry.items():
            backend = str(record.get("identity_backend") or "insightface").strip().casefold()
            if backend != "insightface":
                canonical_failures[name] = ContinuityReferenceResult(
                    found=False,
                    ambiguous=False,
                    reason="identity_backend_unavailable",
                    identity_status="identity_backend_unavailable",
                    attempts=({
                        "reason": "identity_backend_unavailable",
                        "identity_backend": record.get("identity_backend"),
                    },),
                )
                continue
            reference = (
                record.get("canonical_reference")
                or record.get("identity_reference")
                if isinstance(record, dict)
                else None
            )
            if reference is None:
                continue
            identity_key = _identity_key(record, name)
            try:
                canonical = identity_validator.prepare_canonical(identity_key, reference)
            except (FileNotFoundError, IdentityModelError, OSError, ValueError) as error:
                canonical_failures[name] = ContinuityReferenceResult(
                    found=False,
                    ambiguous=False,
                    reason="identity_model_error",
                    identity_status="identity_model_error",
                    identity_threshold=config.identity_confidence,
                    identity_margin=config.identity_margin,
                    attempts=({
                        "reason": "identity_model_error",
                        "error": str(error),
                    },),
                )
                continue
            if not canonical.matched:
                canonical_failures[name] = ContinuityReferenceResult(
                    found=False,
                    ambiguous=canonical.reason == "ambiguous_canonical_reference",
                    reason=canonical.reason,
                    identity_status=canonical.reason,
                    identity_threshold=config.identity_confidence,
                    identity_margin=config.identity_margin,
                    attempts=(canonical.to_dict(),),
                )
                continue
            identity_subjects[identity_key] = reference

    final_results = dict(canonical_failures)
    unresolved = {
        name for name in registry if name not in canonical_failures
    }
    attempts_by_subject: dict[Any, list[dict[str, Any]]] = {
        name: [] for name in unresolved
    }
    last_identity_by_subject: dict[Any, Any] = {}
    reasons_by_subject: dict[Any, set[str]] = {
        name: set() for name in unresolved
    }
    frame_count = int(frame_count_fn(video_path))
    if frame_count <= 0:
        return {
            **final_results,
            **{
                name: ContinuityReferenceResult(
                    found=False,
                    ambiguous=False,
                    reason="no_usable_candidate_frame",
                    attempts=tuple(attempts_by_subject[name]),
                )
                for name in unresolved
            },
        }

    with tempfile.TemporaryDirectory(prefix="dino_continuity_shared_") as temporary_directory:
        for ordinal in range(config.max_candidate_frames):
            if not unresolved:
                break
            frame_index = frame_count - 1 - ordinal * config.frame_search_interval
            if frame_index < 0:
                break
            timestamp = frame_index / config.frame_rate
            frame_name = f"candidate_{ordinal:03d}_{frame_index:08d}.png"
            try:
                extracted = frame_extractor(
                    video_path,
                    frame_name,
                    input_directory=temporary_directory,
                    frame_index=frame_index,
                    temporary_prefix=".dino_shared_",
                    error_label=f"Grounding DINO candidate frame {frame_index}",
                )
                candidate_path = _frame_path(extracted, temporary_directory)
                with Image.open(candidate_path) as opened:
                    candidate_image = opened.convert("RGB")
            except Exception as error:
                for name in unresolved:
                    attempts_by_subject[name].append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "reason": "frame_unusable",
                        "error": str(error),
                    })
                continue

            detector_result = detector.detect(
                candidate_image,
                query,
                config.box_threshold,
                config.text_threshold,
            )
            detections = _result_detections(detector_result)
            qualifying = [
                detection for detection in detections
                if float(_detection_value(detection, "confidence", 0.0))
                >= config.dino_confidence
            ]
            if not qualifying:
                reason = "below_confidence_threshold" if detections else "no_detection"
                for name in unresolved:
                    reasons_by_subject[name].add(reason)
                    attempts_by_subject[name].append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "reason": reason,
                        "detection_count": len(detections),
                    })
                continue

            prepared, preparation_attempts, preparation_reasons = _prepare_candidates(
                candidate_image,
                qualifying,
                config,
                frame_index,
                timestamp,
            )
            for name in unresolved:
                attempts_by_subject[name].extend(preparation_attempts)
                reasons_by_subject[name].update(preparation_reasons)
            if not prepared:
                continue

            identity_results = {}
            if identity_subjects and identity_validator is not None:
                active_refs = {
                    _identity_key(registry[name], name): identity_subjects[
                        _identity_key(registry[name], name)
                    ]
                    for name in unresolved
                    if _identity_key(registry[name], name) in identity_subjects
                }
                if active_refs:
                    identity_candidates = [
                        IdentityCandidate(
                            candidate_index=item["candidate_index"],
                            image=item["crop"],
                            dino_confidence=float(
                                _detection_value(item["detection"], "confidence", 0.0)
                            ),
                            bbox=item["bbox"],
                            crop_bbox=item["crop_bbox"],
                        )
                        for item in prepared
                    ]
                    try:
                        identity_results = identity_validator.select_candidates_for_subjects(
                            active_refs,
                            identity_candidates,
                            identity_threshold=config.identity_confidence,
                            identity_margin=config.identity_margin,
                        )
                    except (IdentityModelError, OSError, ValueError) as error:
                        for identity_key in active_refs:
                            name = identity_key_to_subject_key[identity_key]
                            reasons_by_subject[name].add("identity_model_error")
                            attempts_by_subject[name].append({
                                "frame_index": frame_index,
                                "timestamp": timestamp,
                                "reason": "identity_model_error",
                                "error": str(error),
                            })
                        identity_results = {}

            assigned_candidate_indices = set()
            for identity_key, selection in identity_results.items():
                name = identity_key_to_subject_key[identity_key]
                last_identity_by_subject[name] = selection
                attempts_by_subject[name].append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": selection.reason,
                    "identity": selection.to_dict(),
                })
                if not selection.matched:
                    reasons_by_subject[name].add(selection.reason)
                    continue
                selected = next(
                    item for item in prepared
                    if item["candidate_index"] == selection.candidate_index
                )
                _save_crop_atomically(selected["crop"], output_paths[name])
                registry.update_current_state(name, output_paths[name])
                final_results[name] = _accepted_result(
                    selected,
                    candidate_image,
                    frame_index,
                    timestamp,
                    output_paths[name],
                    query,
                    attempts_by_subject[name],
                    selection,
                )
                assigned_candidate_indices.add(selection.candidate_index)
                unresolved.discard(name)

            # Subjects without canonical references retain the previous DINO
            # behavior, but cannot claim a candidate already assigned by an
            # identity-validated subject.
            unvalidated = [
                name for name in unresolved
                if name not in identity_subjects
            ]
            available = [
                item for item in prepared
                if item["candidate_index"] not in assigned_candidate_indices
            ]
            if len(unvalidated) == 1 and len(available) == 1:
                name = unvalidated[0]
                selected = available[0]
                _save_crop_atomically(selected["crop"], output_paths[name])
                registry.update_current_state(name, output_paths[name])
                final_results[name] = _accepted_result(
                    selected,
                    candidate_image,
                    frame_index,
                    timestamp,
                    output_paths[name],
                    query,
                    attempts_by_subject[name],
                )
                unresolved.discard(name)
            elif unvalidated and len(available) >= 1:
                for name in unvalidated:
                    reasons_by_subject[name].add("multiple_matching_subjects")
                    attempts_by_subject[name].append({
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "reason": "multiple_matching_subjects",
                        "detection_count": len(available),
                    })

    for name in unresolved:
        selection = last_identity_by_subject.get(name)
        reasons = reasons_by_subject[name]
        if selection is not None:
            reason = selection.reason
            ambiguous = reason in {
                "ambiguous_identity",
                "ambiguous_candidate_faces",
            }
            final_results[name] = ContinuityReferenceResult(
                found=False,
                ambiguous=ambiguous,
                reason=reason,
                identity_status=reason,
                identity_similarity=selection.identity_similarity,
                identity_threshold=selection.identity_threshold,
                identity_margin=selection.identity_margin,
                identity_candidate_index=selection.candidate_index,
                identity_face_bbox=selection.face_bbox,
                identity_candidates=tuple(
                    item.to_dict() for item in selection.candidates
                ),
                attempts=tuple(attempts_by_subject[name]),
            )
        else:
            reason = (
                "not_visible"
                if name in identity_subjects
                and reasons.issubset({
                    "no_detection",
                    "below_confidence_threshold",
                    "subject_too_small",
                })
                else (_failure_reason(reasons) if reasons else "not_visible")
            )
            final_results[name] = ContinuityReferenceResult(
                found=False,
                ambiguous=reason in {
                    "multiple_matching_subjects",
                    "ambiguous_identity",
                    "ambiguous_candidate_faces",
                },
                reason=reason,
                attempts=tuple(attempts_by_subject[name]),
            )
    return final_results


def update_subject_references(
    video_path: str,
    subjects: SubjectRegistry | Mapping[Any, Mapping[str, Any]],
    output_directory: str,
    *,
    detector: Any = None,
    identity_validator: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    frame_count_fn: Callable[[str], int],
    frame_extractor: Callable[..., Any],
) -> dict[Any, ContinuityReferenceResult]:
    """Run shared-query searches and independent per-subject updates."""

    config = config or ContinuityReferenceConfig()
    registry = _as_subject_registry(subjects)
    if not registry:
        return {}
    shared_detector = detector or get_detector(device=config.dino_device)
    shared_identity_validator = identity_validator
    grouped: dict[str, list[Any]] = {}
    unsupported_results: dict[str, ContinuityReferenceResult] = {}
    for name, record in registry.items():
        backend = str(record.get("identity_backend") or "insightface").strip().casefold()
        if backend != "insightface":
            unsupported_results[name] = ContinuityReferenceResult(
                found=False,
                ambiguous=False,
                reason="identity_backend_unavailable",
                identity_status="identity_backend_unavailable",
                attempts=({
                    "reason": "identity_backend_unavailable",
                    "identity_backend": record.get("identity_backend"),
                },),
            )
            continue
        grouped.setdefault(subject_query(record), []).append(name)
        if (
            isinstance(record, dict)
            and (
                record.get("canonical_reference")
                or record.get("identity_reference")
            )
            and shared_identity_validator is None
        ):
            shared_identity_validator = get_identity_validator(
                device=config.identity_device
            )

    results: dict[str, ContinuityReferenceResult] = dict(unsupported_results)
    for query, subject_keys in grouped.items():
        query_subjects = registry.subset(subject_keys)
        try:
            results.update(search_and_save_references(
                video_path,
                query_subjects,
                output_directory,
                query,
                detector=shared_detector,
                identity_validator=shared_identity_validator,
                config=config,
                frame_count_fn=frame_count_fn,
                frame_extractor=frame_extractor,
            ))
        except Exception as error:
            # Reference extraction must remain non-destructive to the completed
            # H3 segment. The structured error is available for a future path.
            for name in query_subjects:
                results[name] = ContinuityReferenceResult(
                    found=False,
                    ambiguous=False,
                    reason="detector_unavailable",
                    attempts=({"reason": "detector_unavailable", "error": str(error)},),
                )
    return results


__all__ = [
    "ContinuityReferenceConfig",
    "ContinuityReferenceResult",
    "DinoCandidate",
    "IdentityScoreMatrix",
    "IdentityScorePair",
    "SharedQueryCandidates",
    "SubjectCandidateAssignment",
    "SubjectReferenceUpdateResult",
    "DEFAULT_DINO_CONFIDENCE",
    "DEFAULT_DINO_BOX_THRESHOLD",
    "DEFAULT_DINO_TEXT_THRESHOLD",
    "DEFAULT_FRAME_SEARCH_INTERVAL",
    "DEFAULT_MAX_CANDIDATE_FRAMES",
    "DEFAULT_MAX_STATE_AGE_SECONDS",
    "DEFAULT_CROP_PADDING_X",
    "DEFAULT_CROP_PADDING_Y",
    "DEFAULT_MIN_BBOX_AREA_RATIO",
    "DEFAULT_IDENTITY_CONFIDENCE",
    "DEFAULT_IDENTITY_MARGIN",
    "current_reference_path",
    "subject_current_reference_path",
    "build_identity_score_matrix",
    "build_identity_score_matrices",
    "assign_subject_candidates",
    "detect_shared_candidates",
    "filter_candidates_to_state_recency_window",
    "search_and_update_subject_references",
    "search_and_update_current_states",
    "search_and_save_reference",
    "search_and_save_references",
    "subject_query",
    "update_subject_references",
    "validate_subject_identity",
]
