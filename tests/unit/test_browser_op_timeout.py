"""A wedged browser operation must raise (not hang the single worker thread forever).

Regression for the daemon "busy forever" hang: browser methods run on one worker
thread; without a timeout, one frozen Playwright call blocked every later command.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from connectonion.useful_tools.browser_tools import browser as B


class _Fake:
    """Minimal stand-in with the attributes `_runs_on_browser_thread` touches."""
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="testbrowser")
        self._executor_thread = self._executor.submit(threading.current_thread).result()
        self._session_binding = type("SB", (), {"key": None})()

    def _bound_session_key(self):
        return None

    def _ensure_page(self, key):
        pass


def test_wedged_op_raises_timeout(monkeypatch):
    monkeypatch.setattr(B, "_BROWSER_OP_TIMEOUT", 0.2)

    def hang(self):
        time.sleep(1.0)

    wrapped = B._runs_on_browser_thread(hang)
    with pytest.raises(TimeoutError):
        wrapped(_Fake())


def test_fast_op_still_returns(monkeypatch):
    monkeypatch.setattr(B, "_BROWSER_OP_TIMEOUT", 2)

    def quick(self):
        return "ok"

    wrapped = B._runs_on_browser_thread(quick)
    assert wrapped(_Fake()) == "ok"
