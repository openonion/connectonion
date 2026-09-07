"""
LLM-Note: First-run browser auto-install — `co browser` must just work.

What it tests:
- find_system_chrome(): returns a path only when one of the fixed per-OS
  candidates exists.
- client._ensure_browser_ready():
  * pageless verbs (status/tab/close/...) never trigger provisioning
  * a present system Chrome skips provisioning (no subprocess)
  * no Chrome anywhere → runs `<python> -m patchright install chrome`
  * an install failure warns but does NOT raise — the daemon's own launch
    error stays the actionable fallback

Components under test:
- connectonion.useful_tools.browser_tools.chrome_finder
- connectonion.cli.browser_agent.client (_ensure_browser_ready)
"""

import sys

from connectonion.useful_tools.browser_tools import chrome_finder
from connectonion.cli.browser_agent import client as c
from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import decode_frame, encode_frame


def test_find_system_chrome_hits_an_existing_candidate(monkeypatch):
    monkeypatch.setattr(chrome_finder.platform, "system", lambda: "Windows")
    win_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    monkeypatch.setattr(chrome_finder.os.path, "exists", lambda p: p == win_path)
    assert chrome_finder.find_system_chrome() == win_path


def test_find_system_chrome_none_when_absent(monkeypatch):
    monkeypatch.setattr(chrome_finder.os.path, "exists", lambda p: False)
    assert chrome_finder.find_system_chrome() is None


class _RecordingRun:
    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        class R:
            returncode = self.returncode
        return R()


def _patch_env(monkeypatch, chrome_path, run):
    import subprocess
    monkeypatch.setattr(chrome_finder, "find_system_chrome", lambda: chrome_path)
    monkeypatch.setattr(subprocess, "run", run)


def test_pageless_verbs_never_provision(monkeypatch):
    run = _RecordingRun()
    _patch_env(monkeypatch, None, run)
    for verb in ("status", "tab ls", "close", "closetab 2", "help", "use main"):
        c._ensure_browser_ready(verb)
    assert run.calls == []


def test_system_chrome_skips_install(monkeypatch):
    run = _RecordingRun()
    _patch_env(monkeypatch, "/usr/bin/google-chrome", run)
    c._ensure_browser_ready("go_to example.com")
    assert run.calls == []


def test_missing_browser_triggers_patchright_install(monkeypatch, capsys):
    run = _RecordingRun(returncode=0)
    _patch_env(monkeypatch, None, run)
    c._ensure_browser_ready("go_to example.com")
    assert run.calls == [[sys.executable, "-m", "patchright", "install", "chromium"]]  # chromium: per-user dir, never needs admin
    assert "one-time" in capsys.readouterr().err  # the user is told what's happening


def test_failed_install_warns_but_does_not_raise(monkeypatch, capsys):
    run = _RecordingRun(returncode=1)
    _patch_env(monkeypatch, None, run)
    c._ensure_browser_ready("do fill the form")  # must not raise
    err = capsys.readouterr().err
    assert "patchright install chromium" in err  # the manual remedy is named


class TestAWarmDaemonWithNoBrowserStillProvisions:
    """The gate above is `if conn is None` — daemon coldness, not browser absence.

    Found on the real deployed nw-map agent, whose daemon was already running:

        $ co call 0xcf1619cb… co browser status
        Browser: not open · headless=false
        Stealth driver: ✓ patchright 1.61.2 — stealth patches present

        $ co call 0xcf1619cb… co browser go_to https://example.com
        Error: BrowserType.launch_persistent_context: Executable doesn't exist at
        /home/co/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome

    Every page command fails the same way, forever: the connect succeeds, so the
    cold-start branch that would have installed a browser is never reached. The
    auto-install promise ("`co browser` just works with zero setup") holds only
    for a machine whose very first browser command is a page command.

    The signal used here is the daemon's own verdict, not a path probe. There is
    no cheap way to ask whether patchright's downloaded chromium exists —
    find_system_chrome() only knows about desktop Chrome, and the download lives
    under a version-numbered directory (chromium-1228) whose layout is
    patchright's business. Probing it would be a guess that goes stale on the
    next patchright release; the launch failure is the authority, and it arrives
    exactly when it matters. Same reason `cookies()` beats `is_closed()` (#711).
    """

    @staticmethod
    def _warm_daemon(monkeypatch, replies):
        """A daemon that is up and answers `replies` in order."""
        from connectonion.cli.browser_agent import transport

        monkeypatch.setattr(transport, "IS_WINDOWS", False)
        monkeypatch.setattr(c.transport, "IS_WINDOWS", False, raising=False)
        sent = []

        class _Conn:
            def __init__(self):
                self._reply = b""

            def sendall(self, data):
                sent.append(data)
                request_id = decode_frame(data).request_id
                exit_code, text = replies[len(sent) - 1]
                self._reply = encode_frame(
                    wire.Envelope(
                        protocol_version=2,
                        request_id=request_id,
                        result=wire.BrowserResult(
                            exit_code=exit_code,
                            text=text,
                        ),
                    )
                )

            def shutdown(self, _how):
                pass

            def recv(self, size):
                reply, self._reply = self._reply[:size], self._reply[size:]
                return reply

            def close(self):
                pass

        monkeypatch.setattr(c, "_connect", lambda _p: _Conn())
        monkeypatch.setattr(c, "default_sock_path", lambda: "/tmp/never-used.sock")
        return sent

    NO_BROWSER = (
        "BrowserType.launch_persistent_context: Executable doesn't exist\n"
        "Chrome failed to start. No browser is installed for this user.\n"
        "Install it with:  patchright install chromium"
    )

    def test_it_installs_when_the_daemon_says_no_browser(self, monkeypatch):
        run = _RecordingRun(returncode=0)
        _patch_env(monkeypatch, None, run)
        self._warm_daemon(monkeypatch, [(1, self.NO_BROWSER), (0, "done")])

        c.send("go_to https://example.com")

        assert run.calls == [[sys.executable, "-m", "patchright", "install", "chromium"]]

    def test_it_retries_the_command_after_installing(self, monkeypatch):
        run = _RecordingRun(returncode=0)
        _patch_env(monkeypatch, None, run)
        sent = self._warm_daemon(monkeypatch, [(1, self.NO_BROWSER), (0, "done")])

        code = c.send("go_to https://example.com")

        assert len(sent) == 2, "the command was not resent after provisioning"
        assert code == 0

    def test_it_does_not_loop_when_the_install_does_not_help(self, monkeypatch):
        """A box where the install cannot fix it must fail, not retry forever."""
        run = _RecordingRun(returncode=0)
        _patch_env(monkeypatch, None, run)
        sent = self._warm_daemon(
            monkeypatch, [(1, self.NO_BROWSER), (1, self.NO_BROWSER)]
        )

        code = c.send("go_to https://example.com")

        assert len(sent) == 2
        assert code == 1

    def test_an_unrelated_error_provisions_nothing(self, monkeypatch):
        """Only the missing-browser verdict provisions. Any other failure is
        reported as-is — reinstalling a browser is not a general remedy."""
        run = _RecordingRun(returncode=0)
        _patch_env(monkeypatch, None, run)
        sent = self._warm_daemon(monkeypatch, [(3, "unknown tab: research")])

        code = c.send("go_to https://example.com")

        assert run.calls == []
        assert len(sent) == 1
        assert code == 3
