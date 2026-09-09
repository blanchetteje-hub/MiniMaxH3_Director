import numpy as np
from PIL import Image

from dino_continuity import (
    DinoCandidate,
    IdentityScoreMatrix,
    SharedQueryCandidates,
    build_identity_score_matrix,
)
from identity_validator import IdentityValidator
from subject_registry import SubjectRegistry


class FakeFace:
    def __init__(self, bbox, embedding):
        self.bbox = bbox
        self.embedding = np.asarray(embedding, dtype=np.float32)
        self.det_score = 0.99


class FakeIdentityBackend:
    def __init__(self, faces_by_marker):
        self.faces_by_marker = faces_by_marker
        self.calls = []

    def get(self, image):
        marker = int(image[0, 0, 2])
        self.calls.append(marker)
        faces = self.faces_by_marker.get(marker, [])
        if isinstance(faces, Exception):
            raise faces
        return faces


def marked_image(marker):
    image = Image.new("RGB", (100, 80), "black")
    image.putpixel((0, 0), (marker, 0, 0))
    return image


def candidate(index, marker):
    return DinoCandidate(
        candidate_index=index,
        dino_query="woman",
        confidence=0.9,
        bbox=[0, 0, 100, 80],
        crop_bbox=[0, 0, 100, 80],
        bbox_area_ratio=1.0,
        touches_frame_edge=True,
        image_width=100,
        image_height=80,
        crop=marked_image(marker),
    )


def make_registry(*backend_values):
    registry = SubjectRegistry()
    for index, backend in enumerate(backend_values, start=1):
        registry.register(
            f"subject-{index}",
            registry_key=f"subject-{index}",
            name=f"Subject {index}",
            dino_query="woman",
            canonical_reference=marked_image(index + 9),
            identity_backend=backend,
        )
    return registry


def make_group(registry, candidates):
    return {
        "woman": SharedQueryCandidates(
            dino_query="woman",
            subject_keys=tuple(registry.keys()),
            candidates=tuple(candidates),
        )
    }


def make_validator(faces_by_marker):
    backend = FakeIdentityBackend(faces_by_marker)
    return IdentityValidator(
        backend=backend,
        providers=("CPUExecutionProvider",),
    ), backend


def face(embedding):
    return FakeFace([20, 10, 80, 70], embedding)


def test_three_subjects_three_candidates_returns_complete_matrix_without_assignment():
    registry = make_registry("insightface", "insightface", "insightface")
    validator, backend = make_validator({
        10: [face([1, 0])],
        11: [face([0, 1])],
        12: [face([-1, 0])],
        1: [face([1, 0])],
        2: [face([0, 1])],
        3: [face([-1, 0])],
    })

    result = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1), candidate(1, 2), candidate(2, 3)]),
        registry,
        identity_validator=validator,
        identity_threshold=0.99,
    )
    matrix = result["woman"]

    assert isinstance(matrix, IdentityScoreMatrix)
    assert matrix.candidate_indices == (0, 1, 2)
    assert set(matrix.scores) == set(registry)
    assert [
        matrix.scores["subject-1"][index].identity_similarity
        for index in matrix.candidate_indices
    ] == [1.0, 0.0, -1.0]
    assert [
        matrix.scores["subject-2"][index].identity_similarity
        for index in matrix.candidate_indices
    ] == [0.0, 1.0, 0.0]
    assert all(
        pair.status == "identity_score"
        for row in matrix.scores.values()
        for pair in row.values()
    )
    assert matrix.identity_threshold == 0.99
    assert "assigned_candidate" not in matrix.to_dict()
    assert "selected_subject" not in matrix.to_dict()
    # Three canonical analyses + three shared candidate analyses, not nine
    # candidate face-model passes.
    assert backend.calls == [10, 11, 12, 1, 2, 3]


def test_below_threshold_scores_are_retained_and_candidate_analysis_is_reused():
    registry = make_registry("insightface", "insightface", "insightface")
    validator, backend = make_validator({
        10: [face([1, 0])],
        11: [face([1, 0])],
        12: [face([1, 0])],
        1: [face([1, 0])],
    })
    candidates = [candidate(0, 1)]

    result = build_identity_score_matrix(
        make_group(registry, candidates),
        registry,
        identity_validator=validator,
        identity_threshold=0.99,
    )

    matrix = result["woman"]
    assert [
        matrix.scores[key][0].identity_similarity
        for key in registry
    ] == [1.0, 1.0, 1.0]
    assert len(backend.calls) == 4

    # The canonical embeddings are cached, while the new candidate crop is
    # analyzed once for this new matrix invocation.
    build_identity_score_matrix(
        make_group(registry, candidates),
        registry,
        identity_validator=validator,
        identity_threshold=0.99,
    )
    assert len(backend.calls) == 5


