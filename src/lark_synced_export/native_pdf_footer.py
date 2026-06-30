from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

import fitz


FAILURE_STATUSES = {"detection_failed", "unsafe_geometry", "mask_failed"}
FOOTER_VARIANTS = (
    "注:内容由AI生成,请谨慎参考",
    "(注:内容由AI生成,请谨慎参考)",
    "内容由AI生成,请谨慎参考",
)
CONTROL_RE = re.compile(r"[\u0000-\u001f\u007f]+")
WHITESPACE_RE = re.compile(r"\s+")
PUNCT_TRANSLATION = str.maketrans(
    {
        "：": ":",
        "，": ",",
        "（": "(",
        "）": ")",
    }
)


@dataclass(frozen=True)
class PdfWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class FooterDetection:
    status: Literal["matched", "not_found", "unsafe_geometry"]
    normalized_text: str | None
    word_indexes: tuple[int, ...]
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class NativePdfPostprocessResult:
    status: Literal[
        "removed",
        "not_found",
        "detection_failed",
        "unsafe_geometry",
        "mask_failed",
    ]
    final_pdf_path: str | None
    raw_pdf_path: str | None
    warning: str | None


def normalize_footer_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = CONTROL_RE.sub("", text)
    text = text.translate(PUNCT_TRANSLATION)
    text = WHITESPACE_RE.sub("", text)
    return text


def _rectangles_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def _words_share_line(left: PdfWord, right: PdfWord) -> bool:
    left_height = left.y1 - left.y0
    right_height = right.y1 - right.y0
    overlap = min(left.y1, right.y1) - max(left.y0, right.y0)
    if overlap <= 0.0:
        return False

    min_height = min(left_height, right_height)
    if min_height <= 0.0:
        return False

    overlap_ratio = overlap / min_height
    return (
        overlap_ratio >= 0.8
        and abs(left.y0 - right.y0) <= 4.0
        and abs(left.y1 - right.y1) <= 4.0
    )


def _cluster_bbox(
    cluster: Sequence[tuple[int, PdfWord]],
) -> tuple[float, float, float, float]:
    x0 = min(word.x0 for _, word in cluster)
    y0 = min(word.y0 for _, word in cluster)
    x1 = max(word.x1 for _, word in cluster)
    y1 = max(word.y1 for _, word in cluster)
    return (float(x0), float(y0), float(x1), float(y1))


def _cluster_text(cluster: Sequence[tuple[int, PdfWord]]) -> str:
    return normalize_footer_text("".join(word.text for _, word in cluster))


def _build_clusters(
    indexed_words: Sequence[tuple[int, PdfWord]],
) -> list[list[tuple[int, PdfWord]]]:
    if not indexed_words:
        return []

    clusters: list[list[tuple[int, PdfWord]]] = []
    current = [indexed_words[0]]
    for item in indexed_words[1:]:
        previous_word = current[-1][1]
        _, word = item
        same_line = _words_share_line(previous_word, word)
        gap = word.x0 - previous_word.x1
        small_gap = 0.0 <= gap <= 12.0
        if same_line and small_gap:
            current.append(item)
        else:
            clusters.append(current)
            current = [item]
    clusters.append(current)
    return clusters


def _find_split_cluster_variant(
    clusters: Sequence[Sequence[tuple[int, PdfWord]]],
) -> str | None:
    for start in range(len(clusters)):
        combined: list[tuple[int, PdfWord]] = []
        for end in range(start, len(clusters)):
            combined.extend(clusters[end])
            if end == start:
                continue

            normalized_text = _cluster_text(combined)
            if normalized_text in FOOTER_VARIANTS:
                return normalized_text
    return None


def _match_sort_key(match: tuple[Sequence[tuple[int, PdfWord]], str]) -> tuple[float, float, float, int]:
    cluster, _normalized_text = match
    x0, y0, x1, y1 = _cluster_bbox(cluster)
    return (-y0, -y1, x1 - x0, len(cluster))


