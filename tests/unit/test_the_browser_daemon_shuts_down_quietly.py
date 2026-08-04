"""A browser daemon that is shutting down exits; it does not abort the process.

Closing the listener is how a daemon is told to stop — `_cleanup` closes the
socket first, and `_accept`'s docstring says so:

    A dead listener still raises out on both platforms so a dying daemon exits.

Raising is the intended mechanism. Escaping as an unhandled thread exception is
not. Each `serve()` thread prints a full traceback to stderr on its way out, and
with several of them going at once while the interpreter finalises, one holds
the stderr buffer lock when finalisation starts:

    ConnectionAbortedError: [Errno 53] Software caused connection abort
      File ".../browser_agent/daemon.py", line 694, in _accept
        conn, _ = self._srv.accept()
    ...
    Fatal Python error: _enter_buffered_busy: could not acquire lock for
    <_io.BufferedWriter name='<stderr>'> at interpreter shutdown, possibly due
    to daemon threads

Observed at the end of a full local test run: 4181 tests passed and the process
then died with SIGABRT (exit 134). An abort at shutdown discards whatever was
still buffered, and what a user sees when they stop `co browser` is a wall of
tracebacks under a fatal error.

So: a listener closed by our own shutdown ends the loop quietly. A socket error
at any other time still raises — a daemon whose listener breaks while it is
supposed to be serving is a real failure and must not be swallowed.
"""

import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from connectonion.cli.browser_agent import daemon as d


@pytest.fixture
def server():
    """A daemon on its own socket path, no browser launched.

    Not bound here: serve() binds for itself, and binding twice on one path is
    a different failure than the one under test.

    Its own short directory rather than pytest's tmp_path, because an AF_UNIX
    path is capped near 104 bytes and pytest's includes the test's own name —
    long test names in a deep checkout produce "AF_UNIX path too long", which
    looks like a daemon failure and is not one.
    """
    directory = tempfile.mkdtemp(prefix="cod")
    server = d.BrowserDaemon(str(Path(directory) / "s.sock"), headless=True)
    yield server
    if server._srv:
        server._srv.close()
    shutil.rmtree(directory, ignore_errors=True)


class TestClosingTheListenerStopsIt:

    def test_serve_returns_instead_of_raising(self, server):
        error = {}

        def run():
            try:
                server.serve()
            except BaseException as exc:      # SystemExit included
                error["exc"] = exc

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        threading.Event().wait(0.3)

        server._cleanup()
        thread.join(timeout=5)

        assert not thread.is_alive(), "serve() did not stop when the listener closed"
        assert "exc" not in error, f"serve() raised on shutdown: {error.get('exc')!r}"

    def test_it_is_marked_as_closing(self, server):
        server._bind()
        server._cleanup()

        assert server._closing is True

    def test_a_fresh_daemon_is_not_closing(self, server):
        assert server._closing is False


class TestARealFailureStillRaises:
    """Swallowing every socket error would hide a daemon that broke while serving."""

    def test_an_accept_error_while_serving_is_not_swallowed(self, server):
        def explode():
            raise OSError("the listener broke while we were serving")

        server._accept = explode

        with pytest.raises(OSError):
            server.serve()

    def test_a_non_socket_error_is_untouched(self, server):
        def explode():
            raise ValueError("something else entirely")

        server._accept = explode

        with pytest.raises(ValueError):
            server.serve()
