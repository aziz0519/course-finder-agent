# M3 conversation workflow — implementation baseline

M3 is now underway. The first implementation slice adds a framework-independent,
provider-neutral conversation workflow; it does not expose an HTTP route or authenticate
users (those remain M4).

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
- Operational nuclear-design requests are rejected before retrieval.
- End-to-end regressions for the 12-to-8-unit planning conversation and the PHYS 350
  prose → ambiguous diagram → Figure 2/page 4 conversation.

## Deliberate boundaries

- Tutor prose responses use approved source excerpts directly. A future configured
  answer-composer may improve readability, but it must retain claim-level citations and
  may not add model knowledge.
- No LangGraph dependency is required for this deterministic initial graph.
- `ReadingScope` is still supplied by a trusted caller. M4 must mint it from verified
  identity and authorization policy and expose owner-scoped API routes.
- No chain-of-thought, unrestricted SQL/filesystem access, PDF bytes, or page renders are
  placed in conversation state.

## Next M3 slices

1. Add a bounded model-provider answer composer with timeout/token/cost controls and a
   deterministic no-provider fallback.
2. Add richer follow-up reference resolution for named assets without weakening visual
   ambiguity checks.
3. Add trace records and recovery/concurrency tests around interrupted turns.
