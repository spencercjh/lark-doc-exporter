# Native PDF AI Footer Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--pdf-mode native` so `lark-doc-exporter` can export Feishu native PDF, remove the AI footer when it is safely detected on the last page, and fail with explicit warnings plus a preserved raw-native artifact when the footer cannot be removed safely.

**Architecture:** Add one new module, `native_pdf_footer.py`, that splits the work into two layers: pure footer-detection/geometry rules and a PyMuPDF-backed post-process state machine. Keep the existing temp-doc front half intact, but move temp-doc deletion so native PDF export still happens before cleanup, stage raw native PDFs in tmp space, and only preserve `<stem>.native-raw.pdf` into the real output directory on failure. Make the CLI print JSON for both success and controlled native-mode failures, and mirror native failure warnings to stderr.

**Tech Stack:** Python 3.14, `uv`, `pytest`, `lark-cli`, PyMuPDF (`fitz`), existing local Chromium renderer for rendered mode

---

## File Structure

- Create: `src/lark_synced_export/native_pdf_footer.py`
  Responsibility: pure footer normalization/detection rules plus the PyMuPDF-backed native PDF footer post-processor.
- Modify: `pyproject.toml`
  Responsibility: add the native PDF geometry backend dependency.
- Modify: `src/lark_synced_export/exporter.py`
  Responsibility: keep the temp-doc/markdown pipeline, add the native PDF branch, and emit native footer post-process JSON/warning payloads.
- Modify: `src/lark_synced_export/cli.py`
  Responsibility: parse `--pdf-mode`, reject incompatible theme/CSS usage in native mode, and return exit `1` while still printing JSON for controlled native-mode failures.
- Create: `tests/test_native_pdf_footer.py`
  Responsibility: pure footer rule tests plus post-process state-machine integration tests.
- Modify: `tests/test_exporter.py`
  Responsibility: native-mode exporter integration, output payload shape, and markdown+pdf partial-failure behavior.
- Create: `tests/test_cli.py`
  Responsibility: CLI option parsing, native-mode rejection semantics, and failure-JSON exit behavior.
- Modify: `README.md`
  Responsibility: document rendered-vs-native PDF modes, warning/raw-artifact semantics, and the native-mode restrictions.
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
  Responsibility: keep the companion skill docs aligned with the new CLI surface.

### Task 1: Add pure footer detection and geometry rules

**Files:**
- Create: `src/lark_synced_export/native_pdf_footer.py`
- Create: `tests/test_native_pdf_footer.py`

- [ ] **Step 1: Write the failing pure-rule tests**

Create `tests/test_native_pdf_footer.py`:

