# Installable Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `lark-doc-exporter` runnable as a real installed Python tool (`uvx`, `uv tool install`, future PyPI) without requiring a repo checkout, while preserving current export behavior and Chromium PDF output.

**Architecture:** Replace the repo-relative Node runtime seams with package-local Python modules: a markdown renderer, a Chromium PDF renderer, and a small diagnostics layer. Keep the existing export flow and theme CSS, remove repo-root assumptions from `exporter.py`, and validate both repo-local and installed-tool execution paths.

**Tech Stack:** Python 3.11+, `uv`, setuptools, `markdown`, `playwright` (Python), `pytest`, `lark-cli`

---

## File Structure

- Create: `src/lark_synced_export/markdown_runtime.py`
  Responsibility: package-local markdown-to-HTML rendering; no shell-outs.
- Create: `src/lark_synced_export/pdf_runtime.py`
  Responsibility: Chromium discovery, browser readiness checks, HTML-to-PDF rendering.
- Create: `src/lark_synced_export/doctor.py`
  Responsibility: user-facing runtime diagnostics for `lark-cli` and browser readiness.
- Modify: `src/lark_synced_export/exporter.py`
  Responsibility: keep export orchestration, but stop depending on repo-root paths and delegate rendering to package-local helpers.
- Modify: `src/lark_synced_export/cli.py`
  Responsibility: preserve the current export CLI surface and add `doctor`.
- Modify: `pyproject.toml`
  Responsibility: runtime dependencies and package metadata.
- Modify: `README.md`
  Responsibility: install-first end-user flow, browser prep guidance, dev flow separation.
- Delete: `scripts/render_html_to_pdf.mjs`
  Responsibility removed: repo-local Node helper.
- Delete: `package.json`
  Responsibility removed: runtime JS dependency declaration.
- Delete: `package-lock.json`
  Responsibility removed: runtime JS lockfile.
- Create: `tests/test_markdown_runtime.py`
  Responsibility: package-local markdown rendering behavior.
- Create: `tests/test_pdf_runtime.py`
  Responsibility: browser discovery and PDF rendering contract.
- Create: `tests/test_doctor.py`
  Responsibility: doctor output and CLI routing.
- Modify: `tests/test_exporter.py`
  Responsibility: keep existing HTML wrapper checks and add one regression test proving `export_document()` no longer pins temp files to the repo root.
- Reuse: `tests/test_theme_resolution.py`
  Responsibility: package theme lookup regression coverage.

### Task 1: Add a package-local markdown renderer

**Files:**
- Create: `src/lark_synced_export/markdown_runtime.py`
- Create: `tests/test_markdown_runtime.py`
- Modify: `pyproject.toml:5-19`

- [ ] **Step 1: Write the failing markdown renderer test**

Create `tests/test_markdown_runtime.py`:

```python
from pathlib import Path

from lark_synced_export.markdown_runtime import render_markdown_body


def test_render_markdown_body_supports_tables_and_fenced_code(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text(
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n\n"
        "```python\n"
        "print('hi')\n"
        "```\n",
        encoding="utf-8",
    )

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "language-python" in html
    assert "print" in html
```

- [ ] **Step 2: Run the test and verify it fails because the module does not exist yet**

Run:

```bash
uv run pytest tests/test_markdown_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lark_synced_export.markdown_runtime'`.

- [ ] **Step 3: Add the markdown dependency and implement the module**

Modify `pyproject.toml` so `[project].dependencies` becomes:

```toml
dependencies = [
  "markdown>=3.7,<4",
]
```

Create `src/lark_synced_export/markdown_runtime.py`:

```python
from __future__ import annotations

from pathlib import Path

import markdown as markdown_lib


MARKDOWN_EXTENSIONS = [
    "extra",
    "sane_lists",
]


def render_markdown_body(markdown_path: Path, body_html: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    html = markdown_lib.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html5",
    )
    body_html.write_text(html, encoding="utf-8")
```

- [ ] **Step 4: Sync dependencies and rerun the targeted test**

Run:

