"""Global setup builds REM without prompts and retains a revocable init grant."""

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from connectonion.cli.commands import init as init_commands, rem_commands
from connectonion.cli.main import app
from connectonion.rem import config, schedule, service


init_rem_flow = rem_commands.init_rem_flow


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def rem_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(config, "first_runner", lambda value: value)
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    monkeypatch.setattr(rem_commands, "init_rem_flow", Mock(return_value={}))
    monkeypatch.setattr(service, "run_sync", lambda *a, **kw: pytest.fail("foreground source read"))
    monkeypatch.setattr(service, "mail_client", lambda *a, **kw: pytest.fail("mail body read"))
    monkeypatch.setattr("connectonion.rem.codex_history.archive_history", lambda *a, **kw: {})
    installed = Mock(return_value={"scheduler": "launchd"})
    monkeypatch.setattr(schedule, "default_scheduler", lambda *a, **kw: SimpleNamespace(install=installed))
    monkeypatch.setattr(init_commands, "handle_global_init", lambda **kw: None)
    return tmp_path / ".co/rem", installed


def test_no_rem_leaves_storage_absent(rem_setup):
    root, installed = rem_setup
    result = CliRunner().invoke(app, ["init", "--no-rem"])
    assert result.exit_code == 0, result.output
    assert not root.exists()
    installed.assert_not_called()


@pytest.mark.parametrize("approved", [False, True])
def test_second_init_rem_changes_nothing(rem_setup, monkeypatch, capsys, approved):
    root, installed = rem_setup
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    rem_commands.init_global_rem(yes=not approved)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    installed.reset_mock()
    capsys.readouterr()
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: pytest.fail("repeat mailbox offer"))
    monkeypatch.setattr("typer.confirm", lambda *a, **kw: pytest.fail("repeat consent"))
    rem_commands.init_global_rem()
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    installed.assert_not_called()
    assert "REM is already initialized. Watch: co rem status" in capsys.readouterr().out


@pytest.mark.parametrize("mailboxes", [{"gmail"}, {"outlook"}, {"gmail", "outlook"}])
def test_authenticated_mailboxes_are_granted_at_init(rem_setup, monkeypatch, mailboxes):
    root, _ = rem_setup
    monkeypatch.setattr(service, "mail_available", lambda kind: kind in mailboxes)
    monkeypatch.setattr(typer, "prompt", lambda *a, **kw: pytest.fail("mailbox choice"))
    monkeypatch.setattr(typer, "confirm", lambda *a, **kw: pytest.fail("consent prompt"))
    rem_commands.init_global_rem()
    for kind in mailboxes:
        assert service.subscriptions(root)[kind]["enabled"]
        assert service.subscriptions(root)[kind]["consented"]


def test_codex_scheduler_is_named_in_final_summary(rem_setup, monkeypatch, capsys):
    _, installed = rem_setup
    installed.return_value = {"scheduler": "codex-native"}
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    rem_commands.init_global_rem()
    assert "Codex Scheduled task" in next(line for line in capsys.readouterr().out.splitlines() if line.startswith("REM ready;"))


def test_start_after_global_setup_reports_deferred_first_batch(rem_setup, monkeypatch):
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    rem_commands.init_global_rem()
    result = CliRunner().invoke(app, ["rem", "start"])
    assert result.exit_code == 0, result.output
    assert "Not run on this start" in result.output
    assert "first start already ran" not in result.output
    assert "co rem sync" in result.output


@pytest.mark.parametrize("flags", [[], ["--no-rem"]])
def test_background_init_uses_the_same_rem_step(rem_setup, monkeypatch, flags):
    root, _ = rem_setup
    from connectonion.cli import mac_bootstrap
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_bootstrap, "prepare_mac_host", lambda: {"codex_ready": True})
    result = CliRunner().invoke(app, ["init", "--background", *flags])
    assert result.exit_code == 0, result.output
    assert root.exists() == (not flags)
    assert (root / ".state/consent.json").exists() == (not flags)
    if not flags:
        assert "REM ready" in result.output


def test_unsupported_platform_preserves_consent_without_scheduling(rem_setup, monkeypatch, capsys):
    root, installed = rem_setup
    monkeypatch.setattr(schedule, "default_scheduler", lambda *a, **kw: schedule.Unsupported())
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    rem_commands.init_global_rem()
    assert (root / ".state/consent.json").exists()
    installed.assert_not_called()
    assert "No scheduler available" in capsys.readouterr().out
    rem_commands.init_rem_flow.assert_called_once()


