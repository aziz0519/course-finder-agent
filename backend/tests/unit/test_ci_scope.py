"""Publishing configurations must not cross the local-build CI boundary."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_ci_scope.sh"


@pytest.mark.parametrize(
    ("inputs", "allowed"),
    [
        ("push: false", True),
        ('push: "false"', True),
        ("outputs: type=docker", True),
        ("push: true", False),
        ('push: "true"', False),
        ("'push': 'true'", False),
        ("push: ${{ inputs.publish }}", False),
        ("outputs: type=registry", False),
        ("outputs: |\n          type=registry,ref=example/image", False),
        ("outputs: type=image,name=example/image,push=true", False),
        ("outputs: type=image,push=false", True),
    ],
)
def test_build_action_publishing_scope(tmp_path: Path, inputs: str, allowed: bool) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "build.yml").write_text(
        "jobs:\n  build:\n    steps:\n"
        "      - uses: docker/build-push-action@v6\n"
        f"        with:\n          {inputs}\n"
    )
    result = subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True)
    assert result.returncode == (0 if allowed else 1)
