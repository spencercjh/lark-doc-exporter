import json
import subprocess
from pathlib import Path

import pytest

import lark_synced_export.exporter as exporter_module
from lark_synced_export.exporter import (
    LARK_CLI_IDENTITY_ENV,
    delete_temp_doc,
    export_doc,
    export_document,
    normalize_xml_for_create,
    resolve_lark_cli_identity,
    slugify_filename,
)
from lark_synced_export.native_pdf_footer import NativePdfPostprocessResult


def patch_tempdir(monkeypatch, stage_dir: Path) -> None:
    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *args, **kwargs: DummyTempDir(),
    )


def patch_markdown_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        "lark_synced_export.exporter.require_feishu_docx_credentials",
        lambda _doc: object(),
    )


def test_resolve_lark_cli_identity_defaults_to_user(monkeypatch):
    monkeypatch.delenv(LARK_CLI_IDENTITY_ENV, raising=False)

    assert resolve_lark_cli_identity() == "user"


def test_resolve_lark_cli_identity_accepts_bot_override(monkeypatch):
    monkeypatch.setenv(LARK_CLI_IDENTITY_ENV, "bot")

    assert resolve_lark_cli_identity() == "bot"


def test_resolve_lark_cli_identity_rejects_invalid_override(monkeypatch):
    monkeypatch.setenv(LARK_CLI_IDENTITY_ENV, "robot")

    with pytest.raises(ValueError, match=LARK_CLI_IDENTITY_ENV):
        resolve_lark_cli_identity()


def test_slugify_filename_collapses_spaces_and_invalid_chars():
    assert slugify_filename('A / B: "Spec"') == "A-B-Spec"


def test_export_doc_returns_saved_path_without_async_follow_up(
    monkeypatch, tmp_path: Path
):
    commands: list[tuple[str, ...]] = []

    def fake_run_json(cmd: list[str], cwd: Path | None = None) -> dict:
        commands.append(tuple(cmd))
        assert cwd == tmp_path
        return {"data": {"saved_path": str(tmp_path / "demo.pdf")}}

    monkeypatch.setattr(exporter_module, "run_json", fake_run_json)

    result = export_doc(
        temp_doc_token="doc-token",
        output_dir=tmp_path / "exports",
        file_stem="demo",
        formats=["pdf"],
        lark_cli_identity="bot",
    )

    assert result == {"pdf": str(tmp_path / "demo.pdf")}
    assert commands == [
        (
            "lark-cli",
            "drive",
            "+export",
            "--as",
            "bot",
            "--token",
            "doc-token",
            "--doc-type",
            "docx",
            "--file-extension",
            "pdf",
            "--file-name",
            "demo.pdf",
            "--output-dir",
            "exports",
            "--overwrite",
        )
    ]


def test_export_doc_polls_task_result_and_downloads_async_export(
    monkeypatch, tmp_path: Path
):
    commands: list[tuple[str, ...]] = []
    task_result_calls = 0
    sleeps: list[float] = []

    def fake_run_json(cmd: list[str], cwd: Path | None = None) -> dict:
        nonlocal task_result_calls
        commands.append(tuple(cmd))
        if cmd[2] == "+export":
            assert cwd == tmp_path
            return {
                "data": {
                    "ready": False,
                    "ticket": "ticket-123",
                    "timed_out": True,
                }
            }
        if cmd[2] == "+task_result":
            task_result_calls += 1
            if task_result_calls == 1:
                return {"data": {"ready": False, "failed": False}}
            return {
                "data": {
                    "ready": True,
                    "failed": False,
                    "file_token": "exported-file-token",
                }
            }
        if cmd[2] == "+export-download":
            assert cwd == tmp_path
            return {"data": {"saved_path": str(tmp_path / "exports" / "demo.pdf")}}
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(exporter_module, "run_json", fake_run_json)
    monkeypatch.setattr(
        exporter_module.time,
        "sleep",
        lambda seconds: sleeps.append(seconds),
    )

    result = export_doc(
        temp_doc_token="doc-token",
        output_dir=tmp_path / "exports",
        file_stem="demo",
        formats=["pdf"],
        lark_cli_identity="bot",
    )

    assert result == {"pdf": str(tmp_path / "exports" / "demo.pdf")}
    assert sleeps == [2.0]
    assert commands == [
        (
            "lark-cli",
            "drive",
            "+export",
            "--as",
            "bot",
            "--token",
            "doc-token",
            "--doc-type",
            "docx",
            "--file-extension",
            "pdf",
            "--file-name",
            "demo.pdf",
            "--output-dir",
            "exports",
            "--overwrite",
        ),
        (
            "lark-cli",
            "drive",
            "+task_result",
            "--as",
            "bot",
            "--scenario",
            "export",
            "--ticket",
            "ticket-123",
            "--file-token",
            "doc-token",
        ),
        (
            "lark-cli",
            "drive",
            "+task_result",
            "--as",
            "bot",
            "--scenario",
            "export",
            "--ticket",
            "ticket-123",
            "--file-token",
            "doc-token",
        ),
        (
            "lark-cli",
            "drive",
            "+export-download",
            "--as",
            "bot",
            "--file-token",
            "exported-file-token",
            "--file-name",
            "demo.pdf",
            "--output-dir",
            "exports",
            "--overwrite",
        ),
    ]