```bash
uv sync --group dev
uv run pytest tests/test_markdown_runtime.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the markdown-renderer slice**

```bash
git add pyproject.toml src/lark_synced_export/markdown_runtime.py tests/test_markdown_runtime.py uv.lock
git commit -S -s -m "feat(runtime): add packaged markdown renderer"
```

### Task 2: Add a package-local Chromium PDF runtime

**Files:**
- Create: `src/lark_synced_export/pdf_runtime.py`
- Create: `tests/test_pdf_runtime.py`
- Modify: `pyproject.toml:5-19`

- [ ] **Step 1: Write the failing Chromium runtime tests**

Create `tests/test_pdf_runtime.py`:

```python
from pathlib import Path

from lark_synced_export.pdf_runtime import check_chromium_ready, render_html_to_pdf


class FakePage:
    def __init__(self, calls: dict):
        self.calls = calls

    def goto(self, url: str, wait_until: str) -> None:
        self.calls["goto"] = {"url": url, "wait_until": wait_until}

    def emulate_media(self, media: str) -> None:
        self.calls["media"] = media

    def pdf(self, **kwargs) -> None:
        self.calls["pdf"] = kwargs


class FakeBrowser:
    def __init__(self, calls: dict):
        self.calls = calls

    def new_page(self) -> FakePage:
        return FakePage(self.calls)

    def close(self) -> None:
        self.calls["browser_closed"] = True


class FakeChromium:
    def __init__(self, calls: dict):
        self.calls = calls

    def launch(self, **kwargs):
        self.calls["launch"] = kwargs
        return FakeBrowser(self.calls)


class FakePlaywrightContext:
    def __init__(self, calls: dict):
        self.calls = calls
        self.chromium = FakeChromium(calls)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_render_html_to_pdf_prefers_explicit_browser(monkeypatch, tmp_path: Path):
    calls: dict = {}
    input_html = tmp_path / "render.html"
    output_pdf = tmp_path / "demo.pdf"
    input_html.write_text("<html><body>demo</body></html>", encoding="utf-8")

    monkeypatch.setenv("LARK_DOC_EXPORTER_CHROMIUM", "/custom/chromium")
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.sync_playwright",
        lambda: FakePlaywrightContext(calls),
    )

    render_html_to_pdf(input_html, output_pdf)

    assert calls["launch"]["executable_path"] == "/custom/chromium"
    assert calls["goto"]["url"] == input_html.resolve().as_uri()
    assert calls["goto"]["wait_until"] == "load"
    assert calls["media"] == "print"
    assert calls["pdf"]["format"] == "A4"
    assert calls["pdf"]["print_background"] is True
    assert calls["pdf"]["prefer_css_page_size"] is True


def test_check_chromium_ready_returns_helpful_failure(monkeypatch):
    class BrokenContext:
        def __enter__(self):
            raise RuntimeError("no browser")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.delenv("LARK_DOC_EXPORTER_CHROMIUM", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.sync_playwright",
        lambda: BrokenContext(),
    )

    ok, detail = check_chromium_ready()

    assert ok is False
    assert "uvx --from playwright playwright install chromium" in detail
```

- [ ] **Step 2: Run the tests and verify they fail because the module does not exist yet**

Run:

```bash
uv run pytest tests/test_pdf_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lark_synced_export.pdf_runtime'`.

- [ ] **Step 3: Add the Playwright dependency and implement the runtime**

Modify `pyproject.toml` so `[project].dependencies` becomes:

```toml
dependencies = [
  "markdown>=3.7,<4",
  "playwright>=1.54,<2",
]
```

Create `src/lark_synced_export/pdf_runtime.py`:

```python
from __future__ import annotations

import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
)


def resolve_browser_executable() -> str | None:
    explicit = os.environ.get("LARK_DOC_EXPORTER_CHROMIUM")
    if explicit:
        return explicit

    for name in BROWSER_CANDIDATES:
        candidate = shutil.which(name)
        if candidate:
            return candidate

    return None


def launch_browser(playwright):
    executable = resolve_browser_executable()
    if executable:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        return browser, executable

    browser = playwright.chromium.launch(headless=True)
    return browser, "playwright-managed"


def check_chromium_ready() -> tuple[bool, str]:
    try:
        with sync_playwright() as playwright:
            browser, source = launch_browser(playwright)
            browser.close()
        return True, f"Chromium is available via {source}."
    except Exception as exc:
        return (
            False,
            "Chromium is not ready. Install a system Chrome/Chromium binary or run "
            "`uvx --from playwright playwright install chromium`. "
            f"Original error: {exc}",
        )


def render_html_to_pdf(input_html: Path, output_pdf: Path) -> None:
    with sync_playwright() as playwright:
        browser, _source = launch_browser(playwright)
        try:
            page = browser.new_page()
            page.goto(input_html.resolve().as_uri(), wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=str(output_pdf.resolve()),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            browser.close()
```

