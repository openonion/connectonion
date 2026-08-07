"""`co server ls` puts a requirement's name in the LAST CHECK column.

Seen on a real listing:

    NAME         TARGET            LAST CHECK      BILLING
    nw-map       co@35.189.30.72   ok 14h ago      until 2027-08-05
    nw-runner    claude-runner     Ubuntu 24.04    not ours

That machine is Ubuntu **22.04** (`#63~22.04.1-Ubuntu`). The cell is the name of
the requirement that failed — `_record(name, failures[0][0])` — and every one of
those names is a bare noun:

    Ubuntu · Ubuntu 24.04 · python3 · python 3.10+ · systemd
    permission to manage units

so in a column headed LAST CHECK they read as facts about the server rather than
as what went wrong. "Ubuntu 24.04" against a 22.04 box states the opposite of the
truth. It is red rather than green, which is the only thing telling the reader it
is bad news — and a reader who greps or pipes the output loses even that.

This is the table `co server check` writes for `co deploy --to` to be consulted
against, so the cell has to say the verdict. `needs <requirement>` makes all of
them read correctly, and matches the sentence already printed under a failed
check: "co deploy --to <name> needs all of these".

The time half of this column is owned by test_a_cached_check_says_when.py.
"""

import pytest

from connectonion.cli.commands import server_commands as sc


class TestAFailedRequirementReadsAsOne:

    @pytest.mark.parametrize("requirement", [
        "Ubuntu",
        "Ubuntu 24.04",
        "python3",
        "python 3.10+",
        "systemd",
        "permission to manage units",
    ])
    def test_the_stored_outcome_says_needs(self, tmp_path, monkeypatch, requirement):
        monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml", raising=False)
        sc._save({"box": {"ssh": "u@h", "last_check": None}})

        sc._record_requirement_failure("box", requirement)

        assert sc._load()["box"]["last_check"] == f"needs {requirement}"

    def test_it_does_not_state_a_bare_version(self, tmp_path, monkeypatch):
        """The specific reading that was wrong: a 22.04 box labelled 'Ubuntu 24.04'."""
        monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml", raising=False)
        sc._save({"box": {"ssh": "u@h", "last_check": None}})

        sc._record_requirement_failure("box", "Ubuntu 24.04")

        assert sc._load()["box"]["last_check"] != "Ubuntu 24.04"


class TestTheOtherOutcomesAreUnchanged:
    """`ok` is what the renderer greens, and `unreachable` already reads as a
    verdict. Neither should acquire a prefix."""

    @pytest.mark.parametrize("outcome", ["ok", "unreachable"])
    def test_they_are_stored_verbatim(self, tmp_path, monkeypatch, outcome):
        monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml", raising=False)
        sc._save({"box": {"ssh": "u@h", "last_check": None}})

        sc._record("box", outcome)

        assert sc._load()["box"]["last_check"] == outcome

    def test_ok_still_renders_green(self, tmp_path, monkeypatch, capsys):
        """Guard the renderer's `last == "ok"` branch against a prefix landing
        there — a green check turning red would be the worse mistake."""
        monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml", raising=False)
        sc._save({"box": {"ssh": "u@h", "last_check": "ok",
                          "last_check_at": "2026-08-07T00:00:00+00:00"}})

        sc.handle_server_list()  # the real entry point, not a name I assumed

        assert "ok" in capsys.readouterr().out
