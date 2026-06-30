from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturePoint:
    name: str
    markdown_contains_snapshot: str | None = None
    pdf_text_contains_snapshot: str | None = None
    pdf_image_snapshot: str | None = None
    pdf_total_images_at_least: int | None = None
    markdown_forbid: tuple[str, ...] = ()
    pdf_forbid: tuple[str, ...] = ()


# Pinned canonical fixture. PUBLIC_DOC_E2E_REF is only for local override.
DOC_REF = os.environ.get("PUBLIC_DOC_E2E_REF") or "IkCedJjFIoypyzxwXjacRSy9nBg"
FILE_STEM = "public-doc-e2e"
EXPECTED_PDF_TOTAL_IMAGES = 2
EXPORT_ARGS = {
    "formats": ["markdown", "pdf"],
    "pdf_mode": "native",
    "file_stem": FILE_STEM,
}
FEATURE_POINTS: tuple[FeaturePoint, ...] = (
    FeaturePoint(
        name="synced_block",
        markdown_contains_snapshot="markdown/synced_block.md",
        pdf_text_contains_snapshot="pdf/synced_block.txt",
        markdown_forbid=("<synced_reference", "<synced-source"),
        pdf_forbid=("不支持导出查看",),
    ),
    FeaturePoint(
        name="markdown_table",
        markdown_contains_snapshot="markdown/table.md",
        pdf_text_contains_snapshot="pdf/table.txt",
    ),
    FeaturePoint(
        name="markdown_blockquote",
        markdown_contains_snapshot="markdown/blockquote.md",
        pdf_text_contains_snapshot="pdf/blockquote.txt",
    ),
    FeaturePoint(
        name="callout",
        markdown_contains_snapshot="markdown/callout.md",
        pdf_text_contains_snapshot="pdf/callout.txt",
        markdown_forbid=("<callout",),
    ),
    FeaturePoint(
        name="whiteboard",
        markdown_contains_snapshot="markdown/whiteboard.md",
        pdf_image_snapshot="pdf/whiteboard_image.json",
        markdown_forbid=("<whiteboard",),
    ),
    FeaturePoint(
        name="image",
        markdown_contains_snapshot="markdown/image.md",
        pdf_image_snapshot="pdf/image_image.json",
        pdf_total_images_at_least=2,
        markdown_forbid=("authcode/?code=",),
        pdf_forbid=("加载失败",),
    ),
)
