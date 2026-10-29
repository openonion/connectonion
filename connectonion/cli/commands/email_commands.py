"""
Purpose: CLI surface for the agent mailbox — send, list (inbox), and read emails from the terminal
LLM-Note:
  Dependencies: imports from [rich.console, rich.table, rich.panel, .project_cmd_lib.load_api_key, ...useful_tools.send_email.send_email, ...useful_tools.get_emails.get_emails/mark_read] | imported by [cli/main.py via handle_email_*()] | hits the configured backend through the engine tools at [/api/v1/email/*]
  Data flow: load_api_key() ensures OPENONION_API_KEY + AGENT_EMAIL are in env → handle_email_send() → send_email(to, subject, message) → prints message_id | handle_email_inbox() → get_emails(last, unread, offset) → Rich table | handle_email_read() → get_emails() → find by id → print body → optionally mark_read(id)
  State/Effects: no local state | network calls happen inside the engine tools | only read --mark-read flips server-side read status | writes to stdout via rich.Console
  Integration: exposes handle_email_send(), handle_email_inbox(), handle_email_read(), handle_email_addresses(), handle_email_share()/handle_email_unshare() (connectonion#1137) for cli/main.py | thin presentation layer — all email logic lives in useful_tools/{send_email,get_emails}.py, share/unshare hit /api/v1/email/share directly like addresses/name do | requires prior 'co auth'
  Errors: prints a 'run co auth' hint when no API key found | send_email returns {success, error} dicts (printed as-is); get_emails/mark_read let API errors crash | an empty inbox --address page is checked against owned addresses and can_read grants before it is reported as no mail (#2671)
"""

import shlex

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.table import Table

from ...backend import backend_url
from .project_cmd_lib import load_api_key

console = Console()

def _print_no_auth():
    console.print("\n❌ [bold red]No API key found[/bold red]")
    console.print("\n[cyan]Authenticate first:[/cyan]")
    console.print("  [bold]co auth[/bold]     Authenticate with OpenOnion\n")


def _require_auth() -> bool:
    """Ensure OPENONION_API_KEY (and the .env it lives next to) are loaded. Exits 1 if missing."""
    if load_api_key():
        return True
    _print_no_auth()
    raise typer.Exit(1)


def _err(response) -> str:
    """Pull a human-readable message out of an error response (JSON detail or raw text)."""
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        detail = body.get("detail", body)
        return detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
    return response.text.strip() or f"HTTP {response.status_code}"


def _read_failure(exc, mailbox: str):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status in (401,403):
            console.print("Your mail session expired or access was denied. Run co auth login, then retry.", markup=False)
            return
        if status == 404:
            console.print(f"No {mailbox} email with that ID is available to this account.", markup=False)
            if mailbox == "received":
                console.print("To select an existing message, run co email inbox, then co email read <#>.", markup=False)
            return
        console.print(f"The email service returned HTTP {status}. Please retry.", markup=False)
    elif isinstance(exc, requests.RequestException):
        console.print("Could not reach the email service. Check your connection and retry.", markup=False)
    else:
        console.print(str(exc), markup=False)


