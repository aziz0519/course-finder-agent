# M4 local API demo

M4 is scoped to a local authenticated demo. Cognito sign-in/callback, AWS deployment,
and production identity are intentionally not acceptance-tested in this milestone.

## Start locally

```bash
uv sync --all-groups
cp .env.example .env
```

Set `LOCAL_DEV_PASSWORD` in `.env` to a private disposable demo password before starting.
The same password is used for the seeded local identities; the username selects the
identity and role:

| Username | Role | Academic scope |
|---|---|---|
| `student-001` | student | Own supplied record |
| `student-002` | student | Own supplied record |
| `adviser-001` | adviser | Assigned `student-001` only |
| `adviser-002` | adviser | Assigned `student-002` only |
| `admin` | admin | Dataset ingestion and operational reports |

This is a local demonstration adapter, not a university identity system. Do not expose
the development server to an untrusted network. Passwords are Argon2id-hashed in memory;
opaque sessions are HTTP-only, expire, and are revoked on logout. Restarting the API
invalidates local sessions. Mutating requests require the CSRF token returned by login.

Run the API from the repository root:

```bash
uv run uvicorn app.main:app --app-dir backend --reload
```

OpenAPI is available at <http://127.0.0.1:8000/api/v1/docs>.

## Initialize the local reading index

After logging in as `admin`, use the returned `csrf_token` as `X-CSRF-Token`:

```http
POST /api/v1/admin/ingestions
Content-Type: application/json
X-CSRF-Token: <csrf_token>

{}
```

Poll `GET /api/v1/admin/ingestions/{job_id}` until the state is `completed`. The local
job validates the source dataset and checksum-bound QA manifest, then idempotently
ingests each supplied reading into the local processed directory. Job state is
in-process and is lost if the server restarts; this is not a durable worker queue.

## Demo flows

### Student summary and planning

- `GET /api/v1/students/me`
- `GET /api/v1/students/me/progress`
- `GET /api/v1/academic-plan?term=Spring%202027&unit_cap=12`
- Start a chat with `POST /api/v1/chat/sessions`, then send messages to
  `POST /api/v1/chat/sessions/{thread_id}/messages`.
- Ask for the 12-unit plan, then follow up with “cap me at 8 units”. The thread retains
  the request cap and recomputes; the catalogue's 16-unit rule is unchanged.

### PHYS 350 tutoring

Ask how the Bohr model explains hydrogen spectral lines, then ask about “the diagram”.
The tutor should ask which visual when ambiguous. Specify Figure 2; the approved source
label on PDF page 4 supports the second-level capacity answer. Responses carry structured
citation IDs. Resolve a text citation with
`GET /api/v1/chat/sessions/{thread_id}/citations/{chunk_id}` or retrieve a previously
cited, approved crop with
`GET /api/v1/chat/sessions/{thread_id}/assets/{asset_id}`. Both endpoints check thread
ownership, active student course scope, and citation provenance.

The visual inventory is not fully reviewed. Unapproved visuals remain unavailable;
the API must not treat the presence of an asset as evidence that it is approved.

## OpenAI answer composition (optional)

The deterministic offline composer is the default and requires no API key. Once a key is
available, configure only your local `.env`:

```dotenv
MODEL_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=your-local-key
```

The key is loaded as a secret setting, sent only to the OpenAI API, and is never included
in API responses or application logs. Requests have a bounded timeout, evidence input,
and completion size, with no automatic retries. Output is schema-validated and every
claim must refer to returned evidence; provider or validation failures fail closed. This
is evidence-linked composition, not a guarantee that a model paraphrase is perfectly
entailed by its citation. Keep `MODEL_PROVIDER=offline` for deterministic tests.

Never commit `.env` or place an API key in frontend code, logs, fixtures, or screenshots.

## Endpoint inventory

All routes use `/api/v1`:

- `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`
- `GET /students/me`, `GET /students/me/progress`
- `GET /advisers/students/{student_id}`
- `GET /courses`, `GET /courses/{course_id}`
- `GET /academic-plan`
- `POST /chat/sessions`, `GET /chat/sessions`,
  `GET /chat/sessions/{thread_id}`,
  `POST /chat/sessions/{thread_id}/messages`
- `GET /chat/sessions/{thread_id}/citations/{chunk_id}`
- `GET /chat/sessions/{thread_id}/assets/{asset_id}`
- `POST /admin/ingestions`, `GET /admin/ingestions/{job_id}`

`GET /auth/callback` is intentionally unimplemented. Cognito/JWT support is a future
adapter seam and is not part of the local demo's test gate.

## Verification

```bash
make check
uv run pytest backend/tests/integration/test_api_v1.py -q
```

Latest repository-wide run: Ruff passes; mypy passes across **81 source files**;
**215 tests pass**; strict dataset validation reports **62 passed, 0 warnings, 0 errors,
0 pending**. The tests do not call OpenAI or Cognito.

The local API tests cover login failure/rate limiting, logout revocation, CSRF,
student/adviser/admin roles, owner isolation, the planner cap follow-up, and the approved
PHYS 350 Figure 2 citation/asset flow. Redacted audit events record route templates,
verified actor IDs, role, status, and outcome only; request bodies, prompts, and retrieved
passages are excluded. OpenAI tests use a mocked HTTP transport; no real key or network
call is needed.
