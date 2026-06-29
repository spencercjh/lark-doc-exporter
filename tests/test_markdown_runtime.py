from pathlib import Path

from lark_synced_export.markdown_runtime import (
    _normalize_table_inline_code,
    render_markdown_body,
)


def test_render_markdown_body_supports_tables_and_fenced_code(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text(
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```python\nprint('hi')\n```\n",
        encoding="utf-8",
    )

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "<code" in html
    assert "print" in html


def test_render_markdown_body_unescapes_table_cell_pipes_in_inline_code(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text(
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| Prometheus CRD | `kubectl api-resources \\| grep monitoring.coreos.com/v1` |\n",
        encoding="utf-8",
    )

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert "<code>kubectl api-resources | grep monitoring.coreos.com/v1</code>" in html
    assert "\\|" not in html


def test_render_markdown_body_keeps_non_table_inline_code_literal(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text(
        "Outside table: `kubectl api-resources \\| grep monitoring.coreos.com/v1`\n",
        encoding="utf-8",
    )

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert (
        "<code>kubectl api-resources \\| grep monitoring.coreos.com/v1</code>" in html
    )


def test_normalize_table_inline_code_skips_fenced_code_blocks():
    text = "```text\n| `a\\|b` |\n```\n"

    assert _normalize_table_inline_code(text) == text


def test_render_markdown_body_upgrades_callout_blockquote(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text(
        "> [!TIP]\n"
        "> 💡 **核心结论：** Hosted.ai 与 HAMi 的关系，更准确地说是……\n"
        ">\n"
        "> 第二段正文\n",
        encoding="utf-8",
    )

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert 'class="callout callout--tip"' in html
    assert "[!TIP]" not in html
    assert "💡" in html
    assert "第二段正文" in html


def test_render_markdown_body_keeps_plain_blockquote_as_plain_blockquote(
    tmp_path: Path,
):
    markdown_path = tmp_path / "demo.md"
    body_html = tmp_path / "body.html"
    markdown_path.write_text("> plain quote\n", encoding="utf-8")

    render_markdown_body(markdown_path, body_html)

    html = body_html.read_text(encoding="utf-8")
    assert "<blockquote>" in html
    assert 'class="callout' not in html
