# M5 — Gradio interface

M5 is a local demonstration UI over the authenticated M4 API. It is not a production
frontend: it holds one opaque session per browser session, has no multi-tenant
hardening, and does not remove or weaken any server-side authorization check.

## Run

```bash
uv sync --all-groups
cp .env.example .env          # set LOCAL_DEV_PASSWORD to a disposable local password
uv run uvicorn app.main:app --app-dir backend --reload
```

In a second terminal:

```bash
uv run python -m ui.app       # or: make ui
```

- API: `http://127.0.0.1:8000` (`/api/v1/docs` for OpenAPI)
- UI: `http://127.0.0.1:7860`
- `COURSE_FINDER_API_URL` overrides the API base URL; `UI_HOST`/`UI_PORT` change the
  bind address.

Sign in with the configured `LOCAL_DEV_PASSWORD` and one of `student-001`,
`student-002`, `adviser-001`, `adviser-002`, or `admin`.

## Visual design

The interface is deliberately minimal: white background, no dark mode, and two brand
colors.

| Token | Value | Applied to |
|---|---|---|
| Navy | `#001E60` | Headings, tab labels/selection, secondary buttons, links, slider track labels, structure |
| Red | `#DA291C` | Primary buttons, slider handle/fill, selected checkboxes, accent border, active tab underline |
| White | `#ffffff` | Body, panels, blocks, tables, inputs |

Gradio switches to a dark palette when the browser prefers dark, and its defaults put
near-black table text (`#1f2430`) on near-black rows (`#0a0f1e`, contrast 1.2:1). Because
this app is white-only, `ui/app.py::_theme()` pins the `*_dark` counterpart of every
styled property to the same light value, and `CSS` additionally pins the `--table-*`
variables under `body.dark`. A unit test computes WCAG contrast for table text against
both row fills in both modes (must stay ≥ 4.5:1) and asserts the dark values match the
light palette.

The username and password fields use white text on a navy `#001E60` fill with a red focus
border; white text on the white page background would be unreadable, so the fill is part
of that rule.

A 6px navy-to-red rule sits under the page title. The theme is defined in
`ui/app.py::_theme()` and the small structural CSS in `ui/app.py::CSS`. Gradio 6 takes
`theme` and `css` at `launch()`, not at `Blocks(...)`.

## Screens

### Student

| Screen | Behavior |
|---|---|
| Chat | Sends a turn to the supervisor; renders answer text plus a status note. “New conversation” starts a fresh server thread. |
| Citations | Dropdown of structured citations from this conversation. Selecting one shows the excerpt, source metadata, a rendered PDF page image, and an approved visual crop when present. |
| My courses | Current Fall 2026 enrolments and each mapped reading's page count, approved-visual count, and availability. |
| Degree progress | Requirement groups with `satisfied`, `in progress`, `remaining`, or `unable to determine` states. Completed and in-progress members are shown separately. |
| Spring 2027 | Unit-cap slider (4–16), deterministic recommendation table with explanations, deferred courses, and alternatives. |

### Adviser

Assigned-student dropdown comes from `GET /advisers/students`, which filters by the
authenticated adviser's assignment. Selecting a student shows read-only progress and a
plan. Chat is student-only, so the adviser view says so explicitly rather than relying
on a hidden control.

### Admin

“Validate and ingest” starts the local ingestion job; “Refresh status” shows the
current job report. Jobs are in-process and disappear on API restart.

## Demo script

1. Sign in as `student-001`.
2. **Chat:** “How does the Bohr model explain the lines in the hydrogen spectrum?”
   The answer cites the supplied Bohr reading.
3. **Chat:** “According to the diagram in that reading, how many electrons can the
   second energy level hold?” The tutor asks for clarification.
4. **Chat:** “I mean Figure 2…” The answer reports the source label (up to 8 electrons)
   and cites PDF page 4. Select that citation to see the page render and approved crop.
5. **Spring 2027:** build a 12-unit plan (PHYS 110 + MATH 150 + PHYS 340), then set the
   slider to 8 and rebuild (PHYS 110 + MATH 150). PHYS 340 moves to deferred, not
   ineligible.
6. **Chat:** “Are there seats available for Spring 2027 courses?” The UI shows the
   explicit unsupported-data response and no citations.
7. Sign in as `adviser-001` and confirm only `student-001` is listed.
8. Sign in as `admin`, run ingestion, and refresh the job.

## Safety and authorization behavior

- The UI never imports backend services; all data comes over HTTP with the session
  cookie and CSRF token.
- A page render is served only when that document is already cited in the conversation,
  is inside the student's current-course scope, is the active ingestion version, and the
  page is not classified as restricted.
- Visual crops are served only when the asset is approved and its checksum matches.
- Unapproved visuals and restricted pages produce a note, not an image.
- Source excerpts and model text are HTML-escaped before Markdown rendering.
- Sign-in and sign-out reset every user-specific panel — chat transcript, thread ID,
  citations, page and crop images, plans, adviser selection, and ingestion job state —
  so one browser tab can never display the previous user's data after a switch.
- A failed sign-in clears those panels too and reports invalid credentials rather than
  a session-expiry message.
- Sign-out revokes the server session; an expired/invalid session surfaces as a
  “sign in again” message on the next action.

## API additions made for M5

| Endpoint | Purpose |
|---|---|
| `GET /students/me/materials` | Course + reading metadata with ingestion/review state |
| `GET /advisers/students` | Students assigned to the authenticated adviser |
| `GET /chat/sessions/{thread_id}/documents/{document_id}/pages/{page_number}` | Rendered page for a document already cited in that conversation |

## Tests

```bash
uv run pytest backend/tests/unit/test_ui_presenters.py \
  backend/tests/unit/test_ui_app.py \
  backend/tests/integration/test_ui_controller.py -q
```

- `test_ui_presenters.py` — pure formatting: escaping, status notes, progress/materials
  rows, plan output, citation labels, error messages, ingestion report rendering.
- `test_ui_controller.py` — starts the real API under Uvicorn and drives `ui.api_client`
  over HTTP: login, dashboard data, 12→8 cap recomputation, owner isolation, adviser
  assignment, admin gating, citation/page/asset retrieval, invalid session. It also calls
  the Gradio handlers directly to prove sign-in/sign-out reset every user-specific
  component and that a failed login reports credentials without leaving stale panels.
- `test_ui_app.py` — headless Gradio build check (component inventory and brand tokens).

Not covered: browser automation, visual regression, screen-reader behavior, live OpenAI
answers, Cognito, and multi-user load. Those remain explicit gaps rather than implied
passes.

## Known UI limitations

- Adviser chat is unavailable (API is student-scoped for conversations).
- Conversation history is not listed in the UI, although the API supports it.
- Responses are not streamed.
- The reader shows a page image, not a scrollable PDF with text selection.
- Gradio state is per browser session and in memory; restarting the UI signs everyone
  out, and restarting the API invalidates local sessions.
- Because the UI calls the API server-side, the API's per-IP login limiter sees the UI
  host as the client: repeated failed sign-ins throttle UI sign-in as a whole, not just
  one browser.
