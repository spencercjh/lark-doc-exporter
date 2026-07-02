from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.resources import as_file, files
import json
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
        plan = plan_bundled_skill(install_options)
        _raise_for_plan_conflicts(plan)
        targets = [asdict(item) for item in _targets_from_plan(plan)]

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "targets": targets,
            }

        report = install_bundled_skill(install_options)
        _raise_for_report_errors(report)
        return {
            "ok": True,
            "dry_run": False,
            "targets": targets,
        }


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

    selected_hosts = ("codex", "claude") if host == "all" else (host,)
    for name in selected_hosts:
        _validate_host_root(name, roots[name])


def _validate_host_root(host: str, root: Path) -> None:
    if (root.exists() or root.is_symlink()) and not root.is_dir():
        raise RuntimeError(
            f"Supported host skill root for {host} exists but is not a directory: {root}"
        )


def _targets_from_plan(plan) -> list[InstallTarget]:
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


def _raise_for_plan_conflicts(plan) -> None:
    if plan.errors:
        raise RuntimeError("; ".join(error.reason for error in plan.errors))
    if not plan.conflicts:
        return
    conflict = plan.conflicts[0]
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
            f"Refusing to overwrite conflicting skill directory: {conflict.target_dir}."
        )
