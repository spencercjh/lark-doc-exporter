# Remove Legacy Markdown and Rendered PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy `lark-cli` Markdown exporter, remove rendered PDF mode, keep `--pdf-mode native` as a compatibility shell, and enforce a URL-only export contract while preserving the approved native-result JSON fields.

**Architecture:** Split the exporter into two explicit stages: a strict `feishu-docx` Markdown stage and a native-PDF temp-doc stage. Delete provider-selection and rendered-PDF logic instead of hiding it behind more conditionals, then rewrite the CLI, doctor, tests, docs, and snapshots to match that narrower contract.

**Tech Stack:** Python 3.14, `feishu-docx`, `lark-cli`, `pytest`, `ruff`, `PyMuPDF`, `uv`

---

## File Map

- `src/lark_synced_export/feishu_docx_bridge.py`
  Purpose: URL validation, `feishu-docx` import/credential discovery, Markdown export helper, asset normalization.
- `src/lark_synced_export/exporter.py`
  Purpose: top-level export orchestration, native temp-doc stage, JSON result contract.
- `src/lark_synced_export/cli.py`
  Purpose: CLI argument parsing, compatibility-shell handling for `--pdf-mode native`, JSON output.
- `src/lark_synced_export/doctor.py`
  Purpose: readiness reporting for `lark-cli` native PDF and `feishu-docx` Markdown only.
- `src/lark_synced_export/pdf_runtime.py`
  Purpose today: rendered-PDF Chromium probing. Expected outcome: delete.
- `src/lark_synced_export/themes/default.css`
  Purpose today: rendered-PDF theme asset. Expected outcome: delete if unused.
- `src/lark_synced_export/themes/company.css`
  Purpose today: rendered-PDF theme asset. Expected outcome: delete if unused.
- `README.md`
  Purpose: user-facing contract, examples, doctor guidance, output description.
- `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
  Purpose: bundled skill instructions installed by `skill install`.
- `pyproject.toml`
  Purpose: version, dependencies, packaged assets.
- `src/lark_synced_export/__init__.py`
  Purpose: module version constant.
- `uv.lock`
  Purpose: locked dependency graph after rendered-only cleanup.
- `tests/test_feishu_docx_bridge.py`
  Purpose: strict URL/import/credential checks for Markdown readiness helper.
- `tests/test_exporter.py`
  Purpose: unit coverage for Markdown stage, native-PDF stage, combined-result contract, removed fields.
- `tests/test_cli.py`
  Purpose: CLI help and compatibility-shell assertions.
- `tests/test_doctor.py`
  Purpose: doctor contract without Chromium.
- `tests/test_skill_install.py`
  Purpose: bundled skill text assertions after contract rewrite.
- `tests/test_public_doc_e2e.py`
  Purpose: live native-lane result snapshot and public-doc export behavior.
- `tests/e2e_snapshots/public_doc/result.json`
  Purpose: stable native-lane result snapshot.
- `tests/public_doc_e2e_case.py`
  Purpose: live e2e invocation args and snapshot expectations.
- `tests/test_release_version.py`
  Purpose: release-version validation still passes after version bump.

### Task 1: Remove Provider Selection and Enforce URL-Only Markdown Readiness

**Files:**
- Modify: `src/lark_synced_export/feishu_docx_bridge.py`
- Test: `tests/test_feishu_docx_bridge.py`

- [ ] **Step 1: Rewrite the bridge tests around the strict contract**

Replace the provider-mode/fallback tests with tests for:

- URL-shaped refs succeed when import + credentials are available
- token-only refs fail
- missing `feishu-docx` import fails
- missing credentials fail
- unreadable config is treated as missing credentials

Use assertions shaped like:

```python
def test_validate_markdown_doc_ref_rejects_token_only_ref():
    with pytest.raises(RuntimeError, match="full document URL"):
        validate_markdown_doc_ref("IkCedJjFIoypyzxwXjacRSy9nBg")


