"""Typed, environment-driven settings.

Scenario terms are configuration, never values computed from the server clock.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

_PLACEHOLDER_PREFIX = "replace-"

EnvName = Literal["development", "test", "production"]
AuthProviderName = Literal["local", "cognito"]


class Settings(BaseSettings):
    """Application settings loaded from the environment and an optional ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: EnvName = "development"

    # Fixed scenario constants (AGENTS.md section 2). Do not derive from the clock.
    current_term: str = "Fall 2026"
    next_term: str = "Spring 2027"

    # Local runtime
    data_root: Path = Path("./data")
    database_url: str = "sqlite:///./data/processed/app.db"

    # Authentication. "local" is development-only; AWS uses Cognito.
    auth_provider: AuthProviderName = "local"
    session_secret: SecretStr = SecretStr("replace-me-local-only")
    csrf_secret: SecretStr = SecretStr("replace-me-local-only")
    local_dev_password: SecretStr = SecretStr("replace-me-local-only")
    session_ttl_seconds: int = 3600

    # Model providers, kept behind interfaces. "offline" runs deterministically.
    model_provider: str = "offline"
    model_name: str = ""
    openai_api_key: SecretStr | None = None
    embedding_model: str = ""
    vector_dimensions: int = 0

    # AWS deploy-time values (never credentials)
    aws_region: str = "ap-southeast-1"
    aws_account_id: str = ""
    aws_environment: str = "dev"
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    s3_document_bucket: str = ""

    @field_validator("data_root")
    @classmethod
    def _resolve_data_root(cls, value: Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @field_validator("current_term", "next_term")
    @classmethod
    def _non_empty_term(cls, value: str) -> str:
        term = value.strip()
        if not term:
            raise ValueError("scenario terms must not be empty")
        return term

    @model_validator(mode="after")
    def _distinct_terms(self) -> Settings:
        if self.current_term == self.next_term:
            raise ValueError("current_term and next_term must differ")
        return self

    # --- Derived paths -----------------------------------------------------------

    @property
    def samples_dir(self) -> Path:
        return self.data_root / "samples"

    @property
    def course_materials_dir(self) -> Path:
        return self.samples_dir / "course-materials"

    @property
    def schemas_dir(self) -> Path:
        return self.data_root / "schemas"

    @property
    def manifests_dir(self) -> Path:
        return self.data_root / "manifests"

    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    # --- Guards ------------------------------------------------------------------

    def assert_production_ready(self) -> None:
        """Fail closed when a non-development environment still holds placeholders."""
        if self.app_env != "production":
            return
        if self.auth_provider != "cognito":
            raise RuntimeError("production requires AUTH_PROVIDER=cognito")
        if not self.cognito_user_pool_id or not self.cognito_client_id:
            raise RuntimeError("production requires Cognito user pool and client IDs")
        for name, secret in (
            ("SESSION_SECRET", self.session_secret),
            ("CSRF_SECRET", self.csrf_secret),
        ):
            if secret.get_secret_value().startswith(_PLACEHOLDER_PREFIX):
                raise RuntimeError(f"{name} still holds a placeholder value")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
