"""Every project on this machine answers to the same address.

Confirmed on `main`, in a directory `co init --yes` had just created:

    $ ls .co/keys/
    (nothing — no key of its own)
    $ co keys
    Address   0x10e68f6dff39ab1c50cc48ea1c74e7fd6ce7269aa6e8123829b…
    Source    ~/.co (global)

That is #642: `oo` on this laptop and `naturewill` on the deployed box announced
the same address, because a project with no key of its own inherits the global
one. #688 made the collision visible; this is the half that stops it happening.

Aaron's call, and it is better than minting a random keypair per project, which
is what I had proposed: **derive it**. `derive.py` already exports what is
needed, and `server_commands.py` already uses it:

    signing_key = SigningKey(derive_path(seed, slip13_path(identity_uri(name))))

`slip13_path`'s docstring says why that shape was chosen:

    The name *is* the path, which is what lets `co keys` print an agent's
    address before anything is deployed, and makes the same name always return
    the same key. `index` is the rotation counter.

So a project's identity costs nothing to back up — the twelve words already
cover it — is recoverable from the phrase and the project name alone, and is
knowable before the project has ever run. A random per-project key had none of
those properties.

BEHAVIOUR CHANGE: a 1.5.x project with no key of its own moves from the global
address to a derived one. That is the point of the issue, and it means whatever
was whitelisted or paid to the old address does not follow. Inheriting stays
for a project that cannot derive — no phrase on the machine — because an agent
has to have an address.
"""

from pathlib import Path

import pytest

