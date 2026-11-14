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
from app.domain.models import (
    AcademicPolicy,
    Course,
    CourseRecord,
    CourseStatus,
    InProgressPrerequisitePolicy,
    Program,
    RequirementGroup,
    RuleType,
    Student,
)
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


# --- Programme scoping ---------------------------------------------------------------


def _course(code: str, *, prerequisites: tuple[str, ...] = ()) -> Course:
    return Course(
        course_id=code,
        course_code=code,
        title=code,
        units=4,
        prerequisite_course_ids=prerequisites,
        terms_offered=frozenset({"Spring"}),
    )


def _two_programme_catalog() -> AcademicCatalog:
    """Programmes that share PHYS 110 but treat it differently."""
    policy = AcademicPolicy(
        current_term=Term.parse("Fall 2026"),
        next_term=Term.parse("Spring 2027"),
        max_units_per_term=16,
        in_progress_prerequisites=InProgressPrerequisitePolicy(allowed=True),
    )
    courses = (
        _course("PHYS 110"),
        _course("PHYS 120", prerequisites=("PHYS 110",)),
        _course("PHYS 220"),
    )
    programs = (
        Program(
            program_id="program-a",
            name="Programme A",
            requirement_groups=(
                RequirementGroup(
                    group_id="a-elective",
                    label="A elective",
                    rule_type=RuleType.CHOOSE,
                    required_course_ids=("PHYS 110", "PHYS 220"),
                    count=1,
                ),
            ),
        ),
        Program(
            program_id="program-b",
            name="Programme B",
            requirement_groups=(
                RequirementGroup(
                    group_id="b-core",
                    label="B core",
                    rule_type=RuleType.ALL,
                    required_course_ids=("PHYS 110", "PHYS 120"),
                ),
            ),
        ),
    )
    return AcademicCatalog(policy=policy, courses=courses, programs=programs)


def _student_in(program_id: str) -> Student:
    return Student(
        student_id=f"student-{program_id}",
        academic_level="Freshman",
        program_id=program_id,
        adviser_id="adviser-001",
    )


def test_requirement_groups_come_only_from_the_students_programme() -> None:
    catalog = _two_programme_catalog()

    # b-core requires PHYS 110 for programme B; for programme A it is only an option.
    result = evaluate_course(catalog.course("PHYS 110"), _student_in("program-a"), catalog, SPRING)

    assert result.requirement_groups == ("a-elective",)
    assert result.mandatory is False
    assert result.priority == 1


def test_unlock_score_ignores_other_programmes_requirements() -> None:
    catalog = _two_programme_catalog()

    # PHYS 120 requires PHYS 110 but belongs only to programme B's b-core group.
    program_a = evaluate_course(
        catalog.course("PHYS 110"), _student_in("program-a"), catalog, SPRING
    )
    program_b = evaluate_course(
        catalog.course("PHYS 110"), _student_in("program-b"), catalog, SPRING
    )

    assert program_a.unlock_score == 0
    assert program_b.unlock_score == 1


def test_unlock_score_does_not_count_dependants_already_taken() -> None:
    catalog = _two_programme_catalog()
    student = Student(
        student_id="student-program-b",
        academic_level="Sophomore",
        program_id="program-b",
        adviser_id="adviser-001",
        completed_courses=(
            CourseRecord(
                course_id="PHYS 120",
                term=Term.parse("Fall 2025"),
                status=CourseStatus.COMPLETED,
            ),
        ),
    )

    # PHYS 110 used to unlock PHYS 120, but that dependant is already completed.
    result = evaluate_course(catalog.course("PHYS 110"), student, catalog, SPRING)

    assert result.unlock_score == 0

