# Companion Skill Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `lark-doc-exporter skill install` flow that installs the bundled companion skill into Codex and/or Claude Code while keeping the current export entrypoint and `doctor` behavior unchanged.

**Architecture:** Add a focused `skill_install.py` module that owns packaged asset loading, host detection, metadata tracking, conflict handling, and filesystem writes. Keep the CLI in its current default-export shape, route `skill install` through a narrow branch, and validate the behavior with unit tests, CLI tests, README updates, and one wheel-installed smoke run outside the repo checkout.

**Tech Stack:** Python 3.13, `argparse`, `pathlib`, `importlib.resources`, `json`, `shutil`, setuptools package-data, `uv`, `pytest`

---

## File Structure

- Create: `src/lark_synced_export/skill_install.py`
  Responsibility: bundled asset access, host/root resolution, install metadata, dry-run planning, and safe install/overwrite behavior.
- Create: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
  Responsibility: the packaged companion skill payload shipped with the wheel/tool install.
- Modify: `src/lark_synced_export/cli.py`
  Responsibility: keep the existing export entrypoint, preserve `doctor`, add `skill install`, and expose that route in help text.
- Modify: `pyproject.toml`
  Responsibility: include the packaged `SKILL.md` in the built distribution.
- Modify: `README.md`
  Responsibility: make `skill install` a standard setup step, document `--host` / `--force` / `--dry-run`, and keep the runtime prerequisites clear.
- Create: `tests/test_skill_install.py`
  Responsibility: bundled asset checks, installer semantics, dry-run coverage, overwrite safety, and CLI routing coverage.

Deliberate v1 omission: do **not** create `references/` under `skill_assets/` yet. The current skill content fits in one `SKILL.md`, and adding extra files now would violate the spec’s “keep v1 surface intentionally small” boundary.

### Task 1: Bundle the companion skill as package data

**Files:**
- Create: `src/lark_synced_export/skill_install.py`
- Create: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
- Create: `tests/test_skill_install.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing package-asset tests**

Create `tests/test_skill_install.py`:

```python
from lark_synced_export.skill_install import bundled_skill_dir, bundled_skill_markdown


def test_bundled_skill_dir_contains_skill_markdown():
    root = bundled_skill_dir()

    assert root.joinpath("SKILL.md").is_file()


def test_bundled_skill_markdown_mentions_commands_and_prereqs():
    text = bundled_skill_markdown()

    assert "lark-doc-exporter doctor" in text
    assert "lark-doc-exporter skill install" in text
    assert "lark-cli" in text
    assert "Chromium" in text
```

- [ ] **Step 2: Run the targeted tests and verify they fail because the module does not exist yet**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lark_synced_export.skill_install'`.

- [ ] **Step 3: Add the packaged skill asset and the minimal loader**

Create `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`:

````markdown
---
name: lark-doc-exporter
description: Export Feishu/Lark docs with synced blocks expanded into Markdown and themeable local PDFs, and install this companion skill into Codex or Claude Code.
---

# lark-doc-exporter

Use this tool when a user wants to:

- export a Feishu/Lark doc into localized Markdown
- render a themeable local PDF from that Markdown
- check whether `lark-cli` and Chromium are ready
- install this companion skill into supported AI hosts

## Prerequisites

- `lark-cli` available on `PATH` with a user session configured
- Chromium available locally, or install it with `uvx --from playwright playwright install chromium`
- the `lark-doc-exporter` command installed if the user wants repeated local use

## Common commands

```bash
lark-doc-exporter doctor
```

Checks whether `lark-cli` and Chromium are ready for local export work.

```bash
lark-doc-exporter \
  --doc "<doc-url-or-token>" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

Expands synced blocks, exports Markdown, localizes images, and optionally renders a local PDF.

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install --host codex
lark-doc-exporter skill install --host all --force
```

Installs this companion skill into supported AI hosts. Auto mode installs only into detected hosts; explicit `--host` may create the host skill root.

## Key parameters