def handle_email_send(
    to: str, subject: str, message: str,
    idempotency_key: str = None, from_address: str = None,
    max_cost_usd: str = '0',
):
    """Send an email from the agent's address."""
    if not _require_auth():
        return

    from ...useful_tools.send_email import send_email
    budget = {} if str(max_cost_usd) in ('0','0.0') else {'max_cost_usd':max_cost_usd}
    result = send_email(
        to, subject, message,
        idempotency_key=idempotency_key, from_address=from_address, **budget,
    )

    if result.get("success"):
        console.print(f"\n[green]✓ Sent[/green] to [cyan]{to}[/cyan]")
        console.print(f"  From:       {result.get('from', '')}")
        console.print(f"  Message ID: {result.get('message_id', '')}")
        if result.get('charged_usd') is not None:
            from decimal import Decimal
            charged=Decimal(str(result['charged_usd']))
            console.print(f"  Cost:       ${charged:.3f}" if charged else '  Cost:       Included in your monthly allowance',markup=False)
        console.print("\n[dim]See it in your sent mail:[/dim] [bold]co email sent[/bold]\n")
    else:
        error = result.get("error", "Unknown error")
        console.print(f"\nSend not confirmed: {error}",markup=False)
        if result.get("request_id"):
            console.print(f"  Request ID: {result['request_id']}")
        if result.get('idempotency_key'):
            console.print(f"  Send ID: {result['idempotency_key']}",markup=False)
            if result.get('dispatched') is not False:
                print('  Check delivery: co email status '+shlex.quote(result['idempotency_key']))
        if result.get('code') in ('email_payment_required','insufficient_credits'):
            quote=result.get('billing') or {}
            console.print(f"  Next email: ${quote.get('next_send_cost_usd','—')} · Available credits: ${quote.get('balance_usd','—')}",markup=False)
            console.print('  Review allowance: co email tier. PAYG requires an explicit --max-cost (USD). No subscription.',markup=False)
        if result.get("retryable") and result.get("idempotency_key"):
            # The full command, restated — "the same command" is not in the
            # output, so an agent reading only this output could not retry.
            retry = ["co", "email", "send", shlex.quote(to), shlex.quote(subject), shlex.quote(message)]
            if from_address:
                retry += ["--from", shlex.quote(from_address)]
            if budget:
                retry += ['--max-cost',shlex.quote(str(max_cost_usd))]
            retry += ["--idempotency-key", shlex.quote(result["idempotency_key"])]
            # Plain print, not console.print: Rich wraps at the console width,
            # and a line-broken command is no longer copy-pasteable.
            print("  Retry safely with: " + " ".join(retry))
        if "not one of this account's email addresses" in error:
            console.print("  See your addresses: [bold]co email addresses[/bold]")
        console.print()
        raise typer.Exit(1)


