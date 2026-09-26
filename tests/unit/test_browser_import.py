"""`co browser import` carries Chrome's logins into the co browser profile (#1477).

The Chrome profile is fake, the Keychain is stubbed and the daemon is a
recorder: no real Chrome, Keychain, browser or network. What matters is what
reaches the target browser's add_cookies, what is refused before that, and
that a cookie value never reaches the terminal.
"""

import json
import os
import re
import shlex
import time

import pytest

from connectonion.cli.commands import browser_import
from connectonion.useful_tools.browser_tools import chrome_cookies as chrome
from tests.fixtures.chrome_profile import PASSWORD, cookie, make_profile

LATER = time.time() + 86400
VALUES = ["li-at-SECRET-1", "jsession-SECRET-2", "gh-SECRET-3", "old-SECRET-4"]


class FakeDaemon:
    """Answers the three verbs the import sends, and keeps what was loaded."""

    def __init__(self, target_cookies=(), reject=()):
        self.lines, self.loaded = [], []
        self.target_cookies, self.reject = list(target_cookies), set(reject)

    def __call__(self, line, *, engine_mode, headless):
        self.lines.append((line, engine_mode))
        argv = shlex.split(line)
        if argv[:1] == ["open_browser"]:
            return 0, "Browser opened"
        if argv[:2] == ["cookies", "ls"]:
            return 0, json.dumps(self.target_cookies)
        if argv[:2] == ["cookies", "load"]:
            batch = json.loads(open(argv[2]).read())["cookies"]
            if any(c["name"] in self.reject for c in batch):
                return 1, "Error: BrowserContext.add_cookies: Invalid cookie fields"
            self.loaded.extend(batch)
            return 0, f"loaded {len(batch)} cookie(s)"
        raise AssertionError(f"unexpected daemon line {line!r}")


@pytest.fixture
def chrome_home(tmp_path, monkeypatch):
    make_profile(tmp_path, "Default", [
        cookie("github.com", "user_session", "gh-SECRET-3", expires=LATER),
    ], shown_name="Aaron")
    make_profile(tmp_path, "Profile 1", [
        cookie(".linkedin.com", "li_at", "li-at-SECRET-1", expires=LATER, samesite=0),
        cookie(".www.linkedin.com", "JSESSIONID", "jsession-SECRET-2", expires=LATER, samesite=0),
        cookie(".linkedin.com", "stale", "old-SECRET-4", expires=time.time() - 60),
        cookie(".example.com", "other", "not-selected"),
    ], shown_name="openonion")
    monkeypatch.setattr(chrome, "chrome_root", lambda: tmp_path)
    monkeypatch.setattr(chrome, "is_macos", lambda: True)
    keychain = []
    monkeypatch.setattr(chrome, "keychain_password", lambda: keychain.append(1) or PASSWORD)
    monkeypatch.setattr("connectonion.cli.commands.browser_commands._ensure_paid_client", lambda: None)
    monkeypatch.delenv("CO_BROWSER_ENGINE", raising=False)
    return keychain


@pytest.fixture(autouse=True)
def _keep_stdin(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "stdin", sys.stdin)


@pytest.fixture
def daemon(monkeypatch):
    fake = FakeDaemon()
    monkeypatch.setattr(browser_import, "_daemon", fake)
    return fake


class _Stdin:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


def run(capsys, *args, tty=False):
    browser_import.sys.stdin = _Stdin(tty)  # restored by the autouse fixture below
    code = browser_import.handle_browser_import(list(args))
    out = capsys.readouterr()
    text = re.sub(r"\x1b\[[0-9;]*m", "", out.out + out.err)
    for value in VALUES:
        assert value not in text, "a cookie value reached the terminal"
    return code, text


def test_dry_run_lists_sites_and_counts_and_writes_nothing(chrome_home, daemon, capsys):
    code, text = run(capsys, "--profile", "openonion", "--domain", "linkedin.com", "--dry-run")

    assert code == 0
    assert re.search(r"linkedin\.com\s+2 cookie\(s\)\s+\(skipped 1 expired\)", text)
    assert "example.com" not in text
    assert "Cookies only" in text
    assert daemon.lines == [] and chrome_home == [], "a dry run must not reach the browser or Keychain"
    assert "Next: co browser import --profile 'Profile 1' --domain linkedin.com" in text


