from types import SimpleNamespace

from connectonion.useful_tools.browser_tools import browser as browser_module
from connectonion.useful_tools.browser_tools.browser import BrowserAutomation


class FakePage:
    url = "https://example.com/feed"

    def content(self):
        return "<html><body><button>Like</button></body></html>"

    def evaluate(self, script):
        return "button { color: blue; }"


class FakeMouse:
    """Records the effective press point. Clicks are humanized (curved move → down →
    up), so the press lands wherever the last move ended — that is the click point."""
    def __init__(self):
        self.clicks = []
        self._pos = (0, 0)

    def move(self, x, y):
        self._pos = (x, y)

    def down(self, button="left", click_count=1):
        self.clicks.append(self._pos)

    def up(self, button="left", click_count=1):
        pass

    def click(self, x, y):  # kept for any direct callers
        self.clicks.append((x, y))


class FakeLocatorItem:
    def __init__(self, text="Like", box=None):
        self.text = text
        self.box = box or {"x": 10, "y": 20, "width": 100, "height": 40}
        self.force_clicked = False
        self.uploaded_files = []

    def bounding_box(self):
        return self.box

    def click(self, force=False):
        self.force_clicked = force

    def inner_text(self):
        return self.text

    def set_input_files(self, file_path):
        self.uploaded_files.append(file_path)


class FakeLocator:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeFileChooser:
    def __init__(self):
        self.files = []

    def set_files(self, file_path):
        self.files.append(file_path)


class FakeFileChooserContext:
    def __init__(self, chooser):
        self.value = chooser
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeSelectorPage(FakePage):
    def __init__(self, items):
        self.items = items
        self.mouse = FakeMouse()
        self.keyboard = SimpleNamespace(typed=[], type=lambda text: self.keyboard.typed.append(text))
        self.waits = []

    def locator(self, selector):
        self.last_selector = selector
        return FakeLocator(self.items)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    @property
    def frames(self):
        return [self]


class FakeTextFilteredClickPage(FakeSelectorPage):
    def __init__(self, matches):
        super().__init__([])
        self.matches = matches
        self.evaluate_args = []

    def evaluate(self, script, arg=None):
        self.evaluate_args.append(arg)
        return self.matches


class FakeExtractItemsPage(FakePage):
    def __init__(self, items):
        self.items = items

    def evaluate(self, script, arg=None):
        self.last_arg = arg
        return self.items[:arg["max_items"]]


class FakeNearSelectorClickPage(FakePage):
    def __init__(self, target, state):
        self.target = target
        self.state = state
        self.mouse = FakeMouse()
        self.waits = []
        self.evaluate_calls = []

    def evaluate(self, script, arg=None):
        self.evaluate_calls.append(arg)
        if len(self.evaluate_calls) == 1:
            return self.target
        return self.state

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


class FakeRunScriptPage(FakePage):
    def __init__(self, result):
        self.result = result
        self.evaluate_calls = []

    def evaluate(self, script, arg=None):
        self.evaluate_calls.append((script, arg))
        return self.result


class FakeFrame:
    def __init__(self, result, url="https://example.com/frame", name=""):
        self.result = result
        self.url = url
        self.name = name
        self.evaluate_calls = []

    def evaluate(self, script, arg=None):
        self.evaluate_calls.append((script, arg))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeFramePage(FakePage):
    def __init__(self, frames):
        self.frames = frames


def test_save_page_context_writes_html_css_and_elements(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        browser_module.element_finder,
        "extract_elements",
        lambda page: [
            SimpleNamespace(
                model_dump=lambda: {
                    "index": 0,
                    "tag": "button",
                    "text": "Like",
                    "aria_label": "Reaction button state: no reaction",
                    "locator": '[data-browser-agent-id="0"]',
                }
            )
        ],
    )

    browser = BrowserAutomation(headless=True)
    browser.page = FakePage()

    result = browser.save_page_context("linkedin feed")

    context_dirs = list((tmp_path / ".co" / "browser_context").glob("*_linkedin_feed"))
    assert len(context_dirs) == 1

    out_dir = context_dirs[0]
    assert (out_dir / "page.html").read_text() == "<html><body><button>Like</button></body></html>"
    assert (out_dir / "styles.css").read_text() == "button { color: blue; }"
    assert '"locator": "[data-browser-agent-id=\\"0\\"]"' in (out_dir / "elements.json").read_text()
    assert "Saved page context" in result
    assert "Elements: 1" in result


