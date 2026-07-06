from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from lark_synced_export.feishu_docx_bridge import (
    FEISHU_DOCX_CONFIG_PATH,
    FeishuDocxCredentials,
    normalize_feishu_docx_assets,
    require_feishu_docx_credentials,
    require_feishu_docx_exporter,
    validate_markdown_doc_ref,
)


def test_validate_markdown_doc_ref_accepts_url_shaped_ref():
    validate_markdown_doc_ref("https://example.feishu.cn/docx/abc123")


def test_validate_markdown_doc_ref_rejects_token_only_ref():
    with pytest.raises(RuntimeError, match="full document URL"):
        validate_markdown_doc_ref("IkCedJjFIoypyzxwXjacRSy9nBg")


def test_require_feishu_docx_exporter_returns_imported_exporter(monkeypatch):
    fake_exporter = type("FakeExporter", (), {})
    exporter_module = types.ModuleType("feishu_docx.core.exporter")
    exporter_module.FeishuExporter = fake_exporter
    core_module = types.ModuleType("feishu_docx.core")
    package_module = types.ModuleType("feishu_docx")
    core_module.exporter = exporter_module
    package_module.core = core_module
    monkeypatch.setitem(sys.modules, "feishu_docx", package_module)
    monkeypatch.setitem(sys.modules, "feishu_docx.core", core_module)
    monkeypatch.setitem(sys.modules, "feishu_docx.core.exporter", exporter_module)

    assert require_feishu_docx_exporter() is fake_exporter


def test_require_feishu_docx_exporter_raises_when_package_missing(monkeypatch):
    monkeypatch.delitem(sys.modules, "feishu_docx.core.exporter", raising=False)
    monkeypatch.delitem(sys.modules, "feishu_docx.core", raising=False)
    monkeypatch.delitem(sys.modules, "feishu_docx", raising=False)

    def fake_import(name, *args, **kwargs):
        if name == "feishu_docx.core.exporter":
            raise ImportError("missing feishu_docx")
        return __import__(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="requires the feishu-docx package"):
        require_feishu_docx_exporter()


def test_require_feishu_docx_credentials_uses_env(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_secret")

    credentials = require_feishu_docx_credentials(
        "https://example.feishu.cn/docx/abc123"
    )

    assert credentials == FeishuDocxCredentials(
        app_id="cli_app",
        app_secret="cli_secret",
        auth_mode="tenant",
        is_lark=False,
        source="env",
    )


def test_require_feishu_docx_credentials_reads_config_file(monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        config_path,
    )

    credentials = require_feishu_docx_credentials(
        "https://example.larksuite.com/docx/abc123"
    )

    assert credentials == FeishuDocxCredentials(
        app_id="cfg_app",
        app_secret="cfg_secret",
        auth_mode="oauth",
        is_lark=True,
        source="config",
    )


def test_require_feishu_docx_credentials_raises_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        Path("/definitely/missing/config.json"),
    )

    with pytest.raises(RuntimeError, match="requires FEISHU_APP_ID/FEISHU_APP_SECRET"):
        require_feishu_docx_credentials("https://example.feishu.cn/docx/abc123")


def test_require_feishu_docx_credentials_treats_unreadable_config_as_missing(
    monkeypatch, tmp_path: Path
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"app_id": "cfg_app", "app_secret": "cfg_secret"}),
        encoding="utf-8",
    )
    real_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self == config_path:
            raise PermissionError("denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.feishu_docx_bridge.FEISHU_DOCX_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(RuntimeError, match="requires FEISHU_APP_ID/FEISHU_APP_SECRET"):
        require_feishu_docx_credentials("https://example.feishu.cn/docx/abc123")


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
