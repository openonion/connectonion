"""The Investigate button on a person's page: its words, its levels, a run followed in place, and Undo (#3105).

Every /rem/* request goes through the real Host handler (rem_http) to the real page_runs and page_versions;
only the investigation itself is a fake worker that writes what `co rem investigate PAGE --enrich` would:
two run records (append, then enrich), one appended line, the previous page for Undo, and its receipt.
The notebook is invented. Opt in with CO_REM_BROWSER_TEST=1.
"""

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from tests.e2e.cli.test_rem_hand_any_row_browser import BASE, _host

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
SHOTS = os.environ.get("CO_REM_SHOTS")
PAGE = "people/mara.md"
TEXT = ("# Mara Quill\n\nMara runs the Fernhill pilot with the user. [1]\n\n## Facts\n- Email: mara@fernhill.example [1]\n\n"
        "## Who they are\n- Mara leads the Fernhill pilot. [1]\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa — 2026-10-01\n\n"
        "Investigation: mapped 2026-09-01 · investigated 2026-10-01 (gmail)\n")
LINE = "- Mara moved the pilot review to Friday. [1]"
FAKE = r"""
import json, sys, time, uuid
from pathlib import Path
from connectonion.rem import page_runs, page_versions
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.service import now
root, record, line = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def run(phase, outcome, stage):
    path = state_path(root, f"runs/run_{uuid.uuid4().hex}.json")
    write_json(path, {"id": path.stem, "phase": phase, "record": record, "started_at": now().isoformat(),
                      "outcome": outcome, "stage": stage, "speed": "fast"})
    return path
book = Notebook(root); before = book.read(record)
first = run("investigate", "running", "writing investigation"); time.sleep(7)
after = before.replace("- Mara leads the Fernhill pilot. [1]", "- Mara leads the Fernhill pilot. [1]\n" + line)
book.write(record, after)
write_json(first, {**read_json(first, {}), "outcome": "completed", "stage": "recording result"})
second = run("enrich", "running", "following leads"); time.sleep(7)
write_json(second, {**read_json(second, {}), "outcome": "completed"})
page_versions.keep_previous(root, record, before, after)
receipt = read_json(page_runs.receipt_path(root, record), {})
write_json(page_runs.receipt_path(root, record), {**receipt, "result": "completed", "exit_code": 0, "finished_at": now().isoformat()})
"""


