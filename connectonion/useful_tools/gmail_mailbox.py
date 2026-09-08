"""Gmail mailbox pages, exact reply debt, and bounded incoming attachments."""

import base64
import binascii
from email.utils import parseaddr
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import quote
from uuid import uuid4

import requests
from ..provider_credentials import ProviderCredentialError

ATTACHMENT_LIMIT = 25_000_000
DOWNLOAD_LIMIT = 100_000_000
RESPONSE_LIMIT = 40_000_000
MAX_ATTACHMENTS = 100


class MailboxError(ValueError):
    """An operational failure safe to include in machine output."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _headers(message: dict) -> dict:
    return {item['name'].casefold(): item['value']
            for item in message.get('payload', {}).get('headers', [])}


def _summary(message: dict) -> dict:
    headers = _headers(message)
    return {'id': message['id'], 'thread_id': message.get('threadId'),
            'from': headers.get('from', ''), 'subject': headers.get('subject', ''),
            'date': headers.get('date', ''), 'snippet': message.get('snippet', ''),
            'unread': 'UNREAD' in message.get('labelIds', [])}


def _cursor_context(account: str, family: str, query: str, last: int) -> dict:
    return {'version': 1, 'account': hashlib.sha256(account.encode()).hexdigest(),
            'family': family, 'query': query, 'limit': last}


def _decode_cursor(cursor: str | None, context: dict) -> str | None:
    if not cursor:
        return None
    try:
        if len(cursor) > 16384:
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if (data['context'] != context or not time.time() < data['expires_at'] <= time.time() + 901
                or not isinstance(data['token'], str) or not data['token']):
            raise ValueError
        return data['token']
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError):
        raise MailboxError('invalid_cursor', 'Invalid, expired or mismatched Gmail cursor; repeat the original listing.') from None


def _page(items: list, response: dict, context: dict) -> dict:
    token = response.get('nextPageToken')
    cursor = base64.urlsafe_b64encode(json.dumps({'context': context, 'token': token,
        'expires_at': time.time() + 900}).encode()).decode() if token else None
    return {'items': items, 'next_cursor': cursor, 'truncated': bool(token),
            'total_estimate': response.get('resultSizeEstimate'), 'complete': True}


def _attachment_parts(payload: dict) -> list[dict]:
    stack, result, visited = [(payload, '0', 0)], [], 0
    while stack:
        part, location, depth = stack.pop()
        visited += 1
        if depth > 30 or visited > 1000:
            raise MailboxError('mime_limit', 'Message exceeds the supported MIME nesting or part count.')
        headers = {h['name'].casefold(): h['value'] for h in part.get('headers', [])}
        disposition = headers.get('content-disposition', '').split(';', 1)[0].strip().casefold()
        filename = part.get('filename', '')
        body = part.get('body', {})
        container_only = bool(part.get('parts')) and 'data' not in body and not body.get('attachmentId')
        if (filename or disposition in {'inline', 'attachment'}) and not container_only:
            result.append({'id': body.get('attachmentId') or f"part:{part.get('partId') or location}",
                'filename': filename, 'mime_type': part.get('mimeType', 'application/octet-stream'),
                'size': body.get('size', 0), 'inline': disposition == 'inline', '_body': body})
        stack.extend((child, f'{location}.{i}', depth + 1)
                     for i, child in reversed(list(enumerate(part.get('parts', [])))))
    if len(result) > MAX_ATTACHMENTS or len({row['id'] for row in result}) != len(result):
        raise MailboxError('attachment_limit', 'Too many attachments or duplicate provider part identifiers.')
    return result


def _filename(value: str) -> str:
    name = value.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', '_', name).strip(' .')
    if not name or name.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}:
        name = 'attachment'
    return name[:180]


def _save_unique(directory: Path, filename: str, data: bytes) -> Path:
    """Publish a complete private file atomically without replacing any entry."""
    descriptor = None
    if os.open in os.supports_dir_fd and os.link in os.supports_dir_fd:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0))
    def at(name):
        return name if descriptor is not None else directory / name
    kwargs = {'dir_fd': descriptor} if descriptor is not None else {}
    temporary = f'.co-gmail-{uuid4().hex}.tmp'
    try:
        with os.fdopen(os.open(at(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, **kwargs), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        name = _filename(filename)
        for suffix in range(10000):
            candidate = name if not suffix else f'{Path(name).stem} ({suffix}){Path(name).suffix}'
            try:
                link_args = {'src_dir_fd': descriptor, 'dst_dir_fd': descriptor} if descriptor is not None else {}
                os.link(at(temporary), at(candidate), **link_args)
                return directory / candidate
            except FileExistsError:
                continue
        raise MailboxError('name_conflict', 'No unused attachment filename is available.')
    finally:
        try:
            os.unlink(at(temporary), **kwargs)
        except FileNotFoundError:
            # Creation can fail before a temporary entry exists.
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
        if descriptor is not None:
            os.close(descriptor)


class GmailMailbox:
    """Provider methods shared by Gmail's SDK and machine-readable CLI."""

    def _mailbox_get(self, path: str, *, params: dict | None = None) -> dict:
        # Reuse the bound record and broker refresh; never load a second account.
        self._get_service()
        for attempt in range(2):
            with requests.get(f'https://gmail.googleapis.com/gmail/v1/users/me/{path}',
                    params=params, headers={'Authorization': f'Bearer {self._credentials.get("ACCESS_TOKEN")}'},
                    timeout=(5, 30), stream=True, allow_redirects=False) as response:
                if response.status_code == 401 and attempt == 0:
                    self._refresh_via_backend(None)
                    continue
                if response.status_code != 200:
                    code = {401:'auth_required', 403:'permission_denied', 404:'not_found'}.get(response.status_code, 'provider_error')
                    raise MailboxError(code, f'Gmail read failed (HTTP {response.status_code}).')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > RESPONSE_LIMIT:
                        raise MailboxError('response_too_large', 'Gmail response exceeds the 40 MB read limit.')
                    chunks.append(chunk)
                try:
                    data = json.loads(b''.join(chunks))
                except (ValueError, UnicodeError):
                    raise MailboxError('invalid_response', 'Gmail returned an invalid JSON response.') from None
                if not isinstance(data, dict):
                    raise MailboxError('invalid_response', 'Gmail returned an invalid response shape.')
                return data
        raise MailboxError('auth_required', 'Gmail authorization failed after refresh.')

    def message_page(self, query: str, last: int = 10, cursor: str | None = None) -> dict:
        """Fetch one page; estimates are not exact counts or immutable snapshots."""
        if not 1 <= last <= 500:
            raise MailboxError('invalid_limit', 'Message page size must be between 1 and 500.')
        context = _cursor_context(self.get_account_email(), 'messages', query, last)
        token = _decode_cursor(cursor, context)
        response = self._mailbox_get('messages', params={'q': query, 'maxResults': last, 'pageToken': token})
        items = [_summary(self._mailbox_get(f'messages/{quote(row["id"], safe="")}', params={'format':'metadata'}))
                 for row in response.get('messages', [])]
        return _page(items, response, context)

    def read_message(self, email_id: str) -> dict:
        """Read full IDs, headers and body without changing labels."""
        message = self._mailbox_get(f'messages/{quote(email_id, safe="")}', params={'format':'full'})
        return {**_summary(message), 'headers': _headers(message), 'labels': message.get('labelIds', []),
                'body': self._extract_body(message.get('payload', {})), 'body_truncated': False}

    def draft_page(self, last: int = 20, cursor: str | None = None) -> dict:
        """Fetch one draft page with full provider IDs and continuation context."""
        if not 1 <= last <= 500:
            raise MailboxError('invalid_limit', 'Draft page size must be between 1 and 500.')
        context = _cursor_context(self.get_account_email(), 'drafts', '', last)
        response = self._mailbox_get('drafts', params={'maxResults': last, 'pageToken': _decode_cursor(cursor, context)})
        return _page([self.get_draft(row['id']) for row in response.get('drafts', [])], response, context)

    def list_unanswered(self, within_days: int = 30, last: int = 20,
                        exclude_automated: bool = False, cursor: str | None = None) -> dict:
        """Latest non-draft incoming message, irrespective of thread origin."""
        if not 1 <= within_days <= 3650 or not 1 <= last <= 100:
            raise MailboxError('invalid_limit', 'Use 1–3650 days and 1–100 threads per unanswered page.')
        account = self.get_account_email()
        query = f'newer_than:{within_days}d -in:trash -in:spam'
        context = _cursor_context(account, 'unanswered', f'{query};automated={exclude_automated}', last)
        response = self._mailbox_get('threads', params={'q': query, 'maxResults': last, 'pageToken': _decode_cursor(cursor, context)})
        items = []
        for row in response.get('threads', []):
            thread = self._mailbox_get(f'threads/{quote(row["id"], safe="")}', params={'format':'metadata'})
            messages = [m for m in thread.get('messages', []) if 'DRAFT' not in m.get('labelIds', [])]
            if not messages:
                continue
            latest = max(messages, key=lambda m: int(m.get('internalDate', 0)))
            if int(latest.get('internalDate', 0)) < (time.time() - within_days * 86400) * 1000:
                continue
            headers = _headers(latest)
            sender = parseaddr(headers.get('from', ''))[1].strip().casefold()
            if not sender or sender == account or 'SENT' in latest.get('labelIds', []):
                continue
            automated = headers.get('auto-submitted', 'no').casefold() != 'no' or headers.get('precedence', '').casefold() in {'bulk','list','junk'}
            if exclude_automated and automated:
                continue
            items.append({**_summary(latest), 'automated': automated, 'messages_in_thread': len(messages)})
        page = _page(items, response, context)
        # Gmail estimates candidate threads, not threads that survived filtering.
        page['candidate_threads_estimate'] = page.pop('total_estimate')
        page['scanned_threads'] = len(response.get('threads', []))
        page['filters'] = {'within_days': within_days, 'exclude_automated': exclude_automated}
        return page

    def list_attachments(self, email_id: str) -> list[dict]:
        """Include nested named attachments and explicitly inline MIME parts."""
        message = self._mailbox_get(f'messages/{quote(email_id, safe="")}', params={'format':'full'})
        return [{k:v for k,v in row.items() if k != '_body'} for row in _attachment_parts(message.get('payload', {}))]

    def download_attachments(self, email_id: str, directory: str | Path, *,
                             attachment_id: str | None = None, all_attachments: bool = False) -> dict:
        """Save selected attachments; retain successful files on partial failure."""
        if bool(attachment_id) == all_attachments:
            raise MailboxError('invalid_selection', 'Choose exactly one attachment ID or all attachments.')
        destination = Path(directory).expanduser().resolve(strict=True)
        if not destination.is_dir():
            raise MailboxError('invalid_destination', 'Download destination must be an existing directory.')
        message = self._mailbox_get(f'messages/{quote(email_id, safe="")}', params={'format':'full'})
        rows = _attachment_parts(message.get('payload', {}))
        selected = rows if all_attachments else [row for row in rows if row['id'] == attachment_id]
        if attachment_id and not selected:
            raise MailboxError('attachment_not_found', 'Attachment ID is not present in this message.')
        results, consumed = [], 0
        for row in selected:
            result = {'id': row['id'], 'filename': row['filename']}
            try:
                body = row['_body']
                size = body.get('size', 0)
                if not isinstance(size, int) or size < 0 or size > ATTACHMENT_LIMIT or consumed + size > DOWNLOAD_LIMIT:
                    raise MailboxError('attachment_too_large', 'Attachment exceeds the 25 MB file or 100 MB operation limit.')
                if body.get('attachmentId'):
                    body = self._mailbox_get(f'messages/{quote(email_id, safe="")}/attachments/{quote(body["attachmentId"], safe="")}')
                encoded = body.get('data', '')
                remaining = min(ATTACHMENT_LIMIT, DOWNLOAD_LIMIT - consumed)
                if not isinstance(encoded, str) or len(encoded) > (remaining + 2) // 3 * 4:
                    raise MailboxError('attachment_too_large', 'Encoded attachment exceeds the file limit.')
                try:
                    data = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
                except (ValueError, binascii.Error):
                    raise MailboxError('invalid_attachment', 'Attachment contains invalid base64 data.') from None
                if len(data) > remaining:
                    raise MailboxError('attachment_too_large', 'Decoded attachment exceeds the remaining operation limit.')
                consumed += len(data)
                if len(data) != size or body.get('size', size) != size:
                    raise MailboxError('size_mismatch', 'Attachment bytes do not match the provider size.')
                if consumed > DOWNLOAD_LIMIT:
                    raise MailboxError('attachment_too_large', 'Download exceeds the 100 MB operation limit.')
                path = _save_unique(destination, row['filename'], data)
                result.update(status='saved', path=str(path), size=len(data), sha256=hashlib.sha256(data).hexdigest())
            except MailboxError as error:
                result.update(status='failed', error={'code':error.code, 'message':str(error)})
            except ProviderCredentialError as error:
                result.update(status='failed', error={'code':error.code, 'message':'Google authorization failed during attachment download.'})
            except (OSError, requests.RequestException):
                result.update(status='failed', error={'code':'download_failed', 'message':'Attachment network or local file operation failed.'})
            results.append(result)
        return {'items': results, 'complete': all(row['status'] == 'saved' for row in results), 'decoded_bytes': consumed}

    def unstar_email(self, email_id: str) -> str:
        """Remove a star without affecting any other message label."""
        self._get_service().users().messages().modify(userId='me', id=email_id, body={'removeLabelIds':['STARRED']}).execute()
        return f'Unstarred email: {email_id}'

    def remove_label(self, email_id: str, label: str) -> str:
        """Remove the exact named label or full label ID."""
        labels = self._get_service().users().labels().list(userId='me').execute().get('labels', [])
        label_id = next((row['id'] for row in labels if row['name'].casefold() == label.casefold()), label)
        self._get_service().users().messages().modify(userId='me', id=email_id, body={'removeLabelIds':[label_id]}).execute()
        return f'Removed label from email: {email_id}'
