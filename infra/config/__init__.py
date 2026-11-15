"""Validated, non-secret CDK environment configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

EnvironmentName = Literal["dev", "prod"]


@dataclass(frozen=True)
class EnvConfig:
    """Configuration shared by every construct in one environment."""

    env_name: EnvironmentName = "dev"
    account: str | None = None
    region: str | None = None
    owner: str = "course-finder-agent"
    image_tag: str = "m6-synth-placeholder"

    @property
    def is_production(self) -> bool:
        return self.env_name == "prod"

    @property
    def nat_gateways(self) -> int:
        return 2 if self.is_production else 1

    @property
    def log_retention_days(self) -> int:
        return 30 if self.is_production else 14

    @property
    def s3_noncurrent_retention_days(self) -> int:
        return 365 if self.is_production else 30

    @property
    def backup_retention_days(self) -> int:
        return 14 if self.is_production else 3

    @property
    def database_instance_type(self) -> str:
        return "t4g.medium" if self.is_production else "t4g.micro"

    @property
    def database_multi_az(self) -> bool:
        return self.is_production

    @property
    def desired_count(self) -> int:
        return 2 if self.is_production else 1

    @classmethod
    def from_env(cls) -> EnvConfig:
        raw_environment = os.getenv("CDK_ENV", "dev")
        if raw_environment not in ("dev", "prod"):
            raise ValueError("CDK_ENV must be either 'dev' or 'prod'")
        account = os.getenv("CDK_DEFAULT_ACCOUNT") or os.getenv("AWS_ACCOUNT_ID") or None
        region = os.getenv("CDK_DEFAULT_REGION") or os.getenv("AWS_REGION") or None
        if bool(account) != bool(region):
            raise ValueError("Set both CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION, or neither")
        if raw_environment == "prod" and (not account or not region):
            raise ValueError(
                "prod synthesis requires explicit account and region environment values"
            )
        image_tag = os.getenv("CDK_IMAGE_TAG", "m6-synth-placeholder")
        if (
            image_tag == "latest"
            or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", image_tag) is None
        ):
            raise ValueError(
                "CDK_IMAGE_TAG must be a non-empty immutable release tag, not 'latest'"
            )
        owner = os.getenv("RESOURCE_OWNER", "course-finder-agent").strip()
        if not owner:
            raise ValueError("RESOURCE_OWNER must not be empty")
        return cls(
            env_name=raw_environment,  # type: ignore[arg-type]
            account=account,
            region=region,
            owner=owner,
            image_tag=image_tag,
        )