def test_import_writes_through_add_cookies_into_the_paid_engine_by_default(chrome_home, daemon, capsys):
    code, text = run(capsys, "--profile", "Profile 1", "--domain", "linkedin.com", "--yes")

    assert code == 0, text
    assert {engine for _, engine in daemon.lines} == {"onion"}
    assert [line.split()[0:2] for line, _ in daemon.lines][:2] == [["open_browser"], ["cookies", "ls"]]
    assert sorted(c["name"] for c in daemon.loaded) == ["JSESSIONID", "li_at"]
    li_at = next(c for c in daemon.loaded if c["name"] == "li_at")
    assert li_at["value"] == "li-at-SECRET-1" and li_at["sameSite"] == "None"
    assert re.search(r"linkedin\.com\s+wrote 2 cookie\(s\)\s+\(skipped 1 expired\)", text)
    assert "Keychain" in text
    assert "Next: co browser --engine wtf go_to https://linkedin.com" in text


def test_a_site_the_target_is_signed_in_to_is_left_alone(chrome_home, monkeypatch, capsys):
    """The owner's rule: an import must never switch the account the paid
    browser is already using. --replace is the explicit way to do that."""
    fake = FakeDaemon(target_cookies=[{"name": "li_at", "domain": ".linkedin.com", "value": "…"}])
    monkeypatch.setattr(browser_import, "_daemon", fake)

    code, text = run(capsys, "--profile", "Profile 1", "--domain", "linkedin.com", "--yes", "--engine", "system")

    assert code == 0
    assert fake.loaded == []
    assert "already signed in in the target (1 cookie(s) there)" in text

    code, text = run(capsys, "--profile", "Profile 1", "--domain", "linkedin.com", "--yes", "--replace",
                     "--engine", "system")
    assert sorted(c["name"] for c in fake.loaded) == ["JSESSIONID", "li_at"]
    assert re.search(r"linkedin\.com\s+replaced with 2 cookie\(s\)", text)


def test_a_rejected_cookie_is_named_and_the_rest_still_land(chrome_home, monkeypatch, capsys):
    fake = FakeDaemon(reject={"JSESSIONID"})
    monkeypatch.setattr(browser_import, "_daemon", fake)

    code, text = run(capsys, "--profile", "Profile 1", "--domain", "linkedin.com", "--yes", "--engine", "system")

    assert code == 0
    assert [c["name"] for c in fake.loaded] == ["li_at"]
    assert "rejected by the browser (JSESSIONID: Error: BrowserContext.add_cookies: Invalid cookie fields)" in text


def test_the_cookie_files_handed_to_the_daemon_are_gone_afterwards(chrome_home, daemon, capsys):
    run(capsys, "--domain", "github.com", "--yes", "--engine", "system")
    paths = [shlex.split(line)[2] for line, _ in daemon.lines if line.startswith("cookies load")]
    assert paths and not any(os.path.exists(p) for p in paths)


def test_no_terminal_and_no_yes_is_refused_before_the_keychain(chrome_home, daemon, capsys):
    code, text = run(capsys, "--domain", "github.com")

    assert code == 2
    assert chrome_home == [] and daemon.lines == []
    assert "Next: co browser import --profile Default --domain github.com --yes" in text


def test_a_terminal_asks_once_and_no_means_nothing(chrome_home, daemon, capsys, monkeypatch):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda text: prompts.append(text) or "n")

    code, text = run(capsys, "--domain", "github.com", tty=True)

    assert code == 2 and len(prompts) == 1 and "billed" in prompts[0]
    assert chrome_home == [] and daemon.lines == []


def test_a_terminal_yes_imports(chrome_home, daemon, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda text: "y")
    code, _ = run(capsys, "--profile", "Aaron", "--domain", "github.com", "--engine", "system", tty=True)
    assert code == 0 and [c["name"] for c in daemon.loaded] == ["user_session"]


def test_usage_errors_name_the_help_page(chrome_home, daemon, capsys):
    assert run(capsys, "--bogus")[0] == 2
    assert run(capsys, "--from", "safari")[0] == 2
    code, text = run(capsys, "--help")
    assert code == 0 and "Example:" in text and "Back: co browser --help" in text


def test_not_macos_says_so(chrome_home, daemon, capsys, monkeypatch):
    monkeypatch.setattr(chrome, "is_macos", lambda: False)
    code, text = run(capsys, "--dry-run")
    assert code == 1 and "macOS only" in text


def test_co_browser_import_help_is_its_own_page():
    """Click answers --help before any handler; the import page must still be reachable."""
    from typer.testing import CliRunner
    from connectonion.cli import main

    result = CliRunner().invoke(main.app, ["browser", "--engine", "wtf", "import", "--help"])
    assert result.exit_code == 0
    assert "co browser import — carry your Chrome logins" in result.output
    assert "Back: co browser --help" in result.output
