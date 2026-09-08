"""Explicit provider-backed source records; body URLs alone never create items."""

import base64
import hashlib
import json
from urllib.parse import urlsplit
from uuid import uuid4

from .gmail_draft_mime import DraftFormatError

SOURCE_HEADER = 'X-ConnectOnion-Source'
LINK_HEADER = 'X-ConnectOnion-Drive-Links'


def _encode(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).decode()


def _decode(value: str, limit: int) -> dict:
    try:
        # Header folding adds whitespace around the encoded value.
        value = ''.join(value.split())
        if len(value) > limit:
            raise ValueError
        result = json.loads(base64.b64decode(value, altchars=b'-_', validate=True))
        if not isinstance(result, dict) or result.get('version') != 1:
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError):
        raise DraftFormatError('Managed draft source metadata is invalid; inspect the draft before editing.') from None


def tag_file(part, data: bytes, source: dict | None = None) -> None:
    source = source or {'source':'external'}
    record = {key:source[key] for key in ('source','drive_file_id','link','export_type','original_type') if key in source}
    record.update(version=1, item_id=uuid4().hex, sha256=hashlib.sha256(data).hexdigest())
    if record['source'] not in {'local','external','drive_attachment'}:
        raise DraftFormatError('Unsupported draft attachment source.')
    del part[SOURCE_HEADER]
    part[SOURCE_HEADER] = _encode(record)


def file_source(part) -> dict:
    if SOURCE_HEADER not in part:
        return {'source':'external'}
    record = _decode(str(part[SOURCE_HEADER]), 8192)
    data = part.get_payload(decode=True)
    if data is None:
        data = part.as_bytes()
    if (record.get('source') not in {'local','external','drive_attachment'} or
            record.get('sha256') != hashlib.sha256(data).hexdigest()):
        raise DraftFormatError('Managed attachment bytes changed; replace the item before reviewing.')
    return {key:value for key,value in record.items() if key != 'version'}


def _plain_part(message):
    part = message.get_body(preferencelist=('plain',)) if message.is_multipart() else message
    if part is None or part.get_content_type() != 'text/plain' or part.get_content_disposition() == 'attachment':
        raise DraftFormatError('Managed Drive links require a plain-text body; attach the bytes instead.')
    return part


def read_links(message, *, strict: bool = True) -> list[dict]:
    if LINK_HEADER not in message:
        return []
    record = _decode(str(message[LINK_HEADER]), 65536)
    rows = record.get('items')
    if not isinstance(rows, list) or len(rows) > 100:
        raise DraftFormatError('Managed Drive-link manifest is invalid.')
    body = _plain_part(message).get_content().replace('\r\n', '\n')
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key]
                for key in ('item_id','name','drive_file_id','link','text')):
            raise DraftFormatError('Managed Drive-link record is invalid.')
        if strict and body.count(row['text']) != 1:
            raise DraftFormatError('Managed Drive-link text changed or became ambiguous; remove or replace the item before reviewing.')
    if len({row['item_id'] for row in rows}) != len(rows):
        raise DraftFormatError('Managed Drive-link identifiers are duplicated.')
    return rows


def _write_links(message, rows: list) -> None:
    del message[LINK_HEADER]
    if rows:
        encoded = _encode({'version':1, 'items':rows})
        if len(encoded) > 65536:
            raise DraftFormatError('Managed Drive-link manifest is too large.')
        message[LINK_HEADER] = encoded


def add_link(message, item: dict) -> None:
    url, name, file_id = item['link'], item['name'], item['id']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'drive.google.com','docs.google.com'} or parsed.username or parsed.password:
        raise DraftFormatError('Drive did not return a supported HTTPS file link.')
    if not file_id or any(char in name + url for char in '\r\n\0'):
        raise DraftFormatError('Drive link metadata contains invalid fields.')
    rows = read_links(message)
    if len(rows) >= 100:
        raise DraftFormatError('A draft supports at most 100 managed Drive links.')
    part = _plain_part(message)
    body = part.get_content().replace('\r\n', '\n')
    text = f'{name}: {url}\n'
    if text in body:
        raise DraftFormatError('This exact Drive-link text already exists in the body; it was not added as another managed item.')
    separator = '' if body.endswith('\n\n') else ('\n' if body.endswith('\n') else '\n\n')
    part.set_content(body + separator + text)
    rows.append({'item_id':uuid4().hex, 'source':'drive_link', 'name':name, 'type':item.get('type',''),
                 'size':item.get('raw_size'), 'drive_file_id':file_id, 'link':url, 'text':text,
                 'sharing':'unchanged; recipient access unverified'})
    _write_links(message, rows)


def remove_link(message, index: int) -> None:
    rows = read_links(message, strict=False)
    if not 0 <= index < len(rows):
        raise DraftFormatError('Managed Drive-link number is out of range.')
    row = rows.pop(index)
    part = _plain_part(message)
    body = part.get_content().replace('\r\n', '\n')
    if body.count(row['text']) > 1:
        raise DraftFormatError('Managed link text is ambiguous; edit the duplicate text before removing it.')
    part.set_content(body.replace(row['text'], '', 1))
    _write_links(message, rows)
