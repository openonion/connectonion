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
           in30: t('in {n} min', { n: 30 }),
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
        assert got["soon"]["label"] == got["in30"], got  # the hour before counts down in words (art director on #3423)
        assert got["after"]["state"] == "passed", got
        assert got["after"]["label"].endswith(" · " + got["passed"]), got  # 「今天 14:00 · 已过」, not a stale 「今天 14:00」
        assert got["after"]["cls"] == "", got  # after it the card keeps its weight: only 「已过」 is muted
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


# A card past its time stays where it was and as heavy as it was: the debt is still owed. Only the word 已过 is muted.
# The first card's person gets a calendar event; the queue is drawn before it, and again with the clock 2 hours on.
ORDER = """() => {
  const who = () => [...document.querySelectorAll('#main .today-who')].map(n => n.textContent);
  const first = document.querySelector('#main .qhead .today-who')?.textContent;
  const r = inCategory('people').find(p => p.title === first || pageName(p) === first);
  const base = Date.parse(REM.as_of), real = clockNow;
  REM.calendar = { events: [{ id: 'e-1', start: new Date(base + 20 * 60e3).toISOString(), end: new Date(base + 50 * 60e3).toISOString(),
                              title: 'Call', calendar: 'google', people: [r.path] }] };
  clockNow = () => base; render(); const soonOrder = who();
  const soonAge = document.querySelector('#main .qhead .qage');
  const soon = { text: soonAge.textContent, cls: soonAge.className, bucket: soonAge.dataset.bucket };
  clockNow = () => base + 2 * 3600e3; render(); const pastOrder = who();
  const age = document.querySelector('#main .qhead .qage'), mark = age.querySelector('.age-passed');
  const out = { soonOrder, pastOrder, soon, past: { cls: age.className, text: age.textContent,
    markColor: mark && getComputedStyle(mark).color, ageColor: getComputedStyle(age).color,
    markWeight: mark && getComputedStyle(mark).fontWeight, ageWeight: getComputedStyle(age).fontWeight }, in20: t('in {n} min', { n: 20 }) };
  clockNow = real; REM.calendar = { events: [] }; render(); return out;
}"""


def test_a_passed_card_keeps_its_place_and_weight_and_only_mutes_the_word(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(ORDER, isolated_context=False)
        assert got["soon"]["text"].startswith(got["in20"]), got  # 「20 分钟后 · 已等 …」
        assert "soon" in got["soon"]["cls"] and got["soon"]["bucket"] == "soon", got
        assert got["pastOrder"] == got["soonOrder"], got  # no reordering once it has passed
        # The event ended an hour ago: the card falls back to its words, which name no time, so it is the age alone,
        # still on the same card in the same place.
        assert "soon" not in got["past"]["cls"] and "late" not in got["past"]["cls"], got
    finally:
        browser.close(); api.stop()


MUTED = """() => {
  const node = el('span', { class: 'qage' }, ageNodes('Today 14:00 · ' + t('passed') + ' · ' + t('waiting {age}', { age: '14 days' })));
  const head = document.querySelector('#main .qhead'); head.appendChild(node);
  const mark = node.querySelector('.age-passed');
  const out = { text: node.textContent, hasMark: !!mark, markWeight: mark && getComputedStyle(mark).fontWeight,
                ageWeight: getComputedStyle(node).fontWeight, plain: ageNodes('Today 14:00').length };
  node.remove(); return out;
}"""


def test_only_the_word_passed_is_muted(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(MUTED, isolated_context=False)
        assert got["hasMark"] and got["text"].startswith("Today 14:00 · "), got
        assert int(got["markWeight"]) < int(got["ageWeight"]), got  # the time keeps the card's weight; 已过 is lighter
        assert got["plain"] == 1, got  # a time that has not passed is one plain text node, as before
    finally:
        browser.close(); api.stop()


ROLES = """() => { setInterfaceLanguage('zh'); const w = v => labelWord(v);
  return { head: w('Head of Partnerships'), sales: w('Sales Director'), ops: w('Operations Manager'), eng: w('Senior Software Engineer'),
           fc: w('Founder & CEO'), cc: w('Co-founder and CTO'), coo: w('COO'), vp: w('VP of Marketing'), md: w('Managing Director'),
           unknown: w('Chief Vibes Wrangler'), team: w('team member') }; }"""


def test_common_job_titles_are_translated_not_marked_original(page_file):
    api, browser, page = _open(page_file)
    try:
        got = page.evaluate(ROLES, isolated_context=False)
        assert got == {"head": "合作负责人", "sales": "销售总监", "ops": "运营经理", "eng": "高级软件工程师",
                       "fc": "创始人兼CEO", "cc": "联合创始人兼CTO", "coo": "COO", "vp": "市场副总裁", "md": "董事总经理",
                       "unknown": "Chief Vibes Wrangler", "team": "团队成员"}, got
    finally:
        browser.close(); api.stop()
