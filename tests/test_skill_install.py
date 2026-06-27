import json
from pathlib import Path

import pytest

from lark_synced_export import skill_install
from lark_synced_export.skill_install import (
    INSTALL_METADATA_FILENAME,
    bundled_skill_dir,
    bundled_skill_markdown,
    run_skill_install,
)


def test_bundled_skill_dir_contains_skill_markdown():
    root = bundled_skill_dir()

    assert root.joinpath("SKILL.md").is_file()


def test_bundled_skill_markdown_mentions_commands_and_prereqs():
    text = bundled_skill_markdown()

    assert "lark-doc-exporter doctor" in text
    assert "lark-doc-exporter skill install" in text
    assert "lark-cli" in text
    assert "Chromium" in text


def test_run_skill_install_auto_uses_existing_hosts_only(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".agents" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills").mkdir(parents=True)

    result = run_skill_install(host="auto", force=False, dry_run=True, home=home)

    assert result["dry_run"] is True
    assert [item["host"] for item in result["targets"]] == ["codex", "claude"]
    assert [item["action"] for item in result["targets"]] == ["install", "install"]


def test_run_skill_install_explicit_host_creates_parent_and_writes_metadata(
    tmp_path: Path,
):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    metadata = json.loads(
        (target_dir / INSTALL_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    assert result["targets"][0]["host"] == "codex"
    assert result["targets"][0]["action"] == "install"
    assert (target_dir / "SKILL.md").is_file()
    assert metadata["tool"] == "lark-doc-exporter"
    assert metadata["host"] == "codex"


def test_run_skill_install_refuses_unknown_existing_directory_without_force(
    tmp_path: Path,
):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")

    with pytest.raises(RuntimeError, match="--force"):
        run_skill_install(host="codex", force=False, dry_run=False, home=home)


def test_run_skill_install_force_overwrites_unknown_existing_directory(tmp_path: Path):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")

    result = run_skill_install(host="codex", force=True, dry_run=False, home=home)

    assert result["targets"][0]["action"] == "overwrite"
    assert "lark-doc-exporter doctor" in (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("metadata_payload", ["{not json", "[]", '"x"', "1"])
def test_run_skill_install_force_recovers_from_invalid_metadata(
    tmp_path: Path, metadata_payload: str
):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")
    (target_dir / INSTALL_METADATA_FILENAME).write_text(
        metadata_payload, encoding="utf-8"
    )

    result = run_skill_install(host="codex", force=True, dry_run=False, home=home)

    assert result["targets"][0]["action"] == "overwrite"
    assert "lark-doc-exporter doctor" in (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_run_skill_install_auto_rejects_host_root_file(tmp_path: Path):
    home = tmp_path / "home"
    codex_root = home / ".agents" / "skills"
    codex_root.parent.mkdir(parents=True)
    codex_root.write_text("not a directory", encoding="utf-8")
    (home / ".claude" / "skills").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="not a directory"):
        run_skill_install(host="auto", force=False, dry_run=True, home=home)


def test_run_skill_install_upgrades_existing_managed_install(tmp_path: Path):
    home = tmp_path / "home"

    initial = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    (target_dir / "SKILL.md").write_text("stale managed content", encoding="utf-8")

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    assert initial["targets"][0]["action"] == "install"
    assert result["targets"][0]["action"] == "upgrade"
    assert "lark-doc-exporter doctor" in (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_run_skill_install_restores_existing_target_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    run_skill_install(host="codex", force=False, dry_run=False, home=home)
    (target_dir / "SKILL.md").write_text("managed but existing", encoding="utf-8")

    real_replace = skill_install.replace_path

    def fail_stage_replace(source: Path, destination: Path) -> None:
        if source.name == "lark-doc-exporter" and destination == target_dir:
            raise OSError("swap failed")
        real_replace(source, destination)

    monkeypatch.setattr(skill_install, "replace_path", fail_stage_replace)

    with pytest.raises(OSError, match="swap failed"):
        run_skill_install(host="codex", force=False, dry_run=False, home=home)

    assert (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "managed but existing"


def test_run_skill_install_dry_run_does_not_write_files(tmp_path: Path):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=True, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    assert result["targets"][0]["target_dir"] == str(target_dir)
    assert result["targets"][0]["action"] == "install"
    assert target_dir.exists() is False
