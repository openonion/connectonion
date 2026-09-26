"""Reading a Chrome profile's cookies the way Chrome on macOS writes them (#1477).

Every profile here is fake and encrypted with a known password: no real
Chrome, no Keychain, no network.
"""

import time

import pytest

from connectonion.useful_tools.browser_tools import chrome_cookies as chrome
from tests.fixtures.chrome_profile import PASSWORD, cookie, make_profile

HOUR = 3600


@pytest.mark.parametrize("meta_version", [23, 24])
def test_decrypts_both_database_versions(tmp_path, meta_version):
    """Version 24 prepends SHA-256(host) to every value; 23 does not. Getting
    this wrong imports a login cookie with 32 bytes of garbage in front."""
    profile = make_profile(tmp_path, "Default", [
        cookie(".linkedin.com", "li_at", "secret-session", expires=time.time() + HOUR),
    ], meta_version=meta_version)

    version, cookies = chrome.read_cookies(profile)
    value, reason = chrome.decrypt(cookies[0], chrome.derive_key(PASSWORD), version)

    assert version == meta_version
    assert (value, reason) == ("secret-session", "")


def test_a_wrong_key_is_a_skip_reason_not_garbage(tmp_path):
    profile = make_profile(tmp_path, "Default", [cookie(".a.com", "n", "v" * 40, expires=time.time() + HOUR)])
    version, cookies = chrome.read_cookies(profile)

    value, reason = chrome.decrypt(cookies[0], chrome.derive_key(b"not-the-password"), version)

    assert value is None and "could not be decrypted" in reason


def test_reads_a_copy_and_leaves_the_profile_as_it_was(tmp_path):
    profile = make_profile(tmp_path, "Default", [cookie(".a.com", "n", "v", expires=time.time() + HOUR)])
    db = profile / "Network" / "Cookies"
    before = (db.read_bytes(), db.stat().st_mtime_ns)

    chrome.read_cookies(profile)

    assert (db.read_bytes(), db.stat().st_mtime_ns) == before
    assert sorted(p.name for p in db.parent.iterdir()) == ["Cookies"]


def test_falls_back_to_the_older_cookies_location(tmp_path):
    profile = make_profile(tmp_path, "Default", [cookie("a.com", "n", "v")], network_dir=False)
    assert len(chrome.read_cookies(profile)[1]) == 1


def test_a_profile_is_found_by_folder_or_by_the_name_chrome_shows(tmp_path):
    make_profile(tmp_path, "Default", [], shown_name="Aaron")
    make_profile(tmp_path, "Profile 1", [], shown_name="openonion")

    assert chrome.resolve_profile(tmp_path, "Profile 1").name == "Profile 1"
    assert chrome.resolve_profile(tmp_path, "openonion").name == "Profile 1"
    assert chrome.resolve_profile(tmp_path, "OpenOnion").name == "Profile 1"
    with pytest.raises(chrome.ChromeImportError, match='"Profile 1" \\(openonion\\)'):
        chrome.resolve_profile(tmp_path, "Work")


def test_expired_and_partitioned_cookies_are_skipped_with_a_reason(tmp_path):
    profile = make_profile(tmp_path, "Default", [
        cookie(".a.com", "old", "v", expires=time.time() - HOUR),
        cookie(".a.com", "embedded", "v", expires=time.time() + HOUR, partition="https://b.com"),
        cookie(".a.com", "session", "v"),
    ])
    reasons = {c.name: chrome.skip_reason(c) for c in chrome.read_cookies(profile)[1]}

    assert reasons == {"old": "expired", "embedded": "partitioned (belongs to one embedding site)",
                       "session": ""}


def test_conversion_to_add_cookies_input(tmp_path):
    expires = int(time.time()) + HOUR
    profile = make_profile(tmp_path, "Default", [
        cookie(".linkedin.com", "li_at", "x", expires=expires, samesite=0),
        cookie("www.linkedin.com", "lang", "y", path="/feed", secure=False, httponly=False, samesite=1),
        cookie("www.linkedin.com", "unspecified", "z", samesite=-1),
    ])
    rows = {c.name: c for c in chrome.read_cookies(profile)[1]}

    persistent = chrome.to_playwright(rows["li_at"], "x")
    session = chrome.to_playwright(rows["lang"], "y")

    assert persistent == {"name": "li_at", "value": "x", "domain": ".linkedin.com", "path": "/",
                          "secure": True, "httpOnly": True, "expires": expires, "sameSite": "None"}
    # A session cookie carries no expiry: Playwright would otherwise persist it.
    assert session == {"name": "lang", "value": "y", "domain": "www.linkedin.com", "path": "/feed",
                       "secure": False, "httpOnly": False, "sameSite": "Lax"}
    assert "sameSite" not in chrome.to_playwright(rows["unspecified"], "z")


def test_site_grouping():
    assert chrome.matches("www.linkedin.com", "linkedin.com")
    assert not chrome.matches("notlinkedin.com", "linkedin.com")
    assert chrome.site_of("www.linkedin.com", ["linkedin.com"]) == "linkedin.com"
    assert chrome.site_of("api.github.com", []) == "github.com"
    assert chrome.site_of("www.bbc.co.uk", []) == "bbc.co.uk"


def test_the_keychain_is_asked_for_chromes_own_item(monkeypatch):
    calls = []

    class Done:
        returncode, stdout = 0, b"pw\n"

    monkeypatch.setattr(chrome.subprocess, "run", lambda argv, **kw: calls.append(argv) or Done())

    assert chrome.keychain_password() == b"pw"
    assert calls == [["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"]]


def _security_exits(monkeypatch, code, stderr):
    class Result:
        returncode, stdout = code, b""

    Result.stderr = stderr
    monkeypatch.setattr(chrome.subprocess, "run", lambda argv, **kw: Result())


def test_a_denied_keychain_dialog_says_what_to_do(monkeypatch):
    _security_exits(monkeypatch, 128, b"security: SecKeychainSearchCopyNext: User canceled the operation.\n")
    with pytest.raises(chrome.ChromeImportError, match="denied or cancelled.*Nothing was written.*Allow"):
        chrome.keychain_password()


def test_a_missing_keychain_item_says_so(monkeypatch):
    _security_exits(monkeypatch, 44, b"security: SecKeychainSearchCopyNext: The specified item "
                                     b"could not be found in the keychain.\n")
    with pytest.raises(chrome.ChromeImportError, match="no \"Chrome Safe Storage\" item.*Nothing was written"):
        chrome.keychain_password()


def test_an_unanswered_keychain_dialog_is_a_sentence_not_a_traceback(monkeypatch):
    """Live test, 2026-09-26: nobody at the screen, and the import died with
    TimeoutExpired after 120 seconds."""
    def times_out(argv, **kw):
        raise chrome.subprocess.TimeoutExpired(argv, kw.get("timeout"))

    monkeypatch.setattr(chrome.subprocess, "run", times_out)
    with pytest.raises(chrome.ChromeImportError, match="not answered.*Nothing was written.*Always Allow"):
        chrome.keychain_password()
