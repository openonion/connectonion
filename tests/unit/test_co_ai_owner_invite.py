"""A fresh ``co ai`` owner always has one private way back in."""

import os
import re

from connectonion.cli.co_ai.main import _ensure_owner_invite
from connectonion.network.trust.fast_rules import evaluate_request


def test_a_fresh_install_mints_one_private_invite(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    (co_dir / "keys.env").write_text("AGENT_ADDRESS=0xowner\n", encoding="utf-8")
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)

    created = _ensure_owner_invite(co_dir)

    code = os.environ["CO_INVITE_CODE"]
    assert created is True
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{5}(?:-[A-HJ-NP-Z2-9]{5}){2}", code)
    assert f"CO_INVITE_CODE={code}\n" in (co_dir / "keys.env").read_text()
    if os.name != "nt":
        assert (co_dir / "keys.env").stat().st_mode & 0o777 == 0o600


def test_restart_keeps_the_invite_people_already_hold(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    keys_env = co_dir / "keys.env"
    keys_env.write_text("CO_INVITE_CODE=KEPT2-KEPT3-KEPT4\n", encoding="utf-8")
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)

    created = _ensure_owner_invite(co_dir)

    assert created is False
    assert os.environ["CO_INVITE_CODE"] == "KEPT2-KEPT3-KEPT4"
    assert keys_env.read_text().count("CO_INVITE_CODE=") == 1


def test_an_explicit_project_invite_wins_without_copying_it_global(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    keys_env = co_dir / "keys.env"
    keys_env.write_text("AGENT_ADDRESS=0xowner\n", encoding="utf-8")
    monkeypatch.setenv("CO_INVITE_CODE", "LOCAL-OWNER-CODE2")

    created = _ensure_owner_invite(co_dir)

    assert created is False
    assert "CO_INVITE_CODE" not in keys_env.read_text()


def test_the_new_invite_opens_only_for_the_client_who_knows_it(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    (co_dir / "keys.env").touch()
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    _ensure_owner_invite(co_dir)
    policy = {
        "onboard": {"invite_code": ["$CO_INVITE_CODE"]},
        "default": "deny",
    }

    assert evaluate_request(policy, "0xowner-client", {"invite_code": os.environ["CO_INVITE_CODE"]}) == "allow"
    assert evaluate_request(policy, "0xunrelated", {"invite_code": "SOMEONE-ELSES-CODE2"}) == "deny"