```python
from lark_synced_export.native_pdf_footer import (
    FooterDetection,
    PdfWord,
    detect_footer,
    normalize_footer_text,
)


def test_normalize_footer_text_canonicalizes_pdf_artifacts():
    text = "(注：内容由\u0001AI\u0001⽣成，请谨慎参考）"

    assert normalize_footer_text(text) == "(注:内容由AI生成,请谨慎参考)"


def test_detect_footer_matches_single_bottom_cluster():
    words = [
        PdfWord("(注：内容由", 24, 792, 116, 806),
        PdfWord("AI", 120, 792, 138, 806),
        PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=842.0)

    assert detection == FooterDetection(
        status="matched",
        normalized_text="(注:内容由AI生成,请谨慎参考)",
        word_indexes=(0, 1, 2),
        bbox=(24.0, 792.0, 258.0, 806.0),
    )


def test_detect_footer_matches_footer_anywhere_on_last_page():
    words = [
        PdfWord("(注：内容由", 24, 193.26, 116, 207.26),
        PdfWord("AI", 120, 193.26, 138, 207.26),
        PdfWord("生成，请谨慎参考）", 142, 193.26, 258, 207.26),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=841.92)

    assert detection == FooterDetection(
        status="matched",
        normalized_text="(注:内容由AI生成,请谨慎参考)",
        word_indexes=(0, 1, 2),
        bbox=(24.0, 193.26, 258.0, 207.26),
    )


def test_detect_footer_prefers_lowest_whitelist_match_on_last_page():
    words = [
        PdfWord("(注：内容由", 24, 193.26, 116, 207.26),
        PdfWord("AI", 120, 193.26, 138, 207.26),
        PdfWord("生成，请谨慎参考）", 142, 193.26, 258, 207.26),
        PdfWord("(注：内容由", 24, 792, 116, 806),
        PdfWord("AI", 120, 792, 138, 806),
        PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=841.92)

    assert detection == FooterDetection(
        status="matched",
        normalized_text="(注:内容由AI生成,请谨慎参考)",
        word_indexes=(3, 4, 5),
        bbox=(24.0, 792.0, 258.0, 806.0),
    )


def test_detect_footer_returns_unsafe_geometry_for_split_clusters():
    words = [
        PdfWord("(注：内容由AI", 24, 792, 136, 806),
        PdfWord("生成，请谨慎参考）", 224, 792, 338, 806),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=842.0)

    assert detection.status == "unsafe_geometry"
    assert detection.normalized_text == "(注:内容由AI生成,请谨慎参考)"


def test_detect_footer_returns_unsafe_geometry_for_paragraph_like_width():
    words = [
        PdfWord("(注：内容由AI生成，请谨慎参考）", 24, 792, 540, 806),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=842.0)

    assert detection.status == "unsafe_geometry"
    assert detection.bbox == (24.0, 792.0, 540.0, 806.0)


def test_detect_footer_returns_unsafe_geometry_when_mask_hits_other_text():
    words = [
        PdfWord("(注：内容由", 24, 792, 116, 806),
        PdfWord("AI", 120, 792, 138, 806),
        PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
        PdfWord("附注正文", 20, 788, 82, 808),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=842.0)

    assert detection.status == "unsafe_geometry"
    assert detection.normalized_text == "(注:内容由AI生成,请谨慎参考)"
```

- [ ] **Step 2: Run the test and verify it fails because the module does not exist yet**

Run:

```bash
uv run pytest tests/test_native_pdf_footer.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lark_synced_export.native_pdf_footer'`.

- [ ] **Step 3: Implement the pure-rule layer**

Create `src/lark_synced_export/native_pdf_footer.py`:

```python
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Sequence


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


def detect_footer(
    words: Sequence[PdfWord],
    page_width: float,
    page_height: float,
) -> FooterDetection:
    indexed_words = list(enumerate(words))
    if not indexed_words:
        return FooterDetection("not_found", None, (), None)

    clusters: list[list[tuple[int, PdfWord]]] = []
    current = [indexed_words[0]]
    for item in indexed_words[1:]:
        previous_word = current[-1][1]
        _, word = item
        same_line = min(previous_word.y1, word.y1) > max(previous_word.y0, word.y0)
        small_gap = word.x0 - previous_word.x1 <= 12.0
        if same_line and small_gap:
            current.append(item)
        else:
            clusters.append(current)
            current = [item]
    clusters.append(current)

    matches: list[tuple[list[tuple[int, PdfWord]], str]] = []
    for cluster in clusters:
        for start in range(len(cluster)):
            for end in range(start + 1, len(cluster) + 1):
                candidate = cluster[start:end]
                normalized_text = normalize_footer_text(
                    "".join(word.text for _, word in candidate)
                )
                if normalized_text in FOOTER_VARIANTS:
                    matches.append((candidate, normalized_text))

    if not matches:
        for start in range(len(clusters)):
            combined: list[tuple[int, PdfWord]] = []
            for end in range(start, len(clusters)):
                combined.extend(clusters[end])
                if end == start:
                    continue

                normalized_text = normalize_footer_text(
                    "".join(word.text for _, word in combined)
                )
                if normalized_text in FOOTER_VARIANTS:
                    return FooterDetection("unsafe_geometry", normalized_text, (), None)
        return FooterDetection("not_found", None, (), None)

    matches.sort(
        key=lambda match: (
            -min(word.y0 for _, word in match[0]),
            -max(word.y1 for _, word in match[0]),
            max(word.x1 for _, word in match[0]) - min(word.x0 for _, word in match[0]),
            len(match[0]),
        )
    )
    cluster, normalized_text = matches[0]
    word_indexes = tuple(index for index, _ in cluster)
    x0 = min(word.x0 for _, word in cluster)
    y0 = min(word.y0 for _, word in cluster)
    x1 = max(word.x1 for _, word in cluster)
    y1 = max(word.y1 for _, word in cluster)
    bbox = (float(x0), float(y0), float(x1), float(y1))

    if (y1 - y0) > max(36.0, page_height * 0.05):
        return FooterDetection("unsafe_geometry", normalized_text, word_indexes, bbox)
    if (x1 - x0) > page_width * 0.80:
        return FooterDetection("unsafe_geometry", normalized_text, word_indexes, bbox)

    expanded = (x0 - 6.0, y0 - 4.0, x1 + 6.0, y1 + 4.0)
    for index, word in enumerate(words):
        if index in word_indexes:
            continue
        if _rectangles_overlap(expanded, (word.x0, word.y0, word.x1, word.y1)):
            return FooterDetection(
                "unsafe_geometry", normalized_text, word_indexes, bbox
            )

    return FooterDetection("matched", normalized_text, word_indexes, bbox)
```

