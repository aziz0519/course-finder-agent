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
| **M1** | Deterministic domain core: adapters, prerequisite eligibility, degree progress | next |
| M2 | Reading ingestion and course-scoped retrieval with page citations | |
| M3 | Conversation state, supervisor routing, tutor and planner | |
| M4 | API, local auth, RBAC and negative security tests | |
| M5 | UI (Gradio over the API is the recommendation; Next.js remains supported) | |
| M6 | Deployable demo (container + single CDK stack) | |
| M7 | Acceptance run, quality baseline, documentation | |

## M0 exit gate — confirmed

| Criterion | Evidence | Result |
|---|---|---|
| Repository is standalone and clean | Own git repo, two commits, no remote, no secrets staged | ✅ |
| Python toolchain reproducible | `uv.lock`, Python 3.12 pinned, `uv sync --all-groups` | ✅ |
| Scenario terms are configuration, not clock-derived | `Settings.current_term` / `next_term`, equal-term combinations rejected | ✅ |
| Production cannot start with placeholders | `assert_production_ready()` rejects local auth and `replace-me` secrets | ✅ |
| Dataset contract exists | JSON Schemas for catalogue and student records | ✅ |
| Supplied catalogue validates | 14 courses, 1 programme, 5 requirement groups, 16-unit cap, terms Fall 2026 → Spring 2027 | ✅ |
| Reading corpus complete | **5 of 5** PDFs present; PHYS 230 checksum matches the recorded `9cc30f28…` and its 11-page count | ✅ |
| Student fixtures validate | 2 records, unique IDs, references resolve, enrolled terms equal Fall 2026, no completed/enrolled conflict | ✅ |
| Validator fails closed on bad data | A deliberately corrupted copy produced 6 expected failures (bad prerequisite, unsupported rule, out-of-bounds `count`, duplicate ID, completed∩enrolled overlap, wrong enrolment term) | ✅ |
| Quality gates green | `ruff` clean, `mypy` clean (14 files), `pytest` 17 passed | ✅ |
| Dataset report | `validate_datasets.py` → 38 passed, 0 warnings, 0 errors, 0 pending; `--require-complete` exits `0` | ✅ |

M0 deliberately stops at the data boundary. It contains **no** prerequisite engine, no
PDF ingestion, no API, and no cloud resources — those are M1–M6.

## Quick start

```bash
uv sync --all-groups          # creates .venv with Python 3.12
cp .env.example .env          # placeholders only; safe for local development
make validate                 # 38 checks against the supplied fixtures
make check                    # lint + typecheck + tests
```

`make validate` exits `0` when the data is valid, `1` on validation errors, and
`make validate-strict` additionally exits `2` if any expected input is missing.

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
- `policies.in_progress_prerequisites` is currently a human-readable sentence. M1 must
  convert it into an explicit typed rule — a catalogue string is documentation, not an
  executable policy.

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

## Next: M1 — deterministic domain core

Scope is fixed and needs no model provider, database, or UI:

1. Canonical Pydantic models: `Course`, `Program`, `RequirementGroup`, `AcademicPolicy`,
   `Student`, `ReadingDocument`.
2. Source adapters for the two supplied files, preserving the raw JSON and source version.
3. `AcademicPolicy` type that encodes the in-progress prerequisite rule explicitly.
4. Prerequisite evaluator: `completed ∪ in-progress` for the next term, never treating
   concurrently-planned courses as satisfying one another.
5. Term filter, completed/enrolled exclusion, and the 16-unit cap.
6. Degree progress per `all` / `choose` group with `satisfied | in_progress | remaining |
   unable_to_determine`.

Exit criteria are golden tests, fixed from the current fixtures:

| Student | Eligible Spring 2027 candidates | Notes |
|---|---|---|
| `student-001` | PHYS 110, MATH 150, PHYS 340, ENGL 130 | 12-unit core plan = 110 + 150 + 340; 8-unit plan = 110 + 150 with 340 deferred, not ineligible |
| `student-002` | PHYS 110, MATH 150, ENGL 130, HIST 210 | PHYS 340 must be **absent**: PHYS 230 is neither completed nor in progress |

PHYS 120 and PHYS 490 must never be recommended for Spring 2027, and HIST 250 / PHYS 230
are not Spring offerings.

## Open decisions

| Decision | Recommendation | Impact if deferred |
|---|---|---|
| Frontend: Gradio vs Next.js | Gradio over the FastAPI boundary (~1–2 days, swappable later) | Blocks M5 only |
| Infrastructure tier | Local-first now; single cheap stack (~$50/mo) after acceptance | Blocks M6 only |

See [`docs/decisions/0001-mvp-stack.md`](docs/decisions/0001-mvp-stack.md) and
[`infra/README.md`](infra/README.md).

## Known limitations

- All five readings are present and structurally validated, but **no reading has been
  ingested yet**, so the assistant cannot answer content questions or cite a page until
  M2.
- Only PHYS 230 has a completed visual preflight; the other four need their own.
- Degree progress is only as reliable as the supplied requirements JSON.
- No seats, timetable, instructor, or grade data exists in the fixtures and none will be
  invented.
- Suggestions will be candidates, not an official study plan or graduation audit.

## Security housekeeping

This directory is its own repository with **no remote**. The parent workspace
(`/mnt/c/Users/aziz_`) is an unrelated project whose `.git/config` contains a plaintext
GitHub token — rotate it and add this project as a clean, separate remote.
