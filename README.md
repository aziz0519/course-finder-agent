# Course Finder Agent — MVP

A student learning and course-planning assistant for the fixed Fall 2026 → Spring 2027
scenario. It answers questions from supplied course readings with page-level citations,
reports degree progress against the supplied BSc Physics requirements, and recommends
verified Spring 2027 candidates using deterministic eligibility rules.

**Everything factual comes from the supplied fixtures.** When a fact is absent, the
assistant says so instead of guessing.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M0** | Repo scaffold, typed settings, dataset contract, Phase 0 validator | **done** — awaiting supplied fixtures |
| M1 | Deterministic domain core: adapters, prerequisite eligibility, degree progress | next |
| M2 | Ingestion and course-scoped retrieval with page citations | |
| M3 | Conversation state, supervisor routing, tutor and planner | |
| M4 | API, local auth, RBAC and negative security tests | |
| M5 | UI (Gradio over the API is the recommendation; Next.js remains supported) | |
| M6 | Deployable demo (container + single CDK stack) | |
| M7 | Acceptance run, quality baseline, documentation | |

## Quick start

```bash
cd course-finder-agent
uv sync --all-groups          # creates .venv with Python 3.12
cp .env.example .env          # placeholders only; safe for local development
uv run python scripts/validate_datasets.py
uv run pytest
```

The validator exits `0` while inputs are still pending, `1` on validation errors, and
`2` when `--require-complete` is passed and files are missing.

## Supplying the data

Copy the supplied files in unchanged:

```text
data/samples/course-catalog.json          14 courses, 1 programme, 5 requirement groups
data/samples/student-records.json         student-001 and student-002
data/samples/course-materials/*.pdf       five catalogue-referenced readings
```

Then re-run the validator. Details and path conventions: [`data/README.md`](data/README.md).
PDFs are gitignored; presence and integrity are proven by
`data/manifests/course_readings_manifest.json`.

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
data/             fixtures, schemas, manifests, derived artefacts
scripts/          validate_datasets.py (Phase 0), ingest_datasets.py (M2)
infra/            AWS CDK v2 target and demo tiers
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

## Open decisions

| Decision | Recommendation | Impact if deferred |
|---|---|---|
| Frontend: Gradio vs Next.js | Gradio over the FastAPI boundary (~1–2 days, swappable later) | Blocks M5 only |
| Infrastructure tier | Local-first now; single cheap stack after acceptance | Blocks M6 only |
| Fixture provenance | You supply the original files | **Blocks M1** |

See [`docs/decisions/0001-mvp-stack.md`](docs/decisions/0001-mvp-stack.md) and
[`infra/README.md`](infra/README.md).

## Known limitations

- One of five readings is supplied, so four tutor regressions cannot pass yet, including
  the PHYS 350 Bohr-model follow-up.
- Degree progress is only as reliable as the supplied requirements JSON.
- No seats, timetable, instructor, or grade data exists in the fixtures and none will be
  invented.
- Suggestions are candidates, not an official study plan or graduation audit.

## Security housekeeping

This directory is scaffolded as its own repository with **no remote**. The parent
workspace (`/mnt/c/Users/aziz_`) is an unrelated project whose `.git/config` contains a
plaintext GitHub token — rotate it and add this project as a clean, separate remote.
