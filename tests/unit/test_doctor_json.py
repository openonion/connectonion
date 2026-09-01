"""Stable JSON and fail-closed semantics for scriptable doctor repairs."""

import json
import subprocess

from typer.testing import CliRunner

from connectonion.cli.commands.doctor_runtime import RuntimeCheck, runtime_json_report
from connectonion.cli.main import app


def _missing():
    return [
        RuntimeCheck("python", "Python", "ok", "3.10.13"),
        RuntimeCheck(
            "browser",
            "Browser binary",
            "missing",
            "none installed",
            ("python", "-m", "onionwright", "install", "chromium"),
        ),
        RuntimeCheck("platform", "Operating system", "ok", "Linux"),
    ]


def test_same_state_produces_the_same_ordered_schema():
    first, first_code = runtime_json_report(fix=False, approved=False, probe=_missing)
    second, second_code = runtime_json_report(fix=False, approved=False, probe=_missing)

    assert first == second
    assert first_code == second_code == 1
    assert list(first) == [
        "schema_version",
        "command",
        "fix_requested",
        "approved_noninteractive",
        "approval_required",
        "checks",
        "plan",
        "outcomes",
        "summary",
    ]
    assert [check["id"] for check in first["checks"]] == ["python", "browser", "platform"]
    assert first["schema_version"] == 1
    assert "generated_at" not in first


def test_noninteractive_fix_without_yes_fails_closed():
    calls = []
    report, code = runtime_json_report(
        fix=True,
        approved=False,
        probe=_missing,
        run=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert code == 1
    assert calls == []
    assert report["approval_required"] is True
    assert report["outcomes"][0]["outcome"] == "skipped"
    assert report["outcomes"][0]["detail"] == "not approved"


def test_explicit_yes_records_the_command_and_repair_result():
    states = [_missing(), [
        RuntimeCheck("python", "Python", "ok", "3.10.13"),
        RuntimeCheck("browser", "Browser binary", "ok", "/user/chromium"),
        RuntimeCheck("platform", "Operating system", "ok", "Linux"),
    ]]
    calls = []

    def probe():
        return states.pop(0)

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    report, code = runtime_json_report(fix=True, approved=True, probe=probe, run=run)

    assert code == 0
    assert calls == [["python", "-m", "onionwright", "install", "chromium"]]
    assert report["plan"][0]["command"] == calls[0]
    assert report["outcomes"][0]["outcome"] == "repaired"
    assert report["summary"] == {
        "status": "healthy",
        "exit_code": 0,
        "blocked_check_ids": [],
    }


def test_cli_json_is_one_parseable_document(monkeypatch):
    from connectonion.cli.commands import doctor_runtime

    healthy = lambda: [RuntimeCheck("python", "Python", "ok", "3.10.13")]
    monkeypatch.setattr(doctor_runtime, "runtime_checks", healthy)
    secret = "oo_live_must_never_enter_the_support_bundle"
    monkeypatch.setenv("OPENONION_API_KEY", secret)

    result = CliRunner().invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["schema_version"] == 1
    assert result.output.count("\n") == 1
    assert secret not in result.output
