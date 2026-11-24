"""Past the Codex week's floor, translation and tagging go on to a ceiling (#3195, #3165).

2026-11-20: the week reached its 90% floor on a Friday and every scheduled turn
served nothing until Tuesday, with 142 translations, 226 untagged pages and 56 tag
pages waiting. The floor keeps the owner's own coding safe from investigation; a
translate or tag turn is a minute of a small model. Fictional notebooks only.
"""

from datetime import datetime, timezone

import pytest

from connectonion.rem import morning, native, quota, service, tag_stage
from connectonion.rem.config import read_config, set_config
from connectonion.rem.files import Notebook
from tests.unit.test_rem_mail_every_slot import held_round
from tests.unit.test_rem_unstick import notebook  # noqa: F401

pytestmark = pytest.mark.usefixtures("rem_clock")

RESETS = int(datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc).timestamp())  # Tuesday in UTC and in Sydney


def week(monkeypatch, used):
    reading = {"used_percent": used, "window_minutes": 10080, "plan": "pro", "resets_at": RESETS}
    monkeypatch.setattr(quota, "read", lambda config, request=None: reading)


@pytest.fixture(autouse=True)
def friday(monkeypatch, rem_clock):
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 9, 4, 17, tzinfo=timezone.utc))


def untagged(root):
    """Three written pages no tag turn has read yet."""
    for n in range(3):
        Notebook(root).write(f"people/p{n:02}.md", f"# P{n}\n\n## Facts\n- Role: Student in a fictional course [1]\n")


def dashboard(root):
    from connectonion.cli.commands.rem_status import card as draw
    return draw(root, service.status(root), lambda arguments: "co rem " + " ".join(arguments))


def test_at_the_floor_next_serves_a_tag_turn_and_no_investigation(notebook, monkeypatch):
    week(monkeypatch, 90)
    held_round(notebook)
    untagged(notebook)
    assert tag_stage.candidates(notebook), "fixture: the notebook should have untagged pages"
    result = native.next_task(notebook)
    assert result["outcome"] == "task", result
    assert result["stage"] in ("tag", "translate", "tag-node"), result
    assert result["stage"] not in ("investigate", "plan", "maintain"), result


def test_at_the_ceiling_next_serves_nothing(notebook, monkeypatch):
    week(monkeypatch, 97)
    held_round(notebook)
    untagged(notebook)
    result = native.next_task(notebook)
    assert result["outcome"] == "done", result
    assert "97% ceiling for translation and tagging" in result["reason"], result


def test_the_ceiling_is_a_setting_and_never_sits_below_the_floor(notebook, monkeypatch):
    set_config(notebook, ["limits.cheap_ceiling_percent", "92"])
    assert read_config(notebook)["limits"]["cheap_ceiling_percent"] == 92
    limits = read_config(notebook)["limits"]
    assert quota.ceiling_block({"used_percent": 92}, limits)
    assert not quota.ceiling_block({"used_percent": 91}, limits)
    # A ceiling set under the floor is the floor: the cheap stages never stop before investigation.
    assert not quota.ceiling_block({"used_percent": 89}, {**limits, "cheap_ceiling_percent": 50})


@pytest.mark.parametrize("used, language, line", [
    (90, "en", "Codex week at 90%: investigation paused until Tue; translation and tagging continue."),
    (90, "zh", "额度到 90%：调查暂停到 周二；翻译和标签照常。"),
    (98, "en", "Codex week at 98%: investigation, translation and tagging paused until Tue."),
    (98, "zh", "额度到 98%：调查、翻译和标签都暂停到 周二。")])
def test_the_morning_line_says_what_stopped_and_what_goes_on(notebook, monkeypatch, used, language, line):
    set_config(notebook, ["languages", language])
    week(monkeypatch, used)
    quota.record_pause(notebook, quota.read(None), read_config(notebook)["limits"])
    local = service.now().astimezone()
    assert morning._pause_line(notebook, local, language == "zh") == line


def test_status_heads_the_pause_with_what_goes_on(notebook, monkeypatch):
    week(monkeypatch, 90)
    quota.record_pause(notebook, quota.read(None), read_config(notebook)["limits"])
    text = dashboard(notebook)
    assert "Codex week at 90%: investigation paused until Tue; translation and tagging continue." in text, text
    assert "translation and tagging stop at 97%" in text, text
