from pathlib import Path

import pytest

from lark_synced_export.release_version import (
    ReleaseVersions,
    validate_release_versions,
)


def write_version_files(tmp_path: Path, pyproject_version: str, init_version: str):
    pyproject = tmp_path / "pyproject.toml"
    module_init = tmp_path / "__init__.py"
    pyproject.write_text(
        f'[project]\nversion = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    module_init.write_text(
        f'"""demo"""\n\n__version__ = "{init_version}"\n',
        encoding="utf-8",
    )
    return pyproject, module_init


def test_validate_release_versions_accepts_three_way_match(tmp_path: Path):
    pyproject, module_init = write_version_files(tmp_path, "0.1.0", "0.1.0")

    assert validate_release_versions(
        "v0.1.0", pyproject, module_init
    ) == ReleaseVersions(
        tag="0.1.0",
        pyproject="0.1.0",
        module_init="0.1.0",
    )


def test_validate_release_versions_requires_v_prefix(tmp_path: Path):
    pyproject, module_init = write_version_files(tmp_path, "0.1.0", "0.1.0")

    with pytest.raises(ValueError, match="must start with 'v'"):
        validate_release_versions("0.1.0", pyproject, module_init)


def test_validate_release_versions_rejects_pyproject_tag_mismatch(tmp_path: Path):
    pyproject, module_init = write_version_files(tmp_path, "0.1.1", "0.1.1")

    with pytest.raises(ValueError, match="version mismatch"):
        validate_release_versions("v0.1.0", pyproject, module_init)


def test_validate_release_versions_rejects_init_drift(tmp_path: Path):
    pyproject, module_init = write_version_files(tmp_path, "0.1.0", "0.1.1")

    with pytest.raises(ValueError, match="version mismatch"):
        validate_release_versions("v0.1.0", pyproject, module_init)
