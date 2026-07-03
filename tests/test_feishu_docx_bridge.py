from __future__ import annotations

import json
from pathlib import Path

import pytest

from lark_synced_export.feishu_docx_bridge import (
    FEISHU_DOCX_CONFIG_PATH,
    MARKDOWN_PROVIDER_ENV,
    FeishuDocxCredentials,
    normalize_feishu_docx_assets,
    resolve_markdown_provider,
)


def test_resolve_markdown_provider_auto_uses_env_credentials(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_secret")
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )

    selection = resolve_markdown_provider("https://example.feishu.cn/docx/abc123")

    assert selection.provider == "feishu-docx"
    assert selection.detail == "auto:selected from env"
    assert selection.credentials == FeishuDocxCredentials(
        app_id="cli_app",
        app_secret="cli_secret",
        auth_mode="tenant",
        is_lark=False,
        source="env",
    )


def test_resolve_markdown_provider_auto_falls_back_when_credentials_missing(
    monkeypatch,
):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        Path("/definitely/missing/config.json"),
    )

    selection = resolve_markdown_provider("https://example.feishu.cn/docx/abc123")

    assert selection.provider == "legacy"
    assert selection.detail.startswith("auto:fallback to legacy")
    assert selection.credentials is None


def test_resolve_markdown_provider_forced_feishu_docx_requires_credentials(
    monkeypatch,
):
    monkeypatch.setenv(MARKDOWN_PROVIDER_ENV, "feishu-docx")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        Path("/definitely/missing/config.json"),
    )

    with pytest.raises(RuntimeError, match="requires FEISHU_APP_ID/FEISHU_APP_SECRET"):
        resolve_markdown_provider("https://example.feishu.cn/docx/abc123")


def test_resolve_markdown_provider_reads_config_file(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_id": "cfg_app",
                "app_secret": "cfg_secret",
                "auth_mode": "oauth",
                "is_lark": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )

    selection = resolve_markdown_provider("https://example.larksuite.com/docx/abc123")

    assert selection.provider == "feishu-docx"
    assert selection.detail == "auto:selected from config"
    assert selection.credentials == FeishuDocxCredentials(
        app_id="cfg_app",
        app_secret="cfg_secret",
        auth_mode="oauth",
        is_lark=True,
        source="config",
    )


def test_resolve_markdown_provider_auto_falls_back_for_token_only_doc_ref(
    monkeypatch,
):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_secret")
    monkeypatch.delenv(MARKDOWN_PROVIDER_ENV, raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.import_feishu_docx_exporter",
        lambda: object(),
    )

    selection = resolve_markdown_provider("IkCedJjFIoypyzxwXjacRSy9nBg")

    assert selection.provider == "legacy"
    assert "requires URL-shaped doc ref" in selection.detail


def test_normalize_feishu_docx_assets_moves_links_into_images(tmp_path: Path):
    raw_markdown = tmp_path / "demo.md"
    raw_markdown.write_text(
        "![image](demo/pic.png)\n\n📎 [report.pdf](demo/report.pdf)\n",
        encoding="utf-8",
    )
    raw_assets = tmp_path / "demo"
    raw_assets.mkdir()
    (raw_assets / "pic.png").write_bytes(b"png")
    (raw_assets / "report.pdf").write_bytes(b"pdf")
    final_markdown = tmp_path / "final.md"
    final_assets = tmp_path / "images"

    localized_count = normalize_feishu_docx_assets(
        markdown_path=raw_markdown,
        raw_assets_dir=raw_assets,
        localized_path=final_markdown,
        target_assets_dir=final_assets,
    )

    assert localized_count == 1
    assert final_markdown.read_text(encoding="utf-8") == (
        "![image](images/pic.png)\n\n📎 [report.pdf](images/report.pdf)\n"
    )
    assert (final_assets / "pic.png").read_bytes() == b"png"
    assert (final_assets / "report.pdf").read_bytes() == b"pdf"


def test_module_exports_default_config_path():
    assert FEISHU_DOCX_CONFIG_PATH.name == "config.json"
