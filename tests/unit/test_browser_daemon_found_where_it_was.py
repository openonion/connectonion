"""The browser daemon is found where it is, however the shell was started.

Four ways this week's `co browser` changes lost a running daemon, or could not
stop one:

1. Linux: the socket lived under $XDG_RUNTIME_DIR when it was set and under
   /run/user/<uid> or /tmp otherwise. Whether it is set depends on how the user
   logged in (a desktop session, `ssh`, `su`, a container shell), so one user
   got two addresses, two daemons, one profile — and the old one could not be
   reached to close it.
2. macOS: a TMPDIR that differs from the per-user temp dir (set in a profile,
   or different between shells) made the daemon started before an upgrade
   invisible to the new client.
3. `co browser --no-headless close` on a machine with no display was refused
   before it reached the running browser.
4. The close check parses `ps -o lstart`, which is localized: under ko_KR or
   ja_JP the date is not five English words and the parse finds no processes.
"""

import os
import sys
import tempfile

import pytest
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.browser_agent import client
from connectonion.cli.browser_agent import transport as tp
from connectonion.cli.commands import browser_commands
from connectonion.useful_tools.browser_tools import _async_browser

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Unix-socket endpoints")


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A fake machine: its own /tmp, /run/user and macOS per-user temp dir."""
    monkeypatch.delenv("CO_BROWSER_SOCK", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", None)       # gettempdir() caches
    monkeypatch.setattr(tp, "_current_user", lambda: "onion")
    root = tmp_path / "m"
    for name in ("tmp", "run-user", "darwin-T", "elsewhere"):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(tp, "_STABLE_TEMP_ROOT", root / "tmp")
    monkeypatch.setattr(tp, "_RUN_USER_ROOT", root / "run-user")
    monkeypatch.setattr(tp, "_darwin_user_temp_dir", lambda: root / "darwin-T")
    return root


def linux(monkeypatch):
    monkeypatch.setattr(tp, "_IS_DARWIN", False)


def macos(monkeypatch):
    monkeypatch.setattr(tp, "_IS_DARWIN", True)


def running_daemon_at(sock_dir):
    """What an older client left behind: a 0700 dir, a socket and a live owner pid."""
    sock_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(sock_dir, 0o700)
    sock = sock_dir / "browser.sock"
    sock.write_text("")
    (sock_dir / "browser.sock.pid").write_text(str(os.getpid()))
    return str(sock)


@posix_only
class TestLinuxOneAddressPerUser:
    def test_the_address_does_not_depend_on_how_the_user_logged_in(self, machine, monkeypatch):
        linux(monkeypatch)
        uid_dir = machine / "run-user" / str(os.getuid())

        uid_dir.mkdir()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(uid_dir))
        desktop = tp.default_address()
        monkeypatch.delenv("XDG_RUNTIME_DIR")
        ssh_with_logind = tp.default_address()
        uid_dir.rmdir()
        ssh_without_logind = tp.default_address()

        assert desktop == ssh_with_logind == ssh_without_logind

    def test_a_daemon_under_the_old_xdg_address_is_still_found(self, machine, monkeypatch):
        linux(monkeypatch)
        xdg = machine / "run-user" / str(os.getuid())
        old = running_daemon_at(xdg / "co")
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))

        assert client.default_sock_path() == old

    def test_an_ssh_shell_finds_the_desktop_sessions_daemon(self, machine, monkeypatch):
        linux(monkeypatch)
        old = running_daemon_at(machine / "run-user" / str(os.getuid()) / "co")

        assert client.default_sock_path() == old          # no XDG_RUNTIME_DIR here

    def test_a_dead_old_daemon_is_not_followed(self, machine, monkeypatch):
        linux(monkeypatch)
        xdg = machine / "run-user" / str(os.getuid())
        old = running_daemon_at(xdg / "co")
        (xdg / "co" / "browser.sock.pid").write_text("999999999")
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))

        assert client.default_sock_path() == tp.default_address() != old

    def test_an_old_address_anyone_can_write_to_is_not_trusted(self, machine, monkeypatch):
        linux(monkeypatch)
        xdg = machine / "elsewhere"
        running_daemon_at(xdg / "co")
        os.chmod(xdg / "co", 0o777)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))

        assert client.default_sock_path() == tp.default_address()

    def test_a_running_daemon_at_the_stable_address_wins(self, machine, monkeypatch):
        linux(monkeypatch)
        stable = tp.default_address()
        running_daemon_at(machine / "tmp" / "co-onion")
        xdg = machine / "run-user" / str(os.getuid())
        running_daemon_at(xdg / "co")
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))

        assert client.default_sock_path() == stable


@posix_only
class TestMacOSOneAddressPerUser:
    def test_tmpdir_does_not_move_the_address(self, machine, monkeypatch):
        macos(monkeypatch)
        monkeypatch.setenv("TMPDIR", str(machine / "elsewhere"))
        custom = tp.default_address()
        monkeypatch.delenv("TMPDIR")
        bare = tp.default_address()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(machine / "elsewhere"))
        nix_shell = tp.default_address()

        assert custom == bare == nix_shell
        assert custom.startswith(str(machine / "darwin-T"))

    def test_the_daemon_started_under_tmpdir_before_the_upgrade_is_found(self, machine, monkeypatch):
        macos(monkeypatch)
        monkeypatch.setenv("TMPDIR", str(machine / "elsewhere"))
        old = running_daemon_at(machine / "elsewhere" / "co-onion")

        assert client.default_sock_path() == old

    def test_an_explicit_override_is_never_second_guessed(self, machine, monkeypatch):
        macos(monkeypatch)
        monkeypatch.setenv("TMPDIR", str(machine / "elsewhere"))
        running_daemon_at(machine / "elsewhere" / "co-onion")
        monkeypatch.setenv("CO_BROWSER_SOCK", str(machine / "mine.sock"))

        assert client.default_sock_path() == str(machine / "mine.sock")


class TestCloseIgnoresDisplayFlags:
    @pytest.fixture
    def sent(self, monkeypatch):
        seen = []
        monkeypatch.setattr(browser_commands, "handle_browser",
                            lambda args, headless, engine_mode: seen.append(args) or 0)
        monkeypatch.setattr("connectonion.useful_tools.browser_tools.engine.effective_mode",
                            lambda engine: "system")
        monkeypatch.setattr(_async_browser.platform, "system", lambda: "Linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        return seen

    @pytest.mark.parametrize("args", [["close"], ["-t", "work", "close"], ["tab", "close", "work"]])
    def test_no_headless_close_without_a_display_reaches_the_browser(self, sent, args):
        result = CliRunner().invoke(cli_main.app, ["browser", "--no-headless", *args])

        assert result.exit_code == 0, result.output
        assert sent == [args]

    def test_a_page_command_is_still_refused(self, sent):
        result = CliRunner().invoke(cli_main.app, ["browser", "--no-headless", "go_to", "x.com"])

        assert result.exit_code == 2
        assert sent == []


@posix_only
def test_the_process_table_is_read_in_the_c_locale(monkeypatch):
    """ps localizes lstart; a Korean desktop's close found no processes at all."""
    def fake_ps(cmd, **kwargs):
        env = kwargs.get("env") or os.environ
        if env.get("LC_ALL") == "C" and env.get("LANG") == "C":
            out = "  4242     1 Thu Sep 24 19:30:00 2026 Google Chrome\n"
        else:
            out = "  4242     1 목  9/24 19:30:00 2026 Google Chrome\n"
        return type("Done", (), {"stdout": out})()

    monkeypatch.setenv("LC_ALL", "ko_KR.UTF-8")
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    monkeypatch.setattr(client.subprocess, "run", fake_ps)

    table = client._ps_table()

    assert table == {4242: (1, "Thu Sep 24 19:30:00 2026", "Google Chrome")}
