"""Admin/operator CLI for the local M2 corpus. No HTTP endpoint or student upload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from app.ingestion.dataset import load_dataset
from app.ingestion.readings import ingest_reading, load_reviews
from app.repositories.readings import ReadingRepository


def main(argv: list[str] | None = None) -> int:
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("--data-root", type=Path, default=get_settings().data_root)
    args_parser.add_argument("--output", type=Path)
    args_parser.add_argument("--reviews", type=Path)
    args_parser.add_argument("--course", help="Only ingest this catalogue course code")
    args = args_parser.parse_args(argv)
    dataset = load_dataset(args.data_root)
    repository = ReadingRepository(args.output or args.data_root / "processed" / "readings")
    review_path = args.reviews or args.data_root / "manifests" / "reading_qa.json"
    reviews = load_reviews(review_path) if review_path.exists() else None
    documents = [
        d
        for d in dataset.catalog.reading_documents
        if not args.course or d.course_id == args.course
    ]
    if not documents:
        args_parser.error("no catalogue readings match the requested course")
    failed = False
    for document in documents:
        try:
            report = ingest_reading(
                document,
                args.data_root / "samples" / "course-materials",
                repository,
                reviews.documents.get(document.document_id) if reviews else None,
            )
            print(
                json.dumps(
                    {
                        "course": document.course_id,
                        "version": report.ingestion_version,
                        "pages": report.page_count,
                        "chunks": report.chunk_count,
                        "assets": report.asset_count,
                        "text_activatable": report.text_activatable,
                        "visual_qa_complete": report.visual_qa_complete,
                        "warnings": len(report.warnings),
                        "errors": report.errors,
                    }
                )
            )
            failed |= bool(report.errors)
        except (OSError, ValueError, RuntimeError) as exc:
            # Never print source text, student records, or provider prompts.
            print(json.dumps({"course": document.course_id, "error_type": type(exc).__name__}))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
