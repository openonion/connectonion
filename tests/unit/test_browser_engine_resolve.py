"""Getting from "a browser command was typed" to "this binary, this note".

`choose()` is the policy and is tested next door. This is the part that has to
touch the world -- is the paid package installed, is there a cached licence --
and the only thing it may never do is make a browser command fail.

The load-bearing design decision here is that **the presence of the
`onionwright` package is itself the free/paid signal.** A default install does
not have it (verified on a clean Ubuntu box: `pip list` shows patchright and no
onionwright), so on a free machine there is no import, no licence call, and no
network on the launch path at all -- which is exactly the behaviour that was
measured before any of this existed, preserved by construction rather than by
remembering to guard it.
"""

import pytest

from connectonion.useful_tools.browser_tools import engine


def test_the_default_install_gives_up_at_the_import(monkeypatch):
    """Where "no network on the free path" is actually enforced.

    `resolve()` has to call the loader to find out there is nothing to load —
    an earlier version of this test asserted the loader was never called,
    which is not something the code can know in advance. The real property is
    one level down: the production loader's first statement is
    `from onionwright...`, so on a machine without the paid package it raises
    before reading a token or opening a socket.
    """
    monkeypatch.setitem(__import__("sys").modules, "onionwright", None)

    with pytest.raises(Exception):
        engine._cached_attestation()


def test_the_real_loader_on_a_free_machine_still_browses():
    """The same thing from the outside: default wiring, no paid binary, and a
    browser still starts."""
    chosen, _ = engine.resolve(onion_path=lambda: None)

    assert chosen == engine.PATCHRIGHT


def test_a_licence_lookup_that_explodes_does_not_take_the_browser_with_it():
    """oo-api down, token expired, disk unreadable, clock wrong. All the same
    answer: browse anyway."""
    def boom():
        raise RuntimeError("oo-api unreachable")

    chosen, _ = engine.resolve(load_attestation=boom,
                               onion_path=lambda: "/opt/onion/chrome")

    assert chosen == engine.PATCHRIGHT


def test_a_pro_licence_with_the_binary_present_drives_it():
    chosen, _ = engine.resolve(
        load_attestation=lambda: {"tier": "pro", "active": True},
        onion_path=lambda: "/opt/onion/chrome",
    )

    assert chosen == engine.ONION


def test_the_onion_path_is_returned_so_the_caller_can_launch_it():
    """A name is not enough to start a process."""
    _, _, path = engine.resolve(
        load_attestation=lambda: {"tier": "pro", "active": True},
        onion_path=lambda: "/opt/onion/chrome",
        with_path=True,
    )

    assert path == "/opt/onion/chrome"


def test_a_free_resolve_returns_no_path_and_leaves_the_choice_to_the_usual_finder():
    """patchright and system Chrome are already resolved by
    installed_browser_path(); this module should not duplicate that."""
    _, _, path = engine.resolve(load_attestation=lambda: None,
                                onion_path=lambda: None, with_path=True)

    assert path is None


def test_a_probe_that_explodes_is_treated_as_absent():
    """Asking where the paid binary is can fail on a machine mid-install."""
    def boom():
        raise OSError("permission denied")

    chosen, note = engine.resolve(
        load_attestation=lambda: {"tier": "pro", "active": True},
        onion_path=boom,
    )

    assert chosen == engine.PATCHRIGHT
    assert note is not None


@pytest.mark.parametrize("attestation", [
    None,
    {},
    {"tier": "free"},
    {"tier": "pro", "active": False},
    {"tier": "pro", "active": True},
])
@pytest.mark.parametrize("path", [None, "/opt/onion/chrome"])
def test_resolve_always_produces_an_engine(attestation, path):
    chosen, _ = engine.resolve(load_attestation=lambda: attestation,
                               onion_path=lambda: path)

    assert chosen in (engine.ONION, engine.PATCHRIGHT)


def test_a_machine_without_onionwright_still_browses():
    """The free install, which is most installs.

    `onionwright` is not a dependency, so both production lookups raise
    ImportError before touching the disk or the network. `resolve()` reads
    that the same way it reads an offline machine, and the answer is a working
    browser. Asserted through the real defaults rather than injected doubles,
    because the property being protected is that the *defaults* are safe.
    """
    chosen, _ = engine.resolve()

    assert chosen == engine.PATCHRIGHT


def test_the_paid_lookups_read_what_onionwright_actually_wrote(tmp_path, monkeypatch):
    """The wiring, against the real on-disk layout.

    `resolve_binary()` extracts to `~/.onionwright/chrome/<revision>/chrome`
    and `ensure_licensed()` caches `~/.onionwright/attestation.json` holding a
    hex-encoded payload. Both readers are pointed at a fake HOME with exactly
    that shape — the same shape verified on a real paid Linux box, where the
    binary refuses to start without the licence and runs with it.
    """
    import json
    import sys
    import types

    launcher = types.ModuleType("onionwright.launcher")
    launcher.HOME = tmp_path
    package = types.ModuleType("onionwright")
    package.launcher = launcher
    monkeypatch.setitem(sys.modules, "onionwright", package)
    monkeypatch.setitem(sys.modules, "onionwright.launcher", launcher)

    payload = {"tier": "pro", "active": True, "max_concurrent": 1}
    (tmp_path / "attestation.json").write_text(json.dumps({
        "payload": json.dumps(payload).encode().hex(),
        "signature": "00" * 64,
    }))
    executable = tmp_path / "chrome" / "150.0.7871.187" / "chrome"
    executable.parent.mkdir(parents=True)
    executable.touch()

    assert engine._cached_attestation() == payload
    assert engine._onion_path() == executable

    chosen, note, path = engine.resolve(with_path=True)
    assert (chosen, note, path) == (engine.ONION, None, executable)


def test_paid_without_the_binary_downloaded_falls_back(tmp_path, monkeypatch):
    """Paid, licensed, but `resolve_binary()` has not run yet.

    A browser command must not start a 180 MB download, so this is patchright
    plus a line saying why — not a stall and not a failure.
    """
    import json
    import sys
    import types

    launcher = types.ModuleType("onionwright.launcher")
    launcher.HOME = tmp_path
    package = types.ModuleType("onionwright")
    package.launcher = launcher
    monkeypatch.setitem(sys.modules, "onionwright", package)
    monkeypatch.setitem(sys.modules, "onionwright.launcher", launcher)

    (tmp_path / "attestation.json").write_text(json.dumps({
        "payload": json.dumps({"tier": "pro", "active": True}).encode().hex(),
        "signature": "00" * 64,
    }))

    chosen, note = engine.resolve()

    assert chosen == engine.PATCHRIGHT
    assert note is not None
