import json
from pathlib import Path

import pytest

from lark_synced_export.cli import run_main


def test_run_main_rejects_rendered_pdf_mode(capsys, tmp_path: Path):
    with pytest.raises(SystemExit) as excinfo:
        run_main(
            [
                "--doc",
                "https://example.feishu.cn/docx/abc123",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--pdf-mode",
                "rendered",
            ]
        )

    assert excinfo.value.code == 2
    assert "invalid choice: 'rendered'" in capsys.readouterr().err


def test_run_main_defaults_pdf_mode_to_native(monkeypatch, tmp_path: Path):
    calls: dict[str, object] = {}

    def fake_export_document(**kwargs):
        calls.update(kwargs)
        return {
            "ok": True,
            "doc": kwargs["doc_ref"],
            "pdf_mode": kwargs["pdf_mode"],
            "warnings": [],
            "outputs": {"pdf": str(tmp_path / "demo.pdf")},
        }

    monkeypatch.setattr("lark_synced_export.cli.export_document", fake_export_document)

    exit_code = run_main(
        [
            "--doc",
            "https://example.feishu.cn/docx/abc123",
            "--output-dir",
            str(tmp_path),
            "--formats",
            "pdf",
        ]
    )

    assert exit_code == 0
    assert calls["pdf_mode"] == "native"


def test_run_main_rejects_theme_arg_as_unknown(capsys, tmp_path: Path):
    with pytest.raises(SystemExit) as excinfo:
        run_main(
            [
                "--doc",
                "https://example.feishu.cn/docx/abc123",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--theme",
                "company",
            ]
        )

    assert excinfo.value.code == 2
    assert "unrecognized arguments: --theme company" in capsys.readouterr().err


def test_run_main_rejects_css_arg_as_unknown(capsys, tmp_path: Path):
    css_path = tmp_path / "custom.css"
    css_path.write_text("body { color: red; }\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        run_main(
            [
                "--doc",
                "https://example.feishu.cn/docx/abc123",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--css",
                str(css_path),
            ]
        )

    assert excinfo.value.code == 2
    assert f"unrecognized arguments: --css {css_path}" in capsys.readouterr().err


def test_run_main_returns_one_and_prints_json_for_controlled_native_failure(
    monkeypatch, capsys, tmp_path: Path
):
    monkeypatch.setattr(
        "lark_synced_export.cli.export_document",
        lambda **kwargs: {
            "ok": False,
            "doc": "demo",
            "pdf_mode": "native",
            "warnings": [
                "native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at /tmp/demo.native-raw.pdf"
            ],
            "ai_footer_postprocess": {
                "status": "unsafe_geometry",
                "raw_pdf_path": "/tmp/demo.native-raw.pdf",
                "warning": "native PDF footer post-process failed (unsafe_geometry); raw native PDF kept at /tmp/demo.native-raw.pdf",
            },
            "outputs": {"markdown": str(tmp_path / "demo.md")},
        },
    )

    exit_code = run_main(
        [
            "--doc",
            "https://example.feishu.cn/docx/abc123",
            "--output-dir",
            str(tmp_path),
            "--formats",
            "markdown,pdf",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["ai_footer_postprocess"]["status"] == "unsafe_geometry"
    assert payload["warnings"][0].startswith("native PDF footer post-process failed")
    assert "native PDF footer post-process failed" in captured.err


def test_run_main_help_mentions_native_only_contract(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_main(["--help"])

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "Only native Feishu PDF is supported." in captured.out
    assert "--theme" not in captured.out
    assert "--css" not in captured.out
    assert "rendered" not in captured.out
    assert "LARK_DOC_EXPORTER_MARKDOWN_PROVIDER" not in captured.out
