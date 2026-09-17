"""Live end-to-end acceptance for `co whatsapp`, against real WhatsApp accounts.

LLM-Note: Tests for connectonion/inbox/whatsapp.py and the inbox verbs, through the real CLI

What it tests:
- A linked session connects with no QR, and a restart reuses the link instead of pairing again
- `check` passes on a linked session, and refuses a session file that never finished pairing
- A send to our own chat goes out and is not delivered back as an inbound message
- Ctrl-C stops the listener
- With a second number: a direct message arrives once and the reply reaches the sender,
  a message sent while the listener was down arrives exactly once, and in a group only a
  message that names the number is `mentioned`

Components under test:
- `co whatsapp listen | send | receive | reply | check`, driven as subprocesses, so the
  same file accepts a source checkout or an installed wheel (WHATSAPP_E2E_CO)

Why this exists: every WhatsApp check used to mean scanning a QR and typing messages by
hand. A linked session is a file and survives restarts, so each number is scanned
**once, ever**; after that this suite is the whole acceptance run.

One-time setup, per number (a dedicated number, never a personal one):

    WHATSAPP_SESSION=~/.co/e2e/whatsapp/bot.db CO_INBOX_HOME=~/.co/e2e/whatsapp/link \
        co whatsapp listen          # scan the QR, wait for "connected", then close the window

WhatsApp allows four linked devices per number, so link the bot number a second time for
tests rather than reusing the session your everyday listener holds: two processes on one
session take the socket from each other. For the driver tests, do the same for a second
number (driver.db). For the group test, make a group containing both numbers.

Run:

    WHATSAPP_E2E_BOT_SESSION=~/.co/e2e/whatsapp/bot.db \
    WHATSAPP_E2E_DRIVER_SESSION=~/.co/e2e/whatsapp/driver.db \
    WHATSAPP_E2E_GROUP=1203630000000@g.us \
        python -m pytest -m real_api tests/e2e/real_api/test_real_whatsapp.py -v

Against the installed package instead of this checkout:
    WHATSAPP_E2E_CO="$(command -v co)"  (or "python3.14 -m connectonion.cli.main")

Every message carries a fresh nonce, so a run never mistakes an old message for its own.
"""

import json
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli, pytest.mark.timeout(900)]

CONNECT_SECONDS = 90
RECEIVE_SECONDS = 120
QR_BLOCKS = re.compile("[▀▄█]")


def _co_command() -> list:
    configured = os.environ.get("WHATSAPP_E2E_CO", "").strip()
    return shlex.split(configured) if configured else [sys.executable, "-m", "connectonion.cli.main"]


def _session(variable: str) -> Path:
    value = os.environ.get(variable, "").strip()
    if not value:
        pytest.skip(f"Set {variable} to a linked WhatsApp session file (see this module's docstring)")
    path = Path(value).expanduser()
    if not path.exists():
        pytest.skip(f"{variable}={path} does not exist; link it once with `co whatsapp listen`")
    return path


def _nonce(label: str) -> str:
    return f"co-e2e-{label}-{uuid.uuid4().hex[:10]}"


def _paired_devices(session: Path) -> int:
    """Rows in whatsmeow's device table: 1 once a phone has confirmed the link."""
    with sqlite3.connect(f"file:{session}?mode=ro", uri=True) as db:
        return db.execute("select count(*) from whatsmeow_device").fetchone()[0]


