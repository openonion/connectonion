"""Agent-side decryption and mailbox behavior for OpenOnion Messages."""

import json
import base64
from pathlib import Path
from unittest.mock import Mock
import uuid

import pytest
from nacl.signing import SigningKey

from connectonion.useful_tools import sms


FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sms_protocol_v1.json").read_text()
)
PAIRING_VECTOR = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sms_pairing_v2.json").read_text()
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
    pairing_id = uuid.UUID("11111111-2222-4333-8444-555555555555")
    nonce = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    expires_at = 1_788_250_600
    link = (
        f"openonion://sms/pair?v=2&id={pairing_id}&recipient={FIXTURE['address']}"
        f"&nonce={nonce}&expires={expires_at}&signature={'00' * 64}"
    )
    post = Mock(
        return_value=response(
            {
                "id": str(pairing_id),
                "recipient": FIXTURE["address"],
                "pairing_link": link,
                "expires_at": "2026-09-01T00:00:00Z",
                "version": 2,
            }
        )
    )
    monkeypatch.setattr(sms.requests, "post", post)
    monkeypatch.setattr(sms, "_headers", lambda: {})
    monkeypatch.setattr(sms, "_identity", identity)
    monkeypatch.setattr(sms.uuid, "uuid4", lambda: pairing_id)
    monkeypatch.setattr(sms.secrets, "token_bytes", lambda size: bytes(range(size)))
    monkeypatch.setattr(sms.time, "time", lambda: expires_at - 600)

    assert sms.create_sms_pairing(600)["pairing_link"].startswith("openonion://")
    body = post.call_args.kwargs["json"]
    grant = sms._canonical_pairing_grant(
        pairing_id, FIXTURE["address"], nonce, expires_at
    )
    identity()["signing_key"].verify_key.verify(
        grant.encode(), bytes.fromhex(body["signature"])
    )
    assert body["nonce"] == nonce
    with pytest.raises(ValueError):
        sms.create_sms_pairing(59)


def test_confirmation_code_binds_the_link_to_the_device_key():
    pairing_id = "11111111-2222-4333-8444-555555555555"
    nonce = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    link = (
        f"openonion://sms/pair?v=2&id={pairing_id}&recipient={FIXTURE['address']}"
        f"&nonce={nonce}&expires=1788250600&signature={'11' * 64}"
    )
    first_key = base64.b64encode(b"device-key-one").decode()
    second_key = base64.b64encode(b"device-key-two").decode()

    first = sms.pairing_confirmation_code(link, first_key)

    assert len(first) == 6 and first.isdigit()
    assert first != sms.pairing_confirmation_code(link, second_key)


def test_v2_pairing_shared_vector_is_byte_for_byte_compatible():
    link = (
        "openonion://sms/pair"
        f"?v={PAIRING_VECTOR['version']}"
        f"&id={PAIRING_VECTOR['pairing_id']}"
        f"&recipient={PAIRING_VECTOR['recipient']}"
        f"&nonce={PAIRING_VECTOR['nonce']}"
        f"&expires={PAIRING_VECTOR['expires_at']}"
        f"&signature={PAIRING_VECTOR['agent_signature_hex']}"
    )
    grant = sms._canonical_pairing_grant(
        uuid.UUID(PAIRING_VECTOR["pairing_id"]),
        PAIRING_VECTOR["recipient"],
        PAIRING_VECTOR["nonce"],
        PAIRING_VECTOR["expires_at"],
    )

    assert grant == PAIRING_VECTOR["grant_utf8"]
    SigningKey(bytes(range(32))).verify_key.verify(
        grant.encode(), bytes.fromhex(PAIRING_VECTOR["agent_signature_hex"])
    )
    assert sms.pairing_confirmation_code(
        link, PAIRING_VECTOR["device_public_key_base64"]
    ) == PAIRING_VECTOR["confirmation_code"]


def test_public_package_exports_sms_tools():
    import connectonion

    assert connectonion.get_sms is sms.get_sms
    assert connectonion.wait_for_sms is sms.wait_for_sms
    assert connectonion.create_sms_pairing is sms.create_sms_pairing
    assert connectonion.confirm_sms_pairing is sms.confirm_sms_pairing
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