def test_require_feishu_docx_credentials_uses_env(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_secret")

    credentials = require_feishu_docx_credentials(
        "https://example.feishu.cn/docx/abc123"
    )

    assert credentials == FeishuDocxCredentials(
        app_id="cli_app",
        app_secret="cli_secret",
        auth_mode="tenant",
        is_lark=False,
        source="env",
    )
```

- [ ] **Step 2: Run the rewritten bridge tests to verify they fail on the old provider-based implementation**

Run:

```bash
uv run pytest tests/test_feishu_docx_bridge.py -q
```

Expected: FAIL because the file still exposes `MARKDOWN_PROVIDER_ENV`, `resolve_markdown_provider(...)`, and legacy fallback behavior.

- [ ] **Step 3: Replace provider selection with strict validation helpers**

Refactor `feishu_docx_bridge.py` so the public helpers become URL/import/credential checks instead of provider policy.

Target structure:

```python
URL_DOC_REF_RE = re.compile(
    r"^https?://.+/(?:doc|docx|wiki|sheet|sheets|base)/[A-Za-z0-9]+"
)


def validate_markdown_doc_ref(doc_ref: str) -> None:
    if not URL_DOC_REF_RE.match(doc_ref.strip()):
        raise RuntimeError(
            "markdown and native PDF exports require a full URL-shaped Feishu/Lark document ref"
        )


def require_feishu_docx_exporter():
    try:
        from feishu_docx.core.exporter import FeishuExporter
    except ImportError as exc:
        raise RuntimeError(
            "feishu-docx markdown export requires the feishu-docx package"
        ) from exc
    return FeishuExporter


def require_feishu_docx_credentials(doc_ref: str) -> FeishuDocxCredentials:
    credentials = discover_feishu_docx_credentials(doc_ref)
    if credentials is None:
        raise RuntimeError(
            "feishu-docx markdown export requires FEISHU_APP_ID/FEISHU_APP_SECRET "
            "or a readable ~/.feishu-docx/config.json"
        )
    return credentials
```

Keep `discover_feishu_docx_credentials(...)`, `export_markdown_with_feishu_docx(...)`, and `normalize_feishu_docx_assets(...)`, but remove:

- `MARKDOWN_PROVIDER_ENV`
- `SUPPORTED_PROVIDER_MODES`
- `LEGACY_DEPRECATION_NOTICE`
- `MarkdownProviderSelection`
- `_resolve_mode()`
- `resolve_markdown_provider(...)`
- every `legacy` branch

- [ ] **Step 4: Re-run bridge tests until they pass**

Run:

```bash
uv run pytest tests/test_feishu_docx_bridge.py -q
```

Expected: PASS with only strict readiness tests remaining.

- [ ] **Step 5: Commit the bridge contract rewrite**

Run:

```bash
git add src/lark_synced_export/feishu_docx_bridge.py tests/test_feishu_docx_bridge.py
git commit -S -s -m "refactor(exporter): remove markdown provider selection"
```

### Task 2: Refactor Exporter to Explicit Markdown and Native-PDF Stages

**Files:**
- Modify: `src/lark_synced_export/exporter.py`
- Test: `tests/test_exporter.py`

- [ ] **Step 1: Rewrite exporter tests around the final result contract**

Add or rewrite tests so they assert:

- invalid `doc_ref` fails before any export stage
- Markdown-only runs call only the `feishu-docx` stage
- PDF-only runs call only the native-PDF stage
- combined runs keep `pdf_mode="native"` / `pdf_renderer="feishu-native"`
- `markdown_provider`, `markdown_provider_detail`, and `theme` are gone

Use focused tests like:

```python
def test_export_document_rejects_non_url_doc_ref(tmp_path: Path):
    with pytest.raises(RuntimeError, match="full URL-shaped Feishu/Lark document ref"):
        export_document(
            doc_ref="IkCedJjFIoypyzxwXjacRSy9nBg",
            output_dir=tmp_path / "out",
            formats=["markdown"],
            title_suffix="",
            file_stem="demo",
            keep_temp_doc=False,
            pdf_mode="native",
        )


def test_export_document_keeps_native_result_fields(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_assets_dir = stage_dir / "demo"
    raw_assets_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *args, **kwargs: type(
            "DummyTempDir",
            (),
            {
                "__enter__": lambda self: str(stage_dir),
                "__exit__": lambda self, exc_type, exc, tb: False,
            },
        )(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, raw_assets_dir),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, _identity: raw_native_pdf,
    )
    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        pdf_mode="native",
    )
    assert result["pdf_mode"] == "native"
    assert result["pdf_renderer"] == "feishu-native"
    assert "markdown_provider" not in result
    assert "theme" not in result
