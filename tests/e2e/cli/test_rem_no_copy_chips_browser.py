"""No command to copy anywhere, a private project asked about from its page, and Today saying it is behind (opt in).

Owner rule D-60: the reader never asks him to copy a command or a prompt; REM does the work and he
approves. #2910 found command chips left on the reviews page and the knowledge backfill; #2909 lost
the only way to ask about a private project. The live page is the Host's own render and every /rem/*
request goes through the real Host handler to real tasks; only Codex is the recorded fake in
tests/fixtures/native_runners. The notebook is invented.
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
PRIVATE = "projects/private-notes-ab12.md"


def _notebook(root):
    from connectonion.rem import night, reviews
    from connectonion.rem.config import prepare, read_config
    from connectonion.rem.files import Notebook
    prepare(root)
    book = Notebook(root)
    book.stub_project(PRIVATE, "Private notes", [])
    book.stub_project("projects/fernhill.md", "Fernhill Labs pilot", [])
    book.write("projects/fernhill.md", book.read("projects/fernhill.md").replace(
        "## Open threads\n", "## Open threads\n- Fern owes you the Fernhill Labs contract draft.\n"))
    book.write("people/mara-quill.md", "# Mara Quill\n")
    book.write("people/fern-vale.md", "# Fern Vale\n")
    reviews.propose(root, "link", ["people/mara-quill.md", "people/fern-vale.md"],
                    "Is Mara Quill the same person as Fern Vale?", "Same phone in two signatures.")
    night.prepare(root, read_config(root))


def _host(root, identity):
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
    monkeypatch.setenv("FAKE_CODEX_SLEEP", "2")
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
        page.goto(BASE + "/rem")
        page.locator("#main").wait_for()
        yield page, root
        browser.close()
    assert not errors, errors


def _no_command(page):
    main = page.locator("#main")
    assert main.locator(".cmd, code").count() == 0
    assert "co rem " not in main.inner_text()


def test_reviews_and_knowledge_offer_actions_not_commands(live):
    page, _ = live
    page.goto(BASE + "/rem#reviews=1")
    review = page.locator("section.review").filter(has_text="Is Mara Quill the same person as Fern Vale?")
    review.get_by_role("button", name="Yes").wait_for()
    _no_command(page)
    if SHOTS:
        review.screenshot(path=str(Path(SHOTS) / "reviews-actions.png"))
    review.get_by_role("button", name="Yes").click()
    review.get_by_text("Recorded: Yes").wait_for()
    page.goto(BASE + "/rem#c=knowledge")
    page.get_by_text("REM files knowledge from your records on its night run.").wait_for()
    _no_command(page)
    if SHOTS:
        page.locator("#main").screenshot(path=str(Path(SHOTS) / "knowledge-empty.png"))


def test_ask_codex_to_look_investigates_a_private_project_in_place(live):
    page, root = live
    page.goto(BASE + "/rem#r=" + PRIVATE.replace("/", "%2F"))
    box = page.locator(".missing")
    box.get_by_role("button", name="Ask Codex to look").wait_for()
    assert " ".join(box.locator(".handoff-line").inner_text().split()) == "Ask Codex to look · Ask Claude to look"
    _no_command(page)
    if SHOTS:
        box.screenshot(path=str(Path(SHOTS) / "ask-codex-before.png"))
    box.get_by_role("button", name="Ask Codex to look").click()
    line = box.locator(".handoff-line")
    line.get_by_text("Codex is working").wait_for(timeout=10000)
    line.get_by_text("Codex finished").wait_for(timeout=30000)
    line.get_by_role("button", name="See result").click()
    box.locator(".task-output").wait_for()
    if SHOTS:
        box.screenshot(path=str(Path(SHOTS) / "ask-codex-finished.png"))
        page.evaluate("() => { setInterfaceLanguage('zh'); render(); }", isolated_context=False)
        page.locator(".missing").screenshot(path=str(Path(SHOTS) / "ask-codex-zh.png"))
        page.evaluate("() => { setInterfaceLanguage('en'); render(); }", isolated_context=False)
    receipts = list((root / ".state" / "tasks").glob("do-*/receipt.json"))
    assert len(receipts) == 1 and PRIVATE in receipts[0].read_text()


def test_a_held_redraw_says_updates_are_waiting_and_draws_when_the_field_is_left(live):
    page, _ = live
    page.goto(BASE + "/rem")
    page.locator("#main").wait_for()
    page.locator("#q").focus()
    page.evaluate("() => window.dispatchEvent(new Event('focus'))", isolated_context=False)
    mark = page.get_by_role("button", name="Updates waiting")
    mark.wait_for()
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "updates-waiting.png"))
    page.evaluate("() => { setInterfaceLanguage('zh'); document.getElementById('updates-waiting').textContent = t('Updates waiting'); }",
                  isolated_context=False)
    assert page.locator("#updates-waiting").inner_text() == "有更新"
    page.evaluate("() => setInterfaceLanguage('en')", isolated_context=False)
    page.locator("#q").blur()
    mark.wait_for(state="detached", timeout=5000)
