"""An agent told "message Alex at alex@example.com on Lark" or "post in the ops
group" can do it without first finding an oc_… id somewhere (#3000).

Before: `send` addressed every recipient as a chat id, so a person's own id
from the inbox (`sender`, on_…), an email, a phone number or a group's name
were all refused, and nothing could look a person up. Lark is faked at the
HTTP layer; nothing here reaches a real tenant.
"""

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.inbox import feishu as feishu_module

runner = CliRunner()


class Lark:
    """A fake open platform: records each call, answers by path."""

    def __init__(self, monkeypatch, answers):
        self.calls = []
        self.answers = answers
        monkeypatch.setattr(feishu_module.requests, "post", self.post)
        monkeypatch.setattr(feishu_module.requests, "get", self.get)

    def answer(self, url, body):
        self.calls.append((url, body))
        if "tenant_access_token" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"code": 0, "tenant_access_token": "t", "expire": 7200})
        for fragment, payload in self.answers.items():
            if fragment in url:
                payload = payload.pop(0) if isinstance(payload, list) else payload
                return SimpleNamespace(status_code=200, json=lambda: payload)
        raise AssertionError(f"unexpected call {url}")

    def post(self, url, json=None, headers=None, timeout=None):
        return self.answer(url, json)

    def get(self, url, headers=None, timeout=None):
        return self.answer(url, None)

    def sent_to(self):
        return [(url.split("receive_id_type=")[1], body["receive_id"])
                for url, body in self.calls if "/im/v1/messages?" in url]


SENT = {"/im/v1/messages?": {"code": 0, "data": {"message_id": "om_new", "chat_id": "oc_dm"}}}


@pytest.fixture(autouse=True)
def lark_app(monkeypatch, tmp_path):
    monkeypatch.setenv("LARK_APP_ID", "cli_a1b2c3d4e5f6")
    monkeypatch.setenv("LARK_APP_SECRET", "s3cret")
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))


def send(*args):
    return runner.invoke(app, ["lark", "send", *args])


def test_a_person_from_the_inbox_is_sent_to_by_their_own_id(monkeypatch):
    lark = Lark(monkeypatch, dict(SENT))
    result = send("on_7c6d", "Hello")
    assert result.exit_code == 0, result.output
    assert lark.sent_to() == [("union_id", "on_7c6d")]


def test_an_email_is_sent_to_directly_without_a_lookup_scope(monkeypatch):
    lark = Lark(monkeypatch, dict(SENT))
    result = send("alex@example.com", "Hello")
    assert result.exit_code == 0, result.output
    assert lark.sent_to() == [("email", "alex@example.com")]
    assert not any("batch_get_id" in url for url, _ in lark.calls)


def test_a_phone_number_is_looked_up_then_sent_to(monkeypatch):
    lark = Lark(monkeypatch, {
        "batch_get_id": {"code": 0, "data": {"user_list": [{"user_id": "on_sam", "mobile": "+61412345678"}]}},
        **SENT})
    result = send("+61 412 345 678", "Hello")
    assert result.exit_code == 0, result.output
    lookup = next(body for url, body in lark.calls if "batch_get_id" in url)
    assert lookup == {"mobiles": ["+61412345678"]}
    assert lark.sent_to() == [("union_id", "on_sam")]


def test_a_group_is_found_by_its_name_across_pages(monkeypatch):
    lark = Lark(monkeypatch, {
        "/im/v1/chats": [
            {"code": 0, "data": {"items": [{"chat_id": "oc_lobby", "name": "Lobby"}], "has_more": True, "page_token": "p2"}},
            {"code": 0, "data": {"items": [{"chat_id": "oc_ops", "name": "Ops Room"}], "has_more": False}}],
        **SENT})
    result = send("ops room", "Deploy done")
    assert result.exit_code == 0, result.output
    assert lark.sent_to() == [("chat_id", "oc_ops")]


def test_a_name_nobody_has_says_where_to_look(monkeypatch):
    Lark(monkeypatch, {"/im/v1/chats": {"code": 0, "data": {"items": [], "has_more": False}}, **SENT})
    result = send("Nobody", "Hello")
    assert result.exit_code == 1
    assert "co lark contacts ls" in result.output and "co lark groups" in result.output


def test_a_missing_scope_names_it_and_prints_the_link_that_grants_it(monkeypatch):
    Lark(monkeypatch, {"batch_get_id": {"code": 99991672, "msg": "Access denied. One of the following scopes is required"}})
    result = runner.invoke(app, ["lark", "lookup", "+61412345678"])
    assert result.exit_code == 1
    assert "contact:user.id:readonly" in result.output
    assert "https://open.larksuite.com/page/launcher?clientID=cli_a1b2c3d4e5f6" in result.output
    assert "Next:" in result.output


