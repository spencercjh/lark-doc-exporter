# Public Document E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one pure-Python public-document E2E lane for `lark-doc-exporter`, author a stable public fixture document that covers the required Feishu feature set, and wire a dedicated CI workflow that runs the lane when runner auth is available and otherwise skips explicitly.

**Architecture:** Keep the implementation narrow: one case-config module, one pytest entrypoint, one checked-in snapshot tree, and one dedicated workflow. The test should compare only stable result fields plus feature-point snapshot fragments, while live Feishu/Lark dependencies are isolated behind explicit skip gates and a separate workflow instead of entering the default offline test surface.

**Tech Stack:** Python 3.14, `uv`, `pytest`, PyMuPDF (`fitz`), `lark-cli` 1.0.56 (`@larksuite/cli`), GitHub Actions

---

## File Structure

- Create: `tests/public_doc_e2e_case.py`
  Responsibility: one tiny pure-Python config module holding the public doc ref, fixed export args, and the canonical feature-point list.
- Create: `tests/test_public_doc_e2e.py`
  Responsibility: helper functions, offline unit checks for helper behavior, and the single marked live E2E test.
- Create: `tests/e2e_snapshots/public_doc/result.json`
  Responsibility: stable result payload snapshot.
- Create: `tests/e2e_snapshots/public_doc/markdown/*.md`
  Responsibility: markdown fragment snapshots per feature point.
- Create: `tests/e2e_snapshots/public_doc/pdf_text/*.txt`
  Responsibility: extracted-PDF text fragment snapshots per feature point.
- Modify: `pyproject.toml`
  Responsibility: register the `e2e_public_doc` pytest marker.
- Create: `.github/workflows/public-doc-e2e.yml`
  Responsibility: dedicated visible CI workflow that installs `lark-cli`, restores optional auth state, and runs only the public-doc E2E lane.

## Fixture Coverage To Author

The one public fixture document must contain these exact coverage points:

- markdown table
- markdown blockquote
- Feishu callout / highlight block
- one synced-source block referenced twice later in the same document
- one whiteboard block
- one ordinary uploaded image

Use the following exact section structure when creating the fixture document:

1. `Markdown Table`
2. `Markdown Quote`
3. `Callout`
4. `Synced Source`
5. `Synced Block Reference One`
6. `Synced Block Reference Two`
7. `Whiteboard`
8. `Image`

Use these exact canonical texts in the document body:

- table cells:
  - `公开 E2E 表格单元格 A`
  - `公开 E2E 表格单元格 B`
  - `公开 E2E 表格单元格 C`
  - `公开 E2E 表格单元格 D`
- blockquote body:
  - `公开 E2E 引用：这段文字应该以引用形式导出。`
- callout body:
  - `公开 E2E 高亮块：这段文字应该保留为高亮块导出。`
- synced-source body:
  - `公开 E2E 同步块正文：alpha beta gamma。`
- whiteboard caption paragraph:
  - `公开 E2E 画板说明。`
- image caption paragraph:
  - `公开 E2E 图片说明。`

The whiteboard drawing itself should contain the visible label:

- `PUBLIC E2E WHITEBOARD`

## Task 1: Add the case module, helper functions, and offline helper tests

**Files:**
- Create: `tests/public_doc_e2e_case.py`
- Create: `tests/test_public_doc_e2e.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the case module and helper-test skeleton**

Create `tests/public_doc_e2e_case.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturePoint:
    name: str
    markdown_contains_snapshot: str | None = None
    pdf_text_contains_snapshot: str | None = None
    markdown_forbid: tuple[str, ...] = ()
    pdf_forbid: tuple[str, ...] = ()


DOC_REF: str | None = None
FILE_STEM = "public-doc-e2e"
EXPORT_ARGS = {
    "formats": ["markdown", "pdf"],
    "pdf_mode": "native",
    "file_stem": FILE_STEM,
}
FEATURE_POINTS: tuple[FeaturePoint, ...] = ()
```

Create `tests/test_public_doc_e2e.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from public_doc_e2e_case import FeaturePoint


SNAPSHOT_ROOT = Path(__file__).with_name("e2e_snapshots") / "public_doc"


