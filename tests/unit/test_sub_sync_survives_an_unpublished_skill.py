"""`co sub sync` prints a traceback on a real published agent.

Measured against a live relay agent, `0xcf1619cb…` (naturewill-mapping):

    $ co sub sync 0xcf1619cb4cd96c6d5bcb8f8a0cac4e7e0091c511fbce329e3acb6b8d4fb0c8c6
    Fetching profile 0xcf1619cb…
    ╭─ Traceback ─╮
    │ sub_commands.py:91 in _fetch_skill                │
    │ ❱ 91 return r.json()["body"]                       │
    KeyError: 'body'

The profile advertises the skill and the relay will not hand over its contents:

    GET /api/agents/0xcf1619…/profile
      skills: [{"name": "candidate-mapping", "description": "No description"}]

    GET /api/agents/0xcf1619…/skills/candidate-mapping
      HTTP 200  {"error": "skill body not published"}

**200 with an error inside**, so `raise_for_status()` passes and the next line
indexes a key that is not there. Any agent that announces a skill without
publishing its body — which `co announce` allows, `publish: false` being the
default — breaks `co sub sync` for whoever subscribes to it. Nothing the
subscriber did is wrong and nothing tells them what happened.

A skill whose body is withheld is normal and expected. It should be named and
skipped, and the other skills in the bundle should still sync.
"""

import json

import pytest

from connectonion import address


KEYS = address.generate()
ADDR = KEYS["address"]
SHARED_BODY = "---\nname: shared\ndescription: A real one\n---\n\n# Body\n"


def _envelope():
    full = {
        "alias": "mapper",
        "skills": [
            {"name": "withheld", "description": "No description"},
            {"name": "shared", "description": "A real one", "body": SHARED_BODY},
        ],
    }
    metadata = json.loads(json.dumps(full))
    metadata["skills"][1].pop("body")
    canonical = json.dumps(full, sort_keys=True, separators=(",", ":"))
    return {
        "profile": metadata,
        "publisher": ADDR,
        "signature": address.sign(KEYS, canonical.encode()).hex(),
        "signature_version": "profile-v1",
    }


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def relay(monkeypatch):
    """Answer profile and skill requests the way the live relay does."""
    from connectonion.cli.commands import sub_commands

    published = {
        "shared": {"body": SHARED_BODY},
        "withheld": {"error": "skill body not published"},
    }

    def fake_get(url, **kwargs):
        if url.endswith("/profile"):
            return _Response(_envelope())
        name = url.rsplit("/", 1)[-1]
        return _Response(published.get(name, {"error": "not found"}))

    monkeypatch.setattr(sub_commands.httpx, "get", fake_get)
    return sub_commands


class TestAWithheldBodyIsSkippedNotFatal:

    def test_fetching_it_returns_nothing_rather_than_raising(self, relay):
        assert relay._fetch_skill("0xabc", "withheld", "https://relay") is None

    def test_a_published_body_still_comes_back(self, relay):
        body = relay._fetch_skill("0xabc", "shared", "https://relay")

        assert body.startswith("---\nname: shared")

    def test_a_bundle_with_one_withheld_skill_still_syncs_the_others(
        self, relay, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(relay, "SUBS_DIR", tmp_path / "subs")

        envelope = relay._fetch_profile(ADDR, "https://relay")
        profile, bodies = relay._verified_bundle(ADDR, envelope, "https://relay")
        count = relay._mirror_bundle("mapper", profile, bodies)

        assert count == 1, "the readable skill did not survive its neighbour"

    def test_the_withheld_one_is_not_written_as_an_error_document(
        self, relay, tmp_path, monkeypatch
    ):
        """Writing {"error": ...} into a SKILL.md would be worse than skipping."""
        monkeypatch.setattr(relay, "SUBS_DIR", tmp_path / "subs")

        envelope = relay._fetch_profile(ADDR, "https://relay")
        profile, bodies = relay._verified_bundle(ADDR, envelope, "https://relay")
        relay._mirror_bundle("mapper", profile, bodies)

        written = list((tmp_path / "subs").rglob("SKILL.md"))
        for path in written:
            assert "not published" not in path.read_text(encoding="utf-8")


class TestTheOperatorIsTold:

    def test_the_skipped_skill_is_named(self, relay, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(relay, "SUBS_DIR", tmp_path / "subs")

        envelope = relay._fetch_profile(ADDR, "https://relay")
        profile, bodies = relay._verified_bundle(ADDR, envelope, "https://relay")
        relay._mirror_bundle("mapper", profile, bodies)

        assert "withheld" in capsys.readouterr().out


class TestARealFailureStillFails:
    """Skipping a withheld body must not swallow a broken relay."""

    def test_a_500_still_raises(self, monkeypatch):
        from connectonion.cli.commands import sub_commands

        monkeypatch.setattr(
            sub_commands.httpx, "get",
            lambda url, **kw: _Response({"error": "boom"}, status=500),
        )

        with pytest.raises(Exception):
            sub_commands._fetch_skill("0xabc", "any", "https://relay")
