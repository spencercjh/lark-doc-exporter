from pathlib import Path

from lark_synced_export.mention_markdown import (
    normalize_markdown_user_mentions,
    normalize_markdown_user_mentions_file,
)


def test_normalize_markdown_user_mentions_replaces_user_cite_with_user_name():
    source = (
        'Owner：<cite type="user" user-id="ou_b2c4" '
        'user-name="蔡佳昊(spencer)"></cite>\n'
    )

    result = normalize_markdown_user_mentions(source)

    assert result == "Owner：蔡佳昊(spencer)\n"


def test_normalize_markdown_user_mentions_unescapes_user_name_entities():
    source = (
        'Maintainer：<cite type="user" user-id="ou_b2c4" '
        'user-name="Tom &amp; Jerry"></cite>\n'
    )

    result = normalize_markdown_user_mentions(source)

    assert result == "Maintainer：Tom & Jerry\n"


def test_normalize_markdown_user_mentions_leaves_other_cite_types_unchanged():
    source = '<cite type="doc" token="doccn"></cite>\n'

    assert normalize_markdown_user_mentions(source) == source


def test_normalize_markdown_user_mentions_leaves_missing_user_name_unchanged():
    source = '<cite type="user" user-id="ou_b2c4"></cite>\n'

    assert normalize_markdown_user_mentions(source) == source


def test_normalize_markdown_user_mentions_file_rewrites_in_place(tmp_path: Path):
    markdown_path = tmp_path / "demo.md"
    markdown_path.write_text(
        'Owner：<cite type="user" user-id="ou_b2c4" user-name="蔡佳昊(spencer)"></cite>\n',
        encoding="utf-8",
    )

    normalize_markdown_user_mentions_file(markdown_path)

    assert markdown_path.read_text(encoding="utf-8") == "Owner：蔡佳昊(spencer)\n"
