"""Contract tests for the internal 1.8 Patchright async browser core.

The public synchronous BrowserAutomation remains unchanged until #500. These
tests prove the new core itself is genuinely async, preserves per-session tabs,
and cleans up deterministically before #499 puts concurrent IPC in front of it.
"""

import asyncio
import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import _async_browser as async_mod
from connectonion.useful_tools.browser_tools.browser import BrowserAutomation


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    async def press(self, key):
        self.pressed.append(key)


class FakeLocator:
    def __init__(self, page, selector, index=None):
        self.page = page
        self.selector = selector
        self.index = index

    async def count(self):
        return self.page.selector_counts.get(self.selector, 1)

    def nth(self, index):
        return FakeLocator(self.page, self.selector, index=index)

    async def click(self, force=False):
        self.page.clicked.append((self.selector, self.index))

    async def inner_text(self):
        return self.page.text_by_selector.get(self.selector, f"text:{self.index}")

    async def fill(self, text):
        self.page.filled.append((self.selector, self.index, text))

    async def set_input_files(self, path):
        self.page.uploaded.append((self.selector, self.index, path))


class FakePage:
    def __init__(self, idx=1):
        self.idx = idx
        self.url = "about:blank"
        self.closed = False
        self.close_calls = 0
        self.goto_calls = []
        self.waits = []
        self.viewport = None
        self.keyboard = FakeKeyboard()
        self.focused = {"tag": "body", "is_editable": False, "sensitive": False}
        self.selector_counts = {}
        self.text_by_selector = {"body": "page body"}
        self.clicked = []
        self.filled = []
        self.uploaded = []
        self.name = ""
        self.frames = [self]
        self.waited_selectors = []
        self.evaluate_calls = []
        self.evaluate_result = None
        self.file_chooser = FakeFileChooser()
        self.file_chooser_timeouts = []

    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    async def set_viewport_size(self, viewport):
        self.viewport = viewport

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    async def wait_for_selector(self, selector, **kwargs):
        self.waited_selectors.append((selector, kwargs))

    def is_closed(self):
        return self.closed

    async def close(self):
        self.close_calls += 1
        self.closed = True

    def locator(self, selector):
        return FakeLocator(self, selector)

    def expect_file_chooser(self, timeout=0):
        self.file_chooser_timeouts.append(timeout)
        return FakeFileChooserContext(self.file_chooser)

    async def evaluate(self, script, arg=None):
        if "document.activeElement" in script:
            return dict(self.focused)
        self.evaluate_calls.append((script, arg))
        return self.evaluate_result if self.evaluate_result is not None else {"arg": arg}

    async def screenshot(self, **kwargs):
        return b"png"


class FakeFileChooser:
    def __init__(self):
        self.files = []

    async def set_files(self, path):
        self.files.append(path)


class FakeFileChooserContext:
    def __init__(self, chooser):
        self.chooser = chooser

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @property
    def value(self):
        async def resolve():
            return self.chooser

        return resolve()


class FakeFrame(FakePage):
    def __init__(self, result, *, url="https://example.com/frame", name=""):
        super().__init__()
        self.url = url
        self.name = name
        self.frames = []
        self.evaluate_result = result


class FakeContext:
    def __init__(self, page_factory=FakePage):
        self.page_factory = page_factory
        self.pages_created = []
        self.closed = False
        self.cookies_added = []
        self.storage_paths = []

    async def new_page(self):
        page = self.page_factory(len(self.pages_created) + 1)
        self.pages_created.append(page)
        return page

    async def cookies(self):
        if self.closed:
            raise RuntimeError("closed")
        return []

    async def add_cookies(self, cookies):
        self.cookies_added.extend(cookies)

    async def storage_state(self, path):
        self.storage_paths.append(path)

    async def close(self):
        self.closed = True
        for page in self.pages_created:
            page.closed = True


class FakeChromium:
    def __init__(self, context):
        self.context = context
        self.launch_kwargs = None

    async def launch_persistent_context(self, profile, **kwargs):
        self.profile = profile
        self.launch_kwargs = kwargs
        return self.context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakeManager:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
        return self.playwright