def _same_address(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


def _granted_read_addresses(token: str) -> list[str]:
    """Addresses another account granted this one read access to."""
    response = requests.get(
        f"{backend_url()}/api/v1/email/share",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not response.ok:
        console.print(f"\n[red]✗ {_err(response)}[/red]\n")
        raise typer.Exit(1)
    return [
        str(row["address"])
        for row in response.json().get("granted_to_me", [])
        if row.get("can_read") and row.get("address")
    ]


def _require_inbox_address(address: str) -> None:
    """An empty received page is not proof the mailbox is empty.

    GET /received answers an address this account cannot read with an empty
    page, so a caller cannot learn which addresses exist. This account's own
    list is already available. Name it and exit, instead of reporting that no
    mail arrived. A can_read grant is readable without being owned, so an
    empty page there stays "no mail".
    """
    token, settings = _address_settings()
    owned = [
        str(item["address"])
        for item in settings.get("addresses", [])
        if item.get("address")
    ]
    if any(_same_address(address, item) for item in owned):
        return
    granted = _granted_read_addresses(token)
    if any(_same_address(address, item) for item in granted):
        return
    yours = ", ".join(owned) if owned else "(none)"
    console.print(
        f"\n{address} is not one of this account's email addresses.\n"
        f"Yours are: {yours}",
        markup=False,
    )
    console.print("  See your addresses: [bold]co email addresses[/bold]\n")
    raise typer.Exit(1)


def handle_email_inbox(
    last: int = 10, unread: bool = False, offset: int = 0, address: str = None
):
    """List recent emails received at any address this account can read."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_emails
    emails = get_emails(last=last, offset=offset, address=address)
    page_is_full = len(emails) == last
    # Empty is also what /received returns for an address this account cannot
    # read. Only that case is an error; a local --unread filter of a real page
    # is still "no unread mail".
    received_any = bool(emails)
    if unread:
        # The /received endpoint ignores the unread param, so filter here to keep the flag honest.
        emails = [e for e in emails if not e.get("read")]

    if not emails:
        if address and not received_any:
            _require_inbox_address(address)
        scope = "unread " if unread else ""
        where = f" at {address}" if address else ""
        console.print(f"\n[cyan]Inbox:[/cyan] no {scope}emails{where}")
        if unread:
            console.print("[dim]Including read ones:[/dim] [bold]co email inbox[/bold]\n")
        else:
            console.print('[dim]Send one:[/dim] [bold]co email send <to> "<subject>" "<body>"[/bold]\n')
        return

    # The To column earns its width only when the page actually spans more than
    # one mailbox. On a single-address account it would be the same string on
    # every row, which is noise; the moment a second address appears, knowing
    # which one a message landed at is the whole point.
    recipients = {e.get("to", "") for e in emails if e.get("to")}
    show_to = len(recipients) > 1

    table = Table(title="📬 Inbox", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From")
    if show_to:
        # Fold, never ellipsize: a half-printed address is the one thing this
        # column exists to disambiguate, and "aaron@mail.op…" and
        # "aaron.xie@mail.op…" are the same string once Rich truncates them.
        table.add_column("To", overflow="fold")
    table.add_column("Subject")
    table.add_column("Received")

    for email in emails:
        unread_mark = "" if email.get("read") else "[bold green]●[/bold green] "
        row = [str(email.get("id", "")), str(email.get("from", ""))]
        if show_to:
            row.append(str(email.get("to", "")))
        row += [
            f"{unread_mark}{email.get('subject', '')}",
            str(email.get("timestamp", ""))[:19],
        ]
        table.add_row(*row)

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co email read <#>[/bold]")
    if show_to:
        console.print(
            "[dim]One mailbox only:[/dim] "
            "[bold]co email inbox --address <address>[/bold]"
        )
    if page_is_full:
        next_offset = offset + last
        address_flag = f" --address {address}" if address else ""
        console.print(
            "[dim]Next page:[/dim] "
            f"[bold]co email inbox --last {last} --offset {next_offset}{address_flag}[/bold]"
        )
    console.print()


def handle_email_sent(last: int = 10, to: str = None):
    """List emails the agent has sent."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_sent
    try:
        emails = get_sent(last=last, to=to)
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None and response.status_code == 404:
            console.print(
                "\n[yellow]Sent mail is not available on this backend yet.[/yellow] "
                "The oo-api Sent endpoint must be deployed before this command can be used.\n"
            )
        else:
            status = response.status_code if response is not None else "unknown"
            console.print(f"\n[red]✗ Could not load sent mail (HTTP {status}).[/red]\n")
        raise typer.Exit(1)
    except requests.RequestException:
        console.print("\n[red]✗ Could not reach the email service.[/red] Try again later.\n")
        raise typer.Exit(1)

    if not emails:
        scope = f" to {to}" if to else ""
        console.print(f"\n[cyan]Sent:[/cyan] no emails{scope}")
        console.print('[dim]Send one:[/dim] [bold]co email send <to> "<subject>" "<body>"[/bold]\n')
        return

    table = Table(title="📤 Sent", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("To")
    table.add_column("Subject")
    table.add_column("Status")
    table.add_column("Sent")

    for email in emails:
        table.add_row(
            str(email.get("id", "")),
            str(email.get("to", "")),
            str(email.get("subject", "")),
            str(email.get("status", "")),
            str(email.get("timestamp", ""))[:19],
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co email sent read <#>[/bold]\n")


def handle_email_sent_read(email_id: str):
    """Show a single sent email's body."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_sent_email
    try:
        match = get_sent_email(email_id)
    except (requests.RequestException, ValueError) as exc:
        _read_failure(exc, "sent")
        console.print("Next: co email sent", markup=False)
        raise typer.Exit(1) from exc

    header = (
        f"[cyan]To:[/cyan]         {escape(str(match.get('to', '')))}\n"
        f"[cyan]From:[/cyan]       {escape(str(match.get('from', '')))}\n"
        f"[cyan]Subject:[/cyan]    {escape(str(match.get('subject', '')))}\n"
        f"[cyan]Status:[/cyan]     {escape(str(match.get('status', '')))}\n"
        f"[cyan]Message ID:[/cyan] {escape(str(match.get('message_id', '')))}\n"
        f"[cyan]Date:[/cyan]       {escape(str(match.get('timestamp', '')))}"
    )
    console.print()
    console.print(Panel.fit(header, title=f"📤 Sent #{email_id}", border_style="cyan"))
    console.print()
    console.print(match["body"], soft_wrap=True, markup=False) if match.get("body") else console.print("[dim](empty body)[/dim]")
    console.print()


def handle_email_read(email_id: str, mark_read: bool = False):
    """Show a single email's body; mutate its read state only when requested."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_email
    try:
        match = get_email(email_id)
    except (requests.RequestException, ValueError) as exc:
        _read_failure(exc, "received")
        console.print("Next: co email inbox", markup=False)
        raise typer.Exit(1) from exc

    header = (
        f"[cyan]From:[/cyan]    {escape(str(match.get('from', '')))}\n"
        f"[cyan]Subject:[/cyan] {escape(str(match.get('subject', '')))}\n"
        f"[cyan]Date:[/cyan]    {escape(str(match.get('timestamp', '')))}"
    )
    console.print()
    console.print(Panel.fit(header, title=f"✉️  Email #{email_id}", border_style="cyan"))
    console.print()
    # soft_wrap: a long token (a handoff code, a URL) must stay on one line to be copyable.
    if match.get("message"):
        console.print(match["message"], soft_wrap=True, markup=False)
    else:
        console.print("[dim](empty body)[/dim]")
    console.print()

    if mark_read:
        from ...useful_tools.get_emails import mark_read as mark_email_read
        mark_email_read(str(email_id))
        console.print("[dim]Marked read.[/dim]")
    else:
        console.print("[dim]Unread state unchanged. Use --mark-read to change it.[/dim]")


def handle_email_default(address: str):
    """Choose which owned address this account sends from by default.

    The default lives on the account, not in a local file, so it is the same
    from every machine and every agent using this key. A per-project override
    is still `--from` on the individual send — one place to look when a message
    goes out as the wrong address, instead of two that can disagree.
    """
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    r = requests.post(
        f"{backend_url()}/api/v1/email/addresses/default",
        headers={"Authorization": f"Bearer {token}"},
        json={"address": address},
        timeout=10,
    )
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)

    console.print(f"\n[green]✓[/green] {address} is now the default sender\n")


def _address_settings():
    """Read the account's addresses, domain choices and prices from the cloud."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)
    response = requests.get(
        f"{backend_url()}/api/v1/email/addresses",
        headers={"Authorization": f"Bearer {token}"}, timeout=10,
    )
    if not response.ok:
        console.print(f"\n[red]✗ {_err(response)}[/red]\n")
        raise typer.Exit(1)
    return token, response.json()


def handle_email_domains():
    """Discover hosted domains and the current price without buying anything."""
    _, settings = _address_settings()
    for domain in settings["domains"]:
        console.print(domain, markup=False)
    console.print(f"\nAdd an address: ${settings['prices']['add']:.2f} one-time, from credits.")
    console.print("Set one up: co email setup <alias> --domain <domain>\n")


# Phrases check-name uses when the local part itself cannot be sold. A name
# that is only taken uses a different reason and still gets a price preview.
_NAME_REFUSAL_MARKS = ("reserved", "can only contain", "must be", "too short", "too long", "invalid")


def _name_rule_refuses(reason: str) -> bool:
    text = reason.casefold()
    return any(mark in text for mark in _NAME_REFUSAL_MARKS)


def _unsellable_name_reason(token: str, name: str) -> str | None:
    """Why check-name rejects this local part, or None if a price may be quoted.

    /email/check-name is the read-only form of the validator purchase uses
    (length, letters and single dots, the reserved list, the automatic 0x
    mailbox). Which domain is free stays a buy-time question.
    """
    checked = requests.get(
        f"{backend_url()}/api/v1/email/check-name",
        params={"name": name},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not checked.ok:
        return _err(checked)
    body = checked.json()
    if body.get("available") is True:
        return None
    reason = str(body.get("reason") or "")
    if body.get("available") is False and not _name_rule_refuses(reason):
        return None
    if _name_rule_refuses(reason):
        return reason
    return "Could not check whether this name can be purchased."


def handle_email_setup(alias: str, domain: str = "mail.openonion.ai", buy: bool = False):
    """Add an address without replacing this account's existing mailboxes."""
    token, settings = _address_settings()
    alias, domain = alias.strip().lower(), domain.strip().lower()
    address = f"{alias}@{domain}"
    if any(item["address"].lower() == address for item in settings["addresses"]):
        console.print(f"Already owned: {address}", markup=False)
        return
    if domain not in settings["domains"]:
        console.print("Unknown hosted domain. Choose one with: co email domains")
        raise typer.Exit(1)
    refusal = _unsellable_name_reason(token, alias)
    if refusal:
        console.print(f"\n[red]✗ {refusal}[/red]\n")
        raise typer.Exit(1)
    if not buy:
        console.print(f"{address}: ${settings['prices']['add']:.2f} one-time, from credits.", markup=False)
        console.print("Availability is checked when you buy; a taken address is not charged.")
        print(f"Add it: co email setup {alias} --domain {domain} --buy")
        return
    response = requests.post(
        f"{backend_url()}/api/v1/email/addresses",
        headers={"Authorization": f"Bearer {token}"},
        json={"local_part": alias, "domain": domain}, timeout=15,
    )
    if not response.ok:
        console.print(f"\n[red]✗ {_err(response)}[/red]\n")
        raise typer.Exit(1)
    result = response.json()
    console.print(result["message"], markup=False)
    print(f"Choose default: co email default {result['address']}")
    print(f'Send once: co email send <to> "<subject>" "<body>" --from {result["address"]}')


def handle_email_addresses():
    """List every email address this account owns, marking the default sender."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    r = requests.get(
        f"{backend_url()}/api/v1/email/addresses",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)

    addresses = r.json().get("addresses", [])
    if not addresses:
        console.print("\n[cyan]Addresses:[/cyan] none owned yet")
        console.print("\n[dim]Get one with:[/dim] [bold]co email name <name>[/bold]\n")
        return

    if not console.is_terminal:
        # Scripts and agents get tab-separated rows: address, default flag.
        # Plain print, not console.print: Rich expands \t into spaces.
        for a in addresses:
            print(f"{a['address']}\t{'default' if a.get('is_default') else ''}")
        print('Add another: co email setup <alias> --domain <domain> (co email domains lists choices)')
        print('Send as one with: co email send <to> "<subject>" "<body>" --from <address>')
        return

    table = Table(title="📧 Your addresses", show_header=True, header_style="bold cyan")
    table.add_column("Address")
    table.add_column("Default")
    table.add_column("Since")

    for a in addresses:
        table.add_row(
            str(a["address"]),
            "[green]✓[/green]" if a.get("is_default") else "",
            str(a.get("created_at") or "")[:10],
        )

    console.print()
    console.print(table)
    console.print('\n[dim]Send as one with:[/dim] [bold]co email send <to> "<subject>" "<body>" --from <address>[/bold]\n')


_CAPABILITIES = {"send": "can_send", "read": "can_read"}


def _parse_capabilities(can: str) -> dict:
    """'send,read' -> {'can_send': True, 'can_read': True}. Rejects a typo rather
    than silently granting nothing, which the server would also refuse but
    only after a round trip."""
    flags = {"can_send": False, "can_read": False}
    for word in can.split(","):
        word = word.strip().lower()
        if not word:
            continue
        key = _CAPABILITIES.get(word)
        if not key:
            console.print(f"\n[red]✗ Unknown capability: '{word}'.[/red] Use send, read, or both.\n")
            raise typer.Exit(1)
        flags[key] = True
    if not flags["can_send"] and not flags["can_read"]:
        console.print("\n[red]✗ --can needs at least one of: send, read[/red]\n")
        raise typer.Exit(1)
    return flags


def _print_shares_table(title: str, rows: list, other_key: str):
    if not rows:
        console.print(f"[cyan]{title}:[/cyan] none\n")
        return
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Address")
    table.add_column("With" if other_key == "grantee_public_key" else "Owner")
    table.add_column("Can")
    for row in rows:
        capabilities = ",".join(
            name for name, key in _CAPABILITIES.items() if row.get(key)
        )
        table.add_row(str(row.get("address", "")), str(row.get(other_key, "")), capabilities)
    console.print(table)
    console.print()


def handle_email_share(
    address: str = None, *, with_: str = None, can: str = None, list_: bool = False,
):
    """Grant, or list, access to one of your addresses (connectonion#1137)."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)
    headers = {"Authorization": f"Bearer {token}"}

    if list_:
        r = requests.get(f"{backend_url()}/api/v1/email/share", headers=headers, timeout=10)
        if not r.ok:
            console.print(f"\n[red]✗ {_err(r)}[/red]\n")
            raise typer.Exit(1)
        data = r.json()
        console.print()
        _print_shares_table("📤 Shared by you", data.get("granted_by_me", []), "grantee_public_key")
        _print_shares_table("📥 Shared with you", data.get("granted_to_me", []), "owner_public_key")
        console.print("[dim]Grant access:[/dim] [bold]co email share <address> --with <who> --can send,read[/bold]\n")
        return

    if not address or not with_ or not can:
        console.print(
            "\n[red]✗ Usage:[/red] co email share <address> --with <who> --can send,read"
            "\n         co email share --list\n"
        )
        raise typer.Exit(1)

    payload = {"address": address, "grantee": with_, **_parse_capabilities(can)}
    r = requests.post(f"{backend_url()}/api/v1/email/share", json=payload, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)

    data = r.json()
    granted = ",".join(name for name, key in _CAPABILITIES.items() if data.get(key))
    console.print(f"\n[green]✓ Shared {address}[/green] with [cyan]{with_}[/cyan] ({granted})")
    console.print("[dim]Revoke it with:[/dim]")
    # Plain print, not console.print: Rich wraps at the console width, and a
    # line-broken command is no longer copy-pasteable.
    print(f"  co email unshare {address} --with {with_}\n")


def handle_email_unshare(address: str, *, with_: str):
    """Revoke a grant on one of your addresses (connectonion#1137)."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    r = requests.delete(
        f"{backend_url()}/api/v1/email/share/{address}/{with_}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)

    console.print(f"\n[green]✓ Revoked {with_}'s access to {address}[/green]\n")


def handle_email_name(name: str, buy: bool = False):
    """Check whether a custom email name is available, or claim it (deducts credits)."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    if not buy:
        r = requests.get(f"{backend_url()}/api/v1/email/check-name", params={"name": name}, headers=headers, timeout=10)
        if not r.ok:
            console.print(f"\n[red]✗ {_err(r)}[/red]\n")
            raise typer.Exit(1)
        data = r.json()
        if data.get("available"):
            console.print(f"\n[green]✓ {data['email']} is available[/green] — [bold]${data['price']:.2f}[/bold] one-time, from credits")
            console.print(f"[dim]Claim it:[/dim] [bold]co email name {name} --buy[/bold]\n")
        else:
            console.print(f"\n[yellow]✗ {data['email']} — {data.get('reason', 'unavailable')}[/yellow]\n")
        return

    r = requests.post(f"{backend_url()}/api/v1/email/purchase-name", json={"name": name}, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Your address: [cyan]{data['email']}[/cyan]")
    console.print(f'[dim]Send from it:[/dim] [bold]co email send <to> "<subject>" "<body>" --from {data["email"]}[/bold]\n')


def handle_email_upgrade(
    tier: str,
    domain: str = None,
    alias: str = None,
    keep_address: bool = False,
):
    """Upgrade email tier (plus/pro), deducting the monthly price from credits."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {"tier": tier}
    if domain:
        payload["domain"] = domain
    if alias:
        payload["alias"] = alias
    if keep_address:
        payload["keep_address"] = True

    r = requests.post(f"{backend_url()}/api/v1/email/upgrade", json=payload, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Tier address: [cyan]{data['email_address']}[/cyan]")
    console.print(f"  Quota:   {data['emails_per_month']:,}/month")
    if data.get("balance") is not None:
        console.print(f"  Balance: ${data['balance']:.2f}")
    console.print()