- `--formats markdown,pdf`: choose output formats
- `--theme default|company`: pick the built-in PDF theme
- `--css /path/to/extra.css`: layer extra print CSS on top of the chosen theme
- `--keep-temp-doc`: keep the temporary expanded Feishu doc for inspection
- `skill install --host codex|claude|all`: select install targets
- `skill install --force`: overwrite an unknown existing target directory
- `skill install --dry-run`: print planned writes without changing the filesystem

## Guidance

- Prefer `doctor` before the first export on a new machine.
- Use `--dry-run` before `skill install` when the user wants to verify target paths.
- The PDF path is local HTML/CSS + Chromium, so it avoids the Feishu server-side PDF disclaimer route.
````

Create `src/lark_synced_export/skill_install.py`:

```python
from __future__ import annotations

from importlib.resources import files
from typing import Final


SKILL_NAME: Final = "lark-doc-exporter"


def bundled_skill_dir():
    return files("lark_synced_export").joinpath("skill_assets", SKILL_NAME)


def bundled_skill_markdown() -> str:
    return bundled_skill_dir().joinpath("SKILL.md").read_text(encoding="utf-8")
```

Modify `pyproject.toml` so the package-data section becomes:

```toml
[tool.setuptools.package-data]
lark_synced_export = [
  "themes/*.css",
  "skill_assets/lark-doc-exporter/SKILL.md",
]
```

- [ ] **Step 4: Rerun the package-asset tests**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the packaged-skill slice**

```bash
git add pyproject.toml src/lark_synced_export/skill_install.py src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md tests/test_skill_install.py
git commit -S -s -m "feat(skill): bundle companion skill assets"
```

### Task 2: Implement safe install semantics, metadata, and dry-run behavior

**Files:**
- Modify: `src/lark_synced_export/skill_install.py`
- Modify: `tests/test_skill_install.py`

- [ ] **Step 1: Add failing installer-semantics tests**

Replace the imports in `tests/test_skill_install.py` with:

```python
import json
from pathlib import Path

import pytest

from lark_synced_export.skill_install import (
    INSTALL_METADATA_FILENAME,
    bundled_skill_dir,
    bundled_skill_markdown,
    run_skill_install,
)
```

Append these tests to `tests/test_skill_install.py`:

```python
def test_run_skill_install_auto_uses_existing_hosts_only(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".agents" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills").mkdir(parents=True)

    result = run_skill_install(host="auto", force=False, dry_run=True, home=home)

    assert result["dry_run"] is True
    assert [item["host"] for item in result["targets"]] == ["codex", "claude"]
    assert [item["action"] for item in result["targets"]] == ["install", "install"]


def test_run_skill_install_explicit_host_creates_parent_and_writes_metadata(tmp_path: Path):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    metadata = json.loads(
        (target_dir / INSTALL_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    assert result["targets"][0]["host"] == "codex"
    assert result["targets"][0]["action"] == "install"
    assert (target_dir / "SKILL.md").is_file()
    assert metadata["tool"] == "lark-doc-exporter"
    assert metadata["host"] == "codex"


def test_run_skill_install_refuses_unknown_existing_directory_without_force(
    tmp_path: Path,
):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")

    with pytest.raises(RuntimeError, match="--force"):
        run_skill_install(host="codex", force=False, dry_run=False, home=home)


def test_run_skill_install_force_overwrites_unknown_existing_directory(tmp_path: Path):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")

    result = run_skill_install(host="codex", force=True, dry_run=False, home=home)

    assert result["targets"][0]["action"] == "overwrite"
    assert "lark-doc-exporter doctor" in (
        target_dir / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_run_skill_install_dry_run_does_not_write_files(tmp_path: Path):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=True, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    assert result["targets"][0]["target_dir"] == str(target_dir)
    assert result["targets"][0]["action"] == "install"
    assert target_dir.exists() is False
```

- [ ] **Step 2: Run the targeted tests and verify they fail because the installer logic does not exist yet**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: FAIL with `ImportError: cannot import name 'INSTALL_METADATA_FILENAME'` or `cannot import name 'run_skill_install'`.

- [ ] **Step 3: Implement host resolution, metadata, dry-run planning, and safe writes**

