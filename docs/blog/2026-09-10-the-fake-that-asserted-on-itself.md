# The fake that asserted on itself

`tests/unit/test_events.py` has thirty-eight tests and every one of them was
green. They check the thing the event system exists for: that `before_tools`
fires once before the batch, `before_each_tool` before each call, `on_error`
when a tool fails, `after_tools` once at the end, in that order. If the tool
executor ever dropped one of those or fired them in the wrong sequence, this
was the file that would say so.

It could not have. Its autouse fixture replaced `Agent._execute_and_record_tools`
with a forty-line fake that fired `before_each_tool`, then `on_error` if the
tool's name was `failing_tool`, then `after_each_tool`, then `after_tools`, and
appended a hand-built trace entry. The tests then asserted that those events
had fired in that order. They were checking the fixture. The real executor in
`tool_executor.py` could have stopped emitting `on_error` in 2025 and this file
would have kept passing.

The audit in #210 had flagged it in July. Two months later I deleted the fake,
stubbed only the model, and ran the file. Thirty-eight passed. The real path
produced the same trace shape, the same error string, the same order — which
is good news about the executor and a small indictment of the fake, which had
been faithfully reimplementing forty lines of production code so that the
tests would not have to run them.

## The same shape, three more times

Once you have seen a test that asserts on itself you start seeing the family.

Two tests in `test_tui_components.py` imported `SmartInput` and `Pick` inside a
`try`, and skipped on `ImportError`. Neither name exists. The widget is `Input`
and the picker is a function called `pick`. The tests had skipped on every run
since they were written, and would have gone on skipping through any breakage
of the modules they were meant to guard. A required import that fails is a
failure; they now import the real names and assert.

`pytest.ini` ignored every `DeprecationWarning` and `PendingDeprecationWarning`
in the process. The warning count at the bottom of a run therefore said
nothing about upgrade debt. I took the ignore out, expecting a wall. The full
run surfaced exactly one: Pillow's `Image.getdata`, which the scroll code used
to compare two screenshots pixel by pixel, is going away in Pillow 14 on
2027-10-15. That is a date the blanket had been keeping from us. The
comparison now reads raw bytes, which every Pillow has, and the filter is
gone for good; a third-party warning that must be silenced gets a line with
its message, its owner and the condition for deleting the line.

The run also surfaced `ResourceWarning`, which nobody had asked to hide and
nobody had looked at either: a sqlite handle in the replay ledger
that leaked when its first pragma failed, a probe socket in the browser daemon
left open on the refused path, and four tests reading `host.yaml` through a
bare `open()` with no close. Each is a file and a line in the summary now, and
each of those is fixed.

## The test that depended on the shell

The last one was not a fake. `test_co_command_works` ran `co --version` from
`PATH` and asserted it exited zero. On a machine where `PATH` finds a `co` from
some other interpreter, it fails with `No module named connectonion`, and on
CI, where the only `co` is the one just installed, it passes. That is the local
run disagreeing with CI for a reason that is not a bug, the same disease as
`FORCE_COLOR` two days ago. It now runs the console script beside the
interpreter that is running the tests, which is the installation the test
claims to check.

None of these changes made a test go red. That is the point. The suite had
thirty-eight tests that could not fail, two that could not run, a warning
filter that could not report, and one that failed for the wrong reason. It
looked exactly the same as a suite that had none of those. The only way to
tell was to take each shortcut away and see whether anything changed.
