from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.resources import as_file, files
import json
from pathlib import Path
import shutil
from typing import Final

from . import __version__


SKILL_NAME: Final = "lark-doc-exporter"
INSTALL_METADATA_FILENAME: Final = ".lark-doc-exporter-install.json"
HOST_SUFFIXES: Final = {
    "codex": Path(".agents") / "skills",
    "claude": Path(".claude") / "skills",
}


@dataclass(frozen=True)
class InstallTarget:
    host: str
    root: Path
    target_dir: Path
    create_parent: bool


@dataclass(frozen=True)
class PlannedInstall:
    host: str
    root: str
    target_dir: str
    action: str
    reason: str


def bundled_skill_dir():
    return files("lark_synced_export").joinpath("skill_assets", SKILL_NAME)


def bundled_skill_markdown() -> str:
    return bundled_skill_dir().joinpath("SKILL.md").read_text(encoding="utf-8")


def host_roots(home: Path | None = None) -> dict[str, Path]:
    base_home = home if home is not None else Path.home()
    return {name: base_home / suffix for name, suffix in HOST_SUFFIXES.items()}


def resolve_targets(host: str, home: Path | None = None) -> list[InstallTarget]:
    roots = host_roots(home)
    if host == "auto":
        targets = [
            InstallTarget(name, root, root / SKILL_NAME, False)
            for name, root in roots.items()
            if root.exists()
        ]
        if not targets:
            raise RuntimeError(
                "No supported host skill directory found under ~/.agents/skills or ~/.claude/skills. "
                "Re-run with --host codex, --host claude, or --host all for explicit setup."
            )
        return targets

    selected_hosts = ("codex", "claude") if host == "all" else (host,)
    return [
        InstallTarget(name, roots[name], roots[name] / SKILL_NAME, True)
        for name in selected_hosts
    ]


def read_install_metadata(target_dir: Path) -> dict | None:
    metadata_path = target_dir / INSTALL_METADATA_FILENAME
    if not metadata_path.is_file():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def is_managed_install(target_dir: Path) -> bool:
    metadata = read_install_metadata(target_dir)
    return bool(metadata and metadata.get("tool") == SKILL_NAME)


def plan_target(target: InstallTarget, force: bool) -> PlannedInstall:
    if not target.target_dir.exists():
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="install",
            reason="target directory does not exist",
        )

    if is_managed_install(target.target_dir):
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="upgrade",
            reason="managed install metadata found",
        )

    if force:
        return PlannedInstall(
            host=target.host,
            root=str(target.root),
            target_dir=str(target.target_dir),
            action="overwrite",
            reason="force requested for unmanaged target",
        )

    raise RuntimeError(
        f"Refusing to overwrite unmanaged skill directory: {target.target_dir}. "
        "Re-run with --force if you want to replace it."
    )


def write_install_metadata(stage_dir: Path, host: str) -> None:
    payload = {
        "tool": SKILL_NAME,
        "version": __version__,
        "installed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": host,
    }
    (stage_dir / INSTALL_METADATA_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def install_target(target: InstallTarget) -> None:
    if target.create_parent:
        target.root.mkdir(parents=True, exist_ok=True)

    staging_dir = target.root / f".{SKILL_NAME}.{target.host}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    with as_file(bundled_skill_dir()) as source_dir:
        shutil.copytree(source_dir, staging_dir)

    write_install_metadata(staging_dir, target.host)

    if target.target_dir.exists():
        shutil.rmtree(target.target_dir)

    staging_dir.replace(target.target_dir)


def run_skill_install(
    host: str = "auto",
    force: bool = False,
    dry_run: bool = False,
    home: Path | None = None,
) -> dict:
    targets = resolve_targets(host=host, home=home)
    planned = [plan_target(target, force=force) for target in targets]

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "targets": [asdict(item) for item in planned],
        }

    for target in targets:
        install_target(target)

    return {
        "ok": True,
        "dry_run": False,
        "targets": [asdict(item) for item in planned],
    }
