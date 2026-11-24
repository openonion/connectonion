"""After the fix is installed, status and Today stop describing the old failure as current (#3413).

2026-11-23 on the owner's notebook: rc21 (#3403) was installed with the uninstalled-skill filter, but until
the next slot (about 14 hours later) Today still said 「重试解决不了它，要等修复它的新版本」 and `co rem
status` still said "run co rem map-skills first" and "co rem start after fixing the cause", in UTC. The
stored failures are judged against the INSTALLED build: a turn that ran on this version and still failed
the same way is not handled; turns from an older build, on an error this build skips, are.
Fictional data.
"""

import json
import re
from datetime import timedelta

import pytest

from connectonion import __version__
from connectonion.rem import service
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import state_path, write_json

GONE = "skills/catalog/kiln-notes.md has no installed source file; run co rem map-skills first"


def _failed_turns(root, reasons, *, version=None, start=None):
    start = start or service.now() - timedelta(hours=6)
    for index, reason in enumerate(reasons):
        stamp = (start + timedelta(minutes=15 * index)).isoformat()
        turn = {"turn_id": str(index), "started_at": stamp, "finished_at": stamp, "result": "failed",
                "exit_code": 0, "reason": reason, "accepted": 0, **({"version": version} if version else {})}
        write_json(state_path(root, f"turns/{index:03}.json"), turn)
    write_json(state_path(root, "last-turn.json"), turn)


def test_turns_from_an_older_build_on_an_error_this_build_skips_are_handled(tmp_path, rem_clock):
    _failed_turns(tmp_path, [GONE] * 6)  # older receipts carry no version
    assert service.schedule_failure(tmp_path)["stuck"]["handled"] is True


def test_the_same_error_on_this_very_build_is_not_handled(tmp_path, rem_clock):
    _failed_turns(tmp_path, [GONE] * 6, version=__version__)
    assert service.schedule_failure(tmp_path)["stuck"]["handled"] is False


def test_an_unrecognised_error_with_no_page_is_never_called_handled(tmp_path, rem_clock):
    _failed_turns(tmp_path, ["The runner said something new"] * 4)
    assert service.schedule_failure(tmp_path)["stuck"]["handled"] is False


def test_a_new_turn_records_the_build_that_ran_it(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    prepare(tmp_path)
    receipts = []
    monkeypatch.setattr(codex_exec, "write_json", lambda path, value: receipts.append(dict(value)))
    monkeypatch.setattr(codex_exec, "read_json", lambda path, default=None: default)
    with pytest.raises(Exception):  # stop as soon as the first receipt is written
        monkeypatch.setattr(codex_exec, "_reap_orphan_maintenance", lambda root: (_ for _ in ()).throw(RuntimeError("stop")))
        codex_exec._run_locked(tmp_path, lambda *a, **k: None, None)
    assert receipts and receipts[0]["version"] == __version__


def _status_text(root):
    from rich.text import Text
    from connectonion.cli.commands.rem_status import card
    return Text.from_markup(card(root, service.status(root), lambda args: "co rem " + " ".join(args))).plain


def test_status_says_the_fix_is_installed_in_local_time_and_gives_no_impossible_advice(tmp_path, rem_clock):
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "Australia/Sydney"])
    _failed_turns(tmp_path, [GONE] * 6)
    output = _status_text(tmp_path)
    assert "already handles" in output, output
    assert "map-skills" not in output and "after fixing the cause" not in output, output
    assert " UTC" not in output, output


def test_status_on_the_same_build_still_says_what_is_wrong(tmp_path, rem_clock):
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    _failed_turns(tmp_path, [GONE] * 6, version=__version__)
    output = _status_text(tmp_path)
    assert "already handles" not in output
    assert "Last error:" in output


def _today(language, stuck, next_run="2026-11-24T01:00+11:00"):
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    function = re.search(r"function turnTrouble\(.*?\n\}", TEMPLATE.read_text(), re.S)[0]
    script = (f'uiLanguage = {json.dumps(language)}; const REM = {{status: {{timezone: "Australia/Sydney", '
              f'next_run: {json.dumps(next_run)}}}}};\n' + function)
    script += '\nconsole.log(JSON.stringify(turnTrouble(' + json.dumps({
        "code": "repeated_failure", "failures": 6, "same_error": 6, "since": "2026-11-22T19:15:05+00:00",
        "evidence": GONE, "stuck": stuck}) + ')));'
    return _run_reader_js(script)


