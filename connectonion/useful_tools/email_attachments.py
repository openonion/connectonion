"""List, send and download mailbox files without exposing credentials or overwriting files."""

import base64
import hashlib
import mimetypes
import os
import re
from pathlib import Path

import requests

from ..backend import backend_url
from ..credentials import require_ambient_api_key

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def encode_attachments(paths):
    files, total = [], 0
    if len(paths) > 100:
        raise ValueError("At most 100 attachments are allowed")
    for path in paths:
        source = Path(path).expanduser()
        with source.open("rb") as stream:
            data = stream.read(MAX_ATTACHMENT_BYTES - total + 1)
        total += len(data)
        if total > MAX_ATTACHMENT_BYTES:
            raise ValueError("Attachments exceed 20 MiB total")
        files.append({"filename": source.name,
                      "content_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                      "content": base64.b64encode(data).decode("ascii")})
    return files


def _mail_path(email_id, sent=False):
    if isinstance(email_id, bool) or not str(email_id).isdigit() or int(email_id) < 1:
        raise ValueError("email_id must be a positive mailbox ID")
    return f"/api/v1/email/{'sent' if sent else 'received'}/{int(email_id)}"


def _get(path):
    response = requests.get(backend_url() + path,
                            headers={"Authorization": f"Bearer {require_ambient_api_key()}"},
                            timeout=60)
    response.raise_for_status()
    return response


def get_email_attachments(email_id: str, sent: bool = False) -> list:
    """List attachment IDs, filenames, types, sizes and checksums; leave read state unchanged."""
    return _get(_mail_path(email_id, sent) + "/attachments").json()["attachments"]


def download_email_attachment(email_id: str, attachment_id: int, output_dir: str = ".",
                              sent: bool = False) -> dict:
    """Download one file, verify SHA256 and refuse to overwrite an existing path."""
    files = get_email_attachments(email_id, sent)
    file = next((f for f in files if str(f["id"]) == str(attachment_id)), None)
    if file is None:
        raise ValueError("Attachment ID is not in this email")
    response = _get(_mail_path(email_id, sent) + f"/attachments/{int(file['id'])}")
    data = response.content
    if len(data) != file["size"] or hashlib.sha256(data).hexdigest() != file["sha256"]:
        raise ValueError("Attachment size or SHA256 verification failed")
    filename = re.split(r"[/\\]", file["filename"])[-1]
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', "_", filename).rstrip(" .")
    if filename.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        filename = "_" + filename
    if filename in ("", ".", "..") or any(ord(c) < 32 for c in filename):
        filename = f"attachment-{file['id']}"
    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / filename
    # O_EXCL also refuses a symlink pointing outside the chosen directory.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    return {**file, "path": str(target.resolve())}


def download_raw_email(email_id: str, output: str) -> str:
    """Save the original MIME email, including attachments, to a new .eml file."""
    response = _get(_mail_path(email_id) + "/raw")
    fd = os.open(Path(output).expanduser(), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(response.content)
    return str(Path(output).expanduser().resolve())


def read_email_attachment(email_id: str, attachment_id: int, output_dir: str = ".",
                          sent: bool = False) -> dict:
    """Download and extract PDF, Word, spreadsheet or text content.

    The original file is retained. Image-only PDFs need OCR and unsupported or
    unreadable files return readable=False rather than an invented empty order.
    """
    from ..rem.attachments import extract_text
    saved = download_email_attachment(email_id, attachment_id, output_dir, sent)
    text = extract_text(Path(saved["path"]), limit=100000)
    unreadable = (not text or text.startswith(("[could not read", "[XLSX not read:", f"[{Path(saved['path']).name}:"))
                  or "more characters not shown]" in text)
    return {**saved, "text": text, "readable": not unreadable,
            **({"error": text or "No extractable text; a scanned PDF or image may need OCR"} if unreadable else {})}
