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
    assert "<code" in html
    assert "print" in html