def test_delete_temp_doc_ignores_already_deleted_error(monkeypatch):
    commands: list[tuple[str, ...]] = []
    payload = {
        "ok": False,
        "error": {
            "code": 1061007,
            "message": "file has been delete.",
        },
    }

    def fake_run_json(cmd: list[str], cwd: Path | None = None) -> dict:
        del cwd
        commands.append(tuple(cmd))
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=cmd,
            output=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(exporter_module, "run_json", fake_run_json)

    delete_temp_doc("doc-token", "bot")

    assert commands == [
        (
            "lark-cli",
            "drive",
            "+delete",
            "--as",
            "bot",
            "--file-token",
            "doc-token",
            "--type",
            "docx",
            "--yes",
            "--format",
            "json",
        )
    ]


def test_delete_temp_doc_reraises_other_delete_errors(monkeypatch):
    payload = {
        "ok": False,
        "error": {
            "code": 999999,
            "message": "permission denied",
        },
    }

    def fake_run_json(cmd: list[str], cwd: Path | None = None) -> dict:
        del cwd
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=cmd,
            output=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(exporter_module, "run_json", fake_run_json)

    with pytest.raises(subprocess.CalledProcessError):
        delete_temp_doc("doc-token", "bot")


def test_normalize_xml_for_create_drops_fetch_only_img_attrs():
    xml = (
        "<title>Demo</title>"
        '<img width="1260" height="946" caption="Figure 1" name="test.jpg" '
        'href="https://example.com/auth" alt="demo" mime="image/jpeg" '
        'scale="1.000000" src="NYRpb4o9Wo5ISexpegvcMRZXnwg" token="imgtok"/>'
    )

    normalized, title = normalize_xml_for_create(xml, "")

    assert title == "Demo"
    assert (
        '<img width="1260" height="946" caption="Figure 1" name="test.jpg" '
        'href="https://example.com/auth"/>'
    ) in normalized
    for leaked_attr in (' alt="', ' mime="', ' scale="', ' src="', ' token="'):
        assert leaked_attr not in normalized


def test_export_document_rejects_non_url_doc_ref(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("markdown stage should not run")
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("native PDF stage should not run")
        ),
    )

    with pytest.raises(RuntimeError, match="full document URL-shaped"):
        export_document(
            doc_ref="IkCedJjFIoypyzxwXjacRSy9nBg",
            output_dir=tmp_path / "out",
            formats=["markdown", "pdf"],
            title_suffix="",
            file_stem="demo",
            keep_temp_doc=False,
            theme_name="default",
            override_css=None,
            pdf_mode="native",
        )


