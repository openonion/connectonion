"""Hand any unfinished row to an agent, watch it in place, and talk with the agent about it (opt in).

Owner, 2026-11-09: «很多未完成的事项，里面没有一个"让 AI 替我完成"之类的按钮。如果我是用户，我就想直接让
Codex 现在就帮我去完成，或者起一个对话之类的». The live page is the Host's own render, and every
/rem/* request goes through the real Host handler (rem_http) to real tasks and conversations; only
Codex and Claude Code are the recorded fakes in tests/fixtures/native_runners. The notebook is invented.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://127.0.0.1:8123"
NATIVE = Path(__file__).resolve().parents[2] / "fixtures" / "native_runners"
SHOTS = os.environ.get("CO_REM_SHOTS")


def _notebook(root):
    from connectonion.rem import night
    from connectonion.rem.config import prepare, read_config
    from connectonion.rem.files import Notebook
    prepare(root)
    book = Notebook(root)
    book.stub_project("projects/fernhill.md", "Fernhill Labs pilot", [])
    book.write("projects/fernhill.md", book.read("projects/fernhill.md").replace("## Open threads\n", (
        "## Open threads\n- You owe Mara a pilot review.\n- Fern owes you the Fernhill Labs contract draft.\n")))
    night.prepare(root, read_config(root))


def _host(root, identity):
    """One request through the Host's own HTTP handler, as co ai serves it."""
    from connectonion.network.host.http_router import handle_http

    def call(method, path, body, cookie):
        headers = [[b"host", b"127.0.0.1:8123"], [b"content-type", b"application/json"], [b"cookie", cookie.encode()]]
        scope = {"type": "http", "method": method, "path": path, "query_string": b"", "headers": headers,
                 "client": ("127.0.0.1", 50000)}
        sent = []

        async def receive():
            return {"body": body, "more_body": False}

        async def send(message):
            sent.append(message)

        # Playwright's sync API holds this thread's event loop; the Host's handler gets a thread of its own.
        with ThreadPoolExecutor(1) as pool:
            pool.submit(asyncio.run, handle_http(scope, receive, send, route_handlers={"rem_root": root, "identity_dir": identity},
                                                 storage=Mock(), trust="careful", start_time=0)).result()
        head = dict((k.decode(), v.decode()) for k, v in sent[0]["headers"])
        return sent[0]["status"], head.get("content-type", "text/plain"), sent[1]["body"]
    return call


