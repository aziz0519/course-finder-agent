# M7 acceptance report

**Status:** local acceptance run completed; GitHub Actions rerun after this change is
pending. **Deployment boundary:** local/CI only. M6's no-AWS scope is unchanged:
no bootstrap, deploy, account-backed diff, ECR publish, AWS CLI call, or provisioning.

## Acceptance command

```bash
make acceptance
```

This selects the `acceptance` pytest marker. Acceptance tests are excluded from ordinary
`make test` / `make check`, so their run is visible and deliberate. The tests reuse the
real FastAPI TestClient setup and cover the HTTP boundary. The test requiring source PDFs
also carries the `corpus` marker and is skipped with an explicit reason on a clean
checkout; the remaining academic-data and role-scope scenarios still run.

## Local results

The local run with all five approved PDFs present completed **4 acceptance tests passed**.
The marked cases exercise:

| §14 area | Coverage |
|---|---|
| Tutoring and citations | Bohr reading response, citation round-trip, approved Figure 2 page/crop |
| Visual follow-up uncertainty | Ambiguous diagram requests clarification; unparsed equation on page 7 abstains |
| Planning and context | 12-unit plan followed by an 8-unit cap update in the same thread |
| Missing facts | Seat-availability question returns unsupported with no citations |
| Authorization | Adviser assignment checks, student ownership of thread/citations/assets, out-of-course document denial |
| Admin controls | Student ingestion denied; admin can queue ingestion |

The clean-checkout simulation completed **3 passed, 1 skipped**; the skip is explicitly
reported as “approved reading PDFs are not installed.” The baseline's
`--allow-missing-readings` path validates the conversation fixture and reports `PENDING`
instead of emitting fabricated metric values.

The existing corpus, security, and conversation regression suites remain part of the
ordinary test suite where appropriate. The acceptance run is a smoke suite, not a
replacement for those focused tests.

## M7 hardening checks

- **Adversarial source text:** synthetic PDF instructions are marked untrusted; tests
  verify retrieved document content cannot broaden course or document scope.
- **Request size:** API request bodies over 1 MiB are rejected with HTTP 413, including
  chunked bodies. Tests also check audit metadata excludes bearer tokens.
- **Model bounds:** the optional OpenAI composer is a single bounded attempt, with a
  12-second timeout, 450 completion-token cap, 12,000 evidence-character cap, and
  2,000-character question cap. No retry is performed.
- **Ingestion recovery:** existing idempotency, failed-version, and atomic active-version
  replacement regressions verify failed ingestion cannot displace the last good version.

## Quality baseline

See [M7 quality baseline](M7_QUALITY_BASELINE.md) and its machine-readable companion.
It runs the canonical, schema-validated `data/samples/test-conversations.json` through
the local parser/retriever and deterministic offline composer. Values are report-only.
The baseline is intentionally small and is not a statistically meaningful model-quality
or safety-accuracy claim.

| Metric | Local result |
|---|---:|
| Grounded answer rate | 2/2 (100%) |
| Citation correctness (text and visual citation round-trip) | 4/4 (100%) |
| Abstention quality | 2/2 (100%) |
| Planning correctness | 2/2 (100%) |
| Follow-up resolution | 2/2 (100%) |
| Access-control pass rate | 2/2 (100%) |

These denominators are small regression counts, not large evaluation samples. The
baseline records the exact fixture checksum and PDF hashes for reproducibility.

## Explicit limitations and deferred delivery

- Only 4 of 50 visual assets are approved. Full-resolution visual QA is incomplete for
  all five readings; formula-heavy regions, unreviewed tables/charts, and exact chart
  values remain gated.
- PHYS 230 / Critical mass and HIST 250 / Demon core remain fully quarantined from
  student-facing retrieval pending a reviewed safe-excerpt set.
- Live OpenAI quality, Cognito, PostgreSQL/RDS, S3 runtime storage, production identity,
  and AWS network/runtime behavior were not tested.
- M6's CI builds images without publishing them and synthesizes CDK without AWS calls.
  M7 preserves that boundary. First AWS deployment requires a separately approved
  milestone, account/Region, certificate/domain, runtime adapters, cost review, and
  deployment authorization.

## Reproduction

```bash
uv run python scripts/run_baseline.py       # full local baseline; requires all PDFs
uv run python scripts/run_baseline.py --allow-missing-readings
uv run pytest -m acceptance -q
uv run pytest -q                             # default suite excludes acceptance marker
```

On a clean checkout, the baseline command with `--allow-missing-readings` validates the
conversation fixture and reports `PENDING` rather than claiming a score. The CI
acceptance job runs non-corpus acceptance scenarios and reports the PDF-dependent test
as skipped/pending.
