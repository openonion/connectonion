"""`co wechat contacts` answers "how many WeChat friends / find a friend" (#3355).

WeChat's contact table mixes friends (local_type 1), people only seen in a shared group (3), groups and
official accounts. An agent asked about the owner's friends had no command; now it counts and finds them.
"""
import json
import sqlite3
from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.commands import wechat_commands as wc
from connectonion.cli.main import app
from connectonion.useful_tools import wechat as engine

runner = CliRunner()


def _contact_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, alias TEXT, local_type INTEGER)")
    conn.executemany("INSERT INTO contact VALUES (?,?,?,?,?)", [
        ("wxid_owner", "", "Me", "", 1),
        ("wxid_mia", "Mia Chen", "mia", "miachen", 1),
        ("wxid_otto", "", "Otto", "", 1),
        ("wxid_stranger", "", "Someone in a group", "", 3),
        ("12345@chatroom", "", "Book club", "", 2),
        ("gh_news", "", "A news account", "", 1),
    ])
    return conn


def test_contact_kinds_separate_friends_from_groups_accounts_and_strangers():
    rows = engine.contacts(_contact_db(), owner="wxid_owner")
    kinds = {row["username"]: row["kind"] for row in rows}
    assert kinds == {"wxid_mia": "friend", "wxid_otto": "friend", "wxid_stranger": "other",
                     "12345@chatroom": "group", "gh_news": "account"}
    assert next(row for row in rows if row["username"] == "wxid_mia")["name"] == "Mia Chen"  # the owner's remark


def _invoke(*args):
    with patch.object(wc, "_ready", return_value=wc.Path("/nonexistent")), \
         patch.object(wc, "_open", return_value=_contact_db()), \
         patch.object(engine, "owner_username", return_value="wxid_owner"):
        return runner.invoke(app, ["wechat", "contacts", *args])


def test_bare_contacts_prints_the_counts_and_the_next_step():
    result = _invoke()
    assert result.exit_code == 0, result.output
    assert "Friends 2 · groups 1 · official accounts 1 · seen only in groups 1" in result.output
    assert "Next: co wechat contacts --friends --search NAME" in result.output


def test_friends_search_finds_by_remark_nickname_alias_or_id():
    for needle in ("mia", "miachen", "wxid_mia", "Chen"):
        result = _invoke("--friends", "--search", needle)
        assert "Mia Chen" in result.output and "Otto" not in result.output, needle


def test_json_carries_counts_and_matches():
    data = json.loads(_invoke("--friends", "--json").output)
    assert data["counts"] == {"friend": 2, "group": 1, "account": 1, "other": 1}
    assert [row["username"] for row in data["contacts"]] == ["wxid_mia", "wxid_otto"]  # named by the owner first


def test_no_key_for_contact_db_names_the_capture():
    with patch.object(wc, "_ready", return_value=wc.Path("/nonexistent")), patch.object(wc, "_open", return_value=None):
        result = runner.invoke(app, ["wechat", "contacts"])
    assert result.exit_code == 2 and "co wechat key capture" in result.output
