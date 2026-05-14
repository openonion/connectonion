"""Unit tests for connectonion.cli.commands.sub_commands."""

import json
from pathlib import Path

import httpx
import pytest

from connectonion.cli.commands import fanout, sub_commands as sub


ADDR = "0x" + "a" * 64
ALIAS = "alice"
PROFILE_BODY = {
    "alias": ALIAS,
    "bio": "Test publisher",
    "version": "v0.2.0",
    "skills": [
        {"name": "alpha", "description": "Alpha skill"},
        {"name": "beta", "description": "Beta skill"},
    ],
}
ALPHA_BODY = "---\nname: alpha\ndescription: Alpha skill\n---\nAlpha content\n"
BETA_BODY = "---\nname: beta\ndescription: Beta skill\n---\nBeta content\n"


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect every filesystem destination to tmp_path."""
    co_home = tmp_path / ".co"
    co_home.mkdir()
    monkeypatch.setattr(sub, "CO_HOME", co_home)
    monkeypatch.setattr(sub, "SUBS_DIR", co_home / "subs")
    monkeypatch.setattr(sub, "SUBS_LIST", co_home / "subscriptions.txt")
    monkeypatch.setattr(fanout, "HOME", tmp_path)
    return tmp_path


@pytest.fixture
def fake_relay(monkeypatch):
    """Stub httpx.get with canned profile + skill body responses."""

    def _fake_get(url, timeout=None):
        if url.endswith(f"/agents/{ADDR}/profile"):
            return _Response(json={"profile": PROFILE_BODY})
        if url.endswith(f"/agents/{ADDR}/skills/alpha"):
            return _Response(json={"name": "alpha", "body": ALPHA_BODY})
        if url.endswith(f"/agents/{ADDR}/skills/beta"):
            # Return as raw text (no JSON content-type) to exercise that branch
            return _Response(text=BETA_BODY, content_type="text/markdown")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(sub.httpx, "get", _fake_get)


class _Response:
    def __init__(self, *, json=None, text=None, content_type="application/json"):
        self._json = json
        self._text = text if text is not None else ""
        self.headers = {"content-type": content_type}
        self.status_code = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._json

    @property
    def text(self):
        return self._text


def test_add_writes_subscriptions_file_and_mirrors_bundle(isolated_home, fake_relay):
    sub.handle_sub_add(ADDR)

    subs_file = isolated_home / ".co" / "subscriptions.txt"
    assert subs_file.exists()
    content = subs_file.read_text(encoding="utf-8")
    assert f"{ADDR} {ALIAS}" in content
    assert content.startswith("# ~/.co/subscriptions.txt")

    bundle = isolated_home / ".co" / "subs" / ALIAS
    assert (bundle / "agent.json").exists()
    assert json.loads((bundle / "agent.json").read_text())["alias"] == ALIAS
    assert (bundle / "skills" / "alpha" / "SKILL.md").read_text() == ALPHA_BODY
    assert (bundle / "skills" / "beta" / "SKILL.md").read_text() == BETA_BODY


def test_add_extracts_body_from_json_wrapper(isolated_home, fake_relay):
    """Relay wraps skill bodies in {'body': '...'} — we unwrap, not write JSON."""
    sub.handle_sub_add(ADDR)
    alpha = isolated_home / ".co" / "subs" / ALIAS / "skills" / "alpha" / "SKILL.md"
    assert alpha.read_text().startswith("---\nname: alpha")
    assert "body" not in alpha.read_text()  # not the JSON wrapper


def test_add_fans_out_to_detected_tools(isolated_home, fake_relay):
    (isolated_home / ".claude").mkdir()
    (isolated_home / ".codex").mkdir()

    sub.handle_sub_add(ADDR)

    assert (isolated_home / ".claude" / "plugins" / ALIAS).is_symlink()
    assert (isolated_home / ".codex" / "skills" / f"{ALIAS}-alpha").is_symlink()
    assert (isolated_home / ".codex" / "skills" / f"{ALIAS}-beta").is_symlink()


def test_add_is_idempotent_no_duplicate_lines(isolated_home, fake_relay):
    sub.handle_sub_add(ADDR)
    sub.handle_sub_add(ADDR)
    lines = [l for l in (isolated_home / ".co" / "subscriptions.txt").read_text().splitlines()
             if l and not l.startswith("#")]
    assert lines == [f"{ADDR} {ALIAS}"]


def test_list_with_no_subscriptions_does_not_crash(isolated_home, capsys):
    sub.handle_sub_list()
    out = capsys.readouterr().out
    assert "No subscriptions" in out


def test_list_after_add_shows_alias_version_and_skill_count(isolated_home, fake_relay, capsys):
    sub.handle_sub_add(ADDR)
    capsys.readouterr()  # drain

    sub.handle_sub_list()
    out = capsys.readouterr().out
    assert ALIAS in out
    assert "v0.2.0" in out
    assert "2" in out  # skill count


def test_remove_by_address_clears_record_and_bundle(isolated_home, fake_relay):
    (isolated_home / ".claude").mkdir()
    sub.handle_sub_add(ADDR)
    bundle = isolated_home / ".co" / "subs" / ALIAS
    assert bundle.exists()

    sub.handle_sub_remove(ADDR)

    assert not bundle.exists()
    assert not (isolated_home / ".claude" / "plugins" / ALIAS).exists()
    remaining = [l for l in (isolated_home / ".co" / "subscriptions.txt").read_text().splitlines()
                 if l and not l.startswith("#")]
    assert remaining == []


def test_remove_by_alias_works_too(isolated_home, fake_relay):
    sub.handle_sub_add(ADDR)
    sub.handle_sub_remove(ALIAS)
    bundle = isolated_home / ".co" / "subs" / ALIAS
    assert not bundle.exists()


def test_remove_unknown_target_is_a_no_op(isolated_home, capsys):
    sub.handle_sub_remove("0x" + "1" * 64)
    out = capsys.readouterr().out
    assert "Not subscribed" in out


def test_bare_alias_without_prior_subscription_errors_out(isolated_home, capsys):
    """Aliases are dangerous — we never resolve them remotely. Only locally-pinned
    aliases (already in subscriptions.txt) are accepted as a refresh shortcut."""
    with pytest.raises(SystemExit):
        sub.handle_sub_add("alice")  # not in subscriptions.txt
    out = capsys.readouterr().out
    assert "not a 0x address" in out


def test_alias_refresh_works_when_address_already_pinned(isolated_home, fake_relay):
    """If alias is already in subscriptions.txt, we can refresh by alias."""
    sub.handle_sub_add(ADDR)
    # Now alice is pinned to ADDR — using the alias should refresh, not error
    sub.handle_sub_add(ALIAS)
    lines = [l for l in (isolated_home / ".co" / "subscriptions.txt").read_text().splitlines()
             if l and not l.startswith("#")]
    assert lines == [f"{ADDR} {ALIAS}"]