def test_export_document_markdown_only_calls_only_feishu_docx_stage(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text("![image](demo/pic.png)\n", encoding="utf-8")
    raw_assets_dir = stage_dir / "demo"
    raw_assets_dir.mkdir()
    (raw_assets_dir / "pic.png").write_bytes(b"png")
    calls: list[str] = []

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (
            calls.append("markdown"),
            (raw_markdown_path, raw_assets_dir),
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("native PDF stage should not run")
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda _src, _raw_assets, dst, assets: (
            assets.mkdir(parents=True, exist_ok=True),
            (assets / "pic.png").write_bytes(b"png"),
            dst.write_text("![image](images/pic.png)\n", encoding="utf-8"),
            1,
        )[-1],
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert calls == ["markdown"]
    assert result["outputs"]["markdown"].endswith("demo.md")
    assert result["localized_images"] == 1
    assert result["expanded_references"] is None
    assert result["temp_doc_token"] is None
    assert result["temp_doc_url"] is None
    assert result["pdf_mode"] is None
    assert result["pdf_renderer"] is None


def test_export_document_pdf_only_calls_only_native_stage(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    capture: dict[str, str] = {}

    patch_tempdir(monkeypatch, stage_dir)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("markdown stage should not run")
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, identity: (
            capture.setdefault("prepare", identity),
            (2, "Demo Title", "tmp-token", "https://example.com/doc"),
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, identity: (
            capture.setdefault("export_native_pdf", identity),
            raw_native_pdf,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, identity: capture.setdefault("delete", identity),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, final, preserved: (
            final.write_bytes(b"%PDF-1.4\nclean\n"),
            NativePdfPostprocessResult(
                status="not_found",
                final_pdf_path=str(final),
                raw_pdf_path=str(preserved),
                warning=None,
            ),
        )[-1],
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert capture == {
        "prepare": "user",
        "export_native_pdf": "user",
        "delete": "user",
    }
    assert result["outputs"]["pdf"].endswith("demo.pdf")
    assert result["localized_images"] == 0
    assert result["expanded_references"] == 2
    assert result["temp_doc_token"] == "tmp-token"
    assert result["temp_doc_deleted"] is True
    assert result["pdf_mode"] == "native"
    assert result["pdf_renderer"] == "feishu-native"


def test_export_document_keeps_native_result_fields(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_assets_dir = stage_dir / "demo"
    raw_assets_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, raw_assets_dir),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda _src, _raw_assets, dst, _assets: (
            dst.write_text("# Demo\n", encoding="utf-8"),
            0,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, _identity: (
            1,
            "Demo Title",
            "tmp-token",
            "https://example.com/doc",
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, _identity: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, _identity: None,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, final, preserved: (
            final.write_bytes(b"%PDF-1.4\nclean\n"),
            NativePdfPostprocessResult(
                status="removed",
                final_pdf_path=str(final),
                raw_pdf_path=str(preserved),
                warning=None,
            ),
        )[-1],
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert result["pdf_mode"] == "native"
    assert result["pdf_renderer"] == "feishu-native"
    assert "markdown_provider" not in result
    assert "markdown_provider_detail" not in result
    assert "theme" not in result


def test_export_document_combined_run_reuses_markdown_resolved_stem(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "markdown-derived-name.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_assets_dir = stage_dir / "markdown-derived-name"
    raw_assets_dir.mkdir()
    raw_native_pdf = stage_dir / "native.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    capture: dict[str, str] = {}

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, raw_assets_dir),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda _src, _raw_assets, dst, _assets: (
            dst.write_text("# Demo\n", encoding="utf-8"),
            0,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, _identity: (
            0,
            "Native Title That Should Not Win",
            "tmp-token",
            "https://example.com/doc",
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, stem, _identity: (
            capture.setdefault("native_stem", stem),
            raw_native_pdf,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, _identity: None,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, final, preserved: NativePdfPostprocessResult(
            status="removed",
            final_pdf_path=str(final),
            raw_pdf_path=str(preserved),
            warning=None,
        ),
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert Path(result["outputs"]["markdown"]).name == "markdown-derived-name.md"
    assert Path(result["outputs"]["pdf"]).name == "markdown-derived-name.pdf"
    assert capture["native_stem"] == "markdown-derived-name.native-raw"


def test_export_document_uses_configured_lark_cli_identity(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    capture: dict[str, str] = {}

    monkeypatch.setenv(LARK_CLI_IDENTITY_ENV, "bot")
    patch_tempdir(monkeypatch, stage_dir)
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, identity: (
            capture.setdefault("prepare", identity),
            (0, "Demo", "tmp-token", "https://example.com/doc"),
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, identity: (
            capture.setdefault("export_native_pdf", identity),
            raw_native_pdf,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, identity: capture.setdefault("delete", identity),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, final, preserved: NativePdfPostprocessResult(
            status="not_found",
            final_pdf_path=str(final),
            raw_pdf_path=str(preserved),
            warning=None,
        ),
    )

    export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert capture == {
        "prepare": "bot",
        "export_native_pdf": "bot",
        "delete": "bot",
    }


def test_export_document_rejects_unsupported_pdf_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported pdf_mode: rendered"):
        export_document(
            doc_ref="https://example.feishu.cn/docx/abc123",
            output_dir=tmp_path / "out",
            formats=["pdf"],
            title_suffix="",
            file_stem="demo",
            keep_temp_doc=False,
            theme_name="default",
            override_css=None,
            pdf_mode="rendered",
        )


def test_export_document_normalizes_callouts_in_markdown_output(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text(
        '<callout emoji="💡">\nBody\n</callout>\n',
        encoding="utf-8",
    )

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, None),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda src, _raw_assets, dst, _assets: (
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8"),
            0,
        )[-1],
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert Path(result["outputs"]["markdown"]).read_text(encoding="utf-8") == (
        "> [!TIP]\n> 💡 Body\n"
    )


def test_export_document_normalizes_user_mentions_in_markdown_output(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text(
        'Owner：<cite type="user" user-id="ou_example" user-name="Example User"></cite>\n',
        encoding="utf-8",
    )

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, None),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda src, _raw_assets, dst, _assets: (
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8"),
            0,
        )[-1],
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert Path(result["outputs"]["markdown"]).read_text(encoding="utf-8") == (
        "Owner：Example User\n"
    )


def test_export_document_native_not_found_sets_pdf_payload(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    patch_tempdir(monkeypatch, stage_dir)
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, _identity: (
            0,
            "Demo",
            "tmp-token",
            "https://example.com/doc",
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, _identity: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, _identity: None,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, final, _preserved: NativePdfPostprocessResult(
            status="not_found",
            final_pdf_path=str(final),
            raw_pdf_path=None,
            warning=None,
        ),
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert result["ok"] is True
    assert result["pdf_mode"] == "native"
    assert result["outputs"]["pdf"].endswith("demo.pdf")
    assert result["ai_footer_postprocess"]["status"] == "not_found"
    assert result["ai_footer_postprocess"]["raw_pdf_path"] is None
    assert result["warnings"] == []


def test_export_document_native_failure_keeps_markdown_and_warning(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_native_pdf = stage_dir / "demo.source.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    preserved_raw_pdf = tmp_path / "out" / "demo.native-raw.pdf"

    patch_tempdir(monkeypatch, stage_dir)
    patch_markdown_credentials(monkeypatch)
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown_with_feishu_docx",
        lambda _doc, _stage, _stem, _credentials: (raw_markdown_path, None),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_feishu_docx_assets",
        lambda src, _raw_assets, dst, _assets: (
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8"),
            0,
        )[-1],
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.prepare_temp_doc_stage",
        lambda _doc, _suffix, _stage, _identity: (
            0,
            "Demo",
            "tmp-token",
            "https://example.com/doc",
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda _token, _stage, _stem, _identity: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc",
        lambda _token, _identity: None,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda _raw, _final, _preserved: NativePdfPostprocessResult(
            status="unsafe_geometry",
            final_pdf_path=None,
            raw_pdf_path=str(preserved_raw_pdf),
            warning=(
                "native PDF footer post-process failed (unsafe_geometry); "
                f"raw native PDF kept at {preserved_raw_pdf}"
            ),
        ),
    )

    result = export_document(
        doc_ref="https://example.feishu.cn/docx/abc123",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert result["ok"] is False
    assert "markdown" in result["outputs"]
    assert "pdf" not in result["outputs"]
    assert result["ai_footer_postprocess"]["status"] == "unsafe_geometry"
    assert result["ai_footer_postprocess"]["raw_pdf_path"].endswith(
        "demo.native-raw.pdf"
    )
    assert result["warnings"][0].startswith("native PDF footer post-process failed")
