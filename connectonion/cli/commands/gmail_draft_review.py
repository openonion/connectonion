"""Operator review of frozen MIME and durable, non-retrying send attempts."""

import base64
from dataclasses import dataclass
from email import policy
from email.utils import getaddresses
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tempfile

from ...environment import global_config_dir
from ...env_file import env_lock

from ...useful_tools.gmail_draft_mime import MIME_LIMIT, ATTACHMENT_LIMIT, validate_message


class DraftReviewError(ValueError):
    """Safe review/recovery guidance without message or provider error bodies."""

    def __init__(self, code: str, message: str, next_command: str | None = None):
        super().__init__(message)
        self.code = code
        self.next_command = next_command


@dataclass(frozen=True)
class DraftReview:
    token: str
    raw: str
    thread_id: str | None
    message_id: str
    manifest: dict


def prepare_review(gmail, draft_id: str) -> DraftReview:
    """Read one provider draft and derive its deterministic review and send bytes."""
    draft, message = gmail._draft_message(draft_id)
    account = gmail.get_account_email()
    thread_id = draft.get('message', {}).get('threadId')
    source = validate_message(gmail, message)
    context = json.dumps([1, account, draft_id, thread_id], separators=(',', ':')).encode()
    token = hashlib.sha256(context + b'\0' + source).hexdigest()
    # This stable attempt ID permits inspection after a lost response. It is not
    # an idempotency promise from Gmail; the local ledger prevents resubmission.
    message_id = f'<co-{token}@connectonion.local>'
    manifest = gmail._draft_dict(draft_id, message)
    from ...useful_tools.gmail_draft_sources import SOURCE_HEADER, LINK_HEADER
    for part in message.walk():
        del part[SOURCE_HEADER]
        del part[LINK_HEADER]
    del message['Message-ID']
    message['Message-ID'] = message_id
    raw = validate_message(gmail, message)
    recipients = getaddresses(message.get_all('To', []) + message.get_all('Cc', []) + message.get_all('Bcc', []))
    if not recipients or any(not address or '@' not in address for _,address in recipients):
        raise DraftReviewError('invalid_recipients', 'Draft recipients are missing or invalid; edit and review again.')
    body_parts = [(part.get_content_type(), part.get_content()) for part in message.walk()
                  if part.get_content_maintype() == 'text' and not part.get_filename()]
    names = [item['name'] for item in manifest['items']]
    warnings = ['Duplicate attachment display names.'] if len(names) != len(set(names)) else []
    if any(item.get('source') == 'drive_link' for item in manifest['items']):
        warnings.append('Drive link sharing is unchanged; recipient access has not been verified.')
    if any(item.get('size') is None for item in manifest['items']):
        warnings.append('Some Drive item sizes are unknown; links contribute no MIME file bytes.')
    if any(item.get('export_type') for item in manifest['items']):
        warnings.append('Google-native files are attached as the export formats shown in the manifest.')
    manifest.update(account=account, **{'from':str(message.get('From', account))},
        thread_id=thread_id, message_id=message_id, review_token=token,
        attachment_limit=ATTACHMENT_LIMIT, mime_size=len(raw), mime_limit=MIME_LIMIT,
        encoded_size=len(base64.urlsafe_b64encode(raw)),
        body_sha256=hashlib.sha256(json.dumps(body_parts, ensure_ascii=False).encode()).hexdigest(),
        warnings=warnings)
    return DraftReview(token, base64.urlsafe_b64encode(raw).decode(), thread_id, message_id, manifest)


def _write_attempt(path: Path, data: dict) -> None:
    fd, name = tempfile.mkstemp(prefix='.send-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _read_attempt(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError
        data = json.loads(raw)
        if (data['schema_version'] != 1 or data['status'] not in {'submitted','sent','rejected'} or
                not re.fullmatch(r'[a-f0-9]{64}', data['token'])):
            raise ValueError
        if data['status'] == 'sent' and (not isinstance(data.get('sent_id'), str) or not data['sent_id']):
            raise ValueError
        return data
    except (ValueError, TypeError, KeyError):
        raise DraftReviewError('invalid_send_record', 'Saved send outcome is unreadable; inspect sent mail before retrying.', 'co gmail sent --json') from None


def _recover(gmail, attempt: dict, path: Path, token: str) -> dict | None:
    if attempt['status'] == 'rejected':
        return None
    if attempt['status'] == 'submitted':
        message_id = attempt.get('message_id', '')
        if not re.fullmatch(r'<co-[a-f0-9]{64}@connectonion\.local>', message_id):
            raise DraftReviewError('invalid_send_record', 'Saved send identity is invalid; inspect sent mail.', 'co gmail sent --json')
        query = f'in:sent rfc822msgid:{message_id}'
        response = gmail._get_service().users().messages().list(userId='me', q=query, maxResults=2).execute()
        found = response.get('messages', [])
        if len(found) == 1:
            attempt.update(status='sent', sent_id=found[0]['id'])
            _write_attempt(path, attempt)
        else:
            import shlex
            raise DraftReviewError('delivery_uncertain', 'Delivery remains uncertain; no second send was attempted.',
                                   f'co gmail search {shlex.quote(query)} --json')
    if attempt['token'] != token:
        raise DraftReviewError('already_sent', 'This draft already has a sent receipt for another review; inspect sent mail.', 'co gmail sent --json')
    return {'id':attempt['sent_id'], 'recovered':True}


def send_reviewed(gmail, draft_id: str, token: str, *, directory: Path | None = None) -> dict:
    """Recheck review, freeze raw MIME, and submit at most once per send attempt."""
    from googleapiclient.errors import HttpError
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        raise DraftReviewError('invalid_review', 'Invalid review token; run draft review again.', f'co gmail draft review {shlex.quote(draft_id)} --json')
    account = gmail.get_account_email()
    directory = directory or global_config_dir() / 'gmail-send-attempts'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(json.dumps([account, draft_id]).encode()).hexdigest()
    path = directory / f'{key}.json'
    with env_lock(path):
        attempt = _read_attempt(path)
        if attempt:
            recovered = _recover(gmail, attempt, path, token)
            if recovered:
                return recovered
        review = prepare_review(gmail, draft_id)
        if review.token != token:
            raise DraftReviewError('stale_review', 'Draft changed since review; review the current content before sending.', f'co gmail draft review {shlex.quote(draft_id)} --json')
        gmail._require_draft_write_scope()
        attempt = {'schema_version':1, 'status':'submitted', 'token':token, 'message_id':review.message_id}
        _write_attempt(path, attempt)
        try:
            result = gmail._send_draft(draft_id, raw=review.raw, thread_id=review.thread_id)
            if not isinstance(result.get('id'), str) or not result['id']:
                raise ValueError
        except HttpError as error:
            status = getattr(error.resp, 'status', 0)
            if 400 <= status < 500 and status != 408:
                attempt['status'] = 'rejected'
                _write_attempt(path, attempt)
                raise DraftReviewError('send_rejected', f'Gmail rejected this send request (HTTP {status}); inspect draft and sent state before retrying.',
                    'co auth google' if status in {401,403} else 'co gmail draft list') from None
            raise DraftReviewError('delivery_uncertain', 'Delivery is uncertain; inspect sent mail before any further send.', 'co gmail sent --json') from None
        except Exception:
            # Keep the submitted marker even when the response or receipt write
            # is lost. No exception from the provider may authorize a retry.
            raise DraftReviewError('delivery_uncertain', 'Delivery is uncertain; inspect sent mail before any further send.', 'co gmail sent --json') from None
        attempt.update(status='sent', sent_id=result['id'])
        _write_attempt(path, attempt)
        return result
