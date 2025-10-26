"""
Purpose: Generate and manage Ed25519 cryptographic agent identities with seed phrase recovery
LLM-Note:
  Dependencies: imports from [os, pathlib, typing, nacl.signing, mnemonic] | imported by [cli/commands/auth_commands.py] | tested by [tests/test_address.py]
  Data flow: generate() → creates 12-word seed phrase via Mnemonic → derives SigningKey from seed → creates address (0x + hex public key) → returns {address, short_address, email, seed_phrase, signing_key} | recover(seed_phrase) → validates phrase → recreates SigningKey → recreates address
  State/Effects: save() writes to .co/keys/ directory: agent.key (binary signing key), recovery.txt (seed phrase), DO_NOT_SHARE (warning) | sets file permissions to 0o600 | load() reads from .co/keys/ and .co/config.toml | no global state
  Integration: exposes generate(), recover(seed_phrase), save(address_data, co_dir), load(co_dir), verify(address, message, signature), sign(address_data, message) | address format: 0x + 64 hex chars (32 bytes public key) | email format: first 10 chars + @mail.openonion.ai
  Performance: Ed25519 signing is fast (sub-millisecond) | mnemonic generation and validation are fast | file I/O minimal (only on save/load)
  Errors: raises ImportError if pynacl or mnemonic not installed | raises ValueError for invalid recovery phrase | returns None for missing keys (graceful) | verify() returns False for invalid signatures
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from nacl.signing import SigningKey, VerifyKey
    from mnemonic import Mnemonic
except ImportError:
    # Graceful fallback if dependencies not installed
    SigningKey = None
    VerifyKey = None
    Mnemonic = None
    

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
    
    # Create Ed25519 signing key from first 32 bytes
    signing_key = SigningKey(seed[:32])
    
    # Create address (hex-encoded public key with 0x prefix)
    public_key_bytes = bytes(signing_key.verify_key)
    address = "0x" + public_key_bytes.hex()
    
    # Create short display format
    short_address = f"{address[:6]}...{address[-4:]}"
    
    # Create email address (first 10 chars of address)
    email = f"{address[:10]}@mail.openonion.ai"
    
    return {
        "address": address,
        "short_address": short_address,
        "email": email,
        "email_active": False,  # Email inactive until authenticated
        "seed_phrase": seed_phrase,
        "signing_key": signing_key
    }


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
    
    # Recreate signing key
    signing_key = SigningKey(seed[:32])
    
    # Recreate address
    public_key_bytes = bytes(signing_key.verify_key)
    address = "0x" + public_key_bytes.hex()
    short_address = f"{address[:6]}...{address[-4:]}"
    
    # Create email address (first 10 chars of address)
    email = f"{address[:10]}@mail.openonion.ai"
    
    return {
        "address": address,
        "short_address": short_address,
        "email": email,
        "email_active": False,  # Email inactive until authenticated
        "signing_key": signing_key
    }


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
        
        # Try to load email and activation status from config.toml
        email = f"{address[:10]}@mail.openonion.ai"  # Default
        email_active = False  # Default to inactive
        
        config_path = co_dir / "config.toml"
        if config_path.exists():
            try:
                import toml
                config = toml.load(config_path)
                if "agent" in config:
                    email = config["agent"].get("email", email)
                    email_active = config["agent"].get("email_active", False)
            except Exception:
                pass  # Use defaults if config reading fails
        
        result = {
            "address": address,
            "short_address": short_address,
            "email": email,
            "email_active": email_active,
            "signing_key": signing_key
        }
        
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