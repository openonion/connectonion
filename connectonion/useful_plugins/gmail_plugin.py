"""
Gmail plugin - Approval and CRM sync for Gmail operations.

Usage:
    from connectonion import Agent, Gmail
    from connectonion.useful_plugins import gmail_plugin

    gmail = Gmail()
    agent = Agent("assistant", tools=[gmail], plugins=[gmail_plugin])
"""

from datetime import datetime
from typing import TYPE_CHECKING
from ..events import before_each_tool, after_each_tool
from ..tui import pick
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from ..agent import Agent

_console = Console()

# Gmail class method names that send emails
SEND_METHODS = ('send', 'reply')


@before_each_tool
def check_email_approval(agent: 'Agent') -> None:
    """Ask user approval before sending emails via Gmail.

    Raises:
        ValueError: If user rejects the email
    """
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name']
    if tool_name not in SEND_METHODS:
        return

    args = pending['arguments']

    # Skip if all emails auto-approved
    if agent.current_session.get('gmail_approve_all', False):
        return

    preview = Text()

    if tool_name == 'send':
        to = args.get('to', '')
        subject = args.get('subject', '')
        body = args.get('body', '')
        cc = args.get('cc', '')
        bcc = args.get('bcc', '')

        # Skip if this recipient was auto-approved
        approved_recipients = agent.current_session.get('gmail_approved_recipients', set())
        if to in approved_recipients:
            return

        preview.append("To: ", style="bold cyan")
        preview.append(f"{to}\n")
        if cc:
            preview.append("CC: ", style="bold cyan")
            preview.append(f"{cc}\n")
        if bcc:
            preview.append("BCC: ", style="bold cyan")
            preview.append(f"{bcc}\n")
        preview.append("Subject: ", style="bold cyan")
        preview.append(f"{subject}\n\n")
        body_preview = body[:500] + "..." if len(body) > 500 else body
        preview.append(body_preview)

        action = "Email"
        recipient_key = to

    elif tool_name == 'reply':
        email_id = args.get('email_id', '')
        body = args.get('body', '')

        # Skip if replies auto-approved
        if agent.current_session.get('gmail_approve_replies', False):
            return

        preview.append("Reply to thread: ", style="bold cyan")
        preview.append(f"{email_id}\n\n")
        body_preview = body[:500] + "..." if len(body) > 500 else body
        preview.append(body_preview)

        action = "Reply"
        recipient_key = None

    _console.print()
    _console.print(Panel(preview, title=f"[yellow]{action} to Send[/yellow]", border_style="yellow"))

    options = ["Yes, send it"]
    if tool_name == 'send' and recipient_key:
        options.append(f"Auto approve emails to '{recipient_key}'")
    if tool_name == 'reply':
        options.append("Auto approve all replies this session")
    options.append("Auto approve all emails this session")

    choice = pick(f"Send this {action.lower()}?", options, other=True, console=_console)

    if choice == "Yes, send it":
        return
    if choice.startswith("Auto approve emails to"):
        if 'gmail_approved_recipients' not in agent.current_session:
            agent.current_session['gmail_approved_recipients'] = set()
        agent.current_session['gmail_approved_recipients'].add(recipient_key)
        return
    if choice == "Auto approve all replies this session":
        agent.current_session['gmail_approve_replies'] = True
        return
    if choice == "Auto approve all emails this session":
        agent.current_session['gmail_approve_all'] = True
        return
    # User typed custom feedback via "Other"
    raise ValueError(f"User feedback: {choice}")


@after_each_tool
def sync_crm_after_send(agent: 'Agent') -> None:
    """Update CRM data after each email send - last_contact, clear next_contact_date."""
    trace = agent.current_session['trace'][-1]
    if trace['type'] != 'tool_execution':
        return
    if trace['tool_name'] not in SEND_METHODS:
        return
    if trace['status'] != 'success':
        return

    to = trace['arguments'].get('to', '')
    if not to:
        return

    # Access Gmail instance via agent.tools.gmail
    gmail = agent.tools.gmail
    today = datetime.now().strftime('%Y-%m-%d')
    result = gmail.update_contact(to, last_contact=today, next_contact_date='')

    if 'Updated' in result:
        _console.print(f"[dim]CRM updated: {to}[/dim]")


# Bundle as plugin
gmail_plugin = [
    check_email_approval,
    sync_crm_after_send,
]
