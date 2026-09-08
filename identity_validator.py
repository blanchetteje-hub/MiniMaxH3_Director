"""Lazy, reusable InsightFace/ArcFace identity verification.

Grounding DINO is responsible for finding person candidates. This module only
detects faces inside those candidate crops and compares their normalized
ArcFace embeddings with one cached canonical subject embedding.

InsightFace is optional. Importing this module does not import InsightFace or
ONNX Runtime, so the existing H3 pipeline remains usable without the optional
identity dependencies installed.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from PIL import Image


DEFAULT_IDENTITY_CONFIDENCE = 0.48
DEFAULT_IDENTITY_MARGIN = 0.05
DEFAULT_IDENTITY_MODEL = "buffalo_l"
DEFAULT_IDENTITY_DET_SIZE = (640, 640)
IDENTITY_MODEL_ROOT_ENV = "INSIGHTFACE_MODEL_ROOT"

LOGGER = logging.getLogger(__name__)


def _discover_existing_model_root(model_name: str) -> Optional[str]:
    """Reuse a compatible ComfyUI/InsightFace model cache when present."""

    roots = []
    configured_comfy = os.environ.get("MINIMAX_COMFYUI_ROOT") or os.environ.get(
        "COMFYUI_ROOT"
    )
    if configured_comfy:
        roots.append(Path(configured_comfy).expanduser())
    roots.extend((Path.home() / "AI" / "ComfyUI", Path.home() / "ComfyUI"))
    for root in roots:
        for base in (
            root / "models" / "insightface",
            root / "models",
            root,
        ):
            if (base / "models" / model_name).is_dir():
                return str(base)
            if (base / model_name).is_dir():
                return str(base.parent)
    return None


class IdentityModelError(RuntimeError):
    """Raised when the optional InsightFace runtime cannot be initialized."""


def _validate_threshold(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value) or not -1.0 <= value <= 1.0:
        raise ValueError(f"{label} must be between -1.0 and 1.0")
    return value


def _validate_margin(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 2.0:
        raise ValueError("identity_margin must be between 0.0 and 2.0")
    return value


def normalize_embedding(embedding: Sequence[float]) -> Any:
    """Return a unit-norm NumPy embedding without importing NumPy at module load."""

    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - optional runtime
        raise IdentityModelError(
            "InsightFace identity verification requires NumPy."
        ) from error

    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0.0 or not np.isfinite(vector).all():
        raise ValueError("embedding must contain finite non-zero values")
    return vector / norm


def compare_face_embeddings(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    """Return normalized cosine similarity for two face embeddings."""

    import numpy as np

    first_normalized = normalize_embedding(first)
    second_normalized = normalize_embedding(second)
    similarity = float(np.dot(first_normalized, second_normalized))
    return max(-1.0, min(1.0, similarity))


def _bbox(value: Any) -> Optional[list[float]]:
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or not all(math.isfinite(item) for item in values):
        return None
    return values


@dataclass(frozen=True)
class FaceObservation:
    bbox: list[float]
    embedding: Any = field(repr=False, compare=False)
    detection_score: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": [round(value, 3) for value in self.bbox],
            "detection_score": self.detection_score,
        }


@dataclass(frozen=True)
class CanonicalReferenceResult:
    subject: str
    reference: str
    evaluated: bool
    embedding: Any = field(repr=False, compare=False, default=None)
    face_bbox: Optional[list[float]] = None
    reason: str = "canonical_face_not_found"
    provider: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.embedding is not None and self.reason == "canonical_loaded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_subject": self.subject,
            "canonical_reference": self.reference,
            "evaluated": self.evaluated,
            "matched": self.matched,
            "face_bbox": self.face_bbox,
            "reason": self.reason,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class IdentityCandidate:
    """A DINO candidate crop presented to the identity validator."""

    candidate_index: int
    image: Image.Image
    dino_confidence: float
    bbox: list[int]
    crop_bbox: list[int]


@dataclass(frozen=True)
class CandidateIdentityResult:
    candidate_index: int
    evaluated: bool
    matched: bool
    reason: str
    identity_similarity: Optional[float] = None
    face_bbox: Optional[list[float]] = None
    dino_confidence: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_index": self.candidate_index,
            "evaluated": self.evaluated,
            "matched": self.matched,
            "reason": self.reason,
            "identity_similarity": self.identity_similarity,
            "face_bbox": self.face_bbox,
            "dino_confidence": self.dino_confidence,
        }


@dataclass(frozen=True)
class IdentitySelectionResult:
    evaluated: bool
    matched: bool
    reason: str
    canonical_subject: str
    identity_similarity: Optional[float] = None
    identity_threshold: float = DEFAULT_IDENTITY_CONFIDENCE
    identity_margin: float = DEFAULT_IDENTITY_MARGIN
    candidate_index: Optional[int] = None
    face_bbox: Optional[list[float]] = None
    candidates: tuple[CandidateIdentityResult, ...] = field(default_factory=tuple)
    canonical: Optional[CanonicalReferenceResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "matched": self.matched,
            "reason": self.reason,
            "identity_similarity": self.identity_similarity,
            "identity_threshold": self.identity_threshold,
            "identity_margin": self.identity_margin,
            "canonical_subject": self.canonical_subject,
            "candidate_index": self.candidate_index,
            "face_bbox": self.face_bbox,
            "candidates": [item.to_dict() for item in self.candidates],
            "canonical": self.canonical.to_dict() if self.canonical else None,
        }


def _maximum_weight_assignment(
    subject_ids: Sequence[str],
    edges: Mapping[str, Mapping[int, float]],
) -> dict[str, int]:
    """Return a deterministic maximum-cardinality, maximum-score assignment."""

    ordered_subjects = tuple(sorted(subject_ids))

    def solve(position: int, used: frozenset[int]):
        if position >= len(ordered_subjects):
            return (0, 0.0, tuple())
        subject_id = ordered_subjects[position]
        best = solve(position + 1, used)
        for candidate_index, score in sorted(
            edges.get(subject_id, {}).items(),
            key=lambda item: item[0],
        ):
            if candidate_index in used:
                continue
            tail = solve(position + 1, used | {candidate_index})
            option = (
                tail[0] + 1,
                tail[1] + float(score),
                ((subject_id, candidate_index),) + tail[2],
            )
            if option[0] > best[0] or (
                option[0] == best[0]
                and (
                    option[1] > best[1]
                    or (option[1] == best[1] and option[2] < best[2])
                )
            ):
                best = option
        return best

    return dict(solve(0, frozenset())[2])


def _reference_key(reference: Any) -> str:
    if isinstance(reference, (str, os.PathLike)):
        path = Path(reference).expanduser().resolve()
        try:
            stat = path.stat()
            return f"path:{path}:{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return f"path:{path}"
    if isinstance(reference, Image.Image):
        image = reference.convert("RGB")
        digest = hashlib.sha256(image.tobytes()).hexdigest()
        return f"pil:{image.size}:{digest}"
    return f"object:{id(reference)}"


def _image_to_bgr(image: Image.Image) -> Any:
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - optional runtime
        raise IdentityModelError("InsightFace requires NumPy.") from error
    rgb = image.convert("RGB")
    return np.asarray(rgb, dtype=np.uint8)[:, :, ::-1].copy()


def _load_image(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    path = Path(image).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Identity reference image not found: {path}")
    with Image.open(path) as opened:
        return opened.convert("RGB")


def _face_observation(face: Any) -> Optional[FaceObservation]:
    face_bbox = _bbox(getattr(face, "bbox", None))
    embedding = getattr(face, "embedding", None)
    if face_bbox is None or embedding is None:
        return None
    try:
        normalized = normalize_embedding(embedding)
    except (IdentityModelError, ValueError):
        return None
    score = getattr(face, "det_score", None)
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return FaceObservation(face_bbox, normalized, score)


def _face_center(face_bbox: Sequence[float]) -> tuple[float, float]:
    return (
        (float(face_bbox[0]) + float(face_bbox[2])) / 2.0,
        (float(face_bbox[1]) + float(face_bbox[3])) / 2.0,
    )


def _contained(face_bbox: Sequence[float], person_bbox: Sequence[float]) -> bool:
    return (
        face_bbox[0] >= person_bbox[0]
        and face_bbox[1] >= person_bbox[1]
        and face_bbox[2] <= person_bbox[2]
        and face_bbox[3] <= person_bbox[3]
    )


class IdentityValidator:
    """Lazy persistent InsightFace validator with canonical embedding cache."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_IDENTITY_MODEL,
        root: Optional[str | os.PathLike[str]] = None,
        providers: Optional[Sequence[str]] = None,
        det_size: tuple[int, int] = DEFAULT_IDENTITY_DET_SIZE,
        backend: Any = None,
    ) -> None:
        self.model_name = str(model_name)
        self.root = (
            os.fspath(root)
            if root
            else os.environ.get(IDENTITY_MODEL_ROOT_ENV)
            or _discover_existing_model_root(self.model_name)
            or str(Path.home() / ".insightface")
        )
        self.requested_providers = tuple(providers or ())
        self.det_size = det_size
        self._backend = backend
        self._providers: tuple[str, ...] = tuple()
        self._load_lock = threading.RLock()
        self._canonical_cache: dict[tuple[str, str], CanonicalReferenceResult] = {}

    @property
    def loaded(self) -> bool:
        return self._backend is not None

    @property
    def providers(self) -> tuple[str, ...]:
        return self._providers

    @staticmethod
    def _backend_providers(backend: Any, fallback: Sequence[str]) -> tuple[str, ...]:
        """Read the providers actually attached to InsightFace ONNX sessions."""

        observed: list[str] = []
        models = getattr(backend, "models", {})
        if isinstance(models, Mapping):
            model_values = models.values()
        else:
            model_values = ()
        for model in model_values:
            session = getattr(model, "session", None)
            get_providers = getattr(session, "get_providers", None)
            if not callable(get_providers):
                continue
            try:
                for provider in get_providers() or ():
                    provider = str(provider)
                    if provider not in observed:
                        observed.append(provider)
            except Exception:  # pragma: no cover - provider introspection varies
                continue
        return tuple(observed) or tuple(str(provider) for provider in fallback)

    @staticmethod
    def _prepare_onnx_runtime() -> tuple[Any, Any, list[str]]:
        """Preload Python-packaged CUDA libraries before InsightFace creates sessions."""

        try:
            import torch
        except ImportError as error:  # pragma: no cover - optional runtime
            raise IdentityModelError(
                "InsightFace GPU initialization requires PyTorch."
            ) from error
        try:
            import onnxruntime as ort
        except ImportError as error:  # pragma: no cover - optional runtime
            raise IdentityModelError(
                "InsightFace requires onnxruntime or onnxruntime-gpu."
            ) from error

        torch_version = str(getattr(torch, "__version__", "unknown"))
        torch_version_info = getattr(torch, "version", None)
        torch_cuda_version = getattr(torch_version_info, "cuda", None)
        torch_cuda_available = False
        try:
            torch_cuda_available = bool(torch.cuda.is_available())
        except Exception:  # pragma: no cover - runtime-specific
            LOGGER.debug("torch.cuda.is_available() could not be evaluated", exc_info=True)

        LOGGER.debug(
            "InsightFace runtime: torch=%s torch_cuda=%s torch.cuda.is_available=%s",
            torch_version,
            torch_cuda_version,
            torch_cuda_available,
        )
        LOGGER.debug("InsightFace runtime: onnxruntime=%s", ort.__version__)

        preload_dlls = getattr(ort, "preload_dlls", None)
        if callable(preload_dlls):
            try:
                # An empty directory tells ORT to search installed NVIDIA
                # Python packages, avoiding the host /usr/local/cuda runtime.
                preload_dlls(directory="")
                LOGGER.debug(
                    "InsightFace runtime: preloaded ONNX Runtime CUDA/cuDNN "
                    "libraries from Python packages"
                )
            except Exception:
                LOGGER.debug(
                    "InsightFace runtime: ORT Python-package DLL preload failed; "
                    "provider discovery will continue",
                    exc_info=True,
                )
        else:
            LOGGER.debug(
                "InsightFace runtime: onnxruntime.preload_dlls is unavailable"
            )

        available = list(ort.get_available_providers())
        LOGGER.debug("InsightFace runtime: available ORT providers=%s", available)
        return torch, ort, available

    def _available_providers(self) -> list[str]:
        _torch, _ort, available_names = self._prepare_onnx_runtime()
        available = set(available_names)
        requested = list(self.requested_providers) or [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        providers = [provider for provider in requested if provider in available]
        if "CPUExecutionProvider" in available and "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        if not providers:
            raise IdentityModelError(
                "InsightFace found no usable ONNX Runtime execution provider."
            )
        return providers

    def _get_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        with self._load_lock:
            if self._backend is not None:
                return self._backend
            providers = self._available_providers()
            try:
                from insightface.app import FaceAnalysis
            except ImportError as error:  # pragma: no cover - optional runtime
                raise IdentityModelError(
                    "InsightFace is not installed. Install the optional "
                    "requirements-insightface.txt dependencies."
                ) from error
            try:
                backend = FaceAnalysis(
                    name=self.model_name,
                    root=self.root,
                    providers=providers,
                )
                ctx_id = 0 if providers[0] == "CUDAExecutionProvider" else -1
                backend.prepare(ctx_id=ctx_id, det_size=self.det_size)
            except Exception as error:
                if "CUDAExecutionProvider" in providers:
                    try:
                        backend = FaceAnalysis(
                            name=self.model_name,
                            root=self.root,
                            providers=["CPUExecutionProvider"],
                        )
                        backend.prepare(ctx_id=-1, det_size=self.det_size)
                        providers = ["CPUExecutionProvider"]
                    except Exception as cpu_error:
                        raise IdentityModelError(
                            f"InsightFace model initialization failed on GPU and CPU: {cpu_error}"
                        ) from cpu_error
                else:
                    raise IdentityModelError(
                        f"InsightFace model initialization failed: {error}"
                    ) from error
            self._backend = backend
            self._providers = self._backend_providers(backend, providers)
            LOGGER.debug(
                "InsightFace backend initialized; selected ORT provider(s)=%s",
                self._providers,
            )
        return self._backend

    def _detect_faces(self, image: Image.Image) -> list[FaceObservation]:
        backend = self._get_backend()
        faces = backend.get(_image_to_bgr(image))
        observations = []
        for face in faces or []:
            observation = _face_observation(face)
            if observation is not None:
                observations.append(observation)
        return observations

    def prepare_canonical(
        self,
        subject: str,
        reference: Any,
    ) -> CanonicalReferenceResult:
        subject = str(subject).strip()
        if not subject:
            raise ValueError("canonical subject must not be empty")
        cache_key = (subject, _reference_key(reference))
        cached = self._canonical_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            image = _load_image(reference)
            faces = self._detect_faces(image)
        except Exception as error:
            if isinstance(error, (FileNotFoundError, IdentityModelError)):
                raise
            raise IdentityModelError(
                f"canonical face analysis failed for {subject}: {error}"
            ) from error
        if not faces:
            result = CanonicalReferenceResult(
                subject=subject,
                reference=str(reference),
                evaluated=True,
                reason="canonical_face_not_found",
                provider=self.providers[0] if self.providers else None,
            )
        elif len(faces) > 1:
            result = CanonicalReferenceResult(
                subject=subject,
                reference=str(reference),
                evaluated=True,
                reason="ambiguous_canonical_reference",
                provider=self.providers[0] if self.providers else None,
            )
        else:
            result = CanonicalReferenceResult(
                subject=subject,
                reference=str(reference),
                evaluated=True,
                embedding=faces[0].embedding,
                face_bbox=faces[0].bbox,
                reason="canonical_loaded",
                provider=self.providers[0] if self.providers else None,
            )
        self._canonical_cache[cache_key] = result
        return result

    def _select_candidate_face(
        self,
        faces: list[FaceObservation],
        candidate: IdentityCandidate,
    ) -> tuple[Optional[FaceObservation], str]:
        if not faces:
            return None, "not_evaluated_no_face"
        if len(faces) == 1:
            return faces[0], "identity_evaluated"

        crop_x, crop_y = candidate.crop_bbox[:2]
        person_bbox = [
            candidate.bbox[0] - crop_x,
            candidate.bbox[1] - crop_y,
            candidate.bbox[2] - crop_x,
            candidate.bbox[3] - crop_y,
        ]
        contained = [face for face in faces if _contained(face.bbox, person_bbox)]
        if len(contained) == 1:
            return contained[0], "identity_evaluated"
        return None, "ambiguous_candidate_faces"

    def evaluate_candidate(
        self,
        canonical: CanonicalReferenceResult,
        candidate: IdentityCandidate,
    ) -> CandidateIdentityResult:
        try:
            faces = self._detect_faces(candidate.image)
        except Exception as error:
            raise IdentityModelError(
                f"candidate face analysis failed: {error}"
            ) from error
        face, reason = self._select_candidate_face(faces, candidate)
        if face is None:
            return CandidateIdentityResult(
                candidate_index=candidate.candidate_index,
                evaluated=False,
                matched=False,
                reason=reason,
                dino_confidence=candidate.dino_confidence,
            )
        similarity = compare_face_embeddings(canonical.embedding, face.embedding)
        return CandidateIdentityResult(
            candidate_index=candidate.candidate_index,
            evaluated=True,
            matched=False,
            reason="identity_evaluated",
            identity_similarity=similarity,
            face_bbox=face.bbox,
            dino_confidence=candidate.dino_confidence,
        )

    def select_candidates_for_subjects(
        self,
        subjects: Mapping[str, Any],
        candidates: Sequence[IdentityCandidate],
        *,
        identity_threshold: float = DEFAULT_IDENTITY_CONFIDENCE,
        identity_margin: float = DEFAULT_IDENTITY_MARGIN,
    ) -> dict[str, IdentitySelectionResult]:
        """Score one shared candidate set and assign candidates one-to-one."""

        threshold = _validate_threshold(identity_threshold, "identity_confidence")
        margin = _validate_margin(identity_margin)
        subject_ids = tuple(str(subject_id) for subject_id in subjects)
        if not candidates:
            return {
                subject_id: IdentitySelectionResult(
                    evaluated=False,
                    matched=False,
                    reason="not_visible",
                    canonical_subject=subject_id,
                    identity_threshold=threshold,
                    identity_margin=margin,
                )
                for subject_id in subject_ids
            }

        canonical_by_subject: dict[str, CanonicalReferenceResult] = {}
        output: dict[str, IdentitySelectionResult] = {}
        for subject_id in subject_ids:
            reference = subjects[subject_id]
            if isinstance(reference, dict):
                reference = (
                    reference.get("canonical_reference")
                    or reference.get("identity_reference")
                )
            if reference is None:
                output[subject_id] = IdentitySelectionResult(
                    evaluated=False,
                    matched=False,
                    reason="canonical_face_not_found",
                    canonical_subject=subject_id,
                    identity_threshold=threshold,
                    identity_margin=margin,
                )
                continue
            try:
                canonical = self.prepare_canonical(subject_id, reference)
            except (FileNotFoundError, IdentityModelError, OSError, ValueError):
                output[subject_id] = IdentitySelectionResult(
                    evaluated=False,
                    matched=False,
                    reason="identity_model_error",
                    canonical_subject=subject_id,
                    identity_threshold=threshold,
                    identity_margin=margin,
                )
                continue
            canonical_by_subject[subject_id] = canonical
            if not canonical.matched:
                output[subject_id] = IdentitySelectionResult(
                    evaluated=False,
                    matched=False,
                    reason=canonical.reason,
                    canonical_subject=subject_id,
                    identity_threshold=threshold,
                    identity_margin=margin,
                    canonical=canonical,
                )

        # Face detection is shared across all subjects. Only the embedding
        # comparison varies by canonical subject.
        face_results: list[tuple[Optional[FaceObservation], str]] = []
        for candidate in candidates:
            try:
                faces = self._detect_faces(candidate.image)
                face, reason = self._select_candidate_face(faces, candidate)
            except (IdentityModelError, OSError, ValueError) as error:
                raise IdentityModelError(
                    f"candidate face analysis failed: {error}"
                ) from error
            face_results.append((face, reason))

        score_results: dict[str, tuple[CandidateIdentityResult, ...]] = {}
        edges: dict[str, dict[int, float]] = {}
        ambiguous_subjects: set[str] = set()
        for subject_id, canonical in canonical_by_subject.items():
            candidate_results = []
            for candidate, (face, face_reason) in zip(candidates, face_results):
                if face is None:
                    candidate_results.append(CandidateIdentityResult(
                        candidate_index=candidate.candidate_index,
                        evaluated=False,
                        matched=False,
                        reason=face_reason,
                        dino_confidence=candidate.dino_confidence,
                    ))
                    continue
                candidate_results.append(CandidateIdentityResult(
                    candidate_index=candidate.candidate_index,
                    evaluated=True,
                    matched=False,
                    reason="identity_evaluated",
                    identity_similarity=compare_face_embeddings(
                        canonical.embedding,
                        face.embedding,
                    ),
                    face_bbox=face.bbox,
                    dino_confidence=candidate.dino_confidence,
                ))
            score_results[subject_id] = tuple(candidate_results)
            usable = [
                item for item in candidate_results
                if item.identity_similarity is not None
            ]
            if not usable:
                continue
            ranked = sorted(
                usable,
                key=lambda item: float(item.identity_similarity),
                reverse=True,
            )
            if (
                len(ranked) > 1
                and float(ranked[0].identity_similarity)
                - float(ranked[1].identity_similarity)
                < margin
            ):
                ambiguous_subjects.add(subject_id)
                continue
            edges[subject_id] = {
                item.candidate_index: float(item.identity_similarity)
                for item in usable
                if float(item.identity_similarity) >= threshold
            }

        assignments = _maximum_weight_assignment(
            [subject_id for subject_id in canonical_by_subject
             if subject_id not in ambiguous_subjects],
            edges,
        )
        for subject_id, canonical in canonical_by_subject.items():
            if subject_id in output:
                continue
            candidate_results = score_results.get(subject_id, tuple())
            usable = [
                item for item in candidate_results
                if item.identity_similarity is not None
            ]
            if not usable:
                reason = (
                    "ambiguous_candidate_faces"
                    if any(item.reason == "ambiguous_candidate_faces" for item in candidate_results)
                    else "not_evaluated_no_face"
                )
                output[subject_id] = IdentitySelectionResult(
                    evaluated=False,
                    matched=False,
                    reason=reason,
                    canonical_subject=subject_id,
                    identity_threshold=threshold,
                    identity_margin=margin,
                    candidates=candidate_results,
                    canonical=canonical,
                )
                continue
            ranked = sorted(
                usable,
                key=lambda item: float(item.identity_similarity),
                reverse=True,
            )
            if subject_id in ambiguous_subjects:
                best = ranked[0]
                output[subject_id] = IdentitySelectionResult(
                    evaluated=True,
                    matched=False,
                    reason="ambiguous_identity",
                    canonical_subject=subject_id,
                    identity_similarity=float(best.identity_similarity),
                    identity_threshold=threshold,
                    identity_margin=margin,
                    candidate_index=best.candidate_index,
                    face_bbox=best.face_bbox,
                    candidates=candidate_results,
                    canonical=canonical,
                )
                continue
            assigned_index = assignments.get(subject_id)
            if assigned_index is None:
                best = ranked[0]
                reason = (
                    "identity_mismatch"
                    if float(best.identity_similarity) < threshold
                    else "candidate_already_assigned"
                )
                output[subject_id] = IdentitySelectionResult(
                    evaluated=True,
                    matched=False,
                    reason=reason,
                    canonical_subject=subject_id,
                    identity_similarity=float(best.identity_similarity),
                    identity_threshold=threshold,
                    identity_margin=margin,
                    candidate_index=best.candidate_index,
                    face_bbox=best.face_bbox,
                    candidates=candidate_results,
                    canonical=canonical,
                )
                continue
            selected = next(
                item for item in candidate_results
                if item.candidate_index == assigned_index
            )
            output[subject_id] = IdentitySelectionResult(
                evaluated=True,
                matched=True,
                reason="identity_match",
                canonical_subject=subject_id,
                identity_similarity=selected.identity_similarity,
                identity_threshold=threshold,
                identity_margin=margin,
                candidate_index=assigned_index,
                face_bbox=selected.face_bbox,
                candidates=candidate_results,
                canonical=canonical,
            )
        return output

    def select_candidate(
        self,
        subject: str,
        canonical_reference: Any,
        candidates: Iterable[IdentityCandidate],
        *,
        identity_threshold: float = DEFAULT_IDENTITY_CONFIDENCE,
        identity_margin: float = DEFAULT_IDENTITY_MARGIN,
    ) -> IdentitySelectionResult:
        threshold = _validate_threshold(identity_threshold, "identity_confidence")
        margin = _validate_margin(identity_margin)
        canonical = self.prepare_canonical(subject, canonical_reference)
        candidate_list = tuple(candidates)
        if not canonical.matched:
            return IdentitySelectionResult(
                evaluated=False,
                matched=False,
                reason=canonical.reason,
                canonical_subject=str(subject),
                identity_threshold=threshold,
                identity_margin=margin,
                canonical=canonical,
            )

        evaluated = tuple(
            self.evaluate_candidate(canonical, candidate)
            for candidate in candidate_list
        )
        usable = [
            item for item in evaluated if item.identity_similarity is not None
        ]
        if not usable:
            reason = (
                "ambiguous_candidate_faces"
                if any(item.reason == "ambiguous_candidate_faces" for item in evaluated)
                else "not_evaluated_no_face"
            )
            return IdentitySelectionResult(
                evaluated=False,
                matched=False,
                reason=reason,
                canonical_subject=str(subject),
                identity_threshold=threshold,
                identity_margin=margin,
                candidates=evaluated,
                canonical=canonical,
            )

        ranked = sorted(
            usable,
            key=lambda item: float(item.identity_similarity),
            reverse=True,
        )
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        best_score = float(best.identity_similarity)
        if best_score < threshold:
            reason = "identity_mismatch"
            matched = False
        elif second is not None and best_score - float(second.identity_similarity) < margin:
            reason = "ambiguous_identity"
            matched = False
        else:
            reason = "identity_match"
            matched = True
        return IdentitySelectionResult(
            evaluated=True,
            matched=matched,
            reason=reason,
            canonical_subject=str(subject),
            identity_similarity=best_score,
            identity_threshold=threshold,
            identity_margin=margin,
            candidate_index=best.candidate_index,
            face_bbox=best.face_bbox,
            candidates=evaluated,
            canonical=canonical,
        )


_DEFAULT_VALIDATORS: dict[tuple[str, Optional[str]], IdentityValidator] = {}
_DEFAULT_VALIDATORS_LOCK = threading.RLock()


def get_identity_validator(
    *,
    model_name: str = DEFAULT_IDENTITY_MODEL,
    root: Optional[str | os.PathLike[str]] = None,
) -> IdentityValidator:
    effective_root = (
        os.fspath(root)
        if root
        else os.environ.get(IDENTITY_MODEL_ROOT_ENV)
        or _discover_existing_model_root(str(model_name))
    )
    key = (str(model_name), effective_root)
    with _DEFAULT_VALIDATORS_LOCK:
        validator = _DEFAULT_VALIDATORS.get(key)
        if validator is None:
            validator = IdentityValidator(model_name=model_name, root=effective_root)
            _DEFAULT_VALIDATORS[key] = validator
        return validator


__all__ = [
    "CandidateIdentityResult",
    "CanonicalReferenceResult",
    "DEFAULT_IDENTITY_CONFIDENCE",
    "DEFAULT_IDENTITY_MARGIN",
    "DEFAULT_IDENTITY_MODEL",
    "FaceObservation",
    "IdentityCandidate",
    "IdentityModelError",
    "IdentitySelectionResult",
    "IdentityValidator",
    "compare_face_embeddings",
    "get_identity_validator",
    "normalize_embedding",
]
