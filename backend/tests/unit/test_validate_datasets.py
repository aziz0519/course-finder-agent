"""Behaviour of the Phase 0 dataset validator's pure helpers and exit codes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

import validate_datasets as validator


def test_terms_order_within_and_across_years() -> None:
    assert validator.term_sort_key("Fall 2025") < validator.term_sort_key("Fall 2026")
    assert validator.term_sort_key("Spring 2026") < validator.term_sort_key("Fall 2026")
    assert validator.term_sort_key("Fall 2025") < validator.term_sort_key("Spring 2026")


def test_unparseable_term_is_rejected() -> None:
    with pytest.raises(ValueError, match="unrecognised term"):
        validator.term_sort_key("Autumn 2026")


def test_path_containment_rejects_siblings(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    assert validator.is_within(data_root / "samples" / "x.json", data_root)
    assert not validator.is_within(tmp_path / "elsewhere" / "x.json", data_root)
    assert not validator.is_within(data_root / ".." / "escaped.json", data_root)


def test_traversal_declaration_resolves_outside_the_root(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "samples").mkdir(parents=True)

    resolved = validator.resolve_input_path("../../../etc/passwd", data_root)

    assert not validator.is_within(resolved, data_root)


def test_existing_declaration_wins_over_its_sibling_root(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "samples" / "course-materials").mkdir(parents=True)
    target = data_root / "samples" / "course-materials" / "reading.pdf"
    target.write_bytes(b"%PDF-1.7 placeholder")

    assert (
        validator.resolve_input_path("course-materials/reading.pdf", data_root) == target.resolve()
    )


def test_schemas_fall_back_to_the_repository_copy(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    resolved = validator.resolve_schema_path(validator.CATALOGUE_SCHEMA_NAME, data_root)

    assert resolved.is_file()
    assert resolved.parent == validator.REPO_ROOT / "data" / "schemas"


def test_dataset_local_schema_overrides_the_repository_copy(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "schemas").mkdir(parents=True)
    local = data_root / "schemas" / validator.CATALOGUE_SCHEMA_NAME
    local.write_text("{}", encoding="utf-8")

    assert validator.resolve_schema_path(validator.CATALOGUE_SCHEMA_NAME, data_root) == local


def test_missing_inputs_report_partial_and_do_not_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    assert validator.main(["--data-root", str(data_root)]) == 0
    output = capsys.readouterr().out
    assert "PARTIAL" in output
    assert "PENDING" in output


def test_require_complete_turns_pending_inputs_into_exit_code_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    assert validator.main(["--data-root", str(data_root), "--require-complete"]) == 2
    assert "INCOMPLETE" in capsys.readouterr().out


def _supplied_fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = validator.REPO_ROOT / "data"

    def load(relative: str) -> dict[str, Any]:
        return json.loads((root / relative).read_text(encoding="utf-8"))

    return (
        load("samples/test-conversations.json"),
        load("samples/course-catalog.json"),
        load("samples/student-records.json"),
    )


def test_conversation_validator_rejects_an_unverified_diagram_value() -> None:
    suite, catalogue, students = _supplied_fixtures()
    tampered = deepcopy(suite)
    tutor = next(item for item in tampered["conversations"] if item["kind"] == "tutor")
    tutor["turns"][1]["expected_answer_value"] = 8
    tutor["turns"][1]["value_verification_status"] = "pending_diagram_inspection"

    report = validator.Report()
    validator.validate_conversations(report, tampered, catalogue, students)

    assert any(
        level == "error" and check == "Tutor value not asserted before verification"
        for level, check, _ in report.findings
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("turns", 1), ("expected_recommended_courses", [["unhashable"]])],
)
def test_schema_invalid_conversations_report_failure_without_semantic_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    suite, catalogue, students = _supplied_fixtures()
    planner = next(c for c in suite["conversations"] if c["kind"] == "planner")
    if field == "turns":
        planner[field] = value
    else:
        planner["turns"][0][field] = value
    samples = tmp_path / "samples"
    samples.mkdir()
    for filename, payload in (
        ("course-catalog.json", catalogue),
        ("student-records.json", students),
        ("test-conversations.json", suite),
    ):
        (samples / filename).write_text(json.dumps(payload), encoding="utf-8")

    def unexpected_semantic_validation(*args, **kwargs):
        pytest.fail("schema-invalid suite reached semantic validation")

    monkeypatch.setattr(validator, "validate_conversations", unexpected_semantic_validation)
    assert validator.main(["--data-root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "Conversation suite schema violation" in output and "Result: FAILED" in output
