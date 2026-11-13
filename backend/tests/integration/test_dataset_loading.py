"""The supplied fixtures, loaded through the canonical adapters."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.domain.errors import DatasetError, UnknownStudentError
from app.domain.models import RuleType
from app.ingestion.dataset import CATALOGUE_PATH, AcademicDataset, load_dataset


def test_catalogue_shape_matches_the_supplied_fixture(dataset: AcademicDataset) -> None:
    assert len(dataset.catalog.courses) == 14
    assert len(dataset.catalog.programs) == 1
    assert len(dataset.catalog.programs[0].requirement_groups) == 5
    assert len(dataset.catalog.reading_documents) == 5


def test_student_records_match_the_documented_snapshot(dataset: AcademicDataset) -> None:
    assert {student.student_id for student in dataset.students} == {
        "student-001",
        "student-002",
    }

    first = dataset.student("student-001")
    assert first.academic_level == "Sophomore"
    assert first.program_id == "bachelor-of-science-physics"
    assert first.adviser_id == "adviser-001"
    assert set(first.completed_course_ids) == {"PHYS 230", "HIST 250"}
    assert set(first.current_course_ids) == {"PHYS 350", "HIST 210", "ENGL 120"}

    second = dataset.student("student-002")
    assert second.academic_level == "Freshman"
    assert second.adviser_id == "adviser-002"
    assert second.completed_course_ids == ()
    assert set(second.current_course_ids) == {"HIST 250", "ENGL 120"}


def test_policy_matches_the_scenario(dataset: AcademicDataset) -> None:
    policy = dataset.catalog.policy

    assert policy.current_term.label == "Fall 2026"
    assert policy.next_term.label == "Spring 2027"
    assert policy.max_units_per_term == 16
    assert policy.in_progress_prerequisites.allowed is True
    assert policy.in_progress_prerequisites.source_statement is not None


def test_every_supplied_course_carries_four_units(dataset: AcademicDataset) -> None:
    assert {course.units for course in dataset.catalog.courses} == {4}


def test_spring_offerings_match_the_catalogue(dataset: AcademicDataset) -> None:
    expected = {
        "PHYS 110",
        "PHYS 120",
        "PHYS 320",
        "PHYS 340",
        "PHYS 490",
        "MATH 150",
        "MATH 160",
        "ENGL 120",
        "ENGL 130",
        "HIST 210",
    }

    offered = {
        course.course_code for course in dataset.catalog.courses if course.offered_in("Spring")
    }

    assert offered == expected


def test_fall_only_offerings_match_the_catalogue(dataset: AcademicDataset) -> None:
    fall_only = {
        course.course_code
        for course in dataset.catalog.courses
        if course.offered_in("Fall") and not course.offered_in("Spring")
    }

    assert fall_only == {"PHYS 230", "PHYS 330", "PHYS 350", "HIST 250"}


def test_prerequisites_match_the_catalogue(dataset: AcademicDataset) -> None:
    expected = {
        "PHYS 110": set(),
        "PHYS 120": {"PHYS 110", "MATH 150"},
        "PHYS 230": set(),
        "PHYS 320": {"PHYS 120"},
        "PHYS 330": {"PHYS 230"},
        "PHYS 340": {"PHYS 230"},
        "PHYS 350": {"PHYS 230"},
        "PHYS 490": {"PHYS 350", "PHYS 120"},
        "MATH 150": set(),
        "MATH 160": {"MATH 150"},
        "ENGL 120": set(),
        "ENGL 130": set(),
        "HIST 210": set(),
        "HIST 250": set(),
    }

    actual = {
        course.course_code: set(course.prerequisite_course_ids)
        for course in dataset.catalog.courses
    }

    assert actual == expected


def test_requirement_groups_match_the_catalogue(dataset: AcademicDataset) -> None:
    groups = {
        group.group_id: group
        for group in dataset.catalog.program("bachelor-of-science-physics").requirement_groups
    }

    assert set(groups) == {
        "physics-core",
        "physics-electives",
        "literature",
        "history",
        "capstone",
    }
    assert groups["physics-core"].rule_type is RuleType.ALL
    assert groups["physics-core"].required_count == 5
    assert groups["physics-electives"].rule_type is RuleType.CHOOSE
    assert groups["physics-electives"].required_count == 2
    assert groups["literature"].required_count == 1
    assert groups["history"].required_count == 1
    assert groups["capstone"].required_count == 1


def test_source_provenance_is_recorded(dataset: AcademicDataset, data_root: Path) -> None:
    payload = (data_root / CATALOGUE_PATH).read_bytes()
    expected_sha = hashlib.sha256(payload).hexdigest()

    assert dataset.catalogue_source.sha256 == expected_sha
    assert dataset.catalogue_source.source_version == expected_sha[:12]
    assert "courses" in dataset.catalogue_source.raw
    assert "students" in dataset.students_source.raw


def test_reading_documents_join_the_manifest(dataset: AcademicDataset) -> None:
    document = dataset.catalog.document("phys230-critical-mass")

    assert document is not None
    assert document.course_id == "PHYS 230"
    assert document.title == "Critical mass"
    assert document.week == 6
    assert document.source_filename == "phys230-critical-mass.pdf"
    assert document.page_count == 11
    assert document.file_checksum == (
        "9cc30f28212b81a3886bb418511630c932ddab8a7150015d95b2ee86941f6539"
    )


def test_unknown_student_is_rejected(dataset: AcademicDataset) -> None:
    with pytest.raises(UnknownStudentError):
        dataset.student("student-999")


def test_missing_data_root_is_reported(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="missing source file"):
        load_dataset(tmp_path)
