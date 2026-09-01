"""installed_browser_path() costs a second, and `co browser status` now pays it.

Measured on a Linux box with no desktop Chrome, so the patchright branch is the
one taken:

    patchright branch:     1.06s then 1.01s
    system-chrome branch:  0.0001s

`status` is deliberately in PAGELESS_VERBS — the verbs that never launch Chrome
because they are the cheap ones an agent calls freely to orient itself. Adding a
second to it is a regression, and it is mine: it arrived with the row that
reports whether a browser exists.

So the found path is memoised, and only the found path. The distinction matters:

- A browser that exists keeps existing. If someone deletes it, the launch failure
  reports that, and the client provisions on it.
- A machine with NO browser is one someone is actively fixing, and `status` is
  how they check. Caching "none installed" would keep telling them it is still
  broken after they fixed it — a stale answer from a command whose only job is to
  be current. Re-probing costs a second on a machine that cannot browse at all,
  where a second is nothing.

The system-chrome branch is already 0.1ms and is not worth caching.
"""

import pytest

import connectonion.useful_tools.browser_tools.browser as browser_module


@pytest.fixture(autouse=True)
def clean_memo():
    browser_module.forget_browser_path()
    yield
    browser_module.forget_browser_path()


@pytest.fixture
def no_desktop_chrome(monkeypatch):
    monkeypatch.setattr(browser_module, "find_system_chrome", lambda: None)


class _CountingProbe:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.result


class TestAFoundBrowserIsProbedOnce:

    def test_the_second_call_does_not_probe(self, monkeypatch, tmp_path, no_desktop_chrome):
        real = tmp_path / "chrome"
        real.write_text("#!/bin/sh\n")
        probe = _CountingProbe(str(real))
        monkeypatch.setattr(browser_module, "_onionwright_chromium_path", probe)

        first = browser_module.installed_browser_path()
        second = browser_module.installed_browser_path()

        assert first == second == str(real)
        assert probe.calls == 1


class TestAMissingBrowserIsProbedAgain:

    def test_every_call_re_probes(self, monkeypatch, no_desktop_chrome):
        probe = _CountingProbe("/nowhere/chrome")
        monkeypatch.setattr(browser_module, "_onionwright_chromium_path", probe)

        assert browser_module.installed_browser_path() is None
        assert browser_module.installed_browser_path() is None
        assert probe.calls == 2

    def test_installing_one_is_noticed_without_a_restart(self, monkeypatch, tmp_path,
                                                         no_desktop_chrome):
        """The whole reason the negative is not cached."""
        later = tmp_path / "chrome"
        monkeypatch.setattr(browser_module, "_onionwright_chromium_path", lambda: str(later))

        assert browser_module.installed_browser_path() is None

        later.write_text("#!/bin/sh\n")  # the user runs `onionwright install chromium`

        assert browser_module.installed_browser_path() == str(later)


class TestADesktopChromeShortCircuits:

    def test_the_driver_is_never_started(self, monkeypatch):
        """0.1ms already — and starting a driver to confirm a path we have is
        work for nothing."""
        def explode():
            raise AssertionError("the patchright driver should not have started")

        monkeypatch.setattr(browser_module, "find_system_chrome",
                            lambda: "/usr/bin/google-chrome")
        monkeypatch.setattr(browser_module, "_onionwright_chromium_path", explode)

        assert browser_module.installed_browser_path() == "/usr/bin/google-chrome"
