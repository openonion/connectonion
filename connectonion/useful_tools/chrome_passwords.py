"""Read the owner's own saved logins from Chrome (and other Chromium browsers) on this Mac, read-only.

Each login's password is AES-128-CBC encrypted with the browser's "Safe Storage" key, which lives in the
login Keychain. We read that key (one Touch ID), derive the AES key as Chromium does, and decrypt the
`Login Data` SQLite in memory. Nothing is written; values are returned to the caller, never logged.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Chromium's fixed KDF for the macOS Safe Storage key.
SALT = b"saltysalt"
ITERATIONS = 1003
IV = b" " * 16
KEY_LEN = 16

# Browser -> (Keychain service for the Safe Storage key, user-data directory under Application Support).
BROWSERS = {
    "chrome": ("Chrome Safe Storage", "Google/Chrome"),
    "edge": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
    "brave": ("Brave Safe Storage", "BraveSoftware/Brave-Browser"),
}


class ChromeError(Exception):
    """A readable failure: no browser data, or the Keychain key could not be read."""


def safe_storage_key(browser: str = "chrome") -> bytes:
    """The AES key for a browser's saved passwords, derived from its Keychain Safe Storage secret (one Touch ID)."""
    service = BROWSERS.get(browser, (None,))[0]
    if not service:
        raise ChromeError(f"Unknown browser {browser!r}")
    done = subprocess.run(["security", "find-generic-password", "-ws", service],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    if done.returncode != 0:
        raise ChromeError(f"{browser}: its Safe Storage key is not in the Keychain (is {browser} installed and used?)")
    secret = done.stdout.strip().encode()
    return hashlib.pbkdf2_hmac("sha1", secret, SALT, ITERATIONS, dklen=KEY_LEN)


def _decrypt(value: bytes, key: bytes) -> str | None:
    """One encrypted password field to text, or None when it isn't a v10/v11 AES-CBC value we can read."""
    if not value or value[:3] not in (b"v10", b"v11"):
        return None
    decryptor = Cipher(algorithms.AES(key), modes.CBC(IV)).decryptor()
    plain = decryptor.update(value[3:]) + decryptor.finalize()
    if not plain:
        return None
    pad = plain[-1]
    if 1 <= pad <= 16:
        plain = plain[:-pad]
    return plain.decode("utf-8", "replace")


def login_data_paths(browser: str = "chrome") -> list[Path]:
    """Every profile's `Login Data` for a browser (Default, Profile 1, …)."""
    base = Path.home() / "Library/Application Support" / BROWSERS[browser][1]
    if not base.is_dir():
        return []
    return sorted(p / "Login Data" for p in base.iterdir() if (p / "Login Data").is_file())


def read_logins(path: Path, key: bytes) -> list[dict]:
    """The saved logins in one `Login Data` file: [{url, username, password}], decrypted in memory.

    The file is copied first because Chrome keeps it locked while running; the copy is deleted straight after.
    """
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / "Login Data"
        shutil.copy2(path, copy)
        conn = sqlite3.connect(f"file:{copy}?immutable=1", uri=True)
        try:
            rows = conn.execute("SELECT origin_url, username_value, password_value FROM logins").fetchall()
        except sqlite3.DatabaseError as error:
            raise ChromeError(f"Login Data could not be read: {error}")
        finally:
            conn.close()
    out = []
    for url, username, password in rows:
        text = _decrypt(password, key)
        if text:
            out.append({"url": url or "", "username": username or "", "password": text})
    return out


def all_logins(browser: str = "chrome") -> list[dict]:
    """Every saved login across a browser's profiles. Raises ChromeError when the browser has no data here."""
    paths = login_data_paths(browser)
    if not paths:
        raise ChromeError(f"No {browser} password data on this Mac")
    key = safe_storage_key(browser)
    seen, out = set(), []
    for path in paths:
        for login in read_logins(path, key):
            mark = (login["url"], login["username"])
            if login["password"] and mark not in seen:
                seen.add(mark)
                out.append(login)
    return out
