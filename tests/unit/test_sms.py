"""Agent-side decryption and mailbox behavior for OpenOnion Messages."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from nacl.signing import SigningKey

from connectonion.useful_tools import sms


FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sms_protocol_v1.json").read_text()
)


def identity():
    return {"address": FIXTURE["address"], "signing_key": SigningKey(bytes.fromhex(FIXTURE["seed_hex"]))}


def envelope(**overrides):
    value = {
        "id": "57de9ae4-cd67-447b-a6e4-f4c59dc4183a",
        "device_id": "6be98ef6-f30d-4260-a88c-ec74f2930976",
        "message_id": "969c3fc2-6557-4cda-9ab8-cb764f4f17ae",
        "version": 1,
        "algorithm": sms.ALGORITHM,
        "ciphertext": FIXTURE["ciphertext_base64"],
        "stored_at": "2026-09-01T02:00:01Z",
        "acknowledged_at": None,
    }
    value.update(overrides)
    return value


def response(payload, status=200):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    result.status_code = status
    return result


def test_protocol_vector_decrypts_with_the_agent_identity():
    plaintext = sms._decrypt_envelope(envelope(), identity())
    assert json.dumps(plaintext, separators=(",", ":")) == FIXTURE["plaintext_utf8"]
    assert plaintext["body"] == "Your code is 123456"


def test_tampering_fails_closed():
    encoded = FIXTURE["ciphertext_base64"]
    tampered = encoded[:-4] + "AAAA"
    with pytest.raises(ValueError, match="could not be decrypted"):
        sms._decrypt_envelope(envelope(ciphertext=tampered), identity())


def test_get_sms_returns_untrusted_plaintext_and_acknowledges_after_decrypt(monkeypatch):
    get = Mock(return_value=response({"messages": [envelope()]}))
    acknowledge = Mock(return_value=True)
    monkeypatch.setattr(sms.requests, "get", get)
    monkeypatch.setattr(sms, "acknowledge_sms", acknowledge)
    monkeypatch.setattr(sms, "_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(sms, "_identity", identity)

    messages = sms.get_sms(last=1, unacknowledged=True, acknowledge=True)

    assert messages[0]["sender"] == "+61412345678"
    assert messages[0]["trusted"] is False
    acknowledge.assert_called_once_with(envelope()["id"])
    assert get.call_args.kwargs["params"]["unacknowledged"] == "true"


def test_decryption_failure_is_never_acknowledged(monkeypatch):
    monkeypatch.setattr(
        sms.requests,
        "get",
        Mock(return_value=response({"messages": [envelope(ciphertext="A" * 64)]})),
    )
    acknowledge = Mock(return_value=True)
    monkeypatch.setattr(sms, "acknowledge_sms", acknowledge)
    monkeypatch.setattr(sms, "_headers", lambda: {})
    monkeypatch.setattr(sms, "_identity", identity)

    with pytest.raises(ValueError):
        sms.get_sms(acknowledge=True)
    acknowledge.assert_not_called()


def test_pairing_link_has_a_bounded_lifetime(monkeypatch):
    post = Mock(return_value=response({"pairing_link": "openonion://sms/pair?secret"}))
    monkeypatch.setattr(sms.requests, "post", post)
    monkeypatch.setattr(sms, "_headers", lambda: {})
    assert sms.create_sms_pairing(600)["pairing_link"].startswith("openonion://")
    with pytest.raises(ValueError):
        sms.create_sms_pairing(59)


def test_public_package_exports_sms_tools():
    import connectonion

    assert connectonion.get_sms is sms.get_sms
    assert connectonion.wait_for_sms is sms.wait_for_sms
    assert connectonion.create_sms_pairing is sms.create_sms_pairing
    assert connectonion.delete_sms is sms.delete_sms


def test_delete_sms_is_scoped_through_the_authenticated_api(monkeypatch):
    delete = Mock(return_value=response({"deleted": envelope()["id"]}))
    monkeypatch.setattr(sms.requests, "delete", delete)
    monkeypatch.setattr(sms, "_headers", lambda: {"Authorization": "Bearer test"})

    assert sms.delete_sms(envelope()["id"]) is True
    assert delete.call_args.args[0].endswith(f"/api/v1/sms/messages/{envelope()['id']}")


def test_path_identifiers_fail_closed_before_a_request(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(sms.requests, "delete", delete)

    with pytest.raises(ValueError, match="UUID"):
        sms.delete_sms("../devices/current")
    with pytest.raises(ValueError, match="UUID"):
        sms.revoke_sms_device("not-a-device")
    delete.assert_not_called()