def test_lookup_prints_the_id_send_takes(monkeypatch):
    Lark(monkeypatch, {"batch_get_id": {"code": 0, "data": {"user_list": [{"user_id": "on_alex", "email": "alex@example.com"}]}}})
    result = runner.invoke(app, ["lark", "lookup", "alex@example.com"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "on_alex"


def test_lookup_of_someone_the_bot_cannot_see_says_why(monkeypatch):
    Lark(monkeypatch, {"batch_get_id": {"code": 0, "data": {"user_list": [{"email": "ghost@example.com"}]}}})
    result = runner.invoke(app, ["lark", "lookup", "ghost@example.com"])
    assert result.exit_code == 1
    assert "contact range" in result.output


def test_groups_lists_id_and_name(monkeypatch):
    Lark(monkeypatch, {"/im/v1/chats": {"code": 0, "data": {"items": [
        {"chat_id": "oc_ops", "name": "Ops Room"}, {"chat_id": "oc_ext", "name": "Partners", "external": True}],
        "has_more": False}}})
    result = runner.invoke(app, ["lark", "groups"])
    assert result.exit_code == 0, result.output
    assert "oc_ops\tOps Room" in result.output
    assert "oc_ext\tPartners\texternal" in result.output


def test_a_saved_contact_is_sent_to_by_name(monkeypatch, tmp_path):
    lark = Lark(monkeypatch, {
        "batch_get_id": {"code": 0, "data": {"user_list": [{"user_id": "on_sam", "mobile": "+61412345678"}]}},
        **SENT})
    added = runner.invoke(app, ["lark", "contacts", "add", "Sam Lee", "+61412345678"])
    assert added.exit_code == 0, added.output
    assert "Sam Lee\ton_sam" in added.output
    saved = json.loads((tmp_path / "inbox" / "lark" / "contacts.json").read_text())
    assert saved == {"Sam Lee": "on_sam"}

    result = send("sam lee", "Hello")
    assert result.exit_code == 0, result.output
    assert lark.sent_to() == [("union_id", "on_sam")]
    assert sum("batch_get_id" in url for url, _ in lark.calls) == 1, "a phone is looked up once, when saved"

    listed = runner.invoke(app, ["lark", "contacts", "ls"])
    assert "Sam Lee\ton_sam" in listed.output
    assert runner.invoke(app, ["lark", "contacts", "rm", "Sam Lee"]).exit_code == 0
    assert json.loads((tmp_path / "inbox" / "lark" / "contacts.json").read_text()) == {}


def test_a_contact_saved_by_email_needs_no_lookup(monkeypatch):
    lark = Lark(monkeypatch, dict(SENT))
    assert runner.invoke(app, ["lark", "contacts", "add", "Alex", "alex@example.com"]).exit_code == 0
    assert send("Alex", "Hello").exit_code == 0
    assert lark.sent_to() == [("email", "alex@example.com")]
    assert not any("batch_get_id" in url for url, _ in lark.calls)


def test_removing_a_name_never_saved_names_the_listing(monkeypatch):
    result = runner.invoke(app, ["lark", "contacts", "rm", "Nobody"])
    assert result.exit_code == 1
    assert "co lark contacts ls" in result.output


def test_a_person_outside_availability_is_told_where_to_add_them(monkeypatch):
    Lark(monkeypatch, {"/im/v1/messages?": {"code": 230013, "msg": "Bot has NO availability to this user."}})
    result = send("alex@example.com", "Hello")
    assert result.exit_code == 1
    assert "availability" in result.output and "Version Management" in result.output


def test_feishu_has_the_same_verbs(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_f1e2d3c4b5a6")
    monkeypatch.setenv("FEISHU_APP_SECRET", "s3cret")
    lark = Lark(monkeypatch, dict(SENT))
    result = runner.invoke(app, ["feishu", "send", "ou_alex", "Hello"])
    assert result.exit_code == 0, result.output
    assert lark.sent_to() == [("open_id", "ou_alex")]
    assert lark.calls[-1][0].startswith("https://open.feishu.cn/")


def test_lark_send_help_says_pictures_are_refused():
    result = runner.invoke(app, ["lark", "send", "--help"], env={"COLUMNS": "200"})
    assert "Not on Lark yet" in result.output
    assert "alex@example.com" in result.output
