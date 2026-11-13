"""Degree progress: requirement state, and the rule that in-progress is not completed."""

from __future__ import annotations

import pytest

from app.domain.degree_progress import (
    RequirementState,
    _evaluate_all_group,
    calculate_degree_progress,
)
from app.domain.models import RequirementGroup, RuleType
from app.ingestion.dataset import AcademicDataset


def test_student_001_history_is_satisfied_by_completed_hist_250(
    dataset: AcademicDataset,
) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)
    history = progress.group("history")

    assert history.state is RequirementState.SATISFIED
    assert history.satisfied_by == ("HIST 250",)
    assert history.completed_members == ("HIST 250",)
    assert history.courses_short == 0


def test_student_001_physics_core_is_remaining(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)
    core = progress.group("physics-core")

    assert core.state is RequirementState.REMAINING
    assert core.required_count == 5
    assert core.completed_members == ("PHYS 230",)
    assert set(core.remaining_options) == {
        "PHYS 110",
        "PHYS 120",
        "MATH 150",
        "MATH 160",
    }
    assert core.courses_short == 4


def test_student_001_electives_remain_one_choice_short_of_two(
    dataset: AcademicDataset,
) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)
    electives = progress.group("physics-electives")

    # One of the two required electives is in progress, so the requirement is not
    # yet on track: it still needs a second choice.
    assert electives.state is RequirementState.REMAINING
    assert electives.in_progress_members == ("PHYS 350",)
    assert electives.completed_members == ()
    assert electives.satisfied_by == ()
    assert electives.courses_short == 1
    assert "PHYS 340" in electives.remaining_options


def test_in_progress_is_never_reported_as_completed(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)
    literature = progress.group("literature")

    assert literature.state is RequirementState.IN_PROGRESS
    assert literature.completed_members == ()
    assert literature.satisfied_by == ()
    assert literature.in_progress_members == ("ENGL 120",)


def test_student_001_capstone_is_remaining(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)

    assert progress.group("capstone").state is RequirementState.REMAINING


def test_student_001_overall_state_is_in_progress(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)

    assert progress.state is RequirementState.IN_PROGRESS
    assert progress.satisfied_group_ids == ("history",)


def test_student_002_electives_are_remaining_with_a_two_course_shortfall(
    dataset: AcademicDataset,
) -> None:
    progress = calculate_degree_progress(dataset.student("student-002"), dataset.catalog)
    electives = progress.group("physics-electives")

    assert electives.state is RequirementState.REMAINING
    assert electives.completed_members == ()
    assert electives.in_progress_members == ()
    assert electives.courses_short == 2


def test_student_002_core_is_five_courses_short(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-002"), dataset.catalog)

    assert progress.group("physics-core").state is RequirementState.REMAINING
    assert progress.group("physics-core").courses_short == 5


def test_student_002_alternatives_are_in_progress_not_completed(
    dataset: AcademicDataset,
) -> None:
    progress = calculate_degree_progress(dataset.student("student-002"), dataset.catalog)

    assert progress.group("literature").state is RequirementState.IN_PROGRESS
    assert progress.group("literature").in_progress_members == ("ENGL 120",)
    assert progress.group("history").state is RequirementState.IN_PROGRESS
    assert progress.group("history").in_progress_members == ("HIST 250",)


def test_group_lookup_rejects_unknown_ids(dataset: AcademicDataset) -> None:
    progress = calculate_degree_progress(dataset.student("student-001"), dataset.catalog)

    with pytest.raises(KeyError):
        progress.group("no-such-group")


def test_unknown_group_member_is_unable_to_determine(dataset: AcademicDataset) -> None:
    group = RequirementGroup(
        group_id="ghost",
        label="Ghost",
        rule_type=RuleType.ALL,
        required_course_ids=("PHYS 110", "GHOST 999"),
    )

    progress = _evaluate_all_group(group, dataset.student("student-001"), dataset.catalog)

    assert progress.state is RequirementState.UNABLE_TO_DETERMINE
    assert "GHOST 999" in progress.notes[0]
