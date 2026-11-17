from __future__ import annotations

import hashlib
import importlib
from types import SimpleNamespace

import pytest

baseline = importlib.import_module("scripts.run_baseline")


@pytest.mark.parametrize("value,correct", [(8, True), (18, False), (80, False)])
def test_capacity_compares_the_stated_value(value, correct):
    assert (
        baseline._electron_capacity_matches(
            f"Figure 2 on page 4: up to {value} electrons (reference 8).", 8
        )
        is correct
    )


def test_report_hashes_capture_evaluated_inputs(tmp_path, monkeypatch):
    fixture_bytes = baseline.FIXTURE_PATH.read_bytes()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_bytes(fixture_bytes)
    for name in baseline.PDF_NAMES:
        (tmp_path / name).touch()
    monkeypatch.setattr(baseline, "FIXTURE_PATH", fixture_path)
    monkeypatch.setattr(baseline, "PDF_DIR", tmp_path)
    checksums = {name: f"ingested-{name}" for name in baseline.PDF_NAMES}

    class Service:
        def create(self, *args):
            return SimpleNamespace(thread_id="thread")

        def handle_message(self, thread, owner, scope, message):
            fixture_path.write_bytes(b"changed after validation")
            for name in baseline.PDF_NAMES:
                (tmp_path / name).write_bytes(b"changed after ingestion")
            if scope.principal_id == "another-principal":
                raise PermissionError
            return SimpleNamespace(
                status="unsupported",
                citations=[],
                text="provided data does not support",
                planning=None,
            )

    class Retriever:
        def __init__(self, repository):
            pass

        def search(self, *args):
            raise PermissionError

    monkeypatch.setattr(baseline, "_build_service", lambda *args: (Service(), None, checksums))
    monkeypatch.setattr(baseline, "LocalRetriever", Retriever)
    report = baseline.run()
    assert report["fixture_sha256"] == hashlib.sha256(fixture_bytes).hexdigest()
    assert report["pdf_sha256"] == checksums


def test_build_service_retains_ingestion_checksums(tmp_path, monkeypatch):
    dataset = baseline.load_dataset(baseline.DATA_ROOT)
    monkeypatch.setattr(baseline, "PDF_DIR", tmp_path)
    expected = {}
    for document in dataset.catalog.reading_documents:
        (tmp_path / document.source_filename).touch()
        expected[document.source_filename] = document.file_checksum

    def ingest(document, *args):
        (tmp_path / document.source_filename).write_bytes(b"changed")
        return SimpleNamespace(source_checksum=document.file_checksum)

    monkeypatch.setattr(baseline, "ingest_reading", ingest)
    _, _, checksums = baseline._build_service(tmp_path / "service", dataset)
    assert checksums == expected
