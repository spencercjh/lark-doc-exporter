from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


INIT_VERSION_RE = re.compile(r'^__version__\s*=\s*"(?P<version>[^"]+)"$', re.MULTILINE)


@dataclass(frozen=True)
class ReleaseVersions:
    tag: str
    pyproject: str
    module_init: str


def normalize_release_tag(tag: str) -> str:
    if not tag.startswith("v") or len(tag) == 1:
        raise ValueError("release tag must start with 'v'")
    return tag[1:]


def read_pyproject_version(pyproject_path: Path) -> str:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"could not find [project].version in {pyproject_path}")

    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"could not find [project].version in {pyproject_path}")

    return version


def read_init_version(init_path: Path) -> str:
    match = INIT_VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"could not find __version__ in {init_path}")
    return match.group("version")


def validate_release_versions(
    tag: str,
    pyproject_path: Path,
    init_path: Path,
) -> ReleaseVersions:
    versions = ReleaseVersions(
        tag=normalize_release_tag(tag),
        pyproject=read_pyproject_version(pyproject_path),
        module_init=read_init_version(init_path),
    )
    if len({versions.tag, versions.pyproject, versions.module_init}) != 1:
        raise ValueError(
            "version mismatch: "
            f"tag={versions.tag}, "
            f"pyproject={versions.pyproject}, "
            f"module_init={versions.module_init}"
        )
    return versions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the release tag against pyproject.toml and __init__.__version__."
    )
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.1.0")
    parser.add_argument(
        "--pyproject",
        default="pyproject.toml",
        help="Path to pyproject.toml",
    )
    parser.add_argument(
        "--module-init",
        default="src/lark_synced_export/__init__.py",
        help="Path to the package __init__.py that owns __version__",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    versions = validate_release_versions(
        tag=args.tag,
        pyproject_path=Path(args.pyproject),
        init_path=Path(args.module_init),
    )
    print(json.dumps({"ok": True, "version": versions.tag}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
