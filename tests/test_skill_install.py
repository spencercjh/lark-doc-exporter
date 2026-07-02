import json
from pathlib import Path

import pytest

from lark_synced_export.cli import run_main
from lark_synced_export.skill_install import (
    KITUP_METADATA_FILENAME,
    bundled_skill_dir,
    bundled_skill_markdown,
    run_skill_install,
)


def test_bundled_skill_dir_contains_skill_markdown():
    root = bundled_skill_dir()

    assert root.joinpath("SKILL.md").is_file()


def test_bundled_skill_markdown_mentions_native_first_commands_and_prereqs():
    text = bundled_skill_markdown()

    assert "lark-doc-exporter doctor" in text
    assert "lark-doc-exporter skill install" in text
    assert "lark-cli" in text
    assert "Chromium" in text
    assert "--pdf-mode native" in text
    assert "Prefer `--pdf-mode native`" in text


def test_run_skill_install_auto_uses_existing_hosts_only(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".agents" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills").mkdir(parents=True)

    result = run_skill_install(host="auto", force=False, dry_run=True, home=home)

    assert result["dry_run"] is True
    assert [item["host"] for item in result["targets"]] == ["claude", "codex"]
    assert [item["action"] for item in result["targets"]] == ["install", "install"]


def test_run_skill_install_auto_requires_existing_supported_host(tmp_path: Path):
    home = tmp_path / "home"

    with pytest.raises(RuntimeError, match="No supported host skill directory found"):
        run_skill_install(host="auto", force=False, dry_run=True, home=home)


def test_run_skill_install_explicit_host_creates_parent_and_writes_kitup_metadata(
    tmp_path: Path,
):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    metadata = json.loads(
        (target_dir / KITUP_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    assert result["targets"][0]["host"] == "codex"
    assert result["targets"][0]["action"] == "install"
    assert (target_dir / "SKILL.md").is_file()
    assert metadata["appId"] == "lark-doc-exporter"
    assert metadata["skillName"] == "lark-doc-exporter"
    assert metadata["source"] == "bundled"


def test_run_skill_install_explicit_claude_maps_to_claude_code_target(tmp_path: Path):
    home = tmp_path / "home"

    result = run_skill_install(host="claude", force=False, dry_run=False, home=home)

    target_dir = home / ".claude" / "skills" / "lark-doc-exporter"
    assert result["targets"][0]["host"] == "claude"
    assert target_dir.is_dir()
    assert (target_dir / KITUP_METADATA_FILENAME).is_file()


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
    assert (target_dir / KITUP_METADATA_FILENAME).is_file()
    assert "lark-doc-exporter doctor" in (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("metadata_payload", ["{not json", "[]", '"x"', "1"])
def test_run_skill_install_force_recovers_from_invalid_kitup_metadata(
    tmp_path: Path, metadata_payload: str
):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")
    (target_dir / KITUP_METADATA_FILENAME).write_text(
        metadata_payload, encoding="utf-8"
    )

    result = run_skill_install(host="codex", force=True, dry_run=False, home=home)

    assert result["targets"][0]["action"] == "overwrite"
    assert (target_dir / KITUP_METADATA_FILENAME).is_file()


def test_run_skill_install_force_recovers_from_non_utf8_kitup_metadata(tmp_path: Path):
    home = tmp_path / "home"
    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text("custom", encoding="utf-8")
    (target_dir / KITUP_METADATA_FILENAME).write_bytes(b"\xff")

    result = run_skill_install(host="codex", force=True, dry_run=False, home=home)

    assert result["targets"][0]["action"] == "overwrite"
    assert (target_dir / KITUP_METADATA_FILENAME).is_file()


def test_run_skill_install_auto_rejects_host_root_file(tmp_path: Path):
    home = tmp_path / "home"
    codex_root = home / ".agents" / "skills"
    codex_root.parent.mkdir(parents=True)
    codex_root.write_text("not a directory", encoding="utf-8")
    (home / ".claude" / "skills").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="not a directory"):
        run_skill_install(host="auto", force=False, dry_run=True, home=home)


def test_run_skill_install_explicit_codex_ignores_invalid_claude_root(tmp_path: Path):
    home = tmp_path / "home"
    claude_root = home / ".claude" / "skills"
    claude_root.parent.mkdir(parents=True)
    claude_root.write_text("not a directory", encoding="utf-8")

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    assert result["targets"][0]["host"] == "codex"
    assert target_dir.is_dir()
    assert (target_dir / KITUP_METADATA_FILENAME).is_file()


def test_run_skill_install_explicit_host_rejects_dangling_root_symlink(tmp_path: Path):
    home = tmp_path / "home"
    codex_root = home / ".agents" / "skills"
    codex_root.parent.mkdir(parents=True)
    codex_root.symlink_to(home / "missing-root")

    with pytest.raises(RuntimeError, match="exists but is not a directory"):
        run_skill_install(host="codex", force=False, dry_run=False, home=home)


def test_run_skill_install_upgrades_existing_managed_install_when_hash_changes(
    tmp_path: Path,
):
    home = tmp_path / "home"

    initial = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    metadata_path = target_dir / KITUP_METADATA_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["hash"] = "sha256:old"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (target_dir / "SKILL.md").write_text("stale managed content", encoding="utf-8")

    result = run_skill_install(host="codex", force=False, dry_run=False, home=home)

    assert initial["targets"][0]["action"] == "install"
    assert result["targets"][0]["action"] == "upgrade"
    assert "lark-doc-exporter doctor" in (target_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_run_skill_install_dry_run_does_not_write_files(tmp_path: Path):
    home = tmp_path / "home"

    result = run_skill_install(host="codex", force=False, dry_run=True, home=home)

    target_dir = home / ".agents" / "skills" / "lark-doc-exporter"
    assert result["targets"][0]["target_dir"] == str(target_dir)
    assert result["targets"][0]["action"] == "install"
    assert target_dir.exists() is False


def test_run_main_skill_install_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "lark_synced_export.cli.run_skill_install",
        lambda host, force, dry_run: {
            "ok": True,
            "dry_run": dry_run,
            "targets": [
                {
                    "host": host,
                    "action": "install",
                    "target_dir": "/tmp/.agents/skills/lark-doc-exporter",
                }
            ],
        },
    )

    assert run_main(["skill", "install", "--host", "codex", "--dry-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["targets"][0]["host"] == "codex"


def test_run_main_help_mentions_doctor_and_skill_install(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_main(["--help"])

    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "doctor" in help_text
    assert "skill install" in help_text


def test_run_main_export_route_still_uses_default_flags(
    monkeypatch,
    capsys,
    tmp_path: Path,
):
    calls: dict = {}

    def fake_export_document(**kwargs):
        calls.update(kwargs)
        return {
            "ok": True,
            "outputs": {"markdown": str(tmp_path / "demo.md")},
        }

    monkeypatch.setattr("lark_synced_export.cli.export_document", fake_export_document)

    assert (
        run_main(
            [
                "--doc",
                "demo-token",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "markdown",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert calls["doc_ref"] == "demo-token"
    assert calls["formats"] == ["markdown"]
    assert payload["outputs"]["markdown"].endswith("demo.md")
