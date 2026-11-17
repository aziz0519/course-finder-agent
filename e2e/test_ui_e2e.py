"""Browser-level smoke tests for the containerised student/adviser UI.

These tests are intentionally outside the default ``pytest`` testpaths because
they need a running API + UI and a Playwright browser. CI runs them after
``docker compose up`` and with no AWS or registry access.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

UI_URL = os.environ.get("E2E_UI_URL", "http://127.0.0.1:7860")
PASSWORD = os.environ.get("E2E_PASSWORD", "local-e2e-password")

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.set_default_timeout(20_000)
    try:
        yield page
    finally:
        context.close()


def _sign_in(page: Page, username: str) -> None:
    page.goto(UI_URL, wait_until="domcontentloaded")
    username_input = page.get_by_label("Username")
    expect(username_input).to_be_visible()
    username_input.fill(username)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()


def _set_unit_cap(page: Page, units: int) -> None:
    """Drive the range input from its minimum with keyboard steps.

    Gradio renders a number input and a range input under the same "Unit cap"
    label, so target the slider role explicitly.
    """

    slider = page.get_by_role("slider", name=re.compile("Unit cap"))
    expect(slider).to_be_visible()
    slider.focus()
    slider.press("Home")
    for _ in range((units - 4) // 4):
        slider.press("ArrowRight")
    expect(slider).to_have_value(str(units))


def test_student_planner_cap_and_sign_out(page: Page) -> None:
    _sign_in(page, "student-001")

    expect(page.get_by_role("heading", name=re.compile("Welcome, student-001"))).to_be_visible()
    expect(page.get_by_text("Adviser workspace")).to_be_hidden()

    page.get_by_role("tab", name="Spring 2027").click()
    page.get_by_role("button", name="Build plan").click()
    expect(page.get_by_text("12 units proposed")).to_be_visible()

    _set_unit_cap(page, 8)
    page.get_by_role("button", name="Build plan").click()
    expect(page.get_by_text("8 units proposed")).to_be_visible()
    expect(page.get_by_text("Effective cap: 8 units")).to_be_visible()

    page.get_by_role("button", name="Sign out", exact=True).click()
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile("Welcome, student-001"))).to_be_hidden()


def test_adviser_scope_and_account_switch(page: Page) -> None:
    _sign_in(page, "adviser-001")

    expect(page.get_by_text("Adviser workspace")).to_be_visible()
    assigned = page.get_by_role("combobox", name="Assigned students")
    expect(assigned).to_have_value("student-001 — Sophomore")
    expect(page.get_by_role("heading", name="student-001")).to_be_visible()
    expect(page.get_by_text("student-002")).to_have_count(0)

    page.get_by_role("button", name="Sign out", exact=True).click()
    _sign_in(page, "student-002")

    expect(page.get_by_role("heading", name=re.compile("Welcome, student-002"))).to_be_visible()
    expect(page.get_by_text("Adviser workspace")).to_be_hidden()
    expect(page.get_by_role("heading", name=re.compile("Welcome, student-001"))).to_be_hidden()
