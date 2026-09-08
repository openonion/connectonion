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


def usage_error(message: str, command: str, json_output: bool) -> None:
    if not json_output:
        raise typer.BadParameter(message)
    print(json.dumps({'schema_version':1, 'provider':'gmail', 'operation':command,
        'account':None, 'status':'error', 'complete':False, 'data':None,
        'error':{'code':'usage_error', 'message':message},
        'next_command':selected_command(f'co gmail {command} --help')}))
    raise typer.Exit(2)


class MailboxCommand(TyperCommand):
    def make_context(self, info_name, args, parent=None, **extra):
        json_output = '--json' in args
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except click.ClickException:
            if json_output:
                # Do not echo arbitrary argument values or provider material.
                prefix = parent.command_path.split('gmail', 1)[-1].strip() if parent else ''
                command = f'{prefix} {info_name}'.strip()
                usage_error('Invalid or missing command arguments.', command, True)
            raise


def register_mailbox_commands(app: typer.Typer, group_class: type) -> None:
    @app.command('mark', cls=MailboxCommand)
    def mark(email_id: str, read: bool = typer.Option(False, '--read'),
             unread: bool = typer.Option(False, '--unread'),
             listing: Optional[str] = typer.Option(None, '--listing'),
             json_output: bool = typer.Option(False, '--json')):
        """Set read state; choose exactly one of --read and --unread."""
        if read == unread:
            usage_error('Choose exactly one of --read and --unread.', 'mark', json_output)
        handle_mailbox('mark.read' if read else 'mark.unread', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('archive', cls=MailboxCommand)
    def archive(email_id: str, listing: Optional[str] = typer.Option(None, '--listing'),
                json_output: bool = typer.Option(False, '--json')):
        """Remove INBOX from a message without deleting it."""
        handle_mailbox('archive', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('star', cls=MailboxCommand)
    def star(email_id: str, remove: bool = typer.Option(False, '--remove'),
             listing: Optional[str] = typer.Option(None, '--listing'),
             json_output: bool = typer.Option(False, '--json')):
        """Add a star, or remove it with --remove."""
        handle_mailbox('unstar' if remove else 'star', email_id=email_id, listing=listing, json_output=json_output)

    labels = typer.Typer(cls=group_class, help='List labels and add/remove labels on a message.')
    app.add_typer(labels, name='label')

    @labels.command('list', cls=MailboxCommand)
    def label_list(json_output: bool = typer.Option(False, '--json')):
        """List full label IDs, names and types."""
        handle_mailbox('label.list', json_output=json_output)

    @labels.command('add', cls=MailboxCommand)
    def label_add(email_id: str, label: str, listing: Optional[str] = typer.Option(None, '--listing'),
                  json_output: bool = typer.Option(False, '--json')):
        """Add a label by its exact name or full ID."""
        handle_mailbox('label.add', email_id=email_id, label=label, listing=listing, json_output=json_output)

    @labels.command('remove', cls=MailboxCommand)
    def label_remove(email_id: str, label: str, listing: Optional[str] = typer.Option(None, '--listing'),
                     json_output: bool = typer.Option(False, '--json')):
        """Remove a label without changing other labels."""
        handle_mailbox('label.remove', email_id=email_id, label=label, listing=listing, json_output=json_output)

    @app.command('attachments', cls=MailboxCommand)
    def attachments(email_id: str, listing: Optional[str] = typer.Option(None, '--listing'),
                    json_output: bool = typer.Option(False, '--json')):
        """List nested attachments and inline parts with stable IDs and sizes."""
        handle_mailbox('attachments', email_id=email_id, listing=listing, json_output=json_output)

    @app.command('download', cls=MailboxCommand)
    def download(email_id: str, to: str = typer.Option(..., '--to', help='Existing local destination directory'),
                 attachment: Optional[str] = typer.Option(None, '--attachment', help='Full attachment/part ID from attachments'),
                 all_attachments: bool = typer.Option(False, '--all'),
                 listing: Optional[str] = typer.Option(None, '--listing'),
                 json_output: bool = typer.Option(False, '--json')):
        """Download selected attachments; keep existing files and report partial failures."""
        if bool(attachment) == all_attachments:
            usage_error('Choose exactly one of --attachment ID and --all.', 'download', json_output)
        handle_mailbox('download', email_id=email_id, directory=to, attachment_id=attachment,
                       all_attachments=all_attachments, listing=listing, json_output=json_output)

    @app.command('unanswered', cls=MailboxCommand)
    def unanswered(within_days: int = typer.Option(30, '--within-days', min=1, max=3650),
                   last: int = typer.Option(20, '--last', '-n', min=1, max=100, help='Maximum threads scanned in one page; filtering may return fewer'),
                   exclude_automated: bool = typer.Option(False, '--exclude-automated', help='Filter Auto-Submitted and bulk/list/junk headers'),
                   cursor: Optional[str] = typer.Option(None, '--cursor', help='Continuation from the same account, days, filter and limit'),
                   json_output: bool = typer.Option(False, '--json')):
        """Find threads whose latest non-draft message is incoming, regardless of who started them."""
        handle_mailbox('unanswered', within_days=within_days, last=last,
                       exclude_automated=exclude_automated, cursor=cursor, json_output=json_output)