```

- [ ] **Step 2: Run exporter tests to capture the current breakage**

Run:

```bash
uv run pytest tests/test_exporter.py -q
```

Expected: FAIL because `export_document(...)` still accepts rendered mode, still branches on `resolve_markdown_provider(...)`, and still returns removed result fields.

- [ ] **Step 3: Introduce explicit internal stage helpers in `exporter.py`**

Refactor `exporter.py` so `export_document(...)` delegates to two explicit helpers.

Add functions shaped like:

```python
def run_markdown_stage(
    doc_ref: str,
    stage_dir: Path,
    output_dir: Path,
    file_stem: str,
) -> tuple[Path, int, str]:
    validate_markdown_doc_ref(doc_ref)
    credentials = require_feishu_docx_credentials(doc_ref)
    raw_markdown_path, raw_assets_dir = export_markdown_with_feishu_docx(
        doc_ref,
        stage_dir,
        file_stem or None,
        credentials,
    )
    final_stem = file_stem or raw_markdown_path.stem
    localized_markdown_path = output_dir / f"{final_stem}.md"
    localized_count = normalize_feishu_docx_assets(
        raw_markdown_path,
        raw_assets_dir,
        localized_markdown_path,
        output_dir / "images",
    )
    normalize_markdown_user_mentions_file(localized_markdown_path)
    normalize_markdown_callouts_file(localized_markdown_path)
    return localized_markdown_path, localized_count, final_stem


def run_native_pdf_stage(
    doc_ref: str,
    stage_dir: Path,
    output_dir: Path,
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    lark_cli_identity: str,
) -> dict[str, object]:
    validate_markdown_doc_ref(doc_ref)
    expanded_count, temp_title, temp_doc_token, temp_doc_url = prepare_temp_doc_stage(
        doc_ref,
        title_suffix,
        stage_dir,
        lark_cli_identity,
    )
    output_stem = file_stem or slugify_filename(temp_title)
    output_pdf = output_dir / f"{output_stem}.pdf"
    raw_native_pdf = export_native_pdf(
        temp_doc_token,
        stage_dir,
        f"{output_stem}.native-raw",
        lark_cli_identity,
    )
    preserved_raw_pdf = output_dir / f"{output_stem}.native-raw.pdf"
    footer_result = postprocess_native_pdf(raw_native_pdf, output_pdf, preserved_raw_pdf)
    return {
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_url": temp_doc_url,
        "temp_doc_deleted": not keep_temp_doc,
        "output_pdf": footer_result.final_pdf_path,
        "ai_footer_postprocess": {
            "status": footer_result.status,
            "raw_pdf_path": footer_result.raw_pdf_path,
            "warning": footer_result.warning,
        },
        "warnings": [footer_result.warning] if footer_result.warning else [],
    }
