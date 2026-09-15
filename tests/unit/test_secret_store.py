"""A secret is encrypted under a key derived from agent.key, and never stored.

The reference implementation, `lark-cli`, keeps an AES master key in the OS
keychain because it has nothing else to start from. We have an agent key and a
SLIP-0013 tree, so the encryption key is derived at a path — which is what makes
these properties testable at all:

  * nothing new is written outside the ciphertext file
  * recovery.txt is never opened, because it is an optional backup
  * the twelve words still reach the secret, via the agent key they derive
  * rotation is `index + 1`, and the old ciphertext stops opening
  * a wrong agent key fails loudly rather than returning wrong bytes

The last one matters most. A store that can return a plausible wrong plaintext
is worse than no store.
"""

import json

import pytest

from connectonion import address, secret_store
from connectonion.derive import slip13_path

PHRASE = (
    "legal winner thank year wave sausage worth useful legal winner thank yellow"
)
OTHER_PHRASE = (
    "letter advice cage absurd amount doctor acoustic avoid letter advice cage above"
)


def _plant(root, phrase, *, with_recovery=True):
    """A .co directory holding the agent key those words derive."""
    keys = root / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / "agent.key").write_bytes(bytes(address.recover(phrase)["signing_key"]))
    if with_recovery:
        (keys / "recovery.txt").write_text(phrase, encoding="utf-8")
    return root


@pytest.fixture
def co_dir(tmp_path):
    return _plant(tmp_path, PHRASE)


def test_a_value_survives_a_round_trip(co_dir):
    secret_store.put(co_dir, "LARK_APP_SECRET", "s3cr3t-value")

    assert secret_store.get(co_dir, "LARK_APP_SECRET") == "s3cr3t-value"


def test_the_plaintext_is_not_in_the_file(co_dir):
    """The exposure this exists to remove: a value sitting in a file people cat."""
    path = secret_store.put(co_dir, "LARK_APP_SECRET", "s3cr3t-value")

    body = path.read_text()
    assert "s3cr3t-value" not in body
    assert json.loads(body)["ct"], "the ciphertext is there, just not readable"


def test_no_key_is_written_anywhere(co_dir):
    """lark-cli must store a master key; deriving means there is none to store."""
    secret_store.put(co_dir, "LARK_APP_SECRET", "value")

    written = {p.name for p in (co_dir / "keys").rglob("*") if p.is_file()}
    assert written == {"agent.key", "recovery.txt", "lark_app_secret.enc"}


def test_the_recovery_phrase_file_is_never_needed(tmp_path):
    """The phrase file is a backup people are told to write down and delete.

    Deriving from it would mean that doing the right thing with your backup
    silently made every stored secret unopenable.
    """
    co_dir = _plant(tmp_path, PHRASE, with_recovery=False)

    secret_store.put(co_dir, "LARK_APP_SECRET", "value")

    assert not (co_dir / "keys" / "recovery.txt").exists()
    assert secret_store.get(co_dir, "LARK_APP_SECRET") == "value"


def test_the_twelve_words_still_reach_the_secret(tmp_path, co_dir):
    """Recovery survives the move: the words derive the key that derives the key.

    Portability is the property a keychain-held master key cannot have, and it
    is not given up by rooting the subtree one level lower.
    """
    secret_store.put(co_dir, "LARK_APP_SECRET", "value")

    # A new machine: nothing but the twelve words and the ciphertext.
    elsewhere = _plant(tmp_path / "another-machine", PHRASE, with_recovery=False)
    target = elsewhere / "keys" / "secrets"
    target.mkdir()
    (target / "lark_app_secret.enc").write_text(
        (co_dir / "keys" / "secrets" / "lark_app_secret.enc").read_text()
    )

    assert secret_store.get(elsewhere, "LARK_APP_SECRET") == "value"


def test_a_different_agent_fails_loudly(tmp_path, co_dir):
    """Never a wrong plaintext. A store that can guess is worse than none."""
    secret_store.put(co_dir, "LARK_APP_SECRET", "value")
    (co_dir / "keys" / "agent.key").write_bytes(
        bytes(address.recover(OTHER_PHRASE)["signing_key"])
    )

    with pytest.raises(secret_store.Undecryptable) as raised:
        secret_store.get(co_dir, "LARK_APP_SECRET")

    assert "agent key" in str(raised.value)


