from __future__ import annotations

import re
from html import unescape
from pathlib import Path


ATTR_RE = re.compile(r'([:\w-]+)="([^"]*)"')
EMPTY_CITE_RE = re.compile(r"<cite\b([^>]*)>\s*</cite>", re.S)


def parse_cite_attrs(attr_text: str) -> dict[str, str]:
    return {name: value for name, value in ATTR_RE.findall(attr_text)}


def normalize_markdown_user_mentions(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attrs = parse_cite_attrs(match.group(1))
        if attrs.get("type", "").strip() != "user":
            return match.group(0)

        user_name = attrs.get("user-name", "").strip()
        if not user_name:
            return match.group(0)

        return unescape(user_name)

    return EMPTY_CITE_RE.sub(repl, text)


def normalize_markdown_user_mentions_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(normalize_markdown_user_mentions(text), encoding="utf-8")
