from pathlib import Path

import pytest

from lark_synced_export.exporter import (
    build_render_html,
    export_document,
    resolve_theme_css,
    slugify_filename,
)
from lark_synced_export.native_pdf_footer import NativePdfPostprocessResult


def test_slugify_filename_collapses_spaces_and_invalid_chars():
    assert slugify_filename('A / B: "Spec"') == "A-B-Spec"


def test_build_render_html_includes_theme_and_override(tmp_path: Path):
    body_html = tmp_path / "body.html"
    render_html = tmp_path / "render.html"
    theme_css = tmp_path / "theme.css"
    override_css = tmp_path / "override.css"

    body_html.write_text("<h1>Demo</h1>", encoding="utf-8")
    theme_css.write_text(":root { --accent: #123456; }", encoding="utf-8")
    override_css.write_text("h1 { color: #abcdef; }", encoding="utf-8")

    build_render_html(body_html, render_html, "Demo", theme_css, override_css)

    html = render_html.read_text(encoding="utf-8")
    assert "--accent: #123456" in html
    assert "color: #abcdef" in html
    assert "<h1>Demo</h1>" in html


def test_build_render_html_includes_packaged_callout_styles(tmp_path: Path):
    body_html = tmp_path / "body.html"
    render_html = tmp_path / "render.html"

    body_html.write_text(
        '<div class="callout callout--tip">demo</div>', encoding="utf-8"
    )

    build_render_html(
        body_html,
        render_html,
        "Demo",
        resolve_theme_css("default"),
        None,
    )

    html = render_html.read_text(encoding="utf-8")
    assert ".callout--tip" in html
    assert "--callout-tip-bg" in html


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

    def fake_render_markdown(_markdown_path: Path, body_html: Path) -> None:
        body_html.write_text("<h1>Demo</h1>", encoding="utf-8")

    def fake_render_pdf(_html: Path, output_pdf: Path) -> None:
        output_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory", DummyTempDir
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda token, stage, stem: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images", fake_localize
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.resolve_theme_css", lambda _theme: theme_css
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_markdown_body", fake_render_markdown
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_html_to_pdf", fake_render_pdf
    )

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


def test_export_document_rejects_unsupported_pdf_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported pdf_mode: foo"):
        export_document(
            doc_ref="demo",
            output_dir=tmp_path / "out",
            formats=["pdf"],
            title_suffix="",
            file_stem="demo",
            keep_temp_doc=False,
            theme_name="default",
            override_css=None,
            pdf_mode="foo",
        )


def test_export_document_normalizes_callouts_before_render(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text(
        '<callout emoji="💡">\nBody\n</callout>\n',
        encoding="utf-8",
    )
    theme_css = tmp_path / "theme.css"
    theme_css.write_text(":root { --accent: #123456; }", encoding="utf-8")
    capture: dict[str, str] = {}

    class DummyTempDir:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_localize(src: Path, dst: Path, _assets: Path) -> int:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return 0

    def fake_render_markdown(markdown_path: Path, body_html: Path) -> None:
        capture["render_input"] = markdown_path.read_text(encoding="utf-8")
        body_html.write_text("<div>rendered</div>", encoding="utf-8")

    def fake_render_pdf(_html: Path, output_pdf: Path) -> None:
        output_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory", DummyTempDir
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda token, stage, stem: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images", fake_localize
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.resolve_theme_css", lambda _theme: theme_css
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_markdown_body", fake_render_markdown
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_html_to_pdf", fake_render_pdf
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
    )

    normalized = "> [!TIP]\n> 💡 Body"
    markdown_output = Path(result["outputs"]["markdown"]).read_text(encoding="utf-8")

    assert markdown_output == f"{normalized}\n"
    assert capture["render_input"] == f"{normalized}\n"


def test_export_document_normalizes_user_mentions_before_render(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text(
        'Owner：<cite type="user" user-id="ou_example" user-name="Example User"></cite>\n',
        encoding="utf-8",
    )
    theme_css = tmp_path / "theme.css"
    theme_css.write_text(":root { --accent: #123456; }", encoding="utf-8")
    capture: dict[str, str] = {}

    class DummyTempDir:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_localize(src: Path, dst: Path, _assets: Path) -> int:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return 0

    def fake_render_markdown(markdown_path: Path, body_html: Path) -> None:
        capture["render_input"] = markdown_path.read_text(encoding="utf-8")
        body_html.write_text("<div>rendered</div>", encoding="utf-8")

    def fake_render_pdf(_html: Path, output_pdf: Path) -> None:
        output_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory", DummyTempDir
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda token, stage, stem: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images", fake_localize
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.resolve_theme_css", lambda _theme: theme_css
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_markdown_body", fake_render_markdown
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.render_html_to_pdf", fake_render_pdf
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
    )

    normalized = "Owner：Example User"
    markdown_output = Path(result["outputs"]["markdown"]).read_text(encoding="utf-8")

    assert markdown_output == f"{normalized}\n"
    assert capture["render_input"] == f"{normalized}\n"


def test_export_document_native_not_found_sets_pdf_payload(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_postprocess(
        raw_pdf: Path,
        final_pdf: Path,
        preserved_raw_pdf: Path,
    ) -> NativePdfPostprocessResult:
        final_pdf.write_bytes(b"%PDF-1.4\nclean\n")
        return NativePdfPostprocessResult(
            status="not_found",
            final_pdf_path=str(final_pdf),
            raw_pdf_path=None,
            warning=None,
        )

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *a, **k: DummyTempDir(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda token, stage, stem: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf", fake_postprocess
    )

    result = export_document(
        doc_ref="demo",
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
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_native_pdf = stage_dir / "demo.source.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    preserved_raw_pdf = tmp_path / "out" / "demo.native-raw.pdf"

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_localize(src: Path, dst: Path, _assets: Path) -> int:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory",
        lambda *a, **k: DummyTempDir(),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda token, stage, stem: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda token, stage, stem: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images", fake_localize
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda raw, final, preserved: NativePdfPostprocessResult(
            status="unsafe_geometry",
            final_pdf_path=None,
            raw_pdf_path=str(preserved_raw_pdf),
            warning=f"native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at {preserved_raw_pdf}",
        ),
    )

    result = export_document(
        doc_ref="demo",
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
