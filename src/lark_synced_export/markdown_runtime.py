from __future__ import annotations

import re
from pathlib import Path

import markdown as markdown_lib


MARKDOWN_EXTENSIONS = [
    "extra",
    "sane_lists",
]
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _normalize_inline_code_match(match: re.Match[str]) -> str:
    normalized = match.group(1).replace("\\|", "|")
    return f"`{normalized}`"


def _normalize_table_inline_code(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and stripped.startswith("|") and "`" in line:
            line = INLINE_CODE_RE.sub(_normalize_inline_code_match, line)
        lines.append(line)
    return "".join(lines)


def render_markdown_body(markdown_path: Path, body_html: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    text = _normalize_table_inline_code(text)
    html = markdown_lib.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html5",
    )
    body_html.write_text(html, encoding="utf-8")