HANDLED = {"kind": "skill", "skipped": False, "not_installed": True, "handled": True}


@pytest.mark.parametrize("language,said", [
    ("zh", "这个问题新版本已经处理，下一轮会跳过它（下一轮 01:00）"),
    ("en", "This release already handles it; the next round (01:00) skips it")])
def test_today_says_the_installed_release_handles_it_and_names_the_next_round(language, said):
    output = _today(language, HANDLED)
    assert said in output, output
    assert "要等修复它的新版本" not in output and "needs a release that fixes it" not in output
    assert "map-skills" not in output


def test_today_still_says_stuck_when_this_build_did_not_handle_it():
    output = _today("zh", {**HANDLED, "handled": False})
    assert "要等修复它的新版本" in output and "新版本已经处理" not in output


def _night_only(runs, zone="Australia/Sydney"):
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    text = TEMPLATE.read_text()
    pick = lambda name: re.search(r"function " + name + r"\(.*?\n\}", text, re.S)[0]  # noqa: E731
    one_line = lambda name: re.search(r"function " + name + r"\(.*?\}\n", text)[0]  # noqa: E731
    script = (f'const HOUR = 3600e3; const REM = {{status: {{timezone: {json.dumps(zone)}}}}};\n'
              + one_line("runTime") + pick("runEnd") + "\nconst NIGHT_GAP = 3 * HOUR;\n"
              + pick("localHour") + "\n" + pick("nightOnly")
              + f"\nconsole.log(JSON.stringify(nightOnly({json.dumps(runs)}).map(r => r.started_at)));")
    return _run_reader_js(script)


def _run(at):
    return {"started_at": at, "finished_at": at, "outcome": "completed"}


def test_a_daytime_run_hours_after_the_night_is_not_last_night():
    # Sydney (+11): the night 01:12–06:02, then a manual investigate at 11:42 (#3413, phone 昨夜 listed it).
    night = ["2026-11-22T14:12:00Z", "2026-11-22T16:30:00Z", "2026-11-22T19:02:00Z"]
    day = "2026-11-23T00:42:00Z"
    assert _night_only([_run(t) for t in [*night, day]]) == night


def test_a_night_on_its_own_and_a_late_evening_run_stay():
    night = ["2026-11-22T14:12:00Z", "2026-11-22T16:30:00Z"]
    assert _night_only([_run(t) for t in night]) == night
    # 22:30 local is evening, not daytime: kept even after a gap.
    evening = ["2026-11-22T04:00:00Z", "2026-11-22T11:30:00Z"]
    assert _night_only([_run(t) for t in evening]) == evening


def test_only_daytime_runs_are_still_shown():
    # With no night before them there is nothing to drop: the pass is what ran.
    day = ["2026-11-23T00:42:00Z"]
    assert _night_only([_run(t) for t in day]) == day


def _scheduled(root):
    """A notebook with a schedule and a running worker: `next_run` comes from the same source as `co rem status`."""
    prepare(root)
    set_config(root, ["schedule.timezone", "Australia/Sydney"])
    set_config(root, ["schedule.times", "01:00"])
    write_json(state_path(root, "consent.json"), {"at": "2026-11-01T00:00:00+00:00"})
    # codex-exec: the owner's runner, and no probe of the machine's own Codex schedule.
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "codex-exec"})
    _failed_turns(root, [GONE] * 6)


def test_with_a_schedule_status_and_today_name_the_next_round_in_local_time(tmp_path, rem_clock):
    from connectonion.rem.reader import TEMPLATE, snapshot
    from tests.unit.test_rem_reader import _run_reader_js
    _scheduled(tmp_path)
    value = service.status(tmp_path)
    assert value["next_run"] and value["next_run"][11:16] == "01:00", value["next_run"]
    assert "the next round (01:00) skips it" in _status_text(tmp_path)
    status = snapshot(tmp_path, today=True)["status"]  # what the reader receives
    function = re.search(r"function turnTrouble\(.*?\n\}", TEMPLATE.read_text(), re.S)[0]
    script = (f'uiLanguage = "zh"; const REM = {{status: {json.dumps(status, default=str)}}};\n' + function
              + f"\nconsole.log(JSON.stringify(turnTrouble({json.dumps(status['schedule_failure'])})));")
    output = _run_reader_js(script)
    assert "这个问题新版本已经处理，下一轮会跳过它（下一轮 01:00）" in output, output
