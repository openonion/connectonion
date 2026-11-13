"""Check a new person's number, save them under a name, send to that name (#2964).

An agent handed a new client's mobile could not tell whether the number had
WhatsApp without writing to it, could not see who it belonged to, and could
only send by building `<digits>@s.whatsapp.net` by hand. Everything here runs
against a fake client in the SDK's shape; nothing talks to WhatsApp.
"""

import json
from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands, whatsapp_commands
from connectonion.inbox import whatsapp as wa
from connectonion.inbox import whatsapp_contacts as contacts
from connectonion.inbox.store import Inbox, Message

ALEX = "61412345678"        # fictional, on WhatsApp
NOBODY = "61498765432"      # fictional, no account
ALEX_LID = "209876543210987"


@pytest.fixture(autouse=True)
def inbox_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    monkeypatch.setattr(wa, "_build_jid", lambda chat: jid(*chat.split("@")))


def jid(user, server="s.whatsapp.net"):
    return SimpleNamespace(User=user, Server=server)


class FakeClient:
    """neonize's client: who is on WhatsApp, what it says about them, what was sent."""

    def __init__(self):
        self.sent = []
        self.contact = self   # neonize keeps get_contact on client.contact

    def is_on_whatsapp(self, *numbers):
        return [SimpleNamespace(Query=n, IsIn=n == f"+{ALEX}", JID=jid(n.lstrip("+")),
                                VerifiedName=SimpleNamespace(Details=SimpleNamespace(verifiedName="")))
                for n in numbers]

    def get_user_info(self, *jids):
        return [SimpleNamespace(JID=j, UserInfo=SimpleNamespace(Status="Building things", PictureID="1712"))
                for j in jids]

    def get_contact(self, user):
        return SimpleNamespace(Found=True, FullName="", FirstName="", PushName="Alex E.", BusinessName="")

    def send_message(self, to, body):
        self.sent.append((to.User, body))
        return SimpleNamespace(ID="3EB0AA")


def listener():
    box = wa.WhatsApp()
    box._client = FakeClient()
    return box


# ---- numbers ---------------------------------------------------------------

def test_a_number_with_its_country_code_is_its_digits():
    assert contacts.phone_digits("+61 412 345 678") == ALEX
    assert contacts.phone_digits("0061412345678") == ALEX


def test_a_local_number_needs_a_country_rather_than_reaching_nobody():
    with pytest.raises(ValueError, match="--country"):
        contacts.phone_digits("0412 345 678")
    assert contacts.phone_digits("0412 345 678", "au") == ALEX
    # Italy keeps its leading 0 after the country code; stripping it, as a
    # hand-written rule would, names a different number.
    assert contacts.phone_digits("06 1234 5678", "IT") == "390612345678"


# ---- lookup ----------------------------------------------------------------

def test_lookup_reports_who_a_number_is_without_sending_them_anything():
    box = listener()

    found = box._perform({"kind": "lookup", "phones": [ALEX, NOBODY]})["results"]

    assert found[0] == {"phone": f"+{ALEX}", "on_whatsapp": True, "jid": f"{ALEX}@s.whatsapp.net",
                        "name": "Alex E.", "business": "", "about": "Building things",
                        "has_photo": True, "saved_as": ""}
    assert found[1] == {"phone": f"+{NOBODY}", "on_whatsapp": False}
    assert box._client.sent == []


class FakeProvider:
    via_listener = False

    def __init__(self, results):
        self.results, self.asked = results, None

    def missing(self):
        return []

    def lookup(self, phones):
        self.asked = phones
        return self.results


def test_a_number_not_on_whatsapp_is_a_result_and_exit_4(monkeypatch, capsys):
    fake = FakeProvider([{"phone": f"+{ALEX}", "on_whatsapp": True, "jid": f"{ALEX}@s.whatsapp.net"},
                         {"phone": f"+{NOBODY}", "on_whatsapp": False}])
    monkeypatch.setattr(listen_commands, "provider", lambda name: fake)

    with pytest.raises(SystemExit) as exit_:
        whatsapp_commands.handle_lookup(["0412345678", "+61498765432"], country="AU")

    assert exit_.value.code == whatsapp_commands.EXIT_NOT_ON_WHATSAPP == 4
    assert fake.asked == [ALEX, NOBODY]
    out = capsys.readouterr()
    assert [json.loads(line)["on_whatsapp"] for line in out.out.splitlines()] == [True, False]
    assert "Traceback" not in out.err and f"not on WhatsApp: +{NOBODY}" in out.err


def test_lookup_refuses_a_local_number_before_asking_anyone(monkeypatch, capsys):
    fake = FakeProvider([])
    monkeypatch.setattr(listen_commands, "provider", lambda name: fake)

    with pytest.raises(SystemExit) as exit_:
        whatsapp_commands.handle_lookup(["0412345678"])

    assert exit_.value.code == 2
    assert fake.asked is None
    assert "--country" in capsys.readouterr().err


# ---- contacts --------------------------------------------------------------

def test_contacts_add_ls_rm(capsys):
    whatsapp_commands.handle_contacts_add("0412 345 678", "Alex Example", note="Acme", country="AU")
    whatsapp_commands.handle_contacts_ls()
    out = capsys.readouterr().out
    assert f"{ALEX}@s.whatsapp.net\tAlex Example\n" in out
    assert f"{ALEX}@s.whatsapp.net\tAlex Example\tAcme\n" in out

    whatsapp_commands.handle_contacts_rm("alex example")
    assert contacts.read_contacts() == {}


