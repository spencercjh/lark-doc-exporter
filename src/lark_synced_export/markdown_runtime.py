from __future__ import annotations

import re
from pathlib import Path

import markdown as markdown_lib

from .callout_markdown import extract_callout_type


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


def _render_markdown_fragment(text: str) -> str:
    if not text.strip():
        return ""
    return markdown_lib.markdown(
        _normalize_table_inline_code(text),
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html5",
    )


def _strip_blockquote_prefix(line: str) -> str:
    assert line.startswith(">")
    rest = line[1:]
    if rest.startswith(" "):
        rest = rest[1:]
    return rest


def _extract_callout_marker_from_line(line: str) -> str | None:
    if not line.startswith(">"):
        return None
    return extract_callout_type(_strip_blockquote_prefix(line))


def _render_callout_block(marker: str, body_lines: list[str]) -> str:
    body_text = "\n".join(body_lines)
    body_html = _render_markdown_fragment(body_text)
    return f'<div class="callout callout--{marker.lower()}">\n{body_html}\n</div>'


def _render_with_callouts(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = []
    plain_lines: list[str] = []
    index = 0

    def flush_plain() -> None:
        if not plain_lines:
            return
        parts.append(_render_markdown_fragment("\n".join(plain_lines)))
        plain_lines.clear()

    while index < len(lines):
        marker = _extract_callout_marker_from_line(lines[index])
        if marker is None:
            plain_lines.append(lines[index])
            index += 1
            continue

        flush_plain()

        body_lines: list[str] = []
        index += 1
        while index < len(lines) and lines[index].startswith(">"):
            body_lines.append(_strip_blockquote_prefix(lines[index]))
            index += 1

        parts.append(_render_callout_block(marker, body_lines))

    flush_plain()
    return "\n".join(part for part in parts if part)


def render_markdown_body(markdown_path: Path, body_html: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    html = _render_with_callouts(text)
    body_html.write_text(html, encoding="utf-8")
