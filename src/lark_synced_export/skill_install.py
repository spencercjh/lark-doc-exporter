from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from importlib.resources import as_file, files
import json
import os
from pathlib import Path
from typing import Final

from kitup import (
    BaseOptions,
    InstallOptions,
    directory_bundle,
    install_bundled_skill,
    plan_bundled_skill,
)


SKILL_NAME: Final = "lark-doc-exporter"
KITUP_METADATA_FILENAME: Final = ".kitup.json"
LEGACY_METADATA_FILENAME: Final = ".lark-doc-exporter-install.json"
HOST_LABELS: Final = {
    "codex": "codex",
    "claude-code": "claude",
}


@dataclass(frozen=True)
class InstallTarget:
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
    return {
        "codex": base_home / ".agents" / "skills",
        "claude": base_home / ".claude" / "skills",
    }


def run_skill_install(
    host: str = "auto",
    force: bool = False,
    dry_run: bool = False,
    home: Path | None = None,
) -> dict:
    _validate_requested_roots(host, home=home)
    with (
        as_file(bundled_skill_dir()) as source_dir,
        as_file(files("lark_synced_export").joinpath("kitup_hosts.json")) as hosts_file,
    ):
        install_options = InstallOptions(
            base=BaseOptions(
                home=str(home) if home is not None else None,
                hosts_file=str(hosts_file),
            ),
            app_id=SKILL_NAME,
            skill_bundle=directory_bundle(str(source_dir)),
            scope="user",
            agents=_resolved_agents(host, home=home),
            force=force,
        )
        if dry_run:
            plan = plan_bundled_skill(install_options)
            legacy_targets = _legacy_dry_run_targets(
                plan,
                host,
                source_digest=_compute_target_bundle_digest(Path(source_dir)),
                home=home,
            )
            _raise_for_plan_conflicts(
                plan,
                ignored_target_dirs={item.target_dir for item in legacy_targets},
            )
            targets = [
                asdict(item)
                for item in _targets_from_plan(plan, extra_targets=legacy_targets)
            ]
            return {
                "ok": True,
                "dry_run": True,
                "targets": targets,
            }

        seeded_metadata = _seed_legacy_managed_metadata(host, home=home)
        keep_seeded_metadata = False
        try:
            plan = plan_bundled_skill(install_options)
            _raise_for_plan_conflicts(plan)
            targets = [asdict(item) for item in _targets_from_plan(plan)]

            report = install_bundled_skill(install_options)
            _raise_for_report_errors(report)
            keep_seeded_metadata = True
            return {
                "ok": True,
                "dry_run": False,
                "targets": targets,
            }
        finally:
            if dry_run or not keep_seeded_metadata:
                _cleanup_seeded_metadata(seeded_metadata)


def _resolved_agents(host: str, home: Path | None = None) -> str | list[str]:
    if host == "auto":
        roots = host_roots(home)
        detected = []
        if roots["codex"].exists():
            detected.append("codex")
        if roots["claude"].exists():
            detected.append("claude-code")
        return detected
    if host == "codex":
        return ["codex"]
    if host == "claude":
        return ["claude-code"]
    if host == "all":
        return ["codex", "claude-code"]
    raise RuntimeError(f"unsupported host selector: {host}")


def _validate_requested_roots(host: str, home: Path | None = None) -> None:
    roots = host_roots(home)
    if host == "auto":
        existing_hosts = []
        for name, root in roots.items():
            if root.exists():
                _validate_host_root(name, root)
                existing_hosts.append(name)
        if not existing_hosts:
            raise RuntimeError(
                "No supported host skill directory found under ~/.agents/skills or ~/.claude/skills. "
                "Re-run with --host codex, --host claude, or --host all for explicit setup."
            )
        return

    if host not in {"codex", "claude", "all"}:
        raise RuntimeError(f"unsupported host selector: {host}")

    selected_hosts = ("codex", "claude") if host == "all" else (host,)
    for name in selected_hosts:
        _validate_host_root(name, roots[name])


def _validate_host_root(host: str, root: Path) -> None:
    if (root.exists() or root.is_symlink()) and not root.is_dir():
        raise RuntimeError(
            f"Supported host skill root for {host} exists but is not a directory: {root}"
        )


def _targets_from_plan(
    plan, extra_targets: list[InstallTarget] | None = None
) -> list[InstallTarget]:
    targets: list[InstallTarget] = []
    for item in plan.installed:
        targets.append(_normalize_target(item, action="install", reason="missing"))
    for item in plan.updated:
        state = _existing_target_state(Path(item.target_dir))
        targets.append(
            _normalize_target(
                item,
                action="upgrade" if state == "managed" else "overwrite",
                reason=(
                    "managed install metadata found"
                    if state == "managed"
                    else "force requested for conflicting target"
                ),
            )
        )
    for item in plan.skipped:
        targets.append(_normalize_target(item, action="skip", reason=item.reason))
    if extra_targets:
        targets.extend(extra_targets)
    return sorted(targets, key=lambda item: (item.host, item.target_dir))


def _normalize_target(item, *, action: str, reason: str) -> InstallTarget:
    host_id = item.host_id if item.host_id is not None else (item.host_ids or [""])[0]
    target_dir = Path(item.target_dir)
    return InstallTarget(
        host=HOST_LABELS.get(host_id, host_id),
        root=str(target_dir.parent),
        target_dir=str(target_dir),
        action=action,
        reason=reason,
    )


