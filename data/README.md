# Data boundary

Everything under `data/` is input or derived artefact, never application source.

```text
data/
├── samples/            Supplied authoritative fixtures (JSON committed, PDFs not)
│   └── course-materials/
├── schemas/            Structural JSON Schemas for the supplied fixtures
├── manifests/          Checksums, page counts, presence state for the reading corpus
├── incoming/           Admin upload staging (gitignored)
└── processed/          Page renders, crops, parsed JSON, embeddings, QA reports (gitignored)
```

## Two path conventions

The two source files declare paths against different roots, matching `AGENTS.md`:

| Source | Field | Resolved against |
|---|---|---|
| `samples/course-catalog.json` | `materials[].file` | dataset root, `data/samples/` |
| `manifests/course_readings_manifest.json` | `relative_path` | `DATA_ROOT`, `./data` (declared by `path_base`) |

`scripts/validate_datasets.py` resolves both safely, rejects traversal outside the data
root, and reports the exact path it looked for.

## Source files supplied

All expected inputs are present and re-verified on 2026-11-14: strict validation
reports 62 passed, 0 warnings, 0 errors, and 0 pending inputs.

| File | Content | Status |
|---|---|---|
| `samples/course-catalog.json` | 14 courses, 1 programme, 5 requirement groups, 16-unit cap | ✅ validated |
| `samples/student-records.json` | `student-001`, `student-002` | ✅ validated |
| `samples/test-conversations.json` | 2 scripted conversations | ✅ schema and fixture checks pass; authenticated execution pending |
| `samples/course-materials/phys230-critical-mass.pdf` | 11 pages, `sha256` `9cc30f28…` | ✅ checksum + page count match |
| `samples/course-materials/phys350-bohr-model.pdf` | 12 pages, `sha256` `622528681a28…` | ✅ checksum + page count match |
| `samples/course-materials/engl120-the-raven.pdf` | 15 pages, `sha256` `d84bf67be1b4…` | ✅ checksum + page count match |
| `samples/course-materials/hist210-niels-bohr.pdf` | 17 pages, `sha256` `3d96a5a637fb…` | ✅ checksum + page count match |
| `samples/course-materials/hist250-demon-core.pdf` | 9 pages, `sha256` `e56e78ce782f…` | ✅ checksum + page count match |

M2 has ingested all five readings and retained all 64 pages. Every page's contact
sheet has been inspected, but only 4 of 50 visual assets are approved; full visual QA
remains incomplete for every document. PHYS 230 and HIST 250 are wholly quarantined
from student-facing retrieval. See [the M2 baseline](../docs/M2_INGESTION_REPORT.md)
for review coverage, retrieval restrictions, and remaining work.

The schema files in `data/schemas/` are checked in and validate whatever you supply.
They are a contract, not data: they contain no course or student facts.

## Why the PDFs are not committed

`.gitignore` excludes `samples/course-materials/*.pdf`. The readings are supplied
artefacts, and `AGENTS.md` section 15 requires original data files to stay out of
version control. Reproducibility comes from the manifest checksums. Flip this decision
in `.gitignore` only if the licence review says redistribution is permitted.

## Validation

```bash
uv run python scripts/validate_datasets.py                     # report
uv run python scripts/validate_datasets.py --require-complete  # CI gate
```

Exit codes: `0` valid (pending inputs allowed), `1` validation errors, `2` incomplete
under `--require-complete`.
