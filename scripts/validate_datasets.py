#!/usr/bin/env python3
"""Phase 0 dataset validation for the supplied fixtures.

Discovers the supplied files, validates their structure against the checked-in JSON
Schemas, applies the cross-record rules from AGENTS.md section 5, and prints a
human-readable report.

Missing input files are reported as PENDING rather than crashing, so this script is
usable while the dataset is still arriving. It never substitutes or invents data.

Exit codes
----------
0   No validation errors. PENDING inputs may remain unless ``--require-complete``.
1   One or more validation errors.
2   Inputs are still pending and ``--require-complete`` was passed.

Usage
-----
    uv run python scripts/validate_datasets.py
    uv run python scripts/validate_datasets.py --require-complete
    uv run python scripts/validate_datasets.py --data-root ./data
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import REPO_ROOT, get_settings

Severity = Literal["ok", "warn", "error", "pending"]

# --- Scenario expectations (AGENTS.md sections 2, 5.1, 5.1.1) -------------------------

CATALOGUE_REL = Path("samples/course-catalog.json")
STUDENTS_REL = Path("samples/student-records.json")
CATALOGUE_SCHEMA_REL = Path("schemas/course_catalog.schema.json")
STUDENTS_SCHEMA_REL = Path("schemas/student_records.schema.json")
MANIFEST_REL = Path("manifests/course_readings_manifest.json")

EXPECTED_COURSE_COUNT = 14
EXPECTED_PROGRAM_COUNT = 1
EXPECTED_REQUIREMENT_GROUP_COUNT = 5
EXPECTED_STUDENT_COUNT = 2
EXPECTED_PDF_COUNT = 5
EXPECTED_MAX_UNITS_PER_TERM = 16
EXPECTED_CURRENT_TERM = "Fall 2026"
EXPECTED_NEXT_TERM = "Spring 2027"

# Catalogue-declared reading mappings (AGENTS.md section 5.1.1).
EXPECTED_READING_FILES = {
    "PHYS 230": "phys230-critical-mass.pdf",
    "PHYS 350": "phys350-bohr-model.pdf",
    "ENGL 120": "engl120-the-raven.pdf",
    "HIST 210": "hist210-niels-bohr.pdf",
    "HIST 250": "hist250-demon-core.pdf",
}

KNOWN_ACADEMIC_LEVELS = {"Freshman", "Sophomore", "Junior", "Senior"}
SEASONS = ("Winter", "Spring", "Summer", "Fall")

SYMBOLS: dict[Severity, str] = {
    "ok": "PASS",
    "warn": "WARN",
    "error": "FAIL",
    "pending": "PENDING",
}


# --- Reporting -----------------------------------------------------------------------


@dataclass
class Report:
    """Collects findings and prints a grouped report."""

    findings: list[tuple[Severity, str, str]] = field(default_factory=list)

    def add(self, level: Severity, check: str, detail: str = "") -> None:
        self.findings.append((level, check, detail))

    def count(self, level: Severity) -> int:
        return sum(1 for finding in self.findings if finding[0] == level)

    def render(self, title: str) -> None:
        print(f"\n{title}\n{'=' * len(title)}")
        for level, check, detail in self.findings:
            line = f"  [{SYMBOLS[level]:<7}] {check}"
            if detail:
                line += f" — {detail}"
            print(line)
        print(
            f"\n  {self.count('ok')} passed, {self.count('warn')} warning(s), "
            f"{self.count('error')} error(s), {self.count('pending')} pending"
        )


# --- Small helpers -------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def term_sort_key(term: str) -> tuple[int, int]:
    """Return an orderable key for terms such as 'Fall 2025'. Raises ValueError."""
    season, _, year = term.partition(" ")
    if season not in SEASONS or not year.isdigit():
        raise ValueError(f"unrecognised term: {term!r}")
    return (int(year), SEASONS.index(season) + 1)


def resolve_input_path(declared: str, data_root: Path, base: str = "auto") -> Path:
    """Resolve a declared relative path without leaving the dataset tree.

    ``materials[].file`` is documented as relative to the dataset root, while the
    manifest may legitimately record paths relative to the data root or the
    repository. Existing files win; otherwise the first candidate is returned so the
    caller can report a precise missing path.
    """
    path = Path(declared)
    if path.is_absolute():
        return path.resolve()
    if base == "data_root":
        bases = [data_root]
    elif base == "samples":
        bases = [data_root / "samples", data_root]
    else:
        bases = [data_root / "samples", data_root, REPO_ROOT]
    candidates = [(candidate_base / path).resolve() for candidate_base in bases]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def pdf_page_count(path: Path) -> int | None:
    """Return the page count using PyMuPDF, or None when it is unavailable."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - depends on environment
        return None
    with pymupdf.open(path) as document:
        return int(document.page_count)


