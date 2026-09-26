"""
Purpose: Read the cookies of a Google Chrome profile on macOS, decrypted the way Chrome itself does, and turn them into Playwright add_cookies input.
LLM-Note:
  Dependencies: imports from [sqlite3, json, hashlib, shutil, subprocess, tempfile, datetime, cryptography (AES/PBKDF2)] | imported by [cli/commands/browser_import.py] | tested by [tests/unit/test_chrome_cookies.py]
  Data flow: chrome_root() → resolve_profile(root, name) (folder name or Local State display name) → read_cookies(profile_dir) copies Network/Cookies (+ -wal/-shm/-journal) into a private temp dir and reads the copy → rows with encrypted bytes → keychain_password() → derive_key() → decrypt(row, key, meta_version) → to_playwright(row, value)
  State/Effects: never writes to or locks the source profile; the private copy is removed before read_cookies returns | keychain_password() runs `security`, which may show a macOS permission dialog | never opens Login Data (saved passwords)
  Integration: exposes chrome_root(), resolve_profile(), read_cookies(), keychain_password(), derive_key(), decrypt(), site_of(), matches(), to_playwright(), skip_reason(), ChromeCookie, ChromeImportError | values live only in memory and in the dict handed to add_cookies
  Errors: ChromeImportError with a sentence naming what to do next; per-cookie decryption problems are returned as a skip reason, not raised, so one odd cookie does not stop an import
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# Chrome stores expiry as microseconds since 1601-01-01 (the Windows epoch).
_WINDOWS_TO_UNIX_SECONDS = 11644473600
# Playwright refuses anything past year 9999.
_MAX_EXPIRES = 253402300799
# Chrome's own macOS constants (os_crypt_mac.mm): a fixed salt, 1003 rounds,
# a 16-byte AES-128 key and an IV of sixteen spaces.
_SALT = b"saltysalt"
_ITERATIONS = 1003
_IV = b" " * 16
# From cookie DB version 24 Chrome prepends SHA-256(host_key) to the plaintext,
# so a value copied onto another host fails to decrypt into anything useful.
_HOST_HASH_VERSION = 24
_SAMESITE = {0: "None", 1: "Lax", 2: "Strict"}  # -1 (unspecified) is left for the browser to default


class ChromeImportError(Exception):
    """A problem that stops the import, phrased as what to do about it."""


@dataclass
class ChromeCookie:
    host_key: str
    name: str
    path: str
    expires_utc: int
    is_secure: bool
    is_httponly: bool
    samesite: int
    is_persistent: bool
    top_frame_site_key: str
    plain_value: str
    encrypted_value: bytes

    @property
    def host(self) -> str:
        return self.host_key.lstrip(".")


def chrome_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"


def resolve_profile(root: Path, wanted: str) -> Path:
    """The profile folder for a folder name ("Profile 1") or the name Chrome shows ("openonion")."""
    if (root / wanted).is_dir():
        return root / wanted
    names = {}
    local_state = root / "Local State"
    if local_state.is_file():
        cache = json.loads(local_state.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
        names = {folder: str(info.get("name", "")) for folder, info in cache.items()}
    matches = [folder for folder, shown in names.items() if shown.lower() == wanted.lower()]
    if len(matches) == 1 and (root / matches[0]).is_dir():
        return root / matches[0]
    known = ", ".join(f'"{folder}" ({shown})' for folder, shown in sorted(names.items())) or "none found"
    raise ChromeImportError(f'no Chrome profile called "{wanted}" under {root}. Profiles: {known}')


def _cookie_db(profile_dir: Path) -> Path:
    for candidate in (profile_dir / "Network" / "Cookies", profile_dir / "Cookies"):
        if candidate.is_file():
            return candidate
    raise ChromeImportError(f"no Cookies database in {profile_dir} (looked in Network/Cookies and Cookies)")


def read_cookies(profile_dir: Path) -> Tuple[int, List[ChromeCookie]]:
    """(meta version, cookies) from a private copy of the profile's cookie database.

    A copy because Chrome holds the file locked while it runs, and because
    opening the original could checkpoint its WAL into it — the source profile
    must come out of this exactly as it went in.
    """
    source = _cookie_db(profile_dir)
    scratch = Path(tempfile.mkdtemp(prefix="co-chrome-import-"))  # mkdtemp is 0700
    try:
        copy = scratch / "Cookies"
        shutil.copyfile(source, copy)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = source.with_name(source.name + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, scratch / ("Cookies" + suffix))
        connection = sqlite3.connect(str(copy))
        try:
            return _meta_version(connection), _rows(connection)
        finally:
            connection.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _meta_version(connection) -> int:
    row = connection.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
    return int(row[0]) if row else 0


def _rows(connection) -> List[ChromeCookie]:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(cookies)")}
    # Older databases have no partitioning column; treat them as unpartitioned.
    partition = "top_frame_site_key" if "top_frame_site_key" in columns else "''"
    persistent = "is_persistent" if "is_persistent" in columns else "has_expires"
    query = (f"SELECT host_key, name, path, expires_utc, is_secure, is_httponly, samesite, "
             f"{persistent}, {partition}, value, encrypted_value FROM cookies")
    return [ChromeCookie(host_key=r[0], name=r[1], path=r[2] or "/", expires_utc=int(r[3] or 0),
                         is_secure=bool(r[4]), is_httponly=bool(r[5]), samesite=int(r[6]),
                         is_persistent=bool(r[7]), top_frame_site_key=r[8] or "",
                         plain_value=r[9] or "", encrypted_value=bytes(r[10] or b""))
            for r in connection.execute(query)]


def keychain_password() -> bytes:
    """The "Chrome Safe Storage" secret, which is what Chrome derives its cookie key from."""
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
        capture_output=True, timeout=120,
    )
    if result.returncode != 0:
        raise ChromeImportError("could not read \"Chrome Safe Storage\" from the Keychain "
                                "(the dialog was denied, or Chrome has never run here). "
                                "Run the import again and choose Allow.")
    return result.stdout.strip()


def derive_key(password: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    return PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=_SALT, iterations=_ITERATIONS).derive(password)


def decrypt(cookie: ChromeCookie, key: bytes, meta_version: int) -> Tuple[Optional[str], str]:
    """(value, "") or (None, why it was skipped). Never raises for one bad cookie."""
    if not cookie.encrypted_value:
        return cookie.plain_value, ""
    if not cookie.encrypted_value.startswith(b"v10"):
        return None, "encrypted in a format this version does not read"
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    body = cookie.encrypted_value[3:]
    if not body or len(body) % 16:
        return None, "could not be decrypted"
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    padded = decryptor.update(body) + decryptor.finalize()
    pad = padded[-1]
    if not 1 <= pad <= 16 or padded[-pad:] != bytes([pad]) * pad:
        return None, "could not be decrypted (wrong Keychain key?)"
    plain = padded[:-pad]
    if meta_version >= _HOST_HASH_VERSION:
        # Checked, not just stripped: a mismatch means the bytes are not what
        # Chrome wrote for this host, and importing them would be a broken login.
        if plain[:32] != hashlib.sha256(cookie.host_key.encode()).digest():
            return None, "could not be decrypted (host check failed)"
        plain = plain[32:]
    try:
        return plain.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "could not be decrypted (not text)"


def matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def site_of(host: str, domains: List[str]) -> str:
    """The site a cookie is listed under: the --domain it matched, else its last two labels.

    Two labels is a simplification (no public-suffix list ships with us), so
    `example.co.uk` keeps three when the second-to-last label looks like one.
    """
    for domain in domains:
        if matches(host, domain):
            return domain
    labels = host.split(".")
    keep = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and len(labels[-2]) <= 3 else 2
    return ".".join(labels[-keep:])


def skip_reason(cookie: ChromeCookie, now: Optional[float] = None) -> str:
    """Why a cookie cannot be imported before it is even decrypted, or ""."""
    if cookie.top_frame_site_key:
        return "partitioned (belongs to one embedding site)"
    if cookie.is_persistent and unix_expires(cookie) <= (now if now is not None else time.time()):
        return "expired"
    return ""


def unix_expires(cookie: ChromeCookie) -> float:
    return cookie.expires_utc / 1_000_000 - _WINDOWS_TO_UNIX_SECONDS


def to_playwright(cookie: ChromeCookie, value: str) -> dict:
    """One add_cookies entry. The domain is Chrome's host_key as-is: a leading
    dot is a domain cookie; without one Playwright still sets a domain cookie
    for that exact host, which is as close to host-only as its API allows."""
    entry = {"name": cookie.name, "value": value, "domain": cookie.host_key, "path": cookie.path,
             "secure": cookie.is_secure, "httpOnly": cookie.is_httponly}
    if cookie.is_persistent:
        entry["expires"] = min(int(unix_expires(cookie)), _MAX_EXPIRES)
    if cookie.samesite in _SAMESITE:
        entry["sameSite"] = _SAMESITE[cookie.samesite]
    return entry


def is_macos() -> bool:
    return sys.platform == "darwin"
