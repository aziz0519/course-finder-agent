"""Schedule proposals: the unit cap, deferral, and the no-filler rule."""

from __future__ import annotations

import pytest

from app.domain.planning import propose_schedule
from app.ingestion.dataset import AcademicDataset


def propose(dataset: AcademicDataset, student_id: str, cap: int | None = None):
    return propose_schedule(
        dataset.student(student_id),
        dataset.catalog,
        requested_unit_cap=cap,
    )


def test_default_proposal_advances_requirements_without_filling_capacity(
    dataset: AcademicDataset,
) -> None:
    proposal = propose(dataset, "student-001")

    assert set(proposal.recommended_course_ids) == {"PHYS 110", "MATH 150", "PHYS 340"}
    assert proposal.total_units == 12
    assert proposal.unit_cap == 16
    assert proposal.catalogue_max_units == 16
    assert proposal.deferred_course_ids == ()


def test_twelve_unit_request_matches_the_default(dataset: AcademicDataset) -> None:
    proposal = propose(dataset, "student-001", cap=12)

    assert set(proposal.recommended_course_ids) == {"PHYS 110", "MATH 150", "PHYS 340"}
    assert proposal.total_units == 12
    assert proposal.unit_cap == 12
    assert proposal.requested_unit_cap == 12


def test_eight_unit_request_defers_phys_340_without_making_it_ineligible(
    dataset: AcademicDataset,
) -> None:
    proposal = propose(dataset, "student-001", cap=8)

    assert set(proposal.recommended_course_ids) == {"PHYS 110", "MATH 150"}
    assert proposal.total_units == 8
    assert proposal.deferred_course_ids == ("PHYS 340",)
    assert proposal.is_capped is True
    assert proposal.deferred[0].eligible is True


def test_four_unit_request_recommends_the_single_best_core_course(
    dataset: AcademicDataset,
) -> None:
    proposal = propose(dataset, "student-001", cap=4)

    assert proposal.recommended_course_ids == ("MATH 150",)
    assert proposal.total_units == 4
    assert set(proposal.deferred_course_ids) == {"PHYS 110", "PHYS 340"}


def test_english_130_is_an_alternative_never_a_default_recommendation(
    dataset: AcademicDataset,
) -> None:
    for student_id in ("student-001", "student-002"):
        proposal = propose(dataset, student_id)

        assert "ENGL 130" not in proposal.recommended_course_ids
        assert "ENGL 130" in proposal.alternative_course_ids


def test_student_002_default_is_the_two_core_foundations(
    dataset: AcademicDataset,
) -> None:
    proposal = propose(dataset, "student-002")

    assert set(proposal.recommended_course_ids) == {"PHYS 110", "MATH 150"}
    assert proposal.total_units == 8
    assert set(proposal.alternative_course_ids) == {"ENGL 130", "HIST 210"}


@pytest.mark.parametrize("cap", [4, 8, 12, 16, 20, 32])
def test_proposal_never_exceeds_the_effective_cap(dataset: AcademicDataset, cap: int) -> None:
    proposal = propose(dataset, "student-001", cap=cap)

    assert proposal.total_units <= proposal.unit_cap
    assert proposal.unit_cap == min(cap, 16)


def test_a_cap_above_the_catalogue_maximum_is_clamped(dataset: AcademicDataset) -> None:
    proposal = propose(dataset, "student-001", cap=40)

    assert proposal.unit_cap == 16
    assert proposal.requested_unit_cap == 40


@pytest.mark.parametrize("cap", [0, -4])
def test_non_positive_caps_are_rejected(dataset: AcademicDataset, cap: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        propose(dataset, "student-001", cap=cap)


def test_a_request_cap_never_mutates_the_catalogue_policy(
    dataset: AcademicDataset,
) -> None:
    propose(dataset, "student-001", cap=8)
    propose(dataset, "student-001", cap=4)

    assert dataset.catalog.policy.max_units_per_term == 16


def test_proposals_are_deterministic(dataset: AcademicDataset) -> None:
    first = propose(dataset, "student-001", cap=12)
    second = propose(dataset, "student-001", cap=12)

    assert first.recommended_course_ids == second.recommended_course_ids
    assert first.total_units == second.total_units


def test_target_term_defaults_to_the_next_term(dataset: AcademicDataset) -> None:
    proposal = propose(dataset, "student-001")

    assert proposal.target_term == dataset.catalog.policy.next_term


def test_candidates_include_every_eligible_course(dataset: AcademicDataset) -> None:
    proposal = propose(dataset, "student-001")

    assert set(entry.course_id for entry in proposal.candidates) == {
        "PHYS 110",
        "MATH 150",
        "PHYS 340",
        "ENGL 130",
    }
    assert all(entry.eligible for entry in proposal.candidates)
