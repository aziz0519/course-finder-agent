"""Prerequisite and term eligibility, pinned to the supplied fixtures."""

from __future__ import annotations

import pytest

from app.domain.catalog import AcademicCatalog
from app.domain.eligibility import (
    IneligibilityReason,
    eligible_courses,
    evaluate_all,
    evaluate_course,
)
from app.domain.errors import UnknownCourseError
from app.domain.models import CourseStatus
from app.domain.terms import Term
from app.ingestion.dataset import AcademicDataset

SPRING = Term.parse("Spring 2027")


@pytest.fixture
def catalog(dataset: AcademicDataset) -> AcademicCatalog:
    return dataset.catalog


def candidate_ids(dataset: AcademicDataset, student_id: str) -> set[str]:
    student = dataset.student(student_id)
    return {entry.course_id for entry in eligible_courses(student, dataset.catalog, SPRING)}


def decision(dataset: AcademicDataset, student_id: str, course_id: str):
    return evaluate_course(
        dataset.catalog.course(course_id),
        dataset.student(student_id),
        dataset.catalog,
        SPRING,
    )


# --- Required regression expectations ------------------------------------------------


def test_student_001_candidates_match_the_specified_set(dataset: AcademicDataset) -> None:
    assert candidate_ids(dataset, "student-001") == {
        "PHYS 110",
        "MATH 150",
        "PHYS 340",
        "ENGL 130",
    }


def test_student_002_candidates_match_the_specified_set(dataset: AcademicDataset) -> None:
    assert candidate_ids(dataset, "student-002") == {
        "PHYS 110",
        "MATH 150",
        "ENGL 130",
        "HIST 210",
    }


def test_phys_340_is_eligible_for_student_001_on_completed_phys_230(
    dataset: AcademicDataset,
) -> None:
    result = decision(dataset, "student-001", "PHYS 340")

    assert result.eligible is True
    assert [evidence.course_id for evidence in result.prerequisite.met] == ["PHYS 230"]
    assert result.prerequisite.met[0].status is CourseStatus.COMPLETED
    assert result.prerequisite.met[0].term == Term.parse("Fall 2025")


def test_phys_340_is_ineligible_for_student_002(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-002", "PHYS 340")

    assert result.eligible is False
    assert IneligibilityReason.PREREQUISITE_NOT_MET in result.reasons
    assert result.prerequisite.missing == ("PHYS 230",)


def test_phys_490_is_blocked_by_the_unmet_phys_120_chain(
    dataset: AcademicDataset,
) -> None:
    result = decision(dataset, "student-001", "PHYS 490")

    assert result.eligible is False
    assert result.prerequisite.missing == ("PHYS 120",)
    assert result.prerequisite.in_progress_used == ("PHYS 350",)


def test_phys_120_is_not_satisfied_by_concurrently_planned_courses(
    dataset: AcademicDataset,
) -> None:
    # PHYS 110 and MATH 150 are themselves Spring 2027 candidates for student-002.
    # They must still not satisfy PHYS 120's prerequisites for that same term.
    assert {"PHYS 110", "MATH 150"} <= candidate_ids(dataset, "student-002")

    result = decision(dataset, "student-002", "PHYS 120")

    assert result.eligible is False
    assert set(result.prerequisite.missing) == {"PHYS 110", "MATH 150"}


def test_phys_120_and_phys_490_are_never_recommended_for_student_001(
    dataset: AcademicDataset,
) -> None:
    candidates = candidate_ids(dataset, "student-001")

    assert "PHYS 120" not in candidates
    assert "PHYS 490" not in candidates


# --- Exclusion and term rules --------------------------------------------------------


def test_completed_course_is_excluded(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-001", "PHYS 230")

    assert result.eligible is False
    assert IneligibilityReason.ALREADY_COMPLETED in result.reasons


def test_in_progress_course_is_excluded(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-001", "PHYS 350")

    assert result.eligible is False
    assert IneligibilityReason.CURRENTLY_IN_PROGRESS in result.reasons


def test_fall_only_course_is_not_offered_in_spring(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-002", "HIST 250")

    assert result.eligible is False
    assert IneligibilityReason.NOT_OFFERED_IN_TERM in result.reasons
    assert IneligibilityReason.CURRENTLY_IN_PROGRESS in result.reasons


def test_no_candidate_falls_outside_the_target_season(dataset: AcademicDataset) -> None:
    student = dataset.student("student-001")

    for entry in eligible_courses(student, dataset.catalog, SPRING):
        assert entry.course.offered_in("Spring")
        assert entry.target_term == SPRING


# --- Policy scope --------------------------------------------------------------------


def test_in_progress_prerequisites_apply_to_the_next_term_only(dataset: AcademicDataset) -> None:
    policy = dataset.catalog.policy
    later = Term.parse("Fall 2027")

    assert policy.allows_in_progress_prerequisites_for(policy.next_term) is True
    assert policy.allows_in_progress_prerequisites_for(later) is False

    result = evaluate_course(
        dataset.catalog.course("PHYS 490"),
        dataset.student("student-001"),
        dataset.catalog,
        later,
    )

    assert "PHYS 350" in result.prerequisite.missing
    assert "PHYS 350" in result.prerequisite.in_progress_not_applicable


# --- Ranking and explanations --------------------------------------------------------


def test_ranking_prefers_required_courses_then_unlock_value(
    dataset: AcademicDataset,
) -> None:
    student = dataset.student("student-001")
    ranked = eligible_courses(student, dataset.catalog, SPRING)

    assert [entry.course_id for entry in ranked[:2]] == ["MATH 150", "PHYS 110"]
    assert [entry.mandatory for entry in ranked[:2]] == [True, True]
    assert ranked[0].unlock_score == 2  # unlocks PHYS 120 and MATH 160
    assert ranked[1].unlock_score == 1  # unlocks PHYS 120


def test_eligible_decision_explains_its_evidence(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-001", "PHYS 340")
    explanation = " ".join(result.explanation)

    assert "Prerequisite PHYS 230 satisfied by completed Fall 2025." in explanation
    assert "Offered in Spring 2027." in explanation
    assert "physics-electives" in explanation


def test_ineligible_decision_explains_the_gap(dataset: AcademicDataset) -> None:
    result = decision(dataset, "student-002", "PHYS 340")
    explanation = " ".join(result.explanation)

    assert "requires PHYS 230" in explanation
    assert "not satisfied by completed courses" in explanation


def test_every_catalogue_course_receives_a_decision(dataset: AcademicDataset) -> None:
    student = dataset.student("student-001")

    decisions = evaluate_all(student, dataset.catalog, SPRING)

    assert len(decisions) == len(dataset.catalog.courses)
    assert {entry.course_id for entry in decisions} == set(dataset.catalog.course_ids)


def test_unknown_course_fails_closed(dataset: AcademicDataset) -> None:
    with pytest.raises(UnknownCourseError):
        dataset.catalog.course("PHYS 999")

    with pytest.raises(UnknownCourseError):
        dataset.catalog.groups_for_course("PHYS 999")
