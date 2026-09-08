"""High-confidence Grounding DINO continuity-reference extraction.

This module deliberately does not perform identity matching. A generic query
such as ``woman`` can only establish that one high-confidence woman is visible
in a frame; two qualifying detections are always treated as ambiguous.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from PIL import Image

from dino_detector import get_detector


DEFAULT_DINO_CONFIDENCE = 0.80
DEFAULT_DINO_BOX_THRESHOLD = 0.35
DEFAULT_DINO_TEXT_THRESHOLD = 0.25
DEFAULT_FRAME_SEARCH_INTERVAL = 8
DEFAULT_MAX_CANDIDATE_FRAMES = 12
DEFAULT_CROP_PADDING_X = 0.12
DEFAULT_CROP_PADDING_Y = 0.12
DEFAULT_MIN_BBOX_AREA_RATIO = 0.01
DEFAULT_FRAME_RATE = 24.0


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
    """Return a generic DINO query from the registry's normalized gender."""

    configured = str(subject.get("dino_query", "")).strip()
    if configured:
        return configured
    gender = str(subject.get("gender", "")).strip().casefold()
    return {"female": "woman", "male": "man"}.get(gender, fallback)


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


def _failure_reason(reasons: set[str]) -> str:
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
    identity_validator: Optional[Callable[[Image.Image, Any], Any]] = None,
    canonical_reference: Any = None,
) -> ContinuityReferenceResult:
    """Find and save the newest unambiguous high-confidence subject crop."""

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

    attempts: list[dict[str, Any]] = []
    reasons: set[str] = set()
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
            if len(qualifying) >= 2:
                reasons.add("multiple_matching_subjects")
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": "multiple_matching_subjects",
                    "detection_count": len(qualifying),
                })
                continue

            detection = qualifying[0]
            raw_bbox = _detection_value(detection, "bbox")
            try:
                bbox = [int(round(float(value))) for value in raw_bbox]
            except (TypeError, ValueError):
                bbox = []
            if len(bbox) != 4:
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": "frame_unusable",
                    "error": "detector returned an invalid bbox",
                })
                continue

            image_width, image_height = candidate_image.size
            # The reusable detector already returns clamped pixel boxes, but
            # clamp adapter/test implementations here as a final safety
            # boundary before measuring or cropping.
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
                    "reason": "subject_too_small",
                    "confidence": float(_detection_value(detection, "confidence", 0.0)),
                    "bbox_area_ratio": area_ratio,
                })
                continue

            touches_edge = (
                x1 <= 0 or y1 <= 0 or x2 >= image_width or y2 >= image_height
            )
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
                    "reason": "frame_unusable",
                    "error": "padded crop has no area",
                })
                continue

            crop = candidate_image.crop(tuple(crop_bbox))
            identity_status = (
                identity_validator(crop, canonical_reference)
                if identity_validator
                else validate_subject_identity(crop, canonical_reference)
            )
            if identity_status is False:
                attempts.append({
                    "frame_index": frame_index,
                    "timestamp": timestamp,
                    "reason": "identity_rejected",
                })
                continue

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
                bbox_width=bbox_width,
                bbox_height=bbox_height,
                bbox_area_ratio=area_ratio,
                touches_frame_edge=touches_edge,
                crop_width=crop_width,
                crop_height=crop_height,
                matched_phrase=matched_phrase,
                output_path=os.path.abspath(output_path),
                attempts=tuple(attempts),
            )

    return ContinuityReferenceResult(
        found=False,
        ambiguous="multiple_matching_subjects" in reasons,
        reason=_failure_reason(reasons),
        attempts=tuple(attempts),
    )


def update_subject_references(
    video_path: str,
    subjects: dict[str, dict[str, Any]],
    output_directory: str,
    *,
    detector: Any = None,
    config: Optional[ContinuityReferenceConfig] = None,
    frame_count_fn: Callable[[str], int],
    frame_extractor: Callable[..., Any],
) -> dict[str, ContinuityReferenceResult]:
    """Run the high-confidence search for each registered subject."""

    config = config or ContinuityReferenceConfig()
    shared_detector = detector or get_detector()
    results: dict[str, ContinuityReferenceResult] = {}
    for name, record in (subjects or {}).items():
        output_path = current_reference_path(output_directory, name)
        try:
            results[str(name)] = search_and_save_reference(
                video_path,
                subject_query(record),
                output_path,
                detector=shared_detector,
                config=config,
                frame_count_fn=frame_count_fn,
                frame_extractor=frame_extractor,
            )
        except Exception as error:
            # Reference extraction must remain non-destructive to the completed
            # H3 segment. The structured error is available for a future path.
            results[str(name)] = ContinuityReferenceResult(
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
    "current_reference_path",
    "search_and_save_reference",
    "subject_query",
    "update_subject_references",
    "validate_subject_identity",
]
