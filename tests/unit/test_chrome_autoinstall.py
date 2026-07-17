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
