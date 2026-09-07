"""Opt-in real CLI regression: CO_BROWSER_PROXY_E2E=1 xvfb-run -a python <file>."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest


@unittest.skipUnless(os.getenv("CO_BROWSER_PROXY_E2E") == "1", "real browser opt-in required")
class ProxyNavigationTests(unittest.TestCase):
    def test_valid_proxy_and_rejected_credentials(self):
        password = secrets.token_urlsafe(24)
        expected = "Basic " + base64.b64encode(f"test:{password}".encode()).decode()
        rejected = []
        accepted = []

        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    # Chromium cancels background requests when the test closes.
                    pass

            def do_GET(self):
                if self.headers.get("Proxy-Authorization") != expected:
                    rejected.append(True)
                    self.send_response(407)
                    self.send_header("Proxy-Authenticate", 'Basic realm="acceptance"')
                    body = b""
                else:
                    accepted.append(True)
                    self.send_response(200)
                    body = b"<p>PROXY_AUTHENTICATED</p>"
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        co = os.getenv("CO_BROWSER_TEST_CLI", str(Path(sys.executable).with_name("co")))
        try:
            for valid in (True, False):
                with self.subTest(valid=valid), tempfile.TemporaryDirectory(prefix="co-proxy-") as directory:
                    root = Path(directory)
                    credential = password if valid else secrets.token_urlsafe(24)
                    env = dict(os.environ, CO_WHO="proxy-navigation-test",
                               CO_BROWSER_SOCK=str(root / "b.sock"),
                               CO_BROWSER_PROFILE_DIR=str(root / "profile"),
                               BROWSER_PROXY=f"http://test:{credential}@127.0.0.1:{server.server_port}")

                    def run(*args):
                        return subprocess.run([co, "browser", *args], env=env, cwd=root,
                                              capture_output=True, text=True, timeout=90)

                    before = len(accepted)
                    rejected_before = len(rejected)
                    try:
                        result = run("go_to", "http://co-proxy-test.invalid/")
                        self.assertFalse(credential in result.stdout + result.stderr,
                                         "credential appeared in CLI output")
                        if valid:
                            self.assertEqual(result.returncode, 0)
                            self.assertIn("Navigated to", result.stdout)
                            self.assertIn("PROXY_AUTHENTICATED", run("get_text").stdout)
                            self.assertGreater(len(accepted), before)
                        else:
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn("BrowserNavigationError", result.stdout + result.stderr)
                            # Chromium can surface a rejected challenge as a
                            # network error instead of returning its HTTP 407.
                            self.assertRegex(result.stdout + result.stderr,
                                             r"BrowserNavigationError: NAVIGATION_(PROXY_AUTH_FAILED|NETWORK_ERROR)")
                            self.assertNotIn("Navigated to", result.stdout)
                            self.assertEqual(len(accepted), before)
                            self.assertGreater(len(rejected), rejected_before)
                        print(f"PASS proxy valid={valid}, cli_exit={result.returncode}", flush=True)
                    finally:
                        self.assertEqual(run("close").returncode, 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
