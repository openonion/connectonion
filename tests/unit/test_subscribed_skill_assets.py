"""A published skill's signed companion files survive relay subscription."""

import base64
import json
from pathlib import Path

import pytest

from connectonion import address
from connectonion.cli.commands import announce_commands as announce
from connectonion.cli.commands import fanout, sub_commands as sub


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_publish_and_subscribe_companion_files(tmp_path, monkeypatch):
    skills_dir = tmp_path / "publisher" / "skills"
    source = skills_dir / "demo"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: demo\n---\nRun scripts/run.js\n")
    (source / "scripts" / "run.js").write_bytes(b"console.log('ok')")
    (source / ".env").write_text("never publish")
    monkeypatch.setattr(announce, "SKILLS_DIR", skills_dir)
    listed = announce._build_listed_skills({
        "skills": [{"name": "demo", "description": "Demo", "publish": True}],
    })
    assert listed[0]["files"] == {
        "scripts/run.js": base64.b64encode(b"console.log('ok')").decode(),
    }

    keys = address.generate()
    full = {"alias": "alice", "bio": "", "version": "v1",
            "attestation_version": "profile-v2", "revision": 1,
            "skills": listed}
    metadata = json.loads(json.dumps(full))
    metadata["skills"][0].pop("body")
    metadata["skills"][0].pop("files")
    signature = address.sign(
        keys, json.dumps(full, sort_keys=True, separators=(",", ":")).encode()
    ).hex()

    def get(url, timeout=None):
        if url.endswith("/profile"):
            return Response({"profile": metadata, "publisher": keys["address"],
                             "signature": signature, "signature_version": "profile-v2"})
        return Response(listed[0])

    monkeypatch.setattr(sub.httpx, "get", get)
    co_home = tmp_path / "subscriber" / ".co"
    monkeypatch.setattr(sub, "CO_HOME", co_home)
    monkeypatch.setattr(sub, "SUBS_DIR", co_home / "subs")
    monkeypatch.setattr(sub, "SUBS_LIST", co_home / "subscriptions.txt")
    monkeypatch.setattr(fanout, "HOME", tmp_path / "subscriber")
    sub.handle_sub_sync_one(keys["address"])

    mirrored = co_home / "subs" / "alice" / "skills" / "demo"
    assert (mirrored / "scripts" / "run.js").read_bytes() == b"console.log('ok')"
    assert not (mirrored / ".env").exists()


def test_relay_modified_companion_file_is_refused_before_write(tmp_path, monkeypatch):
    keys = address.generate()
    body = "# Demo"
    files = {"scripts/run.js": "YQ=="}
    full = {"alias": "alice", "attestation_version": "profile-v2",
            "revision": 1, "skills": [{"name": "demo", "description": "Demo",
                                        "body": body, "files": files}]}
    metadata = {**full, "skills": [{"name": "demo", "description": "Demo"}]}
    signature = address.sign(
        keys, json.dumps(full, sort_keys=True, separators=(",", ":")).encode()
    ).hex()

    def get(url, timeout=None):
        if url.endswith("/profile"):
            return Response({"profile": metadata, "publisher": keys["address"],
                             "signature": signature, "signature_version": "profile-v2"})
        return Response({"body": body, "files": {"scripts/run.js": "Yg=="}})

    monkeypatch.setattr(sub.httpx, "get", get)
    co_home = tmp_path / ".co"
    monkeypatch.setattr(sub, "CO_HOME", co_home)
    monkeypatch.setattr(sub, "SUBS_DIR", co_home / "subs")
    monkeypatch.setattr(sub, "SUBS_LIST", co_home / "subscriptions.txt")
    with pytest.raises(ValueError, match="signature"):
        sub.handle_sub_sync_one(keys["address"])
    assert not (co_home / "subs").exists()
