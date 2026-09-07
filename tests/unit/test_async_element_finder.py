"""Contracts for model-selected elements without blocking the browser loop."""

import asyncio
import json
import threading

import pytest

from connectonion.useful_tools.browser_tools import _async_element_finder as finder
from connectonion.useful_tools.browser_tools import element_finder as rules


def _raw_element(**overrides):
    element = {
        "index": 0,
        "tag": "button",
        "text": "Publish",
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 40,
        "frame": "main",
        "locator": '[data-browser-agent-id="0"]',
    }
    element.update(overrides)
    return element


class FakePage:
    def __init__(self, raw):
        self.raw = raw
        self.scripts = []

    async def evaluate(self, script):
        self.scripts.append(script)
        await asyncio.sleep(0)
        return self.raw


@pytest.mark.asyncio
async def test_async_extraction_awaits_dom_and_keeps_debug_json(tmp_path, monkeypatch):
    page = FakePage([_raw_element(), _raw_element(index=1, frame="editor")])
    monkeypatch.setattr(finder.Path, "home", lambda: tmp_path)

    elements = await finder.extract_elements(page)

    assert [element.index for element in elements] == [0, 1]
    assert all(isinstance(element, rules.InteractiveElement) for element in elements)
    assert page.scripts == [rules._get_extract_js()]
    written = json.loads((tmp_path / ".co" / "debug" / "elements.json").read_text())
    assert written == page.raw


@pytest.mark.asyncio
async def test_model_selection_runs_off_event_loop_and_other_work_progresses(
    monkeypatch,
):
    page = FakePage([_raw_element()])
    selected = rules.InteractiveElement(**_raw_element())
    matcher_started = threading.Event()
    release_matcher = threading.Event()
    loop_thread = threading.get_ident()
    matcher_threads = []

    def match(_page, description, elements):
        matcher_threads.append(threading.get_ident())
        assert description == "the publish button"
        assert elements == [selected]
        matcher_started.set()
        release_matcher.wait(timeout=2)
        return selected

    monkeypatch.setattr(
        finder, "extract_elements", lambda _page: _async_value([selected])
    )
    monkeypatch.setattr(finder.rules, "find_element", match)

    task = asyncio.create_task(finder.find_element(page, "the publish button"))
    while not matcher_started.is_set():
        await asyncio.sleep(0)
    progressed = False

    async def unrelated_work():
        nonlocal progressed
        progressed = True

    await unrelated_work()
    assert progressed is True
    assert task.done() is False
    release_matcher.set()
    assert await task is selected
    assert matcher_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_model_none_and_matching_errors_preserve_sync_contract(monkeypatch):
    page = FakePage([])
    monkeypatch.setattr(finder, "extract_elements", lambda _page: _async_value([]))
    assert await finder.find_element(page, "missing") is None

    element = rules.InteractiveElement(**_raw_element())
    monkeypatch.setattr(
        finder, "extract_elements", lambda _page: _async_value([element])
    )

    def fail(_page, _description, _elements):
        raise rules.ElementNotFoundError("ambiguous")

    monkeypatch.setattr(finder.rules, "find_element", fail)
    with pytest.raises(rules.ElementNotFoundError, match="ambiguous"):
        await finder.find_element(page, "button")


async def _async_value(value):
    return value
