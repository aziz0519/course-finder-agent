"""Run the reproducible, offline M7 quality baseline.

Uses the canonical conversation fixture, the checked-in reading QA manifest,
the local PDF parser/retriever, and the deterministic answer composer. It makes
no model or AWS calls. Metrics are report-only; this command fails only when the
baseline cannot be run or its input fixtures are invalid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ingestion.dataset import AcademicDataset, load_dataset  # noqa: E402
from app.ingestion.readings import ingest_reading, load_reviews  # noqa: E402
from app.repositories.conversations import ConversationRepository  # noqa: E402
from app.repositories.readings import ReadingRepository  # noqa: E402
from app.retrieval.readings import LocalRetriever, ReadingScope  # noqa: E402
from app.services.conversations import ConversationService  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"
FIXTURE_PATH = DATA_ROOT / "samples" / "test-conversations.json"
PDF_DIR = DATA_ROOT / "samples" / "course-materials"
MANIFEST_DIR = DATA_ROOT / "manifests"
REPORT_PATH = REPO_ROOT / "docs" / "M7_QUALITY_BASELINE.md"

PDF_NAMES = (
    "phys230-critical-mass.pdf",
    "phys350-bohr-model.pdf",
    "engl120-the-raven.pdf",
    "hist210-niels-bohr.pdf",
    "hist250-demon-core.pdf",
)


def _electron_capacity_matches(text: str, expected_value: int) -> bool:
    capacities = re.findall(r"\bup to\s+(\d+)\s+electrons\b", text, flags=re.IGNORECASE)
    return bool(capacities) and all(int(value) == expected_value for value in capacities)


def _scope(dataset: AcademicDataset, student_id: str, principal_id: str) -> ReadingScope:
    student = dataset.student(student_id)
    documents = frozenset(
        document.document_id
        for document in dataset.catalog.reading_documents
        if document.course_id in student.current_course_ids
    )
    return ReadingScope(
        principal_id=principal_id,
        course_ids=frozenset(student.current_course_ids),
        document_ids=documents,
    )


def _build_service(
    root: Path, dataset: AcademicDataset
) -> tuple[ConversationService, ReadingRepository, dict[str, str]]:
    repository = ReadingRepository(root / "readings")
    pdf_checksums: dict[str, str] = {}
    reviews = load_reviews(MANIFEST_DIR / "reading_qa.json")
    for document in dataset.catalog.reading_documents:
        source = PDF_DIR / document.source_filename
        if not source.is_file():
            raise FileNotFoundError(f"required baseline PDF is missing: {source}")
        review = reviews.documents.get(document.document_id)
        if review is None:
            raise ValueError(f"QA review is missing for {document.document_id}")
        report = ingest_reading(document, PDF_DIR, repository, review)
        pdf_checksums[document.source_filename] = report.source_checksum

    service = ConversationService(
        ConversationRepository(root / "conversations.sqlite3"),
        lambda: dataset,
        LocalRetriever(repository),
    )
    return service, repository, pdf_checksums


def _metric(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
    }


def _validate_fixture(fixture_bytes: bytes | None = None) -> dict[str, Any]:
    import jsonschema

    fixture = json.loads(FIXTURE_PATH.read_bytes() if fixture_bytes is None else fixture_bytes)
    schema = json.loads(
        (DATA_ROOT / "schemas" / "test_conversations.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(fixture, schema)
    return fixture


def run() -> dict[str, Any]:
    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture = _validate_fixture(fixture_bytes)
    dataset = load_dataset(DATA_ROOT)
    missing = [name for name in PDF_NAMES if not (PDF_DIR / name).is_file()]
    if missing:
        raise FileNotFoundError(f"required baseline PDFs are missing: {', '.join(missing)}")

    material_tutor_turns = 0
    grounded_turns = 0
    citation_total = 0
    citation_correct = 0
    abstention_cases = 0
    abstention_correct = 0
    followup_cases = 0
    followup_correct = 0
    planning_cases = 0
    planning_correct = 0
    access_cases = 0
    access_correct = 0
    turn_results: list[dict[str, Any]] = []
    planning_results: list[dict[str, Any]] = []
    citation_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="m7-baseline-") as temporary:
        service, readings, pdf_checksums = _build_service(Path(temporary), dataset)

        # Replay the canonical tutor dialogue in one persistent conversation.
        tutor_fixture = next(x for x in fixture["conversations"] if x["kind"] == "tutor")
        student_id = fixture["student_id"]
        owner_id = "baseline-student-001"
        thread = service.create(owner_id, student_id)
        scope = _scope(dataset, student_id, owner_id)
        for turn in tutor_fixture["turns"]:
            response = service.handle_message(thread.thread_id, owner_id, scope, turn["user"])
            has_grounding = bool(response.citations)
            if response.status == "ok":
                material_tutor_turns += 1
                grounded_turns += int(has_grounding)
            for citation in response.citations:
                citation_total += 1
                citation_record: dict[str, Any] = {
                    "document_id": citation.document_id,
                    "title": citation.document_title,
                    "page": citation.pdf_page_number,
                    "label": citation.label,
                    "resolved": False,
                }
                try:
                    retriever = LocalRetriever(readings)
                    if citation.asset_id:
                        resolved = retriever.resolve_visual(
                            scope,
                            citation.course_code,
                            citation.document_id,
                            asset_id=citation.asset_id,
                            exact=True,
                        )
                        asset_evidence = resolved.evidence
                        if resolved.status != "ok" or asset_evidence is None:
                            citation_results.append(citation_record)
                            continue
                        resolved_title = asset_evidence.document_title
                        resolved_page = asset_evidence.asset.pdf_page_number
                    else:
                        evidence = retriever.resolve_citation(
                            scope,
                            citation.course_code,
                            citation.chunk_id or "",
                        )
                        resolved_title = evidence.document_title
                        resolved_page = evidence.page_number
                except (LookupError, ValueError, PermissionError):
                    citation_results.append(citation_record)
                    continue
                citation_record["resolved"] = (
                    resolved_title == citation.document_title
                    and resolved_page == citation.pdf_page_number
                )
                citation_correct += int(citation_record["resolved"])
                citation_results.append(citation_record)
            expected_value = turn.get("expected_answer_value")
            if turn["turn"] > 1 and (
                expected_value is not None
                or turn.get("value_verification_status") == "not_applicable"
            ):
                followup_cases += 1
                if expected_value is None:
                    is_correct = response.status == "clarification_required"
                    followup_correct += int(is_correct)
                    abstention_cases += 1
                    abstention_correct += int(is_correct and not response.citations)
                else:
                    is_correct = (
                        response.status == "ok"
                        and _electron_capacity_matches(response.text, expected_value)
                        and any(
                            citation.pdf_page_number == 4 and citation.label == "Figure 2"
                            for citation in response.citations
                        )
                    )
                    followup_correct += int(is_correct)
            turn_results.append(
                {
                    "id": f"tutor-{turn['turn']}",
                    "status": response.status,
                    "citation_count": len(response.citations),
                    "grounded": response.status == "ok" and has_grounding,
                }
            )

        # Unknown facts and unreadable visual/formula requests must abstain.
        unsupported = service.handle_message(
            thread.thread_id,
            owner_id,
            scope,
            "Are there seats available for Spring 2027 courses?",
        )
        abstention_cases += 1
        abstention_correct += int(
            unsupported.status == "unsupported"
            and not unsupported.citations
            and "provided data does not support" in unsupported.text
        )

        # Replay planner caps in a single thread and compare with the golden fixture.
        planner_fixture = next(x for x in fixture["conversations"] if x["kind"] == "planner")
        planner_owner = "baseline-planner-001"
        planner_thread = service.create(planner_owner, student_id)
        planner_scope = _scope(dataset, student_id, planner_owner)
        for turn in planner_fixture["turns"]:
            response = service.handle_message(
                planner_thread.thread_id, planner_owner, planner_scope, turn["user"]
            )
            proposal = response.planning
            planning_cases += 1
            correct = bool(
                proposal
                and response.status == "ok"
                and proposal.total_units == turn["expected_total_units"]
                and sorted(c.course_id for c in proposal.recommended)
                == sorted(turn["expected_recommended_courses"])
                and {c.course_id for c in proposal.deferred}
                == set(turn["expected_deferred_courses"])
                and {c.course_id for c in proposal.alternatives}
                == set(turn["expected_alternative_courses"])
                and proposal.catalogue_max_units == turn["expected_catalogue_max_units"]
                and proposal.effective_unit_cap
                == min(turn["request_unit_cap"], proposal.catalogue_max_units)
            )
            planning_correct += int(correct)
            planning_results.append(
                {
                    "turn": turn["turn"],
                    "status": response.status,
                    "units": proposal.total_units if proposal else None,
                    "correct": correct,
                }
            )

        # Deny scope broadening and course access at the service/retriever boundary.
        access_cases += 2
        try:
            service.handle_message(
                thread.thread_id,
                owner_id,
                scope.model_copy(update={"principal_id": "another-principal"}),
                "Explain the Bohr model",
            )
        except PermissionError:
            access_correct += 1
        try:
            LocalRetriever(readings).search(scope, "PHYS 230", "critical mass")
        except PermissionError:
            access_correct += 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "pdf_sha256": pdf_checksums,
        "composer": "OfflineAnswerComposer",
        "external_calls": 0,
        "metrics": {
            "grounded_answer_rate": _metric(grounded_turns, material_tutor_turns),
            "citation_correctness": _metric(citation_correct, citation_total),
            "abstention_quality": _metric(abstention_correct, abstention_cases),
            "planning_correctness": _metric(planning_correct, planning_cases),
            "followup_resolution": _metric(followup_correct, followup_cases),
            "access_control_pass_rate": _metric(access_correct, access_cases),
        },
        "details": {
            "tutor": turn_results,
            "planner": planning_results,
            "citations": citation_results,
        },
        "visual_qa_limitations": {
            "approved_assets": 4,
            "total_assets": 50,
            "visual_qa_complete_documents": 0,
            "quarantined_documents": ["phys230-critical-mass", "hist250-demon-core"],
        },
    }


def render(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# M7 Quality Baseline",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "Offline deterministic baseline using the supplied conversation fixture,",
        "local parser/retriever, and `OfflineAnswerComposer`. No model or AWS calls.",
        "Metric values are report-only, not CI thresholds.",
        "",
        f"- Conversation fixture SHA-256: `{report['fixture_sha256']}`",
        "- PDF corpus: all five files present; SHA-256 values are in the "
        "machine-readable run output.",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    labels = {
        "grounded_answer_rate": "Grounded answer rate",
        "citation_correctness": "Citation correctness (round-trip)",
        "abstention_quality": "Abstention quality",
        "planning_correctness": "Planning correctness",
        "followup_resolution": "Follow-up resolution",
        "access_control_pass_rate": "Access-control pass rate",
    }
    for key, label in labels.items():
        result = metrics[key]
        rate = "N/A" if result["rate"] is None else f"{result['rate']:.1%}"
        lines.append(f"| {label} | {result['numerator']}/{result['denominator']} ({rate}) |")
    lines.extend(
        [
            "",
            "## Interpretation and limitations",
            "",
            "- Grounding counts successful tutor turns with a citation; this small regression "
            "set is not a statistically representative accuracy estimate.",
            "- Citation correctness resolves each citation against the active local reading "
            "version and checks title and 1-based PDF page.",
            "- Planning and follow-up scores are checked against the canonical conversation "
            "fixture.",
            "- Access control covers principal-scope and course-scope denial; HTTP "
            "role/assignment checks are covered by acceptance tests.",
            "- Only 4/50 visual assets are approved; all five documents have incomplete "
            "full-resolution visual QA. PHYS 230 and HIST 250 remain quarantined. "
            "Unreviewed visual/formula evidence must continue to abstain.",
            "- This is an offline-composer baseline, not a live model-quality result.",
            "",
            "Regenerate with `uv run python scripts/run_baseline.py`. CI verifies the "
            "evaluator runs, but does not fail on metric values.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-missing-readings",
        action="store_true",
        help="report a pending corpus baseline instead of failing on a clean checkout",
    )
    args = parser.parse_args()
    _validate_fixture()
    missing = [name for name in PDF_NAMES if not (PDF_DIR / name).is_file()]
    if missing and args.allow_missing_readings:
        print("PENDING: baseline requires approved PDFs; missing: " + ", ".join(missing))
        return 0
    if missing:
        print(
            "ERROR: baseline requires approved PDFs; missing: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    report = run()
    REPORT_PATH.write_text(render(report), encoding="utf-8")
    json_path = REPORT_PATH.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Baseline report: {REPORT_PATH}")
    for name, value in report["metrics"].items():
        rate = "N/A" if value["rate"] is None else f"{value['rate']:.1%}"
        print(f"{name}: {value['numerator']}/{value['denominator']} ({rate})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
