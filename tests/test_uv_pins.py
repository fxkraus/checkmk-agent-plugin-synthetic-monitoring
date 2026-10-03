"""uv is pinned once in pyproject.toml; every place that installs uv must use that version.

A different uv rewrites uv.lock in its own format (older releases cannot even read newer locks),
so the dev container, CI and GitLab CI must all run the same one.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _required() -> str:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    required = pyproject["tool"]["uv"]["required-version"]
    assert required.startswith("=="), "pin an exact uv version (setup-uv installs it)"
    return required.removeprefix("==")


def test_dev_container_uses_the_pinned_uv():
    dockerfile = (REPO / ".devcontainer/Dockerfile").read_text()
    (tag,) = re.findall(r"ghcr\.io/astral-sh/uv:([\d.]+)@sha256:[0-9a-f]{64}", dockerfile)
    assert tag == _required()


def test_gitlab_ci_uses_the_pinned_uv():
    gitlab = (REPO / ".gitlab-ci.yml").read_text()
    tags = re.findall(r"ghcr\.io/astral-sh/uv:([\d.]+)-python", gitlab)
    assert tags and set(tags) == {_required()}


def test_setup_uv_reads_the_pin_instead_of_its_own_version():
    for workflow in (REPO / ".github/workflows").glob("*.yml"):
        text = workflow.read_text()
        for step in re.findall(r"uses: astral-sh/setup-uv@.*(?:\n {8,}.*)*", text):
            assert "version:" not in step, f"{workflow.name}: let setup-uv use required-version"
