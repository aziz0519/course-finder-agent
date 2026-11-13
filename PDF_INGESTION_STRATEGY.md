# PDF Ingestion Strategy — Student Learning Assistant

## Objective

Ingest five short course readings (roughly 9–17 pages each) so the Tutor can answer from prose and can also interpret figures, diagrams, charts, tables, and displayed equations with page-level citations. The MVP corpus is small, so use a quality-first pipeline with strong provenance rather than a large managed knowledge-base stack.

## Recommended approach

Use **Docling for layout-aware conversion**, **selective OCR and vision/formula enrichment for difficult regions**, **PostgreSQL + pgvector for retrieval metadata and embeddings**, and **S3 for source PDFs and derived visual artefacts** in AWS. Keep the parser behind an interface so it can be replaced without changing agent tools or domain logic.

1. Preflight each document and build a source manifest with checksum, page count, page dimensions, text-layer availability, attribution, and current ingestion version.
2. Run Docling's standard PDF pipeline first. Preserve reading order, section hierarchy, text blocks, table structure, captions, page references, and geometry.
3. Render every page and retain page images. Extract picture/diagram/chart/table crops with their bounding boxes and source-page association.
4. Use OCR only on image-only or low-quality pages/regions. Do not run blanket OCR on a born-digital document with a healthy text layer.
5. Apply formula recognition to pages with displayed equations and chart/vision enrichment to detected charts and diagrams. Store the original crop beside the extracted representation.
6. Normalize page, text, table, equation, and figure data into typed records. Chunk by semantic section and content type; preserve table headers and equation context.
7. Index searchable text, table rows, equation text, captions, and labelled machine-generated visual descriptions. For a visual follow-up, retrieve the actual page crop and inspect it with a vision-capable model; never rely on a caption alone.
8. Run visual and structural QA, then publish an immutable ingestion version. Low-confidence assets stay unavailable for exact visual answers until reviewed.

## Findings from the first supplied reading

File: `data/samples/course-materials/phys230-critical-mass.pdf` (PHYS 230, “Critical mass”).

- The file is 11 pages, unencrypted, US Letter, PDF 1.7, and contains a usable text layer.
- Visual inspection identified a photograph, diagrams/schematics, a chart, three tables, and displayed equations.
- Logical figures occur on PDF pages 1, 5, 9, and 10; tables occur on pages 6, 9, and 11; displayed equations occur on page 7.
- Native text extraction works, but it does not preserve the displayed equations. Formula recognition and page-render verification are therefore mandatory for equation-dependent answers.
- Basic table extraction emits three CSV files, but a CSV output is not sufficient evidence of correct header/cell reconstruction. Compare tables with source page crops.
- A generic embedded-image extractor returns repeated copies of the same four underlying image payloads on multiple pages. De-duplicate binary images by checksum while retaining separate page-placement references from layout data.
- The last page contains attribution and a Creative Commons Attribution-ShareAlike notice; preserve it in document metadata.

This is a preflight and extraction smoke test. Full Docling ingestion and the final parser/model configuration have not yet been run.

## Data model minimum

- `documents`: course, title, source filename, checksum, page count, active ingestion version, attribution/license metadata.
- `document_pages`: 1-based PDF page, optional printed page label, rendered page URI, extracted text, layout JSON, parser confidence, quality flags.
- `reading_chunks`: content type, text/LaTeX, section, page range, source bbox, extraction method/confidence, safety label, embedding.
- `figure_assets`: page, figure/table/chart type, bbox, crop URI, checksum, caption, visual description, review status.
- `ingestion_jobs`: file version, status, tool/model versions, timings, warnings, and per-page QA results.

## Retrieval and answer strategy

- Resolve course -> catalogue reading -> document ID before retrieval.
- Text questions use course/document-filtered hybrid keyword + vector search.
- Diagram/chart/table/equation questions use the prior conversation's cited document/asset when the user uses references such as “that diagram”. If the referent is ambiguous, ask a clarification.
- Retrieve the original crop plus caption and adjacent text. Exact table/chart values require verified extraction; otherwise respond that the source cannot be read confidently.
- Cite title + 1-based PDF page + figure/table/equation identifier when available.
- If a requested detail is absent or extraction is uncertain, say so rather than guessing.

## Safety boundary

The PHYS 230 reading includes nuclear weapon-design material. Ingestion must label content at chunk level. Student-facing retrieval may support non-operational educational discussion of general nuclear-physics concepts, but must not surface actionable weapon-design parameters, material configurations, assembly procedures, or calculations that could enable weapon construction or optimization. Apply the restriction during retrieval and answer generation, not only in a prompt. Keep the source PDF available to authorized administrators for provenance and QA.

## Quality gates

- All pages accounted for; no silent page omissions.
- Figure, table, and equation assets have correct page references and review states.
- Table structure visually matches source header/row/column relationships.
- Displayed formulas have verified LaTeX and a source crop or are explicitly marked unparsed.
- Exact chart readings are not generated from a qualitative VLM caption.
- Citation resolves to the original document/page/region.
- Per-document report records parser version, OCR/VLM models, checksum, page-level warnings, and QA outcome.
- Re-ingestion is idempotent; only a fully validated version becomes active.

## Remaining work

Four catalogue-referenced readings are still pending: PHYS 350 / Bohr model, ENGL 120 / The Raven, HIST 210 / Niels Bohr, and HIST 250 / Demon core. Run a separate preflight for each; do not assume the other PDFs have the same text-layer or visual layout profile as the PHYS 230 sample.
