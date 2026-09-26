"""The explicit Gmail mailbox leaves and machine-readable usage failures."""

import json
from typing import Optional

import typer
from typer.core import TyperCommand
try:
    from typer import _click as click
except ImportError:
    import click  # Typer versions before the vendored Click runtime

from ...environment import selected_command


def handle_mailbox(*args, **kwargs):
    # Keep --help and unrelated commands free of provider imports.
    from .gmail_mailbox_commands import handle_mailbox as run
    return run(*args, **kwargs)


def usage_error(message: str, command: str, json_output: bool, provider: str = 'gmail') -> None:
    if not json_output:
        raise typer.BadParameter(message)
    print(json.dumps({'schema_version':1, 'provider':provider, 'operation':command,
        'account':None, 'status':'error', 'complete':False, 'data':None,
        'error':{'code':'usage_error', 'message':message},
        'next_command':selected_command(f'co {provider} {command} --help')}))
    raise typer.Exit(2)


class MailboxCommand(TyperCommand):
    provider = 'gmail'

    def make_context(self, info_name, args, parent=None, **extra):
        json_output = '--json' in args
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except click.ClickException:
            if json_output:
                # Do not echo arbitrary argument values or provider material.
                prefix = parent.command_path.split(self.provider, 1)[-1].strip() if parent else ''
                command = f'{prefix} {info_name}'.strip()
                usage_error('Invalid or missing command arguments.', command, True, self.provider)
            raise


class DriveInfoCommand(MailboxCommand):
    provider = 'gdrive'


MESSAGE_ID = '18f2c3b4a5d6e7f8'  # the shape Gmail gives message IDs
ID_HELP = 'Message ID from co gmail inbox, sent or search, or a row number with --listing'
LISTING_HELP = 'Listing ID printed by co gmail inbox, sent or search; needed with a row number'
JSON_HELP = 'Print JSON with full IDs and the account used'
LABEL_HELP = 'Label name as shown in co gmail label list, or its full ID'


def register_mailbox_commands(app: typer.Typer, group_class: type) -> None:
    @app.command('mark', cls=MailboxCommand, epilog=f'Example:  co gmail mark {MESSAGE_ID} --read')
    def mark(email_id: str = typer.Argument(..., help=ID_HELP), read: bool = typer.Option(False, '--read', help='Mark the message read'),
             unread: bool = typer.Option(False, '--unread', help='Mark the message unread'),
             listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
             json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Set read state; choose exactly one of --read and --unread. Changes the message in Gmail."""
        if read == unread:
            usage_error('Choose exactly one of --read and --unread.', 'mark', json_output)
        handle_mailbox('mark.read' if read else 'mark.unread', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('archive', cls=MailboxCommand, epilog=f'Example:  co gmail archive {MESSAGE_ID}')
    def archive(email_id: str = typer.Argument(..., help=ID_HELP),
                listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
                json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Move a message out of your inbox without deleting it; it stays in All Mail. Changes the message in Gmail."""
        handle_mailbox('archive', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('star', cls=MailboxCommand,
                 epilog=f'Example:  co gmail star {MESSAGE_ID}  |  co gmail star {MESSAGE_ID} --remove')
    def star(email_id: str = typer.Argument(..., help=ID_HELP),
             remove: bool = typer.Option(False, '--remove', help='Unstar the message instead'),
             listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
             json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Star a message, or unstar it with --remove. Changes the message in Gmail."""
        handle_mailbox('unstar' if remove else 'star', email_id=email_id, listing=listing, json_output=json_output)

    labels = typer.Typer(cls=group_class,
                         help='List labels (Read-only) and add/remove labels on a message (Changes it).',
                         epilog=f'Example:  co gmail label list  |  co gmail label add {MESSAGE_ID} Receipts')
    app.add_typer(labels, name='label')

    @labels.command('list', cls=MailboxCommand, epilog='Example:  co gmail label list --json')
    def label_list(json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """List full label IDs, names and types. Read-only."""
        handle_mailbox('label.list', json_output=json_output)

    @labels.command('add', cls=MailboxCommand, epilog=f'Example:  co gmail label add {MESSAGE_ID} Receipts')
    def label_add(email_id: str = typer.Argument(..., help=ID_HELP),
                  label: str = typer.Argument(..., help=LABEL_HELP),
                  listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
                  json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Add a label by its exact name or full ID. Changes the message in Gmail."""
        handle_mailbox('label.add', email_id=email_id, label=label, listing=listing, json_output=json_output)

    @labels.command('remove', cls=MailboxCommand, epilog=f'Example:  co gmail label remove {MESSAGE_ID} Receipts')
    def label_remove(email_id: str = typer.Argument(..., help=ID_HELP),
                     label: str = typer.Argument(..., help=LABEL_HELP),
                     listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
                     json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Take one label off a message; its other labels stay. Changes the message in Gmail."""
        handle_mailbox('label.remove', email_id=email_id, label=label, listing=listing, json_output=json_output)

    @app.command('attachments', cls=MailboxCommand, epilog=f'Example:  co gmail attachments {MESSAGE_ID}')
    def attachments(email_id: str = typer.Argument(..., help=ID_HELP),
                    listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
                    json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """List every attachment in a message, including files embedded in the body, with the IDs and sizes co gmail download needs. Read-only."""
        handle_mailbox('attachments', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('download', cls=MailboxCommand,
                 epilog=f'Example:  co gmail download {MESSAGE_ID} --all --to ~/Downloads  |  '
                        f'co gmail download {MESSAGE_ID} --attachment <attachment-id from co gmail attachments> --to .')
    def download(email_id: str = typer.Argument(..., help=ID_HELP), to: str = typer.Option(..., '--to', help='Existing local destination directory'),
                 attachment: Optional[str] = typer.Option(None, '--attachment', help='Full attachment/part ID from attachments'),
                 all_attachments: bool = typer.Option(False, '--all', help='Download every attachment co gmail attachments lists, inline parts included'),
                 listing: Optional[str] = typer.Option(None, '--listing', help=LISTING_HELP),
                 json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Download selected attachments; keep existing files and report partial failures. Writes files to --to; Gmail is unchanged."""
        if bool(attachment) == all_attachments:
            usage_error('Choose exactly one of --attachment ID and --all.', 'download', json_output)
        handle_mailbox('download', email_id=email_id, directory=to, attachment_id=attachment,
                       all_attachments=all_attachments, listing=listing, json_output=json_output)

    @app.command('unanswered', cls=MailboxCommand,
                 epilog='Example:  co gmail unanswered --within-days 7 --exclude-automated')
    def unanswered(within_days: int = typer.Option(30, '--within-days', min=1, max=3650),
                   last: int = typer.Option(20, '--last', '-n', min=1, max=100, help='Maximum threads scanned in one page; filtering may return fewer'),
                   exclude_automated: bool = typer.Option(False, '--exclude-automated', help='Filter Auto-Submitted and bulk/list/junk headers'),
                   cursor: Optional[str] = typer.Option(None, '--cursor', help='Continuation from the same account, days, filter and limit'),
                   json_output: bool = typer.Option(False, '--json', help=JSON_HELP)):
        """Find threads whose latest non-draft message is incoming, regardless of who started them. Read-only."""
        handle_mailbox('unanswered', within_days=within_days, last=last,
                       exclude_automated=exclude_automated, cursor=cursor, json_output=json_output)