Replace `src/lark_synced_export/skill_install.py` with:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.resources import as_file, files
import json
from pathlib import Path
import shutil
from typing import Final

from . import __version__


SKILL_NAME: Final = "lark-doc-exporter"
INSTALL_METADATA_FILENAME: Final = ".lark-doc-exporter-install.json"
HOST_SUFFIXES: Final = {
    "codex": Path(".agents") / "skills",
    "claude": Path(".claude") / "skills",
}


@dataclass(frozen=True)
class InstallTarget:
    host: str
    root: Path
    target_dir: Path
    create_parent: bool


@dataclass(frozen=True)
class PlannedInstall:
    host: str
    root: str
    target_dir: str
    action: str
    reason: str


def bundled_skill_dir():
    return files("lark_synced_export").joinpath("skill_assets", SKILL_NAME)


def bundled_skill_markdown() -> str:
    return bundled_skill_dir().joinpath("SKILL.md").read_text(encoding="utf-8")


def host_roots(home: Path | None = None) -> dict[str, Path]:
    base_home = home if home is not None else Path.home()
    return {
        name: base_home / suffix
        for name, suffix in HOST_SUFFIXES.items()
    }


def resolve_targets(host: str, home: Path | None = None) -> list[InstallTarget]:
    roots = host_roots(home)
    if host == "auto":
        targets = [
            InstallTarget(name, root, root / SKILL_NAME, False)
            for name, root in roots.items()
            if root.exists()
        ]
        if not targets:
            raise RuntimeError(
                "No supported host skill directory found under ~/.agents/skills or ~/.claude/skills. "
                "Re-run with --host codex, --host claude, or --host all for explicit setup."
            )
        return targets

    selected_hosts = ("codex", "claude") if host == "all" else (host,)
    return [
        InstallTarget(name, roots[name], roots[name] / SKILL_NAME, True)
        for name in selected_hosts
    ]


def read_install_metadata(target_dir: Path) -> dict | None:
    metadata_path = target_dir / INSTALL_METADATA_FILENAME
    if not metadata_path.is_file():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def is_managed_install(target_dir: Path) -> bool:
    metadata = read_install_metadata(target_dir)
    return bool(metadata and metadata.get("tool") == SKILL_NAME)


def plan_target(target: InstallTarget, force: bool) -> PlannedInstall:
    if not target.target_dir.exists():
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="install",
            reason="target directory does not exist",
        )

    if is_managed_install(target.target_dir):
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="upgrade",
            reason="managed install metadata found",
        )

    if force:
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="overwrite",
            reason="force requested for unmanaged target",
        )

    raise RuntimeError(
        f"Refusing to overwrite unmanaged skill directory: {target.target_dir}. "
        "Re-run with --force if you want to replace it."
    )


def write_install_metadata(stage_dir: Path, host: str) -> None:
    payload = {
        "tool": SKILL_NAME,
        "version": __version__,
        "installed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": host,
    }
    (stage_dir / INSTALL_METADATA_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def install_target(target: InstallTarget) -> None:
    if target.create_parent:
        target.root.mkdir(parents=True, exist_ok=True)

    staging_dir = target.root / f".{SKILL_NAME}.{target.host}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    with as_file(bundled_skill_dir()) as source_dir:
        shutil.copytree(source_dir, staging_dir)

    write_install_metadata(staging_dir, target.host)

    if target.target_dir.exists():
        shutil.rmtree(target.target_dir)

    staging_dir.replace(target.target_dir)


def run_skill_install(
    host: str = "auto",
    force: bool = False,
    dry_run: bool = False,
    home: Path | None = None,
) -> dict:
    targets = resolve_targets(host=host, home=home)
    planned = [plan_target(target, force=force) for target in targets]

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "targets": [asdict(item) for item in planned],
        }

    for target in targets:
        install_target(target)

    return {
        "ok": True,
        "dry_run": False,
        "targets": [asdict(item) for item in planned],
    }