def test_click_element_by_selector_wraps_playwright_locator(monkeypatch):
    page = FakeSelectorPage([FakeLocatorItem()])
    browser = BrowserAutomation(headless=True)
    browser.page = page
    monkeypatch.setattr(browser, "_save_context", lambda: None)

    result = browser.click_element_by_selector(
        'button[aria-label="Reaction button state: no reaction"]'
    )

    assert page.last_selector == 'button[aria-label="Reaction button state: no reaction"]'
    # Humanized click lands somewhere inside the element (box x:10..110, y:20..60),
    # off dead-center by design — assert it's on the element, not on an exact pixel.
    assert len(page.mouse.clicks) == 1
    cx, cy = page.mouse.clicks[0]
    assert 10 <= cx <= 110 and 20 <= cy <= 60
    assert page.waits == [1000]
    assert "Clicked element 1/1" in result


def test_click_element_by_selector_can_filter_by_exact_text(monkeypatch):
    page = FakeTextFilteredClickPage([{"x": 10, "y": 20}, {"x": 30, "y": 40}])
    browser = BrowserAutomation(headless=True)
    browser.page = page
    monkeypatch.setattr(browser, "_save_context", lambda: None)

    result = browser.click_element_by_selector("button", index=1, text="Comment")

    assert page.evaluate_args == [{"selector": "button", "text": "Comment"}]
    assert page.mouse.clicks == [(30, 40)]
    assert page.waits == [1000]
    assert "with text: Comment" in result


def test_count_and_get_text_by_selector():
    page = FakeSelectorPage([FakeLocatorItem(text="Like"), FakeLocatorItem(text="Comment")])
    browser = BrowserAutomation(headless=True)
    browser.page = page

    assert browser.count_elements_by_selector("button").startswith("2 elements")
    assert browser.get_element_text_by_selector("button", index=1) == "Comment"


def test_type_text_by_selector_focuses_and_types():
    item = FakeLocatorItem(text="")
    page = FakeSelectorPage([item])
    browser = BrowserAutomation(headless=True)
    browser.page = page

    result = browser.type_text_by_selector(
        'div[contenteditable="true"][role="textbox"]',
        "Great point.",
    )

    assert item.force_clicked is True
    # Typing is humanized — one keystroke per character, not one bulk insert.
    assert page.keyboard.typed == list("Great point.")
    assert page.waits == [1000]
    assert "Typed text into element 1/1" in result


def test_upload_file_by_selector_sets_input_file(tmp_path, monkeypatch):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"png")
    item = FakeLocatorItem(text="")
    page = FakeSelectorPage([item])
    browser = BrowserAutomation(headless=True)
    browser.page = page
    monkeypatch.setattr(browser, "_save_context", lambda: None)

    result = browser.upload_file_by_selector('input[type="file"]', str(cover))

    assert item.uploaded_files == [str(cover)]
    assert page.waits == [1500]
    assert '"uploaded": true' in result
    assert '"selector": "input[type=\\"file\\"]"' in result


def test_upload_file_after_click_by_selector_sets_file_chooser(tmp_path, monkeypatch):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"png")
    item = FakeLocatorItem(text="Upload from computer")
    chooser = FakeFileChooser()
    page = FakeSelectorPage([item])
    page.expect_file_chooser = lambda timeout=0: FakeFileChooserContext(chooser)
    browser = BrowserAutomation(headless=True)
    browser.page = page
    monkeypatch.setattr(browser, "_save_context", lambda: None)

    result = browser.upload_file_after_click_by_selector(
        "button",
        str(cover),
        text="Upload from computer",
    )

    assert item.force_clicked is True
    assert chooser.files == [str(cover)]
    assert page.waits == [2500]
    assert '"uploaded": true' in result
    assert '"text": "Upload from computer"' in result


def test_run_page_script_executes_local_js_with_json_args(tmp_path):
    script = tmp_path / "extract.js"
    script.write_text("(args) => ({ ok: true, maxPosts: args.maxPosts })", encoding="utf-8")
    page = FakeRunScriptPage({"ok": True, "maxPosts": 3})
    browser = BrowserAutomation(headless=True)
    browser.page = page

    result = browser.run_page_script(str(script), '{"maxPosts": 3}')

    assert '"ok": true' in result
    assert '"maxPosts": 3' in result
    assert page.evaluate_calls == [
        ("(args) => ({ ok: true, maxPosts: args.maxPosts })", {"maxPosts": 3})
    ]


def test_run_page_script_reports_invalid_json(tmp_path):
    script = tmp_path / "extract.js"
    script.write_text("(args) => args", encoding="utf-8")
    browser = BrowserAutomation(headless=True)
    browser.page = FakeRunScriptPage({})

    result = browser.run_page_script(str(script), "{bad")

    assert result.startswith("Invalid args_json:")