```

Then simplify `export_document(...)` so it:

- validates `pdf_mode` as native-only compatibility shell
- never references `theme_name`, `override_css`, or rendered helpers
- runs `run_markdown_stage(...)` when `"markdown"` is requested
- runs `run_native_pdf_stage(...)` when `"pdf"` is requested
- returns only the approved JSON fields

The final return shape should look like:

```python
return {
    "ok": not native_failure,
    "doc": doc_ref,
    "expanded_references": expanded_count,
    "temp_doc_token": temp_doc_token,
    "temp_doc_deleted": temp_doc_deleted,
    "temp_doc_url": temp_doc_url,
    "localized_images": localized_image_count,
    "pdf_mode": "native" if "pdf" in formats else None,
    "ai_footer_postprocess": ai_footer_postprocess,
    "warnings": warnings,
    "outputs": outputs,
    "pdf_renderer": "feishu-native" if "pdf" in formats else None,
}
```

- [ ] **Step 4: Delete rendered-only code paths from `exporter.py`**

Remove:

- `render_markdown_body(...)`
- `build_render_html(...)`
- `render_html_to_pdf(...)`
- `resolve_theme_css(...)` call sites inside `export_document(...)`
- rendered-only local variables such as `theme_css_path`

The file should no longer reference:

```python
"rendered"
"local-chromium"
theme_name
override_css
```

- [ ] **Step 5: Re-run exporter tests until they pass**

Run:

```bash
uv run pytest tests/test_exporter.py -q
```

Expected: PASS with the new native-only/result-contract assertions.

- [ ] **Step 6: Commit the exporter refactor**

Run:

```bash
git add src/lark_synced_export/exporter.py tests/test_exporter.py
git commit -S -s -m "refactor(exporter): split markdown and native pdf stages"
```

### Task 3: Tighten the CLI and Doctor Contracts

**Files:**
- Modify: `src/lark_synced_export/cli.py`
- Modify: `src/lark_synced_export/doctor.py`
- Delete: `src/lark_synced_export/pdf_runtime.py`
- Delete: `src/lark_synced_export/themes/default.css`
- Delete: `src/lark_synced_export/themes/company.css`
- Test: `tests/test_cli.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Rewrite CLI and doctor tests to match the approved contract**

Replace rendered/provider-era assertions with:

- `--pdf-mode native` accepted
- omitted `--pdf-mode` behaves like native
- `--pdf-mode rendered` fails
- `--theme` / `--css` are rejected as unknown args once removed
- `--help` no longer mentions provider env or rendered mode
- doctor returns only `lark-cli` and `feishu-docx-markdown` checks

Use tests shaped like:

```python
def test_run_main_rejects_rendered_pdf_mode(tmp_path: Path):
    with pytest.raises(SystemExit, match="invalid choice: 'rendered'"):
        run_main(
            [
                "--doc",
                "https://example.feishu.cn/docx/abc123",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--pdf-mode",
                "rendered",
            ]
        )


def test_run_doctor_reports_only_two_checks(monkeypatch):
    payload = run_doctor()
    assert [item["name"] for item in payload["checks"]] == [
        "lark-cli",
        "feishu-docx-markdown",
    ]
```

- [ ] **Step 2: Run the CLI and doctor tests to capture the current mismatch**

Run:

```bash
uv run pytest tests/test_cli.py tests/test_doctor.py -q
```

Expected: FAIL because the CLI still exposes rendered/theme/provider help and doctor still imports `check_chromium_ready()`.

- [ ] **Step 3: Rewrite `cli.py` as a native-only shell**

Change `parse_export_args(...)` to:

- remove `--theme`
- remove `--css`
- keep `--pdf-mode` with `choices=["native"]` and `default="native"`
- rewrite the description/epilog to the new URL-only/native-only story

Use code shaped like:

```python
parser.add_argument(
    "--pdf-mode",
    choices=["native"],
    default="native",
    help="PDF pipeline selection. Only native Feishu PDF is supported.",
)
```

Update the export call to:

```python
result = export_document(
    doc_ref=args.doc,
    output_dir=Path(args.output_dir).expanduser().resolve(),
    formats=formats,
    title_suffix=args.title_suffix,
    file_stem=args.file_stem,
    keep_temp_doc=args.keep_temp_doc,
    pdf_mode=args.pdf_mode,
)
```

- [ ] **Step 4: Rewrite `doctor.py` and remove rendered-only assets**

Update `doctor.py` to:

- stop importing `check_chromium_ready`
- stop defining `check_pdf_runtime()`
- use direct readiness helpers from `feishu_docx_bridge.py`
- return only two checks

