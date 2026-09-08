"""Tests for co_ai background task tool."""
"""
LLM-Note: Tests for co ai tools background

What it tests:
- Co Ai Tools Background functionality

Components under test:
- Module: co_ai_tools_background
"""


import sys
import os
import pytest
import time

from connectonion.cli.co_ai.tools.background import (
    run_background,
    task_output,
    kill_task,
    _reset_for_testing,
)


def test_run_background_and_output():
    _reset_for_testing()
    cmd = f"{sys.executable} -c \"print('hi')\""
    msg = run_background(cmd)
    assert "Task bg_" in msg

    output = ""
    for _ in range(50):
        output = task_output("bg_1")
        if "completed" in output or "failed" in output:
            break
        time.sleep(0.05)

    assert "hi" in output
    _reset_for_testing()


def test_kill_task_and_missing():
    _reset_for_testing()

    # Missing task
    msg = kill_task("bg_999")
    assert "not found" in msg

    # Start a long task and kill it
    cmd = f"{sys.executable} -c \"import time; time.sleep(5)\""
    run_background(cmd)
    time.sleep(0.1)
    msg = kill_task("bg_1")
    assert "terminated" in msg
    _reset_for_testing()


def test_kill_reaps_the_process_and_reader_thread():
    import threading
    from connectonion.cli.co_ai.tools import background
    _reset_for_testing()
    before={t.ident for t in threading.enumerate()}
    try:
        run_background(f'{sys.executable} -c "import time; print(\'ready\', flush=True); time.sleep(20)"')
        for _ in range(100):
            if 'ready' in background._tasks['bg_1'].output:
                break
            time.sleep(0.01)
        task=background._tasks['bg_1']
        assert 'terminated' in kill_task('bg_1')
        assert task.process.poll() is not None
        assert not [t for t in threading.enumerate() if t.ident not in before and t.is_alive()]
        assert task.process.stdout.closed
    finally:
        _reset_for_testing()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process group and signal escalation')
def test_kill_stops_a_descendant_that_ignores_termination():
    import shlex
    from connectonion.cli.co_ai.tools import background
    child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('child-ready',flush=True); time.sleep(20)"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(20)"
    _reset_for_testing()
    try:
        run_background(shlex.join([sys.executable,'-c',parent]))
        for _ in range(100):
            if 'child-ready' in background._tasks['bg_1'].output:
                break
            time.sleep(0.01)
        task=background._tasks['bg_1']
        assert 'child-ready' in task.output
        assert 'terminated' in kill_task('bg_1')
        assert not task.reader.is_alive()
        assert task.process.poll() is not None
        assert task.process.stdout.closed
    finally:
        _reset_for_testing()
