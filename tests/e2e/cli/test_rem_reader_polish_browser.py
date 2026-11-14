"""Reader polish for 1.9.3: reviews decided in place, Today without zero states, the phone list, the translation mark.

Owner rules (decision ledger): never ask him to copy a command or go to a terminal (D-60); one obvious
next step (D-20); one language per line, the reader's own (D-70..73, D-103); one number says one thing
(TOP10 #9). The page is served over http from a Playwright route so the reader's fetch() reaches a stub
that lives here, never in the reader. The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
GREEN = ("rgb(34, 210, 122)", "rgb(59, 227, 143)")
LINK_ID, QUESTION_ID = "a1" * 16, "b2" * 16
REVIEWS = r'''([live, language]) => {
  REM.live = live;
  REM.reviews = [
    {id: '%s', kind: 'link', subjects: ['people/mara-ostrowski.md', 'people/tomas-reyes.md'], status: 'pending',
     question: 'Is Mara Ostrowski the same person as Tomas Reyes?', basis: 'Both sign with the same phone number.', created_at: '2026-09-30T08:00:00Z'},
    {id: '%s', kind: 'question', subjects: ['projects/harbour.md'], status: 'pending',
     question: 'Which budget does the Harbour pilot draw on?', basis: 'Two mails name different budgets.', created_at: '2026-09-30T08:00:00Z'}];
  setInterfaceLanguage(language); location.hash = 'reviews=1'; render();
}''' % (LINK_ID, QUESTION_ID)


@pytest.fixture
def reader(tmp_path, monkeypatch):
    """The fixture notebook's reader at http://rem.test/, with every /rem/* request answered by `answers`."""
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    html = rem_reader.render(build(tmp_path / "rem", frozen), local=True)
    calls, answers, errors = [], {}, []

    def serve(route):
        request = route.request
        path = request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            body = json.loads(request.post_data or "{}") if request.method == "POST" else None
            calls.append((path, body))
            answer = answers.get(path, (200, {}))
            status, reply = answer(body) if callable(answer) else answer
            return route.fulfill(status=status, body=json.dumps(reply), content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".night-card .count").wait_for()
        yield page, calls, answers
        browser.close()
    assert not errors, errors


def _no_command(page):
    """No copy chip, no code block, no terminal instruction: D-60."""
    main = page.locator("#main")
    assert main.locator(".cmd, code, pre").count() == 0
    text = main.inner_text()
    assert "co rem" not in text and "终端" not in text and "terminal" not in text.lower(), text


def _decided(body):
    verdict = body["verdict"]
    return 200, {"id": body["id"], "status": {"yes": "accepted", "no": "rejected", "answer": "answered"}[verdict],
                 "author": "owner", "response": body.get("response", "")}


def test_a_link_is_decided_in_place_with_quiet_buttons(reader):
    page, calls, answers = reader
    answers["/rem/review"] = _decided
    page.evaluate(REVIEWS, [True, "zh"], isolated_context=False)
    _no_command(page)
    box = page.locator(".review").filter(has_text="Is Mara Ostrowski the same person")
    buttons = box.locator(".review-acts").get_by_role("button")
    assert buttons.all_inner_texts() == ["是", "不是", "不确定"]
    # None is irreversible-looking: no button carries the one green the reader keeps for Send.
    assert all(button.evaluate("n => getComputedStyle(n).backgroundColor") not in GREEN for button in buttons.all())
    box.get_by_role("button", name="是", exact=True).click()
    box.get_by_text("已记下：是").wait_for()
    assert [call for call in calls if call[0] == "/rem/review"] == [("/rem/review", {"id": LINK_ID, "verdict": "yes"})]
    assert box.locator(".review-acts button").count() == 0
    assert box.locator(".pill").inner_text() == "已接受"


