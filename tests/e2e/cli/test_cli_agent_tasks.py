"""An agent that only reads `--help` can find the command for each real task (#3355).

The static audit checks a page's form. This walks the owner's actual jobs the way an agent meets them: start at a
group's help, follow what it lists, and land on a command whose page has the flag the job needs. Each task is one
the owner raised on 2026-11-22.
"""
import re

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def page(*words):
    result = runner.invoke(app, [*words, "--help"], terminal_width=200)
    assert result.exit_code == 0, (words, result.output)
    return result.stdout


def lists(text, command):
    return re.search(rf"^\s+{re.escape(command)}\s{{2,}}\S", text, re.M) is not None


def test_find_a_wechat_friend():
    assert lists(page("wechat"), "contacts")
    contacts = page("wechat", "contacts")
    assert "--friends" in contacts and "--search" in contacts and "friend" in contacts.lower()


def test_search_the_whole_history_says_what_it_can_and_cannot_reach():
    assert lists(page("wechat"), "search")
    search = page("wechat", "search")
    # Until the full-text index is read (#3347), the page is honest that a keyless database is skipped
    # and names the recovery, rather than implying it searched everything.
    assert "co wechat key capture" in search


def test_mark_a_contact_not_a_person():
    assert lists(page("rem", "advanced"), "person")
    person = page("rem", "person")
    assert "--not-person" in person and "--reset" in person and "WeChat" in person


def test_map_then_investigate_wechat():
    assert lists(page("rem"), "map")
    mapped = page("rem", "map")
    assert "co rem map people --source wechat" in mapped
    assert "co rem investigate people --source NAME --new" in mapped
    assert "--source" in page("rem", "investigate")


def test_recover_after_migrating_chat_history():
    capture = " ".join(page("wechat", "key", "capture").split())  # a page wraps its sentences
    assert "migrate chat history" in capture and "keeping the keys saved before" in capture
    assert "Allow" in capture and "QR" in capture  # what the one question really asks of the owner