def _existing_target_state(target_dir: Path) -> str:
    if not target_dir.exists():
        return "missing"
    metadata_path = target_dir / KITUP_METADATA_FILENAME
    if not metadata_path.is_file():
        return "unmanaged"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return "unmanaged"
    if not isinstance(payload, dict):
        return "unmanaged"
    if payload.get("appId") != SKILL_NAME:
        return "owner-mismatch"
    return "managed"


def _selected_target_dirs_by_host(
    host: str, home: Path | None = None
) -> list[tuple[str, Path]]:
    roots = host_roots(home)
    if host == "auto":
        return [
            (name, root / SKILL_NAME) for name, root in roots.items() if root.exists()
        ]
    if host == "codex":
        return [("codex", roots["codex"] / SKILL_NAME)]
    if host == "claude":
        return [("claude", roots["claude"] / SKILL_NAME)]
    if host == "all":
        return [
            ("codex", roots["codex"] / SKILL_NAME),
            ("claude", roots["claude"] / SKILL_NAME),
        ]
    raise RuntimeError(f"unsupported host selector: {host}")


def _selected_target_dirs(host: str, home: Path | None = None) -> list[Path]:
    return [
        target_dir for _, target_dir in _selected_target_dirs_by_host(host, home=home)
    ]


def _legacy_dry_run_targets(
    plan,
    host: str,
    *,
    source_digest: str,
    home: Path | None = None,
) -> list[InstallTarget]:
    selected_hosts = {
        str(target_dir): host_name
        for host_name, target_dir in _selected_target_dirs_by_host(host, home=home)
    }
    targets: list[InstallTarget] = []
    for item in plan.conflicts:
        host_name = selected_hosts.get(item.target_dir)
        if host_name is None:
            continue
        target_dir = Path(item.target_dir)
        if not _is_legacy_managed_target(target_dir):
            continue
        action = (
            "skip"
            if _compute_target_bundle_digest(target_dir) == source_digest
            else "upgrade"
        )
        reason = "unchanged" if action == "skip" else "managed install metadata found"
        targets.append(
            InstallTarget(
                host=host_name,
                root=str(target_dir.parent),
                target_dir=str(target_dir),
                action=action,
                reason=reason,
            )
        )
    return targets


def _is_legacy_managed_target(target_dir: Path) -> bool:
    if (target_dir / KITUP_METADATA_FILENAME).exists():
        return False
    legacy_metadata = _read_legacy_install_metadata(target_dir)
    return legacy_metadata.get("tool") == SKILL_NAME


def _seed_legacy_managed_metadata(host: str, home: Path | None = None) -> list[Path]:
    seeded: list[Path] = []
    for target_dir in _selected_target_dirs(host, home=home):
        if not target_dir.exists():
            continue
        metadata_path = target_dir / KITUP_METADATA_FILENAME
        if metadata_path.exists():
            continue
        legacy_metadata = _read_legacy_install_metadata(target_dir)
        if legacy_metadata.get("tool") != SKILL_NAME:
            continue

        payload = {
            "schemaVersion": 1,
            "appId": SKILL_NAME,
            "skillName": SKILL_NAME,
            "source": "bundled",
            "hash": _compute_target_bundle_digest(target_dir),
        }
        metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        seeded.append(metadata_path)
    return seeded


def _cleanup_seeded_metadata(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _read_legacy_install_metadata(target_dir: Path) -> dict:
    metadata_path = target_dir / LEGACY_METADATA_FILENAME
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _compute_target_bundle_digest(target_dir: Path) -> str:
    digest = hashlib.sha256()
    for current_root, dirnames, filenames in os.walk(target_dir):
        dirnames[:] = sorted(name for name in dirnames if not _skip_metadata_name(name))
        for filename in sorted(filenames):
            if _skip_metadata_name(filename):
                continue
            source = Path(current_root) / filename
            relative = source.relative_to(target_dir).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(source.read_bytes())
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _skip_metadata_name(name: str) -> bool:
    return (
        name in {".git", ".DS_Store", KITUP_METADATA_FILENAME, LEGACY_METADATA_FILENAME}
        or name.endswith(".swp")
        or name.endswith("~")
    )


def _raise_for_plan_conflicts(
    plan, ignored_target_dirs: set[str] | None = None
) -> None:
    if plan.errors:
        raise RuntimeError("; ".join(error.reason for error in plan.errors))
    conflicts = [
        item
        for item in plan.conflicts
        if ignored_target_dirs is None or item.target_dir not in ignored_target_dirs
    ]
    if not conflicts:
        return
    conflict = conflicts[0]
    raise RuntimeError(
        f"Refusing to overwrite conflicting skill directory: {conflict.target_dir}. "
        "Re-run with --force if you want to replace it."
    )


def _raise_for_report_errors(report) -> None:
    if report.errors:
        raise RuntimeError("; ".join(error.reason for error in report.errors))
    if report.conflicts:
        conflict = report.conflicts[0]
        raise RuntimeError(
            f"Refusing to overwrite conflicting skill directory: {conflict.target_dir}. "
            "Re-run with --force if you want to replace it."
        )
