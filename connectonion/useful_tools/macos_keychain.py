"""Read the owner's own login-keychain passwords on this Mac with the system `security` tool, read-only (#3305).

Listing (`security dump-keychain`, attributes only) asks nothing and returns no value. Reading a value
(`security find-…-password -w`) makes macOS show its "允许 / Allow" prompt, once per item, and only a process
inside the owner's GUI login session can show it: a process an agent or ssh started cannot, and `security`
then fails at once with "User interaction is not allowed". Failures come back as a KeychainError whose `code`
says which case it was, so the reader can tell the owner what to do instead of a generic error.
Nothing is written; values are returned to the caller, never logged.
"""
from __future__ import annotations

import re
import subprocess
import sys

# How long a value read waits for the owner to answer the system prompt.
PROMPT_WAIT = 120
UNAVAILABLE = "macOS Keychain is only available on a Mac"

MESSAGES = {
    "no_gui": "macOS cannot show the Keychain prompt to this process (it is outside your login session)",
    "denied": "the Keychain prompt for {what} was declined",
    "not_found": "{what} is not in the Keychain",
    "timeout": "no answer to the Keychain prompt for {what} within {minutes} minutes",
    "failed": "the Keychain could not read {what}",
}


class KeychainError(Exception):
    """A readable Keychain failure; `code` is one of MESSAGES' keys."""

    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


def run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """The one place this module starts a process, so tests can stand in for `security`."""
    if sys.platform != "darwin":
        raise KeychainError(UNAVAILABLE)
    try:
        return subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except (FileNotFoundError, OSError) as error:
        raise KeychainError(UNAVAILABLE) from error


def classify(stderr: str, returncode: int) -> str:
    """Which failure `security` reported, from its message (its exit codes are not stable across versions)."""
    text = stderr.lower()
    if "interaction is not allowed" in text:
        return "no_gui"
    if "cancel" in text or "not correct" in text:
        return "denied"
    if returncode == 44 or "could not be found" in text:
        return "not_found"
    return "failed"


def read_secret(args: list[str], what: str) -> str:
    """One value through `security … -w`, which raises the system prompt; KeychainError with a code otherwise."""
    try:
        done = run(args, PROMPT_WAIT)
    except subprocess.TimeoutExpired:
        raise KeychainError(MESSAGES["timeout"].format(what=what, minutes=PROMPT_WAIT // 60), "timeout")
    except (FileNotFoundError, OSError) as error:
        raise KeychainError(UNAVAILABLE) from error
    if done.returncode != 0:
        code = classify(done.stderr, done.returncode)
        raise KeychainError(MESSAGES[code].format(what=what), code)
    return done.stdout.rstrip("\n")


ATTRIBUTE = re.compile(r'^\s+"(acct|srvr)"<blob>=(?:0x[0-9A-Fa-f]+\s+)?"(.*)"\s*$')


def parse_dump(text: str) -> list[dict]:
    """`security dump-keychain` output to its internet passwords as {server, account}; attributes only."""
    items: list[dict] = []
    for line in text.splitlines():
        if line.startswith("keychain:"):
            items.append({})
        elif items and line.startswith("class:"):
            items[-1]["class"] = line.split(":", 1)[1].strip().strip('"')
        elif items and (match := ATTRIBUTE.match(line)):
            items[-1][match[1]] = match[2]
    return [{"server": item["srvr"], "account": item.get("acct", "")}
            for item in items if item.get("class") == "inet" and item.get("srvr")]


def internet_passwords() -> list[dict]:
    """Every internet password in the login keychain as {server, account}. Nothing prompts: no value is read."""
    try:
        done = run(["security", "dump-keychain"], 60)
    except subprocess.TimeoutExpired:
        raise KeychainError(MESSAGES["timeout"].format(what="the login keychain", minutes=1), "timeout")
    except (FileNotFoundError, OSError) as error:
        raise KeychainError(UNAVAILABLE) from error
    if done.returncode != 0:
        raise KeychainError(MESSAGES["failed"].format(what="the login keychain"), "failed")
    return parse_dump(done.stdout)


def internet_password(server: str, account: str) -> str:
    """One internet password's value; macOS asks the owner first."""
    return read_secret(["security", "find-internet-password", "-s", server, "-a", account, "-w"], server)
