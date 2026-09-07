"""Contract tests for non-blocking humanized input on the async browser core."""

import asyncio
import math

import pytest

from connectonion.useful_tools.browser_tools import _async_humanize as humanize


class FakeMouse:
    def __init__(self, log):
        self.log = log

    async def move(self, x, y):
        self.log.append(("move", x, y))

    async def down(self, button="left", click_count=1):
        self.log.append(("down", button, click_count))

    async def up(self, button="left", click_count=1):
        self.log.append(("up", button, click_count))

    async def wheel(self, dx, dy):
        self.log.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    async def type(self, text):
        self.page.log.append(("type", text))

    async def press(self, key):
        self.page.log.append(("press", key))


class FakeSession:
    def __init__(self, log):
        self.log = log

    async def send(self, method, payload):
        self.log.append(("cdp", method, payload))


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.session = FakeSession(page.log)

    async def new_cdp_session(self, page):
        assert page is self.page
        return self.session


class FakePage:
    def __init__(self):
        self.log = []
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self)
        self.context = FakeContext(self)
        self.lengths = []

    async def evaluate(self, _script):
        return self.lengths.pop(0)


@pytest.fixture(autouse=True)
def fresh_human_state():
    humanize._cursor.clear()
    humanize._cdp.clear()
    humanize.rules._personas.clear()


def _kinds(log):
    return [event[0] for event in log]


async def _no_sleep(_delay):
    return None


@pytest.mark.asyncio
async def test_async_move_is_curved_and_yields_between_steps(monkeypatch):
    page = FakePage()
    yielded = []

    async def record_sleep(delay):
        yielded.append(delay)

    monkeypatch.setattr(humanize.asyncio, "sleep", record_sleep)
    await humanize.move(page, 500, 0)

    points = [(x, y) for kind, x, y in page.log if kind == "move"]
    assert len(points) >= 8
    assert points[-1] == pytest.approx((500, 0), abs=1)
    (x0, y0), (x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    max_perp = max(abs((x - x0) * dy - (y - y0) * dx) / length for x, y in points)
    assert max_perp / length > 0.01
    assert yielded, "human pauses must yield the event loop"


@pytest.mark.asyncio
async def test_async_click_keeps_button_count_box_and_cursor_contract(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(humanize.asyncio, "sleep", _no_sleep)

    await humanize.click(
        page,
        0,
        0,
        button="right",
        clicks=2,
        box={"x": 100, "y": 100, "width": 200, "height": 100},
    )

    kinds = _kinds(page.log)
    assert kinds.index("move") < kinds.index("down") < kinds.index("up")
    assert [event[2] for event in page.log if event[0] == "down"] == [1, 2]
    assert all(event[1] == "right" for event in page.log if event[0] in {"down", "up"})
    x, y = humanize._cursor[page]
    assert 100 <= x <= 300 and 100 <= y <= 200


@pytest.mark.asyncio
async def test_async_latin_typing_is_per_character_and_non_blocking(monkeypatch):
    page = FakePage()
    yielded = []

    async def record_sleep(delay):
        yielded.append(delay)

    monkeypatch.setattr(humanize.asyncio, "sleep", record_sleep)
    await humanize.type_text(page, "hi there", asyncio.Lock())

    assert [event[1] for event in page.log if event[0] == "type"] == list("hi there")
    assert len(yielded) >= len("hi there")


@pytest.mark.asyncio
async def test_async_cjk_paste_restores_clipboard(monkeypatch):
    page = FakePage()
    page.lengths = [0, 2]
    writes = []
    monkeypatch.setattr(humanize.rules, "_clipboard_set_argv", lambda _text: ["pbcopy"])
    monkeypatch.setattr(humanize.rules, "_clipboard_get", lambda: "saved")
    monkeypatch.setattr(
        humanize.rules,
        "_clipboard_set",
        lambda value: writes.append(value) or True,
    )
    monkeypatch.setattr(humanize.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(humanize.asyncio, "sleep", _no_sleep)

    await humanize.type_text(page, "你好", asyncio.Lock())

    assert ("press", "Meta+v") in page.log
    assert writes == ["你好", "saved"]


@pytest.mark.asyncio
async def test_clipboard_restore_finishes_before_cancellation_escapes(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    writes = []

    async def to_thread(func, value):
        started.set()
        await release.wait()
        writes.append(value)
        return func(value)

    monkeypatch.setattr(humanize.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(humanize.rules, "_clipboard_set", lambda _value: True)
    task = asyncio.create_task(humanize._restore_clipboard("saved"))
    await started.wait()
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes == ["saved"]


@pytest.mark.asyncio
async def test_cancellation_during_clipboard_set_still_restores_saved_value(
    monkeypatch,
):
    page = FakePage()
    started = asyncio.Event()
    release = asyncio.Event()
    writes = []

    async def to_thread(func, *args):
        value = func(*args)
        if func is humanize.rules._clipboard_set and args[0] == "你":
            started.set()
            await release.wait()
        return value

    monkeypatch.setattr(humanize.rules, "_clipboard_set_argv", lambda _text: ["pbcopy"])
    monkeypatch.setattr(humanize.rules, "_clipboard_get", lambda: "saved")
    monkeypatch.setattr(
        humanize.rules,
        "_clipboard_set",
        lambda value: writes.append(value) or True,
    )
    monkeypatch.setattr(humanize.asyncio, "to_thread", to_thread)

    task = asyncio.create_task(humanize.type_text(page, "你", asyncio.Lock()))
    await started.wait()
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes == ["你", "saved"]
    assert page.log == []


@pytest.mark.asyncio
async def test_cjk_clipboard_round_trips_are_serialized_between_tabs(monkeypatch):
    pages = [FakePage(), FakePage()]
    for page in pages:
        page.lengths = [0, 1]
    lock = asyncio.Lock()
    active = 0
    peak = 0
    real_sleep = asyncio.sleep

    async def to_thread(func, *args):
        nonlocal active, peak
        if func is humanize.rules._clipboard_set and args[0] in {"一", "二"}:
            active += 1
            peak = max(peak, active)
            await real_sleep(0)
            active -= 1
        return func(*args)

    monkeypatch.setattr(humanize.rules, "_clipboard_set_argv", lambda _text: ["pbcopy"])
    monkeypatch.setattr(humanize.rules, "_clipboard_get", lambda: "saved")
    monkeypatch.setattr(humanize.rules, "_clipboard_set", lambda _value: True)
    monkeypatch.setattr(humanize.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(humanize.asyncio, "sleep", _no_sleep)

    await asyncio.gather(
        humanize.type_text(pages[0], "一", lock),
        humanize.type_text(pages[1], "二", lock),
    )
    assert peak == 1


@pytest.mark.asyncio
async def test_async_cjk_falls_back_to_awaited_cdp_ime(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(humanize.rules, "_clipboard_set_argv", lambda _text: None)
    monkeypatch.setattr(humanize.asyncio, "sleep", _no_sleep)

    await humanize.type_text(page, "你", asyncio.Lock())

    assert [event[1] for event in page.log if event[0] == "cdp"] == [
        "Input.imeSetComposition",
        "Input.insertText",
    ]


@pytest.mark.asyncio
async def test_async_scroll_emits_bounded_ticks_with_exact_net_distance(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(humanize.asyncio, "sleep", _no_sleep)

    await humanize.scroll(page, 1000)

    deltas = [event[2] for event in page.log if event[0] == "wheel"]
    assert len(deltas) >= 6
    assert all(abs(delta) <= 170 for delta in deltas)
    assert sum(deltas) == 1000
