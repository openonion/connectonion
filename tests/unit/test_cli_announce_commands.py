"""Tests for co announce command helpers."""

import json

import pytest

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


def test_build_published_skills_only_includes_publish_true_with_body(isolated_announce_home):
    profile = announce._load_profile()

    skills = announce._build_published_skills(profile)

    assert skills == [
        {"name": "public", "description": "Public skill", "body": "Public body"},
    ]
