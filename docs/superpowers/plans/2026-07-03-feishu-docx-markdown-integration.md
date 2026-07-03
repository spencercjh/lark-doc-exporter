# Feishu-docx Markdown Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `feishu-docx` the preferred Markdown exporter for `lark-doc-exporter`, keep the current CLI surface stable, preserve the native-PDF lane, and fall back to the legacy `lark-cli` Markdown flow only when `feishu-docx` is unavailable in `auto` mode.

**Architecture:** Add one narrow bridge module that owns provider selection, credential discovery, `feishu-docx` invocation, and asset-layout normalization. Then rewire `export_document()` so Markdown and rendered-PDF artifacts come from the selected provider while temp-doc creation remains only for the legacy Markdown path or the existing native-PDF lane. Surface the active Markdown provider in the JSON result and `doctor`, then update the README / bundled skill docs / third-party notice so operators know how to enable the preferred path.

**Tech Stack:** Python 3.14, `uv`, `pytest`, `setuptools`, `lark-cli`, `feishu-docx` (Git pin), Markdown file rewriting, JSON-based doctor output

---

## File Structure

- Create: `src/lark_synced_export/feishu_docx_bridge.py`
  Responsibility: provider selection, `FEISHU_*` / `~/.feishu-docx/config.json` credential discovery, lazy `feishu-docx` import, export staging, and asset-layout normalization from `<stem>/` to `images/`.
- Modify: `src/lark_synced_export/exporter.py`
  Responsibility: call the bridge for Markdown/rendered-PDF artifacts, keep the current native-PDF temp-doc flow, and report provider metadata in the JSON payload.
- Modify: `src/lark_synced_export/doctor.py`
  Responsibility: add an optional `feishu-docx` readiness check without making it required for the overall doctor result.
- Modify: `src/lark_synced_export/cli.py`
  Responsibility: keep the existing CLI surface stable while allowing the exporter result to expose the selected provider.
- Modify: `pyproject.toml`
  Responsibility: add a Git-pinned `feishu-docx` dependency for the synced-block-capable upstream revision.
- Create: `tests/test_feishu_docx_bridge.py`
  Responsibility: unit-test credential discovery, provider selection, forced-provider failures, and asset-layout normalization without live Feishu access.
- Modify: `tests/test_exporter.py`
  Responsibility: cover `auto` fallback, forced `feishu-docx`, and the no-temp-doc Markdown/rendered path.
- Modify: `tests/test_doctor.py`
  Responsibility: pin the new optional doctor check contract.
- Modify: `README.md`
  Responsibility: document provider selection, `FEISHU_*` credential discovery, and the mixed Markdown/PDF pipeline rules.
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
  Responsibility: keep the bundled companion skill aligned with the new preferred Markdown provider.
- Create: `THIRD_PARTY_NOTICES.md`
  Responsibility: record the integrated `feishu-docx` project and its MIT attribution.
- Modify: `tests/test_skill_install.py`
  Responsibility: keep the bundled-skill text contract pinned after the docs update.

## Provider Contract

The implementation should settle on this exact operator surface:

- default behavior: `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=auto`
- explicit override values: `auto`, `feishu-docx`, `legacy`
- credential discovery for `feishu-docx`:
  - `FEISHU_APP_ID`
  - `FEISHU_APP_SECRET`
  - optional `FEISHU_AUTH_MODE`
  - optional `FEISHU_IS_LARK`
  - fallback config file: `~/.feishu-docx/config.json`
- `auto` mode:
  - prefer `feishu-docx` only when both the package import and credentials are available
  - otherwise fall back to `legacy`
- `feishu-docx` mode:
  - fail fast if the package import fails
  - fail fast if credentials/config are missing
- `legacy` mode:
  - force the current temp-doc + `lark-cli` Markdown flow

## Result Contract

Extend the exporter result with these exact fields:

- `markdown_provider`: `"feishu-docx"` or `"legacy"`
- `markdown_provider_detail`: short human-readable detail such as `"auto:selected from env"` or `"auto:fallback to legacy (missing FEISHU_APP_ID/FEISHU_APP_SECRET)"`.

Do **not** remove the existing keys. If no temp doc is created because the selected provider is `feishu-docx` and `--pdf-mode native` is not in play, return:

