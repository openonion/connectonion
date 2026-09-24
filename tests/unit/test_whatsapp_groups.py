"""Start a WhatsApp group for a new client, or add people to one (#1617).

The report has to be per person. WhatsApp calls the group created while
quietly leaving out a number whose privacy settings forbid being added, and a
caller that trusted the overall success told everyone the client was in a group
the client was not in.
"""

from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import whatsapp as wa

# The optional WhatsApp extra is not installed in CI, so these stand-ins carry
# the SDK's field names; test_the_fields_used_are_the_sdks checks the names
# against the real types wherever neonize is installed.


def jid(user, server="s.whatsapp.net"):
    return SimpleNamespace(User=user, Server=server)


def participant(j, error=0, super_admin=False):
    return SimpleNamespace(JID=j, PhoneNumber=j, Error=error, IsSuperAdmin=super_admin)


@pytest.fixture(autouse=True)
def no_sdk_needed(monkeypatch):
    # Importing neonize starts its runtime thread, and CI does not install it.
    monkeypatch.setattr(wa, "_add_participants", lambda: "ADD")
    monkeypatch.setattr(wa, "_build_jid", lambda chat: jid(*chat.split("@")))


class FakeClient:
    """neonize's client, answering in the shape of the SDK's types."""

    def __init__(self, on_whatsapp, errors):
        self.on_whatsapp = on_whatsapp          # numbers that have an account
        self.errors = errors                    # number -> WhatsApp's error code
        self.created = None

    def is_on_whatsapp(self, *numbers):
        return [SimpleNamespace(Query=n, IsIn=n.lstrip("+") in self.on_whatsapp,
                                JID=jid(n.lstrip("+"))) for n in numbers]

    def _participants(self, jids):
        return [participant(j, self.errors.get(j.User, 0)) for j in jids]

    def create_group(self, subject, jids):
        self.created = (subject, [j.User for j in jids])
        me = participant(jid("61400000001"), super_admin=True)
        return SimpleNamespace(JID=jid("120363", "g.us"),
                               Participants=[me, *self._participants(jids)])

    def update_group_participants(self, group, jids, action):
        return self._participants(jids)

    def get_group_invite_link(self, group):
        return "https://chat.whatsapp.com/INVITE"


def provider_with(client):
    box = wa.WhatsApp.__new__(wa.WhatsApp)
    box._client = client
    return box


def outcomes(result):
    return {p["phone"]: p["outcome"] for p in result["participants"]}


def test_each_person_gets_their_own_outcome():
    client = FakeClient(on_whatsapp={"61411111111", "61422222222"},
                        errors={"61422222222": 403})

    result = provider_with(client)._group_now(
        ["+61 411 111 111", "61422222222", "61433333333"], subject="Acme")

    assert result["chat"] == "120363@g.us"
    assert outcomes(result) == {
        "61411111111": "added",
        "61422222222": wa._participant_outcome(403),
        "61433333333": "no WhatsApp account",
    }
    # Someone who can only be invited gets the link to send them.
    assert result["invite_link"] == "https://chat.whatsapp.com/INVITE"
    # A number with no account is never sent to WhatsApp.
    assert client.created == ("Acme", ["61411111111", "61422222222"])


def test_a_number_whatsapp_did_not_list_is_not_reported_as_added():
    class Silent(FakeClient):
        def update_group_participants(self, group, jids, action):
            return []

    result = provider_with(Silent({"61411111111"}, {}))._group_now(
        ["61411111111"], chat="120363@g.us")

    assert outcomes(result)["61411111111"].startswith("not confirmed")
    assert "invite_link" not in result


def test_the_fields_used_are_the_sdks():
    """The stand-ins above are only honest if neonize's types have these fields.

    In a subprocess: importing neonize starts its runtime thread, which this
    suite rightly refuses to let a test leave behind.
    """
    import importlib.util
    import subprocess
    import sys

    if importlib.util.find_spec("neonize") is None:
        pytest.skip("the whatsapp extra is not installed")
    check = (
        "from neonize.proto.Neonize_pb2 import GroupParticipant, GroupInfo, IsOnWhatsAppResponse\n"
        "from neonize.utils.enum import ParticipantChange\n"
        "names = lambda t: {f.name for f in t.DESCRIPTOR.fields}\n"
        "assert {'JID', 'PhoneNumber', 'Error', 'IsSuperAdmin'} <= names(GroupParticipant)\n"
        "assert {'JID', 'Participants'} <= names(GroupInfo)\n"
        "assert {'Query', 'IsIn', 'JID'} <= names(IsOnWhatsAppResponse)\n"
        "assert ParticipantChange.ADD\n"
    )
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


class FakeProvider:
    def __init__(self, result):
        self.result = result

    def missing(self):
        return []

    def create_group(self, subject, phones):
        return self.result

    def add_to_group(self, chat, phones):
        return self.result


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))

    def go(result, **kwargs):
        monkeypatch.setattr(listen_commands, "provider", lambda name: FakeProvider(result))
        try:
            listen_commands.handle_group("whatsapp", ["61411111111", "61422222222"], **kwargs)
        except SystemExit as exit_:
            return exit_.code
        return 0

    return go


def test_everyone_in_exits_0_and_prints_the_chat_first(run, capsys):
    code = run({"chat": "120363@g.us", "participants": [
        {"phone": "61411111111", "outcome": "added"},
        {"phone": "61422222222", "outcome": "already in the group"}]}, subject="Acme")

    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert out[0] == "120363@g.us"
    assert "✓ +61411111111  added" in out[1]


def test_anyone_left_out_exits_1_with_the_invite_link(run, capsys):
    code = run({"chat": "120363@g.us", "invite_link": "https://chat.whatsapp.com/X",
                "participants": [
                    {"phone": "61411111111", "outcome": "added"},
                    {"phone": "61422222222", "outcome": wa._participant_outcome(403)}]},
               chat="120363@g.us")

    out = capsys.readouterr().out
    assert code == 1
    assert "✗ +61422222222  not added: their privacy settings" in out
    assert "invite_link: https://chat.whatsapp.com/X" in out
