#!/usr/bin/env python3
"""Build and locally synthesize the course-finder-agent CDK application."""

from __future__ import annotations

import os

from aws_cdk import App, Environment

from infra.config import EnvConfig
from infra.stacks.course_finder import CourseFinderStack


def create_app(config: EnvConfig | None = None) -> tuple[App, CourseFinderStack]:
    """Create the stack without synthesizing or performing any AWS lookup/call."""

    environment = config or EnvConfig.from_env()
    app = App(outdir=os.getenv("CDK_OUTDIR", "cdk.out"))
    stack = CourseFinderStack(
        app,
        f"CourseFinder-{environment.env_name}",
        config=environment,
        env=Environment(account=environment.account, region=environment.region),
        description=(
            f"Course Finder Agent infrastructure ({environment.env_name}); synth-only M6 baseline."
        ),
    )
    return app, stack


def main() -> None:
    app, _stack = create_app()
    app.synth()


if __name__ == "__main__":
    main()