def test_a_question_takes_the_owners_answer_and_not_sure_posts_nothing(reader):
    page, calls, answers = reader
    answers["/rem/review"] = _decided
    page.evaluate(REVIEWS, [True, "zh"], isolated_context=False)
    box = page.locator(".review").filter(has_text="Which budget does the Harbour pilot")
    box.get_by_role("button", name="不确定").click()
    assert box.get_by_text("先放着，这条还在等你。").is_visible()
    assert not [call for call in calls if call[0] == "/rem/review"]
    box.get_by_role("button", name="改主意").click()
    box.get_by_label("你的回答").fill("The innovation fund.")
    box.get_by_role("button", name="记下回答").click()
    box.get_by_text("已记下你的回答").wait_for()
    assert [call for call in calls if call[0] == "/rem/review"] == [
        ("/rem/review", {"id": QUESTION_ID, "verdict": "answer", "response": "The innovation fund."})]
    assert "The innovation fund." in box.inner_text()


@pytest.mark.parametrize("language, line", [("zh", "你：The innovation fund."), ("en", "You: The innovation fund.")])
def test_a_decided_review_names_the_owner_in_the_readers_language(reader, language, line):
    page, _, _ = reader
    page.evaluate(REVIEWS.replace("render();\n}", "REM.reviews[1] = {...REM.reviews[1], status: 'answered', author: 'owner', response: 'The innovation fund.'}; render();\n}"),
                  [False, language], isolated_context=False)
    response = page.locator(".review .response")
    assert response.inner_text() == line and "owner" not in response.inner_text()


@pytest.mark.parametrize("status, words", [(409, "这条已经有人判断过了，刷新看看。"), (404, "这条已经不在了，刷新一下。"), (401, "登录过期，刷新页面。"),
                                           (400, "这条判断没能记下，刷新后再试。"), (500, "REM 暂时没回应，过会儿再试。")])
def test_a_refused_decision_is_said_in_plain_words(reader, status, words):
    page, _, answers = reader
    answers["/rem/review"] = (status, {"error": "Review does not exist or has already been decided"})
    page.evaluate(REVIEWS, [True, "zh"], isolated_context=False)
    box = page.locator(".review").first
    box.get_by_role("button", name="不是").click()
    box.get_by_text(words).wait_for()
    assert "Review does not exist" not in box.inner_text()
    assert box.locator(".review-acts button").count() == 3  # nothing was recorded, so the choice stays


@pytest.mark.parametrize("language, line", [("zh", "这是快照，判断要在实时页面里做。"),
                                            ("en", "This is a snapshot; decide these on the live page.")])
def test_a_snapshot_has_one_plain_line_and_no_buttons(reader, language, line):
    page, _, _ = reader
    page.evaluate(REVIEWS, [False, language], isolated_context=False)
    _no_command(page)
    assert page.locator("#main").get_by_text(line, exact=True).count() == 1
    assert page.locator(".review button, .review textarea").count() == 0


@pytest.mark.parametrize("live", [True, False])
@pytest.mark.parametrize("view", ["view=graph", "c=knowledge"])
def test_the_graph_files_knowledge_on_the_night_run_without_a_command(reader, live, view):
    page, _, _ = reader
    page.evaluate("""([live, view]) => { REM.live = live; REM.records = REM.records.filter(r => r.category !== 'knowledge');
      setInterfaceLanguage('zh'); location.hash = view; render(); }""", [live, view], isolated_context=False)
    page.wait_for_timeout(300)
    _no_command(page)
    if view == "c=knowledge":
        assert "REM 会在夜里那一轮从已有记录里整理知识。" in page.locator("#main").inner_text()


def test_today_shows_no_zero_count_and_no_number_twice(reader):
    page, _, _ = reader
    page.evaluate("() => { REM.live = true; REM.approval_outcomes = []; setInterfaceLanguage('zh'); render(); }", isolated_context=False)
    header = page.locator("#main")
    assert not page.locator("#approve-all").is_visible()
    assert not re.search(r"(?<!\d)0 ?(件|项|items)", header.inner_text()), header.inner_text()
    # The sidebar's 等你处理 count is the nav; the first screen does not say the same number again.
    total = page.locator("#nav .n.waiting").inner_text()
    assert f"{total} 件等你处理" not in header.inner_text()
    assert total not in re.findall(r"\d+", page.locator(".others").inner_text())
    page.locator(".others .waiting-more").click()
    assert page.evaluate("location.hash", isolated_context=False) == "#view=open"


