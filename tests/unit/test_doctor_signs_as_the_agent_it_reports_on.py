"""`co doctor` picks its own key to sign the backend probe with.

The keys row and the connectivity check each work the resolution out
separately, in the same file:

    local_keys = project_co_dir() / "keys" / "agent.key"
    global_keys = Path.home() / ".co" / "keys" / "agent.key"
    ...
    if local_keys.exists() or global_keys.exists():
        co_dir = project_co_dir() if local_keys.exists() else Path.home() / ".co"
        addr_data = address.load(co_dir)

Two copies of one rule, in the command an operator runs *to find out what is
wrong*. They agree today, and nothing makes them agree — the identity the panel
names and the identity it authenticates as are decided independently, so a
change to one is a doctor that reports on an account that is not the one in
question.

Both ask `project_identity` now: its own key, else the machine's. Same answer,
one place.
"""

from pathlib import Path

import pytest

from connectonion import address


@pytest.fixture
def machine(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    keys = address.generate()
    address.save(keys, home / ".co")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home, keys


class TestOneRuleNotTwo:

    def test_the_file_has_no_second_copy(self):
        import inspect

        from connectonion.cli.commands import doctor_commands

        source = inspect.getsource(doctor_commands)

        assert 'co_dir = project_co_dir() if local_keys.exists()' not in source, (
            "the connectivity check still resolves the identity on its own"
        )

    def test_both_paths_use_the_resolver(self):
        import inspect

        from connectonion.cli.commands import doctor_commands

        source = inspect.getsource(doctor_commands)

        assert source.count("project_identity") >= 1


class TestTheRowAndTheAuthAgree:
    """The keys row names a *file*, which is a different question from *which
    identity* — but the two answers have to match, or doctor names one key and
    authenticates with another. Pinned rather than merged: which file holds it
    is worth printing, and the row cannot say that from an identity alone."""

    def test_the_named_file_holds_the_identity_it_authenticates_as(self, machine, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.project import project_identity

        home, machine_keys = machine
        project = tmp_path / "keyless"
        (project / ".co").mkdir(parents=True)
        monkeypatch.chdir(project)

        named = home / ".co" / "keys" / "agent.key"
        assert named.exists()
        assert address.load(home / ".co")["address"] == project_identity()["address"]

    def test_a_project_key_is_named_and_used(self, machine, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.project import project_identity

        project = tmp_path / "haskey"
        (project / ".co").mkdir(parents=True)
        own = address.generate()
        address.save(own, project / ".co")
        monkeypatch.chdir(project)

        assert (project / ".co" / "keys" / "agent.key").exists()
        assert project_identity()["address"] == own["address"]


class TestItReportsTheIdentityItWouldUse:

    def test_a_keyless_project_names_the_machine_key(self, machine, tmp_path, monkeypatch, capsys):
        """Unchanged behaviour, pinned: the machine key is what a keyless
        project uses, and what doctor should name."""
        from connectonion.cli.commands import doctor_commands

        home, _ = machine
        project = tmp_path / "keyless"
        (project / ".co").mkdir(parents=True)
        monkeypatch.chdir(project)
        monkeypatch.setenv("COLUMNS", "300")

        doctor_commands.handle_doctor()

        assert "agent.key" in capsys.readouterr().out
