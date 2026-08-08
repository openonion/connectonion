"""Tests for co announce command helpers."""

import json

import pytest

from connectonion import address
from connectonion.cli.commands import announce_commands as announce


@pytest.fixture
def isolated_announce_home(tmp_path, monkeypatch):
    co_home = tmp_path / ".co"
    skills_dir = co_home / "skills"
    agent_json = co_home / "agent.json"

    monkeypatch.setattr(announce, "CO_HOME", co_home)
    monkeypatch.setattr(announce, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(announce, "AGENT_JSON", agent_json)

    skills_dir.mkdir(parents=True)
    agent_json.write_text(
        json.dumps(
            {
                "address": "0xabc",
                "alias": "tester",
                "bio": "Test agent",
                "version": "v0.1.0",
                "skills": [
                    {"name": "public", "description": "Public skill", "publish": True},
                    {"name": "private", "description": "Private skill", "publish": False},
                    {"name": "missing", "description": "Missing skill", "publish": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    public_dir = skills_dir / "public"
    private_dir = skills_dir / "private"
    public_dir.mkdir()
    private_dir.mkdir()
    (public_dir / "SKILL.md").write_text("Public body", encoding="utf-8")
    (private_dir / "SKILL.md").write_text("Private body", encoding="utf-8")

    return co_home


def test_announce_ws_url_accepts_base_and_endpoint_urls():
    assert announce._announce_ws_url("https://oo.openonion.ai") == "wss://oo.openonion.ai/ws/announce"
    assert announce._announce_ws_url("http://localhost:8000/") == "ws://localhost:8000/ws/announce"
    assert announce._announce_ws_url("wss://oo.openonion.ai/ws/announce") == "wss://oo.openonion.ai/ws/announce"


def test_build_listed_skills_lists_all_and_only_inlines_published_bodies(isolated_announce_home):
    profile = announce._load_profile()

    skills = announce._build_listed_skills(profile)

    assert skills == [
        {"name": "public", "description": "Public skill", "body": "Public body"},
        {"name": "private", "description": "Private skill"},
        {"name": "missing", "description": "Missing skill"},
    ]


def test_a_successful_publish_signs_and_persists_a_revision(
    isolated_announce_home, monkeypatch
):
    keys = address.generate()
    sent = []

    async def send(message, relay):
        sent.append(message)

    monkeypatch.setattr(announce.address, "load", lambda _home: keys)
    monkeypatch.setattr(announce, "_send", send)

    announce.handle_announce(relay="wss://relay.example")

    revision = sent[0]["profile"]["revision"]
    assert sent[0]["profile"]["attestation_version"] == "profile-v2"
    assert isinstance(revision, int) and revision > 0
    state = json.loads(announce._revision_path(keys["address"]).read_text())
    assert state == {"revision": revision}


def test_a_failed_publish_does_not_advance_the_revision(
    isolated_announce_home, monkeypatch
):
    keys = address.generate()

    async def fail(_message, _relay):
        raise RuntimeError("relay unavailable")

    monkeypatch.setattr(announce.address, "load", lambda _home: keys)
    monkeypatch.setattr(announce, "_send", fail)

    with pytest.raises(RuntimeError, match="relay unavailable"):
        announce.handle_announce(relay="wss://relay.example")

    assert not announce._revision_path(keys["address"]).exists()


def test_dry_run_does_not_consume_a_revision(
    isolated_announce_home, monkeypatch
):
    keys = address.generate()
    monkeypatch.setattr(announce.address, "load", lambda _home: keys)

    announce.handle_announce(relay="wss://relay.example", dry_run=True)

    assert not announce._revision_path(keys["address"]).exists()
