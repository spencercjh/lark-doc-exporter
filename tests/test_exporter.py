from pathlib import Path

from lark_synced_export.exporter import (
    build_render_html,
    export_document,
    resolve_theme_css,
    slugify_filename,
)


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
