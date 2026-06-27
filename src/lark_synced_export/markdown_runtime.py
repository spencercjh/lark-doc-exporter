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
