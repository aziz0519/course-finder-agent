# M7 Quality Baseline

Generated: `2026-11-17T07:06:35.967818+00:00`

Offline deterministic baseline using the supplied conversation fixture,
local parser/retriever, and `OfflineAnswerComposer`. No model or AWS calls.
Metric values are report-only, not CI thresholds.

- Conversation fixture SHA-256: `347894375b4a0d7abfe435981a0471cf573a9e4b0c9a65ffe76154ca54c6b75c`
- PDF corpus: all five files present; SHA-256 values are in the machine-readable run output.

| Metric | Result |
|---|---:|
| Grounded answer rate | 2/2 (100.0%) |
| Citation correctness (round-trip) | 4/4 (100.0%) |
| Abstention quality | 2/2 (100.0%) |
| Planning correctness | 2/2 (100.0%) |
| Follow-up resolution | 2/2 (100.0%) |
| Access-control pass rate | 2/2 (100.0%) |

## Interpretation and limitations

- Grounding counts successful tutor turns with a citation; this small regression set is not a statistically representative accuracy estimate.
- Citation correctness resolves each citation against the active local reading version and checks title and 1-based PDF page.
- Planning and follow-up scores are checked against the canonical conversation fixture.
- Access control covers principal-scope and course-scope denial; HTTP role/assignment checks are covered by acceptance tests.
- Only 4/50 visual assets are approved; all five documents have incomplete full-resolution visual QA. PHYS 230 and HIST 250 remain quarantined. Unreviewed visual/formula evidence must continue to abstain.
- This is an offline-composer baseline, not a live model-quality result.

Regenerate with `uv run python scripts/run_baseline.py`. CI verifies the evaluator runs, but does not fail on metric values.