class Listener:
    """One `co whatsapp listen` on its own inbox root, driven only through the CLI."""

    def __init__(self, label: str, session: Path, workdir: Path):
        self.label = label
        self.session = session
        self.root = workdir / label
        self.inbox = self.root / "whatsapp"
        self.output = workdir / f"{label}-listen.out"
        self.env = dict(
            os.environ,
            WHATSAPP_SESSION=str(session),
            CO_INBOX_HOME=str(self.root),
            PYTHONUNBUFFERED="1",
            NO_COLOR="1",
        )
        self.process = None
        self.number = ""

    # ---- lifecycle -----------------------------------------------------------

    def start(self) -> "Listener":
        handle = self.output.open("ab")
        self.process = subprocess.Popen(
            _co_command() + ["whatsapp", "listen"],
            stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=self.env, start_new_session=True,
        )
        handle.close()
        found = self.wait_for_log(r"connected as (\d+)", CONNECT_SECONDS, after=self._log_size_at_start())
        self.number = found.group(1)
        return self

    def stop(self) -> None:
        # SIGTERM, not SIGINT: see test_ctrl_c_stops_the_listener.
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(10)

    @property
    def jid(self) -> str:
        return f"{self.number}@s.whatsapp.net"

    # ---- observation -----------------------------------------------------------

    def log_text(self) -> str:
        logfile = self.inbox / "log"
        return logfile.read_text(encoding="utf-8") if logfile.exists() else ""

    def _log_size_at_start(self) -> int:
        self._start_offset = len(self.log_text())
        return self._start_offset

    def wait_for_log(self, pattern: str, seconds: float, *, after: int = 0):
        deadline = time.monotonic() + seconds
        compiled = re.compile(pattern)
        while time.monotonic() < deadline:
            found = compiled.search(self.log_text()[after:])
            if found:
                return found
            if self.process is not None and self.process.poll() is not None:
                break
            time.sleep(0.5)
        raise AssertionError(
            f"{self.label}: no /{pattern}/ in the inbox log within {seconds}s "
            f"(listener exit={self.process.poll() if self.process else None}).\n"
            f"--- log ---\n{self.log_text()[-2000:]}\n--- output ---\n{self.output_text()[-2000:]}"
        )

    def output_text(self) -> str:
        return self.output.read_text(encoding="utf-8", errors="replace") if self.output.exists() else ""

    def received(self) -> list:
        path = self.inbox / "received.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---- verbs -----------------------------------------------------------------

    def co(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            _co_command() + ["whatsapp", *args],
            env=self.env, capture_output=True, text=True, timeout=timeout,
        )

    def receive_containing(self, needle: str, seconds: float = RECEIVE_SECONDS) -> dict:
        """Take messages until one contains `needle`; others (real chatter) are released."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            left = max(1, int(deadline - time.monotonic()))
            result = self.co("receive", "--no-start", "-t", str(left), timeout=left + 30)
            if result.returncode == 124:
                break
            assert result.returncode == 0, f"receive failed: {result.stderr}"
            message = json.loads(result.stdout.strip().splitlines()[-1])
            if needle in message.get("text", ""):
                return message
            self.co("done", message["id"])  # not ours; do not leave it for the hourly sweep
        raise AssertionError(f"{self.label}: no message containing {needle!r} within {seconds}s\n"
                             f"--- log ---\n{self.log_text()[-2000:]}")


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def bot(workdir):
    listener = Listener("bot", _session("WHATSAPP_E2E_BOT_SESSION"), workdir)
    listener.start()
    yield listener
    listener.stop()


@pytest.fixture
def driver(workdir):
    listener = Listener("driver", _session("WHATSAPP_E2E_DRIVER_SESSION"), workdir)
    listener.start()
    yield listener
    listener.stop()


# ---- one number ---------------------------------------------------------------


def test_a_linked_session_connects_without_showing_a_qr(bot):
    assert bot.number.isdigit()
    assert _paired_devices(bot.session) == 1
    assert not QR_BLOCKS.search(bot.output_text()), "a linked session must not ask to be scanned again"
    assert "paired" not in bot.log_text(), "connecting reused the link; nothing was paired"


def test_check_passes_on_a_linked_session(bot):
    result = bot.co("check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "whatsapp reachable" in result.stdout


def test_a_restart_reuses_the_link_instead_of_pairing_again(bot):
    first = bot.number
    bot.stop()
    bot.start()

    assert bot.number == first
    assert "paired" not in bot.log_text()


def test_a_message_to_our_own_chat_is_sent_and_not_delivered_back(bot):
    nonce = _nonce("self")

    result = bot.co("send", bot.jid, nonce)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "send prints the id WhatsApp gave the message"
    time.sleep(15)  # our own message comes back over the socket; give it time to be dropped
    assert not any(nonce in m.get("text", "") for m in bot.received()), \
        "our own message must not become an inbound one, or the bot would answer itself"


@pytest.mark.xfail(strict=True, reason="1.8.6a1: SIGINT is not handled while client.connect() blocks in Go")
def test_ctrl_c_stops_the_listener(bot):
    bot.process.send_signal(signal.SIGINT)

    bot.process.wait(20)  # raises TimeoutExpired, and the fixture's SIGTERM cleans up


def test_check_refuses_a_session_that_never_finished_pairing(workdir):
    # Needs no linked account: it only has to reach WhatsApp far enough to be shown a QR.
    # What a failed or abandoned scan leaves behind: the file exists, no device row does.
    session = workdir / "unpaired" / "session.db"
    session.parent.mkdir()
    half = Listener("unpaired", session, workdir)
    half.process = subprocess.Popen(
        _co_command() + ["whatsapp", "listen"],
        stdout=half.output.open("ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        env=half.env, start_new_session=True,
    )
    try:
        deadline = time.monotonic() + CONNECT_SECONDS
        while not QR_BLOCKS.search(half.output_text()) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert QR_BLOCKS.search(half.output_text()), "the listener never offered a QR"
    finally:
        half.stop()
    assert session.exists() and _paired_devices(session) == 0

    result = half.co("check")

    assert result.returncode == 3, "a session nobody scanned is not a linked device"


# ---- two numbers --------------------------------------------------------------


def test_a_direct_message_arrives_once_and_the_reply_reaches_the_sender(bot, driver):
    question = _nonce("dm")

    sent = driver.co("send", bot.jid, question)
    assert sent.returncode == 0, sent.stderr

    message = bot.receive_containing(question)
    assert message["mentioned"] is True, "a direct message is addressed to us by existing"
    assert message["chat"].endswith(("@s.whatsapp.net", "@lid"))

    answer = f"pong {question}"
    replied = bot.co("reply", message["id"], answer)
    assert replied.returncode == 0, replied.stderr
    assert replied.stdout.strip()

    echoed = driver.receive_containing(answer)
    assert echoed["text"] == answer
    assert sum(question in m.get("text", "") for m in bot.received()) == 1


def test_a_message_sent_while_the_listener_is_down_arrives_exactly_once(bot, driver):
    gap = _nonce("gap")
    bot.stop()

    sent = driver.co("send", bot.jid, gap)
    assert sent.returncode == 0, sent.stderr
    time.sleep(20)  # long enough that the server, not a socket buffer, has to hold it
    bot.start()

    message = bot.receive_containing(gap)
    assert message["text"].endswith(gap)
    time.sleep(10)  # a redelivery, if any, lands now
    assert sum(gap in m.get("text", "") for m in bot.received()) == 1


def test_in_a_group_only_a_message_naming_the_number_is_mentioned(bot, driver):
    """KNOWN GAP: this sends the *text* `@<number>`, not a real mention.

    `_addressed_in_group` has three paths — a `mentionedJID` entry, a reply to
    us, and our id written in the text — and a message composed by `send`
    exercises only the third. In September 2026 that let a real bug through:
    WhatsApp had migrated the bot account to LID addressing, a mention tapped
    out of the app's picker arrived as the account's LID rather than its phone
    number, and it was recorded `mentioned: False` while this test stayed green.

    Producing a genuine `mentionedJID` means picking the name from WhatsApp's
    own mention picker, which is the manual step this suite exists to remove, so
    the first path is covered in `tests/unit/test_inbox_whatsapp.py` against the
    real shape instead. Read a pass here as "the text path works", not as "being
    @-mentioned works".
    """
    group = os.environ.get("WHATSAPP_E2E_GROUP", "").strip()
    if not group:
        pytest.skip("Set WHATSAPP_E2E_GROUP to a group JID containing both numbers")
    chatter = _nonce("chatter")
    ping = _nonce("ping")

    assert driver.co("send", group, chatter).returncode == 0
    assert driver.co("send", group, f"@{bot.number} {ping}").returncode == 0

    plain = bot.receive_containing(chatter)
    named = bot.receive_containing(ping)
    assert plain["chat"] == group and named["chat"] == group
    assert plain["mentioned"] is False
    assert named["mentioned"] is True