def test_scheduler_failure_leaves_an_actionable_recovery(rem_setup, monkeypatch, capsys):
    root, installed = rem_setup
    from connectonion.rem.files import RemError
    installed.side_effect = RemError("synthetic scheduler failure")
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    with pytest.raises(RemError, match="synthetic scheduler failure"):
        rem_commands.init_global_rem()
    assert (root / ".state/consent.json").exists()
    assert "Resume setup with co rem start" in capsys.readouterr().out


@pytest.fixture
def first_notebook(rem_setup, monkeypatch):
    """Synthetic mapping and evidence; all model requests stop at the runner."""
    from connectonion.rem import files, investigate, runner, sessions
    root, installed = rem_setup
    monkeypatch.setattr(rem_commands, "init_rem_flow", Mock(wraps=init_rem_flow))
    monkeypatch.setattr(runner, "ready", lambda config: ("", ""))
    monkeypatch.setattr(runner, "model_access", lambda *a: ("", ""))
    monkeypatch.setattr(sessions, "import_sessions", lambda *a, **kw: {})
    monkeypatch.setattr("connectonion.rem.mail_archive.archive_init", lambda *a, **kw: {})
    monkeypatch.setattr(investigate, "warm_session_windows", lambda *a: None)
    monkeypatch.setattr(investigate, "gather", lambda *a, **kw: ([{
        "role": "user", "source": "fixture:1", "timestamp": "2026-11-01T00:00:00Z",
        "text": "I am Ada Vale and I am preparing the Orchard launch."}], ["synthetic evidence"]))
    model = Mock(return_value={"changed": ["people/ada-vale.md"], "usage": None})
    monkeypatch.setattr(runner, "run_stage", model)

    def build_map(root, *a, **kw):
        owner = {"record": "people/ada-vale.md", "name": "Ada Vale", "addresses": ["ada@example.org"]}
        files.Notebook(root).write(owner["record"], "# Ada Vale\n\nInvestigation: not investigated\n")
        result = {"owner": owner, "people": [owner], "projects": [], "orgs": [], "errors": [],
                  "source_inventory": {"mail_observed": 1}}
        files.write_json(files.state_path(root, "map.json"), result)
        return result

    monkeypatch.setattr("connectonion.rem.map.build_map", build_map)
    monkeypatch.setattr("connectonion.rem.map.owner_summary", lambda *a: {
        "record": "people/ada-vale.md", "title": "Ada Vale",
        "path": str(root / "people/ada-vale.md"), "facts": []})
    monkeypatch.setattr(rem_commands, "_first_people_rows", lambda *a: [])
    monkeypatch.setattr(rem_commands, "_first_project_rows", lambda *a, **kw: [])
    return root, installed, model


def test_global_init_builds_first_notebook_without_questions(first_notebook, monkeypatch, capsys):
    root, installed, model = first_notebook
    from connectonion.cli import main
    monkeypatch.setattr(sys, "stdin", Terminal())
    main.init(path=None, template=None, yes=False, key=None, description=None,
              force=False, background=False, no_rem=False)
    output = capsys.readouterr().out
    rem_commands.init_rem_flow.assert_called_once()
    assert rem_commands.init_rem_flow.call_args.kwargs == {"yes": True, "start_background": False}
    assert "Read these sources with this model and schedule?" not in output
    assert "Build the first map now?" not in output
    assert "Estimate: About" in output
    assert model.called
    installed.assert_called_once()
    assert service.worker_state(root)["enabled"]
    assert "Written this run: your page" in next(line for line in output.splitlines() if line.startswith("REM ready;"))
    assert "launchd" in next(line for line in output.splitlines() if line.startswith("REM ready;"))
    assert "Full first map" not in output


@pytest.mark.parametrize("tty,yes,answer", [(True, False, "n"), (True, False, "Y"),
                                            (True, True, ""), (False, False, "")])