- `expanded_references: None`
- `temp_doc_token: None`
- `temp_doc_url: None`
- `temp_doc_deleted: True`

When native PDF still needs the temp-doc lane, keep the existing temp-doc fields populated.

### Task 1: Add the `feishu-docx` bridge module and its focused unit tests

**Files:**
- Create: `src/lark_synced_export/feishu_docx_bridge.py`
- Create: `tests/test_feishu_docx_bridge.py`

- [ ] **Step 1: Write the failing bridge tests**

Create `tests/test_feishu_docx_bridge.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lark_synced_export.feishu_docx_bridge import (
    FEISHU_DOCX_CONFIG_PATH,
    MARKDOWN_PROVIDER_ENV,
    FeishuDocxCredentials,
    normalize_feishu_docx_assets,
    resolve_markdown_provider,
)


def test_resolve_markdown_provider_auto_uses_env_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_secret")
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )

    selection = resolve_markdown_provider("https://example.feishu.cn/docx/abc")

    assert selection.provider == "feishu-docx"
    assert selection.detail == "auto:selected from env"
    assert selection.credentials == FeishuDocxCredentials(
        app_id="cli_app",
        app_secret="cli_secret",
        auth_mode="tenant",
        is_lark=False,
        source="env",
    )


def test_resolve_markdown_provider_auto_falls_back_when_credentials_missing(
    monkeypatch,
):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        Path("/tmp/does-not-exist"),
    )

    selection = resolve_markdown_provider("https://example.feishu.cn/docx/abc")

    assert selection.provider == "legacy"
    assert selection.detail.startswith("auto:fallback to legacy")
    assert selection.credentials is None


def test_resolve_markdown_provider_forced_feishu_docx_requires_credentials(
    monkeypatch,
):
    monkeypatch.setenv(MARKDOWN_PROVIDER_ENV, "feishu-docx")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        Path("/tmp/does-not-exist"),
    )

    with pytest.raises(RuntimeError, match="feishu-docx provider requires"):
        resolve_markdown_provider("https://example.feishu.cn/docx/abc")


def test_resolve_markdown_provider_reads_config_file(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_id": "cfg_app",
                "app_secret": "cfg_secret",
                "auth_mode": "oauth",
                "is_lark": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )

    selection = resolve_markdown_provider("https://example.larksuite.com/docx/abc")

    assert selection.provider == "feishu-docx"
    assert selection.detail == "auto:selected from config"
    assert selection.credentials == FeishuDocxCredentials(
        app_id="cfg_app",
        app_secret="cfg_secret",
        auth_mode="oauth",
        is_lark=True,
        source="config",
    )


def test_normalize_feishu_docx_assets_moves_links_into_images(tmp_path: Path):
    raw_markdown = tmp_path / "demo.md"
    raw_markdown.write_text(
        "![image](demo/pic.png)\\n\\n📎 [report.pdf](demo/report.pdf)\\n",
        encoding="utf-8",
    )
    raw_assets = tmp_path / "demo"
    raw_assets.mkdir()
    (raw_assets / "pic.png").write_bytes(b"png")
    (raw_assets / "report.pdf").write_bytes(b"pdf")
    final_markdown = tmp_path / "final.md"
    final_assets = tmp_path / "images"

    localized_count = normalize_feishu_docx_assets(
        markdown_path=raw_markdown,
        raw_assets_dir=raw_assets,
        localized_path=final_markdown,
        target_assets_dir=final_assets,
    )

    assert localized_count == 1
    assert final_markdown.read_text(encoding="utf-8") == (
        "![image](images/pic.png)\\n\\n📎 [report.pdf](images/report.pdf)\\n"
    )
    assert (final_assets / "pic.png").read_bytes() == b"png"
    assert (final_assets / "report.pdf").read_bytes() == b"pdf"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest tests/test_feishu_docx_bridge.py -q
```

Expected: FAIL with `ModuleNotFoundError` because `lark_synced_export.feishu_docx_bridge` does not exist yet.

- [ ] **Step 3: Implement the bridge module**

Create `src/lark_synced_export/feishu_docx_bridge.py`:

