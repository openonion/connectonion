"""`co tiktok`: a local plan and read-only browser evidence, and nothing past that.

The browser is faked at `_send`, the one place the CLI talks to `co browser`.
No test here reaches TikTok, a browser, or the network. What they pin down is
the boundary: a confirmed plan still refuses to submit, evidence is saved
before anything is read from the page, and a login page is never "ready".
"""

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import tiktok_browser_commands as browser
from connectonion.useful_tools.creator_plan import CreatorError

runner = CliRunner()
SKILL = Path(__file__).resolve().parents[2] / "connectonion/useful_skills/co-tiktok/SKILL.md"


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic, not playable and never sent")
    return str(path)


def _post(clip, *extra):
    return runner.invoke(app, ["tiktok", "post", clip, "--caption", "Demo", "--account", "@creator", "--json", *extra])


def _page(extracted, verified='{"ok":true}'):
    """A fake `co browser` that saves evidence and answers the two scripts."""
    calls = []

    def send(tab, *args):
        calls.append((tab, args))
        if args[0] == "take_screenshot":
            return f"Screenshot saved to: {args[1]}"
        if args[0] == "save_page_context":
            return "Saved page context to /tmp/synthetic-context\n- HTML: /tmp/synthetic-context/page.html"
        if "extract" in args[1]:
            return json.dumps(extracted)
        return verified

    return send, calls


