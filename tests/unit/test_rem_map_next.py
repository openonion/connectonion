"""`co rem map`'s help and a run name the same next step (#3355).

The help said `Next: co rem investigate …`; a run on the owner's machine printed `Next: co rem status`, because
while the nightly schedule writes, `_owner_next` leaves investigating to the night. Both are honest; the page now
says both, and this pins that each runtime form is the one the page names for that state.
"""
import re

from connectonion.cli.commands import rem_commands
from connectonion.cli.commands.rem_help import pages

FOLLOW = ["investigate", "people", "--source", "wechat", "--new"]


def _next_lines():
    return re.search(r"^Next:(.*?)^Back:", pages()["co rem map"], re.M | re.S).group(1)


def test_without_a_schedule_the_run_says_investigate_as_the_page_does(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.worker_state", lambda root: {"enabled": False})
    assert rem_commands._owner_next(tmp_path, FOLLOW) == FOLLOW
    assert "co rem investigate people --source NAME --new" in _next_lines()


def test_with_the_schedule_on_the_run_says_status_as_the_page_does(tmp_path, monkeypatch):
    class Installed:
        def installed(self, root):
            return True
    monkeypatch.setattr("connectonion.rem.service.worker_state", lambda root: {"enabled": True})
    monkeypatch.setattr("connectonion.rem.schedule.default_scheduler", lambda root: Installed())
    assert rem_commands._owner_next(tmp_path, FOLLOW) == ["status"]
    assert "co rem status" in _next_lines() and "nightly schedule is on" in _next_lines()
