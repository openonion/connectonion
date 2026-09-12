"""Versioned Gmail mailbox output with no prompts or provider error bodies."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import shlex
import sys

import typer

from ...environment import selected_command
from ...provider_credentials import ProviderCredentialError
from ...credentials import AmbientCredentialError
from ...useful_tools.gmail_mailbox import MailboxError
from .gmail_listings import ListingError, save_listing


def _perform(client, operation: str, args: dict) -> tuple[dict, str]:
    from . import gmail_commands as gm
    if operation in {'inbox', 'sent', 'search', 'unanswered'}:
        if operation == 'unanswered':
            data = client.list_unanswered(**args)
        else:
            query = {'inbox': 'is:unread in:inbox' if args.pop('unread', False) else 'in:inbox',
                     'sent': 'in:sent', 'search': args.pop('query', '')}[operation]
            data = client.message_page(query, **args)
        data['listing_id'] = save_listing(gm.INBOX_CACHE.parent / 'gmail-listings', client.get_account_email(),
                                          'messages', [row['id'] for row in data['items']])
        next_command = f'co gmail read {shlex.quote(data["items"][0]["id"])}' if data['items'] else 'co gmail inbox'
        return data, next_command
    if operation == 'label.list':
        return {'items': client._get_service().users().labels().list(userId='me').execute().get('labels', []),
                'complete': True}, 'co gmail label add --help'
    if operation == 'draft.list':
        data = client.draft_page(**args)
        data['listing_id'] = save_listing(gm.DRAFT_CACHE.parent / 'gmail-listings', client.get_account_email(),
                                         'drafts', [row['id'] for row in data['items']])
        tip = f'co gmail draft preview {shlex.quote(data["items"][0]["id"])}' if data['items'] else 'co gmail draft create --help'
        return data, tip
    reference = args.pop('email_id', None)
    if operation == 'draft.preview':
        id = gm._resolve_draft_id(client, args.pop('draft_id'), args.pop('listing', None))
        return {**client.get_draft(id), 'complete':True}, f'co gmail draft review {shlex.quote(id)} --json'
    if operation in {'draft.review', 'draft.send'}:
        from .gmail_draft_review import prepare_review, send_reviewed, DraftReviewError
        id = gm._resolve_draft_id(client, args.pop('draft_id'), args.pop('listing', None))
        if operation == 'draft.review':
            review = prepare_review(client, id)
            return {**review.manifest, 'complete':True}, f'co gmail draft send {shlex.quote(id)} --confirm {review.token}'
        token = args.pop('confirm', None)
        if not token:
            raise DraftReviewError('confirmation_required', 'JSON send requires --confirm from a current review.', f'co gmail draft review {shlex.quote(id)} --json')
        return {**send_reviewed(client, id, token), 'complete':True}, 'co gmail sent --json'
    id = gm._resolve_email_id(client, reference, args.pop('listing', None))
    tip = f'co gmail read {shlex.quote(id)} --json'
    mutation = operation in {'mark.read','mark.unread','archive','star','unstar','label.add','label.remove'}
    mark_read = args.pop('mark_read', False)
    if mutation or mark_read:
        scopes = client._credentials.scopes
        if scopes and not scopes.intersection({'gmail.modify','https://mail.google.com/'}):
            raise MailboxError('permission_denied', 'Gmail modify permission is required for this action.')
    if operation == 'read':
        data = client.read_message(id)
        if mark_read:
            client.mark_read(id)
        return {**data, 'marked_read':mark_read, 'complete':True}, f'co gmail reply {shlex.quote(id)} <message>'
    if operation == 'attachments':
        return {'id':id, 'items':client.list_attachments(id), 'complete':True}, f'co gmail download {shlex.quote(id)} --all --to <directory>'
    if operation == 'download':
        return {'id':id, **client.download_attachments(id, **args)}, f'co gmail attachments {shlex.quote(id)} --json'
    method = {'mark.read':'mark_read', 'mark.unread':'mark_unread', 'archive':'archive_email',
              'star':'star_email', 'unstar':'unstar_email', 'label.add':'add_label', 'label.remove':'remove_label'}[operation]
    result = getattr(client, method)(id, **args)
    return {'id':id, 'action':operation, 'result':result, 'complete':True}, tip


def handle_mailbox(operation: str, *, json_output: bool = False, **args) -> None:
    """Emit one envelope; partial operations exit 1 and retain per-file results."""
    from googleapiclient.errors import HttpError
    from google.auth.exceptions import GoogleAuthError
    from httplib2 import HttpLib2Error
    from requests import RequestException
    from .gmail_commands import _gmail
    from .gmail_draft_review import DraftReviewError
    from ...useful_tools.gmail_draft_mime import DraftFormatError
    result = {'schema_version':1, 'provider':'gmail', 'operation':operation,
              'account':None, 'status':'error', 'complete':False, 'data':None, 'error':None}
    next_command = 'co gmail inbox'
    try:
        # Existing setup diagnostics are captured so --json stays a single document.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            client = _gmail()
            result['account'] = client.get_account_email()
            data, next_command = _perform(client, operation, args)
        result.update(data=data, complete=data.get('complete', True),
                      status='success' if data.get('complete', True) else 'partial')
    except ProviderCredentialError as error:
        result['error'] = {'code':error.code, 'message':str(error).split('\nNext:',1)[0]}
        next_command = error.next_command
    except AmbientCredentialError:
        result['error'] = {'code':'broker_auth_required', 'message':'OpenOnion authorization is required for Google token refresh.'}
        next_command = 'co auth'
    except MailboxError as error:
        result['error'] = {'code':error.code, 'message':str(error)}
        if error.code in {'permission_denied', 'auth_required'}:
            next_command = 'co auth google'
    except ListingError as error:
        result['error'] = {'code':'invalid_listing', 'message':str(error)}
    except DraftReviewError as error:
        result['error'] = {'code':error.code, 'message':str(error)}
        next_command = error.next_command or 'co gmail draft list'
    except DraftFormatError as error:
        result['error'] = {'code':'invalid_draft', 'message':str(error)}
        next_command = 'co gmail draft list'
    except (HttpError, GoogleAuthError) as error:
        status = getattr(getattr(error, 'resp', None), 'status', None)
        code = {401:'auth_required', 403:'permission_denied', 404:'not_found'}.get(status, 'provider_error')
        result['error'] = {'code':code, 'message':'Gmail request failed; inspect state before retrying a mutation.'}
        if code in {'auth_required', 'permission_denied'}:
            next_command = 'co auth google'
    except (RequestException, HttpLib2Error, OSError):
        result['error'] = {'code':'io_error', 'message':'Gmail connection or local I/O failed; inspect state before retrying.'}
    except typer.Exit:
        result['error'] = {'code':'auth_required', 'message':'Google account setup or required permission is missing.'}
        next_command = 'co auth google'
    except (ValueError, KeyError, TypeError):
        result['error'] = {'code':'invalid_input', 'message':'Invalid input or malformed Gmail response.'}
    result['next_command'] = selected_command(next_command)
    if json_output:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result['data'] if result['data'] is not None else result['error'], ensure_ascii=False, indent=2))
        print(f'Next: {result["next_command"]}', file=sys.stderr)
    if not result['complete']:
        raise typer.Exit(1)
