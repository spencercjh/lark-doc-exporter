from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MARKDOWN_PROVIDER_ENV = "LARK_DOC_EXPORTER_MARKDOWN_PROVIDER"
FEISHU_DOCX_CONFIG_PATH = Path.home() / ".feishu-docx" / "config.json"
SUPPORTED_PROVIDER_MODES = {"auto", "feishu-docx", "legacy"}
URL_DOC_REF_RE = re.compile(
    r"^https?://.+/(?:doc|docx|wiki|sheet|sheets|base)/[A-Za-z0-9]+"
)
IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class FeishuDocxCredentials:
    app_id: str
    app_secret: str
    auth_mode: str
    is_lark: bool
    source: str


@dataclass(frozen=True)
class MarkdownProviderSelection:
    provider: str
    detail: str
    credentials: FeishuDocxCredentials | None = None


def import_feishu_docx_exporter():
    from feishu_docx.core.exporter import FeishuExporter

    return FeishuExporter


def _parse_bool_env(raw: str | None) -> bool:
    if not raw:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _infer_is_lark(doc_ref: str) -> bool:
    host = urlparse(doc_ref).netloc.lower()
    return "larksuite" in host or "larkoffice" in host


def _normalize_auth_mode(raw: str | None) -> str:
    mode = (raw or "tenant").strip().lower()
    return mode if mode in {"tenant", "oauth"} else "tenant"


def is_feishu_docx_compatible_doc_ref(doc_ref: str) -> bool:
    return bool(URL_DOC_REF_RE.match(doc_ref.strip()))


def discover_feishu_docx_credentials(doc_ref: str) -> FeishuDocxCredentials | None:
    env_app_id = os.getenv("FEISHU_APP_ID")
    env_app_secret = os.getenv("FEISHU_APP_SECRET")
    if env_app_id and env_app_secret:
        return FeishuDocxCredentials(
            app_id=env_app_id,
            app_secret=env_app_secret,
            auth_mode=_normalize_auth_mode(os.getenv("FEISHU_AUTH_MODE")),
            is_lark=_parse_bool_env(os.getenv("FEISHU_IS_LARK"))
            or _infer_is_lark(doc_ref),
            source="env",
        )

    if not FEISHU_DOCX_CONFIG_PATH.is_file():
        return None

    try:
        payload = json.loads(FEISHU_DOCX_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    app_id = payload.get("app_id")
    app_secret = payload.get("app_secret")
    if not app_id or not app_secret:
        return None

    return FeishuDocxCredentials(
        app_id=app_id,
        app_secret=app_secret,
        auth_mode=_normalize_auth_mode(payload.get("auth_mode")),
        is_lark=bool(payload.get("is_lark", False)) or _infer_is_lark(doc_ref),
        source="config",
    )


def _resolve_mode() -> str:
    mode = (os.getenv(MARKDOWN_PROVIDER_ENV) or "auto").strip().lower()
    if mode not in SUPPORTED_PROVIDER_MODES:
        raise ValueError(
            f"{MARKDOWN_PROVIDER_ENV} must be one of "
            f"{', '.join(sorted(SUPPORTED_PROVIDER_MODES))}; got {mode!r}"
        )
    return mode


def resolve_markdown_provider(doc_ref: str) -> MarkdownProviderSelection:
    mode = _resolve_mode()
    if mode == "legacy":
        return MarkdownProviderSelection(provider="legacy", detail="forced:legacy")

    if not is_feishu_docx_compatible_doc_ref(doc_ref):
        detail = "requires URL-shaped doc ref; falling back to legacy"
        if mode == "feishu-docx":
            raise RuntimeError(f"feishu-docx provider {detail}")
        return MarkdownProviderSelection(
            provider="legacy",
            detail=f"auto:fallback to legacy ({detail})",
        )

    try:
        import_feishu_docx_exporter()
    except ImportError as exc:
        if mode == "feishu-docx":
            raise RuntimeError(
                "feishu-docx provider requires the feishu-docx package"
            ) from exc
        return MarkdownProviderSelection(
            provider="legacy",
            detail="auto:fallback to legacy (feishu-docx package unavailable)",
        )

    credentials = discover_feishu_docx_credentials(doc_ref)
    if credentials is None:
        if mode == "feishu-docx":
            raise RuntimeError(
                "feishu-docx provider requires FEISHU_APP_ID/FEISHU_APP_SECRET "
                "or ~/.feishu-docx/config.json"
            )
        return MarkdownProviderSelection(
            provider="legacy",
            detail=(
                "auto:fallback to legacy "
                "(missing FEISHU_APP_ID/FEISHU_APP_SECRET)"
            ),
        )

    source_detail = "env" if credentials.source == "env" else "config"
    return MarkdownProviderSelection(
        provider="feishu-docx",
        detail=f"auto:selected from {source_detail}",
        credentials=credentials,
    )


def export_markdown_with_feishu_docx(
    doc_ref: str,
    stage_dir: Path,
    file_stem: str | None,
    credentials: FeishuDocxCredentials,
) -> tuple[Path, Path | None]:
    FeishuExporter = import_feishu_docx_exporter()
    exporter = FeishuExporter(
        app_id=credentials.app_id,
        app_secret=credentials.app_secret,
        is_lark=credentials.is_lark,
        auth_mode=credentials.auth_mode,
    )
    markdown_path = Path(
        exporter.export(
            url=doc_ref,
            output_dir=stage_dir,
            filename=file_stem,
            silent=True,
        )
    )
    raw_assets_dir = stage_dir / markdown_path.stem
    return markdown_path, raw_assets_dir if raw_assets_dir.is_dir() else None


def _count_localized_images(markdown_text: str) -> int:
    count = 0
    for match in IMAGE_LINK_RE.finditer(markdown_text):
        target = match.group(1).strip()
        if target.startswith("images/") or target.startswith("<images/"):
            count += 1
    return count


def normalize_feishu_docx_assets(
    markdown_path: Path,
    raw_assets_dir: Path | None,
    localized_path: Path,
    target_assets_dir: Path,
) -> int:
    text = markdown_path.read_text(encoding="utf-8")
    localized_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_assets_dir and raw_assets_dir.is_dir():
        target_assets_dir.mkdir(parents=True, exist_ok=True)
        for child in raw_assets_dir.iterdir():
            if child.is_file():
                shutil.copy2(child, target_assets_dir / child.name)
        text = text.replace(f"]({raw_assets_dir.name}/", "](images/")
        text = text.replace(f"](<{raw_assets_dir.name}/", "](<images/")

    localized_path.write_text(text, encoding="utf-8")
    return _count_localized_images(text)
