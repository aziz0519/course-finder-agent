# Dataset validation report

**Scenario:** Fall 2026 → Spring 2027  
**Validation result:** PASS for all supplied fixtures and source integrity; M2 ingestion implemented, full visual QA incomplete
**Scope note:** updated 2026-11-14 from strict dataset validation and the M2 ingestion baseline. Ingestion and retrieval checks are not authenticated conversation acceptance tests.

> **Re-verified (2026-11-14):** `scripts/validate_datasets.py --require-complete` reports **62 passed, 0 warnings, 0 errors, 0 pending**. All five reading checksums and page counts match the manifest. The validator builds the canonical domain model (14 courses, 1 programme, 5 readings, 2 students), rejecting schema-valid inputs that fail the runtime adapter. `make check` passes Ruff, mypy (45 source files), and **180 tests**. All five PDFs have been ingested with **64/64 pages** retained. Contact sheets were inspected for every page, but only **4 of 50 visual assets** are approved; all five full-visual-QA flags remain false. See [the M2 ingestion baseline](docs/M2_INGESTION_REPORT.md) for per-document results and safety restrictions.

## Files checked

- `data/samples/course-catalog.json`
- `data/samples/student-records.json`
- `data/samples/test-conversations.json`
- `data/schemas/course_catalog.schema.json`
- `data/schemas/student_records.schema.json`
- `data/schemas/test_conversations.schema.json`
- `data/manifests/course_readings_manifest.json`
- `data/manifests/reading_qa.json` (M2 review metadata)
- `data/samples/course-materials/phys230-critical-mass.pdf`
- `data/samples/course-materials/phys350-bohr-model.pdf`
- `data/samples/course-materials/engl120-the-raven.pdf`
- `data/samples/course-materials/hist210-niels-bohr.pdf`
- `data/samples/course-materials/hist250-demon-core.pdf`

## Structural checks

| Check | Result |
|---|---|
| Catalogue courses | 14 |
| Programmes | 1 |
| Requirement groups | 5 |
| Maximum units per term | 16; all 14 courses carry 4 units |
| Scenario terms | Fall 2026 → Spring 2027 |
| Prerequisite and requirement references | PASS |
| Reading references, checksums and page counts | PASS; 5 of 5 |
| Student records | 2 |
| Student IDs unique | PASS |
| Student programme references resolve | PASS |
| Completed/enrolled course codes resolve to catalogue | PASS |
| Enrolment terms match Fall 2026 | PASS |
| Duplicate course records | None |
| Completed/enrolled status conflicts | None |
| Student JSON Schema validation | PASS |

## Representative PDF — preflight and M2 status

| Check | Result |
|---|---|
| Catalogue mapping | PHYS 230 / Critical mass resolves to the supplied file |
| File presence | PASS |
| SHA-256 | `9cc30f28212b81a3886bb418511630c932ddab8a7150015d95b2ee86941f6539` |
| PDF page count | 11 |
| Native text layer | Present; native extraction produced searchable text |
| Visual content inventory | Three figures, one chart, three tables, and one unparsed equation region (8 placements) |
| Visual page locations | Figures: pages 1, 5, 10; chart: page 9; tables: pages 6, 9, 11; displayed equations: page 7 |
| Equation extraction | Source crop retained with `equation_unparsed`; no verified LaTeX |
| Table extraction | Structured cells and header-aware row-group chunks retained; visual header/cell QA still required |
| OCR strategy | Selective OCR only; blanket OCR is not required for this born-digital file |
| Ingestion | Implemented; all 11 pages retained with renders, layout, chunks, crops and quality report |
| Student-facing access | Entire PHYS 230 reading quarantined pending a reviewed safe-excerpt set |

The initial generic embedded-image extractor returned repeated instances of four unique image payloads across pages. M2 uses page-region placements and checksum-deduplicated crops rather than raw image-object counts. Source attribution and the Creative Commons Attribution-ShareAlike notice on the final page are retained in the immutable artifacts.

## Spring 2027 eligibility regression fixtures

Eligibility means offered in Spring 2027, not already completed or enrolled in Fall 2026, and all prerequisites satisfied by completed courses plus Fall 2026 courses in progress. Courses planned concurrently for Spring 2027 do not satisfy one another's prerequisites.

| Student | Eligible catalogue candidates | Notes |
|---|---|---|
| `student-001` | PHYS 110, MATH 150, PHYS 340, ENGL 130 | PHYS 110 and MATH 150 advance the Physics core. PHYS 340 is eligible with completed PHYS 230 and may be the second Physics elective if PHYS 350 is successfully completed. ENGL 130 is an optional alternative while ENGL 120 is in progress. |
| `student-002` | PHYS 110, MATH 150, ENGL 130, HIST 210 | ENGL 130 and HIST 210 are optional alternatives while ENGL 120 and HIST 250 are in progress. PHYS 340 is not eligible because PHYS 230 is neither completed nor in progress. |

A sensible core-oriented Spring 2027 proposal for `student-001` is PHYS 110 + MATH 150 + PHYS 340 (12 units). The 16-unit limit is a maximum, not a target. PHYS 120 and PHYS 490 are not eligible in Spring 2027 under the supplied record and prerequisite policy.

## Remaining validation work

- Complete readable-resolution QA of the remaining 46 visual assets across all five readings; contact-sheet inspection is not full visual approval.
- Verify equation LaTeX, remaining table structure, and chart labels/values against source crops. Unparsed or unreviewed regions remain unavailable; OCR/VLM enrichment and exact chart digitization are not enabled.
- Review a safe-excerpt set before relaxing the full PHYS 230/HIST 250 quarantine or other weapons-context page restrictions.
- Confirm the adviser IDs against an adviser directory or identity mapping if one is later supplied. The current source provides only opaque adviser ID strings.
- Implement and test authenticated multi-turn conversations, generated-answer grounding, HTTP citation delivery, and complete RBAC. Existing Pydantic validators and domain/retrieval regressions do not establish production acceptance.


## Sample conversation acceptance suite

The conversation suite was not present in the repository as received. A suite reconstructed
from AGENTS.md section 14 is checked in at `data/samples/test-conversations.json` and
validated against `data/schemas/test_conversations.schema.json`; its `provenance` field
records the reconstruction. It is a test script, not academic evidence.

| Scenario | Current status | Key assertions |
|---|---|---|
| PHYS 350 Bohr model question + diagram follow-up | Ingestion, approved-figure retrieval and citation regressions pass; authenticated conversation pending | Figure 2 on PDF page 4 explicitly labels up to 8 electrons for the second level. The fixture requests clarification for an ambiguous diagram reference in turn 2, then verifies `expected_answer_value: 8` with `verified_from_source` after the explicit Figure 2 reference in turn 3. Preserve document/page/asset context and abstain when evidence is unavailable. |
| Spring 2027 12-unit plan + 8-unit follow-up | Deterministic schedule regressions pass; persisted conversational cap pending | Start with PHYS 110 + MATH 150 + PHYS 340 (12 units); on follow-up recompute to PHYS 110 + MATH 150 (8 units) as the core-progression default. Keep the request-specific cap in thread state and leave the catalogue's 16-unit policy unchanged. |

The 8-unit default prioritizes the two outstanding Physics core foundations and their downstream prerequisite paths. PHYS 340 remains prerequisite-eligible and can be chosen instead when the student explicitly prefers to prioritize Physics electives.
