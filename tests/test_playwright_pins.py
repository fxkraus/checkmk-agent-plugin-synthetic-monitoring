"""The Playwright pin and every Playwright image reference must move together.

The executor images copy Chromium out of the Playwright image, so a pip-only bump (e.g. a
Dependabot PR) would ship a Playwright that cannot find its browser. This makes such a PR fail
with a clear message until the image tags and digests are bumped too.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGE_FILES = [
    "executor/Containerfile",
    "executor/Containerfile.playwright",
    "Makefile",
]
_IMAGE = re.compile(
    r"mcr\.microsoft\.com/playwright/python:"
    r"v(?P<version>[\d.]+)-noble(?P<digest>@sha256:[0-9a-f]{64})?"
)


def _pinned_version() -> str:
    deps = tomllib.loads((REPO / "executor/pyproject.toml").read_text())["project"]["dependencies"]
    (pin,) = [d for d in deps if d.startswith("playwright==")]
    return pin.removeprefix("playwright==")


def test_every_playwright_image_matches_the_python_pin():
    version = _pinned_version()
    for name in IMAGE_FILES:
        refs = list(_IMAGE.finditer((REPO / name).read_text()))
        assert refs, f"{name}: no Playwright image reference"
        for ref in refs:
            assert ref["version"] == version, (
                f"{name} uses Playwright image v{ref['version']}, executor pins {version}: "
                "bump the image tag and digest together with the playwright pin"
            )
            assert ref["digest"], f"{name}: Playwright image must be pinned by digest"
