# PyPI Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tag-triggered PyPI Trusted Publishing workflow and switch the public install path to `uv tool install lark-doc-exporter` without changing exporter runtime behavior.

**Architecture:** Keep the release surface intentionally small. Add one pure-Python release-version checker that the workflow and tests both use, add one dedicated `publish-pypi.yml` workflow that reuses `make ci` plus a fresh `uv build`, and then reorder the README so package-name install is the first-class path while Git URL install stays only under unreleased/development guidance.

**Tech Stack:** Python 3.14, `uv`, `pytest`, `tomllib`, GitHub Actions, PyPI Trusted Publishing

---

## File Structure

- Create: `src/lark_synced_export/release_version.py`
  Responsibility: parse the release tag, read the repo’s two version sources, enforce three-way equality, and expose a tiny `python -m` entrypoint for the publish workflow.
- Create: `tests/test_release_version.py`
  Responsibility: pin the release contract in unit tests so tag-prefix mistakes and `__init__.__version__` drift fail before the workflow is written.
- Create: `.github/workflows/publish-pypi.yml`
  Responsibility: run only on `v*` tags, reuse `make ci`, rebuild `dist/`, smoke-test the built wheel through `lark-doc-exporter --help`, and upload with OIDC.
- Modify: `README.md`
  Responsibility: make the published-package install path (`uv tool install lark-doc-exporter`) the main user path, keep one-off usage on `uvx lark-doc-exporter`, and demote Git URL installation to explicit unreleased/development guidance.
- Do not modify: `Makefile`
  Responsibility: `make ci` remains the canonical validation surface exactly as it exists today.
- Do not modify: `.github/workflows/python-ci.yml`
  Responsibility: ordinary development CI stays unchanged; the new workflow is release-only.

### Task 1: Add the release-version contract checker and tests

**Files:**
- Create: `src/lark_synced_export/release_version.py`
- Create: `tests/test_release_version.py`

- [ ] **Step 1: Write the failing tests for the release contract**

Create `tests/test_release_version.py`:

```python
from pathlib import Path

import pytest

from lark_synced_export.release_version import ReleaseVersions, validate_release_versions


def write_version_files(tmp_path: Path, pyproject_version: str, init_version: str):
    pyproject = tmp_path / "pyproject.toml"
    module_init = tmp_path / "__init__.py"
    pyproject.write_text(
        "[project]\n"
        f'version = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    module_init.write_text(
        '"""demo"""\n\n'
        f'__version__ = "{init_version}"\n',
        encoding="utf-8",
    )
    return pyproject, module_init


def test_validate_release_versions_accepts_three_way_match(tmp_path: Path):
    pyproject, module_init = write_version_files(tmp_path, "0.1.0", "0.1.0")

    assert validate_release_versions("v0.1.0", pyproject, module_init) == ReleaseVersions(
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
```

- [ ] **Step 2: Run the new test file and confirm it fails before implementation**

Run:

```bash
uv run pytest tests/test_release_version.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lark_synced_export.release_version'`.

- [ ] **Step 3: Add the minimal release-version helper that the tests and workflow will share**

Create `src/lark_synced_export/release_version.py`:

```python
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
    return payload["project"]["version"]


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
```

- [ ] **Step 4: Re-run the focused tests and the helper on the current repo version**

Run:

```bash
uv run pytest tests/test_release_version.py -q
uv run python -m lark_synced_export.release_version --tag v0.1.0
```

Expected:
- `4 passed`
- the helper prints JSON containing `"ok": true` and `"version": "0.1.0"`

- [ ] **Step 5: Commit the release-version checker**

```bash
git add src/lark_synced_export/release_version.py tests/test_release_version.py
git commit -S -s -m "build(release): add version contract checker"
```

### Task 2: Add the tag-triggered PyPI publish workflow

**Files:**
- Create: `.github/workflows/publish-pypi.yml`

- [ ] **Step 1: Prove the release workflow file does not exist yet**

Run:

```bash
test -f .github/workflows/publish-pypi.yml && echo "exists" || echo "missing"
```

Expected: `missing`

- [ ] **Step 2: Create the dedicated publish workflow**

Create `.github/workflows/publish-pypi.yml`:

```yaml
name: publish-pypi

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write

env:
  PYTHON_VERSION: "3.14"

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7
        with:
          fetch-depth: 1

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Set up uv
        uses: astral-sh/setup-uv@v8.2.0
        with:
          enable-cache: true

      - name: Sync dev dependencies
        run: uv sync --python ${{ env.PYTHON_VERSION }} --group dev

      - name: Verify release tag and package versions
        run: uv run python -m lark_synced_export.release_version --tag "${GITHUB_REF_NAME}"

      - name: Run repository checks
        run: make ci

      - name: Rebuild release artifacts
        run: |
          rm -rf dist
          uv build

      - name: Smoke-test the built wheel
        run: uv tool run --isolated --from dist/lark_doc_exporter-*.whl lark-doc-exporter --help

      - name: Publish distribution to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 3: Sanity-check the workflow without uploading anything**

Run:

```bash
grep -n 'tags:' .github/workflows/publish-pypi.yml
grep -n 'id-token: write' .github/workflows/publish-pypi.yml
grep -n 'python -m lark_synced_export.release_version' .github/workflows/publish-pypi.yml
grep -n 'uv tool run --isolated --from dist/lark_doc_exporter-.*\\.whl lark-doc-exporter --help' .github/workflows/publish-pypi.yml
grep -n 'pypa/gh-action-pypi-publish@release/v1' .github/workflows/publish-pypi.yml
git diff --check
```

Expected:
- each `grep` prints exactly one matching workflow line
- `git diff --check` prints nothing

- [ ] **Step 4: Commit the publish workflow**

```bash
git add .github/workflows/publish-pypi.yml
git commit -S -s -m "ci(release): add pypi publish workflow"
```

### Task 3: Reorder the README around the published-package install path

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Capture the current Git-URL-first install guidance**

Run:

```bash
rg -n 'git\\+https://github.com/spencercjh/lark-doc-exporter|uv tool install git\\+https://github.com/spencercjh/lark-doc-exporter|uvx --from git\\+https://github.com/spencercjh/lark-doc-exporter' README.md
```

Expected: output shows the Quick Start and installed-tool sections still centered on Git URL commands.

- [ ] **Step 2: Rewrite only the install-path sections and leave the rest of the README untouched**

Edit `README.md` so:

- `## Quick Start` becomes:

