from __future__ import annotations

from dataclasses import asdict, dataclass
import shutil
import subprocess

from .feishu_docx_bridge import (
    require_feishu_docx_credentials,
    require_feishu_docx_exporter,
    validate_markdown_doc_ref,
)


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True


def check_lark_cli() -> DoctorCheck:
    binary = shutil.which("lark-cli")
    if not binary:
        return DoctorCheck(
            name="lark-cli",
            ok=False,
            detail="`lark-cli` is not on PATH. Install/configure it before running exports.",
        )

    try:
        subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return DoctorCheck(
            name="lark-cli",
            ok=False,
            detail=f"`lark-cli` was found but is not runnable: {exc}",
        )

    return DoctorCheck(
        name="lark-cli", ok=True, detail=f"`lark-cli` is available at {binary}."
    )


def check_feishu_docx_markdown() -> DoctorCheck:
    try:
        validate_markdown_doc_ref("https://example.feishu.cn/docx/placeholder")
        require_feishu_docx_exporter()
        credentials = require_feishu_docx_credentials(
            "https://example.feishu.cn/docx/placeholder"
        )
    except Exception as exc:
        return DoctorCheck(
            name="feishu-docx-markdown",
            ok=False,
            detail=str(exc),
            required=False,
        )

    return DoctorCheck(
        name="feishu-docx-markdown",
        ok=True,
        detail=f"feishu-docx markdown is ready ({credentials.source}).",
        required=False,
    )


def run_doctor() -> dict:
    checks = [check_lark_cli(), check_feishu_docx_markdown()]
    return {
        "ok": all(check.ok for check in checks if check.required),
        "checks": [asdict(check) for check in checks],
    }
