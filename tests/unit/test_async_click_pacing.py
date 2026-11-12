"""Click targets and button events stay correct when pointer dispatch is slow."""
import asyncio
from collections import deque

import pytest

from connectonion.useful_tools.browser_tools import _async_humanize as humanize


class Clock:
    def __init__(self):
        self.now = 0.0

    async def pause(self, _page, base, _sigma=0.45):
        self.now += base
        await asyncio.sleep(0)


class Mouse:
    def __init__(self, clock, delay=0, first=None, fail_target=None):
        self.clock, self.delay = clock, delay
        self.first = deque(first or [])
        self.fail_target = fail_target
        self.log = []

    async def move(self, x, y):
        if self.fail_target and (x, y) == (1000, 0):
            raise self.fail_target
        delay = self.first.popleft() if self.first else self.delay
        if isinstance(delay, BaseException):
            raise delay
        self.clock.now += delay
        self.log.append(('move', x, y))
        await asyncio.sleep(0)

    async def down(self, button='left', click_count=1):
        self.log.append(('down', button, click_count))

    async def up(self, button='left', click_count=1):
        self.log.append(('up', button, click_count))


class Page:
    def __init__(self, clock, **kwargs):
        self.mouse = Mouse(clock, **kwargs)


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    humanize._cursor.clear()
    monkeypatch.setattr(humanize, 'monotonic', lambda: clock.now, raising=False)
    monkeypatch.setattr(humanize, '_pause', clock.pause)
    monkeypatch.setattr(humanize.random, 'random', lambda: 1)
    monkeypatch.setattr(humanize.rules, '_control_points',
                        lambda start, end: ((start[0] + 300, 100), (end[0] - 300, -100)))
    return clock


def page_for(clock, **kwargs):
    page = Page(clock, **kwargs)
    humanize._cursor[page] = (0, 0)
    return page


@pytest.mark.asyncio
async def test_slow_click_does_not_replay_a_minute_of_stale_waypoints(clock):
    page = page_for(clock, delay=1)
    await humanize.click(page, 1000, 0)
    moves = [event for event in page.mouse.log if event[0] == 'move']
    assert clock.now < 6
    assert len(moves) <= 4
    assert page.mouse.log[-3:] == [('move', 1000, 0), ('down', 'left', 1), ('up', 'left', 1)]
    assert humanize._cursor[page] == (1000, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('delay', [0, .02, .03])
async def test_healthy_click_retains_a_dense_curved_approach(clock, delay):
    page = page_for(clock, delay=delay)
    await humanize.click(page, 1000, 0)
    moves = [event[1:] for event in page.mouse.log if event[0] == 'move']
    assert len(moves) >= 38
    assert max(abs(y) for _, y in moves) > 10
    assert moves[-1] == (1000, 0)


@pytest.mark.asyncio
async def test_one_stall_then_healthy_dispatch_still_draws_the_remaining_curve(clock):
    page = page_for(clock, delay=.02, first=[1])
    await humanize.click(page, 1000, 0)
    moves = [event for event in page.mouse.log if event[0] == 'move']
    assert 8 <= len(moves) <= 40
    assert moves[-1] == ('move', 1000, 0)
    assert clock.now < 4


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [ValueError('move failed'), asyncio.CancelledError()])
async def test_failed_or_cancelled_approach_never_presses_a_button(clock, failure):
    page = page_for(clock, first=[failure])
    with pytest.raises(type(failure)):
        await humanize.click(page, 1000, 0)
    assert page.mouse.log == []
    assert humanize._cursor[page] == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [ValueError('target dispatch failed'), asyncio.CancelledError()])
async def test_final_target_failure_is_not_followed_by_a_click(clock, failure):
    page = page_for(clock, delay=1, fail_target=failure)
    with pytest.raises(type(failure)):
        await humanize.click(page, 1000, 0)
    assert all(event[0] == 'move' for event in page.mouse.log)
    assert humanize._cursor[page] == (0, 0)


@pytest.mark.asyncio
async def test_slow_overshoot_returns_to_the_exact_target_before_button_down(clock, monkeypatch):
    page = page_for(clock, delay=1)
    monkeypatch.setattr(humanize.random, 'random', lambda: 0)
    monkeypatch.setattr(humanize.random, 'gauss', lambda _mean, _sigma: 3)
    await humanize.click(page, 1000, 0)
    assert page.mouse.log[-4:] == [('move', 1003, 3), ('move', 1000, 0),
                                 ('down', 'left', 1), ('up', 'left', 1)]
    assert clock.now < 8


@pytest.mark.asyncio
async def test_cancelled_overshoot_never_presses_a_button(clock, monkeypatch):
    page = page_for(clock, delay=1)
    monkeypatch.setattr(humanize.random, 'random', lambda: 0)
    monkeypatch.setattr(humanize.random, 'gauss', lambda _mean, _sigma: 3)
    original = page.mouse.move

    async def cancelled_overshoot(x, y):
        if (x, y) == (1003, 3):
            raise asyncio.CancelledError()
        await original(x, y)

    monkeypatch.setattr(page.mouse, 'move', cancelled_overshoot)
    with pytest.raises(asyncio.CancelledError):
        await humanize.click(page, 1000, 0)
    assert all(event[0] == 'move' for event in page.mouse.log)
    assert humanize._cursor[page] == (0, 0)


@pytest.mark.asyncio
async def test_slow_box_double_right_click_preserves_target_and_button_counts(clock):
    page = page_for(clock, delay=1)
    await humanize.click(page, 0, 0, box={'x': 900, 'y': 20, 'width': 100, 'height': 50},
                         button='right', clicks=2)
    x, y = humanize._cursor[page]
    assert 900 <= x <= 1000 and 20 <= y <= 70
    assert [event for event in page.mouse.log if event[0] != 'move'] == [
        ('down', 'right', 1), ('up', 'right', 1), ('down', 'right', 2), ('up', 'right', 2)]
    assert [event for event in page.mouse.log if event[0] == 'move'][-1] == ('move', x, y)


@pytest.mark.asyncio
async def test_general_move_preserves_intermediate_points_under_backpressure(clock):
    page = page_for(clock, delay=1)
    await humanize.move(page, 1000, 0)
    assert len(page.mouse.log) >= 40
    assert page.mouse.log[-1] == ('move', 1000, 0)


@pytest.mark.asyncio
async def test_waiting_for_one_tabs_mouse_does_not_block_another_tab(clock, monkeypatch):
    first, second = page_for(clock), page_for(clock)
    started, release = asyncio.Event(), asyncio.Event()
    original = first.mouse.move

    async def wait_for_dispatch(x, y):
        started.set()
        await release.wait()
        await original(x, y)

    monkeypatch.setattr(first.mouse, 'move', wait_for_dispatch)
    pending = asyncio.create_task(humanize.click(first, 1000, 0))
    await started.wait()
    await asyncio.wait_for(humanize.click(second, 1000, 0), timeout=1)
    assert not pending.done()
    assert second.mouse.log[-1] == ('up', 'left', 1)
    release.set()
    await pending