````markdown
## Quick Start

Install the released tool once:

```bash
uv tool install lark-doc-exporter
lark-doc-exporter doctor
```

If Chromium is missing, prepare it once:

```bash
uvx --from playwright playwright install chromium
```

Then run an export:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```
````

- insert a new `## One-off Run` section immediately after `## Quick Start`:

````markdown
## One-off Run

If you do not want a persistent tool install:

```bash
uvx lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```
````

- `## Install As A Tool` becomes:

````markdown
## Install As A Tool

After installing the released package, companion-skill operations stay the same:

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install
```

Auto mode installs the companion skill into every detected supported host:

- Codex: `~/.agents/skills/lark-doc-exporter`
- Claude Code: `~/.claude/skills/lark-doc-exporter`

Use `--host codex`, `--host claude`, or `--host all` to target specific hosts. `--dry-run` previews the install plan and target directories without writing files. Use `--force` only when you intentionally want to replace an existing unmanaged target directory.
````

- `## Development` becomes:

````markdown
## Development / Unreleased

Use the Git URL or a local checkout only when you intentionally need unreleased code:

```bash
uvx --from git+https://github.com/spencercjh/lark-doc-exporter lark-doc-exporter doctor

git clone https://github.com/spencercjh/lark-doc-exporter
cd lark-doc-exporter
uv sync --python 3.14 --group dev
make fmt
make ci

# Optional runtime/environment check (not part of required CI)
uv run lark-doc-exporter doctor
```
````

Leave `## Chromium Setup`, `## Output`, `## Themes`, and `## Notes` unchanged.

- [ ] **Step 3: Run the final local validation for docs plus release plumbing**

Run:

```bash
make ci
rm -rf dist
uv build
uv tool run --isolated --from dist/lark_doc_exporter-*.whl lark-doc-exporter --help
rg -n 'uv tool install lark-doc-exporter|uvx lark-doc-exporter|git\\+https://github.com/spencercjh/lark-doc-exporter' README.md
git diff --check
```

Expected:
- `make ci` passes
- `uv build` succeeds and recreates `dist/`
- `uv tool run --isolated --from dist/lark_doc_exporter-*.whl lark-doc-exporter --help` prints the CLI usage text
- `README.md` now shows package-name install/one-off commands first, keeps the skill-install guidance under `Install As A Tool`, preserves `Chromium Setup` / `Output` / `Themes` / `Notes`, and keeps Git URL usage only in `Development / Unreleased`
- `git diff --check` prints nothing

- [ ] **Step 4: Commit the README reorder**

```bash
git add README.md
git commit -S -s -m "docs(readme): switch public install path to pypi"
```

## Release Rollout Checklist

These steps happen after the implementation branch is reviewed, pushed only with Spencer’s explicit approval, and merged to `main`.

- [ ] **Step 1: Confirm the PyPI project name is still available to this repository**

Open `https://pypi.org/project/lark-doc-exporter/`.

Expected:
- if the page is missing, proceed with a pending publisher / first release flow
- if the page exists under this project’s control, proceed with an existing-project publisher flow
- if the page exists under an unrelated owner, stop and escalate the naming decision instead of tagging any release

- [ ] **Step 2: Configure the PyPI Trusted Publisher without a long-lived token**

In the PyPI project UI (or pending publisher UI), configure:

- owner / account: `spencercjh`
- repository: `lark-doc-exporter`
- workflow: `publish-pypi.yml`
- environment: leave blank, because this plan does not add a GitHub Actions environment gate

Expected:
- the project is ready for GitHub OIDC uploads
- no `PYPI_TOKEN` secret is added to the GitHub repository

- [ ] **Step 3: Cut the first release tag from merged `main`**

If `main` still carries `0.1.0` and no earlier release tag exists, cut `v0.1.0` exactly:

```bash
git checkout main
git pull --ff-only origin main
uv run python -m lark_synced_export.release_version --tag v0.1.0
git tag v0.1.0
git push origin main v0.1.0
```

If Spencer asks for a different first release version before tagging, update both version files in the same commit first, rerun the helper with the new tag, and only then push the matching release tag.

- [ ] **Step 4: Verify the publish run and the public install surface**

Run:

```bash
gh run list --workflow publish-pypi.yml --limit 1
uvx lark-doc-exporter --help
```

Expected:
- the latest `publish-pypi.yml` run finishes with `success`
- `uvx lark-doc-exporter --help` prints the published CLI usage from PyPI
