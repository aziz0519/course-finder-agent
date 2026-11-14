# M2 ingestion baseline

Recorded 2026-11-14 using the supplied corpus and
`data/manifests/reading_qa.json`. This is an **agent preflight and gated extraction
baseline**, not a complete human visual audit or a tutor-answer accuracy evaluation.

## Observed run

`uv run python scripts/ingest_datasets.py` ingested all five authoritative files.
Every source SHA-256 and page count matched
`data/manifests/course_readings_manifest.json`. All **64 pages** have a native text
layer, page render, layout record, status, page number and quality flags. No blanket
OCR, model inference, guessed formulas, or network-based academic facts were used.

| Course / reading | Pages | Chunks | Cropped placements | Approved assets | Restricted chunks | Structural errors |
|---|---:|---:|---:|---:|---:|---:|
| PHYS 230 / Critical mass | 11 | 106 | 8 | 0 | 106 | 0 |
| PHYS 350 / Bohr model | 12 | 69 | 9 | 2 | 0 | 0 |
| ENGL 120 / The Raven | 15 | 120 | 10 | 2 | 0 | 0 |
| HIST 210 / Niels Bohr | 17 | 117 | 13 | 0 | 49 | 0 |
| HIST 250 / Demon core | 9 | 64 | 10 | 0 | 64 | 0 |
| **Total** | **64** | **476** | **50** | **4** | **219** | **0** |

Counts are normalized placement records, **not embedded-image-object counts**.
Conservative full-page equation regions can combine several displayed formulas.
Chunks include unreviewed table row groups, which are retained for QA but excluded
from ordinary text retrieval. A document can have reviewed text active while all
its visual assets remain blocked.

All documents preserve source attribution and CC-BY-SA metadata. The final-page
attribution of the reference PDF is retained verbatim in the immutable artifacts.
Parser versions/options, processing time, page-level exceptions, source metadata,
and OCR/VLM identifiers (`null` for this run) live in each `parsed.json`/`quality.json`.
Reported confidence is a parser heuristic, not calibrated extraction accuracy.

## Reviewed evidence and explicit limits

- Contact sheets were inspected for **every page of every document**.
- PHYS 350 PDF pages **1 and 4** were inspected at readable resolution. Figure 1
  shows the labelled hydrogen transition; Figure 2 explicitly states: “The second
  and third energy levels can each contain up to 8 electrons.” The verified source
  transcription is stored separately from generated descriptions. The canonical
  conversation fixture now expects `8` with `verified_from_source`.
- The two PHYS 350 figures remain distinct references. An unqualified “the diagram”
  must not guess between them; the resolver requests clarification unless a prior
  asset/page or another explicit reference selects one.
- ENGL 120 PDF page **1** was inspected at readable resolution. Its Figure 1 and
  publication-metadata table were approved. The table matches its `Item` / `Detail`
  header, six body rows, and `Lines` / `108` final row. Row-group chunks repeat headers.
- ENGL 120 page **9** was also inspected, but the stress/syllable table transcription
  remains unverified and cannot support an exact answer.
- PHYS 230's reference placements are retained: figures on pages **1, 5, 10**,
  chart on **9**, tables on **6, 9, 11**, and unparsed equations on **7**.
  This is an inventory, not approval of the table cells or chart readings.
- The remaining **46 assets** are `needs_review`. Full-resolution review of every
  visual/table/formula, exact chart data, and verified equation LaTeX remain pending.
  All five `visual_qa_complete` flags are therefore **false**.
- Formula-heavy PHYS 350 pages **3, 5–10** and the formula region on HIST 210 page
  **6** retain explicit equation crops and `equation_unparsed`; overlapping prose
  is conservatively withheld until finer region extraction/review.
- PHYS 230 and HIST 250 are wholly quarantined from student-facing retrieval.
  Other weapons-context pages are restricted page-wide. Their raw PDFs, images,
  tables and parser outputs remain administrator-only QA artifacts. No approved safe
  excerpt set exists yet; some harmless content is intentionally also withheld.

## Reproducibility and regression results

- `make check`: Ruff passes; mypy passes (44 files); **170 tests pass**.
- `uv run python scripts/validate_datasets.py --require-complete`: **61 passed**,
  zero warnings/errors/pending inputs.
- Full-corpus tests verify page coverage, source checksums, attribution, reference
  inventory, table integrity, Bohr figure/citation evidence and expected value,
  correct abstention, and repeat-run idempotence.
- Synthetic tests run without the PDF corpus and cover reused image payloads with
  distinct placements, unreviewed/image-only pages, stale reviews, path containment,
  source changes, missing artifacts, failed QA, atomic active-version replacement,
  and obsolete citation denial.
- Security-boundary tests cover cross-course/document denial, per-call asset checks,
  restricted text/visual/citation blocking, untrusted source instructions, SQL/FTS
  injection-shaped inputs, crop checksums, and pre-filtered optional embedding input.

These are correctness regressions, **not** a statistically meaningful answer-quality
or safety accuracy threshold. Authenticated multi-turn tutoring, generated-answer
grounding, HTTP citation delivery, complete RBAC, and production adapters remain
M3/M4 and later acceptance work. Usage and review instructions:
[`M2_READINGS.md`](M2_READINGS.md).
