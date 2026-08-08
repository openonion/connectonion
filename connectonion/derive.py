"""SLIP-0010 key derivation — one recovery phrase, a tree of keys.

LLM-Note:
  Dependencies: imports from [hashlib, hmac, struct] — stdlib only, no crypto library | imported by [address.py] | tested by [tests/unit/test_derive.py]
  Data flow: BIP-39 seed (64 bytes) → master_key() → (key, chain_code) → derive_child() per hardened index → derive_path(seed, "m/13'/…") → 32-byte private key for SigningKey()
  State/Effects: none — pure functions, no I/O, no globals
  Integration: exposes derive_path(seed, path), slip13_path(uri, index=0), identity_uri/ssh_uri/ACCOUNT_URI | the 32 bytes returned are an Ed25519 seed, i.e. what nacl.signing.SigningKey() takes
  Performance: one HMAC-SHA512 per path level; a five-level path is five HMACs, microseconds
  Errors: raises ValueError on a non-hardened index, a malformed path, or a seed of the wrong length — never silently derives something else

What this replaces and why
--------------------------
Identity used to be ``SigningKey(seed[:32])``: standards-compliant BIP-39 right up
to the last step, then a bare slice that corresponds to no BIP, no SLIP, and no
derivation path. Import the phrase into Ledger, Trezor, Phantom or Keplr and you
never arrive at the same address, on any path any of them offers (see #400).

SLIP-0010 is BIP-32 adapted to Ed25519 — what Solana, Brave and Trezor's own
SSH/GPG features use. The twelve words stop meaning something only inside our own
software: any SLIP-0010 implementation recovers the tree.

Hardened-only, and that is the point
------------------------------------
SLIP-0010 offers **hardened derivation only** for Ed25519. Ed25519 clamps bits of
the private key and its group order carries a cofactor, so BIP-32's "add a scalar
to both the private and public side" trick does not survive; there is no
parent-public → child-public step, and therefore no watch-only.

That is the property we want, not a compromise. Non-hardened derivation has an
inverse: ``child = parent + t`` where ``t`` is computable from public data, so one
leaked child private key plus the public tree recovers the parent — and the parent
generates everything else. Our agent identities and SSH keys live on servers,
which can be breached or snapshotted. Under SLIP-0010 that exposes one key. The
watch-only we give up answers a question nobody here asks: our balances live in a
Postgres row keyed by public key and need a signature to read.

This module therefore refuses a non-hardened index rather than accepting one and
quietly deriving something else.
"""

import hashlib
import hmac
import struct

# SLIP-0010's domain separator for the ed25519 curve. Changing this string
# changes every key in the tree.
ED25519_CURVE = b"ed25519 seed"

HARDENED = 0x80000000

# SLIP-0013 (authentication identities) rather than BIP-44. It needs no coin-type
# registration, and it is what trezor-agent already uses for SSH. SLIP-0044 assigns
# coin types only where "there is a wallet implementing BIP-0044 for desired coin"
# — we are not a coin, and squatting an unregistered index risks colliding with a
# real assignment later. m/44'/<chain>' stays free for on-chain assets, using that
# chain's own coin type, if they ever exist.
SLIP13_PURPOSE = 13

# The account identity — the operator's own key, the one holding the balance.
# This is a cryptographic domain separator, not a network destination. It must
# remain stable when CONNECTONION_BACKEND_URL changes or recovery would derive a
# different key on staging than on production.
ACCOUNT_URI = "https://oo.openonion.ai"


def master_key(seed: bytes) -> tuple[bytes, bytes]:
    """The SLIP-0010 master key and chain code for a BIP-39 seed.

    ``I = HMAC-SHA512(key="ed25519 seed", data=seed)``; the left half is the
    private key, the right half the chain code. Ed25519 needs no "is this scalar
    in range" retry loop — every 32-byte string is a valid ed25519 seed — so
    unlike secp256k1 this cannot fail.
    """
    if not 16 <= len(seed) <= 64:
        raise ValueError(f"seed must be 16-64 bytes, got {len(seed)}")
    digest = hmac.new(ED25519_CURVE, seed, hashlib.sha512).digest()
    return digest[:32], digest[32:]


