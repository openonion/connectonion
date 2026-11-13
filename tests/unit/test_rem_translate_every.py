"""One click translates every page (#2999): Chinese, English and mixed pages all end read in the
owner's language, from `co rem translate` with no flag or the reader's «全部翻译成中文» through the Host.

The owner, 2026-11-13: «有的页面是中文，有的是英文，有的是中英文混合，一键让 Codex 全部都翻译。»
The notebook is invented; the model is the fake translator these tests always use (runner.run_task).
"""

import asyncio
import json
import threading
import time

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import translate as tr
from connectonion.rem.config import prepare, set_config

ENGLISH = ("# Avery Lin\n\n## Facts\n- Role: founder of Fernhill Labs [1]\n\n## Summary\n"
           "Avery runs the pilot and sends the weekly numbers on Fridays [1].\n\n"
           "## Sources\n- [1] gmail:abc — intro mail\n")
# Chinese prose, with what stays as written in any translation: names, a Facts label, a quoted
# English line, a reader marker and an English term inside a Chinese sentence.
CHINESE = ("# Lin Qiao\n\n## Facts\n- Role: 产品负责人 [1]\n- Company: Fernhill Labs\n\n## Summary\n"
           "跟进 Avery Lin 的 Q3 pricing proposal，下周一前回复 [1]。\n"
           "她在邮件里写：“Please send the revised pricing deck by Monday.” [1]\n"
           "- Now: Unknown\n\n## Sources\n- [1] gmail:def — pricing thread\n")
MIXED = ("# Fernhill pilot\n\n## Summary\n试点在三月开始，目前进展顺利 [1]。\n"
         "The second cohort is waiting on the data-sharing agreement from legal [1].\n\n"
         "## Sources\n- [1] codex:s1 — planning session\n")
PAGES = {"people/avery-lin.md": ENGLISH, "people/lin-qiao.md": CHINESE, "projects/fernhill.md": MIXED}


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    for record, text in PAGES.items():
        (tmp_path / record).write_text(text)
    set_config(tmp_path, ["languages", "zh,en"])
    set_config(tmp_path, ["limits.workers", "1"])
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    # The Host's job ends by asking the reader to rebuild; no reader process here.
    monkeypatch.setattr("connectonion.rem.reader.owner_changed", lambda root: False)
    return tmp_path


def fake_translator(calls, gate=None):
    """Prefix every prose line: headings, source ids and quotes come back as they were."""
    def run(workspace, prompt, config, stage):
        page = (workspace / "page.md").read_text()
        calls.append(page.splitlines()[0])
        if gate is not None:
            gate.wait(10)
        lines = [line if not line.strip() or line.startswith(("#", ">")) else "译文：" + line for line in page.splitlines()]
        (workspace / "translation.md").write_text("\n".join(lines) + "\n")
        return {"outcome": "natural"}
    return run


def test_a_page_counts_as_chinese_only_when_all_its_own_prose_is():
    assert tr.foreign_lines(CHINESE, "zh") == []
    assert tr.foreign_lines(ENGLISH, "zh") == ["- Role: founder of Fernhill Labs [1]",
                                               "Avery runs the pilot and sends the weekly numbers on Fridays [1]."]
    assert tr.foreign_lines(MIXED, "zh") == ["The second cohort is waiting on the data-sharing agreement from legal [1]."]
    assert tr.foreign_lines(ENGLISH, "en") == [] and tr.foreign_lines(CHINESE, "en") != []
    # Paths and ids stay as written, so they are not English prose in a Chinese page.
    assert tr.foreign_lines(CHINESE + "- Folder: /Users/avery/fernhill-pilot\n- Session: 01a0-5a90-959e-7b92\n", "zh") == []
    # A stub with no line of three words is still English when none of its lines is Chinese.
    assert tr.foreign_lines("# Avery Lin\n\n- Role: founder [1]\n", "zh") == ["- Role: founder [1]"]


def test_co_rem_translate_with_no_flag_translates_english_and_mixed_pages_and_a_rerun_is_a_no_op(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls))
    total = len(tr.Notebook(notebook).list())
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate", "--all"])
    assert result.exit_code == 0, result.output
    assert sorted(calls) == ["# Avery Lin", "# Fernhill pilot"]          # the Chinese page needs no model turn
    assert f"{total - 2} of {total} pages already read in 中文; translating 2…" in result.output
    assert "[1/2] " in result.output and "[2/2] " in result.output
    assert f"2 translated, 0 cached, 0 failed. {total} of {total} pages now read in 中文." in result.output
    assert all(tr.current(notebook, record, "zh") for record in PAGES)
    assert tr.coverage(notebook)["zh"]["translated"] == total            # co rem status agrees
    again = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate", "--all"])
    assert again.exit_code == 0, again.output
    assert len(calls) == 2 and f"All {total} pages already read in 中文; nothing to translate." in again.output


def test_the_night_queue_skips_a_chinese_page_but_keeps_a_mixed_one(notebook):
    assert set(tr.backlog(notebook, "zh")) == {"people/avery-lin.md", "projects/fernhill.md"}


def _host(root, identity):
    from connectonion.network.host.rem_http import handle_rem_http

    def call(body, *, cookie=True, kind="application/json"):
        from connectonion.rem.live_host import reader_token
        headers = [[b"host", b"127.0.0.1:8123"], [b"content-type", kind.encode()]]
        if cookie:
            headers.append([b"cookie", ("co_rem=" + reader_token(identity)).encode()])
        scope = {"type": "http", "method": "POST", "path": "/rem/translate-all", "query_string": b"",
                 "headers": headers, "client": ("127.0.0.1", 50000)}
        sent = []

        async def receive():
            return {"body": json.dumps(body).encode(), "more_body": False}

        async def send(message):
            sent.append(message)
        asyncio.run(handle_rem_http(scope, receive, send, {"rem_root": root, "identity_dir": identity}))
        return sent[0]["status"], sent[1]["body"].decode()
    return call