```python
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


MARKDOWN_PROVIDER_ENV = "LARK_DOC_EXPORTER_MARKDOWN_PROVIDER"
FEISHU_DOCX_CONFIG_PATH = Path.home() / ".feishu-docx" / "config.json"


@dataclass(frozen=True)
class FeishuDocxCredentials:
    app_id: str
    app_secret: str
    auth_mode: str
    is_lark: bool
    source: str


@dataclass(frozen=True)
class MarkdownProviderSelection:
    provider: str
    detail: str
    credentials: FeishuDocxCredentials | None = None


def import_feishu_docx_exporter():
    from feishu_docx.core.exporter import FeishuExporter

    return FeishuExporter


def _parse_bool_env(raw: str | None) -> bool:
    if not raw:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _infer_is_lark(doc_ref: str) -> bool:
    host = urlparse(doc_ref).netloc.lower()
    return "larksuite" in host or "larkoffice" in host


def discover_feishu_docx_credentials(doc_ref: str) -> FeishuDocxCredentials | None:
    env_app_id = os.getenv("FEISHU_APP_ID")
    env_app_secret = os.getenv("FEISHU_APP_SECRET")
    if env_app_id and env_app_secret:
        return FeishuDocxCredentials(
            app_id=env_app_id,
            app_secret=env_app_secret,
            auth_mode=os.getenv("FEISHU_AUTH_MODE") or "tenant",
            is_lark=_parse_bool_env(os.getenv("FEISHU_IS_LARK")) or _infer_is_lark(doc_ref),
            source="env",
        )

    if not FEISHU_DOCX_CONFIG_PATH.is_file():
        return None

    payload = json.loads(FEISHU_DOCX_CONFIG_PATH.read_text(encoding="utf-8"))
    app_id = payload.get("app_id")
    app_secret = payload.get("app_secret")
    if not app_id or not app_secret:
        return None

    return FeishuDocxCredentials(
        app_id=app_id,
        app_secret=app_secret,
        auth_mode=payload.get("auth_mode") or "tenant",
        is_lark=bool(payload.get("is_lark", False)) or _infer_is_lark(doc_ref),
        source="config",
    )


def resolve_markdown_provider(doc_ref: str) -> MarkdownProviderSelection:
    mode = (os.getenv(MARKDOWN_PROVIDER_ENV) or "auto").strip().lower()
    if mode not in {"auto", "feishu-docx", "legacy"}:
        raise ValueError(
            f"{MARKDOWN_PROVIDER_ENV} must be auto, feishu-docx, or legacy; got {mode!r}"
        )
    if mode == "legacy":
        return MarkdownProviderSelection("legacy", "forced:legacy")

    try:
        import_feishu_docx_exporter()
    except ModuleNotFoundError as exc:
        if mode == "feishu-docx":
            raise RuntimeError("feishu-docx provider requires the feishu-docx package") from exc
        return MarkdownProviderSelection(
            "legacy",
            "auto:fallback to legacy (feishu-docx package unavailable)",
        )

    credentials = discover_feishu_docx_credentials(doc_ref)
    if credentials is None:
        if mode == "feishu-docx":
            raise RuntimeError(
                "feishu-docx provider requires FEISHU_APP_ID/FEISHU_APP_SECRET "
                "or ~/.feishu-docx/config.json"
            )
        return MarkdownProviderSelection(
            "legacy",
            "auto:fallback to legacy (missing FEISHU_APP_ID/FEISHU_APP_SECRET)",
        )

    detail = "auto:selected from env" if credentials.source == "env" else "auto:selected from config"
    return MarkdownProviderSelection("feishu-docx", detail, credentials)


def export_markdown_with_feishu_docx(
    doc_ref: str,
    stage_dir: Path,
    file_stem: str,
    credentials: FeishuDocxCredentials,
) -> tuple[Path, Path | None]:
    FeishuExporter = import_feishu_docx_exporter()
    exporter = FeishuExporter(
        app_id=credentials.app_id,
        app_secret=credentials.app_secret,
        is_lark=credentials.is_lark,
        auth_mode=credentials.auth_mode,
    )
    markdown_path = Path(
        exporter.export(
            url=doc_ref,
            output_dir=stage_dir,
            filename=file_stem,
            silent=True,
        )
    )
    raw_assets_dir = stage_dir / file_stem
    return markdown_path, raw_assets_dir if raw_assets_dir.exists() else None


def normalize_feishu_docx_assets(
    markdown_path: Path,
    raw_assets_dir: Path | None,
    localized_path: Path,
    target_assets_dir: Path,
) -> int:
    text = markdown_path.read_text(encoding="utf-8")
    localized_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_assets_dir and raw_assets_dir.is_dir():
        target_assets_dir.mkdir(parents=True, exist_ok=True)
        for child in raw_assets_dir.iterdir():
            if child.is_file():
                shutil.copy2(child, target_assets_dir / child.name)
        text = text.replace(f"]({raw_assets_dir.name}/", "](images/")

    localized_path.write_text(text, encoding="utf-8")
    return text.count("![") 
```