def load_json(report: Report, path: Path, label: str) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.add("error", f"{label} parses as JSON", str(exc))
        return None


def validate_schema(report: Report, instance: Any, schema_path: Path, label: str) -> bool:
    import jsonschema

    schema = load_json(report, schema_path, f"{label} schema")
    if schema is None:
        report.add("error", f"{label} schema available", str(schema_path))
        return False
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.absolute_path))
    if not errors:
        report.add("ok", f"{label} matches {schema_path.name}")
        return True
    for error in errors[:15]:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        report.add("error", f"{label} schema violation", f"{location}: {error.message}")
    if len(errors) > 15:
        report.add("error", f"{label} schema violation", f"+{len(errors) - 15} more")
    return False


def normalise_terms(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def season_of(term: str) -> str:
    return term.split(" ", 1)[0]


# --- Catalogue -----------------------------------------------------------------------


def validate_catalogue(
    report: Report, catalogue: Any, data_root: Path
) -> tuple[set[str], set[str]]:
    """Validate the catalogue. Returns (course_codes, program_ids) for referential checks."""
    if not isinstance(catalogue, dict):
        report.add("error", "Catalogue shape", "expected a JSON object")
        return set(), set()

    courses = catalogue.get("courses") or []
    programs = catalogue.get("programs") or []
    policies = catalogue.get("policies") or {}

    # Scenario terms and unit policy
    current_term = catalogue.get("current_term")
    next_term = catalogue.get("next_term")
    report.add(
        "ok" if current_term == EXPECTED_CURRENT_TERM else "error",
        "Catalogue current_term",
        f"{current_term!r} (expected {EXPECTED_CURRENT_TERM!r})",
    )
    report.add(
        "ok" if next_term == EXPECTED_NEXT_TERM else "error",
        "Catalogue next_term",
        f"{next_term!r} (expected {EXPECTED_NEXT_TERM!r})",
    )
    max_units = policies.get("max_units_per_term")
    report.add(
        "ok" if max_units == EXPECTED_MAX_UNITS_PER_TERM else "error",
        "Maximum units per term",
        f"{max_units!r} (expected {EXPECTED_MAX_UNITS_PER_TERM})",
    )

    # Record counts
    report.add(
        "ok" if len(courses) == EXPECTED_COURSE_COUNT else "error",
        "Catalogue course count",
        f"{len(courses)} (expected {EXPECTED_COURSE_COUNT})",
    )
    report.add(
        "ok" if len(programs) == EXPECTED_PROGRAM_COUNT else "error",
        "Programme count",
        f"{len(programs)} (expected {EXPECTED_PROGRAM_COUNT})",
    )

    # Course codes and units
    course_codes: set[str] = set()
    duplicates: set[str] = set()
    for course in courses:
        if not isinstance(course, dict):
            continue
        code = course.get("course_code")
        if not isinstance(code, str):
            continue
        if code in course_codes:
            duplicates.add(code)
        course_codes.add(code)
    report.add(
        "ok" if not duplicates else "error",
        "Course codes unique",
        f"duplicates: {', '.join(sorted(duplicates))}"
        if duplicates
        else f"{len(course_codes)} codes",
    )

    non_four_unit = [
        f"{course.get('course_code')}={course.get('units')}"
        for course in courses
        if isinstance(course, dict) and course.get("units") != 4
    ]
    report.add(
        "ok" if not non_four_unit else "warn",
        "All catalogue courses are 4 units",
        ", ".join(non_four_unit) if non_four_unit else "14 x 4 units",
    )

    # Prerequisites
    unresolved: list[str] = []
    self_referential: list[str] = []
    for course in courses:
        if not isinstance(course, dict):
            continue
        code = course.get("course_code")
        prerequisites = course.get("prerequisites")
        if not isinstance(prerequisites, list):
            report.add("error", "Prerequisites field present", f"{code}: missing or not a list")
            continue
        for prerequisite in prerequisites:
            if prerequisite == code:
                self_referential.append(str(code))
            if prerequisite not in course_codes:
                unresolved.append(f"{code} -> {prerequisite}")
    report.add(
        "ok" if not unresolved else "error",
        "Prerequisite references resolve",
        ", ".join(unresolved) if unresolved else "all resolve",
    )
    if self_referential:
        report.add("error", "Self-referential prerequisites", ", ".join(self_referential))

    # Terms offered
    year_qualified: list[str] = []
    missing_season: list[str] = []
    for course in courses:
        if not isinstance(course, dict):
            continue
        offerings = normalise_terms(course.get("terms_offered"))
        if not offerings:
            missing_season.append(str(course.get("course_code")))
            continue
        for offering in offerings:
            if season_of(offering) not in SEASONS:
                missing_season.append(f"{course.get('course_code')}:{offering}")
            if " " in offering:
                year_qualified.append(f"{course.get('course_code')}:{offering}")
    report.add(
        "ok" if not missing_season else "error",
        "Term offerings use recognised seasons",
        ", ".join(missing_season) if missing_season else "Fall/Spring only",
    )
    if year_qualified:
        detail = (
            f"{', '.join(year_qualified)} — eligibility matches on season; "
            "confirm the adapter strips the year"
        )
        report.add("warn", "Term offerings carry a year", detail)

    # Programmes and requirement groups
    program_ids: set[str] = set()
    group_ids: set[str] = set()
    group_count = 0
    for program in programs:
        if not isinstance(program, dict):
            continue
        program_id = program.get("program_id")
        if isinstance(program_id, str):
            program_ids.add(program_id)
        groups = program.get("requirement_groups")
        if groups is None:
            groups = program.get("requirements")
        if not isinstance(groups, list):
            report.add("error", "Requirement groups present", f"{program_id}: missing array")
            continue
        group_count += len(groups)
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_id = str(group.get("requirement_id"))
            if group_id in group_ids:
                report.add("error", "Requirement IDs unique", f"duplicate {group_id}")
            group_ids.add(group_id)

            rule = group.get("rule")
            members = [str(code) for code in group.get("courses") or []]
            if rule not in {"all", "choose"}:
                report.add("error", "Requirement rule supported", f"{group_id}: {rule!r}")
            unresolved_members = [code for code in members if code not in course_codes]
            if unresolved_members:
                report.add(
                    "error",
                    "Requirement course references resolve",
                    f"{group_id}: {', '.join(unresolved_members)}",
                )
            if rule == "choose":
                count = group.get("count")
                if not isinstance(count, int) or not 1 <= count <= len(members):
                    report.add(
                        "error",
                        "Choose-rule count within bounds",
                        f"{group_id}: count={count!r}, options={len(members)}",
                    )
            if len(set(members)) != len(members):
                report.add("warn", "No duplicate courses in a requirement group", group_id)

    report.add(
        "ok" if group_count == EXPECTED_REQUIREMENT_GROUP_COUNT else "error",
        "Requirement group count",
        f"{group_count} (expected {EXPECTED_REQUIREMENT_GROUP_COUNT})",
    )

    # Reading mappings
    materials: list[tuple[str, dict[str, Any]]] = []
    for course in courses:
        if not isinstance(course, dict):
            continue
        for material in course.get("materials") or []:
            if isinstance(material, dict):
                materials.append((str(course.get("course_code")), material))

    report.add(
        "ok" if len(materials) == EXPECTED_PDF_COUNT else "error",
        "Reading mappings",
        f"{len(materials)} (expected {EXPECTED_PDF_COUNT})",
    )

    for code, material in materials:
        raw_file = material.get("file")
        if not isinstance(raw_file, str):
            report.add("error", "Material path present", f"{code}: {raw_file!r}")
            continue
        expected_name = EXPECTED_READING_FILES.get(code)
        if expected_name and Path(raw_file).name != expected_name:
            report.add(
                "warn",
                "Material filename matches the manifest",
                f"{code}: {Path(raw_file).name} (expected {expected_name})",
            )
        material_path = resolve_input_path(raw_file, data_root)
        if not is_within(material_path, data_root):
            report.add("error", "Material path contained in data root", f"{code}: {raw_file}")
            continue
        if material_path.is_file():
            report.add("ok", "Reading file present", f"{code}: {raw_file}")
        else:
            report.add("pending", "Reading file pending", f"{code}: {raw_file}")

    return course_codes, program_ids


# --- Students ------------------------------------------------------------------------


def validate_students(
    report: Report,
    records: Any,
    course_codes: set[str],
    program_ids: set[str],
    current_term: str,
) -> None:
    if not isinstance(records, dict):
        report.add("error", "Student record shape", "expected a JSON object")
        return

    students = records.get("students") or []
    report.add(
        "ok" if len(students) == EXPECTED_STUDENT_COUNT else "error",
        "Student count",
        f"{len(students)} (expected {EXPECTED_STUDENT_COUNT})",
    )

    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    issues: list[str] = []

    for student in students:
        if not isinstance(student, dict):
            continue
        student_id = str(student.get("student_id"))
        if student_id in seen_ids:
            duplicate_ids.append(student_id)
        seen_ids.add(student_id)

        program_id = student.get("program_id")
        if program_ids and program_id not in program_ids:
            issues.append(f"{student_id}: unknown programme {program_id!r}")

        level = student.get("academic_level")
        if level not in KNOWN_ACADEMIC_LEVELS:
            report.add(
                "warn",
                "Academic level recognised",
                f"{student_id}: {level!r} is descriptive data; confirm it is intentional",
            )

        completed = student.get("completed_courses") or []
        enrolled = student.get("enrolled_courses") or []

        completed_codes: list[str] = []
        for entry in completed:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("course_code"))
            completed_codes.append(code)
            term = str(entry.get("term"))
            if course_codes and code not in course_codes:
                issues.append(f"{student_id}: completed {code} not in catalogue")
            try:
                if term_sort_key(term) >= term_sort_key(current_term):
                    issues.append(
                        f"{student_id}: completed {code} term {term} is not before {current_term}"
                    )
            except ValueError:
                issues.append(f"{student_id}: completed {code} has unparseable term {term!r}")

        enrolled_codes: list[str] = []
        for entry in enrolled:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("course_code"))
            enrolled_codes.append(code)
            term = str(entry.get("term"))
            if course_codes and code not in course_codes:
                issues.append(f"{student_id}: enrolled {code} not in catalogue")
            if term != current_term:
                issues.append(f"{student_id}: enrolled {code} term {term} != {current_term}")

        if len(set(completed_codes)) != len(completed_codes):
            issues.append(f"{student_id}: duplicate completed course records")
        if len(set(enrolled_codes)) != len(enrolled_codes):
            issues.append(f"{student_id}: duplicate enrolled course records")
        overlap = set(completed_codes) & set(enrolled_codes)
        if overlap:
            issues.append(
                f"{student_id}: course(s) both completed and enrolled: {', '.join(sorted(overlap))}"
            )

    report.add(
        "ok" if not duplicate_ids else "error",
        "Student IDs unique",
        ", ".join(duplicate_ids) if duplicate_ids else f"{len(seen_ids)} records",
    )
    report.add(
        "ok" if not issues else "error",
        "Student record referential integrity",
        "; ".join(issues) if issues else "programme, course, term and status checks pass",
    )


