"""A server the operator was charged for must end up in the registry.

`co server new` read the registry, spent a minute creating a machine, and wrote
it back — so anything that registered during that minute was silently dropped.
The operator is charged either way, and the entry that vanishes is the one
nothing points at: `co server check` answers "No server named …" for a machine
that exists and is billing. openonion/connectonion#445
"""

import threading
import time

import pytest
import yaml

from connectonion.cli.commands import server_commands as sc


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml")
    return tmp_path / "servers.yaml"


class TestConcurrentRegistrationsSurvive:
    def test_a_slow_write_does_not_drop_a_fast_one(self, registry):
        """The shape of the bug: read, wait on the API, write."""
        def add(name, delay):
            def mutate(servers):
                time.sleep(delay)
                servers[name] = {"ssh": f"co@{name}"}
            sc._update(mutate)

        threads = [threading.Thread(target=add, args=(n, 0.15))
                   for n in ("alpha", "beta", "gamma")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(sc._load()) == ["alpha", "beta", "gamma"]

    def test_the_read_happens_inside_the_lock(self, registry):
        """Reading before taking the lock is the same bug with extra steps."""
        sc._update(lambda s: s.update({"first": {"ssh": "co@a"}}))

        seen = {}

        def mutate(servers):
            seen.update(servers)
            servers["second"] = {"ssh": "co@b"}

        sc._update(mutate)

        assert "first" in seen, "the mutation ran against a stale copy"


class TestTheFileIsNeverHalfWritten:
    def test_a_write_replaces_the_file_atomically(self, registry, monkeypatch):
        """write_text truncates first, so a process killed mid-write leaves a
        file that parses as an empty registry."""
        sc._update(lambda s: s.update({"prod": {"ssh": "co@1.2.3.4"}}))

        renamed = []
        monkeypatch.setattr(sc.os, "replace",
                            lambda a, b: renamed.append((a, b)) or None)
        sc._save({"prod": {"ssh": "co@x"}})

        assert renamed, "wrote in place instead of renaming"

    def test_no_temporary_file_is_left_behind(self, registry):
        sc._update(lambda s: s.update({"prod": {"ssh": "co@1.2.3.4"}}))

        leftovers = list(registry.parent.glob("*.tmp"))
        assert not leftovers, leftovers

    def test_what_was_written_reads_back(self, registry):
        sc._update(lambda s: s.update({"prod": {"ssh": "co@1.2.3.4"}}))

        assert yaml.safe_load(registry.read_text())["servers"]["prod"]["ssh"] == "co@1.2.3.4"


class TestTheRegistrationItself:
    def test_a_created_server_is_registered_before_it_is_announced(self):
        """The success line is printed after the write, so a reader who trusts
        the output is not trusting something that failed silently."""
        import inspect

        src = inspect.getsource(sc.handle_server_new)

        assert src.index("_update(") < src.index("is ready")
