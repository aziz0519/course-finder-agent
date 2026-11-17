# M6 — Container CI and browser smoke tests

M6 P0 now has two independent, local-only quality surfaces:

1. The CDK v2 application synthesizes the target AWS topology and its assertion tests
   inspect the generated CloudFormation. No AWS API is contacted.
2. GitHub Actions builds the API, Gradio UI, and ingestion-worker images, starts the API
   and UI locally, and runs a small Playwright journey through the real HTTP boundary.

**Out of scope and deliberately absent:** `cdk bootstrap`, `cdk deploy`, `cdk destroy`,
account-backed `cdk diff`, AWS CLI calls, ECR login/push, and any provisioning. The
workflow also contains a scope guard (`scripts/check_ci_scope.sh`) that fails if an
AWS/ECR deployment step is added.

## Workflow jobs

| Job | What it does | What it does not do |
|---|---|---|
| `quality` | Locked `uv sync`, Ruff, mypy, pytest, fixture validation, local `cdk synth` | Contact AWS or read the untracked PDFs |
| `docker-images` | Builds the `api`, `ui`, and `worker` targets with BuildKit cache | Logs in to a registry or pushes an image |
| `e2e` | Starts Compose, waits for UI readiness, runs Playwright | Deploys to ECS, RDS, S3, or Cognito |

The image build job uses `docker/build-push-action` with `push: false`. The E2E job
builds the same targets through Compose, so a broken Dockerfile cannot be hidden by a
separate test path.

## Container topology

`Dockerfile` has three targets that share a Python 3.12 base and a non-root runtime user:

| Target | Command | Purpose |
|---|---|---|
| `api` | `uvicorn app.main:app` on port 8000 | Authenticated FastAPI service |
| `ui` | `python -m ui.app` on port 7860 | Gradio UI calling the API over HTTP |
| `worker` | `python scripts/ingest_datasets.py` | On-demand ingestion job; no service |

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:c7055910f253a6a5240daf6abae0c081e4d813d82db17cad5ee8a0657768e030 -->

`compose.yaml` starts only `api` and `ui` by default. The worker is behind the
`ingestion` profile and mounts the local `data/samples/course-materials` directory
read-only. PDFs are not baked into images. `make images` activates the ingestion
profile to build all three images.

<!-- /coderabbit-ai-generated:v1 -->

## Readiness and E2E coverage

The UI healthcheck waits for `http://127.0.0.1:7860/`; the API healthcheck uses
`/health`. `scripts/wait_for_ui.sh` provides a bounded wait before Playwright starts.

The browser suite (`e2e/test_ui_e2e.py`) covers:

- `student-001` sign-in and dashboard rendering.
- The Spring 2027 planner at 12 units, then an 8-unit cap recomputation.
- Sign-out clearing the student workspace.
- `adviser-001` seeing only `student-001`.
- Switching to `student-002` without leaking the adviser or prior student view.

The suite is intentionally small: it proves that the built containers, local auth,
session cookie, CSRF handling, and UI-to-API path work together. It is not a visual
regression suite and does not test live OpenAI, Cognito, PostgreSQL, or AWS networking.

## Reading-corpus boundary

The five supplied PDFs are gitignored. A clean checkout therefore does not contain the
corpus, and tests that need real PDF bytes are marked `corpus`. `backend/tests/conftest.py`
skips those tests when any expected PDF is missing; synthetic-PDF tests still run.

This means the workflow's `62 passed, 0 pending` strict dataset check cannot run on a
clean checkout. CI runs `scripts/validate_datasets.py --allow-missing-readings`, which
validates the JSON, schemas, references, and manifest while reporting the PDFs as
pending. The flag is explicit and only relaxes the manifest's stale `present` status;
all other validation remains fail-closed. To run the full corpus suite locally:

```bash
# Place the five approved PDFs in data/samples/course-materials/
uv run python scripts/validate_datasets.py --require-complete
uv run pytest
uv run python scripts/ingest_datasets.py
```

Do not commit the PDFs or replace them with fabricated substitutes merely to make CI
look complete.

## Local commands

```bash
# Build all three images without pushing
make images

# Start API + UI, wait for readiness, and run the browser suite
make e2e-up
make e2e

# Or run the suite directly against a UI you started yourself
E2E_UI_URL=http://127.0.0.1:7860 \
E2E_PASSWORD="$LOCAL_DEV_PASSWORD" \
uv run pytest e2e -q

# Stop and remove the local containers/volumes
make e2e-down
```

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:bea41565cbcc3d08c9a72b0e86624c4c55d2bc45fe133bb6a4cec29c2043d5c2 -->

Before starting Compose, copy `.env.example` to `.env` and replace
`LOCAL_DEV_PASSWORD`, `SESSION_SECRET`, and `CSRF_SECRET` with disposable local
values. The Compose defaults are rejected placeholders: login is disabled until a
password is configured, and production rejects the placeholder secrets.
`E2E_PASSWORD` must match the API's `LOCAL_DEV_PASSWORD`; CI supplies its local
values explicitly.

<!-- /coderabbit-ai-generated:v1 -->

## Verification status

Validated without Docker in this repository:

- Ruff, mypy, and the full Python suite (including corpus regressions).
- `scripts/check_ci_scope.sh`, workflow YAML parsing, and Compose YAML parsing.
- `scripts/validate_datasets.py --allow-missing-readings` against a simulated clean
  checkout with the PDFs removed, plus the default suite with `corpus` tests skipped.
- The Playwright suite, run against a natively started API and Gradio UI
  (`E2E_UI_URL=http://127.0.0.1:7860 E2E_PASSWORD=... uv run pytest e2e -q`).

Not validated here: Docker Engine is unavailable in this WSL installation, so the
image builds, Compose startup, and the containerised E2E job must be proven by GitHub
Actions or another Docker-enabled machine. Gradio renders only the active panel, so the
browser suite targets the visible slider/combobox roles explicitly.

No live deployment validation is included in M6 P0.
