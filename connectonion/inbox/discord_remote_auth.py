"""
Purpose: Link the owner's Discord account by QR, the way the desktop app's "Log in with QR code" does
LLM-Note:
  Dependencies: imports from [asyncio, base64, hashlib, json, cryptography (RSA-OAEP), httpx, inbox/discord_user.py (web_headers, API)] and lazily from [websockets] | imported by [cli/commands/discord_commands.py] | tested by [tests/unit/test_inbox_discord_user.py]
  Data flow: wss remote-auth gateway → hello → init(our RSA public key) → nonce_proof (decrypt, hash, echo) → pending_remote_init(fingerprint) → QR of https://discord.com/ra/<fingerprint> → phone scans → pending_ticket(encrypted user preview) → phone confirms → pending_login(ticket) → POST /users/@me/remote-auth/login → encrypted_token → decrypt
  State/Effects: the private key lives in memory for one link only; nothing is written here
  Integration: the CLI shows the QR and the "log in as" preview through the two callbacks, so this module prints nothing
  Errors: Captcha when Discord wants a captcha (the paste fallback is the way out) | RuntimeError for a phone cancel, a timeout (close 4003) or any unexpected close

Protocol from docs.discord.food (remote-authentication/desktop); no code was
copied from any client that implements it.
"""

import asyncio
import base64
import hashlib
import json
from typing import Callable, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .discord_user import API, web_headers

REMOTE_AUTH = "wss://remote-auth-gateway.discord.gg/?v=2"

_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class Captcha(RuntimeError):
    """Discord wants a captcha before it hands over the token; co cannot solve one."""


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def encoded_public_key(key: rsa.RSAPrivateKey) -> str:
    der = key.public_key().public_bytes(serialization.Encoding.DER,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode()


def decrypt(key: rsa.RSAPrivateKey, encrypted: str) -> bytes:
    return key.decrypt(base64.b64decode(encrypted), _OAEP)


def proof(nonce: bytes) -> str:
    """What v2 wants back: the nonce's SHA-256, URL-safe base64, no padding."""
    return base64.urlsafe_b64encode(hashlib.sha256(nonce).digest()).decode().rstrip("=")


def qr_url(fingerprint: str) -> str:
    return f"https://discord.com/ra/{fingerprint}"


def user_preview(payload: bytes) -> dict:
    """`id:discriminator:avatar:username`, what the phone is about to log in as."""
    user_id, discriminator, avatar, username = payload.decode().split(":", 3)
    return {"id": user_id, "discriminator": discriminator, "avatar": avatar, "username": username}


async def ticket(show_qr: Callable[[str], None], show_user: Callable[[dict], None], *,
                 key: rsa.RSAPrivateKey, url: str = REMOTE_AUTH) -> str:
    """Hold the remote-auth socket until the phone confirms; return the login ticket."""
    import websockets

    headers = web_headers()
    async with websockets.connect(url, open_timeout=15, user_agent_header=headers["User-Agent"],
                                  additional_headers={"Origin": "https://discord.com"}) as socket:
        heartbeat = None
        try:
            async for frame in socket:
                event = json.loads(frame)
                op = event.get("op")
                if op == "hello":
                    heartbeat = asyncio.create_task(_heartbeat(socket, event["heartbeat_interval"] / 1000))
                    await socket.send(json.dumps({"op": "init", "encoded_public_key": encoded_public_key(key)}))
                elif op == "nonce_proof":
                    nonce = decrypt(key, event["encrypted_nonce"])
                    await socket.send(json.dumps({"op": "nonce_proof", "proof": proof(nonce)}))
                elif op == "pending_remote_init":
                    show_qr(qr_url(event["fingerprint"]))
                elif op == "pending_ticket":
                    show_user(user_preview(decrypt(key, event["encrypted_user_payload"])))
                elif op == "pending_login":
                    return str(event["ticket"])
                elif op == "cancel":
                    raise RuntimeError("the login was cancelled on the phone; nothing was linked")
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
    raise RuntimeError(_closed(socket.close_code))


def _closed(code: Optional[int]) -> str:
    if code == 4003:
        return "the QR code expired before the phone confirmed; nothing was linked. Next: co discord link --yes"
    return f"Discord closed the QR login (code {code}); nothing was linked. Next: co discord link --yes"


async def _heartbeat(socket, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await socket.send(json.dumps({"op": "heartbeat"}))


def exchange(http, key: rsa.RSAPrivateKey, login_ticket: str) -> str:
    """Trade the ticket for the account's token, decrypted with our key."""
    response = http.post(f"{API}/users/@me/remote-auth/login", json={"ticket": login_ticket},
                         headers=web_headers())
    payload = response.json()
    if "captcha_key" in payload:
        raise Captcha("Discord asked for a captcha before it would finish the QR login, and co "
                      "cannot solve one; nothing was linked. Next: co discord link --token --yes "
                      "and paste a token from a browser session you keep only for co")
    if response.status_code != 200 or "encrypted_token" not in payload:
        raise RuntimeError(f"Discord refused the QR login: {payload.get('message', response.status_code)}. "
                           "Next: co discord link --yes")
    return decrypt(key, payload["encrypted_token"]).decode()
