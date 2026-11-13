"""«全部翻译成中文» in the live reader (#2999, opt in): one worded button, in Settings and beside
«中文版还没好，先看原文», starts the job `co rem translate` runs, says «已翻译 N / M» as it goes, and stops.

The owner, 2026-11-13: «命令行里应该有一个"一键翻译所有页面"的功能 … 如果有这么一个命令行和这么一个 button
的话，是不是会好一点？» Every /rem/* request goes through the real Host handler (rem_http), with its loopback,
cookie and JSON-only rules; the only fake is the translator these tests always use (runner.run_task). The
notebook is invented: one English page, one Chinese, one mixed.
"""

import os
import re
import threading
from pathlib import Path

import pytest

from tests.e2e.cli.test_rem_hand_any_row_browser import BASE, _host
from tests.unit.test_rem_translate_every import PAGES, fake_translator

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
SHOTS = os.environ.get("CO_REM_SHOTS")


def _notebook(root):
    from connectonion.rem import night
    from connectonion.rem.config import prepare, read_config, set_config
    prepare(root)
    for record, text in PAGES.items():
        (root / record).write_text(text)
    set_config(root, ["languages", "zh,en"])
    set_config(root, ["limits.workers", "1"])
    night.prepare(root, read_config(root))


@pytest.fixture
def live(tmp_path, monkeypatch, request):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import live_host
    gate = threading.Event()
    if not getattr(request, "param", False):
        gate.set()
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    monkeypatch.setattr("connectonion.rem.runner.run_task", fake_translator(calls, gate))
    monkeypatch.setenv("CONNECTONION_REM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root, identity = tmp_path / "rem", tmp_path / "co"
    identity.mkdir()
    _notebook(root)
    cookie = "co_rem=" + live_host.reader_token(identity)
    call, errors, posts, faults = _host(root, identity), [], [], []

    def serve(route):
        req = route.request
        path = req.url[len(BASE):].split("#")[0].split("?")[0]
        if not path.startswith("/rem"):
            return route.abort()
        # A rebuild the language switch started would reload the page mid-test and close Settings.
        if path == "/rem/version":
            return route.fulfill(status=404, body="")
        if path == "/rem/translate-all":
            posts.append((req.method, req.headers.get("content-type")))
            fault = faults.pop(0) if faults else "pass"
            # A request is refused (a status code), never arrives ("abort"), or goes through ("pass").
            if fault != "pass":
                return route.abort() if fault == "abort" else route.fulfill(
                    status=fault, body='{"error": "REM is busy"}', content_type="application/json")
        status, kind, body = call(req.method, path, (req.post_data or "").encode(), cookie)
        return route.fulfill(status=status, body=body, content_type=kind.split(";")[0])

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE + "/rem")
        page.locator("#main").wait_for()
        page.evaluate("() => { setInterfaceLanguage('zh'); render(); }", isolated_context=False)
        page.faults = faults
        yield page, root, calls, gate, posts
        gate.set()
        browser.close()
    assert not errors, errors


def _settings(page):
    page.evaluate("() => openSettings()", isolated_context=False)
    return page.locator("#settings .translate-all")


@pytest.mark.parametrize("width", [1440, 390])
def test_the_settings_button_translates_every_page_and_says_how_far_it_is(live, width):
    from patchright.sync_api import expect
    page, root, calls, _, posts = live
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    control = _settings(page)
    # The cost in words on the button itself: two pages need a model turn, the Chinese one does not.
    go = control.get_by_role("button", name="全部翻译成中文（2 页）")
    expect(go).to_be_visible()
    from connectonion.rem.files import Notebook
    total = len(Notebook(root).list())
    expect(control.locator(".ta-state")).to_have_text(f"已翻译 {total - 2} / {total}")    # the Chinese page needs no turn
    assert "null" not in page.locator("#settings").inner_text()                     # rows only a live page has
    if SHOTS:
        page.locator("#settings").screenshot(path=str(Path(SHOTS) / f"settings-translate-all-{width}.png"))
    go.click()
    expect(control.locator(".ta-state")).to_have_text("所有页面都已是中文。", timeout=20000)
    assert sorted(calls) == ["# Avery Lin", "# Fernhill pilot"]
    assert posts and all(method == "POST" and kind == "application/json" for method, kind in posts)
    # D-60: no command anywhere (the sidebar's brand "co rem" is a name, not a command).
    assert not re.search(r"co rem [a-z-]+", page.locator("body").inner_text())
    assert "co rem" not in page.locator("#settings").inner_text()
    from connectonion.rem import translate
    assert all(translate.current(root, record, "zh") for record in PAGES)


