# Course Finder Agent — MVP

A student learning and course-planning assistant for the fixed Fall 2026 → Spring 2027
scenario. It answers questions from the supplied course readings with page-level
citations, reports degree progress against the supplied BSc Physics requirements, and
recommends verified Spring 2027 candidates using deterministic eligibility rules.

**Everything factual comes from the supplied fixtures.** When a fact is absent, the
assistant says so instead of guessing.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M0** | Repo scaffold, typed settings, dataset contract, Phase 0 validator | ✅ **complete** (2026-11-13) |
| **M1** | Deterministic domain core: adapters, prerequisite eligibility, degree progress | ✅ **complete** (2026-11-13) |
| **M2** | Reading ingestion and course-scoped retrieval with page citations | **implemented** — visual QA remains gated |
| **M3** | Conversation state, supervisor routing, tutor and planner | ✅ **complete** (2026-11-14) |
| M4 | API, local auth, RBAC and negative security tests | |
| M5 | UI (Gradio over the API is the recommendation; Next.js remains supported) | |
| M6 | Deployable demo (container + single CDK stack) | |
| M7 | Acceptance run, quality baseline, documentation | |

## M0 exit gate — confirmed

Historical results below describe M0 at completion. Current verification is recorded
in the M2 section.

| Criterion | Evidence | Result |
|---|---|---|
| Repository is standalone and clean | Own git repo, no secrets staged, PDF bytes gitignored | ✅ |
| Python toolchain reproducible | `uv.lock`, Python 3.12 pinned, `uv sync --all-groups` | ✅ |
| Scenario terms are configuration, not clock-derived | `Settings.current_term` / `next_term`, equal-term combinations rejected | ✅ |
| Production cannot start with placeholders | `assert_production_ready()` rejects local auth and `replace-me` secrets | ✅ |
| Dataset contract exists | JSON Schemas for catalogue and student records | ✅ |
| Supplied catalogue validates | 14 courses, 1 programme, 5 requirement groups, 16-unit cap, terms Fall 2026 → Spring 2027 | ✅ |
| Reading corpus complete | **5 of 5** PDFs present; PHYS 230 checksum matches the recorded `9cc30f28…` and its 11-page count | ✅ |
| Student fixtures validate | 2 records, unique IDs, references resolve, enrolled terms equal Fall 2026, no completed/enrolled conflict | ✅ |
| Validator fails closed on bad data | A deliberately corrupted copy produced 6 expected failures (bad prerequisite, unsupported rule, out-of-bounds `count`, duplicate ID, completed∩enrolled overlap, wrong enrolment term) | ✅ |
| Quality gates green | `ruff` clean, `mypy` clean (14 files), `pytest` 17 passed | ✅ |
| Dataset report | `validate_datasets.py` → 61 passed, 0 warnings, 0 errors, 0 pending; `--require-complete` exits `0` | ✅ |

M0 deliberately stops at the data boundary. It contains **no** prerequisite engine, no
PDF ingestion, no API, and no cloud resources — those are M1–M6.

## Quick start

```bash
uv sync --all-groups          # creates .venv with Python 3.12
cp .env.example .env          # placeholders only; safe for local development
make validate                 # 62 checks against the supplied fixtures
make ingest                   # all five PDFs; local versioned artifacts and QA reports
make check                    # lint + typecheck + tests
```

The Makefile targets return `0` on success and `2` on failure — make's own recipe-failure
code, whether the cause is validation errors (`make validate`) or a missing expected input
(`make validate-strict`). The distinct `0`/`1`/`2` codes apply only when invoking
`scripts/validate_datasets.py` directly: `0` valid (pending inputs tolerated), `1`
validation errors, `2` pending inputs with `--require-complete`.

## Dataset inventory

| Course | Reading | Pages | Text chars | Checksum (sha256, truncated) |
|---|---|---|---|---|
| PHYS 230 | Critical mass | 11 | 21,454 | `9cc30f28212b…` |
| PHYS 350 | Bohr model | 12 | 22,406 | `622528681a28…` |
| ENGL 120 | The Raven | 15 | 29,143 | `d84bf67be1b4…` |
| HIST 210 | Niels Bohr | 17 | 36,722 | `3d96a5a637fb…` |
| HIST 250 | Demon core | 9 | 16,126 | `e56e78ce782f…` |

All five sit inside the documented 9–17 page range and carry an extractable text layer.
Full checksums, sizes, and the PHYS 230 preflight findings are in
[`data/manifests/course_readings_manifest.json`](data/manifests/course_readings_manifest.json).
PDF bytes are gitignored; integrity is proven by that manifest.

Two facts about the fixtures worth recording:

- The programme uses the `requirements` key rather than `requirement_groups`. Both are
  accepted by the schema and the validator; the M1 adapter normalises to
  `RequirementGroup`.
