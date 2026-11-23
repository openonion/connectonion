"""The login keychain through `security`, always a stand-in here: no test reads the real Keychain (#3305)."""
import subprocess

import pytest

from connectonion.useful_tools import macos_keychain as mk

DUMP = '''keychain: "/Users/someone/Library/Keychains/login.keychain-db"
version: 512
class: "inet"
attributes:
    0x00000007 <blob>="mail.example.test"
    "acct"<blob>="me@example.test"
    "srvr"<blob>="mail.example.test"
keychain: "/Users/someone/Library/Keychains/login.keychain-db"
version: 512
class: "genp"
attributes:
    "acct"<blob>="someone"
    "svce"<blob>="Chrome Safe Storage"
keychain: "/Users/someone/Library/Keychains/login.keychain-db"
version: 512
class: "inet"
attributes:
    "acct"<blob>=0x6D65  "me"
    "srvr"<blob>="nas.example.test"
keychain: "/Users/someone/Library/Keychains/login.keychain-db"
version: 512
class: "inet"
attributes:
    "acct"<blob>="nobody"
    "srvr"<blob>=<NULL>
'''


def test_a_dump_gives_internet_passwords_only_as_server_and_account():
    assert mk.parse_dump(DUMP) == [{"server": "mail.example.test", "account": "me@example.test"},
                                   {"server": "nas.example.test", "account": "me"}]


@pytest.mark.parametrize("stderr,code,expected", [
    ("security: SecKeychainSearchCopyNext: User interaction is not allowed.", 36, "no_gui"),
    ("security: SecKeychainItemCopyContent: User canceled the operation.", 128, "denied"),
    ("The user name or passphrase you entered is not correct.", 51, "denied"),
    ("security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.", 44, "not_found"),
    ("something else", 1, "failed"),
])
def test_each_security_failure_is_named(stderr, code, expected):
    assert mk.classify(stderr, code) == expected


def test_a_read_says_which_failure_it_was_and_returns_only_the_value(monkeypatch):
    replies = iter([subprocess.CompletedProcess([], 0, "s3cret-value\n", ""),
                    subprocess.CompletedProcess([], 36, "", "User interaction is not allowed.")])
    monkeypatch.setattr(mk, "run", lambda args, timeout: next(replies))
    assert mk.internet_password("mail.example.test", "me") == "s3cret-value"
    with pytest.raises(mk.KeychainError) as caught:
        mk.internet_password("mail.example.test", "me")
    assert caught.value.code == "no_gui" and "s3cret" not in str(caught.value)


def test_an_unanswered_prompt_is_a_timeout_not_a_crash(monkeypatch):
    def run(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)
    monkeypatch.setattr(mk, "run", run)
    with pytest.raises(mk.KeychainError) as caught:
        mk.read_secret(["security", "find-generic-password", "-ws", "Chrome Safe Storage"], "Chrome Safe Storage")
    assert caught.value.code == "timeout"