def detect_footer(
    words: Sequence[PdfWord],
    page_width: float,
    page_height: float,
) -> FooterDetection:
    indexed_words = list(enumerate(words))
    if not indexed_words:
        return FooterDetection("not_found", None, (), None)

    clusters = _build_clusters(indexed_words)

    matches: list[tuple[list[tuple[int, PdfWord]], str]] = []
    for cluster in clusters:
        for start in range(len(cluster)):
            for end in range(start + 1, len(cluster) + 1):
                candidate = cluster[start:end]
                normalized_text = _cluster_text(candidate)
                if normalized_text in FOOTER_VARIANTS:
                    matches.append((candidate, normalized_text))

    if not matches:
        split_variant = _find_split_cluster_variant(clusters)
        if split_variant is not None:
            return FooterDetection("unsafe_geometry", split_variant, (), None)
        return FooterDetection("not_found", None, (), None)

    matches.sort(key=_match_sort_key)
    cluster, normalized_text = matches[0]
    word_indexes = tuple(index for index, _ in cluster)
    x0, y0, x1, y1 = _cluster_bbox(cluster)
    bbox = (x0, y0, x1, y1)

    if (y1 - y0) > max(36.0, page_height * 0.05):
        return FooterDetection("unsafe_geometry", normalized_text, word_indexes, bbox)
    if (x1 - x0) > page_width * 0.80:
        return FooterDetection("unsafe_geometry", normalized_text, word_indexes, bbox)

    expanded = (x0 - 6.0, y0 - 4.0, x1 + 6.0, y1 + 4.0)
    for index, word in enumerate(words):
        if index in word_indexes:
            continue
        if _rectangles_overlap(expanded, (word.x0, word.y0, word.x1, word.y1)):
            return FooterDetection("unsafe_geometry", normalized_text, word_indexes, bbox)

    return FooterDetection("matched", normalized_text, word_indexes, bbox)


def _build_warning(status: str, raw_pdf: Path) -> str:
    return (
        f"native PDF footer post-process failed ({status}); "
        f"raw native PDF kept at {raw_pdf}"
    )


def _read_last_page_words(pdf_path: Path) -> tuple[list[PdfWord], float, float]:
    document = fitz.open(pdf_path)
    try:
        page = document[-1]
        words = [
            PdfWord(
                text=str(item[4]),
                x0=float(item[0]),
                y0=float(item[1]),
                x1=float(item[2]),
                y1=float(item[3]),
            )
            for item in page.get_text("words")
        ]
        return words, float(page.rect.width), float(page.rect.height)
    finally:
        document.close()


def _copy_raw_pdf(raw_pdf: Path, final_pdf: Path) -> None:
    final_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_pdf, final_pdf)


def _preserve_raw_pdf(raw_pdf: Path, preserved_raw_pdf: Path) -> Path:
    preserved_raw_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_pdf, preserved_raw_pdf)
    return preserved_raw_pdf


def _apply_footer_redaction(
    raw_pdf: Path,
    final_pdf: Path,
    bbox: tuple[float, float, float, float],
) -> None:
    final_pdf.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(raw_pdf)
    try:
        page = document[-1]
        page.add_redact_annot(fitz.Rect(*bbox), fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        document.save(final_pdf)
    finally:
        document.close()


def _verify_footer_removed(pdf_path: Path) -> bool:
    words, page_width, page_height = _read_last_page_words(pdf_path)
    return detect_footer(words, page_width, page_height).status == "not_found"


def _cleanup_failed_output(final_pdf: Path) -> None:
    if final_pdf.exists():
        final_pdf.unlink()


def postprocess_native_pdf(
    raw_pdf: Path,
    final_pdf: Path,
    preserved_raw_pdf: Path,
) -> NativePdfPostprocessResult:
    try:
        words, page_width, page_height = _read_last_page_words(raw_pdf)
        detection = detect_footer(words, page_width, page_height)
    except Exception:
        preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
        return NativePdfPostprocessResult(
            status="detection_failed",
            final_pdf_path=None,
            raw_pdf_path=str(preserved),
            warning=_build_warning("detection_failed", preserved),
        )

    if detection.status == "not_found":
        _copy_raw_pdf(raw_pdf, final_pdf)
        return NativePdfPostprocessResult(
            status="not_found",
            final_pdf_path=str(final_pdf),
            raw_pdf_path=None,
            warning=None,
        )

    if detection.status != "matched" or detection.bbox is None:
        preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
        return NativePdfPostprocessResult(
            status="unsafe_geometry",
            final_pdf_path=None,
            raw_pdf_path=str(preserved),
            warning=_build_warning("unsafe_geometry", preserved),
        )

    try:
        _apply_footer_redaction(raw_pdf, final_pdf, detection.bbox)
        if not _verify_footer_removed(final_pdf):
            _cleanup_failed_output(final_pdf)
            preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
            return NativePdfPostprocessResult(
                status="mask_failed",
                final_pdf_path=None,
                raw_pdf_path=str(preserved),
                warning=_build_warning("mask_failed", preserved),
            )
    except Exception:
        _cleanup_failed_output(final_pdf)
        preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
        return NativePdfPostprocessResult(
            status="mask_failed",
            final_pdf_path=None,
            raw_pdf_path=str(preserved),
            warning=_build_warning("mask_failed", preserved),
        )

    return NativePdfPostprocessResult(
        status="removed",
        final_pdf_path=str(final_pdf),
        raw_pdf_path=None,
        warning=None,
    )
