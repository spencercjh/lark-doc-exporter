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


def test_detect_footer_returns_not_found_outside_footer_zone():
    words = [
        PdfWord("(注：内容由", 24, 640, 116, 654),
        PdfWord("AI", 120, 640, 138, 654),
        PdfWord("生成，请谨慎参考）", 142, 640, 258, 654),
    ]

    detection = detect_footer(words, page_width=595.0, page_height=842.0)

    assert detection.status == "not_found"
    assert detection.bbox is None


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
