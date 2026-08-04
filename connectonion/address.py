"""
Purpose: Generate and manage Ed25519 cryptographic agent identities with seed phrase recovery
LLM-Note:
  Dependencies: imports from [os, pathlib, typing, nacl.signing, mnemonic] | imported by [cli/commands/auth_commands.py] | tested by [tests/unit/test_address.py]
  Data flow: generate() → creates 12-word seed phrase via Mnemonic → derives SigningKey from seed → creates address (0x + hex public key) → returns {address, short_address, email, seed_phrase, signing_key} | recover(seed_phrase) → validates phrase → recreates SigningKey → recreates address
  State/Effects: save() writes to .co/keys/ directory: agent.key (binary signing key), recovery.txt (seed phrase), DO_NOT_SHARE (warning) | sets file permissions to 0o600 | load() reads from .co/keys/ and env vars (AGENT_EMAIL, IS_EMAIL_ACTIVE) | no global state
  Integration: exposes generate(), recover(seed_phrase), save(address_data, co_dir), load(co_dir), verify(address, message, signature), sign(address_data, message) | address format: 0x + 64 hex chars (32 bytes public key) | email format: first 10 chars + @mail.openonion.ai
  Performance: Ed25519 signing is fast (sub-millisecond) | mnemonic generation and validation are fast | file I/O minimal (only on save/load)
  Errors: raises ImportError if pynacl or mnemonic not installed | raises ValueError for invalid recovery phrase | returns None for missing keys (graceful) | verify() returns False for invalid signatures
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from .derive import ACCOUNT_URI, derive_path, slip13_path, ssh_uri

try:
    from nacl.signing import SigningKey, VerifyKey
    from mnemonic import Mnemonic
except ImportError:
    # Graceful fallback if dependencies not installed
    SigningKey = None
    VerifyKey = None
    Mnemonic = None
    

# ---------------------------------------------------------------------------
# Where the identity key comes from
#
# BIP-39 gives the phrase and the seed; SLIP-0010 turns that seed into a tree
# (connectonion/derive.py), and this is the account leaf of it:
#
#     twelve words ──BIP-39──▶ seed ──SLIP-0010/SLIP-0013──▶ m/13'/…
#
# It used to be `SigningKey(seed[:32])` — a bare slice matching no BIP, no SLIP
# and no path, so the twelve words meant something only inside this software.
# Retiring it re-keys every address at once, which is why it happened while the
# user base made that affordable rather than later, when it would not (#404).
#
# Existing installs are unaffected until they recover: load() reads
# .co/keys/agent.key, and that file still holds whatever key wrote it. The break
# is that a phrase now derives a *different* key than the one on disk beside it —
# which load() detects and says out loud rather than leaving you with two
# identities and no hint of it.
# ---------------------------------------------------------------------------


def _account_key(seed: bytes) -> "SigningKey":
    """The Ed25519 key at the account's SLIP-0013 path."""
    return SigningKey(derive_path(seed, slip13_path(ACCOUNT_URI)))


class Identity(dict):
    """The identity dict, which does not print its own secrets.

    `load()` carries the recovery phrase because things genuinely need it after
    loading -- `co server` derives the deploy SSH key from it, `co keys` shows
    it on request -- so it stays. What changes is that reading it is something
    you ask for, `keys["seed_phrase"]`, rather than something that falls out of
    printing the object.

    A plain dict prints everything it holds, and this one is held in ordinary
    places: it is what `address.load()` hands to `connect(keys=...)`, and since
    #673 every client stores one. `print(keys)`, a logger call, a crash reporter
    that renders locals, or `repr(agent.__dict__)` then puts twelve words that
    reconstruct the private key wherever that text goes. That happened during
    review of #673, to a real machine identity, from a five-line probe.

    The signing key is hidden for the same reason: it is the private half, and a
    repr that renders it is the same leak by another route.
    """

    _SECRET = ("seed_phrase", "signing_key", "private_key")

    def __repr__(self) -> str:
        return repr({
            key: ("<hidden>" if key in self._SECRET and value is not None else value)
            for key, value in self.items()
        })

    __str__ = __repr__


def derives_from(seed_phrase: str, signing_key) -> bool:
    """Does this phrase produce this key under the current derivation?

    False for a key minted before the SLIP-0010 switch — that is the whole
    reason this exists.
    """
    mnemo = Mnemonic("english")
    if not mnemo.check(seed_phrase):
        return False
    return bytes(_account_key(mnemo.to_seed(seed_phrase))) == bytes(signing_key)


