"""Recover a cited original using the same mail clients as co outlook/co gmail."""

from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error
from httpx import RequestError

from ..provider_credentials import ProviderCredentialError
from . import service
from .files import RemError
from .mail_archive import mail_metadata, retain_message


def _metadata(client, provider, identity):
    """An unindexed citation still carries its provider message ID; read its headers directly."""
    if provider == 'gmail':
        message = client._get_service().users().messages().get(
            userId='me', id=identity, format='metadata',
            metadataHeaders=['From', 'To', 'Cc', 'Subject', 'Date', 'Reply-To']).execute(num_retries=3)
        headers = {h['name'].casefold(): h['value'] for h in message['payload']['headers']}
        return {'id': identity, 'thread': message.get('threadId', ''),
                **{key: headers.get(header, '') for key, header in (
                    ('from', 'from'), ('to', 'to'), ('cc', 'cc'), ('date', 'date'),
                    ('subject', 'subject'), ('reply_to', 'reply-to'))}}
    message = client._request('GET', f'/me/messages/{identity}', params={
        '$select': 'id,conversationId,from,toRecipients,ccRecipients,replyTo,subject,receivedDateTime'},
        headers={'Prefer': 'IdType="ImmutableId"'})
    address = lambda value: value.get('emailAddress', {}).get('address', '')
    return {'id': identity, 'thread': message.get('conversationId', ''),
            'from': address(message.get('from', {})), 'to': [address(v) for v in message.get('toRecipients', [])],
            'cc': [address(v) for v in message.get('ccRecipients', [])],
            'reply_to': address(next(iter(message.get('replyTo', [])), {})),
            'subject': message.get('subject', ''), 'date': message.get('receivedDateTime', '')}


def _fetch(root, source, metadata):
    provider, _, identity = source.partition(':')
    subscription = service.subscriptions(root).get(provider, {})
    if not subscription.get('enabled') or not subscription.get('consented') or subscription.get('unsubscribed'):
        return f'{provider.title()} read consent is not active for this mailbox.'
    # Credential expiry, network failures and deleted messages are expected per-item failures.
    try:
        client = _client(provider)
        row = metadata.get((provider, identity)) or _metadata(client, provider, identity)
        body = client.get_email_body(identity)
    except RemError as error:
        return str(error)
    except (OSError, ProviderCredentialError, RequestError, HttpError, GoogleAuthError, HttpLib2Error) as error:
        return service._collection_failure(provider, error)['error']
    if not isinstance(body, str) or not body.strip():
        return f'{provider.title()} returned no message body.'
    retain_message(root, provider, row, body, fetched_at=service.now().isoformat(), lock_held=True,
                   input_scope='Cited original fetched during nightly preparation; not initial-window coverage.')
    return ''


def _client(provider):
    # Both existing clients use ValueError for missing OAuth scopes at construction.
    # Translate only that boundary; malformed provider data must still fail visibly.
    try:
        return service.mail_client(provider)
    except ValueError as error:
        raise RemError(f'{provider.title()} mailbox configuration no longer permits reading.') from error


def fetch_missing(root, rows, *, fetches=None):
    """Read each missing original once per round; the caller reclassifies after indexing it."""
    fetches = {} if fetches is None else fetches
    metadata = {(row['source'], row['id']): row for row in mail_metadata(root)}
    errors = {}
    for row in rows:
        reply = row['reply']
        if reply['state'] != 'unarchived':
            continue
        source = reply['source']
        if source not in fetches:
            fetches[source] = _fetch(root, source, metadata)
        if fetches[source]:
            errors[source] = fetches[source]
    return errors
