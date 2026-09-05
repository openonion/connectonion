"""CLI behavior, not SDK internals: synthetic Google credentials and no live browser access."""

import io
import json
import re
import shlex
import stat
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import creator_commands as shared
from connectonion.cli.commands import youtube_commands as youtube
from connectonion.cli.commands import tiktok_browser_commands as browser
from connectonion.useful_tools.creator_plan import CreatorError

CHANNEL = "UC" + "a" * 22
VIDEO = "Abcdefgh_01"
runner = CliRunner()


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic, not playable and never sent")
    return str(path)


@pytest.fixture
def client(monkeypatch):
    tool = MagicMock()
    tool.list_videos.return_value = [{"id": VIDEO, "title": "Visible title", "visibility": "public", "views": 0}]
    tool.channel.return_value = {"id": CHANNEL, "title": "Channel"}
    tool.video.return_value = {"id": VIDEO, "channel_id": CHANNEL, "title": "Video"}
    tool.update.return_value = {"operation": "youtube.update", "confirmation": "a" * 64}
    monkeypatch.setattr(youtube, "_client", lambda: tool)
    return tool


def test_upload_and_tiktok_previews_need_no_token_client_or_network(clip, monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda *a, **k: pytest.fail("Offline preview accessed auth"))
    commands = [
        ["youtube", "put", clip, "--title", "Demo", "--channel", CHANNEL, "--json"],
        ["tiktok", "post", clip, "--caption", "Demo", "--account", "@creator", "--json"],
    ]
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True and data["mode"] == "preview"
        assert len(data["plan"]["confirmation"]) == 64
        assert data["next_command"].startswith("co ")


