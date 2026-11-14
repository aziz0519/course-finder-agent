# M3 conversation workflow

M3 is complete. It provides a framework-independent, provider-neutral conversation
workflow; it does not expose an HTTP route or authenticate users (those remain M4).

## Implemented

- Compact, typed conversation checkpoints containing intent, planning preferences, and
  source IDs—never student snapshots, retrieved passages, or restricted content.
- SQLite development persistence with server-generated thread/message IDs, owner-scoped
  reads, and atomic user-message/assistant-message/checkpoint writes.
- Bounded supervisor routing to tutor, planner, or unsupported-response paths.
- Fresh loading of the authoritative student and catalogue fixtures on every turn.
- Planner follow-ups that persist and recompute a request-specific unit cap without
  mutating the catalogue's 16-unit policy.
- Tutor course/reading resolution, exact-title precedence, page-level citations,
  visual clarification, approved-asset retrieval, and transparent abstention.
- A provider-neutral answer-composer contract and deterministic offline implementation.
  The offline composer selects at most three relevant source sentences and never adds
  model knowledge. Invalid composer evidence references fail closed.
- Named visual resolution, so a follow-up can select an approved `Figure 2` without
  requiring the user to repeat its page number.
- Operational nuclear-design requests are rejected before retrieval.
- Redacted supervisor/specialist traces with public trace IDs; prompts, passages, and
  chain-of-thought are not trace metadata.
- Atomic turn persistence, rollback after interrupted writes, and optimistic revision
  checks that reject stale concurrent checkpoints.
- Planner provenance identifies the exact catalogue and student-record source versions.
- End-to-end regressions for the 12-to-8-unit planning conversation and the PHYS 350
  prose → ambiguous diagram → Figure 2/page 4 conversation.

## Deliberate boundaries

- Tutor prose responses use the deterministic offline composer. A future network-backed
  composer must retain claim-level citations and add timeouts, retry/token/cost limits,
  and redacted logs before it can be configured.
- No LangGraph dependency is required for this deterministic initial graph.
- `ReadingScope` is still supplied by a trusted caller. M4 must mint it from verified
  identity and authorization policy and expose owner-scoped API routes.
- No chain-of-thought, unrestricted SQL/filesystem access, PDF bytes, or page renders are
  placed in conversation state.

## Exit gate

- The canonical planning thread recomputes 12 units to 8 units and retains the updated
  preference without mutating source data.
- The canonical Bohr thread retrieves prose, asks for clarification when a diagram is
  ambiguous, and resolves approved Figure 2 with a page-level citation.
- Owner checks, stale writes, interrupted writes, trace persistence, restricted requests,
  and invalid source references have deterministic tests.
- Current verification: Ruff and mypy pass; `pytest` passes 193 tests.
