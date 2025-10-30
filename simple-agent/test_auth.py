#!/usr/bin/env python3
"""Test authentication with OpenOnion API."""

import json
import time
import requests
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder, HexEncoder
from pathlib import Path

def authenticate():
    """Authenticate with OpenOnion API using agent keys."""

    # Load the agent key
    key_path = Path(".co/keys/agent.key")
    if not key_path.exists():
        print("❌ Agent key not found at .co/keys/agent.key")
        return None

    # Read the binary key
    with open(key_path, "rb") as f:
        seed = f.read()

    # Create signing key from seed
    signing_key = SigningKey(seed)
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()

    print(f"🔑 Public key: {public_key}")

    # Create signed message
    timestamp = int(time.time())
    message = json.dumps({
        "public_key": public_key,
        "timestamp": timestamp
    }, separators=(',', ':'))

    # Sign the message
    signed = signing_key.sign(message.encode())
    signature = signed.signature.hex()

    print(f"📝 Message: {message}")
    print(f"✍️  Signature: {signature[:40]}...")

    # Try production API
    api_url = "https://oo.openonion.ai/auth"
    print(f"\n🌐 Authenticating with {api_url}")

    try:
        response = requests.post(
            api_url,
            headers={
                "X-Public-Key": public_key,
                "X-Signature": signature,
                "X-Message": message
            },
            timeout=10
        )

        print(f"📡 Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            print(f"✅ Authentication successful!")
            print(f"🎫 Token: {token[:50]}...")

            # Update config.toml
            import toml
            config_path = Path(".co/config.toml")
            config = toml.load(config_path)
            config["auth"]["token"] = token

            with open(config_path, "w") as f:
                toml.dump(config, f)

            print(f"💾 Token saved to .co/config.toml")
            return token
        else:
            print(f"❌ Authentication failed: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    authenticate()