def generate() -> Dict[str, Any]:
    """
    Generate a new agent address with Ed25519 keys.
    
    Returns:
        Dictionary containing:
        - address: Hex-encoded public key with 0x prefix (66 chars)
        - short_address: Truncated display format (0x3d40...660c)
        - email: Agent's email address (0x3d4017c3@mail.openonion.ai)
        - seed_phrase: 12-word recovery phrase
        - signing_key: Ed25519 signing key for signatures
        
    Example:
        >>> addr = generate()
        >>> print(addr['address'])
        0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
        >>> print(addr['email'])
        0x3d4017c3@mail.openonion.ai
    """
    if SigningKey is None or Mnemonic is None:
        raise ImportError(
            "Required libraries not installed. "
            "Please run: pip install pynacl mnemonic"
        )
    
    # Generate 12-word recovery phrase
    mnemo = Mnemonic("english")
    seed_phrase = mnemo.generate(strength=128)  # 128 bits = 12 words
    
    # Derive seed from phrase
    seed = mnemo.to_seed(seed_phrase)

    # SLIP-0010 down the SLIP-0013 account path. See _account_key().
    signing_key = _account_key(seed)
    
    # Create address (hex-encoded public key with 0x prefix)
    public_key_bytes = bytes(signing_key.verify_key)
    address = "0x" + public_key_bytes.hex()
    
    # Create short display format
    short_address = f"{address[:6]}...{address[-4:]}"
    
    # Create email address (first 10 chars of address)
    email = f"{address[:10]}@mail.openonion.ai"
    
    return Identity({
        "address": address,
        "short_address": short_address,
        "email": email,
        "email_active": False,  # Email inactive until authenticated
        "seed_phrase": seed_phrase,
        "signing_key": signing_key
    })


def recover(seed_phrase: str) -> Dict[str, Any]:
    """
    Recover agent address from a recovery phrase.
    
    Args:
        seed_phrase: 12-word recovery phrase
        
    Returns:
        Dictionary containing address and signing_key
        
    Raises:
        ValueError: If recovery phrase is invalid
        
    Example:
        >>> addr = recover("canyon robot vacuum circle...")
        >>> print(addr['address'])
        0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
    """
    if Mnemonic is None or SigningKey is None:
        raise ImportError(
            "Required libraries not installed. "
            "Please run: pip install pynacl mnemonic"
        )
    
    mnemo = Mnemonic("english")
    
    # Validate recovery phrase
    if not mnemo.check(seed_phrase):
        raise ValueError("Invalid recovery phrase")
    
    # Derive seed from phrase
    seed = mnemo.to_seed(seed_phrase)

    # Must match generate() exactly, or a phrase recovers a different agent.
    signing_key = _account_key(seed)
    
    # Recreate address
    public_key_bytes = bytes(signing_key.verify_key)
    address = "0x" + public_key_bytes.hex()
    short_address = f"{address[:6]}...{address[-4:]}"
    
    # Create email address (first 10 chars of address)
    email = f"{address[:10]}@mail.openonion.ai"
    
    return Identity({
        "address": address,
        "short_address": short_address,
        "email": email,
        "email_active": False,  # Email inactive until authenticated
        "signing_key": signing_key
    })


def save(address_data: Dict[str, Any], co_dir: Path) -> None:
    """
    Save agent keys to .co/keys/ directory.
    
    Args:
        address_data: Dictionary from generate() or recover()
        co_dir: Path to .co directory
        
    Creates:
        - .co/keys/agent.key (private signing key)
        - .co/keys/recovery.txt (12-word phrase)
        - .co/keys/DO_NOT_SHARE (warning file)
    """
    # Create keys directory
    keys_dir = co_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    
    # Save private key (binary format)
    key_file = keys_dir / "agent.key"
    key_file.write_bytes(bytes(address_data["signing_key"]))
    if sys.platform != 'win32':
        key_file.chmod(0o600)  # Read/write for owner only (Unix/Mac only)

    # Save recovery phrase if present
    if "seed_phrase" in address_data:
        recovery_file = keys_dir / "recovery.txt"
        recovery_file.write_text(address_data["seed_phrase"], encoding='utf-8')
        if sys.platform != 'win32':
            recovery_file.chmod(0o600)  # Read/write for owner only (Unix/Mac only)
    
    # Create warning file
    warning_file = keys_dir / "DO_NOT_SHARE"
    if not warning_file.exists():
        warning_content = """⚠️ WARNING: PRIVATE KEYS - DO NOT SHARE ⚠️

This directory contains private cryptographic keys.
NEVER share these files or commit them to version control.
Anyone with these keys can impersonate your agent.

Files:
- agent.key: Your agent's private signing key
- recovery.txt: 12-word recovery phrase

Keep these files secure and backed up.
"""
        warning_file.write_text(warning_content, encoding='utf-8')


