"""The local server registry, which is how you reach machines you have paid for.

Losing an entry here is not a cosmetic bug: `co server new` prints
"✓ ready … $360.00 charged" and writes the entry, and every later command finds
the machine by name. An entry that disappears is a server you are billed for and
cannot reach.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from connectonion.cli.commands import server_commands as sc


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml")
    return tmp_path / "servers.yaml"


def test_a_registration_survives_a_concurrent_writer(registry):
    """Two `co` commands overlapping must not lose each other's servers.

    Reproduces what an e2e run hit for real: `co server new` registered a
    machine it had just been charged $360 for, a `co server ls` was running at
    the same time, and the very next command answered "No server named …".
    """
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: sc._register(f"srv-{i}", {"ssh": f"co@10.0.0.{i}"}), range(40)))

    servers = sc._load()
    assert len(servers) == 40, f"lost {40 - len(servers)} registrations to a race"


def test_a_save_never_leaves_a_half_written_file(registry):
    """write_text truncates first. An interrupted save used to leave the registry
    empty — every paid server unreachable by name until someone re-added them."""
    sc._register("keeper", {"ssh": "co@10.0.0.1"})
    before = registry.read_text()

    with pytest.raises(RuntimeError):
        with sc._registry_lock():
            raise RuntimeError("interrupted mid-update")

    assert registry.read_text() == before
    assert sc._load()["keeper"]["ssh"] == "co@10.0.0.1"


def test_the_lock_is_released_even_when_the_body_raises(registry):
    with pytest.raises(RuntimeError):
        with sc._registry_lock():
            raise RuntimeError("boom")

    with sc._registry_lock():          # would hang or fail if the lock leaked
        pass
    assert not registry.with_suffix(".yaml.lock").exists()


def test_a_stale_lock_does_not_wedge_the_cli_forever(registry):
    """A killed process leaves its lock behind. Refusing to run at all after that
    is worse than the race it prevents."""
    lock = registry.with_suffix(".yaml.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))

    with sc._registry_lock(timeout=0.2):
        sc._save({"after-stale": {"ssh": "co@10.0.0.9"}})

    assert "after-stale" in sc._load()


def test_register_replaces_one_entry_and_keeps_the_rest(registry):
    sc._register("a", {"ssh": "co@1.1.1.1"})
    sc._register("b", {"ssh": "co@2.2.2.2"})
    sc._register("a", {"ssh": "co@3.3.3.3"})

    servers = sc._load()
    assert servers["a"]["ssh"] == "co@3.3.3.3"
    assert servers["b"]["ssh"] == "co@2.2.2.2"


def test_no_temp_files_are_left_behind(registry):
    sc._register("a", {"ssh": "co@1.1.1.1"})
    leftovers = [p.name for p in registry.parent.iterdir() if ".tmp" in p.name]
    assert leftovers == []