Target shape:

```python
def check_feishu_docx_markdown() -> DoctorCheck:
    try:
        validate_markdown_doc_ref("https://example.feishu.cn/docx/placeholder")
        require_feishu_docx_exporter()
        credentials = require_feishu_docx_credentials(
            "https://example.feishu.cn/docx/placeholder"
        )
    except Exception as exc:
        return DoctorCheck(
            name="feishu-docx-markdown",
            ok=False,
            detail=str(exc),
            required=False,
        )
    return DoctorCheck(
        name="feishu-docx-markdown",
        ok=True,
        detail=f"feishu-docx markdown is ready ({credentials.source}).",
        required=False,
    )


def run_doctor() -> dict:
    checks = [check_lark_cli(), check_feishu_docx_markdown()]
    return {
        "ok": all(check.ok for check in checks if check.required),
        "checks": [asdict(check) for check in checks],
    }
```

Then delete rendered-only files:

```bash
rm src/lark_synced_export/pdf_runtime.py
rm src/lark_synced_export/themes/default.css
rm src/lark_synced_export/themes/company.css
```

- [ ] **Step 5: Re-run CLI and doctor tests until they pass**

Run:

```bash
uv run pytest tests/test_cli.py tests/test_doctor.py -q
```

Expected: PASS with native-only argument/help and no Chromium check.

- [ ] **Step 6: Commit the CLI/doctor cleanup**

Run:

```bash
git add src/lark_synced_export/cli.py src/lark_synced_export/doctor.py tests/test_cli.py tests/test_doctor.py
git add -u src/lark_synced_export/pdf_runtime.py src/lark_synced_export/themes/default.css src/lark_synced_export/themes/company.css
git commit -S -s -m "refactor(cli): drop rendered pdf mode"
```

### Task 4: Align Docs, Skill Text, Packaging, and Version Metadata

**Files:**
- Modify: `README.md`
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
- Modify: `pyproject.toml`
- Modify: `src/lark_synced_export/__init__.py`
- Modify: `uv.lock`
- Test: `tests/test_skill_install.py`
- Test: `tests/test_release_version.py`

- [ ] **Step 1: Rewrite the doc and bundled-skill assertions first**

Update `tests/test_skill_install.py` so it asserts the new skill text instead of
the removed wording.

Use assertions like:

```python
def test_bundled_skill_markdown_mentions_url_only_native_contract():
    text = bundled_skill_markdown()
    assert "lark-doc-exporter doctor" in text
    assert "lark-doc-exporter skill install" in text
    assert "lark-cli" in text
    assert "feishu-docx" in text
    assert "full URL" in text
    assert "--pdf-mode native" in text
    assert "Chromium" not in text
    assert "next release" not in text
```

- [ ] **Step 2: Run the doc/skill/version tests to capture the current drift**

Run:

```bash
uv run pytest tests/test_skill_install.py tests/test_release_version.py -q
```

Expected: FAIL because README/SKILL still mention Chromium, rendered mode, and `next release`.

- [ ] **Step 3: Rewrite README and bundled SKILL.md to the final contract**

Update both documents so they consistently say:

- full document URLs only
- Markdown via `feishu-docx`
- PDF via native Feishu export
- `--pdf-mode native` is supported only as a compatibility shell
- no rendered mode, no theme, no CSS, no provider env, no Chromium guidance

Representative README command block:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats markdown,pdf \
  --pdf-mode native
```

Representative bundled-skill guidance:

```md
- export a Feishu/Lark doc URL into localized Markdown
- export native Feishu PDF output
- check whether `lark-cli` is ready for native PDF and whether `feishu-docx` is
  ready for Markdown
