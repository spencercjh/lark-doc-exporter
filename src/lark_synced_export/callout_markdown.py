from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping


ATTR_RE = re.compile(r'([:\w-]+)="([^"]*)"')
CALLOUT_RE = re.compile(r"<callout\b([^>]*)>(.*?)</callout>", re.S)
CALLOUT_MARKER_RE = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")

EMOJI_TYPE_MAP = {
    "💡": "TIP",
    "📌": "NOTE",
    "❗": "WARNING",
    "✅": "IMPORTANT",
    "❌": "CAUTION",
    "⭐": "IMPORTANT",
}

# Reserved for future use if Feishu starts exposing a stable semantic color signal.
COLOR_TYPE_MAP: dict[tuple[str, str], str] = {}


def parse_callout_attrs(attr_text: str) -> dict[str, str]:
    return {name: value for name, value in ATTR_RE.findall(attr_text)}


def extract_callout_type(marker_line: str) -> str | None:
    match = CALLOUT_MARKER_RE.fullmatch(marker_line.strip())
    return match.group(1) if match else None


def map_callout_type(attrs: Mapping[str, str]) -> str:
    emoji = attrs.get("emoji", "").strip()
    if emoji in EMOJI_TYPE_MAP:
        return EMOJI_TYPE_MAP[emoji]

    colors = (
        attrs.get("background-color", "").strip(),
        attrs.get("border-color", "").strip(),
    )
    if colors in COLOR_TYPE_MAP:
        return COLOR_TYPE_MAP[colors]

    return "NOTE"


def _strip_callout_body(body: str) -> str:
    return body.strip("\n")


def _quote_callout_body(body: str, emoji: str) -> list[str]:
    stripped = _strip_callout_body(body)
    if not stripped:
        return [">"]

    lines = stripped.splitlines()
    out: list[str] = []
    first_non_empty = False

    for line in lines:
        content = line.rstrip()
        if not content:
            out.append(">")
            continue

        if not first_non_empty:
            prefix = f"{emoji} " if emoji else ""
            out.append(f"> {prefix}{content}")
            first_non_empty = True
            continue

        out.append(f"> {content}")

    return out


def normalize_markdown_callouts(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attrs = parse_callout_attrs(match.group(1))
        marker = map_callout_type(attrs)
        emoji = attrs.get("emoji", "").strip()
        quoted_lines = _quote_callout_body(match.group(2), emoji)
        block = [f"> [!{marker}]", *quoted_lines]
        return "\n".join(block)

    return CALLOUT_RE.sub(repl, text)


def normalize_markdown_callouts_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(normalize_markdown_callouts(text), encoding="utf-8")