def test_run_frame_script_returns_first_ok_frame(tmp_path):
    script = tmp_path / "verify.js"
    script.write_text("(args) => ({ ok: args.ok })", encoding="utf-8")
    first = FakeFrame({"ok": False}, url="https://example.com/main", name="main")
    second = FakeFrame({"ok": True, "button": "Post"}, url="https://example.com/composer", name="composer")
    third = FakeFrame({"ok": True, "button": "Other"}, url="https://example.com/other", name="other")
    browser = BrowserAutomation(headless=True)
    browser.page = FakeFramePage([first, second, third])

    result = browser.run_frame_script(str(script), '{"ok": true}')

    assert '"ok": true' in result
    assert '"matched_frame"' in result
    assert '"name": "composer"' in result
    assert len(first.evaluate_calls) == 1
    assert len(second.evaluate_calls) == 1
    assert third.evaluate_calls == []


def test_run_frame_script_can_filter_by_frame_url(tmp_path):
    script = tmp_path / "verify.js"
    script.write_text("(args) => ({ ok: true })", encoding="utf-8")
    first = FakeFrame({"ok": True}, url="https://example.com/main", name="main")
    second = FakeFrame({"ok": True}, url="https://example.com/shadow-interop-outlet", name="composer")
    browser = BrowserAutomation(headless=True)
    browser.page = FakeFramePage([first, second])

    result = browser.run_frame_script(
        str(script),
        "{}",
        frame_url_contains="shadow-interop",
    )

    assert '"url": "https://example.com/shadow-interop-outlet"' in result
    assert first.evaluate_calls == []
    assert len(second.evaluate_calls) == 1


def test_run_frame_script_reports_no_matching_frames(tmp_path):
    script = tmp_path / "verify.js"
    script.write_text("(args) => ({ ok: true })", encoding="utf-8")
    browser = BrowserAutomation(headless=True)
    browser.page = FakeFramePage([FakeFrame({"ok": True}, url="https://example.com/main")])

    result = browser.run_frame_script(str(script), "{}", frame_url_contains="missing")

    assert '"ok": false' in result
    assert '"reason": "no frames matched filters"' in result


def test_extract_items_by_selector_returns_json_with_action_index():
    items = [
        {
            "item_index": 0,
            "author": "Baylin Molloy",
            "text": "Four months ago, if you told me Deployed AI would have 4 team members.",
            "action_index": 0,
            "has_action": True,
        }
    ]
    page = FakeExtractItemsPage(items)
    browser = BrowserAutomation(headless=True)
    browser.page = page

    result = browser.extract_items_by_selector(
        container_selector='div[role="listitem"]',
        text_selector='p[componentkey^="feed-commentary_"]',
        max_items=1,
        author_selector='button[aria-label^="Open control menu for post by"]',
        author_attribute="aria-label",
        action_selector="button",
        action_text="Comment",
    )

    assert '"author": "Baylin Molloy"' in result
    assert '"action_index": 0' in result
    assert page.last_arg["max_items"] == 1
    assert page.last_arg["action_text"] == "Comment"


def test_click_element_near_selector_clicks_target_near_anchor(monkeypatch):
    page = FakeNearSelectorClickPage(
        {
            "ok": True,
            "x": 123,
            "y": 456,
            "anchor_text": "the PDF spec is the final boss",
            "target_text": "Comment",
        },
        "anchor_text_cleared",
    )
    browser = BrowserAutomation(headless=True)
    browser.page = page
    monkeypatch.setattr(browser, "_save_context", lambda: None)

    result = browser.click_element_near_selector(
        anchor_selector='div[contenteditable="true"][role="textbox"]',
        target_selector="button",
        target_text="Comment",
        require_anchor_text=True,
        verify_anchor_text_cleared=True,
    )

    assert page.mouse.clicks == [(123, 456)]
    assert page.waits == [1000]
    assert page.evaluate_calls[-1] == {
        "anchor_selector": 'div[contenteditable="true"][role="textbox"]',
        "anchor_text": "the PDF spec is the final boss",
    }
    assert "Clicked target near anchor" in result
    assert "state=anchor_text_cleared" in result


def test_click_element_near_selector_reports_missing_anchor():
    page = FakeNearSelectorClickPage(
        {"ok": False, "error": "No visible anchor found for selector: div.editor"},
        "unused",
    )
    browser = BrowserAutomation(headless=True)
    browser.page = page

    result = browser.click_element_near_selector("div.editor", "button")

    assert result == "No visible anchor found for selector: div.editor"
    assert page.mouse.clicks == []


