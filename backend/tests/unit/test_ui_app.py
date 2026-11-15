from __future__ import annotations

import pytest

pytest.importorskip("gradio")


def test_gradio_app_builds_expected_surfaces() -> None:
    from ui.app import build_ui

    demo = build_ui()
    config = demo.get_config_file()
    types: dict[str, int] = {}
    for component in config["components"]:
        types[component["type"]] = types.get(component["type"], 0) + 1

    assert types["chatbot"] == 1
    assert types["tabs"] == 1
    assert types["tabitem"] == 4
    assert types["dataframe"] >= 5
    assert types.get("image", 0) == 0
    assert types["html"] >= 2
    signouts = [c["id"] for c in config["components"]
                if c["type"] == "button" and c["props"].get("value") == "Sign out"]
    assert len(signouts) == 3
    bindings = [d for d in config["dependencies"]
                if any(target[0] in signouts for target in d["targets"])]
    assert len(bindings) == 3
    assert all(d["outputs"] == bindings[0]["outputs"] for d in bindings)
    assert types["dropdown"] == 2
    assert types["state"] == 4
    assert len(config["dependencies"]) >= 12


def test_theme_uses_brand_colors() -> None:
    from ui.app import CSS, RED, _theme

    theme = _theme()
    assert theme.name
    assert theme.button_primary_background_fill == RED
    assert RED in CSS
    assert "#001E60" in CSS
    assert "background: #ffffff" in CSS


def test_login_fields_use_white_text_on_navy() -> None:
    from ui.app import CSS, build_ui

    login_boxes = [
        component["props"]
        for component in build_ui().get_config_file()["components"]
        if component["type"] == "textbox"
        and "login-field" in (component.get("props", {}).get("elem_classes") or ())
    ]
    assert sorted(props["label"] for props in login_boxes) == ["Password", "Username"]

    assert ".login-field input" in CSS
    assert "color: #ffffff !important" in CSS
    assert "background: #001E60 !important" in CSS


def _contrast(foreground: str, background: str) -> float:
    """WCAG 2.1 relative luminance contrast for two ``#rrggbb`` colors."""

    def luminance(color: str) -> float:
        channels = [int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first, second = luminance(foreground), luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def test_dark_mode_reuses_the_light_palette() -> None:
    """Gradio must not fall back to its dark neutrals in a white-only app."""

    from ui.app import _theme

    theme = _theme()
    pinned = (
        "body_background_fill",
        "body_text_color",
        "body_text_color_subdued",
        "background_fill_primary",
        "background_fill_secondary",
        "block_background_fill",
        "panel_background_fill",
        "color_accent_soft",
        "border_color_primary",
        "border_color_accent",
        "link_text_color",
        "link_text_color_hover",
        "link_text_color_active",
        "link_text_color_visited",
        "button_primary_background_fill",
        "button_primary_background_fill_hover",
        "button_primary_text_color",
        "button_primary_border_color",
        "button_secondary_background_fill",
        "button_secondary_background_fill_hover",
        "button_secondary_text_color",
        "button_secondary_border_color",
        "checkbox_background_color",
        "checkbox_background_color_selected",
        "checkbox_border_color",
        "checkbox_border_color_selected",
        "slider_color",
        "loader_color",
        "input_background_fill",
        "input_border_color",
        "input_border_color_focus",
        "input_placeholder_color",
        "code_background_fill",
        "block_label_text_color",
        "block_title_text_color",
        "table_even_background_fill",
        "table_odd_background_fill",
        "table_border_color",
        "table_text_color",
        "table_row_focus",
        "error_text_color",
        "error_border_color",
        "error_icon_color",
        "error_background_fill",
    )
    drifted = {
        name: getattr(theme, f"{name}_dark")
        for name in pinned
        if getattr(theme, f"{name}_dark") != getattr(theme, name)
    }
    assert drifted == {}


@pytest.mark.parametrize("suffix", ["", "_dark"])
@pytest.mark.parametrize(
    "fill", ["table_even_background_fill", "table_odd_background_fill"]
)
def test_table_text_stays_readable_in_both_modes(fill: str, suffix: str) -> None:
    from ui.app import _theme

    theme = _theme()
    text = getattr(theme, f"table_text_color{suffix}")
    background = getattr(theme, f"{fill}{suffix}")
    assert isinstance(text, str) and text.startswith("#")
    assert isinstance(background, str) and background.startswith("#")
    assert _contrast(text, background) >= 4.5


def test_css_pins_table_variables_under_dark() -> None:
    from ui.app import CSS

    assert "body.dark" in CSS
    assert "--table-even-background-fill: #ffffff !important" in CSS
    assert "--table-odd-background-fill: #f7f9fd !important" in CSS
    assert "--table-text-color: #1f2430 !important" in CSS
