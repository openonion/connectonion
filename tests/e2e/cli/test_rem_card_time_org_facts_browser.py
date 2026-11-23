"""A card's time turns when it passes; an org's website and connection reasons say only what is true (13:25 hunt).

The 13:25 hunt on rc22 found, on the owner's notebook:
(a) a Today card still read 「今天 14:00」 at 14:40, and nothing marked the hour before it;
(b) a student team's 网站 was its members' university mail domain, and a 关联 row's reason was
    「上级组织: 课程 9900」, which only repeats the target's name.
The notebook is invented (tests/fixtures/rem_reader_notebook.py) and read by the same render() path the Host uses."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("cardtime") / "rem"
    build(root, datetime.now(timezone.utc) - timedelta(days=2))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width=1440, height=1000):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_context(viewport={"width": width, "height": height}).new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .today-brief").wait_for()
    return api, browser, page


# A thread whose words name a time today: before it, within the hour before it, and after it, as the clock moves on
# while the page stays open. The clock is moved by replacing clockNow, the one function the reader reads it from.
TURNS = """() => {
  const r = inCategory('people')[0], base = Date.parse(REM.as_of), since = agDay(agToday(), -2);
  REM.calendar = { events: [] };
  const at = base + 3 * 3600e3, day = calendarDay(new Date(at).toISOString()), hm = agTime(new Date(at).toISOString());
  const thread = { since, text: `Demo on ${day} at ${hm}.` };
  const real = clockNow, read = shift => { clockNow = () => base + shift; const m = upcomingMoment(thread, r);
    return { label: m.label, state: m.state, cls: momentClass(thread, r) }; };
  const before = read(0), soon = read(2.5 * 3600e3), after = read(3.5 * 3600e3);
  // An event with this person that has begun and not ended keeps its time and says it has started.
  const other = inCategory('people')[0];
  clockNow = () => base;
  REM.calendar = { events: [{ id: 'm-1', start: new Date(base - 10 * 60e3).toISOString(), end: new Date(base + 50 * 60e3).toISOString(),
                              title: 'Call', calendar: 'google', people: [other.path] }] };
  const running = upcomingMoment({ since, text: 'Call today.' }, other);
  REM.calendar = { events: [] }; clockNow = real;
  return { before, soon, after, running, sameDay: day === agToday(), passed: t('passed'), started: t('started'), at,
           data: (clockNow = () => base, momentData(thread, r)) };
}"""


def test_a_card_time_turns_soon_then_passed_as_the_clock_moves(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(TURNS, isolated_context=False)
        if not got["sameDay"]:
            pytest.skip("the fixture's render time is within 3 hours of midnight in its zone")
        assert got["before"]["state"] == "later" and got["before"]["cls"] == "", got
        assert got["soon"]["state"] == "soon" and got["soon"]["cls"] == " soon", got
        assert got["after"]["state"] == "passed", got
        assert got["after"]["label"].endswith(" · " + got["passed"]), got  # 「今天 14:00 · 已过」, not a stale 「今天 14:00」
        assert got["after"]["cls"] == " passed", got
        assert got["running"]["state"] == "started", got
        assert got["running"]["label"].endswith(" · " + got["started"]), got
        assert got["data"]["data-bucket"] == "later", got  # what the minute tick compares
        assert 0 <= got["at"] - int(got["data"]["data-at"]) < 60e3, got  # the words give HH:MM, so the moment is to the minute
    finally:
        browser.close(); api.stop()


def test_zh_names_the_passed_time_in_chinese(page_file):
    api, browser, page = _open(page_file)
    try:
        page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
        got = page.evaluate("() => [t('passed'), t('started')]", isolated_context=False)
        assert got == ["已过", "已开始"], got
    finally:
        browser.close(); api.stop()


SITES = """() => {
  const team = { path: 'orgs/team-x.md', category: 'orgs', title: 'Team X', text: '# Team X\\n' };
  const person = (path, email) => ({ path, category: 'people', title: path, text: `# ${path}\\n\\n## Contact\\n- Email: ${email}\\n` });
  const site = people => orgWebsite(team, people)?.url || null;
  return {
    student: site([person('people/a.md', 'a@student.uni-example.edu.au'), person('people/b.md', 'b@uni-example.edu.au')]),
    ac: site([person('people/c.md', 'c@example.ac.uk')]),
    work: site([person('people/d.md', 'd@fernhill-labs.example')]),
    free: site([person('people/e.md', 'e@gmail.com')]),
  };
}"""


def test_a_university_mail_domain_is_never_a_teams_website(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(SITES, isolated_context=False)
        assert got["student"] is None, got
        assert got["ac"] is None, got
        assert got["free"] is None, got
        assert got["work"] == "https://fernhill-labs.example", got  # a work domain still names the org's site
    finally:
        browser.close(); api.stop()


REASONS = """() => {
  const course = { path: 'orgs/course-9900.md', category: 'orgs', title: '9900', unit_kind: 'course', kind: 'course', text: '# 9900\\n' };
  return {
    zh: relationReason('上级组织: 课程 9900', course),
    en: relationReason('Parent: Course 9900', course),
    team: relationReason('Organisation: Team 9900-F13D', { path: 'orgs/t.md', category: 'orgs', title: '9900-F13D', text: '' }),
    linked: relationReason('Parent: [[orgs/course-9900.md]] [2]', course),
    markdown: relationReason('上级组织: [课程 9900](../orgs/course-9900.md) [W3]', course),
    real: relationReason('Parent: Course 9900, which the pilot ran inside', course),
  };
}"""


def test_a_reason_that_only_restates_the_target_is_no_reason(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(REASONS, isolated_context=False)
        assert got["zh"] == "", got
        assert got["en"] == "", got
        assert got["team"] == "", got
        assert got["linked"] == "", got  # the org page's own line keeps its link and citation: still only the name
        assert got["markdown"] == "", got
        assert got["real"], got  # a line that says something beyond the name stays a reason
    finally:
        browser.close(); api.stop()
