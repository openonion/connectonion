"""Tests for co_ai background task tool."""

import sys
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
