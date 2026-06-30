from pathlib import Path

from lark_synced_export.native_pdf_footer import (
    FooterDetection,
    NativePdfPostprocessResult,
    PdfWord,
    _read_last_page_words,
    detect_footer,
    normalize_footer_text,
    postprocess_native_pdf,
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


def test_detect_footer_matches_single_bottom_cluster_with_tiny_word_overlap():
    words = [
        PdfWord("(注：内容由", 24, 792, 116, 806),
        PdfWord("AI", 115.5, 792, 138, 806),
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


def test_detect_footer_returns_unsafe_geometry_for_stacked_two_line_fragments():
    words = [
        PdfWord("(注：内容由AI", 24, 792, 136, 806),
        PdfWord("生成，请谨慎参考）", 24, 804, 138, 818),
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

    assert result == NativePdfPostprocessResult(
        status="not_found",
        final_pdf_path=str(final_pdf),
        raw_pdf_path=None,
        warning=None,
    )
    assert final_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not preserved_raw_pdf.exists()


def test_postprocess_native_pdf_returns_detection_warning(monkeypatch, tmp_path: Path):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    final_pdf.write_bytes(b"%PDF-1.4\nstale\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words",
        lambda _path: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "detection_failed"
    assert result.final_pdf_path is None
    assert result.raw_pdf_path == str(preserved_raw_pdf)
    assert result.warning is not None
    assert "detection_failed" in result.warning
    assert str(preserved_raw_pdf) in result.warning
    assert preserved_raw_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not final_pdf.exists()


def test_postprocess_native_pdf_returns_unsafe_geometry_warning(
    monkeypatch, tmp_path: Path
):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    final_pdf.write_bytes(b"%PDF-1.4\nstale\n")

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
    assert result.final_pdf_path is None
    assert result.raw_pdf_path == str(preserved_raw_pdf)
    assert result.warning is not None
    assert "unsafe_geometry" in result.warning
    assert str(preserved_raw_pdf) in result.warning
    assert preserved_raw_pdf.read_bytes() == raw_pdf.read_bytes()
    assert not final_pdf.exists()


def test_postprocess_native_pdf_returns_mask_failed_when_verification_fails(
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
        lambda _raw, dst, _bbox: dst.write_bytes(b"%PDF-1.4\nstill-footer\n"),
    )
    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._verify_footer_removed",
        lambda _path: False,
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "mask_failed"
    assert result.final_pdf_path is None
    assert result.raw_pdf_path == str(preserved_raw_pdf)
    assert result.warning is not None
    assert "mask_failed" in result.warning
    assert str(preserved_raw_pdf) in result.warning
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
        lambda _path, _bbox: True,
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result == NativePdfPostprocessResult(
        status="removed",
        final_pdf_path=str(final_pdf),
        raw_pdf_path=None,
        warning=None,
    )
    assert final_pdf.exists()
    assert not preserved_raw_pdf.exists()


def test_postprocess_native_pdf_uses_padded_mask_bbox(monkeypatch, tmp_path: Path):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")
    capture: dict[str, tuple[float, float, float, float]] = {}

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

    def fake_apply(_raw: Path, dst: Path, bbox: tuple[float, float, float, float]):
        capture["bbox"] = bbox
        dst.write_bytes(b"%PDF-1.4\nclean\n")

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._apply_footer_redaction", fake_apply
    )
    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._verify_footer_removed",
        lambda _path, _bbox: True,
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "removed"
    assert capture["bbox"] == (18.0, 788.0, 264.0, 810.0)


def test_postprocess_native_pdf_verifies_only_the_redacted_region(
    monkeypatch, tmp_path: Path
):
    raw_pdf = tmp_path / "demo.native-raw.pdf"
    final_pdf = tmp_path / "demo.pdf"
    preserved_raw_pdf = tmp_path / "preserved" / "demo.native-raw.pdf"
    raw_pdf.write_bytes(b"%PDF-1.4\nraw\n")

    body_copy = [
        PdfWord("(注：内容由", 24, 193.26, 116, 207.26),
        PdfWord("AI", 120, 193.26, 138, 207.26),
        PdfWord("生成，请谨慎参考）", 142, 193.26, 258, 207.26),
    ]
    footer_copy = [
        PdfWord("(注：内容由", 24, 792, 116, 806),
        PdfWord("AI", 120, 792, 138, 806),
        PdfWord("生成，请谨慎参考）", 142, 792, 258, 806),
    ]

    def fake_read(path: Path):
        if path == raw_pdf:
            return body_copy + footer_copy, 595.0, 842.0
        return body_copy, 595.0, 842.0

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._read_last_page_words", fake_read
    )
    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer._apply_footer_redaction",
        lambda _raw, dst, _bbox: dst.write_bytes(b"%PDF-1.4\nclean\n"),
    )

    result = postprocess_native_pdf(raw_pdf, final_pdf, preserved_raw_pdf)

    assert result.status == "removed"
    assert result.final_pdf_path == str(final_pdf)
    assert result.raw_pdf_path is None


def test_read_last_page_words_requests_sorted_word_order(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "demo.pdf"
    capture: dict[str, object] = {}

    class FakePage:
        rect = type("Rect", (), {"width": 595.0, "height": 842.0})()

        def get_text(self, mode: str, sort: bool = False):
            capture["mode"] = mode
            capture["sort"] = sort
            return [(20, 100, 40, 112, "正文")]

    class FakeDocument:
        def __getitem__(self, index: int):
            assert index == -1
            return FakePage()

        def close(self):
            capture["closed"] = True

    monkeypatch.setattr(
        "lark_synced_export.native_pdf_footer.fitz.open",
        lambda _path: FakeDocument(),
    )

    words, page_width, page_height = _read_last_page_words(pdf_path)

    assert capture == {"mode": "words", "sort": True, "closed": True}
    assert words == [PdfWord("正文", 20.0, 100.0, 40.0, 112.0)]
    assert page_width == 595.0
    assert page_height == 842.0