- `policies.in_progress_prerequisites` is a human-readable sentence in the source. M1
  converts it into an explicit typed rule (`InProgressPrerequisitePolicy`) and refuses to
  guess if the wording changes — a catalogue string is documentation, not an executable
  policy.

## Repository layout

```text
backend/app/
  core/           typed settings (fixed scenario terms, resolved paths, prod guards)
  domain/         deterministic rules — no LLM, no framework
  ingestion/      JSON adapters, PDF pipeline, quality gates
  retrieval/      course-scoped retrieval with provenance
  agents/         supervisor and specialists
  repositories/   authorized data access
  services/       use cases
  auth/           local session adapter, Cognito verification
  policies/       deny-by-default authorization
  api/v1/         versioned HTTP routes
backend/tests/    unit, integration, security, fixtures
data/
  samples/        supplied catalogue, student records, five PDFs
  schemas/        structural JSON Schemas (contract, not data)
  manifests/      checksums, page counts, presence state
  incoming/       admin upload staging (gitignored)
  processed/      renders, crops, parsed JSON, embeddings (gitignored)
scripts/          validate_datasets.py (Phase 0), ingest_datasets.py (M2)
infra/            AWS CDK v2 target and demo tiers (documented, not built)
docs/decisions/   architecture decision records
```

`AGENTS.md` is the source of truth for scope, agent boundaries, and acceptance criteria.

## Commands

| Command | Purpose |
|---|---|
| `make sync` | Create the venv and install dependencies |
| `make validate` | Phase 0 dataset validation |
| `make validate-strict` | Validation that fails on any missing input |
| `make ingest` | Ingest all five readings with checksum-bound review and QA gates |
| `make test` | Run the test suite |
| `make lint` / `make fmt` | Ruff check / format |
| `make typecheck` | mypy |
| `make check` | lint + typecheck + tests |

## Design invariants

These are not negotiable, and every milestone preserves them:

1. Prerequisite, term-offering, and degree-requirement decisions are deterministic code.
   A model may explain the result; it may not produce or override it.
2. Every reading claim carries a document title and a 1-based PDF page. Missing or
   unreadable sources produce an abstention, never a fabricated citation.
3. Authorization is enforced server-side before any agent or retrieval tool runs.
   Student scope comes from the authenticated principal, never from request input.
4. Agents get typed, permission-checked tools. No agent holds an unrestricted database
   or filesystem handle.
5. Retrieved document content is untrusted data. Instructions inside a PDF are not
   instructions to the system.
6. Secrets stay out of the repository; `.env.example` holds placeholders only.
7. Restricted nuclear-content chunks are excluded from student-facing retrieval rather
   than relying on prompt wording alone.

## M1 exit gate — confirmed

M1 is pure deterministic Python: no model provider, no database, no UI, no network.
The counts below are historical M1 completion results; see M2 for current verification.

| Criterion | Evidence | Result |
|---|---|---|
| Canonical models exist and self-validate | `Course`, `Program`, `RequirementGroup`, `AcademicPolicy`, `Student`, `ReadingDocument`, `Term` — frozen, `extra="forbid"` | ✅ |
| Source adapters preserve provenance and fail closed | Raw JSON kept in `SourceDocument` with SHA-256; unknown rules, missing `prerequisites`, dangling references, bad terms, and path traversal all raise instead of defaulting | ✅ |
| In-progress prerequisite rule is typed, not prose | `InProgressPrerequisitePolicy`; absent or unrecognised statement yields `allowed=False`, or `PolicyError` | ✅ |
| Next-term-only prerequisite scope | `allows_in_progress_prerequisites_for()` returns true for `Spring 2027` only | ✅ |
| Golden eligibility for `student-001` | PHYS 110, MATH 150, PHYS 340, ENGL 130 | ✅ |
| Golden eligibility for `student-002` | PHYS 110, MATH 150, ENGL 130, HIST 210; PHYS 340 absent | ✅ |
| Never recommended | PHYS 120, PHYS 490 for Spring 2027; Fall-only PHYS 230/330/350 and HIST 250 excluded by term | ✅ |
| Unit cap enforced, never mutated | 12-unit plan = 110 + 150 + 340; 8-unit plan = 110 + 150 with 340 `deferred` and still `eligible`; request caps never touch catalogue policy | ✅ |
| No filler courses | In-progress ENGL 120 suppresses ENGL 130 as a recommendation; it stays an alternative | ✅ |
| In-progress is not completed credit | `calculate_degree_progress` reports `in_progress`; `satisfied_by` only ever contains completed courses | ✅ |
| Quality gates green | `ruff` clean, `mypy` clean (33 source files including tests), `pytest` 125 passed | ✅ |
| Validator includes the runtime model | `validate_datasets.py` now builds the canonical model too → 61 passed | ✅ |