def test_rotation_moves_the_index_and_keeps_the_value(co_dir):
    secret_store.put(co_dir, "LARK_APP_SECRET", "value")

    nxt = secret_store.rotate(co_dir, "LARK_APP_SECRET")

    assert nxt == 1
    assert secret_store.get(co_dir, "LARK_APP_SECRET") == "value"
    record = json.loads((co_dir / "keys" / "secrets" / "lark_app_secret.enc").read_text())
    assert record["index"] == 1


def test_the_old_ciphertext_no_longer_opens_after_rotation(co_dir):
    """What rotation has to mean, or it is only bookkeeping."""
    path = secret_store.put(co_dir, "LARK_APP_SECRET", "value")
    before = path.read_text()
    secret_store.rotate(co_dir, "LARK_APP_SECRET")

    # Put the pre-rotation bytes back, claiming the new index.
    stale = json.loads(before)
    stale["index"] = 1
    path.write_text(json.dumps(stale))

    with pytest.raises(secret_store.Undecryptable):
        secret_store.get(co_dir, "LARK_APP_SECRET")


def test_rotation_derives_a_different_key(co_dir):
    """The mechanism, asserted directly rather than inferred from behaviour."""
    assert slip13_path(secret_store.secret_uri("x"), 0) != slip13_path(
        secret_store.secret_uri("x"), 1
    )


def test_a_secret_key_is_not_the_agent_key(co_dir):
    """secret:// must be its own namespace, and one hardened level below.

    Sharing the identity path would make one leaked file-encryption key and the
    agent's signing key the same secret.
    """
    agent_key = secret_store.read_agent_key(co_dir)

    derived = secret_store._key_for(agent_key, "agentname", 0)

    assert derived != agent_key


def test_no_agent_key_says_so_and_names_the_command(tmp_path):
    (tmp_path / "keys").mkdir(parents=True)

    with pytest.raises(secret_store.MissingAgentKey) as raised:
        secret_store.get(tmp_path, "LARK_APP_SECRET")

    message = str(raised.value)
    assert "agent key" in message
    assert "co init" in message


def test_a_missing_secret_is_not_a_key_problem(co_dir):
    """Two different failures must read differently."""
    with pytest.raises(secret_store.Undecryptable) as raised:
        secret_store.get(co_dir, "NEVER_STORED")

    assert "no stored secret" in str(raised.value)


def test_an_edited_file_is_refused(co_dir):
    path = secret_store.put(co_dir, "LARK_APP_SECRET", "value")
    path.write_text("not json at all")

    with pytest.raises(secret_store.Undecryptable):
        secret_store.get(co_dir, "LARK_APP_SECRET")


def test_listing_names_does_not_decrypt(co_dir):
    secret_store.put(co_dir, "LARK_APP_SECRET", "a")
    secret_store.put(co_dir, "FEISHU_APP_ID", "b")

    # No agent key present: listing must still work, because `co env` shows
    # names and sources without revealing values.
    (co_dir / "keys" / "agent.key").unlink()

    assert secret_store.stored_names(co_dir) == ["feishu_app_id", "lark_app_secret"]


def test_dropping_reports_whether_there_was_one(co_dir):
    secret_store.put(co_dir, "LARK_APP_SECRET", "value")

    assert secret_store.drop(co_dir, "LARK_APP_SECRET") is True
    assert secret_store.drop(co_dir, "LARK_APP_SECRET") is False


def test_the_name_is_canonicalised_once(co_dir):
    secret_store.put(co_dir, "Lark_App_Secret", "value")

    assert secret_store.get(co_dir, "  lark_app_secret  ") == "value"


def test_an_empty_name_is_refused():
    with pytest.raises(ValueError):
        secret_store.secret_uri("   ")


def test_a_truncated_agent_key_is_refused(tmp_path):
    """Half a key derives a key. Silence there would be a wrong answer."""
    keys = tmp_path / "keys"
    keys.mkdir(parents=True)
    (keys / "agent.key").write_bytes(b"\x01" * 16)

    with pytest.raises(secret_store.MissingAgentKey) as raised:
        secret_store.read_agent_key(tmp_path)

    assert "16 bytes" in str(raised.value)
