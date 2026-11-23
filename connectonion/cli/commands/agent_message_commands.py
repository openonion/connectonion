"""Command help and entry points for native agent text messaging."""

import json
from contextlib import contextmanager

import typer


@contextmanager
def _mailbox(action: str):
    import requests

    from ...inbox.agent_messages import current_mailbox

    try:
        with requests.Session() as session:
            yield current_mailbox(session)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except (requests.RequestException, OSError) as exc:
        typer.echo(f"{action} failed ({type(exc).__name__}). Check the connection and run co agent --help.", err=True)
        raise typer.Exit(1) from exc


def make_agent_message_app(make_app):
    group = make_app(help="Send and receive messages between agents. Start with co agent send or co agent listen.")

    @group.command()
    def send(address: str, text: str):
        """Queue encrypted text for a full 0x agent address, even while it is offline."""
        with _mailbox("Sending") as mailbox:
            message_id = mailbox.send(address, text)
        typer.echo(f"Cloud accepted message {message_id}. The recipient can collect it with co agent listen.")

    @group.command()
    def listen(once: bool = typer.Option(False, "--once", help="Fetch available messages and exit.")):
        """Collect trusted agents' messages into this project's local inbox. Ctrl-C stops."""
        with _mailbox("Listening") as mailbox:
            if not mailbox.inbox.hold_lock():
                typer.echo("A listener is already running here. Run co agent ls to see its messages.", err=True)
                raise typer.Exit(1)
            try:
                if once:
                    _, count = mailbox.poll(0)
                    typer.echo(f"Collected {count} new message(s). Run co agent ls.")
                else:
                    typer.echo(f"Listening as {mailbox.keys['address']}. Run co agent ls in another terminal.")
                    mailbox.listen(
                        lambda count: typer.echo(f"Collected {count} new message(s). Run co agent ls.") if count else None,
                        lambda: typer.echo("Cloud temporarily unavailable. Retrying in 30 seconds.", err=True),
                    )
            except KeyboardInterrupt:
                typer.echo("Listener stopped. Run co agent ls to see received messages.")
            finally:
                mailbox.inbox.release_lock()

    @group.command("ls")
    def ls(as_json: bool = typer.Option(False, "--json", help="Print the messages as a JSON array.")):
        """List local messages awaiting a reply. Start co agent listen to fetch from Cloud."""
        with _mailbox("Listing messages") as mailbox:
            messages = mailbox.inbox.list_messages()
        if as_json:
            typer.echo(json.dumps([message.to_dict() for message in messages]))
            return
        if not messages:
            typer.echo("No pending local messages. Run co agent listen to collect from Cloud.")
            return
        for message in messages:
            typer.echo(f"{message.id}  {message.sender}  {json.dumps(message.text, ensure_ascii=False)}")
        typer.echo(f'Next: co agent reply {messages[0].id} "your reply"')

    @group.command()
    def reply(message_id: str, text: str):
        """Reply to a local message ID from co agent ls, then mark it handled."""
        with _mailbox("Replying") as mailbox:
            sent_id = mailbox.reply(message_id, text)
        typer.echo(f"Cloud accepted reply {sent_id}. Run co agent ls for other pending messages.")

    return group