# --- Manifest and PDF preflight -------------------------------------------------------


def validate_manifest(report: Report, manifest: Any, data_root: Path) -> None:
    if not isinstance(manifest, dict):
        report.add("error", "Manifest shape", "expected a JSON object")
        return

    documents = manifest.get("documents") or []
    report.add(
        "ok" if len(documents) == EXPECTED_PDF_COUNT else "error",
        "Manifest document count",
        f"{len(documents)} (expected {EXPECTED_PDF_COUNT})",
    )
    report.add(
        "ok" if manifest.get("documents_expected") == EXPECTED_PDF_COUNT else "warn",
        "Manifest documents_expected",
        repr(manifest.get("documents_expected")),
    )

    present = 0
    for document in documents:
        if not isinstance(document, dict):
            continue
        code = str(document.get("course_code"))
        relative = document.get("relative_path")
        status = document.get("status")
        if not isinstance(relative, str):
            report.add("error", "Manifest path present", f"{code}: {relative!r}")
            continue

        declared_base = manifest.get("path_base")
        base = declared_base if declared_base in {"data_root", "samples"} else "auto"
        path = resolve_input_path(relative, data_root, base=str(base))
        if not is_within(path, data_root):
            report.add("error", "Manifest path contained in data root", f"{code}: {relative}")
            continue

        exists = path.is_file()
        present += int(exists)

        if exists and status == "pending":
            report.add("warn", "Manifest status stale", f"{code}: file present but marked pending")
        if not exists and status == "present":
            report.add(
                "error", "Manifest status stale", f"{code}: marked present but file is missing"
            )

        if not exists:
            report.add("pending", "Reading file pending", f"{code}: {relative}")
            continue

        expected_checksum = document.get("sha256") or document.get("expected_sha256")
        if isinstance(expected_checksum, str):
            actual = sha256_of(path)
            report.add(
                "ok" if actual == expected_checksum else "error",
                "Reading checksum matches manifest",
                f"{code}: {actual[:12]}…",
            )

        expected_pages = document.get("page_count") or document.get("expected_page_count")
        actual_pages = pdf_page_count(path)
        if actual_pages is None:
            report.add("warn", "Page count verified", f"{code}: PyMuPDF unavailable")
        elif isinstance(expected_pages, int):
            report.add(
                "ok" if actual_pages == expected_pages else "error",
                "Page count matches manifest",
                f"{code}: {actual_pages} (expected {expected_pages})",
            )

        expected_name = EXPECTED_READING_FILES.get(code)
        if expected_name and Path(relative).name != expected_name:
            report.add(
                "warn", "Manifest filename matches catalogue", f"{code}: {Path(relative).name}"
            )

    report.add(
        "ok" if present == EXPECTED_PDF_COUNT else "pending",
        "Reading corpus complete",
        f"{present} of {EXPECTED_PDF_COUNT} PDFs present",
    )