def test_build_stable_result_filters_runtime_fields():
    payload = {
        "ok": True,
        "pdf_mode": "native",
        "pdf_renderer": "feishu-native",
        "localized_images": 2,
        "temp_doc_token": "tmp-token",
        "outputs": {"markdown": "/tmp/demo.md", "pdf": "/tmp/demo.pdf"},
        "ai_footer_postprocess": {"status": "not_found", "warning": None},
    }

    assert build_stable_result(payload) == {
        "ok": True,
        "pdf_mode": "native",
        "pdf_renderer": "feishu-native",
        "localized_images": 2,
        "ai_footer_postprocess.status": "not_found",
    }


def test_normalize_pdf_text_collapses_whitespace():
    assert normalize_pdf_text("A  \\n\\nB\\t\\tC\\n") == "A B C"


def test_assert_feature_point_reports_named_failure(tmp_path: Path):
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "markdown").mkdir(parents=True)
    (snapshot_root / "markdown" / "table.md").write_text(
        "公开 E2E 表格单元格 A", encoding="utf-8"
    )

    feature = FeaturePoint(
        name="markdown_table",
        markdown_contains_snapshot="markdown/table.md",
    )

    with pytest.raises(
        AssertionError, match="feature markdown_table: markdown snapshot missing"
    ):
        assert_feature_point(feature, "other text", "other pdf", snapshot_root)


def build_stable_result(payload: dict[str, object]) -> dict[str, object]:
    raise NotImplementedError


def normalize_pdf_text(text: str) -> str:
    raise NotImplementedError


def load_snapshot(path: Path) -> str:
    raise NotImplementedError


def assert_feature_point(
    feature: FeaturePoint,
    markdown_text: str,
    pdf_text: str,
    snapshot_root: Path = SNAPSHOT_ROOT,
) -> None:
    raise NotImplementedError
```

Modify `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
markers = [
  "e2e_public_doc: runs the live public document export regression lane",
]
```

- [ ] **Step 2: Run the new helper tests and verify they fail**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q
```

Expected: FAIL with `NotImplementedError` from the helper stubs.

- [ ] **Step 3: Implement the pure helper layer**

Replace the helper stubs in `tests/test_public_doc_e2e.py` with:

```python
def build_stable_result(payload: dict[str, object]) -> dict[str, object]:
    ai_footer = payload.get("ai_footer_postprocess") or {}
    return {
        "ok": payload.get("ok"),
        "pdf_mode": payload.get("pdf_mode"),
        "pdf_renderer": payload.get("pdf_renderer"),
        "localized_images": payload.get("localized_images"),
        "ai_footer_postprocess.status": ai_footer.get("status"),
    }


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def load_snapshot(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def assert_feature_point(
    feature: FeaturePoint,
    markdown_text: str,
    pdf_text: str,
    snapshot_root: Path = SNAPSHOT_ROOT,
) -> None:
    if feature.markdown_contains_snapshot:
        expected_markdown = load_snapshot(snapshot_root / feature.markdown_contains_snapshot)
        assert expected_markdown in markdown_text, (
            f"feature {feature.name}: markdown snapshot missing"
        )

    if feature.pdf_text_contains_snapshot:
        expected_pdf = normalize_pdf_text(
            load_snapshot(snapshot_root / feature.pdf_text_contains_snapshot)
        )
        assert expected_pdf in pdf_text, (
            f"feature {feature.name}: pdf text snapshot missing"
        )

    for forbidden in feature.markdown_forbid:
        assert forbidden not in markdown_text, (
            f"feature {feature.name}: forbidden marker {forbidden!r} still present in markdown"
        )

    for forbidden in feature.pdf_forbid:
        assert forbidden not in pdf_text, (
            f"feature {feature.name}: forbidden marker {forbidden!r} found in extracted pdf text"
        )
```

- [ ] **Step 4: Re-run the helper tests and verify they pass**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/public_doc_e2e_case.py tests/test_public_doc_e2e.py
git commit -S -s -m "test(e2e): add public doc helper scaffold"
```

## Task 2: Add live export execution and explicit auth/doc skip gates

**Files:**
- Modify: `tests/test_public_doc_e2e.py`

- [ ] **Step 1: Add failing tests for auth readiness parsing**

Append these tests to `tests/test_public_doc_e2e.py`:

```python
import subprocess
import shutil

