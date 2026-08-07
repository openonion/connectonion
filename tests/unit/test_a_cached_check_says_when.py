"""`co server ls` says "ok" under a column named LAST CHECK, with no when.

The value is written only by `co server check`, and stored flat:

    nw-map:
      last_check: ok
      ssh: co@35.189.30.72

`co server ls` reads that file and renders it — no probe of its own. So a server
that passed once and has been dead since still reads `ok`, and the column name
promises a recency the value cannot carry. On this machine four of five servers
read `ok` and the oldest of those checks is of unknown age.

It is the table you consult before `co deploy --to`, which is exactly when a
stale green is expensive.

A live probe per row would make `ls` pay five SSH round-trips, and the docstring
for the command says the opposite is wanted — being offline must not stop you
listing your targets. So the outcome keeps its cache and gains a time anchor, and
the age is shown next to it.

Not a finding: the failure values are rendered red. `nw-runner` reads
`Ubuntu 24.04`, which is the name of the requirement that failed, and looks like
neutral information in a stripped-colour capture — which is how I first read it.
With colour it is `\x1b[31mUbuntu 24.04\x1b[0m`. The renderer was right.
"""

import pytest


@pytest.fixture
def servers_file(tmp_path, monkeypatch):
    """Point the module at a throwaway servers.yaml."""
    from connectonion.cli.commands import server_commands

    path = tmp_path / "servers.yaml"
    monkeypatch.setattr(server_commands, "SERVERS_FILE", path)
    return path


class TestTheOutcomeIsStamped:

    def test_recording_stores_a_time(self, servers_file):
        from connectonion.cli.commands import server_commands

        server_commands._save({"box": {"ssh": "u@h", "last_check": None}})
        server_commands._record("box", "ok")

        entry = server_commands._load()["box"]
        assert entry.get("last_check_at"), "no time anchor was written"

    def test_the_outcome_is_still_there(self, servers_file):
        from connectonion.cli.commands import server_commands

        server_commands._save({"box": {"ssh": "u@h"}})
        server_commands._record("box", "ok")

        assert server_commands._load()["box"]["last_check"] == "ok"

    def test_a_failure_is_stamped_too(self, servers_file):
        from connectonion.cli.commands import server_commands

        server_commands._save({"box": {"ssh": "u@h"}})
        server_commands._record("box", "Ubuntu 24.04")

        entry = server_commands._load()["box"]
        assert entry["last_check"] == "Ubuntu 24.04"
        assert entry.get("last_check_at")


class TestTheAgeReachesTheTable:

    def _render(self, servers, monkeypatch):
        from connectonion.cli.commands import server_commands

        monkeypatch.setattr(server_commands, "_load", lambda: servers)
        monkeypatch.setattr(
            server_commands, "_fetch_billed_servers", lambda: None
        )
        from rich.console import Console

        recorder = Console(record=True, width=200)
        monkeypatch.setattr(server_commands, "console", recorder)
        server_commands.handle_server_list()
        return recorder.export_text()

    def test_a_recent_check_shows_its_age(self, monkeypatch):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        text = self._render(
            {"box": {"ssh": "u@h", "last_check": "ok", "last_check_at": now}},
            monkeypatch,
        )

        assert "ok" in text
        assert "ago" in text or "just now" in text

    def test_an_old_check_is_not_shown_as_current(self, monkeypatch):
        text = self._render(
            {"box": {"ssh": "u@h", "last_check": "ok",
                     "last_check_at": "2020-01-01T00:00:00+00:00"}},
            monkeypatch,
        )

        assert "ok" in text
        assert "ago" in text

    def test_a_pre_existing_entry_without_a_stamp_still_lists(self, monkeypatch):
        """servers.yaml written by an older version must keep working."""
        text = self._render({"box": {"ssh": "u@h", "last_check": "ok"}}, monkeypatch)

        assert "box" in text
        assert "ok" in text

    def test_never_checked_still_says_so(self, monkeypatch):
        text = self._render({"box": {"ssh": "u@h", "last_check": None}}, monkeypatch)

        assert "never checked" in text