- [ ] **Step 4: Run the targeted test and verify the pure rules pass**

Run:

```bash
uv run pytest tests/test_native_pdf_footer.py -q
```

Expected: PASS, including the new mid-page-footer and lowest-match-selection
coverage.

- [ ] **Step 5: Commit the pure-rule slice**

```bash
git add src/lark_synced_export/native_pdf_footer.py tests/test_native_pdf_footer.py
git commit -S -s -m "feat(native-pdf): add footer detection rules"
```

### Task 2: Add the PyMuPDF-backed native PDF footer post-processor

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/lark_synced_export/native_pdf_footer.py`
- Modify: `tests/test_native_pdf_footer.py`

- [ ] **Step 1: Extend the test file with state-machine integration tests**

Append to `tests/test_native_pdf_footer.py`:

```python
from pathlib import Path

from lark_synced_export.native_pdf_footer import (
    NativePdfPostprocessResult,
    PdfWord,
    postprocess_native_pdf,
)


def test_postprocess_native_pdf_copies_raw_when_footer_not_found(
    monkeypatch, tmp_path: Path
):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words",
        lambda _path: ([PdfWord("正文", 20, 100, 80, 116)], 595.0, 842.0),
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "not_found"
    assert result.final_pdf_path == str(final_pdf)
    assert result.raw_pdf_path is None
    assert result.warning is None
    assert final_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not preserved_raw_pdf.exists()


def test_postprocess_native_pdf_returns_detection_warning(monkeypatch, tmp_path: Path):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words",
        lambda _path: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "detection_failed"
    assert "detection_failed" in result.warning
    assert str(preserved_raw_pdf) in result.warning
    assert result.raw_pdf_path == str(preserved_raw_pdf)
    assert preserved_raw_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not final_pdf.exists()


def test_postprocess_native_pdf_returns_unsafe_geometry_warning(
    monkeypatch, tmp_path: Path
):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words",
        lambda _path: (
            [
                PdfWord("(注：内容由", 24, 792, 116, 806),
                PdfWord("AI", 120, 792, 138, 806),
                PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
                PdfWord("附注正文", 20, 788, 82, 808),
            ],
            595.0,
            842.0,
        ),
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "unsafe_geometry"
    assert "unsafe_geometry" in result.warning
    assert str(preserved_raw_pdf) in result.warning
    assert result.raw_pdf_path == str(preserved_raw_pdf)
    assert preserved_raw_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not final_pdf.exists()


def test_postprocess_native_pdf_redacts_footer_when_geometry_is_safe(
    monkeypatch, tmp_path: Path
):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words",
        lambda _path: (
            [
                PdfWord("(注：内容由", 24, 792, 116, 806),
                PdfWord("AI", 120, 792, 138, 806),
                PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
            ],
            595.0,
            842.0,
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._apply_footer_redaction",
        lambda _raw, dst, _bbox: dst.write_bytes(b"%PDF-1.4\nclean\n"),
    )
    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._verify_footer_removed",
        lambda _path: True,
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "removed"
    assert result.final_pdf_path == str(final_pdf)
    assert result.raw_pdf_path is None
    assert result.warning is None
    assert final_pdf.exists()
    assert not preserved_raw_pdf.exists()
