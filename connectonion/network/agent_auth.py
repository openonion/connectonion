"""Sign in to Cloud as the exact agent identity supplied by the caller."""

import time

import requests


def signed_agent_token(keys: dict, origin: str) -> str:
    address = keys["address"]
    message = f"ConnectOnion-Auth-{address}-{int(time.time())}"
    response = requests.post(f"{origin}/api/v1/auth", timeout=30, json={
        "public_key": address,
        "message": message,
        "signature": keys["signing_key"].sign(message.encode()).signature.hex(),
    })
    response.raise_for_status()
    return response.json()["token"]
