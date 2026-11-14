# M2 — local reading ingestion and retrieval

M2 implements the local reading layer from ADR 0001. It does **not** expose an
unauthenticated API, generate tutor answers, or implement conversation state. Those
remain M3/M4. No model key, network access, OCR download, or AWS credentials are needed.

## Run

```bash
uv sync --all-groups
make validate-strict
make ingest
make check

# One catalogue reading:
uv run python scripts/ingest_datasets.py --course "PHYS 350"

# Alternate data/artifact roots (administrator/operator use):
uv run python scripts/ingest_datasets.py \
  --data-root ./data --output ./data/processed/readings \
  --reviews ./data/manifests/reading_qa.json
```

The CLI exits `1` for an extraction/structural error. It exits `0` for a successful
run **with QA warnings**, including a version whose unreviewed text cannot activate.
Read `text_activatable`, `visual_qa_complete`, and `errors`; exit zero is not full
visual approval. Missing PDF fixtures fail ingestion, not silently substitute content.

## Pipeline and artifacts

1. Load the authoritative catalogue/student adapters and reading manifest.
2. Enforce PDF extension/signature, dataset containment (including symlinks), 50 MiB
   size cap, SHA-256, unencrypted bytes, and manifest page count.
3. Extract native reading-order blocks with pinned **PyMuPDF 2.1** and tables with
   **pdfplumber 0.11.10**, behind `PdfParser`. No blanket OCR is run.
4. Preserve PDF page identities, optional printed labels, geometry, metadata,
   outline, native layout JSON, attribution/license lines, 110 DPI page renders,
   144 DPI crops, and six-pages-per-image contact sheets.
5. Use actual image placements, vector drawing clusters, table boundaries, math
   heuristics, and checksum-bound reviewed regions. Identical crop payloads share a
   checksum/path, but placements retain separate asset IDs and page/region identities.
6. Chunk paragraph/heading blocks without splitting formulas into invented prose.
   Tables retain typed cells and row-group chunks with repeated headers. Approved
   captions link to source crops; unreviewed captions are not ordinary prose evidence.
7. Run structural/provenance/artifact-integrity QA. Every source page remains present.
   Image-only/garbled pages get `ocr_required`/uncertainty warnings, not fake OCR.
   Unparsed math retains a crop and `equation_unparsed`, never guessed LaTeX.
8. Atomically rename completed artifacts and transactionally publish the registry
   version/active pointer. Only reviewed text can activate. Individual visuals still
   require their own approval. Failed versions do not replace the previous active one.

`DATA_ROOT/processed/readings/<hashed-document-id>/<version>/` contains:

```text
source.pdf          # immutable copy; administrator only
parsed.json         # normalized typed document/pages/chunks/assets
quality.json        # checks, warnings, counts, versions, elapsed processing time
layout/*.json       # native parser layout and reading order
pages/*.png         # full page images; administrator only
assets/<sha256>.png # deduplicated crops
contact-sheet-*.png
```

`readings.sqlite3` stores the version registry, normalized records, and active
pointers. Initial schema is the packaged migration
`backend/app/repositories/sql/0001_readings.sql`. A future schema change needs another
numbered migration. Binary artifacts never go into SQLite. Derived artifacts and
original PDFs remain gitignored; commit review metadata and content-free reports only.

The version key includes the source checksum, catalogue document metadata, parser
identity/dependency versions, pipeline policy, and review data. Identical inputs are
idempotent. Changing a review creates a new immutable version; old citation IDs cannot
resolve against a newer active version. To roll back, use an explicit future admin
activation workflow, not an ordinary re-run of an older review.

Interrupted jobs leave `.staging-*/failure.json` with an error type/version; complete
artifact directories whose registry transaction was interrupted are revalidated and
recovered on re-run. Do not delete or modify active artifacts. There is no automatic
garbage collection or concurrent multi-worker ingestion scheduler in this milestone.

## Review workflow