# --- Entry point ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the supplied MVP datasets.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override DATA_ROOT (defaults to the application setting).",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Treat pending input files as errors (use in CI once all data is supplied).",
    )
    args = parser.parse_args(argv)

    data_root = (args.data_root or get_settings().data_root).resolve()
    report = Report()

    print(f"Dataset root: {data_root}")
    print(f"Repository:   {REPO_ROOT}")

    report.add(
        "ok" if data_root.is_dir() else "error",
        "Dataset root exists",
        str(data_root),
    )

    # Inputs
    catalogue_path = data_root / CATALOGUE_REL
    students_path = data_root / STUDENTS_REL
    manifest_path = data_root / MANIFEST_REL

    catalogue = (
        load_json(report, catalogue_path, "Course catalogue") if catalogue_path.is_file() else None
    )
    students = (
        load_json(report, students_path, "Student records") if students_path.is_file() else None
    )
    manifest = (
        load_json(report, manifest_path, "Reading manifest") if manifest_path.is_file() else None
    )

    for label, path, instance in (
        ("Course catalogue", catalogue_path, catalogue),
        ("Student records", students_path, students),
        ("Reading manifest", manifest_path, manifest),
    ):
        if instance is None:
            report.add("pending", f"{label} supplied", str(path))
        elif path.is_file():
            report.add("ok", f"{label} present", path.name)

    course_codes: set[str] = set()
    program_ids: set[str] = set()

    if catalogue is not None:
        validate_schema(report, catalogue, data_root / CATALOGUE_SCHEMA_REL, "Course catalogue")
        course_codes, program_ids = validate_catalogue(report, catalogue, data_root)

    if students is not None:
        validate_schema(report, students, data_root / STUDENTS_SCHEMA_REL, "Student records")
        current_term = EXPECTED_CURRENT_TERM
        if isinstance(catalogue, dict) and isinstance(catalogue.get("current_term"), str):
            current_term = catalogue["current_term"]
        validate_students(report, students, course_codes, program_ids, current_term)

    if manifest is not None:
        validate_manifest(report, manifest, data_root)

    report.render("Phase 0 dataset validation")

    if report.count("error"):
        print("\nResult: FAILED — resolve the errors above.")
        return 1
    if args.require_complete and report.count("pending"):
        print("\nResult: INCOMPLETE — pending input files remain.")
        return 2
    if report.count("pending"):
        print("\nResult: PARTIAL — dataset validates, but input files are still pending.")
        return 0
    print("\nResult: PASS — all expected inputs are present and valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
