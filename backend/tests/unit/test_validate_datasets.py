"""Behaviour of the Phase 0 dataset validator's pure helpers and exit codes."""

from __future__ import annotations

from pathlib import Path

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
