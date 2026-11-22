"""Today's curve draws the whole night, not its last 21 runs (#3391).

On rc19 the page carried only the latest 21 runs, so on a real night of ~60 runs the 昨夜 curve began at 03:40 although
the night ran from 01:00: the stuck 01:12 loop that #3382 draws as Awake fell off its left edge, and the axis ran an
hour past now. Here the runs are real run files in an invented notebook (tests/fixtures/rem_reader_notebook.py), read
by the same render() path the Host uses."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _night(now: datetime) -> list[dict]:
    """60 runs over 5.5 hours: one read, a tag task parked after 93 minutes of retries, then 58 short runs."""
    start = now - timedelta(hours=5.5)
    iso = lambda t: t.isoformat(timespec="seconds")
    runs = [{"phase": "sync", "started_at": iso(start), "finished_at": iso(start + timedelta(minutes=3)),
             "outcome": "completed", "items": 12, "changed": []},
            {"phase": "tag", "started_at": iso(start + timedelta(minutes=12)),
             "finished_at": iso(start + timedelta(minutes=105)), "outcome": "parked", "items": 0, "changed": []}]
    for i in range(58):
        at = start + timedelta(minutes=110 + i * 3.6)
        runs.append({"phase": "daily-translation" if i % 3 else "investigate", "started_at": iso(at),
                     "finished_at": iso(at + timedelta(minutes=2)), "outcome": "completed", "items": 1,
                     "changed": ["people/mara-ostrowski.md"] if i % 3 == 0 else []})
    return runs


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("night") / "rem"
    now = datetime.now(timezone.utc)
    build(root, now - timedelta(days=3))  # the fixture's own runs sit days before tonight's pass
    runs = root / ".state" / "runs"
    for i, run in enumerate(_night(now)):
        run["id"] = f"run_{0xabc000 + i:032x}"
        (runs / f"{run['id']}.json").write_text(json.dumps(run))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width, height, mobile=False):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile, locale="en-US")
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .night-card").wait_for()
    return api, browser, page


SCALE = """() => {
  // The night's first run was written 5.5 hours before the page was drawn; the test knows it without the reader's help.
  const asOf = new Date(REM.as_of).getTime(), s = hypnoScale(asOf), first = asOf - 5.4 * HOUR;
  const stuck = s.runs.find(r => r.outcome === 'parked');
  const svg = document.querySelector('#main .night-card .hypno svg');
  const pts = svg.querySelector('.trace').getAttribute('d').replace('M', 'L').split('L').slice(1).map(p => p.split(',').map(Number));
  const levels = [...document.querySelectorAll('#main .night-card .hypno .lvl')].map(n => parseFloat(n.style.top));
  const mid = stuck ? s.x((runTime(stuck) + runEnd(stuck)) / 2) : null;
  const y = mid === null ? null : pts.filter(([x]) => x <= mid).pop()[1];
  return {detailed: (REM.logs || REM.brief_logs || []).length, curveRuns: s.runs.length, start: s.start, end: s.end, asOf, first,
          stuck: !!stuck, y, awake: levels[0],
          words: [...document.querySelectorAll('#main .night-card .stretch-what')].map(n => n.textContent)};
}"""


@pytest.mark.parametrize("width,mobile", [(1440, False), (390, True)])
def test_the_whole_night_is_on_the_curve_and_the_stuck_loop_reads_awake(page_file, width, mobile):
    api, browser, page = _open(page_file, width, 900, mobile)
    try:
        state = page.evaluate(SCALE, isolated_context=False)
        assert state["detailed"] <= 21, state  # the detailed logs stay small; night_runs fills the night in
        assert state["curveRuns"] >= 60, state
        assert state["start"] <= state["first"], state  # the curve begins at the night's first run
        assert state["stuck"] and state["y"] == state["awake"], state  # the 01:12 loop is drawn awake
        assert any("stuck" in w for w in state["words"]) or mobile, state["words"]
    finally:
        browser.close(); api.stop()


def test_the_axis_ends_at_now_not_an_hour_past_it(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        state = page.evaluate(SCALE, isolated_context=False)
        assert state["end"] <= state["asOf"] + 15 * 60e3, (state["end"] - state["asOf"]) / 60e3
    finally:
        browser.close(); api.stop()