def derive_child(key: bytes, chain_code: bytes, index: int) -> tuple[bytes, bytes]:
    """One hardened SLIP-0010 step.

    ``I = HMAC-SHA512(key=chain_code, data=0x00 || key || index_be)``. The leading
    zero byte is what makes this the *private* derivation; there is no public one
    on this curve.
    """
    if index < HARDENED:
        raise ValueError(
            f"index {index} is not hardened. SLIP-0010 ed25519 has no public "
            f"derivation, so every level must be hardened (>= 2**31)."
        )
    data = b"\x00" + key + struct.pack(">I", index)
    digest = hmac.new(chain_code, data, hashlib.sha512).digest()
    return digest[:32], digest[32:]


def derive_path(seed: bytes, path: str) -> bytes:
    """The 32-byte private key at ``path``, e.g. ``m/13'/1444947841'/…``.

    The result is an Ed25519 seed — hand it straight to ``SigningKey()``.

    Every level must be hardened; a path written without the apostrophe is a
    mistake, not a request for public derivation, so it raises rather than
    deriving a different key.
    """
    key, chain_code = master_key(seed)
    for level in _parse_path(path):
        key, chain_code = derive_child(key, chain_code, level)
    return key


def _parse_path(path: str) -> list[int]:
    """``"m/13'/7'"`` → ``[13 + 2**31, 7 + 2**31]``."""
    parts = path.strip().split("/")
    if not parts or parts[0] != "m":
        raise ValueError(f"path must start with 'm', got {path!r}")

    indices = []
    for part in parts[1:]:
        if not part.endswith(("'", "h", "H")):
            raise ValueError(
                f"path level {part!r} is not hardened. Write it as {part}' — "
                f"SLIP-0010 ed25519 has no unhardened derivation."
            )
        number = part[:-1]
        if not number.isdigit():
            raise ValueError(f"path level {part!r} is not a number")
        value = int(number)
        if value >= HARDENED:
            raise ValueError(f"path level {part!r} is out of range")
        indices.append(value + HARDENED)
    return indices


def slip13_path(uri: str, index: int = 0) -> str:
    """The SLIP-0013 path for an identity URI.

    ``m/13'/A'/B'/C'/D'`` where ``A..D`` are the first 16 bytes of
    ``SHA256(index_le || uri)`` read as four little-endian uint32s, each hardened.

    The name *is* the path, which is what lets ``co keys`` print an agent's
    address before anything is deployed, and makes the same name always return the
    same key. ``index`` is the rotation counter: bump it and the old key simply
    stops being derived.

    The cost, accepted: a path is opaque — ``m/13'/1444947841'/…`` does not say
    which agent it is — and a mistyped name is a different key rather than an
    error. That is why callers must go through :func:`identity_uri` / :func:`ssh_uri`,
    which canonicalise before hashing.
    """
    digest = hashlib.sha256(struct.pack("<I", index) + uri.encode("utf-8")).digest()
    levels = struct.unpack("<4I", digest[:16])
    return "m/13'/" + "/".join(f"{level & 0x7FFFFFFF}'" for level in levels)


def identity_uri(name: str) -> str:
    """``agent://<name>``, canonicalised.

    Trimmed and lowercased, because a different string is a different identity and
    an address is a name people retype.
    """
    canonical = name.strip().lower()
    if not canonical:
        raise ValueError("agent name is empty")
    return f"agent://{canonical}"


def ssh_uri(user: str, host: str) -> str:
    """``ssh://<user>@<host>``, matching what trezor-agent derives for SSH."""
    return f"ssh://{user.strip().lower()}@{host.strip().lower()}"
