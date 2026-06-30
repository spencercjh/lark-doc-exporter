from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

import fitz


FAILURE_STATUSES = {"detection_failed", "unsafe_geometry", "mask_failed"}
SAME_LINE_OVERLAP_TOLERANCE = 1.0
MASK_PADDING_X = 6.0
MASK_PADDING_Y = 4.0
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
    font_size: float | None = None
    color: int | None = None


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


def _rect_intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    overlap_x = min(left[2], right[2]) - max(left[0], right[0])
    overlap_y = min(left[3], right[3]) - max(left[1], right[1])
    if overlap_x <= 0.0 or overlap_y <= 0.0:
        return 0.0
    return overlap_x * overlap_y


def _color_is_footer_like(color: int) -> bool:
    red = (color >> 16) & 0xFF
    green = (color >> 8) & 0xFF
    blue = color & 0xFF
    return (
        max(red, green, blue) - min(red, green, blue) <= 6
        and 120 <= red <= 190
        and 120 <= green <= 190
        and 120 <= blue <= 190
    )


def _candidate_looks_like_footer(cluster: Sequence[tuple[int, PdfWord]]) -> bool:
    styled_words = [
        word
        for _index, word in cluster
        if word.font_size is not None and word.color is not None
    ]
    if not styled_words:
        return True

    font_sizes = [word.font_size for word in styled_words if word.font_size is not None]
    colors = [word.color for word in styled_words if word.color is not None]
    if not font_sizes or not colors:
        return True
    if max(font_sizes) - min(font_sizes) > 0.75:
        return False
    if not all(9.0 <= font_size <= 11.0 for font_size in font_sizes):
        return False
    if len(set(colors)) != 1:
        return False
    return all(_color_is_footer_like(color) for color in colors)


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


def _expand_bbox(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (
        x0 - MASK_PADDING_X,
        y0 - MASK_PADDING_Y,
        x1 + MASK_PADDING_X,
        y1 + MASK_PADDING_Y,
    )


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
        small_gap = -SAME_LINE_OVERLAP_TOLERANCE <= gap <= 12.0
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
            if normalized_text in FOOTER_VARIANTS and _candidate_looks_like_footer(
                combined
            ):
                return normalized_text
    return None


def _match_sort_key(
    match: tuple[Sequence[tuple[int, PdfWord]], str],
) -> tuple[float, float, float, int]:
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
                if normalized_text in FOOTER_VARIANTS and _candidate_looks_like_footer(
                    candidate
                ):
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

    expanded = _expand_bbox(bbox)
    for index, word in enumerate(words):
        if index in word_indexes:
            continue
        if _rectangles_overlap(expanded, (word.x0, word.y0, word.x1, word.y1)):
            return FooterDetection(
                "unsafe_geometry", normalized_text, word_indexes, bbox
            )

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
        rawdict = page.get_text("rawdict", sort=True)
        style_spans: list[
            tuple[tuple[float, float, float, float], float | None, int | None]
        ] = []
        if isinstance(rawdict, dict):
            for block in rawdict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span.get("bbox")
                        if bbox is None:
                            continue
                        style_spans.append(
                            (
                                (
                                    float(bbox[0]),
                                    float(bbox[1]),
                                    float(bbox[2]),
                                    float(bbox[3]),
                                ),
                                (
                                    float(span["size"])
                                    if span.get("size") is not None
                                    else None
                                ),
                                int(span["color"])
                                if span.get("color") is not None
                                else None,
                            )
                        )

        words: list[PdfWord] = []
        for item in page.get_text("words", sort=True):
            bbox = (
                float(item[0]),
                float(item[1]),
                float(item[2]),
                float(item[3]),
            )
            font_size, color = _lookup_word_style(bbox, style_spans)
            words.append(
                PdfWord(
                    text=str(item[4]),
                    x0=bbox[0],
                    y0=bbox[1],
                    x1=bbox[2],
                    y1=bbox[3],
                    font_size=font_size,
                    color=color,
                )
            )
        return words, float(page.rect.width), float(page.rect.height)
    finally:
        document.close()


def _lookup_word_style(
    word_bbox: tuple[float, float, float, float],
    style_spans: Sequence[
        tuple[tuple[float, float, float, float], float | None, int | None]
    ],
) -> tuple[float | None, int | None]:
    overlap_by_style: dict[tuple[float | None, int | None], float] = {}
    style_values: dict[
        tuple[float | None, int | None], tuple[float | None, int | None]
    ] = {}
    for span_bbox, font_size, color in style_spans:
        overlap = _rect_intersection_area(word_bbox, span_bbox)
        if overlap <= 0.0:
            continue
        key = (round(font_size, 3) if font_size is not None else None, color)
        overlap_by_style[key] = overlap_by_style.get(key, 0.0) + overlap
        style_values[key] = (font_size, color)
    if not overlap_by_style:
        return (None, None)
    best_key = max(overlap_by_style.items(), key=lambda item: item[1])[0]
    return style_values[best_key]


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
        # Preserve the original page background instead of painting a white box.
        page.add_redact_annot(fitz.Rect(*bbox), fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        document.save(final_pdf)
    finally:
        document.close()


def _verify_footer_removed(
    pdf_path: Path,
    redaction_bbox: tuple[float, float, float, float],
) -> bool:
    words, _page_width, _page_height = _read_last_page_words(pdf_path)
    return not any(
        _rectangles_overlap(redaction_bbox, (word.x0, word.y0, word.x1, word.y1))
        for word in words
    )


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
        _cleanup_failed_output(final_pdf)
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
        _cleanup_failed_output(final_pdf)
        preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
        return NativePdfPostprocessResult(
            status="unsafe_geometry",
            final_pdf_path=None,
            raw_pdf_path=str(preserved),
            warning=_build_warning("unsafe_geometry", preserved),
        )

    redaction_bbox = _expand_bbox(detection.bbox)

    try:
        _apply_footer_redaction(raw_pdf, final_pdf, redaction_bbox)
        if not _verify_footer_removed(final_pdf, redaction_bbox):
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