```

- [ ] **Step 4: Remove rendered-only dependencies and bump the release version**

Update `pyproject.toml` to:

- remove `playwright>=1.61.0,<2`
- remove `markdown>=3.7,<4` because the rendered-PDF path is the only codepath
  that currently needs the package
- remove `themes/*.css` from package data
- bump `version` to the chosen breaking-release value

Update `src/lark_synced_export/__init__.py` to match.

Then refresh the lockfile:

```bash
uv lock
```

- [ ] **Step 5: Re-run doc/skill/version tests until they pass**

Run:

```bash
uv run pytest tests/test_skill_install.py tests/test_release_version.py -q
```

Expected: PASS with the new native-only wording and matching version metadata.

- [ ] **Step 6: Commit the contract docs and packaging cleanup**

Run:

```bash
git add README.md src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md pyproject.toml src/lark_synced_export/__init__.py uv.lock
git add tests/test_skill_install.py tests/test_release_version.py
git commit -S -s -m "docs(exporter): document native-only contract"
```

### Task 5: Update the Native Snapshot Lane and Run Final Regression

**Files:**
- Modify: `tests/test_public_doc_e2e.py`
- Modify: `tests/public_doc_e2e_case.py`
- Modify: `tests/e2e_snapshots/public_doc/result.json`
- Test: `tests/test_public_doc_e2e.py`
- Test: repo-wide affected suites from earlier tasks

- [ ] **Step 1: Rewrite the snapshot helpers around the preserved result fields**

Update `tests/test_public_doc_e2e.py` and `tests/public_doc_e2e_case.py` so the
stable-result snapshot keeps:

- `ok`
- `expanded_references`
- `pdf_mode`
- `pdf_renderer`
- `localized_images`
- `ai_footer_postprocess.status`

and no longer expects removed provider fields anywhere.

The helper should stay shaped like:

```python
def build_stable_result(payload: dict[str, object]) -> dict[str, object]:
    ai_footer = payload.get("ai_footer_postprocess") or {}
    return {
        "ok": payload.get("ok"),
        "expanded_references": payload.get("expanded_references"),
        "pdf_mode": payload.get("pdf_mode"),
        "pdf_renderer": payload.get("pdf_renderer"),
        "localized_images": payload.get("localized_images"),
        "ai_footer_postprocess.status": ai_footer.get("status"),
    }
```

If `tests/public_doc_e2e_case.py` still hard-codes rendered-era assumptions,
rewrite its `EXPORT_ARGS` to the native-only shell:

```python
EXPORT_ARGS = {
    "formats": ["markdown", "pdf"],
    "pdf_mode": "native",
    "file_stem": FILE_STEM,
}
```

- [ ] **Step 2: Run the snapshot/unit e2e test first**

Run:

```bash
uv run pytest tests/test_public_doc_e2e.py -q
```

Expected: either PASS immediately after helper updates, or FAIL on stale
snapshot/result expectations that need regeneration.

- [ ] **Step 3: Regenerate the native result snapshot if the payload shape changed**

If the unit/live lane now produces a different stable result because removed
fields disappeared elsewhere, update:

```json
{
  "ok": true,
  "expanded_references": 2,
  "pdf_mode": "native",
  "pdf_renderer": "feishu-native",
  "localized_images": 1,
  "ai_footer_postprocess.status": "removed"
}
```

in `tests/e2e_snapshots/public_doc/result.json` to match the actual current
stable native output.

- [ ] **Step 4: Run the full required regression set**

Run:

```bash
make lint
uv run pytest tests/test_feishu_docx_bridge.py tests/test_exporter.py tests/test_cli.py tests/test_doctor.py tests/test_release_version.py -q
uv run pytest tests/test_skill_install.py -q
uv run pytest tests/test_public_doc_e2e.py -q
```

If any dependency/package-data changes touched unexpected surfaces, follow with:

```bash
uv run pytest -q
```

Expected: PASS on the required suites, with the public-doc lane passing or
skipping only for fixture/auth reasons that are already encoded in the test.

- [ ] **Step 5: Commit the snapshot/regression lane updates**

Run:

```bash
git add tests/test_public_doc_e2e.py tests/public_doc_e2e_case.py tests/e2e_snapshots/public_doc/result.json
git commit -S -s -m "test(exporter): update native-only regression snapshots"
```