def load(co_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Load existing agent keys from .co/keys/ directory.
    
    Args:
        co_dir: Path to .co directory
        
    Returns:
        Dictionary with address and signing_key, or None if not found
        
    Example:
        >>> addr = load(Path(".co"))
        >>> if addr:
        ...     print(addr['address'])
    """
    if SigningKey is None:
        return None
        
    keys_dir = co_dir / "keys"
    key_file = keys_dir / "agent.key"
    
    if not key_file.exists():
        return None
    
    try:
        # Load signing key
        key_bytes = key_file.read_bytes()
        signing_key = SigningKey(key_bytes)
        
        # Derive address from public key
        public_key_bytes = bytes(signing_key.verify_key)
        address = "0x" + public_key_bytes.hex()
        short_address = f"{address[:6]}...{address[-4:]}"
        
        # Try to load recovery phrase if it exists
        recovery_file = keys_dir / "recovery.txt"
        seed_phrase = None
        if recovery_file.exists():
            seed_phrase = recovery_file.read_text(encoding='utf-8').strip()

        # A key minted before the SLIP-0010 switch still works — it is right here
        # on disk and this is the identity the agent has been using. What has
        # changed is that the phrase beside it now derives a *different* key, so
        # `co auth recover` with those same words lands on another address.
        #
        # Saying nothing would leave two identities for one phrase and no hint of
        # it, which is how someone recovers onto a fresh agent and wonders where
        # their credits went. Say it once, here, where both halves are in hand.
        legacy_derivation = bool(seed_phrase) and not derives_from(seed_phrase, signing_key)
        
        # Load email and activation status from environment
        email = os.getenv("AGENT_EMAIL", f"{address[:10]}@mail.openonion.ai")
        email_active = os.getenv("IS_EMAIL_ACTIVE", "").lower() == "true"
        
        result = Identity({
            "address": address,
            "short_address": short_address,
            "email": email,
            "email_active": email_active,
            "legacy_derivation": legacy_derivation,
            "signing_key": signing_key
        })
        
        if seed_phrase:
            result["seed_phrase"] = seed_phrase
            
        return result
        
    except Exception:
        # Invalid key file or other error
        return None


def verify(address: str, message: bytes, signature: bytes) -> bool:
    """
    Verify a signature using an agent's address.
    
    Since the address IS the public key (hex-encoded), we can verify
    signatures directly without needing additional information.
    
    Args:
        address: Agent's hex address (0x...)
        message: Message that was signed
        signature: 64-byte Ed25519 signature
        
    Returns:
        True if signature is valid, False otherwise
        
    Example:
        >>> msg = b"Hello, ConnectOnion!"
        >>> sig = agent.sign(msg)
        >>> verify(agent_address, msg, sig)
        True
    """
    if VerifyKey is None:
        return False
    
    try:
        # Validate address format
        if not address.startswith("0x") or len(address) != 66:
            return False
            
        # Extract public key from address (it IS the public key!)
        public_key_hex = address[2:]
        public_key_bytes = bytes.fromhex(public_key_hex)
        
        # Create verify key
        verify_key = VerifyKey(public_key_bytes)
        
        # Verify signature
        verify_key.verify(message, signature)
        return True
        
    except Exception:
        # Invalid signature, wrong key, or other error
        return False


def sign(address_data: Dict[str, Any], message: bytes) -> bytes:
    """
    Sign a message with the agent's private key.
    
    Args:
        address_data: Dictionary from generate() or load()
        message: Message to sign
        
    Returns:
        64-byte Ed25519 signature
        
    Example:
        >>> addr = load(Path(".co"))
        >>> sig = sign(addr, b"Hello!")
    """
    if "signing_key" not in address_data:
        raise ValueError("No signing key in address data")
        
    signed = address_data["signing_key"].sign(message)
    return signed.signature

# ---------------------------------------------------------------------------
# SSH access key
#
# The agent identity above uses only the first 32 of the seed's 64 bytes. The
# same recovery phrase can therefore also back the operator's SSH key, so there
# is still exactly one thing to write down.
#
# The agent key is deliberately left on its original derivation — bare
# seed[:32]. Deriving it through HKDF instead would change every existing
# agent's address and void every trust relationship keyed to it. Only the new
# SSH key is derived with a label, so a third purpose can be added later
# without disturbing either of the first two.
#
#     agent identity : SigningKey(seed[:32])                     (unchanged)
#     ssh access     : HKDF(seed, info="connectonion:ssh:v1")
#
# Two keys, not one used twice: a signing oracle in the agent protocol must not
# be usable against SSH login.
# ---------------------------------------------------------------------------

SSH_DERIVATION_INFO = b"connectonion:ssh:v1"


def _hkdf_sha512(seed: bytes, info: bytes, length: int = 32) -> bytes:
    """RFC 5869 HKDF with SHA-512, no salt. Enough for one 32-byte output."""
    import hashlib
    import hmac

    prk = hmac.new(b"\x00" * hashlib.sha512().digest_size, seed, hashlib.sha512).digest()

    out = b""
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha512).digest()
        out += block
        counter += 1
    return out[:length]


def derive_ssh_key(seed_phrase: str, host: str = None, user: str = "root") -> Dict[str, str]:
    """Derive an Ed25519 SSH keypair from a recovery phrase.

    With a ``host``, the key comes off the SLIP-0010 tree at the SLIP-0013 path
    for ``ssh://<user>@<host>`` — one key per server, and rotatable by bumping
    the URI's index. That is where this is going (#427).

    Without one, it is the original HKDF key: a single key shared by every
    server. That key cannot simply be dropped, because it is the line sitting in
    ``authorized_keys`` on every machine provisioned to date, and it is the way
    back into them. It stays derivable until those are backfilled, and goes in
    1.6.

    Ed25519 is a native OpenSSH type, so the public half is an ordinary
    `ssh-ed25519 AAAA…` line that needs nothing custom on any server.

    Args:
        seed_phrase: The 12-word BIP39 recovery phrase

    Returns:
        {"public_line": "ssh-ed25519 AAAA… connectonion", "private_key": "-----BEGIN…"}

    Example:
        >>> keys = derive_ssh_key("legal winner thank year wave …")
        >>> keys["public_line"].startswith("ssh-ed25519 ")
        True
    """
    if Mnemonic is None or SigningKey is None:
        raise ImportError(
            "Missing dependencies. Install with:\n"
            "  pip install pynacl mnemonic"
        )

    mnemo = Mnemonic("english")
    if not mnemo.check(seed_phrase):
        raise ValueError("Invalid recovery phrase")

    seed = mnemo.to_seed(seed_phrase)
    if host is None:
        # The pre-tree key. Still derived because it is in authorized_keys on
        # every server provisioned so far — see derive_ssh_key's docstring.
        signing_key = SigningKey(_hkdf_sha512(seed, SSH_DERIVATION_INFO))
    else:
        signing_key = SigningKey(derive_path(seed, slip13_path(ssh_uri(user, host))))

    return Identity({
        "public_line": _openssh_public_line(bytes(signing_key.verify_key)),
        "private_key": _openssh_private_key(bytes(signing_key), bytes(signing_key.verify_key)),
    })


def _ssh_string(data: bytes) -> bytes:
    """SSH wire format: 4-byte big-endian length, then the bytes."""
    return len(data).to_bytes(4, "big") + data


def _openssh_public_line(public_key: bytes, comment: str = "connectonion") -> str:
    """Encode an Ed25519 public key as an authorized_keys line."""
    import base64

    blob = _ssh_string(b"ssh-ed25519") + _ssh_string(public_key)
    return f"ssh-ed25519 {base64.b64encode(blob).decode()} {comment}"


def _openssh_private_key(private_key: bytes, public_key: bytes,
                         comment: str = "connectonion") -> str:
    """Encode an Ed25519 keypair in the unencrypted OPENSSH private key format.

    Written by hand rather than pulled from `cryptography`: the format is a
    handful of length-prefixed strings, and this keeps the dependency list as it
    is. Unencrypted because the recovery phrase is the thing being protected —
    the file can always be re-derived from it.
    """
    import base64

    # OpenSSH stores the private half as private||public (64 bytes)
    key_pair = private_key + public_key

    pub_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(public_key)

    # The checkint appears twice so a decrypting client can tell it got the
    # passphrase right. With no passphrase any value works; zero is honest.
    checkint = (0).to_bytes(4, "big")
    private_blob = (
        checkint + checkint
        + _ssh_string(b"ssh-ed25519")
        + _ssh_string(public_key)
        + _ssh_string(key_pair)
        + _ssh_string(comment.encode())
    )
    # Pad to the cipher block size (8 for "none") with 1,2,3…
    pad = 0
    while len(private_blob) % 8 != 0:
        pad += 1
        private_blob += bytes([pad])

    body = (
        b"openssh-key-v1\x00"
        + _ssh_string(b"none")        # cipher
        + _ssh_string(b"none")        # kdf
        + _ssh_string(b"")            # kdf options
        + (1).to_bytes(4, "big")      # number of keys
        + _ssh_string(pub_blob)
        + _ssh_string(private_blob)
    )

    b64 = base64.b64encode(body).decode()
    lines = [b64[i:i + 70] for i in range(0, len(b64), 70)]
    return (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        + "\n".join(lines)
        + "\n-----END OPENSSH PRIVATE KEY-----\n"
    )
