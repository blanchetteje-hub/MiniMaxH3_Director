import copy

import pytest

from dino_continuity import (
    IdentityScoreMatrix,
    IdentityScorePair,
    SubjectCandidateAssignment,
    assign_subject_candidates,
)


def pair(subject, candidate_index, score=None, *, status="identity_score", evaluated=True):
    return IdentityScorePair(
        subject_key=subject,
        candidate_index=candidate_index,
        evaluated=evaluated,
        identity_similarity=score,
        status=status,
        identity_backend="insightface",
    )


def matrix(rows, candidate_indices, *, query="woman", threshold=None):
    subject_keys = tuple(rows)
    return IdentityScoreMatrix(
        dino_query=query,
        subject_keys=subject_keys,
        candidate_indices=tuple(candidate_indices),
        scores={
            subject: {
                candidate_index: pair(subject, candidate_index, score)
                for candidate_index, score in row.items()
            }
            for subject, row in rows.items()
        },
        identity_threshold=threshold,
    )


def test_three_subjects_receive_unique_obvious_assignments():
    result = assign_subject_candidates({
        "woman": matrix({
            "amy": {0: 0.9, 1: 0.1, 2: 0.1},
            "beth": {0: 0.1, 1: 0.9, 2: 0.1},
            "claire": {0: 0.1, 1: 0.1, 2: 0.9},
        }, [0, 1, 2]),
    })

    assert {
        subject: assignment.candidate_index
        for subject, assignment in result.items()
    } == {"amy": 0, "beth": 1, "claire": 2}
    assert all(
        assignment.assigned
        and assignment.status == "identity_assigned"
        for assignment in result.values()
    )


def test_two_subjects_competing_for_one_candidate_leave_one_unmatched():
    result = assign_subject_candidates({
        "woman": matrix({
            "amy": {0: 0.9},
            "beth": {0: 0.8},
        }, [0]),
    })

    assigned = [item for item in result.values() if item.assigned]
    unmatched = [item for item in result.values() if not item.assigned]
    assert len(assigned) == 1
    assert assigned[0].candidate_index == 0
    assert len(unmatched) == 1
    assert unmatched[0].status == "no_eligible_candidate"


def test_global_assignment_beats_greedy_row_selection():
    result = assign_subject_candidates(
        {
            "woman": matrix({
                "amy": {0: 0.90, 1: 0.89},
                "beth": {0: 0.88, 1: 0.30},
            }, [0, 1], threshold=0.10),
        },
        identity_threshold=0.10,
        identity_margin=0.05,
    )

    assert result["amy"].candidate_index == 1
    assert result["beth"].candidate_index == 0


def test_below_threshold_pair_is_not_assigned():
    result = assign_subject_candidates({
        "woman": matrix({"amy": {0: 0.47}}, [0]),
    })

    assert result["amy"].assigned is False
    assert result["amy"].candidate_index is None
    assert result["amy"].status == "no_eligible_candidate"


def test_more_subjects_than_candidates_leave_subjects_unmatched():
    result = assign_subject_candidates({
        "woman": matrix({
            "amy": {0: 0.9},
            "beth": {0: 0.8},
            "claire": {0: 0.7},
        }, [0]),
    })

    assert sum(item.assigned for item in result.values()) == 1
    assert sum(not item.assigned for item in result.values()) == 2


def test_more_candidates_than_subjects_leave_candidates_unused():
    result = assign_subject_candidates({
        "woman": matrix({"amy": {0: 0.9, 1: 0.8, 2: 0.7}}, [0, 1, 2]),
    })

    assert result["amy"].assigned is True
    assert result["amy"].candidate_index == 0


def test_uniform_no_face_status_is_preserved():
    score_matrix = IdentityScoreMatrix(
        dino_query="woman",
        subject_keys=("amy",),
        candidate_indices=(0, 1),
        scores={
            "amy": {
                0: pair("amy", 0, status="not_evaluated_no_face", evaluated=False),
                1: pair("amy", 1, status="not_evaluated_no_face", evaluated=False),
            }
        },
    )

    result = assign_subject_candidates({"woman": score_matrix})["amy"]

    assert result.assigned is False
    assert result.status == "not_evaluated_no_face"


def test_unsupported_backend_status_is_preserved():
    score_matrix = IdentityScoreMatrix(
        dino_query="robot",
        subject_keys=("robot-1",),
        candidate_indices=(0,),
        scores={
            "robot-1": {
                0: IdentityScorePair(
                    subject_key="robot-1",
                    candidate_index=0,
                    evaluated=False,
                    identity_similarity=None,
                    status="identity_backend_unavailable",
                    identity_backend="dino_v2",
                )
            }
        },
    )

    result = assign_subject_candidates({"robot": score_matrix})["robot-1"]

    assert result.status == "identity_backend_unavailable"
    assert result.identity_backend == "dino_v2"


def test_row_margin_is_applied_after_assignment_not_before():
    result = assign_subject_candidates(
        {
            "woman": matrix({"amy": {0: 0.72, 1: 0.70}}, [0, 1]),
        },
        identity_margin=0.05,
    )

    assert result["amy"].assigned is False
    assert result["amy"].status == "ambiguous_identity"


def test_candidate_margin_marks_competing_unassigned_subject_ambiguous():
    result = assign_subject_candidates(
        {
            "woman": matrix({
                "amy": {0: 0.72},
                "beth": {0: 0.71},
            }, [0]),
        },
        identity_margin=0.05,
    )

    assert result["amy"].assigned is False
    assert result["beth"].assigned is False
    assert result["amy"].status == "ambiguous_identity"
    assert result["beth"].status == "ambiguous_identity"


def test_multiple_query_groups_are_assigned_independently():
    result = assign_subject_candidates({
        "woman": matrix({"amy": {0: 0.9}}, [0], query="woman"),
        "man": matrix({"frank": {0: 0.9}}, [0], query="man"),
    })

    assert result["amy"].dino_query == "woman"
    assert result["frank"].dino_query == "man"
    assert result["amy"].candidate_index == 0
    assert result["frank"].candidate_index == 0


def test_assignment_is_pure_and_has_no_assignment_duplicates():
    score_matrix = matrix({
        "amy": {0: 0.9, 1: 0.1},
        "beth": {0: 0.8, 1: 0.7},
    }, [0, 1])
    before = copy.deepcopy(score_matrix)

    result = assign_subject_candidates({"woman": score_matrix})
    assigned_candidates = [
        item.candidate_index
        for item in result.values()
        if item.assigned
    ]

    assert len(assigned_candidates) == len(set(assigned_candidates))
    assert score_matrix == before
    assert all(isinstance(item, SubjectCandidateAssignment) for item in result.values())


def test_malformed_matrix_row_is_rejected():
    score_matrix = matrix({"amy": {0: 0.9}}, [0, 1])

    with pytest.raises(ValueError, match="does not match candidate columns"):
        assign_subject_candidates({"woman": score_matrix})