def test_no_face_candidate_is_reported_for_every_subject_without_mismatch():
    registry = make_registry("insightface", "insightface")
    validator, _ = make_validator({
        10: [face([1, 0])],
        11: [face([0, 1])],
        1: [],
    })

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1)]),
        registry,
        identity_validator=validator,
    )["woman"]

    assert all(
        pair.evaluated is False
        and pair.identity_similarity is None
        and pair.status == "not_evaluated_no_face"
        for row in matrix.scores.values()
        for pair in row.values()
    )
    assert all(
        "mismatch" not in pair.status
        for row in matrix.scores.values()
        for pair in row.values()
    )


def test_canonical_failure_isolated_to_one_subject_and_other_rows_score():
    registry = make_registry("insightface", "insightface")
    validator, _ = make_validator({
        10: [face([1, 0])],
        11: [],
        1: [face([1, 0])],
    })

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1)]),
        registry,
        identity_validator=validator,
    )["woman"]

    assert matrix.scores["subject-1"][0].status == "identity_score"
    assert matrix.scores["subject-2"][0].status == "canonical_face_not_found"
    assert matrix.scores["subject-2"][0].identity_similarity is None


def test_unsupported_backend_does_not_invoke_identity_validator_for_that_row():
    registry = make_registry("insightface", "future_backend")
    validator, backend = make_validator({
        10: [face([1, 0])],
        1: [face([1, 0])],
    })
    before = {
        key: dict(record)
        for key, record in registry.items()
    }

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1)]),
        registry,
        identity_validator=validator,
    )["woman"]

    assert matrix.scores["subject-2"][0].status == "identity_backend_unavailable"
    assert matrix.scores["subject-2"][0].evaluated is False
    assert backend.calls == [10, 1]
    assert {
        key: dict(record)
        for key, record in registry.items()
    } == before


def test_ambiguous_candidate_face_isolated_without_assignment():
    registry = make_registry("insightface")
    validator, _ = make_validator({
        10: [face([1, 0])],
        1: [face([1, 0]), face([0, 1])],
    })

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1)]),
        registry,
        identity_validator=validator,
    )["woman"]

    pair = matrix.scores["subject-1"][0]
    assert pair.status == "ambiguous_candidate_faces"
    assert pair.identity_similarity is None


def test_candidate_model_error_isolated_to_one_column_and_reports_exception(capsys):
    registry = make_registry("insightface", "insightface")
    validator, _ = make_validator({
        10: [face([1, 0])],
        11: [face([0, 1])],
        1: [face([1, 0])],
        2: RuntimeError("candidate analysis failed"),
    })

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1), candidate(1, 2)]),
        registry,
        identity_validator=validator,
    )["woman"]

    assert matrix.scores["subject-1"][0].status == "identity_score"
    assert matrix.scores["subject-2"][0].status == "identity_score"
    assert matrix.scores["subject-1"][1].status == "identity_model_error"
    assert matrix.scores["subject-2"][1].status == "identity_model_error"
    assert matrix.scores["subject-1"][1].error == (
        "RuntimeError: candidate analysis failed"
    )
    assert matrix.scores["subject-2"][1].error == (
        "RuntimeError: candidate analysis failed"
    )
    assert "RuntimeError: candidate analysis failed" in capsys.readouterr().out


def test_canonical_model_error_reports_exception_without_becoming_no_face(capsys):
    registry = make_registry("insightface")
    validator, _ = make_validator({
        10: RuntimeError("canonical backend failed"),
        1: [face([1, 0])],
    })

    matrix = build_identity_score_matrix(
        make_group(registry, [candidate(0, 1)]),
        registry,
        identity_validator=validator,
    )["woman"]

    pair = matrix.scores["subject-1"][0]
    assert pair.status == "identity_model_error"
    assert pair.status != "canonical_face_not_found"
    assert pair.error.startswith("RuntimeError: canonical backend failed")
    assert "RuntimeError: canonical backend failed" in capsys.readouterr().out
