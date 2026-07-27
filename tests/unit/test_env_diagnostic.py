"""The [env] diagnostic must not reach agents through tool output.

`bash` appends any non-empty stderr to the tool result as "STDERR:",
regardless of exit code. Since agents drive the browser as
bash("co browser <verb>"), an unconditional [env] print made every
successful command look to the agent like it had failed.
"""

import subprocess
import sys


def _run(env_extra=None, tty=False):
    """Import connectonion in a subprocess and return what it wrote to stderr."""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp"}
    env.update(env_extra or {})
    if tty:
        # A pty makes stderr a terminal, which is the human case.
        code = (
            "import pty, os, sys\n"
            "pid, fd = pty.fork()\n"
            "if pid == 0:\n"
            "    os.execvpe(sys.executable, [sys.executable, '-c', 'import connectonion'], os.environ)\n"
            "out = b''\n"
            "try:\n"
            "    while True:\n"
            "        d = os.read(fd, 1024)\n"
            "        if not d: break\n"
            "        out += d\n"
            "except OSError: pass\n"
            "sys.stdout.write(out.decode(errors='replace'))\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        return r.stdout
    r = subprocess.run([sys.executable, "-c", "import connectonion"],
                       capture_output=True, text=True, env=env)
    return r.stderr


def test_piped_output_carries_no_env_diagnostic():
    """The agent's case: stderr is a pipe, so nothing should be written."""
    assert "[env]" not in _run()


def test_a_terminal_still_gets_the_diagnostic():
    """The human's case: it answers 'which env file won?'."""
    assert "[env]" in _run(tty=True)


def test_co_debug_env_forces_it_back_on():
    """Escape hatch for debugging a piped or redirected run."""
    assert "[env]" in _run({"CO_DEBUG_ENV": "1"})
