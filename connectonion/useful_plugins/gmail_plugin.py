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
from ..events import before_tool, after_tool
from ..useful_tools.terminal import pick
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from ..agent import Agent

_console = Console()

# Gmail class method names that send emails
SEND_METHODS = ('send', 'reply')


def _get_gmail_instance(agent: 'Agent'):
    """Get Gmail instance from agent's tools."""
    from ..useful_tools.gmail import Gmail
    for tool in agent.tools:
        if isinstance(tool, Gmail):
            return tool
    raise ValueError("Gmail instance not found in agent tools. Add Gmail() to tools list.")


@before_tool
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
    options.append("No, tell agent what I want")

    choice = pick(f"Send this {action.lower()}?", options, console=_console)

    if choice == "Yes, send it":
        return
    elif choice.startswith("Auto approve emails to"):
        if 'gmail_approved_recipients' not in agent.current_session:
            agent.current_session['gmail_approved_recipients'] = set()
        agent.current_session['gmail_approved_recipients'].add(recipient_key)
        return
    elif choice == "Auto approve all replies this session":
        agent.current_session['gmail_approve_replies'] = True
        return
    elif choice == "Auto approve all emails this session":
        agent.current_session['gmail_approve_all'] = True
        return
    else:
        feedback = input("What do you want the agent to do instead? ")
        raise ValueError(f"User feedback: {feedback}")


@after_tool
def sync_crm_after_send(agent: 'Agent') -> None:
    """Update CRM data after sending email - last_contact, clear next_contact_date."""
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

    gmail = _get_gmail_instance(agent)
    today = datetime.now().strftime('%Y-%m-%d')
    result = gmail.update_contact(to, last_contact=today, next_contact_date='')

    if 'Updated' in result:
        _console.print(f"[dim]CRM updated: {to}[/dim]")


# Bundle as plugin
gmail_plugin = [
    check_email_approval,
    sync_crm_after_send,
]