@pytest.fixture
def live(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import live_host
    monkeypatch.setenv("CODEX_CMD", str(NATIVE / "fake_codex_app_server.py"))
    monkeypatch.setenv("CLAUDE_CODE_CMD", str(NATIVE / "fake_claude.py"))
    monkeypatch.setenv("FAKE_CODEX_SLEEP", "3")           # long enough to see it working
    monkeypatch.setenv("CONNECTONION_REM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root, identity = tmp_path / "rem", tmp_path / "co"
    identity.mkdir()
    _notebook(root)
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
        page.goto(BASE + "/rem#view=open")
        page.get_by_role("heading", name="Open threads").wait_for()
        yield page, root
        browser.close()
    assert not errors, errors


def _row(page, words):
    return page.locator("ul.threads > li").filter(has_text=words)


def test_a_waiting_row_the_night_never_prepared_is_handed_watched_and_its_result_opened(live):
    page, root = live
    row = _row(page, "Fernhill Labs contract draft")
    assert row.locator(".task-band").count() == 0 and row.get_by_role("button", name="Hand to Codex").is_enabled()
    row.get_by_role("button", name="Hand to Codex").click()
    line = row.locator(".handoff-line")
    line.get_by_text("Codex is working").wait_for(timeout=10000)
    # Taking the task back has its own words; the row's one Mark done stays in the strip (owner, 2026-11-11).
    assert line.get_by_role("button").all_inner_texts() == ["Stop", "Take back from Codex", "Mark done"]
    line.get_by_text("Codex finished").wait_for(timeout=30000)       # it follows the run by itself
    line.get_by_role("button", name="See result").click()
    from patchright.sync_api import expect
    expect(row.locator(".task-output h2")).to_have_text("Pilot review")          # "# Pilot review", rendered
    if SHOTS:
        row.screenshot(path=str(Path(SHOTS) / "hand-row-finished.png"))
    line.get_by_role("button", name="Take back from Codex").click()
    row.get_by_role("button", name="Hand to Claude").wait_for()
    assert not list((root / ".state" / "tasks").glob("do-*/receipt.json"))


def test_talk_with_claude_about_a_row_answers_in_the_page_and_takes_the_next_turn(live):
    page, _ = live
    row = _row(page, "Fernhill Labs contract draft")
    line = row.locator(".handoff-line")
    assert line.evaluate("node => node.getBoundingClientRect().height") < 48      # one line, not four links on two
    assert " ".join(line.inner_text().split()) == "Hand to Codex · Hand to Claude · Talk it over ▾ · Mark done"
    if SHOTS:
        page.evaluate("() => { setInterfaceLanguage('zh'); render(); }", isolated_context=False)
        zh = _row(page, "Fernhill Labs contract draft")
        assert " ".join(zh.locator(".handoff-line").inner_text().split()) == "交给 Codex · 交给 Claude · 聊一聊 ▾ · 标为完成"
        zh.locator(".talk-menu > summary").click()
        menu = zh.locator(".talk-choices")
        assert menu.evaluate("node => document.elementFromPoint(node.getBoundingClientRect().left + 8, node.getBoundingClientRect().bottom - 8)?.closest('.talk-choices') === node")
        box = zh.bounding_box()
        page.screenshot(path=str(Path(SHOTS) / "row-zh-menu.png"),
                        clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"] + 90})
        page.evaluate("() => { setInterfaceLanguage('en'); render(); }", isolated_context=False)
        row, line = _row(page, "Fernhill Labs contract draft"), _row(page, "Fernhill Labs contract draft").locator(".handoff-line")
    line.locator(".talk-menu > summary").click()
    row.get_by_role("button", name="Talk with Claude about this").click()
    talk = row.locator(".talk")
    talk.locator(".talk-turn.agent").first.wait_for(timeout=30000)
    # The reply is Markdown: its fenced block is a code block, never literal backticks.
    first = talk.locator(".talk-turn.agent .agent-text").first
    assert first.locator("pre code").inner_text().strip() == "Hello from Sample!"
    assert "```" not in first.inner_text()
    assert talk.locator(".talk-context summary").inner_text() == "What Claude was given"
    assert talk.locator(".talk-turn.agent p").first.inner_text().strip()
    talk.get_by_role("textbox", name="Your message").fill("Draft the follow-up to Fern, short.")
    talk.get_by_role("button", name="Send").click()
    talk.locator(".talk-turn.owner").filter(has_text="Draft the follow-up to Fern, short.").wait_for()
    talk.locator(".talk-turn.agent").nth(1).wait_for(timeout=30000)
    assert talk.get_by_role("button", name="Send").is_enabled()
    if SHOTS:
        row.screenshot(path=str(Path(SHOTS) / "talk-with-claude.png"))


def test_agent_text_is_markdown_and_no_html_from_the_model_runs(live):
    page, _ = live
    shown = page.evaluate(r"""() => {
      const box = agentText('Plan:\n\n- read `pilot.md`\n- [docs](https://docs.connectonion.com)\n\n```sh\nco rem status\n```\n\n'
        + '<script>window.pwned = 1</script><img src=x onerror="window.pwned = 2"> [bad](javascript:alert(1))', 'projects/fernhill.md');
      document.body.append(box);
      return {pre: box.querySelector('pre code')?.textContent, items: [...box.querySelectorAll('li')].map(li => li.textContent),
        code: box.querySelector('li code')?.textContent, link: box.querySelector('a[href^="https"]')?.getAttribute('href'),
        scripts: box.querySelectorAll('script, img').length, js: box.querySelectorAll('a[href^="javascript"]').length,
        text: box.textContent, pwned: window.pwned || 0};
    }""", isolated_context=False)
    assert shown['pre'] == 'co rem status' and shown['code'] == 'pilot.md'
    assert shown['items'][1] == 'docs' and shown['link'] == 'https://docs.connectonion.com'
    assert shown['scripts'] == 0 and shown['js'] == 0 and shown['pwned'] == 0
    assert '<script>window.pwned = 1</script>' in shown['text']