```

- [ ] **Step 4: Rerun the installer-semantics tests**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: PASS with `7 passed`.

- [ ] **Step 5: Commit the installer core**

```bash
git add src/lark_synced_export/skill_install.py tests/test_skill_install.py
git commit -S -s -m "feat(skill): add host-aware companion installer"
```

### Task 3: Wire `skill install` into the CLI without breaking the default export path

**Files:**
- Modify: `src/lark_synced_export/cli.py`
- Modify: `tests/test_skill_install.py`

- [ ] **Step 1: Add failing CLI-routing tests**

Replace the imports in `tests/test_skill_install.py` with:

```python
import json
from pathlib import Path

import pytest

from lark_synced_export.cli import run_main
from lark_synced_export.skill_install import (
    INSTALL_METADATA_FILENAME,
    bundled_skill_dir,
    bundled_skill_markdown,
    run_skill_install,
)
```

Append these tests to `tests/test_skill_install.py`:

```python
def test_run_main_skill_install_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "lark_synced_export.cli.run_skill_install",
        lambda host, force, dry_run: {
            "ok": True,
            "dry_run": dry_run,
            "targets": [
                {
                    "host": host,
                    "action": "install",
                    "target_dir": "/tmp/.agents/skills/lark-doc-exporter",
                }
            ],
        },
    )

    assert run_main(["skill", "install", "--host", "codex", "--dry-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["targets"][0]["host"] == "codex"


def test_run_main_help_mentions_doctor_and_skill_install(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_main(["--help"])

    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "doctor" in help_text
    assert "skill install" in help_text


def test_run_main_export_route_still_uses_default_flags(
    monkeypatch,
    capsys,
    tmp_path: Path,
):
    calls: dict = {}

    def fake_export_document(**kwargs):
        calls.update(kwargs)
        return {"outputs": {"markdown": str(tmp_path / "demo.md")}}

    monkeypatch.setattr("lark_synced_export.cli.export_document", fake_export_document)

    assert (
        run_main(
            [
                "--doc",
                "demo-token",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "markdown",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert calls["doc_ref"] == "demo-token"
    assert calls["formats"] == ["markdown"]
    assert payload["outputs"]["markdown"].endswith("demo.md")
```

- [ ] **Step 2: Run the CLI-routing tests and verify they fail before the CLI is wired**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: FAIL because `run_main(["skill", "install", ...])` still falls through to export-arg parsing and demands `--doc` / `--output-dir`.

- [ ] **Step 3: Add the CLI route and help exposure**

Replace `src/lark_synced_export/cli.py` with:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .doctor import run_doctor
from .exporter import export_document
from .skill_install import run_skill_install


def parse_export_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand Feishu/Lark synced blocks, export Markdown, and render local PDF.",
        epilog=(
            "Other commands:\n"
            "  doctor\n"
            "  skill install [--host {auto,codex,claude,all}] [--force] [--dry-run]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--doc",
        required=True,
        help="Original docx/wiki URL or token accepted by `lark-cli docs +fetch`.",
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory for output artifacts."
    )
    parser.add_argument(
        "--formats",
        default="markdown,pdf",
        help="Comma-separated export formats. Supported: markdown,pdf",
    )
    parser.add_argument(
        "--title-suffix",
        default="（同步块展开导出）",
        help="Suffix appended to the temporary expanded doc title.",
    )
    parser.add_argument(
        "--file-stem",
        default="",
        help="Optional output filename stem. Defaults to the expanded doc title slug.",
    )
    parser.add_argument(
        "--keep-temp-doc",
        action="store_true",
        help="Keep the temporary expanded doc instead of deleting it after the Markdown export step.",
    )
    parser.add_argument(
        "--theme",
        default="default",
        help="Built-in PDF theme name. Supported: default, company.",
    )
    parser.add_argument(
        "--css",
        default="",
        help="Optional extra CSS file layered on top of the selected theme for PDF output.",
    )
    return parser.parse_args(argv)


def parse_skill_install_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lark-doc-exporter skill install",
        description="Install the bundled companion skill into Codex and/or Claude Code.",
    )
    parser.add_argument(
        "--host",
        choices=["auto", "codex", "claude", "all"],
        default="auto",
        help="Install target selection. Auto mode uses only already-detected hosts.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing unmanaged target directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned target paths without writing files.",
    )
    return parser.parse_args(argv)


def run_main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "doctor":
        print(json.dumps(run_doctor(), ensure_ascii=False, indent=2))
        return 0

    if argv[:2] == ["skill", "install"]:
        args = parse_skill_install_args(argv[2:])
        print(
            json.dumps(
                run_skill_install(
                    host=args.host,
                    force=args.force,
                    dry_run=args.dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if argv and argv[0] == "skill":
        raise SystemExit("unsupported skill command; expected `lark-doc-exporter skill install`")

    args = parse_export_args(argv)
    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    allowed = {"markdown", "pdf"}
    invalid = [fmt for fmt in formats if fmt not in allowed]
    if invalid:
        raise SystemExit(f"unsupported formats: {', '.join(invalid)}")

    result = export_document(
        doc_ref=args.doc,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        formats=formats,
        title_suffix=args.title_suffix,
        file_stem=args.file_stem,
        keep_temp_doc=args.keep_temp_doc,
        theme_name=args.theme,
        override_css=Path(args.css).expanduser().resolve() if args.css else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    try:
        raise SystemExit(run_main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:  # pragma: no cover - CLI boundary
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rerun the CLI-routing tests**

Run:

```bash
uv run pytest tests/test_skill_install.py -q
```

Expected: PASS with `10 passed`.

- [ ] **Step 5: Commit the CLI integration**

```bash
git add src/lark_synced_export/cli.py tests/test_skill_install.py
git commit -S -s -m "feat(cli): add companion skill install command"
```

### Task 4: Document the flow and prove it works from an installed wheel outside the repo checkout

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README so `skill install` is a standard setup step**

Replace the `## Install As A Tool` section in `README.md` with:

````markdown
## Install As A Tool

For repeated use, install the command once:

```bash
uv tool install git+https://github.com/spencercjh/lark-doc-exporter
```

Then use it directly:

```bash
lark-doc-exporter doctor
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install

lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

Auto mode installs the companion skill into every detected supported host:

- Codex: `~/.agents/skills/lark-doc-exporter`
- Claude Code: `~/.claude/skills/lark-doc-exporter`

Use `--host codex`, `--host claude`, or `--host all` to target specific hosts. Use `--force` only when you intentionally want to replace an existing unmanaged target directory.
````

- [ ] **Step 2: Run the full test suite and build the wheel**

Run:

```bash
uv run pytest -q
uv build
git diff --check
```

Expected:

- `pytest` passes
- `uv build` creates `dist/lark_doc_exporter-0.1.0-py3-none-any.whl`
- `git diff --check` prints nothing

- [ ] **Step 3: Run the package-level smoke test outside the repo checkout**

Run:

```bash
wheel_path="$(pwd)/dist/lark_doc_exporter-0.1.0-py3-none-any.whl"
tmp_home="$(mktemp -d)"
tmp_run="$(mktemp -d)"

cd "$tmp_run"
HOME="$tmp_home" uv tool install --python 3.13 "$wheel_path"
HOME="$tmp_home" PATH="$tmp_home/.local/bin:$PATH" lark-doc-exporter skill install --host codex --dry-run
HOME="$tmp_home" PATH="$tmp_home/.local/bin:$PATH" lark-doc-exporter skill install --host codex
test -f "$tmp_home/.agents/skills/lark-doc-exporter/SKILL.md"
grep -q "lark-doc-exporter skill install" "$tmp_home/.agents/skills/lark-doc-exporter/SKILL.md"
rm -rf "$tmp_home" "$tmp_run"
```

Expected:

- both `skill install` commands exit `0`
- the dry-run JSON mentions `$tmp_home/.agents/skills/lark-doc-exporter`
- the real install creates `SKILL.md` under the temp home, proving the command works from an installed wheel outside the repo checkout

- [ ] **Step 4: Commit the documentation and validation pass**

```bash
git add README.md
git commit -S -s -m "docs(readme): document companion skill install"
```

- [ ] **Step 5: Prepare the review handoff**

Run:

```bash
git status --short
git log --oneline -4
```

Expected:

- `git status --short` is empty
- the last four commits are the four slices from this plan, ready to post back for review