@pytest.mark.parametrize("language, evidence, line", [
    ("zh", "Turn exceeded 3 hours; the next fire continues the round", "昨夜有一轮跑得太久，已停下；下一轮会继续。"),
    ("en", "Turn exceeded 3 hours; the next fire continues the round", "One round last night ran too long and was stopped; the next round continues."),
    ("zh", "OSError: [Errno 28] No space left on device", "最近两轮定时任务都没有跑完；REM 会自动重试。"),
    ("en", "OSError: [Errno 28] No space left on device", "The last two scheduled rounds did not finish; REM retries them automatically.")])
def test_a_run_banner_speaks_the_readers_language(reader, language, evidence, line):
    page, _, _ = reader
    page.evaluate("""([language, evidence]) => { REM.status = {...(REM.status || {}), schedule_failure: {code: 'repeated_failure', evidence}};
      setInterfaceLanguage(language); render(); }""", [language, evidence], isolated_context=False)
    banner = page.locator("#main .schedule-failure")
    assert banner.inner_text() == line
    if language == "zh":
        assert not re.search(r"[A-Za-z]{4,}", banner.inner_text())


def test_waiting_on_you_gives_the_body_the_phone_width(reader):
    page, _, _ = reader
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("() => { setInterfaceLanguage('zh'); location.hash = 'view=open'; render(); }", isolated_context=False)
    row = page.locator(".task-band .thread").first
    what, when = row.locator(".what"), row.locator(".when")
    assert what.bounding_box()["width"] >= 320, what.bounding_box()
    # The date sits under the title, not beside it.
    assert when.bounding_box()["y"] >= what.bounding_box()["y"] + what.bounding_box()["height"] - 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
    assert page.evaluate("""() => [...document.querySelectorAll('.task-band .thread *')]
      .every(n => n.getBoundingClientRect().right <= innerWidth + 0.5)""", isolated_context=False)


@pytest.mark.parametrize("path, head", [("people/mara-ostrowski.md", ".person-head"), ("projects/harbour.md", ".page-head")])
def test_a_pending_translation_is_a_quiet_worded_line_under_the_header(reader, path, head):
    page, calls, _ = reader
    page.evaluate("""path => { REM.live = true; delete byPath(path).translations?.zh; setInterfaceLanguage('zh');
      location.hash = 'r=' + encodeURIComponent(path); render(); }""", path, isolated_context=False)
    h1 = page.locator("#main h1").first
    h1.wait_for()
    # Opening a page only moves it up the nightly queue: nothing is translating it now, so the
    # line says the page is in its original language, never a "translating" that never ends.
    assert page.locator("#main").get_by_text(re.compile("^(翻译中|翻译待处理)$")).count() == 0
    # The owner read the old 原文 chip above the name as jargon (sprint 15): it is gone from the header.
    assert page.locator(f"#main {head} .lang-status, #main .hero-marks .lang-status, #main .eyebrow .lang-status").count() == 0
    line = page.locator("#main .translation-line")
    # #2999 adds the bulk action beside the D-103 notice; the notice itself stays quiet.
    assert line.count() == 1
    assert line.evaluate("n => n.firstChild.textContent") == "中文版还没好，先看原文"
    assert line.get_by_role("button").all_inner_texts() == ["全部翻译成中文"]
    assert line.get_attribute("title") in ("已排入下一轮翻译", "翻译待处理，后台更新未开启")
    assert ("/rem/translation-request", {"page": path, "language": "zh"}) in calls   # still asked for, once
    assert line.get_attribute("role") is None                       # not announced again on every render
    meta = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--s-meta').trim()", isolated_context=False)
    assert line.evaluate("n => getComputedStyle(n).fontSize") == meta
    box, header = line.bounding_box(), page.locator(f"#main {head}").first.bounding_box()
    assert box["y"] >= header["y"] + header["height"] - 1             # under the header, by the body
    assert page.locator("#main > p[role=status]").filter(has_text="翻译中").count() == 0
