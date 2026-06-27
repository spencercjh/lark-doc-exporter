from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Final


SKILL_NAME: Final = "lark-doc-exporter"


def bundled_skill_dir() -> Traversable:
    return files("lark_synced_export").joinpath("skill_assets", SKILL_NAME)


def bundled_skill_markdown() -> str:
    return bundled_skill_dir().joinpath("SKILL.md").read_text(encoding="utf-8")