def test_rem_init_uses_the_same_estimate_gate(first_notebook, monkeypatch, capsys, tty, yes, answer):
    root, installed, model = first_notebook
    # Real recorded consent, reused by the standalone command through its fingerprint.
    config.prepare(root)
    assert service.ensure_consent(root, confirm=lambda summary: True)
    stream = Terminal(answer + "\n") if tty else io.StringIO()
    monkeypatch.setattr(sys, "stdin", stream)
    from click import Command
    ctx = typer.Context(Command("init"), info_name="init",
                                    obj={"root": root, "json": False})
    init_rem_flow(ctx, yes=yes)
    output = capsys.readouterr().out
    assert ("Build the first map now?" in output) == (tty and not yes)
    assert model.called == (answer != "n")
    assert "Read these sources with this model and schedule?" not in output
    if answer == "n":
        assert "co rem init" in output


@pytest.mark.parametrize("mode", ["no-investigate", "no-pages"])
def test_tty_early_return_does_not_summarise_sessions_before_estimate(first_notebook, monkeypatch, mode):
    root, _, model = first_notebook
    config.prepare(root)
    assert service.ensure_consent(root, confirm=lambda summary: True)
    monkeypatch.setattr(sys, "stdin", Terminal())
    summary = Mock(side_effect=AssertionError("model work without an estimate"))
    monkeypatch.setattr("connectonion.rem.sessions.summarise_sessions", summary)
    from click import Command
    ctx = typer.Context(Command("init"), info_name="init", obj={"root": root, "json": False})
    if mode == "no-pages":
        monkeypatch.setattr(rem_commands, "_first_page_skipped", lambda *a, **kw: "No eligible owner page.")
    init_rem_flow(ctx, **({"write_mine": False} if mode == "no-investigate" else {}))
    summary.assert_not_called()
    model.assert_not_called()


def test_connected_mailbox_consent_fingerprint_is_reused_by_first_build(first_notebook, monkeypatch, capsys):
    root, installed, model = first_notebook
    monkeypatch.setattr(service, "mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr(service, "mail_client", lambda *a, **kw: object())
    monkeypatch.setattr(sys, "stdin", Terminal("y\nY\n"))
    rem_commands.init_global_rem()
    output = capsys.readouterr().out
    assert "Read these sources with this model and schedule?" not in output
    assert service.subscriptions(root)["gmail"]["consented"]
    installed.assert_called_once()
    assert model.called


def test_global_summary_reports_each_written_page_kind(rem_setup, monkeypatch, capsys):
    _, installed = rem_setup
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    accepted = {"pages": [{"outcome": "accepted"}, {"outcome": "accepted"}]}
    rem_commands.init_rem_flow.return_value = {
        "people": [{}, {}, {}], "projects": [{}], "orgs": [{}],
        "investigate_me": {"outcome": "completed"}, "people_pages": accepted,
        "project_pages": {"pages": [{"outcome": "accepted"}]},
        "org_pages": {"pages": [{"outcome": "accepted"}]}}
    rem_commands.init_global_rem()
    final = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("REM ready;"))
    assert "Written this run: your page, 2 people, 1 project page and 1 organisation page." in final
    assert "launchd" in final



def test_tty_json_estimate_pause_uses_stderr_and_can_decline(first_notebook, monkeypatch, capsys):
    root, _, model = first_notebook
    config.prepare(root)
    assert service.ensure_consent(root, confirm=lambda summary: True)
    monkeypatch.setattr(sys, "stdin", Terminal("n\n"))
    from click import Command
    ctx = typer.Context(Command("init"), info_name="init", obj={"root": root, "json": True})
    init_rem_flow(ctx)
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["data"]["build_deferred"]
    assert "co rem init" in payload["next"]
    assert "Build the first map now? [Y/n]" in output.err
    model.assert_not_called()


def test_native_registration_failure_falls_back_to_launchd(rem_setup, monkeypatch, capsys):
    """Codex closed, or watching another home, never adopts the task; launchd keeps the clock (#2758)."""
    from connectonion.rem import codex_schedule
    from connectonion.rem.files import RemError
    root, _ = rem_setup
    monkeypatch.setattr(schedule, "default_scheduler", lambda *a, **kw: codex_schedule.CodexNative())
    monkeypatch.setattr(codex_schedule.CodexNative, "install",
                        lambda self, root, config: (_ for _ in ()).throw(RemError("Codex has not registered the paused REM task")))
    launchd = Mock(return_value={"scheduler": "launchd"})
    monkeypatch.setattr(schedule.Launchd, "install", lambda self, root, config: launchd(root, config))
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    rem_commands.init_global_rem()
    out = capsys.readouterr().out
    launchd.assert_called_once()
    assert "Using launchd for upkeep meanwhile" in out
    assert "Scheduler installed: launchd (Codex did not register the task" in next(line for line in out.splitlines() if line.startswith("REM ready;"))
    assert "Traceback" not in out


