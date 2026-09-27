#!/usr/bin/env python3
"""Build a Checkmk ``.mkp`` package from the staged plugin tree — standard library only.

An ``.mkp`` is a gzip-compressed outer tar (verified against ``cmk.mkp_tool._mkp`` on a live
2.4.0p32 site, see ``docs/checkmk-2.4-api-verification.md``) containing:

* ``info``       — ``pprint.pformat(manifest_dict)`` (read back via ``ast.literal_eval``),
* ``info.json``  — the same manifest as JSON (for external tools),
* one **uncompressed** ``<part_ident>.tar`` per package part, whose members are the files
  *relative to that part's site directory* (``cmk_addons_plugins`` ->
  ``local/lib/python3/cmk_addons/plugins`` -> members like ``synmon/lib/parsing.py``).

Reproducing that with the stdlib ``tarfile`` module means CI can build an installable package
without a running Checkmk site. Run ``python3 scripts/build_mkp.py`` to write it to ``dist/``.
"""

from __future__ import annotations

import argparse
import io
import json
import pprint
import sys
import tarfile
from pathlib import Path

# Where each package part's files are staged in this repo, relative to ``checkmk_mkp/``.
_PART_STAGE_DIR = {"cmk_addons_plugins": "cmk_addons/plugins", "agents": "agents", "lib": "lib"}

# Fixed member timestamp for reproducible builds (override with SOURCE_DATE_EPOCH not needed here).
_MTIME = 1700000000

# Manifest keys carried through verbatim (with their dotted aliases) into ``info``/``info.json``.
_MANIFEST_KEYS = (
    "title",
    "name",
    "description",
    "version",
    "version.packaged",
    "version.min_required",
    "version.usable_until",
    "author",
    "download_url",
)


def load_manifest(stage_dir: Path) -> dict:
    return json.loads((stage_dir / "manifest.json").read_text())


def _tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = _MTIME
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.type = tarfile.REGTYPE
    return info


def _build_part_tar(stage_dir: Path, part_ident: str, relpaths: list[str]) -> bytes:
    """Build the uncompressed inner ``<part>.tar``, members named by site-relative path."""
    base = stage_dir / _PART_STAGE_DIR[part_ident]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel in relpaths:
            src = base / rel
            if not src.is_file():
                raise FileNotFoundError(f"manifest lists missing file: {src}")
            data = src.read_bytes()
            tar.addfile(_tar_info(rel, len(data)), io.BytesIO(data))
    return buf.getvalue()


def build_mkp_bytes(stage_dir: Path) -> tuple[str, bytes]:
    """Return ``(filename, mkp_bytes)`` for the package staged under ``stage_dir``."""
    manifest = load_manifest(stage_dir)
    files: dict[str, list[str]] = manifest["files"]

    info_dict = {key: manifest.get(key) for key in _MANIFEST_KEYS}
    info_dict["files"] = {part: list(paths) for part, paths in files.items() if paths}

    members: list[tuple[str, bytes]] = [
        ("info", (pprint.pformat(info_dict) + "\n").encode()),
        ("info.json", json.dumps(info_dict).encode()),
    ]
    for part_ident, relpaths in files.items():
        if relpaths:
            members.append((f"{part_ident}.tar", _build_part_tar(stage_dir, part_ident, relpaths)))

    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, content in members:
            tar.addfile(_tar_info(name, len(content)), io.BytesIO(content))

    filename = f"{manifest['name']}-{manifest['version']}.mkp"
    return filename, out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=repo_root / "checkmk_mkp",
        help="directory holding manifest.json and the staged plugin tree",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=repo_root / "dist",
        help="directory to write the .mkp into",
    )
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="print only the package version and exit",
    )
    args = parser.parse_args(argv)

    if args.print_version:
        print(load_manifest(args.stage_dir)["version"])
        return 0

    filename, data = build_mkp_bytes(args.stage_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / filename
    out_path.write_bytes(data)
    print(f"Built {out_path} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
