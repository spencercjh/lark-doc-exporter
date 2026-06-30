from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturePoint:
    name: str
    markdown_contains_snapshot: str | None = None
    pdf_text_contains_snapshot: str | None = None
    markdown_forbid: tuple[str, ...] = ()
    pdf_forbid: tuple[str, ...] = ()


DOC_REF: str | None = None
FILE_STEM = "public-doc-e2e"
EXPORT_ARGS = {
    "formats": ["markdown", "pdf"],
    "pdf_mode": "native",
    "file_stem": FILE_STEM,
}
FEATURE_POINTS: tuple[FeaturePoint, ...] = ()
