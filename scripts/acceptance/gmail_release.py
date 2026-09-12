"""Opt-in live Gmail/Drive acceptance; touches only this run's synthetic fixtures.

Run with an installed candidate on PYTHONPATH and the explicit consent flag.
One message is sent only to the provider-confirmed account. Two private Drive
fixtures and the sent message move to Trash afterward; no sharing is changed.
Output contains phase names and checks, never addresses, IDs, tokens or content.
"""

import argparse
import base64
from collections import Counter
import contextlib
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


def attachment_hashes(message) -> Counter:
    return Counter(hashlib.sha256(part.get_payload(decode=True)).hexdigest()
                   for part in message.walk() if part.get_filename())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-self-send-and-fixture-writes', action='store_true')
    args = parser.parse_args()
    if not args.allow_self_send_and_fixture_writes:
        parser.error('Explicit consent is required for one self-send and fixture writes.')

    report = {'passed': False, 'checks': [], 'cleanup': [], 'observations': {}}
    phase = 'initialize'
    draft_id = sent_id = None
    drive_ids = []
    gmail_service = drive_service = None
    # Capture provider diagnostics as well as CLI output: the report is safe to
    # retain, while provider resources and the reviewed MIME stay in memory.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaIoBaseUpload
            from connectonion.useful_tools.gmail import Gmail
            from connectonion.useful_tools.gdrive import GDrive
            from connectonion.cli.commands.gmail_draft_review import ATTEMPT_HEADER, prepare_review, send_reviewed

            gmail, drive = Gmail(), GDrive()
            account = gmail.get_account_email()
            assert drive.get_account_email().casefold() == account.casefold()
            gmail._require_draft_write_scope()
            gmail_service, drive_service = gmail._get_service(), drive._get_service()
            run_name = 'ConnectOnion release acceptance ' + uuid.uuid4().hex
            with tempfile.TemporaryDirectory(prefix='co-gmail-acceptance-') as temporary:
                root = Path(temporary).resolve()
                other = root / 'unrelated-directory'
                other.mkdir(mode=0o700)

                def cli(*arguments, error=None, machine=False):
                    child = subprocess.run(
                        [sys.executable, '-m', 'connectonion.cli.main', *arguments],
                        cwd=other, capture_output=True, text=True, timeout=120,
                        env={**os.environ, 'NO_COLOR': '1'},
                    )
                    if machine:
                        data = json.loads(child.stdout)
                        assert data['schema_version'] == 1
                        assert data['account'].casefold() == account.casefold()
                        if error:
                            assert child.returncode == 1 and data['error']['code'] == error
                        else:
                            assert child.returncode == 0 and data['complete']
                        return data['data']
                    assert child.returncode == 0

                phase = 'create_private_fixtures'
                for mime, name in [('text/plain', 'binary.txt'),
                                   ('application/vnd.google-apps.document', 'native')]:
                    data = (run_name + '\nSynthetic fixture only.\n').encode()
                    created = drive_service.files().create(
                        body={'name': run_name + ' ' + name, 'mimeType': mime},
                        media_body=MediaIoBaseUpload(io.BytesIO(data), mimetype='text/plain'),
                        fields='id',
                    ).execute()
                    drive_ids.append(created['id'])
                local = root / 'local.txt'
                local.write_text('Synthetic local attachment.\n')
                replacement = root / 'replacement.txt'
                replacement.write_text('Synthetic replacement attachment.\n')
                draft_id = gmail.create_draft(account, run_name, 'Synthetic release acceptance.\n')['id']
                cli('gmail', 'draft', 'attach', draft_id, str(local))
                cli('gmail', 'draft', 'attach', draft_id, drive_ids[0], '--drive')
                cli('gmail', 'draft', 'attach', draft_id, drive_ids[1], '--drive')
                cli('gmail', 'draft', 'attach', draft_id, drive_ids[0], '--drive', '--link')
                preview = cli('gmail', 'draft', 'preview', draft_id, '--json', machine=True)
                assert len(preview['items']) == 4
                assert {item['source'] for item in preview['items']} == {
                    'local', 'drive_attachment', 'drive_link'}
                assert any(item.get('export_type') for item in preview['items'])
                report['checks'].append('local_binary_native_link_survive_process_restart')

                phase = 'edit_and_review'
                cli('gmail', 'draft', 'replace', draft_id, '1', str(replacement))
                cli('gmail', 'draft', 'remove', draft_id, '2')
                cli('gmail', 'draft', 'attach', draft_id, drive_ids[0], '--drive')
                cli('gmail', 'draft', 'send', draft_id, '--json',
                    machine=True, error='confirmation_required')
                previous = cli('gmail', 'draft', 'review', draft_id, '--json', machine=True)
                # An independent provider update must invalidate the CLI's token.
                _, message = gmail._draft_message(draft_id)
                message.replace_header('Subject', run_name + ' reviewed edit')
                gmail._update_draft(draft_id, message)
                cli('gmail', 'draft', 'send', draft_id, '--confirm', previous['review_token'],
                    '--json', machine=True, error='stale_review')
                reviewed = cli('gmail', 'draft', 'review', draft_id, '--json', machine=True)
                frozen = prepare_review(gmail, draft_id)
                assert frozen.token == reviewed['review_token']
                assert reviewed['to'] == account and not reviewed['cc'] and not reviewed['bcc']
                report['checks'].append('noninteractive_confirmation_and_stale_review_rejected')

                phase = 'send_once_to_same_account'
                sent = cli('gmail', 'draft', 'send', draft_id, '--confirm', frozen.token,
                           '--json', machine=True)
                sent_id = sent['id']
                phase = 'verify_saved_receipt_without_second_send'
                receipt = cli('gmail', 'draft', 'send', draft_id, '--confirm', frozen.token,
                              '--json', machine=True)
                assert receipt['id'] == sent_id and receipt['recovered'] is True
                phase = 'verify_consumed_draft'
                try:
                    gmail_service.users().drafts().get(userId='me', id=draft_id).execute()
                except HttpError as error:
                    assert error.resp.status == 404
                else:
                    raise AssertionError('Sent draft still exists')
                consumed_draft_id, draft_id = draft_id, None
                phase = 'verify_provider_stored_content'
                delivered = gmail_service.users().messages().get(
                    userId='me', id=sent_id, format='raw').execute()
                # Inbox routing is separate from provider storage: account rules
                # can archive a self-send. Do not claim independent SMTP delivery.
                report['observations']['inbox_label_observed'] = 'INBOX' in delivered.get('labelIds', [])
                assert 'SENT' in delivered.get('labelIds', [])
                parsed = BytesParser(policy=policy.SMTP).parsebytes(base64.urlsafe_b64decode(delivered['raw']))
                expected = BytesParser(policy=policy.SMTP).parsebytes(base64.urlsafe_b64decode(frozen.raw))
                assert attachment_hashes(parsed) == attachment_hashes(expected)
                assert parsed.get_body(preferencelist=('plain',)).get_content() == expected.get_body(preferencelist=('plain',)).get_content()
                phase = 'verify_provider_preserved_attempt_marker'
                assert str(parsed[ATTEMPT_HEADER]).strip() == frozen.token
                provider_message_id = str(parsed['Message-ID']).strip()
                report['observations']['message_id_rewritten'] = provider_message_id != frozen.message_id
                report['checks'].append('stored_reviewed_content_draft_consumed_no_duplicate_send')

                phase = 'recover_a_lost_receipt_without_resending'
                recovery_dir = root / 'recovery'
                recovery_dir.mkdir(mode=0o700)
                key = hashlib.sha256(json.dumps([account, consumed_draft_id]).encode()).hexdigest()
                attempt = {'schema_version': 1, 'status': 'submitted', 'token': frozen.token,
                           'message_id': frozen.message_id, 'marker': frozen.token,
                           'submitted_at': int(time.time())}
                (recovery_dir / f'{key}.json').write_text(json.dumps(attempt))
                def must_not_send(*args, **kwargs):
                    raise AssertionError('Recovery must never submit another message')
                gmail._send_draft = must_not_send
                recovered = send_reviewed(gmail, consumed_draft_id, frozen.token, directory=recovery_dir)
                assert recovered == {'id': sent_id, 'recovered': True}
                report['checks'].append('provider_marker_recovers_lost_receipt_without_resending')

                phase = 'search_stored_message'
                result = cli('gmail', 'search', 'rfc822msgid:' + provider_message_id,
                             '--last', '10', '--json', machine=True)
                assert len(result['items']) == 1 and result['items'][0]['id'] == sent_id
                phase = 'read_frozen_listing'
                assert cli('gmail', 'read', '1', '--listing', result['listing_id'],
                           '--json', machine=True)['id'] == sent_id
                labels = [('mark', '--unread', 'UNREAD', True), ('mark', '--read', 'UNREAD', False),
                          ('star', None, 'STARRED', True), ('star', '--remove', 'STARRED', False)]
                for operation, option, label, present in labels:
                    phase = 'mailbox_' + operation + '_' + ('add' if present else 'remove')
                    cli('gmail', operation, sent_id, *([option] if option else []), '--json', machine=True)
                    current = gmail_service.users().messages().get(userId='me', id=sent_id, format='minimal').execute()
                    assert (label in current.get('labelIds', [])) is present
                for operation in ['add', 'remove']:
                    phase = 'important_label_' + operation
                    cli('gmail', 'label', operation, sent_id, 'IMPORTANT', '--json', machine=True)
                    current = gmail_service.users().messages().get(userId='me', id=sent_id, format='minimal').execute()
                    assert ('IMPORTANT' in current.get('labelIds', [])) == (operation == 'add')
                downloads = root / 'downloads'
                downloads.mkdir(mode=0o700)
                paths = set()
                for pass_index in range(2):
                    phase = 'download_attachments_' + str(pass_index + 1)
                    saved = cli('gmail', 'download', sent_id, '--all', '--to', str(downloads), '--json', machine=True)
                    assert Counter(row['sha256'] for row in saved['items']) == attachment_hashes(expected)
                    for row in saved['items']:
                        path = Path(row['path'])
                        assert path not in paths and path.is_relative_to(downloads)
                        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
                        if os.name == 'posix':
                            assert path.stat().st_mode & 0o777 == 0o600
                        paths.add(path)
                phase = 'archive_message'
                cli('gmail', 'archive', sent_id, '--json', machine=True)
                archived = gmail_service.users().messages().get(userId='me', id=sent_id, format='minimal').execute()
                assert 'INBOX' not in archived.get('labelIds', [])
                report['checks'].append('frozen_listing_labels_archive_and_private_collision_safe_downloads')
                report['passed'] = True
        except Exception as error:
            report.update(failed_phase=phase, error_type=type(error).__name__)
        finally:
            # Never delete or search-and-clean resources outside the exact IDs
            # created by this invocation. Leave uncertain sends for inspection.
            cleanup_actions = []
            if draft_id and gmail_service and phase != 'send_once_to_same_account':
                cleanup_actions.append(('draft_deleted', lambda: gmail_service.users().drafts().delete(userId='me', id=draft_id).execute()))
            if sent_id and gmail_service:
                cleanup_actions.append(('message_trashed', lambda: gmail_service.users().messages().trash(userId='me', id=sent_id).execute()))
            for file_id in drive_ids:
                cleanup_actions.append(('drive_fixture_trashed', lambda id=file_id: drive_service.files().update(fileId=id, body={'trashed': True}).execute()))
            for name, action in cleanup_actions:
                try:
                    action()
                    report['cleanup'].append(name)
                except Exception as error:
                    report['passed'] = False
                    report['cleanup'].append(name + '_failed_' + type(error).__name__)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
