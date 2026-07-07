import json
import subprocess

from lark_synced_export.cli import run_main
from lark_synced_export.doctor import (
    DoctorCheck,
    check_feishu_docx_markdown,
    check_lark_cli,
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


def test_run_doctor_reports_only_two_checks(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_lark_cli",
        lambda: DoctorCheck(name="lark-cli", ok=True, detail="ok", required=True),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_feishu_docx_markdown",
        lambda: DoctorCheck(
            name="feishu-docx-markdown",
            ok=False,
            detail="not configured",
            required=False,
        ),
    )

    payload = run_doctor()

    assert payload["ok"] is True
    assert [item["name"] for item in payload["checks"]] == [
        "lark-cli",
        "feishu-docx-markdown",
    ]


def test_run_doctor_fails_when_required_lark_cli_check_fails(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_lark_cli",
        lambda: DoctorCheck(name="lark-cli", ok=False, detail="missing", required=True),
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.check_feishu_docx_markdown",
        lambda: DoctorCheck(
            name="feishu-docx-markdown",
            ok=True,
            detail="ready",
            required=False,
        ),
    )

    payload = run_doctor()

    assert payload["ok"] is False


def test_check_feishu_docx_markdown_reports_ready(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.validate_markdown_doc_ref", lambda _doc: None
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.require_feishu_docx_exporter", lambda: object()
    )
    monkeypatch.setattr(
        "lark_synced_export.doctor.require_feishu_docx_credentials",
        lambda _doc: type("Credentials", (), {"source": "env"})(),
    )

    result = check_feishu_docx_markdown()

    assert result.ok is True
    assert result.required is False
    assert result.detail == "feishu-docx markdown is ready (env)."


def test_check_feishu_docx_markdown_reports_failure(monkeypatch):
    monkeypatch.setattr(
        "lark_synced_export.doctor.validate_markdown_doc_ref",
        lambda _doc: (_ for _ in ()).throw(RuntimeError("missing credentials")),
    )

    result = check_feishu_docx_markdown()

    assert result.ok is False
    assert result.required is False
    assert result.detail == "missing credentials"
