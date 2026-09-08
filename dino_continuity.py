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
from typing import Any, Callable, Mapping, Optional, Sequence

from PIL import Image

from dino_detector import get_detector
from identity_validator import (
    IdentityCandidate,
    IdentityModelError,
    get_identity_validator,
)
from subject_registry import SubjectRegistry


DEFAULT_DINO_CONFIDENCE = 0.80
DEFAULT_DINO_BOX_THRESHOLD = 0.35
DEFAULT_DINO_TEXT_THRESHOLD = 0.25
DEFAULT_FRAME_SEARCH_INTERVAL = 8
DEFAULT_MAX_CANDIDATE_FRAMES = 12
DEFAULT_CROP_PADDING_X = 0.12
DEFAULT_CROP_PADDING_Y = 0.12
DEFAULT_MIN_BBOX_AREA_RATIO = 0.01
DEFAULT_FRAME_RATE = 24.0
DEFAULT_IDENTITY_CONFIDENCE = 0.48
DEFAULT_IDENTITY_MARGIN = 0.05


@dataclass(frozen=True)
class ContinuityReferenceConfig:
    """Tunable settings for the high-confidence reference path."""

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

    def __post_init__(self) -> None:
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
        if float(self.frame_rate) <= 0.0:
            raise ValueError("frame_rate must be greater than zero")


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
        os.replace(temporary_path, output)
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
    detector = detector or get_detector()
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
    detector = detector or get_detector()
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
    shared_detector = detector or get_detector()
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
            shared_identity_validator = get_identity_validator()

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
    "DEFAULT_DINO_CONFIDENCE",
    "DEFAULT_DINO_BOX_THRESHOLD",
    "DEFAULT_DINO_TEXT_THRESHOLD",
    "DEFAULT_FRAME_SEARCH_INTERVAL",
    "DEFAULT_MAX_CANDIDATE_FRAMES",
    "DEFAULT_CROP_PADDING_X",
    "DEFAULT_CROP_PADDING_Y",
    "DEFAULT_MIN_BBOX_AREA_RATIO",
    "DEFAULT_IDENTITY_CONFIDENCE",
    "DEFAULT_IDENTITY_MARGIN",
    "current_reference_path",
    "subject_current_reference_path",
    "search_and_save_reference",
    "search_and_save_references",
    "subject_query",
    "update_subject_references",
    "validate_subject_identity",
]