- [ ] **Step 4: Sync dependencies and rerun the targeted tests**

Run:

```bash
uv sync --group dev
uv run pytest tests/test_pdf_runtime.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the packaged Chromium runtime**

```bash
git add pyproject.toml src/lark_synced_export/pdf_runtime.py tests/test_pdf_runtime.py uv.lock
git commit -S -s -m "feat(runtime): add packaged chromium renderer"
```

### Task 3: Rewire the exporter and add `doctor`

**Files:**
- Create: `src/lark_synced_export/doctor.py`
- Modify: `src/lark_synced_export/cli.py:1-83`
- Modify: `src/lark_synced_export/exporter.py:14-17, 441-497, 524-549`
- Modify: `tests/test_exporter.py`
- Create: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing regression tests for CLI doctor and tempdir behavior**

Create `tests/test_doctor.py`:

```python
import json

from lark_synced_export.cli import run_main
from lark_synced_export.doctor import check_lark_cli


def test_run_main_doctor_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "lark_synced_export.cli.run_doctor",
        lambda: {"ok": True, "checks": [{"name": "lark-cli", "ok": True, "detail": "ok"}]},
    )

    assert run_main(["doctor"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "lark-cli"


def test_check_lark_cli_reports_missing_binary(monkeypatch):
    monkeypatch.setattr("lark_synced_export.doctor.shutil.which", lambda _name: None)

    result = check_lark_cli()

    assert result.ok is False
    assert "lark-cli" in result.detail
```

Append to `tests/test_exporter.py`:

```python
from lark_synced_export.exporter import build_render_html, export_document, slugify_filename


def test_export_document_does_not_pin_tempdir_to_repo(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    theme_css = tmp_path / "theme.css"
    theme_css.write_text(":root { --accent: #123456; }", encoding="utf-8")
    capture: dict = {}

    class DummyTempDir:
        def __init__(self, *args, **kwargs):
            capture["args"] = args
            capture["kwargs"] = kwargs

        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_localize(_src: Path, dst: Path, _assets: Path) -> int:
        dst.write_text("# Demo\n", encoding="utf-8")
        return 0

    def fake_render_markdown(markdown_path: Path, body_html: Path) -> None:
        body_html.write_text("<h1>Demo</h1>", encoding="utf-8")

    def fake_render_pdf(_html: Path, output_pdf: Path) -> None:
        output_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("lark_synced_export.exporter.tempfile.TemporaryDirectory", DummyTempDir)
    monkeypatch.setattr("lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>")
    monkeypatch.setattr("lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0))
    monkeypatch.setattr("lark_synced_export.exporter.normalize_xml_for_create", lambda xml, suffix: (xml, "Demo"))
    monkeypatch.setattr("lark_synced_export.exporter.create_temp_doc", lambda xml, stage: ("tmp-token", "https://example.com/doc"))
    monkeypatch.setattr("lark_synced_export.exporter.export_markdown", lambda token, stage, stem: raw_markdown_path)
    monkeypatch.setattr("lark_synced_export.exporter.delete_temp_doc", lambda _token: None)
    monkeypatch.setattr("lark_synced_export.exporter.localize_markdown_images", fake_localize)
    monkeypatch.setattr("lark_synced_export.exporter.resolve_theme_css", lambda _theme: theme_css)
    monkeypatch.setattr("lark_synced_export.exporter.render_markdown_body", fake_render_markdown)
    monkeypatch.setattr("lark_synced_export.exporter.render_html_to_pdf", fake_render_pdf)

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
    )

    assert "dir" not in capture["kwargs"]
    assert result["outputs"]["pdf"].endswith("demo.pdf")
```

- [ ] **Step 2: Run the targeted tests and verify they fail before the wiring exists**

Run:

```bash
uv run pytest tests/test_doctor.py tests/test_exporter.py -q
```

Expected: FAIL because `doctor.py` does not exist and `run_main()` does not yet accept an argv list or support `doctor`.

- [ ] **Step 3: Implement doctor routing and exporter rewiring**

Create `src/lark_synced_export/doctor.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
import shutil
import subprocess

from .pdf_runtime import check_chromium_ready


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def check_lark_cli() -> DoctorCheck:
    binary = shutil.which("lark-cli")
    if not binary:
        return DoctorCheck(
            name="lark-cli",
            ok=False,
            detail="`lark-cli` is not on PATH. Install/configure it before running exports.",
        )

    try:
        subprocess.run([binary, "--help"], capture_output=True, text=True, check=True)
    except Exception as exc:
        return DoctorCheck(
            name="lark-cli",
            ok=False,
            detail=f"`lark-cli` was found but is not runnable: {exc}",
        )

    return DoctorCheck(name="lark-cli", ok=True, detail=f"`lark-cli` is available at {binary}.")


def check_pdf_runtime() -> DoctorCheck:
    ok, detail = check_chromium_ready()
    return DoctorCheck(name="chromium", ok=ok, detail=detail)


def run_doctor() -> dict:
    checks = [check_lark_cli(), check_pdf_runtime()]
    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
    }
```

Modify `src/lark_synced_export/cli.py` so the top-level control flow becomes:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .doctor import run_doctor
from .exporter import export_document


def parse_export_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand Feishu/Lark synced blocks, export Markdown, and render local PDF."
    )
    parser.add_argument("--doc", required=True, help="Original docx/wiki URL or token accepted by `lark-cli docs +fetch`.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--formats", default="markdown,pdf", help="Comma-separated export formats. Supported: markdown,pdf")
    parser.add_argument("--title-suffix", default="（同步块展开导出）", help="Suffix appended to the temporary expanded doc title.")
    parser.add_argument("--file-stem", default="", help="Optional output filename stem. Defaults to the expanded doc title slug.")
    parser.add_argument("--keep-temp-doc", action="store_true", help="Keep the temporary expanded doc instead of deleting it after the Markdown export step.")
    parser.add_argument("--theme", default="default", help="Built-in PDF theme name. Supported: default, company.")
    parser.add_argument("--css", default="", help="Optional extra CSS file layered on top of the selected theme for PDF output.")
    return parser.parse_args(argv)


def run_main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "doctor":
        print(json.dumps(run_doctor(), ensure_ascii=False, indent=2))
        return 0

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
```

Modify `src/lark_synced_export/exporter.py`:

```python
from .markdown_runtime import render_markdown_body
from .pdf_runtime import render_html_to_pdf
```

Remove these repo-relative constants/functions:

```python
REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = REPO_ROOT / "scripts" / "render_html_to_pdf.mjs"
MARKED_BIN = REPO_ROOT / "node_modules" / ".bin" / "marked"

def ensure_marked_binary() -> Path:
    ...

def render_markdown_to_html_body(markdown_path: Path, body_html: Path) -> None:
    ...

def render_pdf(render_html: Path, output_pdf: Path) -> None:
    ...
```

Replace the temporary directory and render calls in `export_document()`:

```python
with tempfile.TemporaryDirectory(prefix="lark-doc-exporter-") as tmpdir:
    stage_dir = Path(tmpdir)
    ...
    if "pdf" in formats:
        theme_css_path = resolve_theme_css(theme_name)
        body_html = stage_dir / "body.html"
        render_html = stage_dir / "render.html"
        output_pdf = output_dir / f"{final_stem}.pdf"
        render_markdown_body(localized_markdown_path, body_html)
        build_render_html(body_html, render_html, temp_title, theme_css_path, override_css)
        render_html_to_pdf(render_html, output_pdf)
        outputs["pdf"] = str(output_pdf)
```

- [ ] **Step 4: Run the targeted regression tests**

Run:

```bash
uv run pytest tests/test_doctor.py tests/test_exporter.py tests/test_theme_resolution.py -q
```

Expected: PASS. Existing tests should still pass, and the new tempdir/doctor tests should now be green.

- [ ] **Step 5: Commit the exporter/doctor wiring**

```bash
git add src/lark_synced_export/cli.py src/lark_synced_export/doctor.py src/lark_synced_export/exporter.py tests/test_doctor.py tests/test_exporter.py
git commit -S -s -m "refactor(cli): make exporter runnable outside repo"
```

### Task 4: Update packaging docs, remove obsolete Node assets, and validate installed-tool flow

**Files:**
- Modify: `README.md:11-76`
- Delete: `package.json`
- Delete: `package-lock.json`
- Delete: `scripts/render_html_to_pdf.mjs`

- [ ] **Step 1: Rewrite the README around install-first usage**

Update `README.md` so the primary user path becomes:

````md
## Requirements

- `lark-cli` configured with a user session
- Python 3.11+
- A working Chrome/Chromium runtime, or the ability to install one with `uvx --from playwright playwright install chromium`

## Install

```bash
uv tool install git+https://github.com/spencercjh/lark-doc-exporter
lark-doc-exporter doctor
```

If `doctor` reports that Chromium is missing, prepare it with either:

```bash
uvx --from playwright playwright install chromium
```

or a system Chrome/Chromium package on the machine, then rerun:

```bash
lark-doc-exporter doctor
```

## Usage

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

## Development

```bash
uv sync --group dev
uv run pytest
```
````

- [ ] **Step 2: Delete the obsolete repo-local Node runtime files**

Run:

```bash
rm -f package.json package-lock.json scripts/render_html_to_pdf.mjs
```

Expected: those 3 files are gone because runtime no longer depends on repo-local Node assets.

- [ ] **Step 3: Run repo-local regression validation**

Run:

```bash
uv sync --group dev
uv run pytest -q
uv run lark-doc-exporter doctor
uvx --from playwright playwright install chromium
uv run lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir tmp/manual-smoke/installable \
  --formats pdf \
  --theme default
```

Expected:

- full pytest suite passes
- `doctor` returns JSON with `ok: true` after browser prep
- the real-doc smoke export succeeds and writes a PDF under `tmp/manual-smoke/installable`

- [ ] **Step 4: Run installed-tool validation outside the repo checkout**

Run:

```bash
uv build
WHEEL=$(echo /home/azureuser/spencercjh/lark-doc-exporter/dist/*.whl)
TMPDIR=$(mktemp -d)
cd "$TMPDIR"
uv tool install --force "$WHEEL"
lark-doc-exporter --help
lark-doc-exporter doctor
uvx --from playwright playwright install chromium
lark-doc-exporter doctor
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir "$TMPDIR/out" \
  --formats pdf \
  --theme default
```

Expected:

- help works from an installed wheel without repo checkout
- `doctor` clearly reports readiness before and after browser prep
- the real export succeeds from the installed tool
- no step depends on repo-root `scripts/` or `node_modules/`

- [ ] **Step 5: Commit the packaging/docs cleanup**

```bash
git add README.md pyproject.toml uv.lock
git rm -f package.json package-lock.json scripts/render_html_to_pdf.mjs
git commit -S -s -m "docs(dist): switch exporter to installable tool flow"
```

## Self-Review

- Spec coverage:
  - package-local runtime: Task 1 + Task 2 + Task 3
  - no repo-root runtime dependency: Task 3 + Task 4
  - doctor command: Task 3
  - install-first README: Task 4
  - no functional regression: Task 3 + Task 4 validation
  - installed-tool validation outside repo: Task 4
- Placeholder scan: no `TODO` / `TBD` markers remain, and all commands/code snippets are explicit.
- Type consistency:
  - `render_markdown_body()` is introduced once and then reused consistently
  - `render_html_to_pdf()` is introduced once and then reused consistently
  - `run_doctor()` returns a JSON-serializable `dict`
  - `run_main(argv: list[str] | None = None)` is the only CLI entrypoint shape used later

Plan complete and saved to `docs/superpowers/plans/2026-06-27-installable-tool.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