@pytest.mark.parametrize("live", [True], indirect=True)
def test_progress_shows_while_it_runs_and_stop_leaves_the_pages_not_begun(live):
    from patchright.sync_api import expect
    page, root, calls, gate, _ = live
    page.goto(BASE + "/rem#r=people%2Favery-lin.md")
    line = page.locator("#main .translation-line")
    expect(line).to_contain_text("中文版还没好，先看原文")
    # Beside the line, the same worded button; no command to copy anywhere (D-60).
    line.get_by_role("button", name="全部翻译成中文（2 页）").click()
    stop = line.get_by_role("button", name="停止翻译")
    expect(stop).to_be_visible(timeout=10000)
    from connectonion.rem.files import Notebook
    total = len(Notebook(root).list())
    expect(line.locator(".ta-state")).to_have_text(f"已翻译 {total - 2} / {total}")
    if SHOTS:
        line.screenshot(path=str(Path(SHOTS) / "line-translate-all-running.png"))
    stop.click()
    expect(line.locator(".ta-state")).to_contain_text("正在停止")
    gate.set()
    expect(line.locator(".ta-state")).to_have_text(f"已停止。 已翻译 {total - 1} / {total}", timeout=20000)
    expect(line.get_by_role("button", name="全部翻译成中文（1 页）")).to_be_visible()     # it can be started again
    assert len(calls) == 1
    assert not re.search(r"co rem [a-z-]+", page.locator("body").inner_text()) and "co rem" not in line.inner_text()


def test_a_refused_start_says_so_in_words_and_a_dropped_poll_is_retried(live):
    from patchright.sync_api import expect
    page, root, calls, _, _ = live
    control = _settings(page)
    go = control.get_by_role("button", name="全部翻译成中文（2 页）")
    expect(go).to_be_visible()
    page.faults.append(409)
    go.click()
    expect(control.locator(".ta-state")).to_have_text("翻译请求没被接受，请稍后再试。")
    assert not calls
    # Started for real, its next status poll is lost on the way: the line says so and asks again.
    # Then a status poll is refused (409): the job keeps its running line and the poll goes on.
    page.faults.extend(["pass", "abort", 409])
    control.get_by_role("button", name="全部翻译成中文").click()
    expect(control.locator(".ta-state")).to_have_text("所有页面都已是中文。", timeout=30000)
    assert sorted(calls) == ["# Avery Lin", "# Fernhill pilot"]


@pytest.mark.parametrize("live", [True], indirect=True)
def test_a_refused_status_poll_keeps_the_running_line_and_polling(live):
    from patchright.sync_api import expect
    page, root, calls, gate, _ = live
    control = _settings(page)
    control.get_by_role("button", name="全部翻译成中文（2 页）").click()
    expect(control.get_by_role("button", name="停止翻译")).to_be_visible(timeout=10000)
    page.faults.extend([409, 409])
    page.wait_for_timeout(3500)                                       # two refused polls
    assert control.locator(".ta-state").inner_text() != "翻译请求没被接受，请稍后再试。"
    expect(control.get_by_role("button", name="停止翻译")).to_be_visible()
    gate.set()
    expect(control.locator(".ta-state")).to_have_text("所有页面都已是中文。", timeout=20000)