def test_one_name_cannot_mean_two_people(capsys):
    contacts.add_contact(f"+{ALEX}", "Alex Example")

    with pytest.raises(SystemExit) as exit_:
        whatsapp_commands.handle_contacts_add(f"+{NOBODY}", "alex example")

    assert exit_.value.code == 2
    assert "already names" in capsys.readouterr().err


def test_send_takes_a_name_a_number_or_a_jid():
    contacts.add_contact(f"{ALEX}@s.whatsapp.net", "Alex Example")

    assert contacts.resolve_chat("Alex Example") == (f"{ALEX}@s.whatsapp.net", "")
    assert contacts.resolve_chat(f"+{NOBODY}") == (f"{NOBODY}@s.whatsapp.net", NOBODY)
    assert contacts.resolve_chat("1203630000000@g.us") == ("1203630000000@g.us", "")
    with pytest.raises(ValueError, match="contacts ls"):
        contacts.resolve_chat("Sam Nobody")


def test_a_send_to_a_number_without_whatsapp_sends_nothing():
    box = listener()

    with pytest.raises(RuntimeError, match="not on WhatsApp, so nothing was sent"):
        box._perform({"chat": f"{NOBODY}@s.whatsapp.net", "text": "hi", "phone": NOBODY})
    box._perform({"chat": f"{ALEX}@s.whatsapp.net", "text": "hi", "phone": ALEX})

    assert box._client.sent == [(ALEX, "hi")]


def test_send_to_a_saved_name_goes_to_its_jid(monkeypatch, capsys):
    contacts.add_contact(f"+{ALEX}", "Alex Example")
    calls = []

    class Sending(wa.WhatsApp):
        def missing(self):
            return []

        def _queue(self, payload):
            calls.append(payload)
            return "3EB0AA"

    monkeypatch.setattr(listen_commands, "provider", lambda name: Sending())
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 1)

    listen_commands.handle_send("whatsapp", "Alex Example", "Hello", plain=True)

    assert calls[0]["chat"] == f"{ALEX}@s.whatsapp.net" and calls[0]["phone"] == ALEX
    assert json.loads(Inbox("whatsapp").sent.read_text())["chat"] == f"{ALEX}@s.whatsapp.net"
    assert capsys.readouterr().out == "3EB0AA\n"


# ---- names where the inbox shows them -------------------------------------

def lid_map(path, pairs):
    import sqlite3

    db = sqlite3.connect(path)
    db.execute("create table whatsmeow_lid_map (lid text, pn text)")
    db.execute("create table whatsmeow_contacts (our_jid text, their_jid text, first_name text, "
               "full_name text, push_name text, business_name text, redacted_phone text)")
    db.executemany("insert into whatsmeow_lid_map values (?, ?)", pairs)
    db.commit()
    db.close()


def test_the_listener_names_a_sender_by_the_saved_name_even_as_a_lid(tmp_path):
    lid_map(tmp_path / "session.db", [(ALEX_LID, ALEX)])
    contacts.add_contact(f"+{ALEX}", "Alex Example")

    assert wa.WhatsApp().name_of(f"{ALEX_LID}@lid") == "Alex Example"
    assert wa.WhatsApp().name_of(f"{ALEX}:12@s.whatsapp.net") == "Alex Example"


def test_chats_ls_and_log_show_the_saved_name(capsys):
    box = Inbox("whatsapp")
    box.deliver(Message(id="3EB0C1", chat=f"{ALEX}@s.whatsapp.net", sender=f"{ALEX}@s.whatsapp.net",
                        sender_name="Alex E.", text="hello", at="2026-11-12T01:00:00Z", mentioned=True))
    contacts.add_contact(f"+{ALEX}", "Alex Example")

    listen_commands.handle_chats("whatsapp")
    listen_commands.handle_ls("whatsapp")
    listen_commands.handle_log("whatsapp")
    listen_commands.handle_log("whatsapp", sender="Alex Example")

    out = capsys.readouterr().out
    assert "\tAlex Example\thello" in out
    assert f"3EB0C1\t{ALEX}@s.whatsapp.net\tAlex Example\thello" in out
    logged = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert [r["sender_name"] for r in logged] == ["Alex Example", "Alex Example"]


def test_the_fields_used_are_the_sdks():
    """The fake above is honest only if neonize's types carry these fields. In a
    subprocess, because importing neonize starts a runtime thread."""
    import importlib.util
    import subprocess
    import sys

    if importlib.util.find_spec("neonize") is None:
        pytest.skip("the whatsapp extra is not installed")
    check = (
        "from neonize.proto.Neonize_pb2 import IsOnWhatsAppResponse, UserInfo, ContactInfo, "
        "GetUserInfoSingleReturnFunction, VerifiedName\n"
        "names = lambda t: {f.name for f in t.DESCRIPTOR.fields}\n"
        "assert {'Query', 'IsIn', 'JID', 'VerifiedName'} <= names(IsOnWhatsAppResponse)\n"
        "assert {'JID', 'UserInfo'} <= names(GetUserInfoSingleReturnFunction)\n"
        "assert {'Status', 'PictureID'} <= names(UserInfo)\n"
        "assert {'FullName', 'FirstName', 'PushName', 'BusinessName'} <= names(ContactInfo)\n"
        "assert 'verifiedName' in names(VerifiedName.DESCRIPTOR.fields_by_name['Details'].message_type._concrete_class)\n"
        "from neonize.client import NewClient, ContactStore\n"
        "assert hasattr(NewClient, 'is_on_whatsapp') and hasattr(NewClient, 'get_user_info')\n"
        "assert hasattr(ContactStore, 'get_contact')\n"
        "import inspect, neonize.client as c\n"
        "assert 'self.contact = ContactStore(' in inspect.getsource(c.NewClient.__init__)\n"
    )
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