def _until(call, *states):
    for _ in range(200):
        status, body = call({"action": "status"})
        if json.loads(body)["state"] in states:
            return json.loads(body)
        time.sleep(0.05)
    raise AssertionError(body)


def test_the_reader_button_runs_the_same_job_through_the_host_with_its_write_rules(notebook, tmp_path_factory, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls))
    identity = tmp_path_factory.mktemp("co")
    call, total = _host(notebook, identity), len(tr.Notebook(notebook).list())
    assert call({"action": "start"}, cookie=False)[0] == 401
    assert call({"action": "start"}, kind="text/plain")[0] == 415          # a form post cannot start it
    assert call({"action": "go"})[0] == 400 and not calls
    status, body = call({"action": "status", "language": "zh"})
    assert status == 200 and json.loads(body) == {"state": "idle", "translated": 0, "failed": 0, "error": None, "language": "zh",
                                                  "done": total - 2, "total": total}
    assert json.loads(call({"action": "start", "language": "zh"})[1])["state"] in ("starting", "running", "done")
    done = _until(call, "done")
    assert (done["done"], done["total"], done["translated"], done["failed"]) == (total, total, 2, 0)
    assert sorted(calls) == ["# Avery Lin", "# Fernhill pilot"]


def test_stop_lets_the_page_begun_finish_and_leaves_the_rest(notebook, tmp_path_factory, monkeypatch):
    calls, gate = [], threading.Event()
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls, gate))
    call = _host(notebook, tmp_path_factory.mktemp("co"))
    call({"action": "start"})
    running = _until(call, "running")
    assert running["done"] == running["total"] - 2
    for _ in range(200):
        if calls:
            break
        time.sleep(0.05)
    assert json.loads(call({"action": "stop"})[1])["state"] == "stopping"
    gate.set()
    stopped = _until(call, "stopped")
    assert len(calls) == 1 and stopped["translated"] == 1 and stopped["done"] == stopped["total"] - 1


def test_the_command_is_on_the_root_help_page_not_only_under_advanced():
    root = CliRunner().invoke(app, ["rem", "--help"], terminal_width=200).stdout
    assert "  translate     Translate every page not yet in your language, or one page." in root
    page = CliRunner().invoke(app, ["rem", "translate", "--help"], terminal_width=200).stdout
    assert "one model turn per page" in page and "quota floor" in page
    advanced = CliRunner().invoke(app, ["rem", "advanced", "--help"], terminal_width=200).stdout
    assert "  translate " not in advanced


def test_without_a_terminal_bare_translate_asks_for_all_before_spending(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a: pytest.fail("model called"))
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate"])
    assert result.exit_code != 0
    assert "2 pages, one model turn each" in result.output and "--all" in result.output


FULL = {"used_percent": 95, "window_minutes": 10080, "resets_at": 0, "plan": "pro"}


def _meter_after(calls, pages):
    """The week crosses the floor once `pages` model turns have run."""
    return lambda root, config: FULL if len(calls) >= pages else {**FULL, "used_percent": 10}


def test_the_quota_floor_stops_the_cli_before_the_next_page(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls))
    monkeypatch.setattr("connectonion.rem.quota.meter", _meter_after(calls, 1))
    total = len(tr.Notebook(notebook).list())
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate", "--all"])
    assert len(calls) == 1, result.output
    assert f"Stopped at {total - 1} of {total}: the Codex week is at 95%" in result.output


def test_the_quota_floor_stops_the_host_job_in_words(notebook, tmp_path_factory, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls))
    monkeypatch.setattr("connectonion.rem.quota.meter", _meter_after(calls, 1))
    call = _host(notebook, tmp_path_factory.mktemp("co"))
    call({"action": "start"})
    stopped = _until(call, "stopped")
    assert len(calls) == 1 and stopped["halted"].startswith("the Codex week is at 95%")


def _dead_pid():
    import subprocess
    import sys
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_a_running_job_holds_a_claim_the_night_and_a_second_cli_respect(notebook, monkeypatch):
    import os
    from connectonion.rem import native_round
    from connectonion.rem.config import read_config
    from connectonion.rem.daily import _translate_changed
    from connectonion.rem.files import state_path, write_json
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls))
    write_json(state_path(notebook, "translate-all.json"), {"pid": os.getpid(), "started_at": "2026-11-13T10:00:00+00:00"})
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate", "--all"])
    assert result.exit_code != 0 and "already translating every page" in result.output and not calls
    maintenance = {}
    _translate_changed(notebook, read_config(notebook), maintenance, [], None, lambda text: None)
    assert "translations" not in maintenance and not calls
    from connectonion.rem import service
    cursor = {"changed": [], "shown_today": [], "translation_attempts": [], "phase": "daily-translation",
              "task_day": service.notebook_today(notebook).isoformat()}
    directory = state_path(notebook, "tasks/claim-test")
    directory.mkdir(parents=True)
    assert native_round.prepare_translation(notebook, cursor, read_config(notebook), directory) is None
    # A claim whose process is gone is ignored: the night goes on, and the CLI runs.
    write_json(state_path(notebook, "translate-all.json"), {"pid": _dead_pid(), "started_at": "2026-11-13T10:00:00+00:00"})
    assert native_round.prepare_translation(notebook, cursor, read_config(notebook), directory) is not None
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "translate", "--all"])
    assert result.exit_code == 0, result.output
    assert not state_path(notebook, "translate-all.json").exists()              # released when done
