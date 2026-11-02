"""macOS asks for the revision that carries the renewal fix; Linux stays put.

Before openonion/browser#145 every macOS renewal reused one literal
Idempotency-Key, so paid macOS sessions ended after 15 minutes. The fix could
only ship on a new revision. Linux renews through Onionwright, never had the
bug, and its builder was offline, so it keeps the revision it already has.
"""

import importlib
import sys

from connectonion.useful_tools.browser_tools import engine


def revision_on(monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    return importlib.reload(engine).BROWSER_REVISION


def test_macos_asks_for_the_revision_with_the_renewal_fix(monkeypatch):
    assert revision_on(monkeypatch, "darwin") == "154.0.8037.100"


def test_linux_keeps_the_revision_it_already_has(monkeypatch):
    assert revision_on(monkeypatch, "linux") == "154.0.8037.58"


def teardown_module():
    importlib.reload(engine)
