"""Chrome/Chromium password import (#3274): decrypt Login Data with the Safe Storage key, file to the vault.

The Keychain read is not exercised here; a known AES key stands in for it, so the test is about the page
format and the decryption, not the owner's real Keychain.
"""
import sqlite3

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from connectonion.useful_tools import chrome_passwords as cp
from connectonion.rem import keys


KEY = b"0123456789abcdef"  # 16 bytes; what safe_storage_key would derive


def _encrypt(text: str) -> bytes:
    body = text.encode()
    pad = 16 - len(body) % 16
    body += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(KEY), modes.CBC(cp.IV)).encryptor()
    return b"v10" + enc.update(body) + enc.finalize()


def test_decrypt_round_trips_and_skips_unencrypted():
    assert cp._decrypt(_encrypt("hunter2"), KEY) == "hunter2"
    assert cp._decrypt(b"plain text", KEY) is None
    assert cp._decrypt(b"", KEY) is None


def test_read_logins_decrypts_every_row(tmp_path):
    db = tmp_path / "Login Data"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB)")
    conn.executemany("INSERT INTO logins VALUES (?, ?, ?)", [
        ("https://mail.example.com/", "me@example.com", _encrypt("s3cret")),
        ("https://bank.example.com/login", "me", _encrypt("p@ss")),
        ("https://nopass.example.com/", "me", b""),  # a saved site with no password
    ])
    conn.commit()
    conn.close()
    logins = cp.read_logins(db, KEY)
    assert [(x["username"], x["password"]) for x in logins] == [("me@example.com", "s3cret"), ("me", "p@ss")]


def test_import_browser_files_a_page_each_and_counts_only(tmp_path, monkeypatch):
    from connectonion.rem.config import prepare
    from connectonion.rem import vault
    prepare(tmp_path / "rem")
    stored = {}
    monkeypatch.setattr(vault, "put", lambda slug, account, secret: stored.__setitem__(slug, secret))
    monkeypatch.setattr(cp, "all_logins", lambda browser: [
        {"url": "https://mail.example.com/", "username": "me@example.com", "password": "s3cret"},
        {"url": "https://bank.example.com/login", "username": "me", "password": "p@ss"},
        {"url": "", "username": "x", "password": "x"}])  # no service -> skipped
    result = keys.import_browser(tmp_path / "rem", "chrome")
    assert result == {"filed": 2, "skipped": 1}
    # The value is in the vault, never in the page.
    page = (tmp_path / "rem" / "keys" / sorted((tmp_path / "rem" / "keys").iterdir())[0].name).read_text()
    assert "s3cret" not in page and "p@ss" not in page
    assert "s3cret" in stored.values()
