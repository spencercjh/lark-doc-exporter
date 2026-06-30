import json
from pathlib import Path

import pytest

from lark_synced_export.cli import run_main


def test_run_main_rejects_custom_theme_in_native_pdf_mode(tmp_path: Path):
    with pytest.raises(
        SystemExit,
        match="--pdf-mode native does not support explicit --theme or --css",
    ):
        run_main(
            [
                "--doc",
                "demo",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "pdf",
                "--pdf-mode",
                "native",
                "--theme",
                "company",
            ]
        )


def test_run_main_rejects_custom_theme_in_native_pdf_mode_for_markdown_only(
    tmp_path: Path,
):
    with pytest.raises(
        SystemExit,
        match="--pdf-mode native does not support explicit --theme or --css",
    ):
        run_main(
            [
                "--doc",
                "demo",
                "--output-dir",
                str(tmp_path),
                "--formats",
                "markdown",
                "--pdf-mode",
                "native",
                "--theme",
                "company",
            ]
        )


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
            "demo",
            "--output-dir",
            str(tmp_path),
            "--formats",
            "markdown,pdf",
            "--pdf-mode",
            "native",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["ai_footer_postprocess"]["status"] == "unsafe_geometry"
    assert payload["warnings"][0].startswith("native PDF footer post-process failed")
    assert "native PDF footer post-process failed" in captured.err
