"""M5 Gradio demo UI over the authenticated local API.

The UI holds only an opaque session cookie and CSRF token; every action calls the
HTTP API, so authorization is enforced server-side exactly as in M4.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Any

import gradio as gr
from PIL import Image

from ui import presenters
from ui.api_client import DEFAULT_TERM, ApiClient, ApiError, SessionState

NAVY = "#001E60"
RED = "#DA291C"

CSS = """
.gradio-container { background: #ffffff !important; max-width: 1180px; margin: 0 auto; }
body, .gradio-container, .dark .gradio-container { background: #ffffff !important; }
#brand-rule {
  height: 6px; border-radius: 3px; margin: 0 0 16px 0;
  background: linear-gradient(90deg, #001E60 0%, #001E60 62%, #DA291C 62%, #DA291C 100%);
}
h1, h2, h3 { color: #001E60 !important; }
[role="tab"] { color: #001E60 !important; }
[role="tab"][aria-selected="true"] {
  color: #001E60 !important;
  border-bottom: 3px solid #DA291C !important;
}
button.primary { background: #DA291C !important; border-color: #DA291C !important; }

/* Login text fields: white text on the navy fill, since white-on-white is unreadable. */
.login-field input,
.login-field textarea {
  background: #001E60 !important;
  color: #ffffff !important;
  caret-color: #ffffff !important;
  border-color: #001E60 !important;
}
.login-field input::placeholder,
.login-field textarea::placeholder { color: #c9d1e6 !important; }
.login-field label { color: #001E60 !important; }
.login-field input:focus,
.login-field textarea:focus { border-color: #DA291C !important; }

/* Gradio re-applies its dark variable set from the browser preference; pin the
   table variables so rows can never render dark text on a dark fill. */
html.dark, body.dark, .dark .gradio-container {
  --table-even-background-fill: #ffffff !important;
  --table-odd-background-fill: #f7f9fd !important;
  --table-border-color: #dbe2f0 !important;
  --table-text-color: #1f2430 !important;
  --table-row-focus: #fdeeec !important;
}
footer { display: none !important; }
"""


def _theme() -> gr.themes.Base:
    navy = gr.themes.Color(
        name="course-navy",
        c50="#eef1f8",
        c100="#d5dced",
        c200="#aab7d9",
        c300="#7f92c4",
        c400="#546daf",
        c500=NAVY,
        c600="#001a53",
        c700="#001545",
        c800="#001037",
        c900="#000b29",
        c950="#00061c",
    )
    red = gr.themes.Color(
        name="course-red",
        c50="#fdeeec",
        c100="#fad7d3",
        c200="#f3afa8",
        c300="#ec877c",
        c400="#e55f51",
        c500=RED,
        c600="#b52318",
        c700="#911c13",
        c800="#6d150e",
        c900="#490e09",
        c950="#240704",
    )
    # The app is intentionally light-only. Gradio swaps in a dark palette when the
    # browser prefers dark, and its table defaults put near-black text (#1f2430) on
    # near-black rows (#0a0f1e). Every property the UI styles is therefore pinned in
    # both modes to the same light values.
    return gr.themes.Base(
        primary_hue=navy,
        secondary_hue=red,
        neutral_hue="slate",
    ).set(
        body_background_fill="#ffffff",
        body_background_fill_dark="#ffffff",
        background_fill_primary="#ffffff",
        background_fill_primary_dark="#ffffff",
        background_fill_secondary="#ffffff",
        background_fill_secondary_dark="#ffffff",
        block_background_fill="#ffffff",
        block_background_fill_dark="#ffffff",
        panel_background_fill="#ffffff",
        panel_background_fill_dark="#ffffff",
        body_text_color="#1f2430",
        body_text_color_dark="#1f2430",
        body_text_color_subdued="#5b6478",
        body_text_color_subdued_dark="#5b6478",
        color_accent=RED,
        color_accent_soft="#fdeeec",
        color_accent_soft_dark="#fdeeec",
        border_color_primary="#dbe2f0",
        border_color_primary_dark="#dbe2f0",
        border_color_accent=NAVY,
        border_color_accent_dark=NAVY,
        link_text_color=NAVY,
        link_text_color_dark=NAVY,
        link_text_color_hover=RED,
        link_text_color_hover_dark=RED,
        link_text_color_active=RED,
        link_text_color_active_dark=RED,
        link_text_color_visited=NAVY,
        link_text_color_visited_dark=NAVY,
        button_primary_background_fill=RED,
        button_primary_background_fill_dark=RED,
        button_primary_background_fill_hover="#b52318",
        button_primary_background_fill_hover_dark="#b52318",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#ffffff",
        button_primary_border_color=RED,
        button_primary_border_color_dark=RED,
        button_secondary_background_fill="#ffffff",
        button_secondary_background_fill_dark="#ffffff",
        button_secondary_background_fill_hover="#f4f6fb",
        button_secondary_background_fill_hover_dark="#f4f6fb",
        button_secondary_text_color=NAVY,
        button_secondary_text_color_dark=NAVY,
        button_secondary_border_color=NAVY,
        button_secondary_border_color_dark=NAVY,
        slider_color=RED,
        slider_color_dark=RED,
        checkbox_background_color="#ffffff",
        checkbox_background_color_dark="#ffffff",
        checkbox_background_color_selected=RED,
        checkbox_background_color_selected_dark=RED,
        checkbox_border_color="#c9d1e6",
        checkbox_border_color_dark="#c9d1e6",
        checkbox_border_color_selected=RED,
        checkbox_border_color_selected_dark=RED,
        loader_color=RED,
        loader_color_dark=RED,
        input_background_fill="#ffffff",
        input_background_fill_dark="#ffffff",
        input_border_color="#c9d1e6",
        input_border_color_dark="#c9d1e6",
        input_border_color_focus=NAVY,
        input_border_color_focus_dark=NAVY,
        input_placeholder_color="#7a8398",
        input_placeholder_color_dark="#7a8398",
        code_background_fill="#eef1f8",
        code_background_fill_dark="#eef1f8",
        block_label_text_color="#5b6478",
        block_label_text_color_dark="#5b6478",
        block_title_text_color="#5b6478",
        block_title_text_color_dark="#5b6478",
        table_even_background_fill="#ffffff",
        table_even_background_fill_dark="#ffffff",
        table_odd_background_fill="#f7f9fd",
        table_odd_background_fill_dark="#f7f9fd",
        table_border_color="#dbe2f0",
        table_border_color_dark="#dbe2f0",
        table_text_color="#1f2430",
        table_text_color_dark="#1f2430",
        table_row_focus="#fdeeec",
        table_row_focus_dark="#fdeeec",
        error_text_color="#b91c1c",
        error_text_color_dark="#b91c1c",
        error_border_color="#b91c1c",
        error_border_color_dark="#b91c1c",
        error_icon_color="#b91c1c",
        error_icon_color_dark="#b91c1c",
        error_background_fill="#fef2f2",
        error_background_fill_dark="#fef2f2",
    )


def _client(state: SessionState | None) -> ApiClient:
    if state is None:
        raise gr.Error("Sign in to continue.")
    return ApiClient.from_session(state)


def _png(payload: bytes) -> Image.Image:
    with Image.open(io.BytesIO(payload)) as image:
        return image.convert("RGB")


def _history(history: Iterable[Any] | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in history or ():
        if isinstance(item, Mapping):
            messages.append(
                {"role": str(item.get("role", "assistant")), "content": item.get("content", "")}
            )
        else:
            messages.append(
                {
                    "role": getattr(item, "role", "assistant"),
                    "content": getattr(item, "content", ""),
                }
            )
    return messages


CITATION_HINT = "Citations appear here after the tutor answers from a reading."


def _panel_values() -> dict[str, Any]:
    """Fresh values for every user-specific component, keyed by output name."""

    return {
        "welcome": "",
        "profile": "",
        "current_courses": [],
        "progress": [],
        "materials": [],
        "chatbot": [],
        "thread_id": "",
        "citations": [],
        "citation_picker": gr.update(choices=[], value=None),
        "citation_detail": CITATION_HINT,
        "page_view": None,
        "asset_view": None,
        "message": "",
        "adviser_students": gr.update(choices=[], value=None),
        "adviser_profile": "",
        "adviser_progress": [],
        "plan_summary": "",
        "plan_table": [],
        "plan_notes": "",
        "adviser_plan_summary": "",
        "adviser_plan_table": [],
        "adviser_plan_notes": "",
        "job_id": "",
        "job_output": "",
        "password": "",
    }


# Single source of output order: the panels dict in ``build_ui`` and the tuples
# returned by ``_login``/``_logout`` both follow this key order.
PANEL_RESET_KEYS = tuple(_panel_values())


def _auth_result(state: SessionState | None, error: str = "") -> tuple[Any, ...]:
    """Auth controls followed by a full reset of every user-specific panel.

    Both sign-in and sign-out pass through here, so one browser tab can never keep
    showing a previous user's transcript, citations, previews, plans, or adviser data.
    """

    panels = _panel_values()
    return (
        state,
        gr.update(visible=state is None),
        gr.update(visible=bool(state and state.role == "student")),
        gr.update(visible=bool(state and state.role == "adviser")),
        gr.update(visible=bool(state and state.role == "admin")),
        error,
        *(panels[key] for key in PANEL_RESET_KEYS),
    )


def _login(username: str, password: str) -> tuple[Any, ...]:
    if not (username or "").strip() or not password:
        return _auth_result(None, "Enter a username and password.")
    try:
        state = ApiClient().login(username.strip(), password)
    except ApiError as exc:
        error = (
            "Incorrect username or password."
            if exc.status_code in (401, 403)
            else presenters.error_text(exc)
        )
        return _auth_result(None, error)
    return _auth_result(state)


def _logout(state: SessionState | None) -> tuple[Any, ...]:
    if state is not None:
        with suppress(ApiError):
            ApiClient.from_session(state).logout()
    return _auth_result(None)


def _student_dashboard(state: SessionState | None) -> tuple[Any, ...]:
    if state is None or state.role != "student":
        return ("", "", [], [], [])
    try:
        client = ApiClient.from_session(state)
        profile = client.profile()
        progress = client.progress()
        materials = client.materials()
    except ApiError as exc:
        note = presenters.error_text(exc)
        return (note, "", [], [], [])
    welcome = (
        f"### Welcome, {presenters.escape(profile.get('student_id', ''))}\n"
        f"Signed in as **student** · scenario term **Fall 2026** → planning for "
        f"**{DEFAULT_TERM}**"
    )
    return (
        welcome,
        presenters.profile_markdown(profile),
        presenters.course_rows(profile),
        presenters.progress_rows(progress),
        presenters.materials_rows(materials),
    )


def _adviser_panel(state: SessionState | None) -> tuple[Any, ...]:
    if state is None or state.role != "adviser":
        return (gr.update(choices=[], value=None), "", [])
    try:
        students = ApiClient.from_session(state).assigned_students()
    except ApiError as exc:
        return (gr.update(choices=[], value=None), presenters.error_text(exc), [])
    choices = [
        (f"{item['student_id']} — {item.get('academic_level', '')}", item["student_id"])
        for item in students
    ]
    if not choices:
        return (gr.update(choices=[], value=None), "No students are assigned.", [])
    selected = choices[0][1]
    profile, rows = _adviser_detail(selected, state)
    return (gr.update(choices=choices, value=selected), profile, rows)


def _adviser_detail(
    student_id: str | None,
    state: SessionState | None,
) -> tuple[str, list[list[str]]]:
    if not student_id or state is None:
        return ("", [])
    try:
        payload = ApiClient.from_session(state).assigned_student(student_id)
    except ApiError as exc:
        return (presenters.error_text(exc), [])
    return (
        presenters.profile_markdown(payload["student"])
        + "\n\n*Read-only adviser view. Student chat is not available to advisers.*",
        presenters.progress_rows(payload["progress"]),
    )


def _student_plan(cap: float, state: SessionState | None) -> tuple[str, list[list[str]], str]:
    try:
        response = _client(state).plan(unit_cap=int(cap))
    except ApiError as exc:
        return (presenters.error_text(exc), [], "")
    plan = response.get("plan", {})
    return (
        presenters.plan_overview(response),
        presenters.plan_rows(plan.get("recommended", ())),
        presenters.deferred_markdown(response),
    )


def _adviser_plan(
    student_id: str | None,
    cap: float,
    state: SessionState | None,
) -> tuple[str, list[list[str]], str]:
    if not student_id:
        return ("Select a student to build a plan.", [], "")
    try:
        response = _client(state).plan(unit_cap=int(cap), student_id=student_id)
    except ApiError as exc:
        return (presenters.error_text(exc), [], "")
    plan = response.get("plan", {})
    return (
        presenters.plan_overview(response),
        presenters.plan_rows(plan.get("recommended", ())),
        presenters.deferred_markdown(response),
    )


def _new_chat(state: SessionState | None) -> tuple[Any, ...]:
    try:
        thread_id = _client(state).create_thread()["thread_id"]
    except ApiError as exc:
        raise gr.Error(presenters.error_text(exc)) from exc
    return (
        [],
        thread_id,
        [],
        gr.update(choices=[], value=None),
        "",
        None,
        None,
        "",
    )


def _send(
    message: str,
    history: Iterable[Any] | None,
    state: SessionState | None,
    thread_id: str,
    citations: list[dict[str, Any]] | None,
) -> tuple[Any, ...]:
    text = (message or "").strip()
    messages = _history(history)
    if not text:
        return (
            messages,
            "",
            thread_id,
            citations or [],
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )
    if len(text) > 4000:
        raise gr.Error("Messages are limited to 4000 characters.")
    client = _client(state)
    try:
        if not thread_id:
            thread_id = client.create_thread()["thread_id"]
        response = client.send(thread_id, text)["response"]
    except ApiError as exc:
        raise gr.Error(presenters.error_text(exc)) from exc
    known = list(citations or ())
    known.extend(dict(item) for item in response.get("citations", ()))
    messages.append({"role": "user", "content": text})
    messages.append(
        {
            "role": "assistant",
            "content": presenters.assistant_content(
                response.get("text", ""), response.get("status", "ok")
            ),
        }
    )
    return (
        messages,
        "",
        thread_id,
        known,
        gr.update(choices=presenters.citation_choices(known), value=None),
        "",
        None,
        None,
    )


def _show_citation(
    index: int | None,
    citations: list[dict[str, Any]] | None,
    state: SessionState | None,
    thread_id: str,
) -> tuple[Any, ...]:
    if index is None or not citations:
        return ("Select a citation to see its source.", None, None)
    citation = citations[int(index)]
    client = _client(state)
    detail = ""
    page_image: Image.Image | None = None
    asset_image: Image.Image | None = None
    chunk_id = citation.get("chunk_id")
    if chunk_id:
        try:
            evidence = client.citation(thread_id, chunk_id)
            detail = presenters.citation_detail(evidence, citation)
        except ApiError as exc:
            detail = presenters.error_text(exc)
    else:
        detail = (
            f"**{presenters.escape(presenters.citation_label(citation))}**\n\n"
            "Visual citation."
        )
    try:
        page_image = _png(
            client.page_bytes(
                thread_id,
                citation["document_id"],
                int(citation["pdf_page_number"]),
            )
        )
    except (ApiError, KeyError, TypeError, ValueError):
        detail += "\n\n*The rendered page is withheld or unavailable.*"
    asset_id = citation.get("asset_id")
    if asset_id:
        try:
            asset_image = _png(client.asset_bytes(thread_id, asset_id))
        except ApiError:
            detail += "\n\n*The approved visual crop is unavailable.*"
    return (detail, page_image, asset_image)


def _start_ingestion(state: SessionState | None) -> tuple[str, str]:
    try:
        job = _client(state).start_ingestion()
    except ApiError as exc:
        return (presenters.error_text(exc), "")
    return (presenters.job_markdown(job), str(job.get("job_id", "")))


def _refresh_ingestion(job_id: str, state: SessionState | None) -> str:
    if not job_id:
        return "No ingestion job yet. Start one to validate and ingest the dataset."
    try:
        job = _client(state).ingestion(job_id)
    except ApiError as exc:
        return presenters.error_text(exc)
    return presenters.job_markdown(job)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Course Finder Agent") as demo:
        gr.HTML('<div id="brand-rule"></div>')
        gr.Markdown(
            "# Course Finder Agent\n"
            "Answers come only from the supplied readings and academic records. "
            "Unavailable facts are reported, never invented."
        )

        session = gr.State(None)
        thread_id = gr.State("")
        citations = gr.State([])
        job_id = gr.State("")

        with gr.Column(visible=True) as login_col:
            gr.Markdown("### Sign in")
            username = gr.Textbox(
                label="Username",
                placeholder="student-001",
                elem_classes=["login-field"],
            )
            password = gr.Textbox(
                label="Password",
                type="password",
                elem_classes=["login-field"],
            )
            login_button = gr.Button("Sign in", variant="primary")
            login_error = gr.Markdown()

        with gr.Column(visible=False) as student_col:
            welcome = gr.Markdown()
            with gr.Tabs():
                with gr.Tab("Chat"):
                    chatbot = gr.Chatbot(
                        label="Course tutor", height=380, show_label=False
                    )
                    with gr.Row():
                        message = gr.Textbox(
                            placeholder="Ask about your current readings…",
                            show_label=False,
                            scale=5,
                        )
                        send_button = gr.Button("Send", variant="primary", scale=1)
                    new_chat = gr.Button("New conversation", variant="secondary")
                    gr.Markdown("#### Citations")
                    citation_picker = gr.Dropdown(
                        label="Sources used in this conversation",
                        choices=[],
                        interactive=True,
                    )
                    citation_detail = gr.Markdown(CITATION_HINT)
                    with gr.Row():
                        page_view = gr.Image(
                            label="Cited PDF page",
                            type="pil",
                            interactive=False,
                            height=420,
                        )
                        asset_view = gr.Image(
                            label="Approved visual",
                            type="pil",
                            interactive=False,
                            height=420,
                        )
                with gr.Tab("My courses"):
                    current_courses = gr.Dataframe(
                        headers=["Course", "Term", "Status"],
                        datatype="str",
                        interactive=False,
                        wrap=True,
                    )
                    materials = gr.Dataframe(
                        headers=["Course", "Reading", "Pages", "Visual review", "Availability"],
                        datatype="str",
                        interactive=False,
                        wrap=True,
                    )
                with gr.Tab("Degree progress"):
                    profile = gr.Markdown()
                    progress = gr.Dataframe(
                        headers=[
                            "Requirement",
                            "State",
                            "Required",
                            "Completed",
                            "In progress",
                            "Still needed",
                        ],
                        datatype="str",
                        interactive=False,
                        wrap=True,
                    )
                with gr.Tab("Spring 2027"):
                    gr.Markdown(
                        "Deterministic candidates from the supplied snapshot. "
                        "Suggestions are not an official study plan."
                    )
                    with gr.Row():
                        cap = gr.Slider(
                            minimum=4,
                            maximum=16,
                            value=12,
                            step=4,
                            label="Unit cap",
                        )
                        plan_button = gr.Button("Build plan", variant="primary")
                    plan_summary = gr.Markdown()
                    plan_table = gr.Dataframe(
                        headers=["Course", "Title", "Units", "Why"],
                        datatype="str",
                        interactive=False,
                        wrap=True,
                    )
                    plan_notes = gr.Markdown()
            logout_button = gr.Button("Sign out", variant="secondary")

        with gr.Column(visible=False) as adviser_col:
            gr.Markdown(
                "### Adviser workspace\n"
                "Read-only access to assigned students. Every request is checked "
                "against the adviser assignment."
            )
            adviser_students = gr.Dropdown(
                label="Assigned students", choices=[], interactive=True
            )
            adviser_profile = gr.Markdown()
            adviser_progress = gr.Dataframe(
                headers=[
                    "Requirement",
                    "State",
                    "Required",
                    "Completed",
                    "In progress",
                    "Still needed",
                ],
                datatype="str",
                interactive=False,
                wrap=True,
            )
            with gr.Row():
                adviser_cap = gr.Slider(
                    minimum=4, maximum=16, value=12, step=4, label="Unit cap"
                )
                adviser_plan_button = gr.Button("Build plan", variant="primary")
            adviser_plan_summary = gr.Markdown()
            adviser_plan_table = gr.Dataframe(
                headers=["Course", "Title", "Units", "Why"],
                datatype="str",
                interactive=False,
                wrap=True,
            )
            adviser_plan_notes = gr.Markdown()
            adviser_logout = gr.Button("Sign out", variant="secondary")

        with gr.Column(visible=False) as admin_col:
            gr.Markdown(
                "### Admin ingestion\n"
                "Validates the dataset and ingests the supplied readings. "
                "Local job state is in-process and is lost on restart."
            )
            with gr.Row():
                ingest_button = gr.Button("Validate and ingest", variant="primary")
                refresh_button = gr.Button("Refresh status", variant="secondary")
            job_output = gr.Markdown()

        panels = {
            "welcome": welcome,
            "profile": profile,
            "current_courses": current_courses,
            "progress": progress,
            "materials": materials,
            "chatbot": chatbot,
            "thread_id": thread_id,
            "citations": citations,
            "citation_picker": citation_picker,
            "citation_detail": citation_detail,
            "page_view": page_view,
            "asset_view": asset_view,
            "message": message,
            "adviser_students": adviser_students,
            "adviser_profile": adviser_profile,
            "adviser_progress": adviser_progress,
            "plan_summary": plan_summary,
            "plan_table": plan_table,
            "plan_notes": plan_notes,
            "adviser_plan_summary": adviser_plan_summary,
            "adviser_plan_table": adviser_plan_table,
            "adviser_plan_notes": adviser_plan_notes,
            "job_id": job_id,
            "job_output": job_output,
            "password": password,
        }
        if set(panels) != set(PANEL_RESET_KEYS):
            raise RuntimeError("auth panel outputs and reset values are out of sync")
        panel_outputs = [panels[key] for key in PANEL_RESET_KEYS]

        login_button.click(
            _login,
            inputs=[username, password],
            outputs=[
                session,
                login_col,
                student_col,
                adviser_col,
                admin_col,
                login_error,
                *panel_outputs,
            ],
        ).then(
            _student_dashboard,
            inputs=[session],
            outputs=[welcome, profile, current_courses, progress, materials],
        ).then(
            _adviser_panel,
            inputs=[session],
            outputs=[adviser_students, adviser_profile, adviser_progress],
        )

        logout_button.click(
            _logout,
            inputs=[session],
            outputs=[
                session,
                login_col,
                student_col,
                adviser_col,
                admin_col,
                login_error,
                *panel_outputs,
            ],
        )
        adviser_logout.click(
            _logout,
            inputs=[session],
            outputs=[
                session,
                login_col,
                student_col,
                adviser_col,
                admin_col,
                login_error,
                *panel_outputs,
            ],
        )

        send_button.click(
            _send,
            inputs=[message, chatbot, session, thread_id, citations],
            outputs=[
                chatbot,
                message,
                thread_id,
                citations,
                citation_picker,
                citation_detail,
                page_view,
                asset_view,
            ],
        )
        message.submit(
            _send,
            inputs=[message, chatbot, session, thread_id, citations],
            outputs=[
                chatbot,
                message,
                thread_id,
                citations,
                citation_picker,
                citation_detail,
                page_view,
                asset_view,
            ],
        )
        new_chat.click(
            _new_chat,
            inputs=[session],
            outputs=[
                chatbot,
                thread_id,
                citations,
                citation_picker,
                citation_detail,
                page_view,
                asset_view,
                message,
            ],
        )
        citation_picker.change(
            _show_citation,
            inputs=[citation_picker, citations, session, thread_id],
            outputs=[citation_detail, page_view, asset_view],
        )

        plan_button.click(
            _student_plan,
            inputs=[cap, session],
            outputs=[plan_summary, plan_table, plan_notes],
        )
        adviser_students.change(
            _adviser_detail,
            inputs=[adviser_students, session],
            outputs=[adviser_profile, adviser_progress],
        )
        adviser_plan_button.click(
            _adviser_plan,
            inputs=[adviser_students, adviser_cap, session],
            outputs=[adviser_plan_summary, adviser_plan_table, adviser_plan_notes],
        )

        ingest_button.click(
            _start_ingestion,
            inputs=[session],
            outputs=[job_output, job_id],
        )
        refresh_button.click(
            _refresh_ingestion,
            inputs=[job_id, session],
            outputs=[job_output],
        )

    return demo


def main() -> None:
    build_ui().launch(
        server_name=os.environ.get("UI_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("UI_PORT", "7860")),
        theme=_theme(),
        css=CSS,
        show_error=True,
    )


if __name__ == "__main__":
    main()
