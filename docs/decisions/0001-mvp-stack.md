# 0001 — Lightweight MVP stack

- **Status:** accepted for the MVP; two decisions remain open
- **Date:** 2026-11-13
- **Updated:** 2026-11-14 — fixture provenance resolved; parser decision clarified below.
- **Context:** AGENTS.md specifies a Next.js + FastAPI + LangGraph + PostgreSQL/pgvector
  + Docling + ECS/Cognito stack. The objective is a working MVP of the course finder,
  not a production platform. Several specified components are large dependencies that
  add days of work without changing any acceptance criterion.

## Decision

Build the MVP as a **modular Python monolith** with the framework-dependent parts kept
behind interfaces, and defer the heavy components until a milestone needs them.

| Area | AGENTS.md target | MVP decision | Preserved invariant |
|---|---|---|---|
| Frontend | Next.js App Router | Gradio mounted behind the FastAPI session (recommendation, pending approval) | The API remains the only system boundary; no component imports agent code directly |
| Orchestration | LangGraph | Explicit state graph (explicitly permitted by section 3) | Bounded routing, typed tools, resumable thread state |
| Database | PostgreSQL + pgvector | SQLite + FTS5 behind `Retriever`/`Embeddings` interfaces | Filters applied before ranking; provenance retained |
| PDF parsing | Docling + targeted VLM | PyMuPDF + pdfplumber behind `PdfParser` | Page coverage, crops, `equation_unparsed` abstention |
| Auth | Cognito | Local Argon2id + HttpOnly cookie adapter; Cognito verification adapter reserved | Server-enforced RBAC, deny by default |
| Infrastructure | 5 stacks, 3 services, private subnets + NAT | 1 stack, 1 task, public subnet, no NAT (~$50/mo) | Private data stores, least-privilege roles, no secrets in code |

## Why Gradio is acceptable

The acceptance criteria are conversation, citations, progress, and recommendations —
all of which exist in one authenticated workspace. Gradio's `Blocks` + `Chatbot` covers
that in roughly 200 lines, including streaming. The demo's authorization story does
**not** come from Gradio's own `auth=`, which is basic HTTP auth without roles; login is
handled by the FastAPI adapter and Gradio reads the server session. That keeps
"student-001 cannot read student-002" a server-side control rather than a UI illusion.

Gradio is not a production frontend. If the project continues past the MVP, the
replacement is a frontend rewrite against an unchanged API — which is exactly why the
API stays the boundary.

## Why Docling is deferred, not dropped

The preflight on `phys230-critical-mass.pdf` already showed PyMuPDF and pdfplumber
extract native text and tables. Docling is heavy, version-sensitive, and its value grows
with layout complexity we cannot assess until the other four PDFs arrive. Section 5.3.3
explicitly permits a displayed equation to be marked `equation_unparsed` with a retained
crop, so a simpler parser is a conforming MVP state rather than a shortcut around the
quality gate. `PdfParser` is the seam for swapping Docling in per document.

## Consequences

- Positive: an end-to-end demo in days rather than weeks; deterministic tests need no
  model key, no vector database, and no AWS account.
- Positive: each deferred component has a named interface, so adoption is a swap, not a
  rewrite.
- Negative: SQLite will not carry concurrent multi-user load; that limit must be
  documented and reached only after the demo.
- Negative: PyMuPDF may under-recover formulas and dense tables; those cases must
  abstain loudly rather than degrade silently.

## Open decisions

1. **Frontend:** Gradio (recommended), Next.js, or FastAPI + Jinja/HTMX. Blocks M5 only.
2. **Infrastructure tier:** local-first (recommended) or the tier-1 demo stack. Blocks M6.

## Resolved

- **Fixture provenance (2026-11-14):** the authoritative JSON fixtures and all five PDFs
  are now present. Checksums and page counts are recorded in
  `data/manifests/course_readings_manifest.json` and enforced by
  `scripts/validate_datasets.py`.
- **Parser scope (2026-11-14):** M2 implements `PdfParser` with PyMuPDF + pdfplumber as
  described above. Docling is not installed for the MVP; it remains a documented
  per-document swap-in and does not change the M2 quality gates.

## Revisit when

- More than one concurrent writer needs the database.
- Real multi-tenant authentication is required.
- Any of the other four readings defeats the simple parser during its M2 preflight.