Test coverage by area: term ordering (9), adapters (33), eligibility (20), degree progress
(11), planning (19), fixture loading (12), settings/validator (18), conversation fixtures
(3). Total: 125.

Two test expectations were corrected during M1 because the code was right:

- **Term ordering is calendar order.** `Spring 2026 < Fall 2026`, even though the strings
  sort the other way. `Term.sort_key` is `(year, season_index)`, so `Fall 2025 < Spring
  2026` and the "completed before current term" rule holds.
- **One in-progress elective is not on track.** `student-001` has 1 of 2 physics electives
  covered by PHYS 350, so `physics-electives` is `remaining` with `courses_short=1` —
  not `in_progress`. A choose-group only becomes `in_progress` once its count is covered.

## M2 — reading ingestion and retrieval

Implemented with pinned PyMuPDF + pdfplumber behind `PdfParser`, immutable local
artifacts, a SQLite version registry, and course/document-filtered FTS5 BM25 retrieval.
No model calls, database server, or AWS credentials are needed.

| Check | Result |
|---|---|
| Source integrity and page coverage | All five checksums/page counts match; **64/64 pages** retained |
| Visual inventory and provenance | **50** cropped placements; tables retain structured cells and header-aware chunks |
| Review gating | **4** inspected assets approved; remaining visuals/equations abstain |
| Citations | Title, 1-based PDF page, checksum/version, chunk/asset IDs and bbox; scoped round-trip resolver |
| Versioning | Idempotent ingestion, atomic active pointer, failed versions cannot displace an active one |
| Safety | PHYS 230 and HIST 250 fully quarantined; other weapons-context pages restricted |
| Verification (2026-11-14) | `make check`: lint clean, mypy clean (**45 source files**), **180 tests pass**; strict dataset validation: **62 passed**, no warnings/errors/pending inputs |

The Bohr shell-capacity value is now source-verified: Figure 2 on PDF page 4 explicitly
labels up to eight electrons for the second level. The conversation fixture records that
verification. A generic “the diagram” reference still requires clarification when
conversation evidence leaves multiple figures plausible.

See [M2 usage and boundaries](docs/M2_READINGS.md) and the
[ingestion baseline](docs/M2_INGESTION_REPORT.md). Full visual QA is **not** complete:
unreviewed formulas/charts/tables remain unavailable, and no exact chart digitization
or OCR/VLM enrichment is enabled. Tutor answer generation and conversation state are M3;
authentication and HTTP delivery remain M4. The initial workflow is documented in
[`docs/M3_CONVERSATIONS.md`](docs/M3_CONVERSATIONS.md).

## M3 — conversation workflow

M3 adds owner-scoped SQLite thread persistence, compact checkpoints, deterministic
supervisor routing, a grounded offline answer composer, tutor visual follow-ups, planner
preference continuity, source-version provenance, and redacted trace IDs. Turn writes are
atomic and stale concurrent checkpoints fail closed. The canonical Bohr and 12-to-8-unit
planning conversations run end to end at the service boundary.

Current M3 verification: Ruff clean, mypy clean (**57 source files**), and **193 tests
pass**. Authentication and HTTP delivery remain M4.

## Open decisions

| Decision | Recommendation | Impact if deferred |
|---|---|---|
| Frontend: Gradio vs Next.js | Gradio over the FastAPI boundary (~1–2 days, swappable later) | Blocks M5 only |
| Infrastructure tier | Local-first now; single cheap stack (~$50/mo) after acceptance | Blocks M6 only |

See [`docs/decisions/0001-mvp-stack.md`](docs/decisions/0001-mvp-stack.md) and
[`infra/README.md`](infra/README.md).

## Known limitations

- All five readings are locally ingested, but no chat/API is exposed until M3/M4.
- Only explicitly reviewed visuals are available. Remaining assets stay `needs_review`;
  formula-heavy pages conservatively withhold overlapping prose pending finer extraction.
- The two nuclear-system readings are entirely withheld from student retrieval pending
  a reviewed safe-excerpt set. Full PDFs/page renders are administrator-only artifacts.
- The retrieval scope is a server-side service contract, not authentication; M4 must
  construct it from verified identities and authorization decisions.
- Degree progress is only as reliable as the supplied requirements JSON.
- No seats, timetable, instructor, or grade data exists in the fixtures and none will be
  invented.
- Suggestions will be candidates, not an official study plan or graduation audit.

## Security housekeeping

This directory is its own repository with `origin` at `github.com/aziz0519/course-finder-agent`.
The parent workspace (`/mnt/c/Users/aziz_`) is an unrelated project whose `.git/config`
contains a plaintext GitHub token — rotate it and never copy it into this repository.
