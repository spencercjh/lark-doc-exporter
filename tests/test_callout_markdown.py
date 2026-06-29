from pathlib import Path

from lark_synced_export.callout_markdown import (
    extract_callout_type,
    normalize_markdown_callouts,
    normalize_markdown_callouts_file,
)


def test_normalize_markdown_callouts_converts_known_emoji_and_preserves_structure():
    source = (
        '<callout emoji="💡">\n'
        "**核心结论：**Hosted.ai 与 HAMi 的关系，更准确地说是……\n"
        "\n"
        "**这份版本的目标：**按模板把 Hosted.ai 的公开材料严格落进……\n"
        "- 第一条\n"
        "![](images/demo.png)\n"
        "</callout>\n"
    )

    result = normalize_markdown_callouts(source)

    assert result == (
        "> [!TIP]\n"
        "> 💡 **核心结论：**Hosted.ai 与 HAMi 的关系，更准确地说是……\n"
        ">\n"
        "> **这份版本的目标：**按模板把 Hosted.ai 的公开材料严格落进……\n"
        "> - 第一条\n"
        "> ![](images/demo.png)\n"
    )


def test_normalize_markdown_callouts_prefixes_emoji_to_plain_text_and_unknown_defaults_note():
    source = '<callout emoji="🧪">\nPlain text body\n</callout>\n'

    result = normalize_markdown_callouts(source)

    assert result == "> [!NOTE]\n> 🧪 Plain text body\n"


def test_normalize_markdown_callouts_keeps_empty_callout_as_empty_blockquote():
    source = '<callout emoji="📌">\n</callout>\n'

    result = normalize_markdown_callouts(source)

    assert result == "> [!NOTE]\n>\n"


def test_normalize_markdown_callouts_leaves_unclosed_callout_unchanged():
    source = '<callout emoji="💡">\nBroken body\n'

    assert normalize_markdown_callouts(source) == source


def test_extract_callout_type_accepts_only_canonical_markers():
    assert extract_callout_type("[!TIP]") == "TIP"
    assert extract_callout_type("[!WARNING]") == "WARNING"
    assert extract_callout_type("> [!TIP]") is None
    assert extract_callout_type("[!UNKNOWN]") is None


def test_normalize_markdown_callouts_file_rewrites_in_place(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    markdown_path.write_text(
        '<callout emoji="📌">\n这家公司的公开强项是“怎么卖 GPU”。\n</callout>\n',
        encoding="utf-8",
    )

    normalize_markdown_callouts_file(markdown_path)

    assert markdown_path.read_text(encoding="utf-8") == (
        "> [!NOTE]\n> 📌 这家公司的公开强项是“怎么卖 GPU”。\n"
    )
