from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.resources import as_file, files
import json
from pathlib import Path
import shutil
import tempfile
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


def validate_host_root(host: str, root: Path) -> None:
    if root.exists() and not root.is_dir():
        raise RuntimeError(
            f"Supported host skill root for {host} exists but is not a directory: {root}"
        )


def resolve_targets(host: str, home: Path | None = None) -> list[InstallTarget]:
    roots = host_roots(home)
    if host == "auto":
        for name, root in roots.items():
            if root.exists():
                validate_host_root(name, root)
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
    for name in selected_hosts:
        validate_host_root(name, roots[name])
    return [
        InstallTarget(name, roots[name], roots[name] / SKILL_NAME, True)
        for name in selected_hosts
    ]


def read_install_metadata(target_dir: Path) -> dict | None:
    metadata_path = target_dir / INSTALL_METADATA_FILENAME
    if not metadata_path.is_file():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


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


def replace_path(source: Path, destination: Path) -> None:
    source.replace(destination)


def install_target(target: InstallTarget) -> None:
    if target.create_parent:
        target.root.mkdir(parents=True, exist_ok=True)

    temp_root = Path(
        tempfile.mkdtemp(prefix=f".{SKILL_NAME}.{target.host}.", dir=target.root)
    )
    staging_dir = temp_root / SKILL_NAME
    backup_dir = temp_root / "backup"
    keep_temp_root = False

    try:
        with as_file(bundled_skill_dir()) as source_dir:
            shutil.copytree(source_dir, staging_dir)

        write_install_metadata(staging_dir, target.host)

        if not target.target_dir.exists():
            replace_path(staging_dir, target.target_dir)
            return

        replace_path(target.target_dir, backup_dir)
        try:
            replace_path(staging_dir, target.target_dir)
        except Exception:
            keep_temp_root = True
            try:
                replace_path(backup_dir, target.target_dir)
            except Exception as restore_error:
                raise RuntimeError(
                    "Failed to replace the installed skill directory and failed to "
                    f"restore the previous install. Recover from {backup_dir} manually."
                ) from restore_error
            keep_temp_root = False
            raise
    finally:
        if not keep_temp_root:
            shutil.rmtree(temp_root, ignore_errors=True)


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
