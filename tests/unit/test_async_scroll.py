"""Contracts for non-blocking async scroll strategy orchestration."""

import asyncio
import threading

import pytest

from connectonion.useful_tools.browser_tools import _async_scroll as scroll


class FakePage:
    def __init__(self):
        self.evaluate_results = []
        self.evaluated = []

    async def evaluate(self, script):
        self.evaluated.append(script)
        if self.evaluate_results:
            return self.evaluate_results.pop(0)
        return None


async def _no_sleep(_delay):
    return None


@pytest.mark.asyncio
async def test_strategy_order_and_exact_success_result(tmp_path, monkeypatch):
    page = FakePage()
    screenshots = []
    attempts = []

    async def take_screenshot(path=None):
        screenshots.append(path)
        return "data:image/png;base64,cG5n"

    async def failed_human(*_args):
        attempts.append("Human wheel")

    async def successful_ai(*_args):
        attempts.append("AI strategy")

    monkeypatch.setattr(scroll, "_human_scroll", failed_human)
    monkeypatch.setattr(scroll, "_ai_scroll", successful_ai)
    monkeypatch.setattr(scroll.rules, "_screenshots_different", lambda *_args: False)
    differences = iter([False, True])
    monkeypatch.setattr(
        scroll,
        "_screenshots_different",
        lambda *_args: next(differences),
    )
    monkeypatch.setattr(scroll, "_pause", _no_sleep)

    result = await scroll.scroll(page, take_screenshot, screenshots_dir=tmp_path)

    assert result == "Scrolled using AI strategy"
    assert attempts == ["Human wheel", "AI strategy"]
    assert len(screenshots) == 3
    assert screenshots[0].startswith("scroll_before_")
    assert screenshots[1].startswith("scroll_after_")


@pytest.mark.asyncio
async def test_slow_model_selection_runs_off_event_loop(monkeypatch):
    page = FakePage()
    page.evaluate_results = [[{"tag": "DIV"}], "<main>feed</main>"]
    started = threading.Event()
    release = threading.Event()
    selected = scroll.rules.ScrollStrategy(
        method="window",
        selector="",
        javascript="window.scrollBy(0, 10)",
        explanation="page",
    )

    def llm_do(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        return selected

    monkeypatch.setattr(scroll.rules, "llm_do", llm_do)
    monkeypatch.setattr(scroll, "_pause", _no_sleep)
    task = asyncio.create_task(scroll._ai_scroll(page, 1, "the feed"))
    while not started.is_set():
        await asyncio.sleep(0)

    progressed = False

    async def unrelated_work():
        nonlocal progressed
        progressed = True

    await unrelated_work()
    assert progressed is True
    assert task.done() is False
    release.set()
    await task
    assert page.evaluated[-1] == selected.javascript


@pytest.mark.asyncio
async def test_cancellation_stops_remaining_page_scroll_mutations(monkeypatch):
    page = FakePage()
    first_pause = asyncio.Event()

    async def pause(_delay):
        first_pause.set()
        await asyncio.Future()

    monkeypatch.setattr(scroll, "_pause", pause)
    task = asyncio.create_task(scroll._page_scroll(page, 5))
    await first_pause.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert page.evaluated == ["window.scrollBy(0, 1000)"]
