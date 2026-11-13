"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.core.config import get_settings  # noqa: E402
from app.ingestion.dataset import AcademicDataset, load_dataset  # noqa: E402


@pytest.fixture(scope="session")
def data_root() -> Path:
    return get_settings().data_root


@pytest.fixture(scope="session")
def dataset(data_root: Path) -> AcademicDataset:
    return load_dataset(data_root)
