"""Settings contract: fixed scenario terms, resolved paths, and production guards."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import REPO_ROOT, Settings


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type, call-arg]


def test_scenario_terms_default_to_the_fixed_supplied_values() -> None:
    settings = make_settings()

    assert settings.current_term == "Fall 2026"
    assert settings.next_term == "Spring 2027"


def test_terms_come_from_configuration_not_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURRENT_TERM", "Spring 2026")

    assert make_settings().current_term == "Spring 2026"


def test_data_root_is_resolved_to_an_absolute_path() -> None:
    settings = make_settings(data_root=Path("./data"))

    assert settings.data_root.is_absolute()
    assert settings.data_root == (REPO_ROOT / "data").resolve()
    assert settings.samples_dir == settings.data_root / "samples"
    assert settings.course_materials_dir == settings.data_root / "samples" / "course-materials"
    assert settings.schemas_dir == settings.data_root / "schemas"
    assert settings.manifests_dir == settings.data_root / "manifests"
    assert settings.processed_dir == settings.data_root / "processed"


def test_identical_terms_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(current_term="Fall 2026", next_term="Fall 2026")


def test_production_refuses_placeholder_secrets() -> None:
    settings = make_settings(
        app_env="production",
        auth_provider="cognito",
        cognito_user_pool_id="ap-southeast-1_example",
        cognito_client_id="example-client",
    )

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        settings.assert_production_ready()


def test_production_refuses_the_local_auth_provider() -> None:
    with pytest.raises(RuntimeError, match="AUTH_PROVIDER=cognito"):
        make_settings(app_env="production").assert_production_ready()


def test_production_passes_with_cognito_and_real_secrets() -> None:
    settings = make_settings(
        app_env="production",
        auth_provider="cognito",
        cognito_user_pool_id="ap-southeast-1_example",
        cognito_client_id="example-client",
        session_secret=SecretStr("a" * 64),
        csrf_secret=SecretStr("b" * 64),
    )

    settings.assert_production_ready()


def test_development_never_requires_production_secrets() -> None:
    make_settings(app_env="development").assert_production_ready()