```

- [ ] **Step 2: Run the extended test file and verify it fails because the post-processor is still missing**

Run:

```bash
uv run pytest tests/test_native_pdf_footer.py -q
```

Expected: FAIL with `ImportError` / `AttributeError` for `NativePdfPostprocessResult` or `postprocess_native_pdf`.

- [ ] **Step 3: Add the dependency and implement the post-process state machine**

Modify `pyproject.toml` so `[project].dependencies` becomes:

```toml
dependencies = [
  "markdown>=3.7,<4",
  "playwright>=1.61.0,<2",
  "pymupdf>=1.26,<2",
]
```

Append to `src/lark_synced_export/native_pdf_footer.py`:

```python
import shutil
from pathlib import Path

import fitz


FAILURE_STATUSES = {"detection_failed", "unsafe_geometry", "mask_failed"}


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


def _build_warning(status: str, raw_pdf: Path) -> str:
    return (
        f"native PDF footer post-process failed ({status}); "
        f"raw native PDF kept at {raw_pdf}"
    )


def _read_last_page_words(pdf_path: Path) -> tuple[list[PdfWord], float, float]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[-1]
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
        doc.close()


def _copy_raw_pdf(raw_pdf: Path, final_pdf: Path) -> None:
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
    doc = fitz.open(raw_pdf)
    try:
        page = doc[-1]
        page.add_redact_annot(fitz.Rect(*bbox), fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        doc.save(final_pdf)
    finally:
        doc.close()


def _verify_footer_removed(pdf_path: Path) -> bool:
    words, page_width, page_height = _read_last_page_words(pdf_path)
    return detect_footer(words, page_width, page_height).status == "not_found"


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
            preserved = _preserve_raw_pdf(raw_pdf, preserved_raw_pdf)
            return NativePdfPostprocessResult(
                status="mask_failed",
                final_pdf_path=None,
                raw_pdf_path=str(preserved),
                warning=_build_warning("mask_failed", preserved),
            )
    except Exception:
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
```

- [ ] **Step 4: Sync dependencies and rerun the native footer test file**

Run:

```bash
uv sync --group dev
uv run pytest tests/test_native_pdf_footer.py -q
```

Expected: PASS with `10 passed`.

- [ ] **Step 5: Commit the post-processor slice**

```bash
git add pyproject.toml src/lark_synced_export/native_pdf_footer.py tests/test_native_pdf_footer.py uv.lock
git commit -S -s -m "feat(native-pdf): add footer postprocessor"
```

### Task 3: Wire native PDF mode into the exporter result contract

**Files:**
- Modify: `src/lark_synced_export/exporter.py`
- Modify: `tests/test_exporter.py`

- [ ] **Step 1: Add failing exporter tests for native success and native failure**

Append to `tests/test_exporter.py`:

```python
from lark_synced_export.native_pdf_footer import NativePdfPostprocessResult


def test_export_document_native_not_found_sets_pdf_payload(monkeypatch, tmp_path: Path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_native_pdf = stage_dir / "demo.native-raw.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_postprocess(
        raw_pdf: Path,
        final_pdf: Path,
        preserved_raw_pdf: Path,
    ) -> NativePdfPostprocessResult:
        final_pdf.write_bytes(b"%PDF-1.4\nclean\n")
        return NativePdfPostprocessResult(
            status="not_found",
            final_pdf_path=str(final_pdf),
            raw_pdf_path=None,
            warning=None,
        )

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory", lambda *a, **k: DummyTempDir()
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda token, stage, stem: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf", fake_postprocess
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert result["ok"] is True
    assert result["pdf_mode"] == "native"
    assert result["outputs"]["pdf"].endswith("demo.pdf")
    assert result["ai_footer_postprocess"]["status"] == "not_found"
    assert result["ai_footer_postprocess"]["raw_pdf_path"] is None
    assert result["warnings"] == []


def test_export_document_native_failure_keeps_markdown_and_warning(
    monkeypatch, tmp_path: Path
):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    raw_markdown_path = stage_dir / "demo.raw.md"
    raw_markdown_path.write_text("# Demo\n", encoding="utf-8")
    raw_native_pdf = stage_dir / "demo.source.pdf"
    raw_native_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    preserved_raw_pdf = tmp_path / "out" / "demo.native-raw.pdf"

    class DummyTempDir:
        def __enter__(self):
            return str(stage_dir)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_localize(src: Path, dst: Path, _assets: Path) -> int:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "lark_synced_export.exporter.tempfile.TemporaryDirectory", lambda *a, **k: DummyTempDir()
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.fetch_full_xml", lambda _doc: "<title>Demo</title>"
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.expand_synced_references", lambda xml: (xml, 0)
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.normalize_xml_for_create",
        lambda xml, suffix: (xml, "Demo"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.create_temp_doc",
        lambda xml, stage: ("tmp-token", "https://example.com/doc"),
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_markdown",
        lambda token, stage, stem: raw_markdown_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.export_native_pdf",
        lambda token, stage, stem: raw_native_pdf,
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.delete_temp_doc", lambda _token: None
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.localize_markdown_images", fake_localize
    )
    monkeypatch.setattr(
        "lark_synced_export.exporter.postprocess_native_pdf",
        lambda raw, final, preserved: NativePdfPostprocessResult(
            status="unsafe_geometry",
            final_pdf_path=None,
            raw_pdf_path=str(preserved_raw_pdf),
            warning=f"native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at {preserved_raw_pdf}",
        ),
    )

    result = export_document(
        doc_ref="demo",
        output_dir=tmp_path / "out",
        formats=["markdown", "pdf"],
        title_suffix="",
        file_stem="demo",
        keep_temp_doc=False,
        theme_name="default",
        override_css=None,
        pdf_mode="native",
    )

    assert result["ok"] is False
    assert "markdown" in result["outputs"]
    assert "pdf" not in result["outputs"]
    assert result["ai_footer_postprocess"]["status"] == "unsafe_geometry"
    assert result["ai_footer_postprocess"]["raw_pdf_path"].endswith(
        "demo.native-raw.pdf"
    )
    assert result["warnings"][0].startswith("native PDF footer post-process failed")
```

- [ ] **Step 2: Run the focused exporter tests and verify they fail because native mode is not wired yet**

Run:

```bash
uv run pytest tests/test_exporter.py -q -k native
```

Expected: FAIL because `export_document()` does not accept `pdf_mode` yet and `export_native_pdf` / `postprocess_native_pdf` are not imported.

- [ ] **Step 3: Wire the native PDF branch and the JSON payload contract**

Modify the imports at the top of `src/lark_synced_export/exporter.py`:

```python
from .native_pdf_footer import FAILURE_STATUSES, postprocess_native_pdf
```

Extend `export_doc()` so it supports PDF too:

```python
    suffix_map = {"markdown": "md", "pdf": "pdf"}
```

Add the helper:

```python
def export_native_pdf(temp_doc_token: str, output_dir: Path, file_stem: str) -> Path:
    result = export_doc(temp_doc_token, output_dir, file_stem, formats=["pdf"])
    return Path(result["pdf"])
```

Change the `export_document()` signature:

```python
def export_document(
    doc_ref: str,
    output_dir: Path,
    formats: list[str],
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    theme_name: str,
    override_css: Path | None,
    pdf_mode: str = "rendered",
) -> dict:
```

Inside `export_document()`, add the native-mode bookkeeping:

```python
    outputs: dict[str, str] = {}
    warnings: list[str] = []
    ai_footer_postprocess: dict | None = None
    localized_image_count = 0
```

Replace the current temp-doc export block and PDF block with:

```python
        needs_markdown_artifacts = "markdown" in formats or (
            "pdf" in formats and pdf_mode == "rendered"
        )

        try:
            localized_markdown_path: Path | None = None

            if needs_markdown_artifacts:
                raw_markdown_path = export_markdown(
                    temp_doc_token, stage_dir, f"{final_stem}.raw"
                )
                render_root = output_dir if "markdown" in formats else stage_dir
                localized_markdown_path = render_root / f"{final_stem}.md"
                assets_dir = render_root / "images"
                localized_image_count = localize_markdown_images(
                    raw_markdown_path, localized_markdown_path, assets_dir
                )
                normalize_markdown_user_mentions_file(localized_markdown_path)
                normalize_markdown_callouts_file(localized_markdown_path)

                if "markdown" in formats:
                    outputs["markdown"] = str(localized_markdown_path)

            if "pdf" in formats:
                output_pdf = output_dir / f"{final_stem}.pdf"
                if pdf_mode == "rendered":
                    assert localized_markdown_path is not None
                    theme_css_path = resolve_theme_css(theme_name)
                    body_html = stage_dir / "body.html"
                    render_html = stage_dir / "render.html"
                    render_markdown_body(localized_markdown_path, body_html)
                    build_render_html(
                        body_html, render_html, temp_title, theme_css_path, override_css
                    )
                    render_html_to_pdf(render_html, output_pdf)
                    outputs["pdf"] = str(output_pdf)
                else:
                    raw_native_pdf = export_native_pdf(
                        temp_doc_token, stage_dir, f"{final_stem}.native-raw"
                    )
                    preserved_raw_pdf = output_dir / f"{final_stem}.native-raw.pdf"
                    if output_pdf.exists():
                        output_pdf.unlink()
                    if preserved_raw_pdf.exists():
                        preserved_raw_pdf.unlink()
                    footer_result = postprocess_native_pdf(
                        raw_native_pdf, output_pdf, preserved_raw_pdf
                    )
                    ai_footer_postprocess = {
                        "status": footer_result.status,
                        "raw_pdf_path": footer_result.raw_pdf_path,
                        "warning": footer_result.warning,
                    }
                    if footer_result.warning:
                        warnings.append(footer_result.warning)
                    if footer_result.final_pdf_path:
                        outputs["pdf"] = footer_result.final_pdf_path
        finally:
            if not keep_temp_doc:
                delete_temp_doc(temp_doc_token)
```

Compute the final `ok` flag right before returning:

```python
    native_failure = (
        "pdf" in formats
        and pdf_mode == "native"
        and ai_footer_postprocess is not None
        and ai_footer_postprocess["status"] in FAILURE_STATUSES
    )
```

Return the expanded payload:

```python
    return {
        "ok": not native_failure,
        "doc": doc_ref,
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_deleted": not keep_temp_doc,
        "temp_doc_url": temp_doc_url,
        "localized_images": localized_image_count,
        "theme": theme_name if "pdf" in formats and pdf_mode == "rendered" else None,
        "pdf_mode": pdf_mode if "pdf" in formats else None,
        "ai_footer_postprocess": ai_footer_postprocess,
        "warnings": warnings,
        "outputs": outputs,
        "pdf_renderer": (
            "feishu-native"
            if "pdf" in formats and pdf_mode == "native"
            else "local-chromium" if "pdf" in formats else None
        ),
    }
```

- [ ] **Step 4: Run the focused exporter tests and the full exporter file**

Run:

```bash
uv run pytest tests/test_exporter.py -q
```

Expected: PASS, including the new native-mode cases.

- [ ] **Step 5: Commit the exporter-wiring slice**

```bash
git add src/lark_synced_export/exporter.py tests/test_exporter.py
git commit -S -s -m "feat(exporter): add native PDF mode"
```

### Task 4: Add the CLI contract, update user docs, and run final validation

**Files:**
- Modify: `src/lark_synced_export/cli.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`

- [ ] **Step 1: Write failing CLI tests for native-mode validation and controlled failure JSON**

Create `tests/test_cli.py`:

```python
import json
from pathlib import Path

import pytest

from lark_synced_export.cli import run_main


def test_run_main_rejects_custom_theme_in_native_pdf_mode(tmp_path: Path):
    with pytest.raises(
        SystemExit,
        match="--pdf-mode native does not support explicit --theme or --css",
    ):
        run_main(
            [
                "--doc",
                "demo",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--pdf-mode",
                "native",
                "--theme",
                "company",
            ]
        )


def test_run_main_returns_one_and_prints_json_for_controlled_native_failure(
    monkeypatch, capsys, tmp_path: Path
):
    monkeypatch.setattr(
        "lark_synced_export.cli.export_document",
        lambda **kwargs: {
            "ok": False,
            "doc": "demo",
            "pdf_mode": "native",
            "warnings": [
                "native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at /tmp/demo.native-raw.pdf"
            ],
            "ai_footer_postprocess": {
                "status": "unsafe_geometry",
                "raw_pdf_path": "/tmp/demo.native-raw.pdf",
                "warning": "native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at /tmp/demo.native-raw.pdf",
            },
            "outputs": {"markdown": str(tmp_path / "demo.md")},
        },
    )

    exit_code = run_main(
        [
            "--doc",
            "demo",
            "--output-dir",
            str(tmp_path),
            "--formats",
            "markdown,pdf",
            "--pdf-mode",
            "native",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["ai_footer_postprocess"]["status"] == "unsafe_geometry"
    assert payload["warnings"][0].startswith("native PDF footer post-process failed")
    assert "native PDF footer post-process failed" in captured.err
```

- [ ] **Step 2: Run the new CLI tests and verify they fail because `--pdf-mode` is not wired yet**

Run:

```bash
uv run pytest tests/test_cli.py -q
```

Expected: FAIL because `parse_export_args()` does not know `--pdf-mode` yet and `run_main()` always returns `0` for printed exporter payloads.

- [ ] **Step 3: Wire the CLI option and update the user-facing docs**

Modify `src/lark_synced_export/cli.py` to add the new option:

```python
    parser.add_argument(
        "--pdf-mode",
        choices=["rendered", "native"],
        default="rendered",
        help="PDF pipeline selection. Use `rendered` for local HTML/Chromium PDF or `native` for Feishu native PDF plus AI footer handling.",
    )
```

Add the native-mode validation right after format validation:

```python
    if (
        "pdf" in formats
        and args.pdf_mode == "native"
        and (args.theme != "default" or bool(args.css))
    ):
        raise SystemExit(
            "--pdf-mode native does not support explicit --theme or --css"
        )
```

Pass `pdf_mode` into `export_document()`:

```python
        pdf_mode=args.pdf_mode,
```

Change the CLI return contract:

```python
    for warning in result.get("warnings", []):
        sys.stderr.write(f"warning: {warning}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", False) else 1
```

Update the README introduction so it no longer claims that every PDF path avoids the Feishu server-side exporter:

```markdown
- Themeable locally rendered PDF by default
- Optional native Feishu PDF mode with AI-footer post-processing
```

Update the README Quick Start example:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

Then add a native-mode section under `## Output`:

````markdown
### Native PDF Mode

If you want Feishu native PDF layout instead of the local HTML/Chromium path:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats pdf \
  --pdf-mode native
```

Native mode rules:

- only the PDF branch changes; markdown stays on the current markdown pipeline
- explicit non-default `--theme` / `--css` are rejected
- success states are `removed` and `not_found`
- failure states emit warnings and keep `<stem>.native-raw.pdf` for inspection
````

Update `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md` by changing the description line so it no longer says the tool only renders local PDFs, mention native mode availability in the export example, and add one key-parameter bullet:

```markdown
- `--pdf-mode rendered|native`: choose local rendered PDF or native Feishu PDF plus footer handling
```

- [ ] **Step 4: Run focused tests, full CI, and the manual acceptance commands**

Run:

```bash
uv run pytest tests/test_native_pdf_footer.py tests/test_exporter.py tests/test_cli.py -q
make ci
uv run lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir tmp/manual-smoke/native-bvxx \
  --formats pdf \
  --pdf-mode native
uv run lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/CBecwNJO7ieT1BkNIXeclJyCnPh" \
  --output-dir tmp/manual-smoke/native-cbec \
  --formats pdf \
  --pdf-mode native
uv run pytest tests/test_native_pdf_footer.py -q -k unsafe_geometry
```

Expected:

- focused pytest command: PASS
- `make ci`: PASS
- `BVXX...` manual run: JSON `ok: true`, `pdf_mode: "native"`, `ai_footer_postprocess.status: "removed"`
- `CBec...` manual run: JSON `ok: true`, `pdf_mode: "native"`, `ai_footer_postprocess.status: "not_found"`
- `-k unsafe_geometry`: PASS as the anti-footgun acceptance record until a third real doc sample is available

- [ ] **Step 5: Commit the CLI/docs/final-validation slice**

```bash
git add src/lark_synced_export/cli.py tests/test_cli.py README.md src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md uv.lock
git commit -S -s -m "feat(cli): add native PDF footer mode"
```