from connectonion import address
from connectonion.network.host.server import resolve_agent_identity


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A global ~/.co holding a recovery phrase, and two projects with no keys."""
    home = tmp_path / "home"
    home_co = home / ".co"
    (home_co / "keys").mkdir(parents=True)
    identity = address.generate()
    address.save(identity, home_co)
    (home_co / "keys" / "recovery.txt").write_text(identity["seed_phrase"],
                                                   encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    def project(name):
        """Idempotent: the same name is the same directory, so a test can ask
        for it twice and compare."""
        co = tmp_path / name / ".co"
        co.mkdir(parents=True, exist_ok=True)
        return co

    return home_co, identity, project


class TestTwoProjectsAreTwoAgents:

    def test_they_do_not_share_an_address(self, machine):
        _, _, project = machine

        first = resolve_agent_identity(project("oo"))
        second = resolve_agent_identity(project("naturewill"))

        assert first["address"] != second["address"]

    def test_neither_is_the_global_one(self, machine):
        home_co, global_identity, project = machine

        derived = resolve_agent_identity(project("oo"))

        assert derived["address"] != global_identity["address"]

    def test_the_same_project_is_the_same_agent_every_time(self, machine):
        _, _, project = machine

        first = resolve_agent_identity(project("oo"))
        again = resolve_agent_identity(project("oo"))

        assert first["address"] == again["address"]

    def test_it_says_it_was_derived(self, machine):
        """A flag, not a marker in `source`. `source` means "the directory this
        key belongs to" and #688 writes its served-by record there — overloading
        it made claim_identity silently do nothing."""
        _, _, project = machine
        resolved = resolve_agent_identity(project("oo"))

        assert resolved["derived"] is True
        assert Path(resolved["source"]).name == ".co"


class TestItIsTheDocumentedDerivation:
    """Not a new scheme: the one `identity_uri` and `slip13_path` already define."""

    def test_it_matches_deriving_by_hand(self, machine):
        from mnemonic import Mnemonic
        from nacl.signing import SigningKey

        from connectonion.derive import derive_path, identity_uri, slip13_path

        _, global_identity, project = machine
        seed = Mnemonic("english").to_seed(global_identity["seed_phrase"])
        expected = SigningKey(derive_path(seed, slip13_path(identity_uri("oo"))))

        resolved = resolve_agent_identity(project("oo"))

        assert resolved["address"] == "0x" + bytes(expected.verify_key).hex()

    def test_the_name_is_the_directory(self, machine):
        """`co deploy` and the relay already key on the project directory's
        name, so the identity keys on the same thing."""
        from mnemonic import Mnemonic
        from nacl.signing import SigningKey

        from connectonion.derive import derive_path, identity_uri, slip13_path

        _, global_identity, project = machine
        seed = Mnemonic("english").to_seed(global_identity["seed_phrase"])

        for name in ("alpha", "beta"):
            expected = SigningKey(derive_path(seed, slip13_path(identity_uri(name))))
            assert resolve_agent_identity(project(name))["address"] == \
                "0x" + bytes(expected.verify_key).hex()


class TestWhatMustNotChange:

    def test_a_project_with_its_own_key_keeps_it(self, machine):
        _, _, project = machine
        co = project("has-its-own")
        mine = address.generate()
        address.save(mine, co)

        assert resolve_agent_identity(co)["address"] == mine["address"]

    def test_no_phrase_still_inherits(self, tmp_path, monkeypatch):
        """Nothing to derive from. Inheriting beats inventing — that is what
        resolve_agent_identity was fixed to do, and it stays."""
        home = tmp_path / "home"
        home_co = home / ".co"
        home_co.mkdir(parents=True)
        global_identity = address.generate()
        address.save(global_identity, home_co)
        (home_co / "keys" / "recovery.txt").unlink(missing_ok=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        co = tmp_path / "p" / ".co"
        co.mkdir(parents=True)

        assert resolve_agent_identity(co)["address"] == global_identity["address"]

    def test_nothing_at_all_still_generates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty"))
        co = tmp_path / "p" / ".co"
        co.mkdir(parents=True)

        assert resolve_agent_identity(co)["address"].startswith("0x")


class TestEveryPlaceThatReportsTheIdentityAgrees:
    """The point of one resolver is that nothing gets to keep its own copy.

    `co doctor` had one. It printed

        Keys  ✓ /Users/changxing/.co/keys/agent.key

    for a project that derives — naming a file that is not this agent's
    identity, which is #659 in the one command an operator runs *to find out
    what is wrong*. Found by running it, after I had written "all four callers"
    in the PR: doctor was a fifth.
    """

    def test_doctor_does_not_name_the_global_key_for_a_derived_project(self, machine, capsys, monkeypatch):
        """Wide, because rich wraps a long path across table cells and the
        exact string then is not in the output — so this passed for the wrong
        reason first time, the same way #681's did."""
        from connectonion.cli.commands import doctor_commands

        home_co, _, project = machine
        co = project("oo")
        monkeypatch.chdir(co.parent)
        monkeypatch.setenv("COLUMNS", "300")

        doctor_commands.handle_doctor()
        out = capsys.readouterr().out

        assert str(home_co / "keys" / "agent.key") not in out, out[:800]

    def test_doctor_says_it_is_derived(self, machine, capsys, monkeypatch):
        from connectonion.cli.commands import doctor_commands

        _, _, project = machine
        co = project("oo")
        monkeypatch.chdir(co.parent)

        doctor_commands.handle_doctor()

        assert "derived" in capsys.readouterr().out.lower()

    def test_a_project_with_its_own_key_still_names_the_file(self, machine, capsys, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands import doctor_commands

        _, _, project = machine
        co = project("has-its-own")
        address.save(address.generate(), co)
        monkeypatch.chdir(co.parent)

        doctor_commands.handle_doctor()

        assert "agent.key" in capsys.readouterr().out


class TestItIsTheNameDeployUses:
    """`co deploy` has derived the agent's identity since #396, from
    `host.yaml`'s name:

        agent_identity = derived_agent_identity(agent)   # agent = config["name"]

    Deriving locally from the *directory* instead would give the same project
    two addresses — one when it runs here, another when it is deployed — for any
    operator who renamed either. `co init` writes the directory name into
    host.yaml, so they agree until someone edits one, which is exactly the kind
    of divergence nobody notices until an address stops matching.
    """

    def test_host_yaml_name_wins_over_the_directory(self, machine):
        _, global_identity, project = machine
        co = project("on-disk")
        (co / "host.yaml").write_text("name: the-real-name\n", encoding="utf-8")

        from mnemonic import Mnemonic
        from nacl.signing import SigningKey

        from connectonion.derive import derive_path, identity_uri, slip13_path

        seed = Mnemonic("english").to_seed(global_identity["seed_phrase"])
        expected = SigningKey(derive_path(seed, slip13_path(identity_uri("the-real-name"))))

        assert resolve_agent_identity(co)["address"] == \
            "0x" + bytes(expected.verify_key).hex()

    def test_it_matches_what_deploy_would_ship(self, machine):
        from connectonion.cli.commands.server_commands import derived_agent_identity

        _, _, project = machine
        co = project("shipme")
        (co / "host.yaml").write_text("name: shipme\n", encoding="utf-8")

        assert resolve_agent_identity(co)["address"] == \
            derived_agent_identity("shipme")["address"]

    def test_the_directory_is_the_fallback(self, machine):
        """No host.yaml, or no name in it — the directory is still the answer."""
        _, _, project = machine
        co = project("nameless")

        assert resolve_agent_identity(co)["address"] == \
            resolve_agent_identity(project("nameless"))["address"]

    def test_a_host_yaml_without_a_name_falls_back(self, machine):
        _, _, project = machine
        co = project("no-name-key")
        (co / "host.yaml").write_text("port: 8000\n", encoding="utf-8")

        assert resolve_agent_identity(co)["derived"] is True
