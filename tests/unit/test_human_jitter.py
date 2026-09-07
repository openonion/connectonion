"""Compatibility tests for human_jitter on the async browser runtime."""

import asyncio
import importlib
from types import SimpleNamespace

jitter_module = importlib.import_module("connectonion.useful_plugins.human_jitter")


def test_jitter_runs_page_work_on_browser_runtime(monkeypatch):
    moves = []

    class Mouse:
        async def move(self, x, y, steps):
            moves.append((x, y, steps))

    class Page:
        mouse = Mouse()

        async def evaluate(self, script):
            assert script == "() => [window.innerWidth, window.innerHeight]"
            return [1000, 800]

    class Browser:
        def __init__(self):
            self.core = SimpleNamespace(page=Page())
            self.callbacks = 0

        def _run_on_runtime(self, callback):
            self.callbacks += 1
            return asyncio.run(callback(self.core))

    async def no_sleep(_delay):
        pass

    monkeypatch.setattr(jitter_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(jitter_module.random, "uniform", lambda start, end: start)
    monkeypatch.setattr(jitter_module.random, "randint", lambda start, end: start)
    browser = Browser()
    agent = SimpleNamespace(
        current_session={"pending_tool": {"name": "click"}},
        tools=SimpleNamespace(browserautomation=browser),
        logger=SimpleNamespace(print=lambda message: None),
    )

    jitter_module._jitter_before_click(agent)

    assert browser.callbacks == 1
    assert len(moves) == 3
