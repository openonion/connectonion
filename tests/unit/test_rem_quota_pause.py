"""REM at the Codex week's floor says so instead of going quiet (#2938).

A fictional notebook's week reached its 90% floor on a Monday evening. Every
scheduled turn for two nights read the floor and exited; status, the night
stats and the morning note all read as a quiet night. Fictional notebooks only.
"""

from datetime import datetime, timezone
from html import escape
from unittest.mock import Mock

import pytest

from connectonion.rem import morning, native, native_round, night_stats, quota, service
from connectonion.rem.config import read_config, set_config
from connectonion.rem.files import read_json, state_path
from tests.unit.test_rem_mail_every_slot import held_round, mailbox
from tests.unit.test_rem_unstick import notebook  # noqa: F401

pytestmark = pytest.mark.usefixtures("rem_clock")


def week(monkeypatch, used):
    reading = {"used_percent": used, "window_minutes": 10080, "plan": "pro",
               "resets_at": int(datetime(2026, 9, 9, 17, 46, tzinfo=timezone.utc).timestamp())}
    monkeypatch.setattr(quota, "read", lambda config, request=None: reading)


def at(monkeypatch, moment):
    monkeypatch.setattr(service, "now", lambda: moment)


@pytest.fixture(autouse=True)
def at_a_slot(monkeypatch, rem_clock):
    """17:00 UTC on Monday 7 September is one of the notebook's slots."""
    at(monkeypatch, datetime(2026, 9, 7, 17, tzinfo=timezone.utc))


def turn(root, monkeypatch):
    """One scheduled turn on the owner's round shape: a page open, the slot's mail to read."""
    if not state_path(root, "round.json").is_file():
        held_round(root)
    mailbox(monkeypatch, [])
    return native.next_task(root, scheduled=True)


def dashboard(root):
    from connectonion.cli.commands.rem_status import dashboard as draw
    return draw(root, service.status(root), lambda arguments: "co rem " + " ".join(arguments))


def test_a_turn_stopped_by_the_floor_is_a_pause_status_names_with_its_start_and_what_to_do(notebook, monkeypatch):
    week(monkeypatch, 90)
    turn(notebook, monkeypatch)
    paused = service.status(notebook)["paused"]
    assert paused["reason"] == "quota" and paused["since"].startswith("2026-09-07T17:00"), paused
    text = dashboard(notebook)
    assert "Paused since Mon 07 Sep 17:00" in text, text
    assert "90% used" in text and "Wed 09 Sep 17:46" in text, text
    assert "co rem config set limits.quota_floor_percent" in text, text


def test_the_pause_keeps_the_time_it_started_across_turns_and_ends_when_the_floor_lifts(notebook, monkeypatch):
    week(monkeypatch, 90)
    turn(notebook, monkeypatch)
    at(monkeypatch, datetime(2026, 9, 8, 3, tzinfo=timezone.utc))
    turn(notebook, monkeypatch)
    assert service.status(notebook)["paused"]["since"].startswith("2026-09-07T17:00")
    # The owner raises the floor before the week resets: the next turn may work.
    at(monkeypatch, datetime(2026, 9, 8, 22, tzinfo=timezone.utc))
    set_config(notebook, ["limits.quota_floor_percent", "95"])
    monkeypatch.setattr(native_round, "prepare_task", lambda *args: {"stop": "fixture: no page work"})
    turn(notebook, monkeypatch)
    assert service.status(notebook).get("paused") is None
    assert read_json(state_path(notebook, quota.PAUSE), {})["ended_at"].startswith("2026-09-08T22:00")
    assert "Paused since" not in dashboard(notebook)


def test_a_night_spent_at_the_floor_is_recorded_as_paused_not_quiet(notebook, monkeypatch):
    week(monkeypatch, 90)
    turn(notebook, monkeypatch)
    at(monkeypatch, datetime(2026, 9, 8, 13, tzinfo=timezone.utc))  # the next night has begun
    [row] = night_stats.record(notebook)
    assert row["night"] == "2026-09-07" and row["paused"] == "quota", row


def test_a_night_with_no_pause_carries_no_pause(notebook, monkeypatch):
    at(monkeypatch, datetime(2026, 9, 8, 13, tzinfo=timezone.utc))
    [row] = night_stats.record(notebook)
    assert "paused" not in row, row


@pytest.mark.parametrize("language, line", [
    ("en", "REM paused: this week's Codex allowance is 90% used. It resumes Wed 17:46."),
    ("zh", "REM 暂停中：本周 Codex 额度已用 90%，周三 17:46 恢复。")])
def test_the_morning_note_says_rem_is_paused_instead_of_saying_nothing(notebook, monkeypatch, language, line):
    set_config(notebook, ["notify.channel", "telegram", "notify.target", "fictional-owner", "languages", language])
    week(monkeypatch, 90)
    turn(notebook, monkeypatch)
    at(monkeypatch, datetime(2026, 9, 8, 7, tzinfo=timezone.utc))
    monkeypatch.setattr(morning, "actionable", lambda root: [])
    monkeypatch.setattr(morning, "today_link", lambda root: "co rem open")
    value = morning.preview(notebook)
    assert value["message"].splitlines()[0] == line, value["message"]
    assert escape(line, quote=True) in value["html"], "the designed mail still read as a quiet night"
    send = Mock()
    monkeypatch.setattr(morning, "send_message", send)
    entry = morning.run(notebook)
    assert entry["status"] == "sent" and entry["paused"] == "quota", entry
    assert read_json(state_path(notebook, "morning.json"), {})["2026-09-08"]["paused"] == "quota"
    send.assert_called_once()


def test_status_without_a_pause_has_none(notebook):
    assert service.status(notebook).get("paused") is None
    assert read_config(notebook)["limits"]["quota_floor_percent"] == 90
