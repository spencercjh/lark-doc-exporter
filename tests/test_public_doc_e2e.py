from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import fitz
import pytest

import public_doc_e2e_case as case
from lark_synced_export.cli import run_main
from public_doc_e2e_case import FeaturePoint


SNAPSHOT_ROOT = Path(__file__).with_name("e2e_snapshots") / "public_doc"


def test_build_stable_result_filters_runtime_fields():
    payload = {
        "ok": True,
        "expanded_references": 2,
        "pdf_mode": "native",
        "pdf_renderer": "feishu-native",
        "localized_images": 2,
        "temp_doc_token": "tmp-token",
        "outputs": {"markdown": "/tmp/demo.md", "pdf": "/tmp/demo.pdf"},
        "ai_footer_postprocess": {"status": "not_found", "warning": None},
    }

    assert build_stable_result(payload) == {
        "ok": True,
        "expanded_references": 2,
        "pdf_mode": "native",
        "pdf_renderer": "feishu-native",
        "localized_images": 2,
        "ai_footer_postprocess.status": "not_found",
    }


def test_normalize_pdf_text_collapses_whitespace():
    assert normalize_pdf_text("A\u200b  \n\nB\t\tC\ufeff\n") == "A B C"


def test_assert_feature_point_reports_named_failure(tmp_path: Path):
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "markdown").mkdir(parents=True)
    (snapshot_root / "markdown" / "table.md").write_text(
        "公开 E2E 表格单元格 A", encoding="utf-8"
    )

    feature = FeaturePoint(
        name="markdown_table",
        markdown_contains_snapshot="markdown/table.md",
    )

    with pytest.raises(
        AssertionError, match="feature markdown_table: markdown snapshot missing"
    ):
        assert_feature_point(feature, "other text", "other pdf", snapshot_root)


def test_is_lark_cli_user_ready_accepts_needs_refresh(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/lark-cli")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["lark-cli", "auth", "status", "--json"],
            returncode=0,
            stdout=json.dumps(
                {
                    "identities": {
                        "user": {
                            "available": True,
                            "status": "needs_refresh",
                            "message": "User identity: needs refresh",
                        }
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert is_lark_cli_user_ready() == (True, "User identity: needs refresh")


def test_is_lark_cli_user_ready_rejects_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    ok, detail = is_lark_cli_user_ready()

    assert ok is False
    assert "not on PATH" in detail


def build_stable_result(payload: dict[str, object]) -> dict[str, object]:
    ai_footer = payload.get("ai_footer_postprocess") or {}
    return {
        "ok": payload.get("ok"),
        "expanded_references": payload.get("expanded_references"),
        "pdf_mode": payload.get("pdf_mode"),
        "pdf_renderer": payload.get("pdf_renderer"),
        "localized_images": payload.get("localized_images"),
        "ai_footer_postprocess.status": ai_footer.get("status"),
    }


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def load_snapshot(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def assert_feature_point(
    feature: FeaturePoint,
    markdown_text: str,
    pdf_text: str,
    pdf_total_images: int,
    snapshot_root: Path = SNAPSHOT_ROOT,
) -> None:
    if feature.markdown_contains_snapshot:
        expected_markdown = load_snapshot(
            snapshot_root / feature.markdown_contains_snapshot
        )
        assert expected_markdown in markdown_text, (
            f"feature {feature.name}: markdown snapshot missing"
        )

    if feature.pdf_text_contains_snapshot:
        expected_pdf = normalize_pdf_text(
            load_snapshot(snapshot_root / feature.pdf_text_contains_snapshot)
        )
        assert expected_pdf in pdf_text, (
            f"feature {feature.name}: pdf text snapshot missing"
        )

    if feature.pdf_total_images_at_least is not None:
        assert pdf_total_images >= feature.pdf_total_images_at_least, (
            f"feature {feature.name}: expected at least "
            f"{feature.pdf_total_images_at_least} pdf images, got {pdf_total_images}"
        )

    for forbidden in feature.markdown_forbid:
        assert forbidden not in markdown_text, (
            f"feature {feature.name}: forbidden marker {forbidden!r} still present in markdown"
        )

    for forbidden in feature.pdf_forbid:
        assert forbidden not in pdf_text, (
            f"feature {feature.name}: forbidden marker {forbidden!r} found in extracted pdf text"
        )


def is_lark_cli_user_ready() -> tuple[bool, str]:
    binary = shutil.which("lark-cli")
    if not binary:
        return False, "`lark-cli` is not on PATH"

    proc = subprocess.run(
        ["lark-cli", "auth", "status", "--json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "`lark-cli auth status` failed"

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, "invalid JSON from `lark-cli auth status --json`"

    user = payload.get("identities", {}).get("user", {})
    if not user.get("available"):
        return False, user.get("message", "User identity unavailable")
    return True, user.get("message", "User identity ready")


def extract_pdf_text(pdf_path: Path) -> str:
    document = fitz.open(pdf_path)
    try:
        return normalize_pdf_text("\n".join(page.get_text("text") for page in document))
    finally:
        document.close()


def extract_pdf_total_images(pdf_path: Path) -> int:
    document = fitz.open(pdf_path)
    try:
        return sum(len(page.get_images(full=True)) for page in document)
    finally:
        document.close()


@pytest.mark.e2e_public_doc
def test_public_doc_export_e2e(tmp_path: Path, capsys):
    if case.DOC_REF is None:
        pytest.skip("public doc fixture not configured")

    auth_ready, auth_detail = is_lark_cli_user_ready()
    if not auth_ready:
        pytest.skip(
            f"lark-cli user session not configured for public doc e2e: {auth_detail}"
        )

    output_dir = tmp_path / case.FILE_STEM
    exit_code = run_main(
        [
            "--doc",
            case.DOC_REF,
            "--output-dir",
            str(output_dir),
            "--formats",
            ",".join(case.EXPORT_ARGS["formats"]),
            "--pdf-mode",
            case.EXPORT_ARGS["pdf_mode"],
            "--file-stem",
            case.EXPORT_ARGS["file_stem"],
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    expected_result = json.loads(
        (SNAPSHOT_ROOT / "result.json").read_text(encoding="utf-8")
    )
    assert build_stable_result(payload) == expected_result

    markdown_path = Path(payload["outputs"]["markdown"])
    pdf_path = Path(payload["outputs"]["pdf"])
    assert markdown_path.is_file()
    assert pdf_path.is_file()

    markdown_text = markdown_path.read_text(encoding="utf-8")
    pdf_text = extract_pdf_text(pdf_path)
    pdf_total_images = extract_pdf_total_images(pdf_path)

    if "localized_images" in expected_result:
        images_dir = output_dir / "images"
        assert images_dir.is_dir()
        assert len(sorted(images_dir.iterdir())) == expected_result["localized_images"]

    for feature in case.FEATURE_POINTS:
        assert_feature_point(feature, markdown_text, pdf_text, pdf_total_images)
