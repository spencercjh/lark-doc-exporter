from pathlib import Path

from lark_synced_export.exporter import build_render_html, slugify_filename


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

