"""Immutable, short-lived row references for one authenticated Google provider account."""

import hashlib
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

LIFETIME_SECONDS = 15 * 60
MAX_LISTINGS = 128
MAX_FILE_BYTES = 256 * 1024


class ListingError(ValueError):
    """The caller must use a full provider ID or obtain a fresh listing."""


def _account(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ListingError('Cannot establish the authenticated account. List again.')
    return hashlib.sha256(value.strip().casefold().encode()).hexdigest()



def _modified(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        # Another writer may have evicted this old listing after glob returned.
        return 0


def save_listing(directory: Path, account: str, family: str, ids: list[str], *, now: float | None = None, provider: str = 'gmail') -> str:
    """Persist IDs only; never cache message bodies, subjects, recipients or tokens."""
    if (provider, family) not in {('gmail','messages'), ('gmail','drafts'), ('gdrive','files')} or len(ids) > 500 or any(not isinstance(i, str) or not i or len(i) > 256 for i in ids):
        raise ListingError('Invalid provider listing. List again.')
    created = time.time() if now is None else now
    token = uuid4().hex
    payload = {'schema_version': 1, 'provider': provider, 'account': _account(account),
               'family': family, 'listing_id': token, 'created_at': created,
               'expires_at': created + LIFETIME_SECONDS, 'ids': ids}
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f'{token}.json'
    # A token is returned only after the complete file is durable. O_EXCL keeps
    # even a UUID collision from replacing a previously published listing.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream)
        stream.flush()
        os.fsync(stream.fileno())
    files = sorted((entry for entry in directory.glob("*.json")
                    if re.fullmatch(r"[a-f0-9]{32}\.json", entry.name)),
                   key=_modified, reverse=True)
    for old in files[MAX_LISTINGS:]:
        old.unlink(missing_ok=True)
    return token


def resolve_reference(directory: Path, value: str, account: str, family: str,
                      listing: str | None = None, *, now: float | None = None, provider: str = 'gmail') -> str:
    """Full IDs bypass disk; numeric references require the exact displayed token."""
    number = value.removeprefix('#')
    if not (number.isascii() and number.isdigit() and len(number) < 5):
        return value
    if not listing:
        raise ListingError('A row number requires --listing ID from its listing, or use the full provider ID.')
    if not re.fullmatch(r'[a-f0-9]{32}', listing):
        raise ListingError('Invalid listing ID. List again with the corresponding provider command.')
    current = time.time() if now is None else now
    try:
        path = directory / f'{listing}.json'
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError
        data = json.loads(raw)
        if (data['schema_version'] != 1 or data['provider'] != provider or
                data['account'] != _account(account) or data['family'] != family or
                data['listing_id'] != listing or
                not data['created_at'] <= current < data['expires_at'] or
                data['expires_at'] - data['created_at'] != LIFETIME_SECONDS):
            raise ValueError
        ids = data['ids']
        if not isinstance(ids, list) or not 1 <= int(number) <= len(ids) <= 500:
            raise ValueError
        result = ids[int(number) - 1]
        if not isinstance(result, str) or not result or len(result) > 256:
            raise ValueError
        return result
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        raise ListingError('Listing unavailable, expired, or for another account. Relist or use the full provider ID.') from None