def install_fake_runtime(monkeypatch, tmp_path, context=None):
    context = context or FakeContext()
    playwright = FakePlaywright(context)
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_mod, "_profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(async_mod, "find_system_chrome", lambda: "/fake/chrome")
    return context, playwright


def test_async_core_has_no_sync_patchright_dependency():
    source = Path(async_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "patchright.sync_api" not in imported_modules
    assert not any(
        isinstance(node, ast.Name) and node.id == "sync_playwright"
        for node in ast.walk(tree)
    )
    for method in (
        "open_browser",
        "go_to",
        "get_text",
        "keyboard_press",
        "take_screenshot",
        "close",
    ):
        assert inspect.iscoroutinefunction(getattr(async_mod.AsyncBrowserCore, method))


@pytest.mark.asyncio
async def test_open_reuses_one_async_context_and_seeds_before_navigation(monkeypatch, tmp_path):
    seed = tmp_path / "state.json"
    seed.write_text('{"cookies":[{"name":"sid","value":"one","domain":"example.com","path":"/"}]}')
    context, playwright = install_fake_runtime(monkeypatch, tmp_path)
    browser = async_mod.AsyncBrowserCore(headless=True, seed_state=str(seed))

    first = await browser.open_browser()
    second = await browser.open_browser()

    assert "Browser opened" in first
    assert "already open" in second
    assert len(context.pages_created) == 1
    assert context.cookies_added[0]["name"] == "sid"
    assert playwright.chromium.launch_kwargs["no_viewport"] is True
    assert "--use-mock-keychain" in playwright.chromium.launch_kwargs["ignore_default_args"]
    assert browser.page.viewport == {"width": 1920, "height": 1200}

    await browser.close()
    assert context.pages_created[0].close_calls == 0
    assert context.pages_created[0].closed is True
    assert context.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_isolated_runtime_can_keep_chromes_mock_keychain(monkeypatch, tmp_path):
    _, playwright = install_fake_runtime(monkeypatch, tmp_path)
    browser = async_mod.AsyncBrowserCore(headless=True, use_mock_keychain=True)

    await browser.open_browser()

    assert "--use-mock-keychain" not in playwright.chromium.launch_kwargs["ignore_default_args"]
    await browser.close()


@pytest.mark.asyncio
async def test_first_session_adopts_the_persistent_context_page():
    initial_page = FakePage()
    context = FakeContext()
    context.pages = [initial_page]
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context

    await browser._ensure_page(None)

    assert browser.page is initial_page
    assert context.pages_created == []


@pytest.mark.asyncio
async def test_contextvar_sessions_make_progress_on_independent_tabs():
    both_started = asyncio.Event()
    started = set()

    class ConcurrentPage(FakePage):
        async def goto(self, url, **kwargs):
            started.add(self.idx)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            await super().goto(url, **kwargs)

    browser = async_mod.AsyncBrowserCore()
    browser.browser = FakeContext(ConcurrentPage)

    async def navigate(session, url):
        browser._bind_session(session)
        return await browser.go_to(url, purpose="concurrency test", who=session)

    results = await asyncio.gather(
        navigate("A", "a.example"),
        navigate("B", "b.example"),
    )

    assert results == ["Navigated to https://a.example", "Navigated to https://b.example"]
    assert browser._pages["A"] is not browser._pages["B"]


@pytest.mark.asyncio
async def test_same_tab_operations_are_serialized():
    active = 0
    max_active = 0

    class SerialPage(FakePage):
        async def goto(self, url, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            await super().goto(url, **kwargs)
            active -= 1

    browser = async_mod.AsyncBrowserCore()
    browser.browser = FakeContext(SerialPage)
    browser._bind_session("one")
    browser._tab_meta["one"] = {"purpose": "test", "who": "tester"}

    await asyncio.gather(browser.go_to("one.example"), browser.go_to("two.example"))

    assert max_active == 1


@pytest.mark.asyncio
async def test_cancelled_launch_closes_partial_context_and_driver(monkeypatch, tmp_path):
    page_started = asyncio.Event()

    class BlockingContext(FakeContext):
        async def new_page(self):
            page_started.set()
            await asyncio.Event().wait()

    context, playwright = install_fake_runtime(monkeypatch, tmp_path, BlockingContext())
    browser = async_mod.AsyncBrowserCore()
    task = asyncio.create_task(browser.open_browser())
    await page_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert context.closed is True
    assert playwright.stopped is True
    assert browser.browser is None
    assert browser.playwright is None


@pytest.mark.asyncio
async def test_cancel_during_driver_start_waits_for_driver_then_stops_it(monkeypatch, tmp_path):
    start_entered = asyncio.Event()
    release_start = asyncio.Event()
    context = FakeContext()
    playwright = FakePlaywright(context)

    class BlockingManager:
        async def start(self):
            start_entered.set()
            await release_start.wait()
            return playwright

    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", BlockingManager)
    monkeypatch.setattr(async_mod, "_profile_dir", lambda: tmp_path / "profile")
    browser = async_mod.AsyncBrowserCore()
    opening = asyncio.create_task(browser.open_browser())
    await start_entered.wait()

    opening.cancel()
    await asyncio.sleep(0)
    assert opening.done() is False

    release_start.set()
    with pytest.raises(asyncio.CancelledError):
        await opening
    assert playwright.stopped is True
    assert browser.playwright is None


@pytest.mark.asyncio
async def test_cancel_during_context_launch_waits_for_context_then_closes_it(monkeypatch, tmp_path):
    launch_entered = asyncio.Event()
    release_launch = asyncio.Event()
    context = FakeContext()

    class BlockingChromium(FakeChromium):
        async def launch_persistent_context(self, profile, **kwargs):
            launch_entered.set()
            await release_launch.wait()
            return await super().launch_persistent_context(profile, **kwargs)

    playwright = FakePlaywright(context)
    playwright.chromium = BlockingChromium(context)
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_mod, "_profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(async_mod, "find_system_chrome", lambda: "/fake/chrome")
    browser = async_mod.AsyncBrowserCore()
    opening = asyncio.create_task(browser.open_browser())
    await launch_entered.wait()

    opening.cancel()
    await asyncio.sleep(0)
    assert opening.done() is False

    release_launch.set()
    with pytest.raises(asyncio.CancelledError):
        await opening
    assert context.closed is True
    assert playwright.stopped is True
    assert browser.browser is None


@pytest.mark.asyncio
async def test_close_waits_for_an_active_operation_before_teardown(monkeypatch, tmp_path):
    navigation_started = asyncio.Event()
    release_navigation = asyncio.Event()

    class BlockingPage(FakePage):
        async def goto(self, url, **kwargs):
            navigation_started.set()
            await release_navigation.wait()
            await super().goto(url, **kwargs)

    context, playwright = install_fake_runtime(
        monkeypatch,
        tmp_path,
        FakeContext(BlockingPage),
    )
    browser = async_mod.AsyncBrowserCore()
    await browser.open_browser()
    browser._tab_meta[None] = {"purpose": "test", "who": "tester"}
    navigation = asyncio.create_task(browser.go_to("example.com"))
    await navigation_started.wait()

    closing = asyncio.create_task(browser.close())
    await asyncio.sleep(0)
    assert closing.done() is False
    assert context.closed is False

    release_navigation.set()
    await navigation
    assert await closing == "Browser closed. Session saved for next time."
    assert context.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_cancelled_close_finishes_cleanup_before_propagating(monkeypatch, tmp_path):
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    class BlockingCloseContext(FakeContext):
        async def close(self):
            close_started.set()
            await release_close.wait()
            await super().close()

    context, playwright = install_fake_runtime(
        monkeypatch,
        tmp_path,
        BlockingCloseContext(),
    )
    browser = async_mod.AsyncBrowserCore()
    await browser.open_browser()
    closing = asyncio.create_task(browser.close())
    await close_started.wait()

    closing.cancel()
    await asyncio.sleep(0)
    assert closing.done() is False
    assert context.closed is False

    release_close.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert context.closed is True
    assert playwright.stopped is True
    assert browser.browser is None


@pytest.mark.asyncio
async def test_open_is_rejected_while_shutdown_owns_the_runtime(monkeypatch, tmp_path):
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    class BlockingCloseContext(FakeContext):
        async def close(self):
            close_started.set()
            await release_close.wait()
            await super().close()

    install_fake_runtime(monkeypatch, tmp_path, BlockingCloseContext())
    browser = async_mod.AsyncBrowserCore()
    await browser.open_browser()
    closing = asyncio.create_task(browser.close())
    await close_started.wait()

    with pytest.raises(RuntimeError, match="closing"):
        await browser.open_browser()

    release_close.set()
    await closing


@pytest.mark.asyncio
async def test_focus_guard_refuses_destructive_shortcut_and_allows_override():
    page = FakePage()
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    refused = await browser.keyboard_press("Meta+a")
    allowed = await browser.keyboard_press("Meta+a", allow_non_editable=True)

    assert refused.startswith("Refused 'Meta+a'")
    assert page.keyboard.pressed == ["Meta+a"]
    assert allowed == "Pressed: 'Meta+a'"


@pytest.mark.asyncio
async def test_selector_methods_use_async_locator_contract(tmp_path):
    upload = tmp_path / "report.txt"
    upload.write_text("ok")
    page = FakePage()
    page.selector_counts["button"] = 2
    page.selector_counts["missing"] = 0
    page.text_by_selector["button"] = "Publish"
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    assert await browser.count_elements_by_selector("button") == "2 elements match selector: button"
    assert await browser.get_element_text_by_selector("button", 1) == "Publish"
    assert await browser.get_element_text_by_selector("missing") == (
        "No element found for selector: missing"
    )
    assert (
        await browser.get_element_text_by_selector("button", 2)
        == "Selector matched 2 elements; index 2 is out of range"
    )
    assert "Clicked element 2/2" in await browser.click_element_by_selector("button", 1)
    assert "Filled element 1/1" in await browser.fill_text_by_selector("input", "hello")
    assert page.waits == [1000]
    uploaded = json.loads(
        await browser.upload_file_by_selector("input", str(upload))
    )
    assert uploaded["file"] == str(upload)
    assert uploaded["frame"]["index"] == 0
    assert page.clicked == [("button", 1)]
    assert page.filled == [("input", 0, "hello")]


@pytest.mark.asyncio
async def test_deterministic_async_verbs_preserve_sync_signatures_and_results(monkeypatch):
    methods = (
        "tab_status",
        "count_elements_by_selector",
        "get_element_text_by_selector",
        "fill_text_by_selector",
        "get_system_info",
        "extract_items_by_selector",
        "set_viewport",
        "wait_for_text",
        "wait",
        "extract_data",
        "get_links_from_page",
    )
    for name in methods:
        async_method = getattr(async_mod.AsyncBrowserCore, name)
        sync_method = getattr(BrowserAutomation, name)
        assert inspect.iscoroutinefunction(async_method), name
        assert list(inspect.signature(async_method).parameters) == list(
            inspect.signature(sync_method).parameters
        ), name

    page = FakePage()
    page.selector_counts["article"] = 2
    page.text_by_selector["article"] = "Story"
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    assert await browser.set_viewport(1280, 720) == "Viewport set to 1280x720"
    assert page.viewport == {"width": 1280, "height": 720}
    assert await browser.wait_for_text("Ready", timeout=7) == "Found text: 'Ready'"
    assert page.waited_selectors == [("text='Ready'", {"timeout": 7000})]
    assert await browser.wait(1.25) == "Waited for 1.25 seconds"
    assert page.waits[-1] == 1250
    assert await browser.extract_data("article") == ["Story", "Story"]

    monkeypatch.setattr(async_mod.platform, "system", lambda: "Darwin")
    assert await browser.get_system_info() == (
        "OS: macOS. Use Meta for shortcuts (Meta+a select all, Meta+c copy, "
        "Meta+v paste, Meta+z undo)."
    )


@pytest.mark.asyncio
async def test_async_extraction_and_link_contracts_return_sync_shapes():
    page = FakePage()
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    items = [{"item_index": 0, "author": "Ada", "text": "Hello"}]
    page.evaluate_result = items
    result = await browser.extract_items_by_selector(
        ".card",
        ".body",
        max_items=4,
        author_selector=".author",
        author_attribute="data-name",
        action_selector="button",
        action_text="Open",
        exclude_text_pattern="Sponsored",
    )
    assert result == json.dumps(items, indent=2, ensure_ascii=False)
    assert page.evaluate_calls[-1][1] == {
        "container_selector": ".card",
        "text_selector": ".body",
        "max_items": 4,
        "author_selector": ".author",
        "author_attribute": "data-name",
        "action_selector": "button",
        "action_text": "Open",
        "exclude_text_pattern": "Sponsored",
    }

    page.evaluate_result = ["https://example.com/a", "https://example.com/b"]
    assert await browser.get_links_from_page("example.com") == page.evaluate_result
    assert page.evaluate_calls[-1][1] == "example.com"


@pytest.mark.asyncio
async def test_tab_status_renders_registry_before_page_creation():
    browser = async_mod.AsyncBrowserCore()
    browser._bind_session("worker-1")
    browser._tab_meta["worker-1"] = {
        "who": "agent",
        "purpose": "research",
    }
    browser._tab_meta["worker-2"] = {
        "who": "peer",
        "purpose": "verification",
    }
    live = FakePage()
    live.url = "https://example.com"
    browser._pages["worker-2"] = live

    assert await browser.tab_status() == (
        "Tabs (2):\n"
        "  *[worker-1] (reserved — no page yet)  who=agent  purpose='research'\n"
        "   [worker-2] https://example.com  who=peer  purpose='verification'"
    )


@pytest.mark.asyncio
async def test_async_frame_and_upload_verbs_preserve_sync_signatures():
    for name in (
        "run_page_script",
        "run_frame_script",
        "upload_file_by_selector",
        "upload_file_after_click_by_selector",
    ):
        async_method = getattr(async_mod.AsyncBrowserCore, name)
        sync_method = getattr(BrowserAutomation, name)
        assert inspect.iscoroutinefunction(async_method), name
        assert inspect.signature(async_method) == inspect.signature(sync_method), name


@pytest.mark.asyncio
async def test_async_page_and_frame_scripts_keep_validation_and_result_contracts(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "verify.js"
    script.write_text("(args) => ({ ok: args.ok })", encoding="utf-8")
    page = FakePage()
    first = FakeFrame({"ok": False}, url="https://example.com/main", name="main")
    second = FakeFrame(
        {"ok": True, "z": 1},
        url="https://example.com/composer",
        name=lambda: "composer",
    )
    third = FakeFrame({"ok": True}, url="https://example.com/other", name="other")
    page.frames = [first, second, third]
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    page.evaluate_result = {"z": 1, "a": 2}
    assert await browser.run_page_script("verify.js", '{"ok": true}') == (
        '{\n  "z": 1,\n  "a": 2\n}'
    )
    assert await browser.run_page_script("missing.js") == (
        f"Script not found: {tmp_path / 'missing.js'}"
    )
    assert await browser.run_page_script(".") == f"Script path is not a file: {tmp_path}"
    assert (await browser.run_page_script("verify.js", "{")).startswith(
        "Invalid args_json:"
    )

    result = json.loads(await browser.run_frame_script("verify.js", '{"ok": true}'))
    assert result["ok"] is True
    assert result["matched_frame"]["name"] == "composer"
    assert len(result["frames"]) == 2
    assert third.evaluate_calls == []

    filtered = json.loads(
        await browser.run_frame_script(
            "verify.js",
            "{}",
            frame_url_contains="composer",
            frame_name="composer",
            first_ok=False,
        )
    )
    assert filtered["matched_frame"]["url"] == "https://example.com/composer"
    assert len(filtered["frames"]) == 1

    missing = json.loads(
        await browser.run_frame_script("verify.js", "{}", frame_name="missing")
    )
    assert missing["ok"] is False
    assert missing["reason"] == "no frames matched filters"


@pytest.mark.asyncio
async def test_async_direct_upload_is_frame_aware_and_returns_sync_json(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    upload = tmp_path / "cover.png"
    upload.write_bytes(b"png")
    directory = tmp_path / "folder"
    directory.mkdir()
    page = FakePage()
    page.selector_counts['input[type="file"]'] = 0
    child = FakeFrame({}, url="https://example.com/editor", name=lambda: "editor")
    child.selector_counts['input[type="file"]'] = 1
    page.frames = [page, child]
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    result = json.loads(
        await browser.upload_file_by_selector(
            'input[type="file"]',
            "cover.png",
            frame_url_contains="editor",
            frame_name="editor",
        )
    )
    assert result == {
        "ok": True,
        "uploaded": True,
        "file": str(upload),
        "selector": 'input[type="file"]',
        "index": 0,
        "frame": {
            "index": 1,
            "name": "editor",
            "url": "https://example.com/editor",
        },
    }
    assert child.uploaded == [('input[type="file"]', 0, str(upload))]
    assert 1500 in page.waits
    assert await browser.upload_file_by_selector("input", "missing.png") == (
        f"File not found: {tmp_path / 'missing.png'}"
    )
    assert await browser.upload_file_by_selector("input", "folder") == (
        f"Path is not a file: {directory}"
    )
    assert await browser.upload_file_by_selector(
        'input[type="file"]',
        "cover.png",
        frame_name="missing",
    ) == 'No file input found for selector: input[type="file"]'
    assert await browser.upload_file_by_selector(
        'input[type="file"]',
        "cover.png",
        index=1,
        frame_name="editor",
    ) == 'Selector matched 1 file input(s); index 1 is out of range'


@pytest.mark.asyncio
async def test_async_upload_after_click_filters_frame_text_and_awaits_chooser(tmp_path):
    upload = tmp_path / "cover.png"
    upload.write_bytes(b"png")
    page = FakePage()
    page.selector_counts["button"] = 0
    child = FakeFrame({}, url="https://example.com/editor", name="editor")
    child.selector_counts["button"] = 1
    child.text_by_selector["button"] = "Upload from computer"
    page.frames = [page, child]
    context = FakeContext()
    context.pages_created.append(page)
    browser = async_mod.AsyncBrowserCore()
    browser.browser = context
    browser._pages[None] = page

    result = json.loads(
        await browser.upload_file_after_click_by_selector(
            "button",
            str(upload),
            text="Upload from computer",
            frame_name="editor",
            timeout_ms=4321,
        )
    )
    assert result["uploaded"] is True
    assert result["frame"]["name"] == "editor"
    assert child.clicked == [("button", 0)]
    assert page.file_chooser_timeouts == [4321]
    assert page.file_chooser.files == [str(upload)]
    assert 2500 in page.waits

    assert await browser.upload_file_after_click_by_selector(
        "button",
        str(upload),
        text="Different",
        frame_name="editor",
    ) == "No upload trigger found for selector: button with text: Different"
    assert await browser.upload_file_after_click_by_selector(
        "button",
        str(upload),
        index=1,
        frame_name="editor",
    ) == "Selector matched 1 upload trigger(s); index 1 is out of range"


@pytest.mark.asyncio
async def test_bound_close_releases_only_that_session_tab():
    browser = async_mod.AsyncBrowserCore()
    browser.browser = FakeContext()
    browser._bind_session("A")
    await browser._ensure_page("A")
    page_a = browser.page
    browser._bind_session("B")
    await browser._ensure_page("B")

    result = await browser.close()

    assert "tab closed" in result.lower()
    assert "B" not in browser._pages
    assert browser._pages["A"] is page_a
    assert page_a.closed is False
    assert browser.browser is not None