`data/manifests/reading_qa.json` is administrator-authored, strict Pydantic data keyed
by document ID and bound to **the complete SHA-256**. Source PDFs cannot instruct the
pipeline to approve themselves. Reviews record who/what inspected the source, notes,
text-page approval, and visual regions in PDF points (top-left origin).

Inspect every page's contact sheet and inspect each table/chart/equation/figure at
readable resolution before approving it. Match row/column headers, merged cells,
units, chart axes/legend, and signs/subscripts in formulas against the image.
Approve equation assets only with verified LaTeX. Mark exact-value verification only
for independently checked values; generated descriptions are not source text.

The checked-in review is an **agent preflight**, not a human-certified complete
visual audit. It approves only the explicitly inspected assets in the baseline report.
All remaining visual claims abstain. Formula-heavy Bohr pages deliberately retain
full-page equation crops and exclude overlapping blocks from prose retrieval until
finer regions/LaTeX are reviewed. This trades recall for safe abstention.

OCR, Docling, VLM enrichment, chart digitization, and production embedding-provider
adapters are not enabled. `PdfParser`/`Embeddings` are replacement seams. A scanned
page or unreadable region remains inactive until an appropriate parser/enricher and
checksum-bound review are supplied. This limitation is explicit in quality reports.

## Retrieval contract and access boundary

Use `LocalRetriever` from `backend/app/retrieval/readings.py`; never give agents a
`ReadingRepository`, raw artifact directory, unrestricted PDF URL, or SQL connection.

```python
# M4 constructs this from a VERIFIED principal and server-side policy checks.
# It must NOT deserialize it from browser or LLM tool arguments.
scope = ReadingScope(
    principal_id=verified_user_id,
    course_ids=authorized_course_ids,
    document_ids=authorized_reading_ids,
)
result = retriever.search(scope, "PHYS 350", "hydrogen spectrum transitions")
```

This is a scoped service interface, **not a substitute for authentication/RBAC**.
M4 must enforce identity-to-student mapping, adviser assignment, conversation
ownership, and admin-only ingestion before invoking it. No public endpoints exist yet.

- Filter course/document IDs and active versions first, then safe, reviewed chunks.
  Only those candidates enter an ephemeral SQLite FTS5 BM25 index.
- Default retrieval is lexical/offline. An optional `Embeddings` implementation can
  rerank at most 60 lexical candidates; no outside-course/restricted passage is sent
  to it. A production provider must separately implement timeouts, retry/token/cost
  budgets, and redacted logging. There is no configured external provider by default.
- Evidence carries title, course, document/checksum/version, 1-based PDF page,
  section, excerpt, chunk/asset IDs, and bbox. It is explicitly `untrusted_source`.
  `resolve_citation` rechecks scope and active-version membership on every call.
- Visual queries return `visual_required`, not prose-only evidence. M3 resolves a
  thread's document/asset/page reference and calls `resolve_visual`. Multiple
  plausible assets return `clarification_required`, never an unrestricted search.
- Approved visual evidence returns the original checksum-checked crop and adjacent
  approved source text. Exact table values require verified structure; exact
  equations require approved LaTeX. Exact chart digitization is deliberately disabled.
- No source evidence returns an explicit abstention status/note. There is no fallback
  to model knowledge or internet search.

## Content safety

PHYS 230 and HIST 250 are conservatively quarantined **in full**, including text,
tables, captions, crops, citation resolution, and prior asset IDs. Other readings'
weapons/fissile-system context is restricted page-wide, not only in isolated chunks.
Full PDF/page/layout access is administrator-only; a citation is evidence metadata,
not a download link to an unsafe page.

This conservative rule intentionally also withholds some harmless educational
material. A reviewed safe-excerpt set and a stronger classifier are required before
relaxing it. Keyword classification alone is not a production safety guarantee.
M3 still must refuse operational weapon requests and must not put restricted content
into conversation memory. Ingestion/QA does not authorize disclosing source content.