@pytest.mark.parametrize("arguments", [[], ["list"], ["channel"], ["video", VIDEO]])
def test_missing_auth_is_json_error_with_one_recovery(arguments, monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_SCOPES", raising=False)
    result = runner.invoke(app, ["youtube", *arguments, "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["code"] == "auth_required"
    assert data["next_command"] == "co auth google --youtube"


@pytest.mark.parametrize("arguments", [["youtube", "video"], ["youtube", "list", "-n", "201"],
                                       ["youtube", "inspect"], ["tiktok", "post"], ["tiktok", "delete", "1"]])
def test_usage_errors_never_enter_a_provider(arguments, monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda *a, **k: pytest.fail("Usage error entered provider"))
    result = runner.invoke(app, arguments)
    assert result.exit_code == 2
    assert "--help" in result.output
    assert result.stdout.splitlines()[-1].startswith("Next: co ")
    assert not result.stderr


def test_default_list_routes_and_json_counts_are_typed(client):
    result = runner.invoke(app, ["youtube", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["items"][0]["views"] == 0
    assert data["next_command"] == "co youtube video 1"
    client.list_videos.assert_called_once_with(None, 20)


def test_pipe_rows_have_number_full_id_and_one_literal_tip(client, monkeypatch):
    monkeypatch.setattr(shared, "console", Console(force_terminal=False))
    result = runner.invoke(app, ["youtube", "list"])
    assert result.exit_code == 0
    assert f"1\t{VIDEO}\tVisible title\tpublic\t0" in result.output
    assert result.output.splitlines()[-1] == "Inspect one: co youtube video 1"
    assert "\x1b" not in result.output


def test_tty_does_not_interpret_provider_markup_or_escape_sequences(client, monkeypatch):
    client.list_videos.return_value[0]["title"] = "[link=https://evil]x[/link]\x1b[2J"
    stream = io.StringIO()
    monkeypatch.setattr(shared, "console", Console(file=stream, force_terminal=True, width=180))
    result = runner.invoke(app, ["youtube", "list"])
    assert result.exit_code == 0
    assert "https://evil" in stream.getvalue()
    assert "\x1b[2J" not in stream.getvalue()
    assert "Inspect one: co youtube video 1" in result.output


def test_number_cache_contains_only_ids_is_private_and_survives_empty(client):
    assert runner.invoke(app, ["youtube", "list"]).exit_code == 0
    cache = shared._cache()
    before = cache.read_bytes()
    assert json.loads(before) == {"1": VIDEO}
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    client.list_videos.return_value = []
    result = runner.invoke(app, ["youtube", "list", "--json"])
    assert result.exit_code == 0
    assert cache.read_bytes() == before
    assert json.loads(result.output)["next_command"] == "co youtube channel"


@pytest.mark.parametrize("contents", [None, "not json", "[]", '{"1": "https://evil/watch?v=Abcdefgh_01"}'])
def test_stale_or_corrupt_number_refuses_without_refetch(client, contents):
    if contents is not None:
        shared._cache().parent.mkdir(parents=True, exist_ok=True)
        shared._cache().write_text(contents)
    result = runner.invoke(app, ["youtube", "video", "1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["code"] == "stale_number"
    client.video.assert_not_called()
    client.list_videos.assert_not_called()


def test_update_preview_and_confirmation_are_distinct_routes(client):
    result = runner.invoke(app, ["youtube", "update", VIDEO, "--title", "Changed", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["mode"] == "preview"
    client.update.assert_called_once_with(VIDEO, "Changed", None, confirmation=None)
    client.update.reset_mock()
    result = runner.invoke(app, ["youtube", "update", VIDEO, "--title", "Changed", "--dry-run", "--confirm", "abc", "--json"])
    assert result.exit_code == 1
    client.update.assert_not_called()


def test_tiktok_confirmation_checks_digest_but_never_submits(clip):
    command = ["tiktok", "post", clip, "--caption", "Demo", "--account", "@creator", "--json"]
    plan = json.loads(runner.invoke(app, command).output)["plan"]
    result = runner.invoke(app, [*command, "--confirm", plan["confirmation"]])
    assert result.exit_code == 1
    assert json.loads(result.output)["code"] == "submit_unavailable"
    result = runner.invoke(app, [*command, "--confirm", "wrong"])
    assert json.loads(result.output)["code"] == "confirmation_mismatch"


def test_unknown_provider_exception_is_redacted(client):
    client.video.side_effect = RuntimeError("access_token=SECRET refresh_token=SECRET uri=SECRET")
    result = runner.invoke(app, ["youtube", "video", VIDEO, "--json"])
    assert result.exit_code == 1
    assert "SECRET" not in result.output
    assert "Traceback" not in result.output
    assert json.loads(result.output)["code"] == "unexpected_response"


def test_browser_evidence_precedes_extraction_and_reverification(monkeypatch, tmp_path):
    calls = []
    item = {"id": "login", "title": "Log in to TikTok", "text": "Log in to TikTok", "text_hash": "1234abcd"}
    def send(tab, *args):
        calls.append((tab, args))
        if args[0] == "take_screenshot":
            return f"Screenshot saved to: {args[1]}"
        if args[0] == "save_page_context":
            return "Saved page context to /tmp/synthetic-context\n- HTML: /tmp/synthetic-context/page.html"
        if "extract" in args[1]:
            return json.dumps({"ok": False, "reason": "login_required", "selected_item": item})
        assert json.loads(args[2]) == {"expected_item": item}
        return '{"ok":true}'
    monkeypatch.setattr(browser, "_send", send)
    monkeypatch.chdir(tmp_path)
    data = browser.inspect_page("own-tab")
    assert data["ok"] is False and data["verified"] is True
    assert [args[0] for _, args in calls] == ["take_screenshot", "save_page_context", "run_page_script", "run_page_script", "take_screenshot"]
    assert all(tab == "own-tab" for tab, _ in calls)
    assert Path(calls[2][1][1]).is_absolute()


def test_browser_failure_does_not_extract_or_report_ready(monkeypatch):
    calls = []
    def failed(tab, *args):
        calls.append(args)
        return "Error: browser not open"
    monkeypatch.setattr(browser, "_send", failed)
    result = runner.invoke(app, ["tiktok", "inspect", "--tab", "own", "--json"])
    assert result.exit_code == 1
    assert len(calls) == 1
    assert json.loads(result.output)["code"] == "evidence_failed"


def test_browser_transport_uses_public_cli_no_shell_and_a_timeout(monkeypatch):
    transport = MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout='{"ok":true}', stderr=""))
    monkeypatch.setattr(browser.subprocess, "run", transport)
    assert browser._send("own", "run_page_script", "/path with spaces/extract.js", "{}") == '{"ok":true}'
    args, kwargs = transport.call_args
    assert args[0] == ["co", "browser", "-t", "own", "run_page_script", "/path with spaces/extract.js", "{}"]
    assert kwargs["timeout"] == 45 and "shell" not in kwargs
    transport.side_effect = subprocess.TimeoutExpired("co", 45, output="secret")
    with pytest.raises(CreatorError, match="timed out") as error:
        browser._send("own", "get_current_url")
    assert "secret" not in str(error.value)


def test_skill_and_help_have_the_same_complete_command_surface():
    from typer.main import get_command
    skill = (Path(__file__).resolve().parents[2] / "connectonion/useful_skills/co-creator/SKILL.md").read_text()
    for provider in ["youtube", "tiktok"]:
        commands = set(get_command(app).commands[provider].commands)
        documented = set(re.findall(rf"co {provider} ([a-z][a-z-]+)", skill))
        assert documented == commands
        result = runner.invoke(app, [provider, "--help"])
        assert result.exit_code == 0
        assert all(name in result.output for name in commands)


def test_public_youtube_tool_builds_agent_schemas_without_credentials():
    from connectonion import YouTube, create_tool_from_function
    tool = YouTube(service=MagicMock())
    for name in ["channel", "list_videos", "video", "upload", "update"]:
        assert create_tool_from_function(getattr(tool, name))


def test_youtube_never_enters_browser_and_has_no_token_flag(client, monkeypatch):
    monkeypatch.setattr(browser, "_send", lambda *a: pytest.fail("YouTube used browser"))
    for arguments in [[], ["channel"], ["list"], ["video", VIDEO], ["update", VIDEO, "--title", "New"]]:
        assert runner.invoke(app, ["youtube", *arguments]).exit_code == 0
    assert runner.invoke(app, ["youtube", "inspect", "--tab", "own"]).exit_code == 2
    assert runner.invoke(app, ["youtube", "list", "--token-stdin"]).exit_code == 2


def test_upload_tip_binds_exact_arguments_and_digest_without_running_it(clip, monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda *a, **k: pytest.fail("Preview accessed provider"))
    result = runner.invoke(app, ["youtube", "put", clip, "--title", "A 'quoted' demo", "--description", "literal $(no-command)", "--channel", CHANNEL, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert shlex.split(data["next_command"]) == ["co", "youtube", "put", str(Path(clip).resolve()),
        "--title", "A 'quoted' demo", "--channel", CHANNEL, "--description", "literal $(no-command)",
        "--privacy", "private", "--category", "22", "--confirm", data["plan"]["confirmation"]]
    assert "After the user approves" in data["next_tip"]


def test_update_tip_uses_full_id_and_preserves_an_explicit_empty_description(client):
    result = runner.invoke(app, ["youtube", "update", VIDEO, "--description", "", "--json"])
    data = json.loads(result.output)
    assert shlex.split(data["next_command"]) == ["co", "youtube", "update", VIDEO, "--description", "", "--confirm", "a" * 64]
    assert "After the user approves" in data["next_tip"]


@pytest.mark.parametrize("arguments", [["youtube", "--bad-option"], ["youtube", "list", "--bad-option"], ["youtube", "--json", "list"]])
def test_group_and_leaf_usage_errors_end_with_a_piped_recovery(arguments):
    result = runner.invoke(app, arguments)
    assert result.exit_code == 2
    assert result.stdout.splitlines()[-1].startswith("Next: co youtube")
    assert not result.stderr
