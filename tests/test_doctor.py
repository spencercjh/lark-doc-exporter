import json
import subprocess

from lark_synced_export.cli import run_main
from lark_synced_export.doctor import (
    DoctorCheck,
    check_lark_cli,
    check_pdf_runtime,
    run_doctor,
)


def test_run_main_doctor_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "lark_synced_export.cli.run_doctor",
        lambda: {
            "ok": True,
            "checks": [{"name": "lark-cli", "ok": True, "detail": "ok"}],
        },
    )

    assert run_main(["doctor"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "lark-cli"


def test_check_lark_cli_reports_missing_binary(monkeypatch):
    monkeypatch.setattr("lark_synced_export.doctor.shutil.which", lambda _name: None)

    result = check_lark_cli()

    assert result.ok is False
    assert "lark-cli" in result.detail


def test_check_lark_cli_probes_help_with_timeout(monkeypatch):
    calls: dict = {}

    monkeypatch.setattr(
        "lark_synced_export.doctor.shutil.which", lambda _name: "/usr/bin/lark-cli"
    )

    def fake_run(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    monkeypatch.setattr("lark_synced_export.doctor.subprocess.run", fake_run)

    result = check_lark_cli()

    assert result.ok is True
    assert calls["args"] == (["/usr/bin/lark-cli", "--help"],)
    assert calls["kwargs"]["capture_output"] is True
    assert calls["kwargs"]["text"] is True
    assert calls["kwargs"]["check"] is True
    assert calls["kwargs"]["timeout"] == 10


def test_run_doctor_keeps_chromium_check_but_only_requires_lark_cli(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_lark_cli",
        lambda: DoctorCheck(name="lark-cli", ok=True, detail="ok", required=True),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_pdf_runtime",
        lambda: DoctorCheck(
            name="chromium", ok=False, detail="missing", required=False
        ),
    )

    payload = run_doctor()

    assert payload["ok"] is True
    assert payload["checks"] == [
        {"name": "lark-cli", "ok": True, "detail": "ok", "required": True},
        {"name": "chromium", "ok": False, "detail": "missing", "required": False},
    ]


def test_run_doctor_fails_when_required_lark_cli_check_fails(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_lark_cli",
        lambda: DoctorCheck(
            name="lark-cli", ok=False, detail="missing", required=True
        ),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_pdf_runtime",
        lambda: DoctorCheck(name="chromium", ok=True, detail="ok", required=False),
    )

    payload = run_doctor()

    assert payload["ok"] is False


def test_check_pdf_runtime_is_optional_and_mentions_native_mode(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_chromium_ready",
        lambda: (False, "Chromium is not ready. Install it."),
    )

    result = check_pdf_runtime()

    assert result.ok is False
    assert result.required is False
    assert "rendered PDF output" in result.detail
    assert "Native PDF does not require Chromium" in result.detail