class TestThePlan:

    def test_a_preview_touches_no_browser(self, clip, monkeypatch):
        monkeypatch.setattr(browser, "_send", lambda *a: pytest.fail("post used the browser"))
        result = _post(clip)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True and data["mode"] == "preview"
        assert len(data["plan"]["confirmation"]) == 64
        assert data["plan"]["submit_supported"] is False
        assert data["next_command"] == "co browser tab ls"

    def test_the_right_digest_still_does_not_submit(self, clip):
        plan = json.loads(_post(clip).output)["plan"]
        result = _post(clip, "--confirm", plan["confirmation"])
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "submit_unavailable"

    def test_a_wrong_digest_is_a_mismatch_not_a_submit(self, clip):
        result = _post(clip, "--confirm", "wrong")
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "confirmation_mismatch"

    def test_a_changed_file_invalidates_the_digest(self, clip):
        plan = json.loads(_post(clip).output)["plan"]
        Path(clip).write_bytes(b"different bytes")
        result = _post(clip, "--confirm", plan["confirmation"])
        assert json.loads(result.output)["code"] == "confirmation_mismatch"

    def test_dry_run_and_confirm_together_are_refused(self, clip):
        result = _post(clip, "--dry-run", "--confirm", "a" * 64)
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "conflicting_mode"

    @pytest.mark.parametrize("account", ["creator", "@", "@has space", "@" + "x" * 30])
    def test_a_handle_that_is_not_a_handle_is_refused(self, clip, account):
        result = runner.invoke(app, ["tiktok", "post", clip, "--caption", "Demo", "--account", account, "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "invalid_account"

    def test_the_plain_output_ends_on_one_literal_command(self, clip):
        result = runner.invoke(app, ["tiktok", "post", clip, "--caption", "Demo", "--account", "@creator"])
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[-1] == "Find your task's TikTok tab: co browser tab ls"


class TestUsageErrors:

    @pytest.mark.parametrize("arguments", [["tiktok", "post"], ["tiktok", "inspect"], ["tiktok", "delete", "1"]])
    def test_they_exit_2_before_any_browser_call(self, arguments, monkeypatch):
        # The generic "Next:" line belongs to the shared usage-error hook and
        # is tested with it; here the point is that nothing reached a browser.
        monkeypatch.setattr(browser, "_send", lambda *a: pytest.fail("usage error reached the browser"))
        result = runner.invoke(app, arguments)
        assert result.exit_code == 2
        assert "tiktok" in result.stderr and "--help" in result.stderr

    def test_bare_tiktok_shows_both_commands_and_where_to_start(self):
        result = runner.invoke(app, ["tiktok"])
        assert result.exit_code == 0
        assert "post" in result.output and "inspect" in result.output
        assert result.stdout.splitlines()[-1] == "Start a local post plan: co tiktok post --help"


class TestInspect:

    def test_evidence_precedes_extraction_and_reverification(self, monkeypatch, tmp_path):
        item = {"id": "login", "title": "Log in to TikTok", "text": "Log in to TikTok", "text_hash": "1234abcd"}
        send, calls = _page({"ok": False, "reason": "login_required", "selected_item": item})
        monkeypatch.setattr(browser, "_send", send)
        monkeypatch.chdir(tmp_path)
        data = browser.inspect_page("own-tab")
        assert data["ok"] is False and data["reason"] == "login_required"
        assert data["verified"] is True
        assert [args[0] for _, args in calls] == [
            "take_screenshot", "save_page_context", "run_page_script", "run_page_script", "take_screenshot"]
        assert all(tab == "own-tab" for tab, _ in calls)
        assert json.loads(calls[3][1][2]) == {"expected_item": item}
        script = Path(calls[2][1][1])
        assert script.is_absolute() and script.is_file(), "the packaged scanner must exist where the CLI looks"
        assert data["evidence"]["verified_screenshot"].endswith("_verified_1234abcd.png")

    def test_a_changed_heading_is_reported_not_trusted(self, monkeypatch, tmp_path):
        send, _ = _page({"ok": False, "reason": "login_required", "selected_item": {"text_hash": "1234abcd"}},
                        verified='{"ok":false}')
        monkeypatch.setattr(browser, "_send", send)
        monkeypatch.chdir(tmp_path)
        data = browser.inspect_page("own")
        assert data["verified"] is False and data["reason"] == "identity_changed"

    def test_an_unknown_page_is_not_verified_or_ready(self, monkeypatch, tmp_path):
        send, calls = _page({"ok": False, "reason": "unverified_surface", "submit_supported": False})
        monkeypatch.setattr(browser, "_send", send)
        monkeypatch.chdir(tmp_path)
        data = browser.inspect_page("own")
        assert data["ok"] is False and data["verified"] is False
        assert len(calls) == 3, "nothing to verify on an unknown page"

    def test_a_malformed_hash_is_not_written_into_a_filename(self, monkeypatch, tmp_path):
        send, _ = _page({"ok": False, "reason": "login_required", "selected_item": {"text_hash": "../../x"}})
        monkeypatch.setattr(browser, "_send", send)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(CreatorError) as error:
            browser.inspect_page("own")
        assert error.value.code == "evidence_failed"

    def test_a_failed_screenshot_stops_before_reading_the_page(self, monkeypatch, tmp_path):
        calls = []

        def failed(tab, *args):
            calls.append(args)
            return "Error: browser not open"

        monkeypatch.setattr(browser, "_send", failed)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tiktok", "inspect", "--tab", "own", "--json"])
        assert result.exit_code == 1
        assert len(calls) == 1
        data = json.loads(result.output)
        assert data["code"] == "evidence_failed"
        assert data["next_command"] == "co browser tab ls"

    @pytest.mark.parametrize("tab", ["", "has space", "../x", "a;b"])
    def test_a_tab_name_that_could_be_anything_else_is_refused(self, tab, monkeypatch):
        monkeypatch.setattr(browser, "_send", lambda *a: pytest.fail("bad tab reached the browser"))
        with pytest.raises(CreatorError) as error:
            browser.inspect_page(tab)
        assert error.value.code == "invalid_tab"

    def test_transport_is_the_public_cli_with_no_shell_and_a_timeout(self, monkeypatch):
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


def test_the_skill_and_the_help_name_the_same_commands():
    from typer.main import get_command
    commands = set(get_command(app).commands["tiktok"].commands)
    documented = set(re.findall(r"co tiktok ([a-z][a-z-]+)", SKILL.read_text()))
    assert documented == commands
    result = runner.invoke(app, ["tiktok", "--help"])
    assert result.exit_code == 0
    assert all(name in result.output for name in commands)
