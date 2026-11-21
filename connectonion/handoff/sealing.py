"""What a handoff puts on the backend is ciphertext.

Before the recipient's agent is known, a handoff is locked on the sender's machine with a random
key (AES-256-GCM). The key never reaches the backend: it travels only with the person, in the
link's #k= part (a browser never sends that part to a server), in the code, and in the note the
sender mails. The page decrypts in the browser; `co handoff accept` decrypts on the recipient's
machine.

Once both agents know each other's address, which is an Ed25519 public key, what they send each
other is boxed to the other's key (X25519 crypto_box): end-to-end, and the box also proves who
sent it (Aaron, 2026-10-17: "握手建立好之后就可以端到端加密了").
"""

import base64
import gzip
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from nacl.public import Box
from nacl.signing import VerifyKey

KEY_BYTES = 32
NONCE_BYTES = 12


def new_key() -> bytes:
    return os.urandom(KEY_BYTES)


def key_text(key: bytes) -> str:
    """The key as it goes in a link: 43 URL-safe characters."""
    return base64.urlsafe_b64encode(key).decode().rstrip("=")


def key_from(text: str) -> bytes:
    key = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if len(key) != KEY_BYTES:
        raise ValueError("the key in this link is cut off; copy the whole link again")
    return key


def _json_bytes(value) -> bytes:
    """JSON for a seal. A non-UTF-8 diff rides along as lone surrogates (#2570); surrogatepass keeps
    those bytes in the ciphertext and is ordinary UTF-8 for every well-formed string, which is what
    the browser's page holds."""
    return json.dumps(value, ensure_ascii=False).encode("utf-8", errors="surrogatepass")


def _json_value(raw: bytes):
    return json.loads(raw.decode("utf-8", errors="surrogatepass"))


def lock(key: bytes, value, label: str) -> str:
    """`value` as gzipped JSON, sealed with AES-256-GCM. `label` (the drop and which part of it) is bound in,
    so one part cannot be passed off as another. The browser opens the same format (oo-frontend /h)."""
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, gzip.compress(_json_bytes(value)), label.encode())
    return base64.b64encode(nonce + sealed).decode()


def unlock(key: bytes, blob: str, label: str):
    """What `lock` sealed; cryptography's InvalidTag for a wrong key, a wrong label or a changed byte."""
    raw = base64.b64decode(blob)
    plain = gzip.decompress(AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], label.encode()))
    return _json_value(plain)


def _box(signing_key, address: str) -> Box:
    """Ours and theirs, as X25519: an agent's 0x address is its Ed25519 public key."""
    theirs = VerifyKey(bytes.fromhex(address[2:])).to_curve25519_public_key()
    return Box(signing_key.to_curve25519_private_key(), theirs)


def box(signing_key, to_address: str, value: dict) -> str:
    """`value` sealed so that only `to_address`'s agent can open it, and it knows we sent it."""
    return base64.b64encode(bytes(_box(signing_key, to_address).encrypt(json.dumps(value, ensure_ascii=False).encode()))).decode()


def unbox(signing_key, from_address: str, blob: str) -> dict:
    """What `from_address` boxed for us; nacl's CryptoError if anyone else made it or it was changed."""
    return json.loads(_box(signing_key, from_address).decrypt(base64.b64decode(blob)))