def test_co_init_says_a_scheduler_error_in_one_line(rem_setup, monkeypatch, capsys):
    from connectonion.rem.files import RemError
    from connectonion.cli import main
    root, installed = rem_setup
    installed.side_effect = RemError("synthetic scheduler failure")
    monkeypatch.setattr(sys, "stdin", Terminal("skip\ny\n"))
    with pytest.raises(typer.Exit) as stop:
        main.init(path=None, template=None, yes=False, key=None, description=None,
                  force=False, background=False, no_rem=False)
    assert stop.value.exit_code == 1
    out = capsys.readouterr().out
    assert "synthetic scheduler failure" in out
    assert "Next: co rem start" in out
    assert "Traceback" not in out

@pytest.mark.parametrize("tty,yes", [(True, False), (True, True), (False, False)])
def test_global_rem_init_never_asks_and_builds(rem_setup, monkeypatch, capsys, tty, yes):
    root, installed = rem_setup
    monkeypatch.setattr(sys, "stdin", Terminal() if tty else io.StringIO())
    monkeypatch.setattr(typer, "prompt", lambda *a, **kw: pytest.fail("mailbox prompt"))
    monkeypatch.setattr(typer, "confirm", lambda *a, **kw: pytest.fail("confirmation prompt"))
    rem_commands.init_global_rem(yes=yes)
    consent = json.loads((root / ".state/consent.json").read_text())
    assert consent["granted_by"] == "init"
    assert consent["summary"] == service.summary_fingerprint(root)
    installed.assert_called_once()
    rem_commands.init_rem_flow.assert_called_once()
    assert rem_commands.init_rem_flow.call_args.kwargs["yes"] is True
    output = capsys.readouterr().out
    assert "co auth google or co auth microsoft" in output
    assert "co rem stop" in output and "co rem sources" in output
    assert "co auth logout" in output and str(root) in output

@pytest.mark.parametrize("kind", ["gmail", "outlook"])
def test_init_grant_admits_later_mail_on_scheduled_selection(rem_setup, monkeypatch, kind):
    root, _ = rem_setup
    rem_commands.init_global_rem()
    monkeypatch.setattr(service, "mail_available", lambda name: name == kind)
    from connectonion.rem.files import maintenance_lock
    with maintenance_lock(root):
        service.refresh_init_mailboxes(root, lock_held=True)
    selected = service._selected_sources(root, "")
    assert selected[kind]["consented"]
    assert selected[kind]["adapter"] == "available"
    assert service.ensure_consent(root, confirm=lambda summary: pytest.fail("later mailbox consent"))
    service.toggle_source(root, kind, False)
    service.refresh_init_mailboxes(root)
    assert kind not in service._selected_sources(root, "")
    assert service.subscriptions(root)[kind]["unsubscribed"]


def test_init_grant_does_not_approve_new_chat(rem_setup):
    root, _ = rem_setup
    rem_commands.init_global_rem()
    service.toggle_source(root, "whatsapp", True, chats=["fictional-chat"])
    assert not service.ensure_consent(root, confirm=lambda summary: False)
    assert not service.subscriptions(root)["whatsapp"]["consented"]


def test_init_grant_survives_explicit_approval(rem_setup, monkeypatch):
    root, _ = rem_setup
    rem_commands.init_global_rem()
    service.approve_sources(root)
    monkeypatch.setattr(service, "mail_available", lambda kind: kind == "gmail")
    assert service.ensure_consent(root, confirm=lambda summary: pytest.fail("init grant lost"))
    assert service.subscriptions(root)["gmail"]["consented"]


def test_init_grant_admits_mail_enabled_before_login(rem_setup, monkeypatch):
    root, _ = rem_setup
    rem_commands.init_global_rem()
    service.toggle_source(root, "gmail", True)
    monkeypatch.setattr(service, "mail_available", lambda kind: kind == "gmail")
    assert service.ensure_consent(root, confirm=lambda summary: pytest.fail("mail already granted"))
    assert service.subscriptions(root)["gmail"]["consented"]
    assert service.subscriptions(root)["gmail"]["adapter"] == "available"
