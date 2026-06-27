import json

from lark_synced_export.cli import run_main
from lark_synced_export.doctor import check_lark_cli


def test_run_main_doctor_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "lark_synced_export.cli.run_doctor",
        lambda: {"ok": True, "checks": [{"name": "lark-cli", "ok": True, "detail": "ok"}]},
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
