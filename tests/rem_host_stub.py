"""A tests-only server that answers GET /info the way a co ai Host does.

The reader chooses a Host by what /info says (address, version). A real Host
takes seconds to start and needs an identity and a key; these tests are about
the choice, so the answer is all they need. Product code has no test switch.

In a test: `with serving("owner", "1.2.3") as port:` (a thread).
As a process, so it has a pid and a command line to check and to stop:
    python tests/rem_host_stub.py ADDRESS VERSION ai --port N --no-listen --no-launch
(the tail is the real Host's, which is what live_host._alive and the leak guard match).
"""

import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer


def _server(port: int, address: str, version):
    class Info(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"address": address, "name": "stub",
                               **({} if version is None else {"version": version})}).encode()
            self.send_response(200 if self.path == "/info" else 404)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # quiet: pytest's output is the test's
            pass

    return HTTPServer(("127.0.0.1", port), Info)


@contextmanager
def serving(address: str, version, port: int = 0):
    """The port a stub answers on, for the length of the block."""
    server = _server(port, address, version)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    _server(int(sys.argv[sys.argv.index("--port") + 1]), sys.argv[1], sys.argv[2]).serve_forever()