- [ ] **Step 4: Run the bridge tests and verify they pass**

Run:

```bash
uv run pytest tests/test_feishu_docx_bridge.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lark_synced_export/feishu_docx_bridge.py tests/test_feishu_docx_bridge.py
git commit -S -s -m "feat(exporter): add feishu-docx markdown bridge"
```

### Task 2: Rewire `export_document()` and `doctor` around the provider boundary

**Files:**
- Modify: `src/lark_synced_export/exporter.py`
- Modify: `src/lark_synced_export/doctor.py`
- Modify: `src/lark_synced_export/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_exporter.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Add the failing exporter and doctor tests**

Append to `tests/test_exporter.py`:

```python
def test_export_document_auto_falls_back_to_legacy_when_feishu_docx_unavailable(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text("# Demo\\n", encoding="utf-8")

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.delenv("LARK_DOC_EXPORTER_MARKDOWN_PROVIDER", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.exporter.resolve_markdown_provider",
        lambda _doc: type(
            "Selection",
            (),
            {"provider": "legacy", "detail": "auto:fallback to legacy (missing creds)"},
        )(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *a, **k: DummyTempDir(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml",
        lambda _doc, _identity: "<title>Demo</title>",
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references",
        lambda xml, _identity: (xml, 0),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda _xml, _stage, _identity: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda _token, _stage, _stem, _identity: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images",
        lambda _src, dst, _assets: dst.write_text("# Demo\\n", encoding="utf-8") or 0,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, _identity: None,
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["markdown"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
    )

    assert result["markdown_provider"] == "legacy"
    assert result["markdown_provider_detail"].startswith("auto:fallback")
    assert result["temp_doc_token"] == "tmp-token"


def test_export_document_forced_feishu_docx_skips_temp_doc_for_markdown_only(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text("![image](demo/pic.png)\\n", encoding="utf-8")
    raw_assets_dir = stage_dir / "demo"
    raw_assets_dir.mkdir()
    (raw_assets_dir / "pic.png").write_bytes(b"png")

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "lark_synced_export.exporter.resolve_markdown_provider",
        lambda _doc: type(
            "Selection",
            (),
            {
                "provider": "feishu-docx",
                "detail": "auto:selected from env",
                "credentials": object(),
            },
        )(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *a, **k: DummyTempDir(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _creds: (raw_markdown_path, raw_assets_dir),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda _src, _raw_assets, dst, images: dst.write_text(
            "![image](images/pic.png)\\n", encoding="utf-8"
        )
        or (images.mkdir(parents=True, exist_ok=True), (images / "pic.png").write_bytes(b"png"), 1)[-1],
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["markdown"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
    )

    assert result["markdown_provider"] == "feishu-docx"
    assert result["expanded_references"] is None
    assert result["temp_doc_token"] is None
    assert result["outputs"]["markdown"].endswith("demo.md")
```

Append to `tests/test_doctor.py`:

```python
def test_run_doctor_reports_optional_feishu_docx_check(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_lark_cli",
        lambda: DoctorCheck(name="lark-cli", ok=True, detail="ok", required=True),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_pdf_runtime",
        lambda: DoctorCheck(name="chromium", ok=True, detail="ok", required=False),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_feishu_docx_markdown",
        lambda: DoctorCheck(name="feishu-docx-markdown", ok=False, detail="missing creds", required=False),
    )

    payload = run_doctor()

    assert payload["ok"] is True
    assert payload["checks"][-1] == {
        "name": "feishu-docx-markdown",
        "ok": False,
        "detail": "missing creds",
        "required": False,
    }
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
uv run pytest tests/test_feishu_docx_bridge.py tests/test_exporter.py tests/test_doctor.py -q
```

Expected: FAIL because `exporter.py` and `doctor.py` still do not expose the bridge behavior.

- [ ] **Step 3: Add the dependency and wire the provider into the exporter**

Modify `pyproject.toml`:

```toml
[project]
dependencies = [
  "feishu-docx @ git+https://github.com/spencercjh/feishu-docx@7517b56",
  "markdown>=3.7,<4",
  "playwright>=1.61.0,<2",
  "pymupdf>=1.26,<2",
]
```

Update the imports at the top of `src/lark_synced_export/exporter.py`:

```python
from .feishu_docx_bridge import (
    export_markdown_with_feishu_docx,
    normalize_feishu_docx_assets,
    resolve_markdown_provider,
)
```

Replace the body of `export_document()` with this provider-aware structure:

```python
def export_document(
    doc_ref: str,
    output_dir: Path,
    formats: list[str],
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    theme_name: str,
    override_css: Path | None,
    pdf_mode: str = "rendered",
) -> dict:
    if pdf_mode not in {"rendered", "native"}:
        raise ValueError(f"unsupported pdf_mode: {pdf_mode}")
    if override_css and not override_css.is_file():
        raise FileNotFoundError(f"override CSS not found: {override_css}")

    output_dir.mkdir(parents=True, exist_ok=True)
    lark_cli_identity = resolve_lark_cli_identity()
    provider = resolve_markdown_provider(doc_ref)

    outputs: dict[str, str] = {}
    warnings: list[str] = []
    ai_footer_postprocess: dict | None = None
    localized_image_count = 0
    theme_css_path: Path | None = None
    expanded_count: int | None = None
    temp_doc_token: str | None = None
    temp_doc_url: str | None = None
    temp_doc_deleted = True
    temp_title = file_stem or "export"

    with tempfile.TemporaryDirectory(prefix="lark-doc-exporter-") as tmpdir:
        stage_dir = Path(tmpdir)
        needs_markdown_artifacts = "markdown" in formats or (
            "pdf" in formats and pdf_mode == "rendered"
        )
        needs_legacy_temp_doc = provider.provider == "legacy" and needs_markdown_artifacts
        needs_native_temp_doc = "pdf" in formats and pdf_mode == "native"
        needs_temp_doc = needs_legacy_temp_doc or needs_native_temp_doc
        localized_markdown_path: Path | None = None

        if needs_markdown_artifacts:
            render_root = output_dir if "markdown" in formats else stage_dir
            localized_markdown_path = render_root / f"{file_stem or 'export'}.md"
            assets_dir = render_root / "images"

            if provider.provider == "feishu-docx":
                raw_markdown_path, raw_assets_dir = export_markdown_with_feishu_docx(
                    doc_ref,
                    stage_dir,
                    file_stem or "export",
                    provider.credentials,
                )
                localized_image_count = normalize_feishu_docx_assets(
                    raw_markdown_path,
                    raw_assets_dir,
                    localized_markdown_path,
                    assets_dir,
                )
            else:
                raw_xml = fetch_full_xml(doc_ref, lark_cli_identity)
                expanded_xml, expanded_count = expand_synced_references(raw_xml, lark_cli_identity)
                normalized_xml, temp_title = normalize_xml_for_create(expanded_xml, title_suffix)
                final_stem = file_stem or slugify_filename(temp_title)
                localized_markdown_path = render_root / f"{final_stem}.md"
                temp_doc_token, temp_doc_url = create_temp_doc(normalized_xml, stage_dir, lark_cli_identity)
                temp_doc_deleted = not keep_temp_doc
                raw_markdown_path = export_markdown(
                    temp_doc_token,
                    stage_dir,
                    f"{final_stem}.raw",
                    lark_cli_identity,
                )
                localized_image_count = localize_markdown_images(
                    raw_markdown_path,
                    localized_markdown_path,
                    assets_dir,
                )

            normalize_markdown_user_mentions_file(localized_markdown_path)
            normalize_markdown_callouts_file(localized_markdown_path)
            if "markdown" in formats:
                outputs["markdown"] = str(localized_markdown_path)

        if needs_native_temp_doc and temp_doc_token is None:
            raw_xml = fetch_full_xml(doc_ref, lark_cli_identity)
            expanded_xml, expanded_count = expand_synced_references(raw_xml, lark_cli_identity)
            normalized_xml, temp_title = normalize_xml_for_create(expanded_xml, title_suffix)
            final_stem = file_stem or slugify_filename(temp_title)
            temp_doc_token, temp_doc_url = create_temp_doc(normalized_xml, stage_dir, lark_cli_identity)
            temp_doc_deleted = not keep_temp_doc

        if "pdf" in formats and pdf_mode == "rendered":
            assert localized_markdown_path is not None
            theme_css_path = resolve_theme_css(theme_name)
            body_html = stage_dir / "body.html"
            render_html = stage_dir / "render.html"
            render_markdown_body(localized_markdown_path, body_html)
            build_render_html(body_html, render_html, temp_title, theme_css_path, override_css)
            output_pdf = output_dir / f"{file_stem or slugify_filename(temp_title)}.pdf"
            render_html_to_pdf(render_html, output_pdf)
            outputs["pdf"] = str(output_pdf)
        elif "pdf" in formats:
            assert temp_doc_token is not None
            output_pdf = output_dir / f"{file_stem or slugify_filename(temp_title)}.pdf"
            raw_native_pdf = export_native_pdf(
                temp_doc_token,
                stage_dir,
                f"{file_stem or slugify_filename(temp_title)}.native-raw",
                lark_cli_identity,
            )
            preserved_raw_pdf = output_dir / f"{file_stem or slugify_filename(temp_title)}.native-raw.pdf"
            footer_result = postprocess_native_pdf(raw_native_pdf, output_pdf, preserved_raw_pdf)
            ai_footer_postprocess = {
                "status": footer_result.status,
                "raw_pdf_path": footer_result.raw_pdf_path,
                "warning": footer_result.warning,
            }
            if footer_result.warning:
                warnings.append(footer_result.warning)
            if footer_result.final_pdf_path:
                outputs["pdf"] = footer_result.final_pdf_path

        if temp_doc_token and not keep_temp_doc:
            delete_temp_doc(temp_doc_token, lark_cli_identity)

    native_failure = (
        "pdf" in formats
        and pdf_mode == "native"
        and ai_footer_postprocess is not None
        and ai_footer_postprocess["status"] in FAILURE_STATUSES
    )

    return {
        "ok": not native_failure,
        "doc": doc_ref,
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_deleted": temp_doc_deleted,
        "temp_doc_url": temp_doc_url,
        "localized_images": localized_image_count,
        "theme": theme_name if "pdf" in formats and pdf_mode == "rendered" else None,
        "pdf_mode": pdf_mode if "pdf" in formats else None,
        "ai_footer_postprocess": ai_footer_postprocess,
        "warnings": warnings,
        "outputs": outputs,
        "pdf_renderer": (
            "feishu-native"
            if "pdf" in formats and pdf_mode == "native"
            else "local-chromium"
            if "pdf" in formats
            else None
        ),
        "markdown_provider": provider.provider,
        "markdown_provider_detail": provider.detail,
    }
```

Update `src/lark_synced_export/doctor.py`:

```python
from .feishu_docx_bridge import resolve_markdown_provider


def check_feishu_docx_markdown() -> DoctorCheck:
    try:
        selection = resolve_markdown_provider("https://example.feishu.cn/docx/placeholder")
    except Exception as exc:
        return DoctorCheck(
            name="feishu-docx-markdown",
            ok=False,
            detail=f"Preferred Markdown provider not ready: {exc}",
            required=False,
        )

    if selection.provider == "feishu-docx":
        return DoctorCheck(
            name="feishu-docx-markdown",
            ok=True,
            detail=f"Preferred Markdown provider ready ({selection.detail}).",
            required=False,
        )

    return DoctorCheck(
        name="feishu-docx-markdown",
        ok=False,
        detail=f"Preferred Markdown provider unavailable; legacy markdown path will run ({selection.detail}).",
        required=False,
    )


def run_doctor() -> dict:
    checks = [check_lark_cli(), check_pdf_runtime(), check_feishu_docx_markdown()]
    return {
        "ok": all(check.ok for check in checks if check.required),
        "checks": [asdict(check) for check in checks],
    }
```

Keep `src/lark_synced_export/cli.py` behavior the same; only rely on the exporter result to print any added fields.

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:

```bash
uv sync --python 3.14 --group dev
uv run pytest tests/test_feishu_docx_bridge.py tests/test_exporter.py tests/test_doctor.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/lark_synced_export/exporter.py src/lark_synced_export/doctor.py src/lark_synced_export/cli.py tests/test_feishu_docx_bridge.py tests/test_exporter.py tests/test_doctor.py
git commit -S -s -m "feat(exporter): prefer feishu-docx markdown"
```

### Task 3: Update operator docs, bundled skill docs, and third-party notice

**Files:**
- Modify: `README.md`
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
- Modify: `tests/test_skill_install.py`
- Create: `THIRD_PARTY_NOTICES.md`

- [ ] **Step 1: Add the failing bundled-skill assertions**

Append to `tests/test_skill_install.py`:

```python
def test_skill_asset_mentions_feishu_docx_provider() -> None:
    text = Path("src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "feishu-docx" in text
    assert "FEISHU_APP_ID" in text
    assert "THIRD_PARTY_NOTICES.md" in text
```

- [ ] **Step 2: Run the skill-doc test and verify it fails**

Run:

```bash
uv run pytest tests/test_skill_install.py -q -k feishu_docx_provider
```

Expected: FAIL because the bundled skill docs do not mention the new provider yet.

- [ ] **Step 3: Update the docs and notice**

Patch `README.md` so the requirements, doctor section, and notes explicitly say:

```markdown
- Markdown now prefers `feishu-docx` when `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
  (or `~/.feishu-docx/config.json`) are available.
- Set `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=legacy` to force the previous
  `lark-cli` Markdown path.
- `doctor` reports the optional `feishu-docx` readiness check in addition to
  `lark-cli` and Chromium.
- Native PDF can still create a temporary expanded doc even when Markdown came
  from `feishu-docx`.
```

Patch `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md` so the prerequisites and guidance explicitly mention:

```markdown
- `feishu-docx` is the preferred Markdown provider when
  `FEISHU_APP_ID` / `FEISHU_APP_SECRET` or `~/.feishu-docx/config.json` are configured
- `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=legacy` forces the old temp-doc Markdown path
- `THIRD_PARTY_NOTICES.md` records the integrated MIT project attribution
```

Create `THIRD_PARTY_NOTICES.md`:

```markdown
# Third-Party Notices

## feishu-docx

- Project: `spencercjh/feishu-docx` (fork of `leemysw/feishu-docx`)
- License: MIT
- Usage in this repository: preferred Markdown export provider for rich Feishu/Lark document blocks

The upstream `feishu-docx` project is distributed under the MIT License. See the
upstream repository for the full license text and copyright notice.
```

- [ ] **Step 4: Run the docs-facing tests and verify they pass**

Run:

```bash
uv run pytest tests/test_skill_install.py -q -k feishu_docx_provider
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md tests/test_skill_install.py THIRD_PARTY_NOTICES.md
git commit -S -s -m "docs(exporter): document feishu-docx integration"
```

## Self-Review

- Spec coverage:
  - provider boundary -> Task 1 and Task 2
  - credential discovery / `auto|feishu-docx|legacy` policy -> Task 1
  - output-layout normalization back to `images/` -> Task 1
  - keep native PDF lane intact -> Task 2
  - doctor update -> Task 2
  - docs / attribution -> Task 3
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” placeholders remain
  - every code-changing step includes concrete code or file content
- Type consistency:
  - bridge module exports `FeishuDocxCredentials`, `MarkdownProviderSelection`, `resolve_markdown_provider`, `export_markdown_with_feishu_docx`, and `normalize_feishu_docx_assets`
  - exporter result fields use `markdown_provider` and `markdown_provider_detail` consistently across tasks

Plan complete and saved to `docs/superpowers/plans/2026-07-03-feishu-docx-markdown-integration.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
