from __future__ import annotations

from dataclasses import asdict, dataclass
import shutil
import subprocess

from .pdf_runtime import check_chromium_ready


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


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


def check_pdf_runtime() -> DoctorCheck:
    ok, detail = check_chromium_ready()
    return DoctorCheck(name="chromium", ok=ok, detail=detail)


def run_doctor() -> dict:
    checks = [check_lark_cli(), check_pdf_runtime()]
    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
    }
