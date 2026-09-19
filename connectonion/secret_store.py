"""Secrets encrypted with a key derived from the agent's own key, never stored.

LLM-Note:
  Dependencies: imports from [base64, json, os, pathlib, sys, nacl.secret, nacl.utils] and derive.py | imported by [cli/commands/env_commands.py] | tested by [tests/unit/test_secret_store.py]
  Data flow: .co/keys/agent.key → SLIP-0010 root → slip13_path(secret_uri(name), index) → 32-byte key → XSalsa20-Poly1305 → .co/keys/secrets/<name>.enc holding {v, index, ct}
  State/Effects: reads .co/keys/agent.key; writes .co/keys/secrets/*.enc at 0600 in a directory at 0700 | never writes a key anywhere, and never opens recovery.txt
  Integration: exposes secret_uri(), put(), get(), drop(), rotate(), stored_names() | still recoverable from the twelve words, because agent.key is itself derived from them
  Performance: one HMAC-SHA512 per path level (microseconds) plus one AEAD operation
  Errors: MissingAgentKey when there is no agent.key, Undecryptable when that key or the index does not match the file — never returns a wrong plaintext

Why derived and not stored
--------------------------
The reference implementation for this kind of store is ``lark-cli``, which keeps
an AES-256 master key in the OS keychain and writes AES-GCM ciphertext beside it
(``internal/keychain/keychain_darwin.go``, MIT). It has to invent and store a
master key because it has no other secret to start from.

We already have one, and ``derive.py`` already turns a secret into a tree of
keys, so the key that encrypts a value can be *derived* at a path instead of kept
anywhere. That removes the parts of the keychain approach that hurt:

* No new keychain entry, so nothing to be blocked by a sandbox, a denied prompt,
  or the five-second timeout lark-cli has to defend against. An unattended
  agent — launchd, ssh, a ``co deploy --to`` server — has no login keychain at
  all, which is the same wall the browser gate hit over SSH (openonion/browser#137).
* Nothing new to back up, and recovery already exists.
* Rotation is already specified. ``slip13_path`` takes an index whose whole
  purpose is this, so rotating is "derive at index+1, re-encrypt", with no
  key-wrapping scheme to design.

Rooted at agent.key, not at the phrase
--------------------------------------
The root of the subtree is ``.co/keys/agent.key`` — 32 bytes, which is exactly
what ``master_key()`` takes — and **not** ``.co/keys/recovery.txt``.

The phrase file is optional. ``co keys`` prints "missing" for it without
complaint, and writing the twelve words down and deleting the file is the correct
thing to do with a recovery phrase. Deriving from it would have meant that doing
the right thing with your backup silently made every stored secret unopenable,
and that a routine ``co env get`` opened the most sensitive file on the machine.

Nothing is lost by moving the root down one level, because ``agent.key`` is
itself ``derive_path(bip39_seed, slip13_path(ACCOUNT_URI))``. The twelve words
still reach every secret — through the agent key rather than around it:

    twelve words ──BIP-39──▶ seed ──SLIP-0013──▶ agent.key ──SLIP-0013──▶ secret key

So the store keeps the property a keychain-held master key cannot have (a new
machine can decrypt), while depending only on the file that is always present.

Its own namespace, deliberately
-------------------------------
``secret://`` is not ``agent://``, and the derivation is hardened at every level.
One leaked file-encryption key must not be the agent's *signing* key, or a
readable config becomes a forgeable identity; hardened-only derivation is what
makes the other direction impossible too.

What this does not claim
------------------------
``agent.key`` is a ``0600`` file next to the ciphertext. Someone who can read it
can decrypt everything here, and this file does not pretend otherwise — but that
person can already sign as the agent, so the secret store is not what they would
attack. What it buys is that a secret is no longer sitting in plaintext in a file
people ``cat``, paste into issues, and read aloud on calls — which is the
exposure #1497 was opened about.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from .derive import derive_path, slip13_path

SCHEMA = 1


class SecretStoreError(RuntimeError):
    """Base for the two failures a caller must tell apart."""


class MissingAgentKey(SecretStoreError):
    """There is no agent key, so nothing can be derived."""


class Undecryptable(SecretStoreError):
    """The stored bytes do not open with the key this agent and index derive."""


def secret_uri(name: str) -> str:
    """``secret://<name>``, canonicalised the way identity_uri does it.

    A different string is a different key, so the trim-and-lowercase happens in
    one place rather than at each call site.
    """
    canonical = name.strip().lower()
    if not canonical:
        raise ValueError("secret name is empty")
    return f"secret://{canonical}"


def _agent_key_file(co_dir: Path) -> Path:
    return Path(co_dir) / "keys" / "agent.key"


def read_agent_key(co_dir: Path) -> bytes:
    """The 32-byte agent key for this .co directory, or MissingAgentKey.

    Read from the file rather than taken as an argument so an unattended process
    needs nothing interactive — which is the whole point of deriving instead of
    using a keychain.
    """
    path = _agent_key_file(co_dir)
    try:
        material = path.read_bytes()
    except OSError as exc:
        raise MissingAgentKey(
            f"no agent key at {path}. An encrypted secret is unlocked by this "
            f"agent's own key. Next: co init"
        ) from exc
    if len(material) < 32:
        raise MissingAgentKey(
            f"{path} holds {len(material)} bytes; an agent key is 32."
        )
    return material[:32]


def _key_for(agent_key: bytes, name: str, index: int) -> bytes:
    return derive_path(agent_key, slip13_path(secret_uri(name), index))


def _secrets_dir(co_dir: Path) -> Path:
    return Path(co_dir) / "keys" / "secrets"


def _file_for(co_dir: Path, name: str) -> Path:
    # The name is already canonicalised by secret_uri; keep the filename in the
    # same shape so a directory listing and a `co env` listing agree.
    safe = secret_uri(name).removeprefix("secret://").replace("/", "_")
    return _secrets_dir(co_dir) / f"{safe}.enc"


def put(co_dir: Path, name: str, value: str, *, index: int = 0) -> Path:
    """Encrypt ``value`` under the key derived for ``name`` at ``index``."""
    from nacl import secret as nacl_secret
    from nacl import utils as nacl_utils

    agent_key = read_agent_key(co_dir)
    box = nacl_secret.SecretBox(_key_for(agent_key, name, index))
    nonce = nacl_utils.random(nacl_secret.SecretBox.NONCE_SIZE)
    sealed = box.encrypt(value.encode("utf-8"), nonce)

    directory = _secrets_dir(co_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(directory, 0o700)

    path = _file_for(co_dir, name)
    # The index is stored with the ciphertext because it is not a secret and
    # without it a rotated file could only be opened by guessing.
    path.write_text(
        json.dumps(
            {
                "v": SCHEMA,
                "index": index,
                "ct": base64.b64encode(bytes(sealed)).decode("ascii"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if sys.platform != "win32":
        path.chmod(0o600)
    return path


def get(co_dir: Path, name: str) -> str:
    """The plaintext, or Undecryptable. Never a wrong answer."""
    from nacl import secret as nacl_secret
    from nacl.exceptions import CryptoError

    # The agent key is checked first on purpose. With both missing, "there is no
    # agent key" is the fact that explains every other failure that follows, and
    # "no stored secret" would send the reader looking for a file they could not
    # have opened anyway.
    agent_key = read_agent_key(co_dir)

    path = _file_for(co_dir, name)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Undecryptable(f"no stored secret named {name!r} at {path}") from exc
    except json.JSONDecodeError as exc:
        raise Undecryptable(f"{path} is not a secret record this version wrote") from exc

    if record.get("v") != SCHEMA:
        raise Undecryptable(
            f"{path} was written by schema v{record.get('v')}, this is v{SCHEMA}"
        )

    box = nacl_secret.SecretBox(_key_for(agent_key, name, int(record.get("index", 0))))
    try:
        return box.decrypt(base64.b64decode(record["ct"])).decode("utf-8")
    except (CryptoError, KeyError, ValueError) as exc:
        raise Undecryptable(
            f"{path} does not open with the key this agent key derives. "
            f"A different agent wrote it, or the file was edited."
        ) from exc


def rotate(co_dir: Path, name: str) -> int:
    """Re-encrypt at the next index and return it.

    The old ciphertext stops being derivable the moment the file is replaced —
    that is what `slip13_path`'s index is for, and why there is no key-wrapping
    step here.
    """
    path = _file_for(co_dir, name)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Undecryptable(f"no stored secret named {name!r} to rotate") from exc
    plaintext = get(co_dir, name)
    nxt = int(record.get("index", 0)) + 1
    put(co_dir, name, plaintext, index=nxt)
    return nxt


def drop(co_dir: Path, name: str) -> bool:
    """Remove a stored secret. True when there was one."""
    path = _file_for(co_dir, name)
    try:
        path.unlink()
        return True
    except OSError:
        return False


def stored_names(co_dir: Path) -> list[str]:
    """Names with an encrypted value, for listings that must not decrypt."""
    directory = _secrets_dir(co_dir)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.enc"))
