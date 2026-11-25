"""
Purpose: Fetch and open WhatsApp media from what a stored record keeps: a later `co whatsapp download <id>`, and the group history bundle WhatsApp sends when the account is added to a group (#2853)
LLM-Note:
  Dependencies: imports from [base64, hashlib, hmac, zlib, httpx, cryptography] | imported by [inbox/whatsapp.py, cli/commands/whatsapp_commands.py] | tested by [tests/unit/test_whatsapp_history_and_download.py]
  Data flow: a media variant of a message → reference() → kept on the record as `attachments` | download: reference → fetch() (mmg.whatsapp.net + directPath) → decrypt() → bytes | a history bundle: the same fetch and decrypt under "Group History" → history_entries() → serialized WebMessageInfo, oldest first
  State/Effects: one HTTPS GET per file; no WhatsApp connection, so neither needs the listener | writes nothing itself
  Integration: the encryption is WhatsApp's media scheme: HKDF-SHA256 over the media key with a per-kind info string, 112 bytes → iv, cipher key, mac key; the file is AES-256-CBC ciphertext followed by the first 10 bytes of HMAC-SHA256(mac key, iv + ciphertext)
  Errors: MediaGone when WhatsApp's servers no longer have the file (404/410); MediaError for anything that does not verify, with which check failed

Why this is ours and not neonize's.  whatsmeow (and so neonize, as of 0.10.0
and whatsmeow's main in November 2026) has the MessageHistoryBundle protobuf
but no media type for it, so it can neither download nor decrypt one. The
info string "Group History" and the zlib-compressed GroupHistory payload come
from oxidezap/whatsapp-rust, which implements the sending side from WhatsApp
Web; the key fixture in the tests is theirs. It has not been checked against a
real bundle. A wrong string fails the MAC check, so it cannot produce garbage.
"""

import base64
import hashlib
import hmac
import zlib
from typing import Optional

MEDIA_HOST = "https://mmg.whatsapp.net"
# The HKDF info string each kind of file is encrypted under.
INFO = {"image": "WhatsApp Image Keys", "sticker": "WhatsApp Image Keys",
        "video": "WhatsApp Video Keys", "audio": "WhatsApp Audio Keys",
        "document": "WhatsApp Document Keys", "history": "Group History"}
# Bounds on what one file may cost. Anyone who can add the account to a group
# can send it a bundle, and it is read inside the listener.
MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_HISTORY_ENTRIES = 5000
_MAC_BYTES = 10


class MediaError(RuntimeError):
    """The file could not be fetched or did not verify."""


class MediaGone(MediaError):
    """WhatsApp's servers no longer hold the file."""


def _b64(value) -> str:
    return base64.b64encode(bytes(value or b"")).decode()


def reference(variant, kind: str) -> Optional[dict]:
    """What a later download needs from a media message, or None without a path."""
    if not getattr(variant, "directPath", "") or not getattr(variant, "mediaKey", b""):
        return None
    ref = {"kind": kind, "direct_path": variant.directPath, "media_key": _b64(variant.mediaKey),
           "file_enc_sha256": _b64(variant.fileEncSHA256), "file_sha256": _b64(variant.fileSHA256),
           "mime": getattr(variant, "mimetype", "") or ""}
    if getattr(variant, "fileName", ""):
        ref["file_name"] = variant.fileName
    return ref


def fetch(ref: dict) -> bytes:
    """The encrypted file from WhatsApp's media servers."""
    import httpx

    response = httpx.get(MEDIA_HOST + ref["direct_path"], timeout=30.0, follow_redirects=False)
    if response.status_code in (404, 410):
        raise MediaGone("WhatsApp no longer has this file: its servers keep media for a limited "
                        "time. Ask the sender to send it again")
    if response.status_code != 200:
        raise MediaError(f"WhatsApp's media server answered {response.status_code}")
    if len(response.content) > MAX_DOWNLOAD:
        raise MediaError(f"the file is over the {MAX_DOWNLOAD // (1024 * 1024)} MB limit")
    return response.content


def media_keys(media_key: bytes, info: str) -> tuple:
    """(iv, cipher key, mac key) for one file."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    expanded = HKDF(algorithm=hashes.SHA256(), length=112, salt=None,
                    info=info.encode()).derive(media_key)
    return expanded[:16], expanded[16:48], expanded[48:80]


def decrypt(blob: bytes, ref: dict) -> bytes:
    """The plaintext of an encrypted WhatsApp file, every hash checked."""
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if ref.get("file_enc_sha256") and hashlib.sha256(blob).digest() != base64.b64decode(ref["file_enc_sha256"]):
        raise MediaError("the downloaded file is not the one the message names (fileEncSha256)")
    iv, cipher_key, mac_key = media_keys(base64.b64decode(ref["media_key"]), INFO[ref["kind"]])
    body, mac = blob[:-_MAC_BYTES], blob[-_MAC_BYTES:]
    if not hmac.compare_digest(hmac.new(mac_key, iv + body, hashlib.sha256).digest()[:_MAC_BYTES], mac):
        raise MediaError(f"the file does not verify as {ref['kind']} (MAC), so it was not opened")
    decryptor = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(body) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    if ref.get("file_sha256") and hashlib.sha256(plain).digest() != base64.b64decode(ref["file_sha256"]):
        raise MediaError("the opened file does not match the message's fileSha256")
    return plain


def history_entries(plain: bytes) -> list:
    """The serialized WebMessageInfo entries of a GroupHistory payload.

    The payload is zlib-compressed `GroupHistory { repeated WebMessageInfo
    messages = 1; … }`. The protobufs neonize ships have no GroupHistory, so
    field 1 is read off the wire by hand; everything else is skipped."""
    inflater = zlib.decompressobj()
    data = inflater.decompress(plain, MAX_HISTORY_BYTES)
    if inflater.unconsumed_tail:
        raise MediaError(f"the history inflates past {MAX_HISTORY_BYTES // (1024 * 1024)} MB; nothing was read")
    entries, at = [], 0
    while at < len(data):
        key, at = _varint(data, at)
        field, wire = key >> 3, key & 7
        if wire == 0:
            _, at = _varint(data, at)
            continue
        if wire != 2:
            raise MediaError(f"the history payload has a wire type {wire} it should not")
        size, at = _varint(data, at)
        if field == 1:
            entries.append(data[at:at + size])
            if len(entries) > MAX_HISTORY_ENTRIES:
                raise MediaError(f"the history has more than {MAX_HISTORY_ENTRIES} messages; nothing was read")
        at += size
    return entries


def _varint(data: bytes, at: int) -> tuple:
    value, shift = 0, 0
    while True:
        if at >= len(data):
            raise MediaError("the history payload ends in the middle of a field")
        byte = data[at]
        value |= (byte & 0x7F) << shift
        at += 1
        if not byte & 0x80:
            return value, at
        shift += 7