@pytest.fixture
def live(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import live_host, page_runs
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    monkeypatch.setenv("CONNECTONION_REM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root, identity = tmp_path / "rem", tmp_path / "co"
    identity.mkdir()
    prepare(root)
    Notebook(root).write(PAGE, TEXT)
    commands = []
    real = subprocess.Popen

    processes = []

    def worker(command, **options):
        commands.append(command)
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
        processes.append(real([sys.executable, "-c", FAKE, str(root), PAGE, LINE], **{**options, "env": env}))
        return processes[-1]
    # The fake worker is not `-m connectonion.rem.page_runs`, so its liveness is its own process's.
    monkeypatch.setattr(page_runs, "_alive", lambda receipt: bool(processes) and processes[-1].poll() is None)
    # page_runs' own subprocess only: the browser driver needs the real Popen.
    monkeypatch.setattr(page_runs, "subprocess", types.SimpleNamespace(
        Popen=worker, run=subprocess.run, DEVNULL=subprocess.DEVNULL, STDOUT=subprocess.STDOUT))
    cookie = "co_rem=" + live_host.reader_token(identity)
    call, errors = _host(root, identity), []

    def serve(route):
        request = route.request
        path = request.url[len(BASE):].split("#")[0].split("?")[0]
        if not path.startswith("/rem"):
            return route.abort()
        status, kind, body = call(request.method, path, (request.post_data or "").encode(), cookie)
        return route.fulfill(status=status, body=body, content_type=kind.split(";")[0])

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE + "/rem#r=" + PAGE.replace("/", "%2F"))
        page.locator(".inv-go").wait_for()
        try:
            yield page, root, commands
        finally:
            browser.close()
    assert not errors, errors


def _topmost(page, selector):
    """A 5×5 grid of points over the opened element (16px in, clear of its rounded corners) are the element itself to the
    pointer, not a card drawn over it."""
    return page.evaluate("""sel => { const n = document.querySelector(sel), b = n.getBoundingClientRect(), points = [];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++)
        points.push([b.left + 16 + (b.width - 32) * i / 4, b.top + 16 + (b.height - 32) * j / 4]);
      return points.filter(([x, y]) => y < innerHeight && x < innerWidth).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""",
                         selector, isolated_context=False)


def test_the_button_says_why_offers_its_levels_runs_in_place_and_undoes(live):
    from patchright.sync_api import expect
    from connectonion.rem.files import Notebook
    page, root, commands = live
    control = page.locator(".person-head .inv")
    # One verb on the button; the reason is the line under it (owner, 2026-11-18: «更新是什么意思呢？»).
    expect(control.locator(".inv-go")).to_have_text("Up to date")
    expect(control.locator(".inv-go")).to_be_disabled()
    expect(control.locator(".inv-line")).to_have_text("Last investigated Oct 1")
    for state, why in ((dict(label="investigate", last=None), "Not investigated yet"),
                       (dict(label="update", new_mails=3, last="2026-10-01"), "3 new mails not in this page yet · last Oct 1"),
                       (dict(label="update", new_mails=0, new_sessions=1), "1 new session not in this page yet · last Oct 1"),
                       (dict(label="deeper", leads=5), "5 leads not followed yet (uses the web) · last Oct 1")):
        page.evaluate("""s => { const r = byPath('people/mara.md'); r.investigation = { ...r.investigation, ...s };
          render(); }""", state, isolated_context=False)
        expect(control.locator(".inv-go")).to_have_text("Investigate")
        expect(control.locator(".inv-line")).to_have_text(why)
    page.evaluate("() => { const r = byPath('people/mara.md'); r.investigation = { ...r.investigation, label: 'current', last: '2026-10-01', new_mails: 0, new_sessions: 0, leads: 0 }; render(); }", isolated_context=False)
    control.locator(".inv-more > summary").click()
    levels = control.locator(".inv-menu [data-level]")
    expect(levels).to_have_count(3)
    assert _topmost(page, ".inv-menu"), "the Investigate menu is covered by the page below it"
    assert [text.split("\n")[0] for text in levels.all_inner_texts()] == ["Full investigation · default", "Quick update", "Rewrite the page"]
    levels.first.click()                                       # an up-to-date page can still be run from ⋯
    steps = control.locator(".inv-steps li")
    expect(steps.first).to_have_text("Append")
    expect(control.locator(".inv-steps li.running")).to_contain_text("Web follow-up", timeout=20000)
    assert commands and commands[0][-4:] == ["--record", PAGE, "--mode", "full"]
    line = control.locator(".inv-line[role=status]")
    expect(line).to_contain_text("Updated · 1 line added", timeout=30000)
    line.get_by_role("button", name="What changed").click()
    expect(control.locator(".inv-changed li")).to_have_text("Mara moved the pilot review to Friday.")
    # A real run lists many lines (the owner's had a dozen), so the card reaches over the cards under the head.
    page.evaluate("""() => { const ul = document.querySelector('.inv-changed ul');
      for (let i = 1; i <= 10; i++) ul.append(Object.assign(document.createElement('li'), { textContent: 'Another line the run added, number ' + i + '.' })); }""",
                  isolated_context=False)
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "investigate-done.png"))
    # It floats over everything under it (owner, 2026-11-19: some cards were drawn over it, some under).
    assert _topmost(page, ".inv-changed"), "the 'What changed' card is covered by the page below it"
    assert "Friday" in Notebook(root).read(PAGE)
    line.get_by_role("button", name="Undo").click()
    expect(control.locator(".inv-line[role=status]")).to_have_text("Undone · the page is back as it was")
    assert Notebook(root).read(PAGE) == TEXT


def test_a_page_that_lost_its_host_says_so_and_reconnects(live):
    """#3139 (owner, 2026-11-19: «有的时候我点那调查的时候说 REM 暂时没有回应 过会儿再试 这是什么原因»): the Host the page
    came from was restarted. The page says that in words, with one Reconnect, instead of blaming a busy REM."""
    from patchright.sync_api import expect
    page, root, commands = live
    page.evaluate("() => { const r = byPath('people/mara.md'); r.investigation = { ...r.investigation, label: 'investigate' }; render(); }",
                  isolated_context=False)
    page.route("**/rem/**", lambda route: route.abort())          # the Host is gone
    page.locator(".person-head .inv-go").click()
    line = page.locator(".person-head .inv-line")
    expect(line).to_contain_text("This page lost touch with REM (it was just restarted)")
    bar = page.locator("#host-lost")
    expect(bar).to_be_visible()
    assert page.evaluate("""() => { const n = document.getElementById('host-lost'), b = n.getBoundingClientRect();
      return [[0.25, 0.5], [0.5, 0.5], [0.75, 0.5]].every(([fx, fy]) => n.contains(document.elementFromPoint(b.left + b.width * fx, b.top + b.height * fy))); }""",
                         isolated_context=False)                     # over the page, not under a card
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "host-lost.png"))
    assert not commands                                            # nothing ran
    page.unroute("**/rem/**")                                       # the Host is back
    bar.get_by_role("button", name="Reconnect").click()
    page.locator(".inv-go").wait_for()
    expect(page.locator("#host-lost")).to_have_count(0)