# ---- tab accountability: newtab / go_to metadata / tab_status ----------

def test_newtab_requires_purpose_and_who():
    """A shared browser stays accountable: newtab refuses an unowned/unlabeled tab,
    returning the agent-facing help instead of prompting a human."""
    import pytest

    browser = BrowserAutomation(headless=True)
    with pytest.raises(ValueError, match="for the AI agent"):
        browser.newtab("example.com")
    with pytest.raises(ValueError):
        browser.newtab("example.com", purpose="read")  # who still missing


def test_go_to_records_owner_and_purpose_on_active_tab():
    """go_to with purpose/who stamps the active (session) tab's metadata, keyed by session key."""
    page = FakePage()
    page.goto = lambda url, **kw: None
    page.wait_for_timeout = lambda ms: None
    page.url = "https://x.com/home"

    browser = BrowserAutomation(headless=True)
    browser.browser = SimpleNamespace()
    browser.page = page                 # writes _pages[None] (unbound = default tab)
    browser._save_context = lambda: None

    browser.go_to("https://x.com", purpose="post launch", who="aaron")
    meta = browser._tab_meta[None]
    assert meta["who"] == "aaron"
    assert meta["purpose"] == "post launch"
    assert "opened_at" in meta


def test_tab_status_marks_active_and_prunes_closed_tabs():
    p0 = FakePage(); p0.url = "https://x.com/home"
    p1 = FakePage(); p1.url = "https://mail.google.com"

    browser = BrowserAutomation(headless=True)
    browser.browser = SimpleNamespace()          # truthy: context open
    browser._pages = {None: p0, "1": p1}
    browser._tab_meta = {
        None: {"who": "aaron", "purpose": "post"},
        "1": {"who": "tamara", "purpose": "inbox"},
    }
    browser._bind_session("1")                    # active tab = session "1"

    out = browser.tab_status()
    assert "Tabs (2):" in out
    assert " [main] https://x.com/home  who=aaron" in out
    assert "*[1] https://mail.google.com  who=tamara" in out

    # A tab whose page has closed still shows (from the registry) but as reserved.
    p1.is_closed = lambda: True
    out = browser.tab_status()
    assert "mail.google.com" not in out
    assert "[1] (reserved — no page yet)" in out

    # A tab reserved via `tab open` (registry entry, no page) is visible immediately.
    browser._tab_meta["scraper"] = {"who": "codex", "purpose": "scrape"}
    out = browser.tab_status()
    assert "[scraper] (reserved — no page yet)  who=codex" in out

    # _release_tab drops the tab and its metadata together.
    browser._release_tab("1")
    assert "1" not in browser._tab_meta


def test_go_to_unoccupied_tab_demands_purpose():
    """The first go_to on an unoccupied tab errors with an AGENT-facing message
    (not a human prompt), telling the agent to supply --purpose/--who and re-run."""
    import pytest

    browser = BrowserAutomation(headless=True)   # browser None -> no navigation attempted
    with pytest.raises(ValueError, match="for the AI agent"):
        browser.go_to("https://x.com")


def test_go_to_occupied_tab_navigates_without_flags():
    """A go_to on an already-occupied tab (who+purpose set) navigates without repeating
    the flags — this keeps multi-step flows working."""
    page = FakePage()
    page.goto = lambda url, **kw: None
    page.wait_for_timeout = lambda ms: None
    page.url = "https://x.com/home"

    browser = BrowserAutomation(headless=True)
    browser.browser = SimpleNamespace()
    browser.page = page                                  # writes _pages[None]
    browser._save_context = lambda: None
    browser._tab_meta[None] = {"who": "aaron", "purpose": "post"}  # tab already occupied

    result = browser.go_to("https://x.com/explore")      # no flags — must not raise
    assert "Navigated to" in result


def test_tab_status_flags_may_be_closed():
    """A tab past its --hours estimate is flagged 'may be closed' (informational only)."""
    from datetime import datetime, timedelta

    p0 = FakePage(); p0.url = "https://x.com/home"
    browser = BrowserAutomation(headless=True)
    browser.browser = SimpleNamespace()                  # truthy: context open
    browser._pages = {None: p0}
    browser._tab_meta = {
        None: {"who": "aaron", "purpose": "post", "hours": 2,
               "opened_at": datetime.now() - timedelta(hours=3)},
    }

    out = browser.tab_status()
    assert "flagged 2h" in out
    assert "may be closed" in out
