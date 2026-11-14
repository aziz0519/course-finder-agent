"""Source adapters: happy path and every fail-closed rule.

These use deliberately minimal synthetic sources so the adapter's rules are tested
without depending on the shape of the supplied fixtures. Real-fixture assertions live
in ``test_dataset_loading.py``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.domain.errors import DatasetError, PolicyError, UnknownProgramError
from app.domain.models import CourseStatus, RuleType
from app.ingestion.json_adapters import adapt_catalogue, adapt_students

IN_PROGRESS_STATEMENT = (
    "A course in progress counts toward the prerequisites of courses in the following term."
)


def catalogue_source() -> dict[str, Any]:
    return {
        "current_term": "Fall 2026",
        "next_term": "Spring 2027",
        "policies": {
            "max_units_per_term": 16,
            "in_progress_prerequisites": IN_PROGRESS_STATEMENT,
        },
        "courses": [
            {
                "course_code": "TEST 100",
                "title": "Foundations",
                "units": 4,
                "description": None,
                "prerequisites": [],
                "terms_offered": ["Fall", "Spring"],
                "materials": None,
            },
            {
                "course_code": "TEST 200",
                "title": "Continuation",
                "units": 4,
                "description": None,
                "prerequisites": ["TEST 100"],
                "terms_offered": ["Spring"],
                "materials": None,
            },
        ],
        "programs": [
            {
                "program_id": "prog",
                "name": "Programme",
                "requirement_groups": [
                    {
                        "requirement_id": "core",
                        "name": "Core",
                        "rule": "all",
                        "courses": ["TEST 100", "TEST 200"],
                    }
                ],
            }
        ],
    }


def student_source() -> dict[str, Any]:
    return {
        "students": [
            {
                "student_id": "student-x",
                "academic_level": "Sophomore",
                "program_id": "prog",
                "adviser_id": "adviser-x",
                "completed_courses": [{"course_code": "TEST 100", "term": "Fall 2025"}],
                "enrolled_courses": [],
            }
        ]
    }


def adapt_catalogue_from(source: dict[str, Any], root: Path):
    return adapt_catalogue(source, dataset_root=root)


# --- Catalogue happy path ------------------------------------------------------------


def test_catalogue_adapts_courses_programme_and_policy(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)

    assert len(catalog.courses) == 2
    assert len(catalog.programs) == 1
    assert catalog.policy.max_units_per_term == 16
    assert catalog.policy.current_term.label == "Fall 2026"
    assert catalog.policy.next_term.label == "Spring 2027"
    assert catalog.course("TEST 200").prerequisite_course_ids == ("TEST 100",)
    assert catalog.course("TEST 200").terms_offered == frozenset({"Spring"})


def test_requirement_group_rules_are_normalised(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"].append(
        {
            "requirement_id": "choice",
            "name": "Choice",
            "rule": "choose",
            "count": 1,
            "courses": ["TEST 100", "TEST 200"],
        }
    )

    catalog = adapt_catalogue_from(source, tmp_path)
    groups = catalog.program("prog").requirement_groups

    assert groups[0].rule_type is RuleType.ALL
    assert groups[0].required_count == 2
    assert groups[0].count is None
    assert groups[1].rule_type is RuleType.CHOOSE
    assert groups[1].required_count == 1


def test_in_progress_rule_is_typed_and_keeps_its_source_statement(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)

    policy = catalog.policy.in_progress_prerequisites
    assert policy.allowed is True
    assert policy.source_statement == IN_PROGRESS_STATEMENT


def test_absent_in_progress_rule_is_not_assumed(tmp_path: Path) -> None:
    source = catalogue_source()
    del source["policies"]["in_progress_prerequisites"]

    catalog = adapt_catalogue_from(source, tmp_path)

    assert catalog.policy.in_progress_prerequisites.allowed is False
    assert catalog.policy.in_progress_prerequisites.source_statement is None


def test_unrecognised_in_progress_rule_is_refused(tmp_path: Path) -> None:
    source = catalogue_source()
    source["policies"]["in_progress_prerequisites"] = "Ask your adviser."

    with pytest.raises(PolicyError, match="refusing to guess"):
        adapt_catalogue_from(source, tmp_path)


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(
            "A course in progress does not count toward the prerequisites of courses in the "
            "following term.",
            id="negated-does-not-count",
        ),
        pytest.param(
            "A course in progress is not counted toward the prerequisites of courses in the "
            "following term.",
            id="negated-not-counted",
        ),
        pytest.param(
            "A course in progress may count toward the prerequisites of courses in the "
            "following term only if the department approves.",
            id="conditional-may-if-approved",
        ),
        pytest.param(
            "A course in progress counts toward the prerequisites of courses in the following "
            "term when the adviser approves.",
            id="conditional-when-approved",
        ),
    ],
)
def test_negated_or_conditional_in_progress_rule_is_refused(tmp_path: Path, statement: str) -> None:
    # Each statement contains the same keywords as the supported rule, so keyword
    # presence alone must not grant in-progress prerequisite credit.
    source = catalogue_source()
    source["policies"]["in_progress_prerequisites"] = statement

    with pytest.raises(PolicyError, match="refusing to guess"):
        adapt_catalogue_from(source, tmp_path)


def test_unknown_policy_key_is_refused(tmp_path: Path) -> None:
    source = catalogue_source()
    source["policies"]["late_withdrawal"] = "allowed until week 8"

    with pytest.raises(PolicyError, match="cannot honour"):
        adapt_catalogue_from(source, tmp_path)


def test_requirements_key_is_accepted_as_an_alias(tmp_path: Path) -> None:
    source = catalogue_source()
    program = source["programs"][0]
    program["requirements"] = program.pop("requirement_groups")

    catalog = adapt_catalogue_from(source, tmp_path)

    assert len(catalog.program("prog").requirement_groups) == 1


# --- Catalogue fail-closed rules -----------------------------------------------------


def test_missing_prerequisite_list_is_not_treated_as_empty(tmp_path: Path) -> None:
    source = catalogue_source()
    del source["courses"][0]["prerequisites"]

    with pytest.raises(DatasetError, match="missing 'prerequisites'"):
        adapt_catalogue_from(source, tmp_path)


def test_unknown_prerequisite_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["courses"][1]["prerequisites"] = ["TEST 999"]

    with pytest.raises(DatasetError, match="not in the catalogue"):
        adapt_catalogue_from(source, tmp_path)


def test_unsupported_requirement_rule_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0]["rule"] = "any"

    with pytest.raises(DatasetError, match="unsupported rule"):
        adapt_catalogue_from(source, tmp_path)


def test_choose_count_beyond_options_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0] = {
        "requirement_id": "choose",
        "name": "Choose",
        "rule": "choose",
        "count": 3,
        "courses": ["TEST 100", "TEST 200"],
    }

    with pytest.raises(DatasetError, match="needs 3 of 2"):
        adapt_catalogue_from(source, tmp_path)


def test_duplicate_members_in_a_choose_group_are_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0] = {
        "requirement_id": "choose",
        "name": "Choose",
        "rule": "choose",
        "count": 2,
        "courses": ["TEST 100", "TEST 100"],
    }

    # Without the duplicate check, the repeated member would satisfy count=2.
    with pytest.raises(DatasetError, match="duplicate course"):
        adapt_catalogue_from(source, tmp_path)


def test_duplicate_members_in_an_all_group_are_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0]["courses"] = ["TEST 100", "TEST 100"]

    with pytest.raises(DatasetError, match="duplicate course"):
        adapt_catalogue_from(source, tmp_path)


def test_all_rule_must_not_declare_a_count(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0]["count"] = 1

    with pytest.raises(DatasetError, match="must not declare count"):
        adapt_catalogue_from(source, tmp_path)


def test_duplicate_course_codes_are_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    duplicate = copy.deepcopy(source["courses"][0])
    source["courses"].append(duplicate)

    with pytest.raises(DatasetError, match="duplicate course id"):
        adapt_catalogue_from(source, tmp_path)


def test_unresolved_requirement_member_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["programs"][0]["requirement_groups"][0]["courses"] = ["TEST 100", "TEST 999"]

    with pytest.raises(DatasetError, match="not in the catalogue"):
        adapt_catalogue_from(source, tmp_path)


def test_unrecognised_term_label_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["current_term"] = "Autumn 2026"

    with pytest.raises(DatasetError, match="unrecognised term label"):
        adapt_catalogue_from(source, tmp_path)


def test_next_term_must_follow_current_term(tmp_path: Path) -> None:
    source = catalogue_source()
    source["next_term"] = "Fall 2026"

    with pytest.raises(DatasetError, match="must be after"):
        adapt_catalogue_from(source, tmp_path)


def test_non_positive_units_are_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["courses"][0]["units"] = 0

    with pytest.raises(DatasetError, match="units"):
        adapt_catalogue_from(source, tmp_path)


# --- Reading materials ---------------------------------------------------------------


def test_materials_become_reading_documents(tmp_path: Path) -> None:
    source = catalogue_source()
    source["courses"][0]["materials"] = [
        {"title": "A reading", "week": 3, "file": "course-materials/a-reading.pdf"}
    ]

    catalog = adapt_catalogue_from(source, tmp_path)
    course = catalog.course("TEST 100")

    assert course.reading_document_ids == ("a-reading",)
    document = catalog.document("a-reading")
    assert document is not None
    assert document.course_id == "TEST 100"
    assert document.source_filename == "a-reading.pdf"
    assert document.week == 3
    assert document.file_checksum is None


def test_material_path_traversal_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["courses"][0]["materials"] = [{"title": "Escape", "file": "../../../etc/passwd"}]

    with pytest.raises(DatasetError, match="inside the dataset"):
        adapt_catalogue_from(source, tmp_path)


def test_absolute_material_path_is_rejected(tmp_path: Path) -> None:
    source = catalogue_source()
    source["courses"][0]["materials"] = [{"title": "Absolute", "file": "/etc/passwd"}]

    with pytest.raises(DatasetError, match="inside the dataset"):
        adapt_catalogue_from(source, tmp_path)


# --- Students ------------------------------------------------------------------------


def test_students_adapt_with_explicit_status(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)

    students = adapt_students(student_source(), catalog=catalog)

    assert len(students) == 1
    student = students[0]
    assert student.student_id == "student-x"
    assert student.completed_course_ids == ("TEST 100",)
    assert student.completed_courses[0].status is CourseStatus.COMPLETED
    assert student.current_courses == ()


def test_completed_term_must_precede_the_current_term(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"][0]["completed_courses"][0]["term"] = "Fall 2026"

    with pytest.raises(DatasetError, match="not before the current term"):
        adapt_students(source, catalog=catalog)


def test_enrolled_term_must_be_the_current_term(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"][0]["enrolled_courses"] = [{"course_code": "TEST 200", "term": "Spring 2027"}]

    with pytest.raises(DatasetError, match="not the current term"):
        adapt_students(source, catalog=catalog)


def test_course_both_completed_and_enrolled_is_rejected(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"][0]["enrolled_courses"] = [{"course_code": "TEST 100", "term": "Fall 2026"}]

    with pytest.raises(DatasetError, match="both completed and in progress"):
        adapt_students(source, catalog=catalog)


def test_student_course_must_exist_in_the_catalogue(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"][0]["completed_courses"] = [{"course_code": "TEST 999", "term": "Fall 2025"}]

    with pytest.raises(DatasetError, match="unknown course"):
        adapt_students(source, catalog=catalog)


def test_student_programme_must_exist(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"][0]["program_id"] = "missing-programme"

    with pytest.raises(UnknownProgramError):
        adapt_students(source, catalog=catalog)


def test_duplicate_student_ids_are_rejected(tmp_path: Path) -> None:
    catalog = adapt_catalogue_from(catalogue_source(), tmp_path)
    source = student_source()
    source["students"].append(copy.deepcopy(source["students"][0]))

    with pytest.raises(DatasetError, match="duplicate student_id"):
        adapt_students(source, catalog=catalog)
