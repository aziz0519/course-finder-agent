"""Adapters from the supplied source shapes to canonical domain objects.

Every adapter fails closed: unknown rules, missing prerequisite lists, dangling
references, and inconsistent terms raise ``DatasetError`` rather than defaulting to a
convenient value. The raw source object is preserved by the caller for audit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.catalog import AcademicCatalog
from app.domain.errors import DatasetError, PolicyError, UnknownCourseError
from app.domain.models import (
    AcademicPolicy,
    Course,
    CourseRecord,
    CourseStatus,
    InProgressPrerequisitePolicy,
    Program,
    ReadingDocument,
    RequirementGroup,
    RuleType,
    Student,
)
from app.domain.terms import Term, coerce_season

_KNOWN_POLICY_KEYS = frozenset({"max_units_per_term", "in_progress_prerequisites"})


# --- Primitive readers ---------------------------------------------------------------


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DatasetError(f"{context}: expected an object")
    return value


def _sequence(value: object, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DatasetError(f"{context}: expected a list")
    return value


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{context}: expected a non-empty string")
    return value.strip()


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DatasetError(f"{context}: expected an integer")
    return value


def _term(value: object, context: str) -> Term:
    if not isinstance(value, str):
        raise DatasetError(f"{context}: expected a term label such as 'Fall 2026'")
    try:
        return Term.parse(value)
    except ValueError as exc:
        raise DatasetError(f"{context}: {exc}") from exc


def _build[ModelT: BaseModel](model: type[ModelT], context: str, **data: Any) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
            for error in exc.errors()
        )
        raise DatasetError(f"{context}: {details}") from exc


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


# --- Policy --------------------------------------------------------------------------

# Only these explicit affirmative sentences authorise in-progress prerequisite credit.
# Keyword presence is deliberately not enough: a negated or conditional sentence can
# contain "in progress", "prerequisite", and "following term" while authorising nothing.
_SUPPORTED_IN_PROGRESS_STATEMENTS = frozenset(
    {
        "a course in progress counts toward the prerequisites of courses in the following term",
        "a course in progress counts towards the prerequisites of courses in the following term",
        "a course in progress counts toward the prerequisites of courses in the next term",
        "a course in progress counts towards the prerequisites of courses in the next term",
    }
)


def _interpret_in_progress_rule(statement: str) -> InProgressPrerequisitePolicy:
    """Turn a supported catalogue sentence into a typed rule, or refuse to guess.

    Any negated, conditional, or otherwise unsupported statement raises ``PolicyError``
    rather than being treated as an affirmative rule.
    """
    normalised = " ".join(statement.lower().split()).rstrip(".")
    if normalised in _SUPPORTED_IN_PROGRESS_STATEMENTS:
        return InProgressPrerequisitePolicy(allowed=True, source_statement=statement)

    raise PolicyError(
        f"unrecognised in-progress prerequisite rule, refusing to guess: {statement!r}"
    )


def _adapt_policy(raw: Mapping[str, Any]) -> AcademicPolicy:
    policies = _mapping(raw.get("policies"), "policies")

    unknown_keys = set(policies) - _KNOWN_POLICY_KEYS
    if unknown_keys:
        raise PolicyError(
            "catalogue declares policy key(s) this build cannot honour: "
            f"{', '.join(sorted(unknown_keys))}. Extend the adapter before relying on them."
        )

    max_units = _integer(policies.get("max_units_per_term"), "policies.max_units_per_term")

    statement = policies.get("in_progress_prerequisites")
    if statement is None:
        # Absent rule means the exception does not apply. Assuming it would grant
        # prerequisite credit that the source never authorised.
        in_progress = InProgressPrerequisitePolicy(allowed=False, source_statement=None)
    else:
        in_progress = _interpret_in_progress_rule(
            _text(statement, "policies.in_progress_prerequisites")
        )

    return _build(
        AcademicPolicy,
        "academic policy",
        current_term=_term(raw.get("current_term"), "current_term"),
        next_term=_term(raw.get("next_term"), "next_term"),
        max_units_per_term=max_units,
        in_progress_prerequisites=in_progress,
    )


# --- Catalogue -----------------------------------------------------------------------


def _adapt_material(
    raw_material: object, context: str, course_id: str, dataset_root: Path
) -> ReadingDocument:
    material = _mapping(raw_material, context)
    title = _text(material.get("title"), f"{context}.title")
    declared = _text(material.get("file"), f"{context}.file")

    relative = Path(declared)
    if relative.is_absolute() or ".." in relative.parts:
        raise DatasetError(
            f"{context}.file: {declared!r} must be a relative path inside the dataset"
        )
    resolved = (dataset_root / relative).resolve()
    if not _is_within(resolved, dataset_root):
        raise DatasetError(f"{context}.file: {declared!r} escapes the dataset root")

    week_value = material.get("week")
    week = None if week_value is None else _integer(week_value, f"{context}.week")

    return _build(
        ReadingDocument,
        context,
        document_id=relative.stem,
        course_id=course_id,
        title=title,
        source_filename=relative.name,
        week=week,
    )


def _adapt_course(
    raw_course: object, index: int, dataset_root: Path
) -> tuple[Course, tuple[ReadingDocument, ...]]:
    course = _mapping(raw_course, f"courses[{index}]")
    code = _text(course.get("course_code"), f"courses[{index}].course_code")
    context = f"courses[{index}] ({code})"

    if "prerequisites" not in course:
        raise DatasetError(
            f"{context}: missing 'prerequisites'; use [] when there are none rather "
            "than omitting the key"
        )
    prerequisites = tuple(
        _text(item, f"{context}.prerequisites[{position}]")
        for position, item in enumerate(
            _sequence(course["prerequisites"], f"{context}.prerequisites")
        )
    )

    terms_raw = _sequence(course.get("terms_offered"), f"{context}.terms_offered")
    try:
        terms = frozenset(coerce_season(str(entry)) for entry in terms_raw)
    except ValueError as exc:
        raise DatasetError(f"{context}.terms_offered: {exc}") from exc
    if not terms:
        raise DatasetError(f"{context}.terms_offered: must list at least one season")

    documents: list[ReadingDocument] = []
    materials = course.get("materials")
    if materials is not None:
        for position, material in enumerate(_sequence(materials, f"{context}.materials")):
            documents.append(
                _adapt_material(
                    material,
                    f"{context}.materials[{position}]",
                    course_id=code,
                    dataset_root=dataset_root,
                )
            )

    description = course.get("description")
    if description is not None and not isinstance(description, str):
        raise DatasetError(f"{context}.description: expected a string or null")

    adapted = _build(
        Course,
        context,
        course_id=code,
        course_code=code,
        title=_text(course.get("title"), f"{context}.title"),
        units=_integer(course.get("units"), f"{context}.units"),
        description=description,
        prerequisite_course_ids=prerequisites,
        terms_offered=terms,
        reading_document_ids=tuple(document.document_id for document in documents),
    )
    return adapted, tuple(documents)


def _adapt_requirement_group(raw_group: object, context: str) -> RequirementGroup:
    group = _mapping(raw_group, context)
    rule_value = _text(group.get("rule"), f"{context}.rule")
    try:
        rule = RuleType(rule_value)
    except ValueError:
        raise DatasetError(
            f"{context}.rule: unsupported rule {rule_value!r}; expected 'all' or 'choose'"
        ) from None

    count_value = group.get("count")
    count = None if count_value is None else _integer(count_value, f"{context}.count")

    members = tuple(
        _text(item, f"{context}.courses[{position}]")
        for position, item in enumerate(_sequence(group.get("courses"), f"{context}.courses"))
    )

    return _build(
        RequirementGroup,
        context,
        group_id=_text(group.get("requirement_id"), f"{context}.requirement_id"),
        label=_text(group.get("name"), f"{context}.name"),
        rule_type=rule,
        required_course_ids=members,
        count=count,
    )


def _adapt_program(raw_program: object, index: int) -> Program:
    program = _mapping(raw_program, f"programs[{index}]")
    program_id = _text(program.get("program_id"), f"programs[{index}].program_id")
    context = f"programs[{index}] ({program_id})"

    raw_groups = program.get("requirement_groups")
    key = "requirement_groups"
    if raw_groups is None:
        raw_groups = program.get("requirements")
        key = "requirements"
    if raw_groups is None:
        raise DatasetError(
            f"{context}: missing requirement_groups (also accepted as 'requirements')"
        )

    groups = tuple(
        _adapt_requirement_group(item, f"{context}.{key}[{position}]")
        for position, item in enumerate(_sequence(raw_groups, f"{context}.{key}"))
    )

    return _build(
        Program,
        context,
        program_id=program_id,
        name=_text(program.get("name"), f"{context}.name"),
        requirement_groups=groups,
    )


def adapt_catalogue(raw: Mapping[str, Any], *, dataset_root: Path) -> AcademicCatalog:
    """Build a validated catalogue aggregate from the supplied source object."""
    if not isinstance(raw, Mapping):
        raise DatasetError("course catalogue: expected a JSON object")

    policy = _adapt_policy(raw)

    courses: list[Course] = []
    documents: list[ReadingDocument] = []
    for index, raw_course in enumerate(_sequence(raw.get("courses"), "courses")):
        course, course_documents = _adapt_course(raw_course, index, dataset_root)
        courses.append(course)
        documents.extend(course_documents)

    programs = tuple(
        _adapt_program(item, index)
        for index, item in enumerate(_sequence(raw.get("programs"), "programs"))
    )

    return AcademicCatalog(
        policy=policy,
        courses=tuple(courses),
        programs=programs,
        reading_documents=tuple(documents),
    )


# --- Students ------------------------------------------------------------------------


def _adapt_records(
    value: object,
    context: str,
    *,
    catalog: AcademicCatalog,
    status: CourseStatus,
) -> tuple[CourseRecord, ...]:
    if value is None:
        raise DatasetError(f"{context}: missing course list")

    records: list[CourseRecord] = []
    for position, entry in enumerate(_sequence(value, context)):
        record_context = f"{context}[{position}]"
        record = _mapping(entry, record_context)
        course_id = _text(record.get("course_code"), f"{record_context}.course_code")
        term = _term(record.get("term"), f"{record_context}.term")

        try:
            catalog.course(course_id)
        except UnknownCourseError as exc:
            raise DatasetError(f"{record_context}: {exc}") from exc

        if status is CourseStatus.COMPLETED and term >= catalog.policy.current_term:
            raise DatasetError(
                f"{record_context}: completed course {course_id} has term {term.label}, "
                f"which is not before the current term {catalog.policy.current_term.label}"
            )
        if status is CourseStatus.IN_PROGRESS and term != catalog.policy.current_term:
            raise DatasetError(
                f"{record_context}: in-progress course {course_id} has term {term.label}, "
                f"which is not the current term {catalog.policy.current_term.label}"
            )

        records.append(
            _build(
                CourseRecord,
                record_context,
                course_id=course_id,
                term=term,
                status=status,
            )
        )
    return tuple(records)


def adapt_students(raw: Mapping[str, Any], *, catalog: AcademicCatalog) -> tuple[Student, ...]:
    """Build validated canonical students from the supplied source object."""
    if not isinstance(raw, Mapping):
        raise DatasetError("student records: expected a JSON object")

    students: list[Student] = []
    seen: set[str] = set()

    for index, item in enumerate(_sequence(raw.get("students"), "students")):
        record = _mapping(item, f"students[{index}]")
        student_id = _text(record.get("student_id"), f"students[{index}].student_id")
        context = f"students[{index}] ({student_id})"

        if student_id in seen:
            raise DatasetError(f"{context}: duplicate student_id")
        seen.add(student_id)

        program_id = _text(record.get("program_id"), f"{context}.program_id")
        catalog.program(program_id)

        completed = _adapt_records(
            record.get("completed_courses"),
            f"{context}.completed_courses",
            catalog=catalog,
            status=CourseStatus.COMPLETED,
        )
        current = _adapt_records(
            record.get("enrolled_courses"),
            f"{context}.enrolled_courses",
            catalog=catalog,
            status=CourseStatus.IN_PROGRESS,
        )

        students.append(
            _build(
                Student,
                context,
                student_id=student_id,
                academic_level=_text(record.get("academic_level"), f"{context}.academic_level"),
                program_id=program_id,
                adviser_id=_text(record.get("adviser_id"), f"{context}.adviser_id"),
                completed_courses=completed,
                current_courses=current,
            )
        )

    return tuple(students)