from lark_synced_export.cli import run_main


def test_is_lark_cli_user_ready_accepts_needs_refresh(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/lark-cli")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["lark-cli", "auth", "status", "--json"],
            returncode=0,
            stdout=json.dumps(
                {
                    "identities": {
                        "user": {
                            "available": True,
                            "status": "needs_refresh",
                            "message": "User identity: needs refresh",
                        }
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert is_lark_cli_user_ready() == (True, "User identity: needs refresh")


def test_is_lark_cli_user_ready_rejects_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    ok, detail = is_lark_cli_user_ready()

    assert ok is False
    assert "not on PATH" in detail
```

- [ ] **Step 2: Run the auth tests and verify they fail**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q -k "lark_cli_user_ready"
```

Expected: FAIL because `is_lark_cli_user_ready` does not exist yet.

- [ ] **Step 3: Implement auth readiness, PDF extraction, and the live test**

Update `tests/test_public_doc_e2e.py` to add:

```python
import shutil
import subprocess

import fitz

import public_doc_e2e_case as case


def is_lark_cli_user_ready() -> tuple[bool, str]:
    binary = shutil.which("lark-cli")
    if not binary:
        return False, "`lark-cli` is not on PATH"

    proc = subprocess.run(
        ["lark-cli", "auth", "status", "--json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "`lark-cli auth status` failed"

    payload = json.loads(proc.stdout)
    user = payload.get("identities", {}).get("user", {})
    if not user.get("available"):
        return False, user.get("message", "User identity unavailable")
    return True, user.get("message", "User identity ready")


def extract_pdf_text(pdf_path: Path) -> str:
    document = fitz.open(pdf_path)
    try:
        return normalize_pdf_text(
            "\n".join(page.get_text("text") for page in document)
        )
    finally:
        document.close()


@pytest.mark.e2e_public_doc
def test_public_doc_export_e2e(tmp_path: Path, capsys):
    if case.DOC_REF is None:
        pytest.skip("public doc fixture not configured")

    auth_ready, auth_detail = is_lark_cli_user_ready()
    if not auth_ready:
        pytest.skip(f"lark-cli user session not configured for public doc e2e: {auth_detail}")

    output_dir = tmp_path / case.FILE_STEM
    exit_code = run_main(
        [
            "--doc",
            case.DOC_REF,
            "--output-dir",
            str(output_dir),
            "--formats",
            ",".join(case.EXPORT_ARGS["formats"]),
            "--pdf-mode",
            case.EXPORT_ARGS["pdf_mode"],
            "--file-stem",
            case.EXPORT_ARGS["file_stem"],
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    expected_result = json.loads((SNAPSHOT_ROOT / "result.json").read_text(encoding="utf-8"))
    assert build_stable_result(payload) == expected_result

    markdown_path = Path(payload["outputs"]["markdown"])
    pdf_path = Path(payload["outputs"]["pdf"])
    assert markdown_path.is_file()
    assert pdf_path.is_file()

    markdown_text = markdown_path.read_text(encoding="utf-8")
    pdf_text = extract_pdf_text(pdf_path)

    if "localized_images" in expected_result:
        images_dir = output_dir / "images"
        assert images_dir.is_dir()
        assert len(sorted(images_dir.iterdir())) == expected_result["localized_images"]

    for feature in case.FEATURE_POINTS:
        assert_feature_point(feature, markdown_text, pdf_text)
```

- [ ] **Step 4: Verify offline tests pass and the live lane skips cleanly**

Run the offline portion:

```bash
uv run pytest tests/test_public_doc_e2e.py -q -k "not public_doc_export_e2e"
```

Expected: PASS.

Run the live marker before a real `DOC_REF` is configured:

```bash
uv run pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc
```

Expected: `1 skipped` with `public doc fixture not configured`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_public_doc_e2e.py
git commit -S -s -m "test(e2e): add public doc live export path"
```

## Task 3: Add the dedicated public-doc workflow

**Files:**
- Create: `.github/workflows/public-doc-e2e.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/public-doc-e2e.yml`:

```yaml
name: public-doc-e2e

on:
  workflow_dispatch:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  public-doc-e2e:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7
        with:
          fetch-depth: 1
          ref: ${{ github.event.pull_request.head.sha || github.sha }}

      - name: Set up Node.js
        uses: actions/setup-node@v5
        with:
          node-version: "22"

      - name: Install lark-cli
        run: npm install -g @larksuite/cli@1.0.56

      - name: Restore lark-cli home
        if: ${{ secrets.LARK_CLI_HOME_B64 != '' }}
        shell: bash
        run: |
          printf '%s' '${{ secrets.LARK_CLI_HOME_B64 }}' | base64 -d > /tmp/lark-cli-home.tgz
          tar -xzf /tmp/lark-cli-home.tgz -C "$HOME"

      - name: Show lark-cli auth status
        shell: bash
        run: |
          lark-cli auth status --json || true

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Set up uv
        uses: astral-sh/setup-uv@v8.2.0
        with:
          enable-cache: true

      - name: Sync dev dependencies
        run: uv sync --python 3.14 --group dev

      - name: Run public-doc e2e
        run: uv run pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc
```

- [ ] **Step 2: Sanity-check the workflow file structure**

Run:

```bash
python - <<'PY'
from pathlib import Path

workflow = Path(".github/workflows/public-doc-e2e.yml").read_text(encoding="utf-8")
required = [
    "name: public-doc-e2e",
    "npm install -g @larksuite/cli@1.0.56",
    "LARK_CLI_HOME_B64",
    "pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc",
]
for needle in required:
    assert needle in workflow, needle
PY
```

Expected: no output, exit `0`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/public-doc-e2e.yml
git commit -S -s -m "ci(e2e): add public doc workflow"
```

## Task 4: Author the public fixture document and lock the case config

**Files:**
- Modify: `tests/public_doc_e2e_case.py`

- [ ] **Step 1: Generate a tiny local PNG for the fixture image**

Run:

```bash
python - <<'PY'
import base64
from pathlib import Path

png_b64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAMgAAABQCAIAAADTD63nAAAAyUlEQVR4nO3SQQ3AIBDAsAP/nuGN"
    "AvZoFSzZOjNnyNi/A3g1C2EWwiyEWQizEGYhzEKYhTALYRbCLIRZCLMQZiHMQpiFMAthFsIshFkI"
    "sxBmIcxCmIUwC2EWwiyEWQizEGYhzEKYhTALYRbCLIRZCLMQZiHMQpiFMAthFsIshFkIsxBmIcxC"
    "mIUwC2EWwiyEWQizEGYhzEKYhTALYRbCLIRZCLMQZiHMQpiFMAthFsIshFkIs9B6AQ3zB56M1wAA"
    "AABJRU5ErkJggg=="
)
path = Path("/tmp/public-doc-e2e-image.png")
path.write_bytes(base64.b64decode(png_b64))
print(path)
PY
```

Expected: prints `/tmp/public-doc-e2e-image.png`.

- [ ] **Step 2: Create the base document content**

Run:

```bash
lark-cli docs +create --as user --api-version v2 --content '
<title>lark-doc-exporter Public E2E Fixture</title>
<h1>Markdown Table</h1>
<table>
  <tr><th>Feature</th><th>Value</th></tr>
  <tr><td>公开 E2E 表格单元格 A</td><td>公开 E2E 表格单元格 B</td></tr>
  <tr><td>公开 E2E 表格单元格 C</td><td>公开 E2E 表格单元格 D</td></tr>
</table>
<h1>Markdown Quote</h1>
<blockquote><p>公开 E2E 引用：这段文字应该以引用形式导出。</p></blockquote>
<h1>Callout</h1>
<callout emoji="📌"><p>公开 E2E 高亮块：这段文字应该保留为高亮块导出。</p></callout>
<h1>Synced Source</h1>
<p>公开 E2E 同步块正文：alpha beta gamma。</p>
<h1>Synced Block Reference One</h1>
<p>这里后面要插入第一处同步块引用。</p>
<h1>Synced Block Reference Two</h1>
<p>这里后面要插入第二处同步块引用。</p>
<h1>Whiteboard</h1>
<whiteboard type="blank"></whiteboard>
<p>公开 E2E 画板说明。</p>
<h1>Image</h1>
<p>公开 E2E 图片说明。</p>
' --json > /tmp/public-doc-e2e-create.json
python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/public-doc-e2e-create.json").read_text(encoding="utf-8"))
doc_ref = payload["data"]["url"]
Path("/tmp/public-doc-e2e-doc-ref.txt").write_text(doc_ref, encoding="utf-8")
print(doc_ref)
PY
```

Expected: prints the new document URL and stores it in `/tmp/public-doc-e2e-doc-ref.txt`.

- [ ] **Step 3: Finish the fixture document in Feishu**

Use the returned document URL and complete these exact one-time edits:

- convert the `Synced Source` paragraph into a synced-source block
- insert that synced block again under `Synced Block Reference One`
- insert that synced block again under `Synced Block Reference Two`
- keep the callout block as a real Feishu highlighter/callout block
- update the blank whiteboard so it contains the label `PUBLIC E2E WHITEBOARD`
- insert `/tmp/public-doc-e2e-image.png` after the `Image` section caption

Use these commands for the non-text assets:

```bash
DOC_REF="$(cat /tmp/public-doc-e2e-doc-ref.txt)"
lark-cli docs +media-insert \
  --as user \
  --doc "$DOC_REF" \
  --file /tmp/public-doc-e2e-image.png \
  --selection-with-ellipsis 'Image...公开 E2E 图片说明。' \
  --caption '公开 E2E 图片说明。' \
  --json
```

After the blank whiteboard exists, fetch the whiteboard token from the document XML and update it:

```bash
DOC_REF="$(cat /tmp/public-doc-e2e-doc-ref.txt)"
lark-cli docs +fetch --as user --api-version v2 --doc "$DOC_REF" --detail full --format json > /tmp/public-doc-e2e-whiteboard.json
python - <<'PY'
import json
import re
from pathlib import Path

payload = json.loads(Path("/tmp/public-doc-e2e-whiteboard.json").read_text(encoding="utf-8"))
xml = payload["data"]["document"]["content"]
match = re.search(r'<whiteboard[^>]*token="([^"]+)"', xml)
if not match:
    raise SystemExit("could not find whiteboard token in authored fixture doc")
token = match.group(1)
Path("/tmp/public-doc-e2e-whiteboard-token.txt").write_text(token, encoding="utf-8")
print(token)
PY
```

Then run:

```bash
WHITEBOARD_TOKEN="$(cat /tmp/public-doc-e2e-whiteboard-token.txt)"
lark-cli docs +whiteboard-update \
  --as user \
  --whiteboard-token "$WHITEBOARD_TOKEN" \
  --input_format mermaid \
  --overwrite \
  --source 'flowchart TD
    A[PUBLIC E2E WHITEBOARD] --> B[OK]
  ' \
  --json
```

- [ ] **Step 4: Verify the authored document contains the intended rich blocks**

Run:

```bash
DOC_REF="$(cat /tmp/public-doc-e2e-doc-ref.txt)"
lark-cli docs +fetch --as user --api-version v2 --doc "$DOC_REF" --detail full --format json > /tmp/public-doc-e2e-fixture.json
python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/public-doc-e2e-fixture.json").read_text(encoding="utf-8"))
xml = payload["data"]["document"]["content"]
assert "<table>" in xml
assert "<blockquote>" in xml
assert "<callout" in xml
assert xml.count("<synced_reference") >= 2
assert "<synced-source" in xml
assert "<whiteboard" in xml
assert "<img " in xml or "<source " in xml
PY
```

Expected: no output, exit `0`.

- [ ] **Step 5: Update `tests/public_doc_e2e_case.py` with the final fixture config**

Run:

```bash
DOC_REF="$(cat /tmp/public-doc-e2e-doc-ref.txt)"
python - <<'PY'
import os
from pathlib import Path

path = Path("tests/public_doc_e2e_case.py")
path.write_text(
    f'''from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturePoint:
    name: str
    markdown_contains_snapshot: str | None = None
    pdf_text_contains_snapshot: str | None = None
    markdown_forbid: tuple[str, ...] = ()
    pdf_forbid: tuple[str, ...] = ()


DOC_REF = "{os.environ["DOC_REF"]}"
FILE_STEM = "public-doc-e2e"
EXPORT_ARGS = {{
    "formats": ["markdown", "pdf"],
    "pdf_mode": "native",
    "file_stem": FILE_STEM,
}}
FEATURE_POINTS = (
    FeaturePoint(
        name="markdown_table",
        markdown_contains_snapshot="markdown/table.md",
        pdf_text_contains_snapshot="pdf_text/table.txt",
    ),
    FeaturePoint(
        name="markdown_quote",
        markdown_contains_snapshot="markdown/blockquote.md",
        pdf_text_contains_snapshot="pdf_text/blockquote.txt",
    ),
    FeaturePoint(
        name="callout",
        markdown_contains_snapshot="markdown/callout.md",
        pdf_text_contains_snapshot="pdf_text/callout.txt",
        markdown_forbid=("<callout",),
    ),
    FeaturePoint(
        name="synced_block_reference_one",
        markdown_contains_snapshot="markdown/synced_block_reference_one.md",
        pdf_text_contains_snapshot="pdf_text/synced_block_reference_one.txt",
        markdown_forbid=("<synced_reference", "<synced-source"),
    ),
    FeaturePoint(
        name="synced_block_reference_two",
        markdown_contains_snapshot="markdown/synced_block_reference_two.md",
        pdf_text_contains_snapshot="pdf_text/synced_block_reference_two.txt",
        markdown_forbid=("<synced_reference", "<synced-source"),
    ),
    FeaturePoint(
        name="whiteboard",
        markdown_contains_snapshot="markdown/whiteboard.md",
        pdf_forbid=("<whiteboard",),
    ),
    FeaturePoint(
        name="image",
        markdown_contains_snapshot="markdown/image.md",
        pdf_text_contains_snapshot="pdf_text/image.txt",
        markdown_forbid=("authcode/?code=",),
    ),
)
''',
    encoding="utf-8",
)
PY
```

- [ ] **Step 6: Commit**

```bash
git add tests/public_doc_e2e_case.py
git commit -S -s -m "test(e2e): lock public doc fixture case"
```

## Task 5: Capture snapshots from a real successful export and make the lane pass

**Files:**
- Create: `tests/e2e_snapshots/public_doc/result.json`
- Create: `tests/e2e_snapshots/public_doc/markdown/table.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/blockquote.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/callout.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/synced_block_reference_one.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/synced_block_reference_two.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/whiteboard.md`
- Create: `tests/e2e_snapshots/public_doc/markdown/image.md`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/table.txt`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/blockquote.txt`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/callout.txt`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/synced_block_reference_one.txt`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/synced_block_reference_two.txt`
- Create: `tests/e2e_snapshots/public_doc/pdf_text/image.txt`

- [ ] **Step 1: Run one real local export against the new fixture**

Run:

```bash
rm -rf /tmp/public-doc-e2e-out
DOC_REF="$(cat /tmp/public-doc-e2e-doc-ref.txt)"
uv run lark-doc-exporter \
  --doc "$DOC_REF" \
  --output-dir /tmp/public-doc-e2e-out \
  --formats markdown,pdf \
  --pdf-mode native \
  --file-stem public-doc-e2e
```

Expected: exit `0`, plus `/tmp/public-doc-e2e-out/public-doc-e2e.md`, `/tmp/public-doc-e2e-out/public-doc-e2e.pdf`, and `/tmp/public-doc-e2e-out/images/`.

- [ ] **Step 2: Write the stable result snapshot**

Create `tests/e2e_snapshots/public_doc/result.json`:

```json
{
  "ok": true,
  "pdf_mode": "native",
  "pdf_renderer": "feishu-native",
  "localized_images": 2,
  "ai_footer_postprocess.status": "not_found"
}
```

- [ ] **Step 3: Create the markdown fragment snapshots from the real export**

Create:

- `tests/e2e_snapshots/public_doc/markdown/table.md`
- `tests/e2e_snapshots/public_doc/markdown/blockquote.md`
- `tests/e2e_snapshots/public_doc/markdown/callout.md`
- `tests/e2e_snapshots/public_doc/markdown/synced_block_reference_one.md`
- `tests/e2e_snapshots/public_doc/markdown/synced_block_reference_two.md`
- `tests/e2e_snapshots/public_doc/markdown/whiteboard.md`
- `tests/e2e_snapshots/public_doc/markdown/image.md`

Each file must contain the exact fragment copied from `/tmp/public-doc-e2e-out/public-doc-e2e.md` that proves that feature exported correctly. Use these anchors when trimming:

- `table.md`: the `Markdown Table` heading plus the two-row table
- `blockquote.md`: the `Markdown Quote` heading plus the quoted sentence
- `callout.md`: the `Callout` heading plus the normalized callout block
- `synced_block_reference_one.md`: the first synced-reference heading plus the expanded synced text
- `synced_block_reference_two.md`: the second synced-reference heading plus the expanded synced text
- `whiteboard.md`: the `Whiteboard` heading plus the localized markdown image link / caption
- `image.md`: the `Image` heading plus the localized markdown image link / caption

- [ ] **Step 4: Create the PDF text fragment snapshots from the real export**

Extract the final PDF text once:

```bash
python - <<'PY'
import fitz
from pathlib import Path

pdf = Path("/tmp/public-doc-e2e-out/public-doc-e2e.pdf")
doc = fitz.open(pdf)
try:
    text = "\n".join(page.get_text("text") for page in doc)
finally:
    doc.close()
Path("/tmp/public-doc-e2e-out/public-doc-e2e.txt").write_text(text, encoding="utf-8")
PY
```

Then create:

- `tests/e2e_snapshots/public_doc/pdf_text/table.txt`
- `tests/e2e_snapshots/public_doc/pdf_text/blockquote.txt`
- `tests/e2e_snapshots/public_doc/pdf_text/callout.txt`
- `tests/e2e_snapshots/public_doc/pdf_text/synced_block_reference_one.txt`
- `tests/e2e_snapshots/public_doc/pdf_text/synced_block_reference_two.txt`
- `tests/e2e_snapshots/public_doc/pdf_text/image.txt`

Each file must contain the exact text fragment copied from `/tmp/public-doc-e2e-out/public-doc-e2e.txt` that proves the feature is present in the final PDF text extraction.

Do **not** create a whiteboard PDF text snapshot unless the exported PDF text actually contains a stable whiteboard-specific textual marker. For whiteboard, markdown snapshot plus `localized_images == 2` is enough in v1.

- [ ] **Step 5: Run the live E2E lane and verify it passes**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc
```

Expected: `1 passed`.

- [ ] **Step 6: Run the default repo gate to prove the new lane stayed isolated**

Run:

```bash
make ci
```

Expected: PASS, with the new online E2E lane still excluded from the default offline gate.

- [ ] **Step 7: Commit**

```bash
git add tests/e2e_snapshots/public_doc tests/public_doc_e2e_case.py tests/test_public_doc_e2e.py
git commit -S -s -m "test(e2e): add public doc snapshots"
```

## Task 6: Final review handoff

**Files:**
- Modify: none

- [ ] **Step 1: Capture final validation commands/results for reviewers**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc
make ci
git status --short
```

Expected:

- live public-doc E2E passes locally
- default offline CI passes
- git status is clean

- [ ] **Step 2: Ask at least one other agent to review the implementation branch**

Post in the task thread with:

```text
Public-doc E2E implementation is ready for review. Please review:
- public fixture case/config
- snapshot coverage
- dedicated workflow
- live/skip gating in tests
```

- [ ] **Step 3: Commit any review-driven follow-ups**

```bash
git add tests/public_doc_e2e_case.py tests/test_public_doc_e2e.py tests/e2e_snapshots/public_doc .github/workflows/public-doc-e2e.yml pyproject.toml
git commit -S -s -m "fix(e2e): address review feedback"
```
