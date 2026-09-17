"""`check` says linked only when a device actually is.

`linked()` asked whether `session.db` exists. neonize creates that file when the
client starts — before the QR is shown, and regardless of whether anyone scans
it. So a pairing that timed out left a 160 KB database behind and
`co whatsapp check` answered:

    ✓ whatsapp reachable

Measured on a real run: `whatsmeow_device` held **0 rows**. The file was the
proxy; the linked device was the thing it stood for, and the two came apart at
exactly the moment the answer mattered — the operator believed they were linked
and the tool agreed.

A device row is the evidence. It appears when pairing completes and is what the
listener reads to reconnect without a new QR, so "is there a row" and "can this
reconnect" are the same question.
"""

import sqlite3

import pytest

from connectonion.inbox.whatsapp import WhatsApp


def make_session(path, *, devices=0, schema=True):
    """A session database in each of the states a real one passes through."""
    conn = sqlite3.connect(path)
    if schema:
        conn.execute("CREATE TABLE whatsmeow_device (jid TEXT PRIMARY KEY, registration_id INTEGER)")
        for i in range(devices):
            conn.execute("INSERT INTO whatsmeow_device VALUES (?, ?)", (f"6112345678{i}@s.whatsapp.net", i))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    return WhatsApp(), tmp_path / "session.db"


def test_no_file_at_all_is_not_linked(provider):
    wa, path = provider

    problems = wa.linked()

    assert problems and "No linked WhatsApp session" in problems[0]
    assert "co whatsapp listen" in problems[0]


def test_a_file_from_a_timed_out_pairing_is_not_linked(provider):
    """The case that produced a false green on a real run."""
    wa, path = provider
    make_session(path, devices=0)

    problems = wa.linked()

    assert problems, "an empty device table is not a linked device"
    assert "co whatsapp listen" in problems[0]


def test_a_paired_device_is_linked(provider):
    wa, path = provider
    make_session(path, devices=1)

    assert wa.linked() == []


def test_a_database_without_the_table_yet_is_not_linked(provider):
    """neonize creates the file before it creates its schema; that window is
    short and real, and reading it must not raise."""
    wa, path = provider
    make_session(path, schema=False)

    problems = wa.linked()

    assert problems and "co whatsapp listen" in problems[0]


def test_an_unreadable_database_says_so_rather_than_claiming_linked(provider):
    """Corrupt bytes are not evidence of a device. Guessing 'linked' here would
    send the operator to debug a listener that can never connect."""
    wa, path = provider
    path.write_bytes(b"this is not a sqlite database")

    problems = wa.linked()

    assert problems, "an unreadable session must not read as linked"


def test_check_surfaces_it(provider, monkeypatch):
    """The whole point: the command a person runs must not say reachable."""
    wa, path = provider
    make_session(path, devices=0)
    monkeypatch.setattr(wa, "listen_requirements", list)
    monkeypatch.setattr(wa, "protocol_age", list)

    assert wa.check(), "check reported no problem for an unlinked session"
