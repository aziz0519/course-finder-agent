# Dataset validation report

**Scenario:** Fall 2026 → Spring 2027  
**Validation result:** PASS for the supplied catalogue and student JSON fixtures; PARTIAL PASS for the first PDF preflight  
**Scope note:** this report was produced when only the PHYS 230 PDF had been supplied. All five PDFs are now present; the re-verification note below records the current state.

> **Re-verified (2026-11-13, after the fixtures were added):** the supplied bytes now match this report, and the corpus is complete. `scripts/validate_datasets.py` reports 39 passed, 0 warnings, 0 errors, 0 pending; all five reading checksums and page counts match the manifest; the PHYS 230 `sha256` (`9cc30f28…`) and its 11-page count match the preflight above. The validator now also builds the canonical domain model (14 courses, 1 programme, 5 readings, 2 students) so a file that satisfies the schema but not the runtime adapter is a hard failure. The remaining limitation is that only PHYS 230 has a completed *visual* preflight, and no full ingestion has been run.

## Files checked

- `data/samples/course-catalog.json`
- `data/samples/student-records.json`
- `data/schemas/student_records.schema.json`
- `data/samples/course-materials/phys230-critical-mass.pdf`

## Structural checks

| Check | Result |
|---|---|
| Catalogue courses | 14 |
| Programmes | 1 |
| Student records | 2 |
| Student IDs unique | PASS |
| Student programme references resolve | PASS |
| Completed/enrolled course codes resolve to catalogue | PASS |
| Enrolment terms match Fall 2026 | PASS |
| Duplicate course records | None |
| Completed/enrolled status conflicts | None |
| Student JSON Schema validation | PASS |

## Representative PDF preflight

| Check | Result |
|---|---|
| Catalogue mapping | PHYS 230 / Critical mass resolves to the supplied file |
| File presence | PASS |
| SHA-256 | `9cc30f28212b81a3886bb418511630c932ddab8a7150015d95b2ee86941f6539` |
| PDF page count | 11 |
| Native text layer | Present; native extraction produced searchable text |
| Visual content inventory | Four logical figures, three tables, and displayed equations |
| Visual page locations | Figures: pages 1, 5, 9, 10; tables: pages 6, 9, 11; displayed equations: page 7 |
| Equation extraction | Text-only extraction missed displayed formulas; page-image/formula verification required |
| Table extraction | Three table CSVs emitted; visual header/cell QA still required |
| OCR strategy | Selective OCR only; blanket OCR is not required for this born-digital file |
| Full Docling ingestion | NOT YET RUN; this is a preflight/strategy assessment, not a completed RAG ingestion |

The generic embedded-image extractor also returned repeated instances of four unique image payloads across pages. Figure inventory and page attribution must therefore come from layout/page-region associations and page renders, not the raw image-object count alone. Source attribution and the Creative Commons Attribution-ShareAlike notice on the final page must be retained.

## Spring 2027 eligibility regression fixtures

Eligibility means offered in Spring 2027, not already completed or enrolled in Fall 2026, and all prerequisites satisfied by completed courses plus Fall 2026 courses in progress. Courses planned concurrently for Spring 2027 do not satisfy one another's prerequisites.

| Student | Eligible catalogue candidates | Notes |
|---|---|---|
| `student-001` | PHYS 110, MATH 150, PHYS 340, ENGL 130 | PHYS 110 and MATH 150 advance the Physics core. PHYS 340 is eligible with completed PHYS 230 and may be the second Physics elective if PHYS 350 is successfully completed. ENGL 130 is an optional alternative while ENGL 120 is in progress. |
| `student-002` | PHYS 110, MATH 150, ENGL 130, HIST 210 | ENGL 130 and HIST 210 are optional alternatives while ENGL 120 and HIST 250 are in progress. PHYS 340 is not eligible because PHYS 230 is neither completed nor in progress. |

A sensible core-oriented Spring 2027 proposal for `student-001` is PHYS 110 + MATH 150 + PHYS 340 (12 units). The 16-unit limit is a maximum, not a target. PHYS 120 and PHYS 490 are not eligible in Spring 2027 under the supplied record and prerequisite policy.

## Remaining validation work

- Run the full Docling ingestion, page-count, extraction-quality and citation-provenance checks across all five supplied readings, starting with the PHYS 230 reference fixture. No full ingestion has been run yet.
- Complete the visual preflight and QA for the four readings beyond PHYS 230 (PHYS 350, ENGL 120, HIST 210, HIST 250); only PHYS 230 has a completed visual preflight.
- Confirm formula recognition, visual crops, table structure, and content-safety labels using the real parser/model configuration.
- Confirm the adviser IDs against an adviser directory or identity mapping if one is later supplied. The current source provides only opaque adviser ID strings.
- Implement the Pydantic ingestion validators and automated regression tests in the backend; this report records the current fixture-level checks, not a production deployment test.


## Sample conversation acceptance suite

The supplied sample conversations are recorded in `data/samples/test-conversations.json` and validated against `data/schemas/test_conversations.schema.json`.

| Scenario | Current status | Key assertions |
|---|---|---|
| PHYS 350 Bohr model question + diagram follow-up | PDF present; ingestion, diagram verification and retrieval pending | Resolve the Fall 2026 PHYS 350 enrolment, ingest and index the Bohr model reading, preserve document/page/figure context across turns, and cite the diagram. Complete the diagram verification and retrieval checks before asserting the expected value of 8; do not hard-code it until the supplied diagram has been inspected and confirms it. |
| Spring 2027 12-unit plan + 8-unit follow-up | READY for deterministic tests | Start with PHYS 110 + MATH 150 + PHYS 340 (12 units); on follow-up recompute to PHYS 110 + MATH 150 (8 units) as the core-progression default. Keep the request-specific cap in thread state and leave the catalogue's 16-unit policy unchanged. |

The 8-unit default prioritizes the two outstanding Physics core foundations and their downstream prerequisite paths. PHYS 340 remains prerequisite-eligible and can be chosen instead when the student explicitly prefers to prioritize Physics electives.
