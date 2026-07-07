from __future__ import annotations

import argparse
import glob
import sys
import zipfile
from pathlib import Path


def _find_metadata_name(archive: zipfile.ZipFile) -> str:
    for name in archive.namelist():
        if name.endswith(".dist-info/METADATA"):
            return name
    raise RuntimeError("wheel is missing dist-info/METADATA")


def _read_requires_dist_lines(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = _find_metadata_name(archive)
        metadata = archive.read(metadata_name).decode("utf-8")
    return [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]


def _collect_invalid_requires_dist(lines: list[str]) -> list[str]:
    return [line for line in lines if " @ " in line]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when built wheel metadata contains direct URL dependencies."
    )
    parser.add_argument(
        "--wheel",
        default="dist/*.whl",
        help="Wheel path or glob to inspect. Default: dist/*.whl",
    )
    args = parser.parse_args()

    matches = sorted(Path(path) for path in glob.glob(args.wheel))
    if not matches:
        print(f"error: no wheel matched {args.wheel!r}", file=sys.stderr)
        return 1

    wheel_path = matches[0]
    requires_dist = _read_requires_dist_lines(wheel_path)
    invalid = _collect_invalid_requires_dist(requires_dist)
    if invalid:
        print(
            f"error: direct URL dependencies are not publish-safe in {wheel_path}",
            file=sys.stderr,
        )
        for line in invalid:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"Wheel metadata is publish-safe: {wheel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
