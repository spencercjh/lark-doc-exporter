from lark_synced_export.skill_install import bundled_skill_dir, bundled_skill_markdown


def test_bundled_skill_dir_contains_skill_markdown():
    root = bundled_skill_dir()

    assert root.joinpath("SKILL.md").is_file()


def test_bundled_skill_markdown_mentions_commands_and_prereqs():
    text = bundled_skill_markdown()

    assert "lark-doc-exporter doctor" in text
    assert "lark-doc-exporter skill install" in text
    assert "lark-cli" in text
    assert "Chromium" in text
