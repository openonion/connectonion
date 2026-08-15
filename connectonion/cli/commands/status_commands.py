"""
Purpose: Display redacted credential diagnostics, canonical account status, and deployments
LLM-Note:
  Dependencies: imports from [os, requests, pathlib, dotenv.dotenv_values, rich.console, rich.panel, rich.table, rich.text, credentials.account_in_token, project_identity, project_root, address] | imported by [cli/main.py via handle_status()] | calls the configured backend /api/v1/auth | tested by [tests/e2e/cli/test_cli_status.py]
  Data flow: receives reveal=False by default → inspects supported provider variable names in process env/project-root .env/global ~/.co/keys.env without loading values → compares OpenOnion sources by public account claim while keeping token values redacted → if reveal=True, displays full values in a separate warning-marked table → load_api_key() performs guarded resolution/recovery → project_identity() selects the project key or global fallback → creates and signs a fresh auth message → POST to /api/v1/auth → displays account and deployments
  State/Effects: discovery is non-mutating and makes no network call | account resolution may re-authenticate and repair a stored token only when the guarded CLI policy finds a different account | then makes account/deployment requests | default output contains no secret material; explicit --reveal writes full values to the terminal
  Integration: exposes handle_status(reveal=False) for CLI | credential discovery supports every provider in core/llm.py | OpenOnion auth still uses load_api_key() priority | source paths are privacy-safe (<project>/.env and ~/.co/keys.env)
  Performance: network call to backend (1-2s) | signature generation is fast (<10ms) | file I/O for .env files
  Errors: credential parse/read failures are treated as no discovered keys | account status fails gracefully if OPENONION_API_KEY or identity keys are missing | backend errors do not expose credential values; only explicit --reveal prints them
"""

import os
from pathlib import Path
from typing import Mapping

import requests
from dotenv import dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...backend import backend_url
from ...credentials import account_in_token
from ...project import project_identity, project_root
from .project_cmd_lib import load_api_key

console = Console()


CREDENTIAL_ENV_VARS = (
    ("OPENONION_API_KEY", "OpenOnion"),
    ("OPENAI_API_KEY", "OpenAI"),
    ("ANTHROPIC_API_KEY", "Anthropic"),
    ("GEMINI_API_KEY", "Gemini"),
    ("GOOGLE_API_KEY", "Gemini alias"),
    ("GROQ_API_KEY", "Groq"),
    ("XAI_API_KEY", "xAI"),
    ("OPENROUTER_API_KEY", "OpenRouter"),
    ("MISTRAL_API_KEY", "Mistral"),
)

OAUTH_CONNECTIONS = (
    ("Google OAuth", "GOOGLE", "co auth google"),
    ("Microsoft OAuth", "MICROSOFT", "co auth microsoft"),
)

_OAUTH_ENV_VARS = {
    f"{prefix}_{suffix}"
    for _provider, prefix, _action in OAUTH_CONNECTIONS
    for suffix in ("ACCESS_TOKEN", "REFRESH_TOKEN", "TOKEN_EXPIRES_AT", "SCOPES", "EMAIL")
}

_PLACEHOLDER_VALUES = {
    "changeme",
    "replace-me",
    "replace_me",
    "your-api-key-here",
    "your_api_key_here",
}


def _is_configured(value: object) -> bool:
    """Return whether *value* looks like a real configured secret.

    Values are inspected only in memory unless the caller explicitly selects
    the ``--reveal`` display path.
    """
    if value is None:
        return False
    normalized = str(value).strip().strip("\"'")
    if not normalized:
        return False
    lowered = normalized.lower()
    return not (
        lowered in _PLACEHOLDER_VALUES
        or lowered.startswith(("sk-your", "your-", "your_", "<"))
        or (lowered.startswith("${") and lowered.endswith("}"))
    )


def _read_credential_file(
    path: Path,
    supported_names: set[str] | None = None,
) -> dict[str, str]:
    """Read supported key entries without mutating ``os.environ``."""
    if not path.is_file():
        return {}
    try:
        values = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError):
        return {}
    supported = (
        {name for name, _provider in CREDENTIAL_ENV_VARS} | _OAUTH_ENV_VARS
        if supported_names is None
        else supported_names
    )
    return {
        name: str(value)
        for name, value in values.items()
        if name in supported and _is_configured(value)
    }


def _credential_sources(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    supported_names: set[str] | None = None,
) -> tuple[tuple[str, Mapping[str, str]], ...]:
    """Return supported credential values grouped by privacy-safe source."""
    project_dir = (
        Path(project_dir).resolve()
        if project_dir is not None
        else project_root().resolve()
    )
    home = (home or Path.home()).resolve()
    environ = os.environ if environ is None else environ
    project_source = "~/.env" if project_dir == home else "<project>/.env"

    return (
        ("process environment", environ),
        (
            project_source,
            _read_credential_file(project_dir / ".env", supported_names),
        ),
        (
            "~/.co/keys.env",
            _read_credential_file(home / ".co" / "keys.env", supported_names),
        ),
    )


def _selected_credential_values(
    names: tuple[str, ...],
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Select the first configured value from the canonical source inventory."""
    sources = _credential_sources(
        project_dir=project_dir,
        home=home,
        environ=environ,
        supported_names=set(names),
    )
    return {
        name: next(
            (
                str(values[name])
                for _source, values in sources
                if _is_configured(values.get(name))
            ),
            None,
        )
        for name in names
    }


def _short_account(account: str) -> str:
    """A public address that distinguishes accounts without dominating a row."""
    if len(account) <= 20:
        return account
    return f"{account[:16]}…{account[-4:]}"


def _openonion_source_status(
    found: list[tuple[str, str]],
) -> tuple[str, str]:
    """Describe OpenOnion sources by account identity, never token text.

    JWTs rotate, so two different strings can still authorize the same account.
    When every token has an inspectable public claim, the claims define whether
    there is a conflict. If any token is opaque, value equality is the only safe
    fallback; server authentication remains authoritative.
    """
    claims = [account_in_token(value) for _source, value in found]
    if all(claim is not None for claim in claims):
        conflict = len({claim.casefold() for claim in claims if claim}) > 1
    else:
        conflict = len({value for _source, value in found}) > 1

    labels = []
    for index, ((source, _value), claim) in enumerate(zip(found, claims)):
        details = []
        if conflict and index == 0:
            details.append("used")
        if claim:
            details.append(f"account {_short_account(claim)}")
        labels.append(
            f"{source} ({' · '.join(details)})" if details else source
        )

    if conflict:
        return "conflict", " + ".join(labels)
    if found[0][0] == "process environment":
        return "configured", " + ".join(labels)
    return "discovered · not loaded", " + ".join(labels)


def _credential_rows(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Return redacted credential metadata suitable for display or JSON.

    The returned dictionaries intentionally cannot contain secret values.
    """
    sources = _credential_sources(
        project_dir=project_dir,
        home=home,
        environ=environ,
    )

    rows: list[dict[str, str]] = []
    for name, provider in CREDENTIAL_ENV_VARS:
        found = [
            (source, str(values.get(name)))
            for source, values in sources
            if _is_configured(values.get(name))
        ]
        source_names = [source for source, _value in found]
        unique_values = {value for _source, value in found}

        if not found:
            status = "missing"
            source = "—"
        elif name == "OPENONION_API_KEY":
            status, source = _openonion_source_status(found)
        elif len(unique_values) > 1:
            status = "conflict"
            # Which one is actually used. _credential_sources returns its
            # sources in precedence order — process environment first, because
            # load_dotenv() does not override a variable already set — so the
            # first one found is the winner.
            #
            # The panel named the conflict and stopped one word short of the
            # answer, and an operator reading it is looking *because* something
            # is using the wrong key. The natural guess is that the project's
            # own .env wins, being the more specific of the two. It does not.
            source = " + ".join(
                f"{name} (used)" if index == 0 else name
                for index, name in enumerate(source_names)
            )
        elif source_names[0] == "process environment":
            status = "configured"
            source = " + ".join(source_names)
        else:
            status = "discovered · not loaded"
            source = " + ".join(source_names)

        rows.append(
            {
                "provider": provider,
                "credential": name,
                "status": status,
                "source": source,
            }
        )
    return rows


def _revealed_credential_rows(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Return full credential values for the explicit ``--reveal`` path."""
    sources = _credential_sources(
        project_dir=project_dir,
        home=home,
        environ=environ,
    )
    rows: list[dict[str, str]] = []
    for name, provider in CREDENTIAL_ENV_VARS:
        for source, values in sources:
            value = values.get(name)
            if _is_configured(value):
                rows.append(
                    {
                        "provider": provider,
                        "credential": name,
                        "source": source,
                        "value": str(value),
                    }
                )
    return rows


def _oauth_rows(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
) -> list[dict[str, str]]:
    """Return redacted OAuth connection state using the same source precedence."""
    import datetime
    import time

    sources = _credential_sources(project_dir=project_dir, home=home, environ=environ)
    now = time.time() if now is None else now
    rows = []
    for provider, prefix, action in OAUTH_CONNECTIONS:
        found = []
        for source, values in sources:
            access = values.get(f"{prefix}_ACCESS_TOKEN")
            refresh = values.get(f"{prefix}_REFRESH_TOKEN")
            if _is_configured(access) or _is_configured(refresh):
                state = tuple(
                    str(values.get(f"{prefix}_{suffix}") or "")
                    for suffix in ("ACCESS_TOKEN", "REFRESH_TOKEN", "TOKEN_EXPIRES_AT", "SCOPES", "EMAIL")
                )
                found.append((source, state, values))

        if not found:
            rows.append({"provider": provider, "status": "missing", "source": "—", "action": action})
            continue

        unique_states = {state for _source, state, _values in found}
        source_names = [source for source, *_rest in found]
        if len(unique_states) > 1:
            source = " + ".join(
                f"{name} (used)" if index == 0 else name
                for index, name in enumerate(source_names)
            )
            rows.append({"provider": provider, "status": "conflict", "source": source,
                         "action": f"remove or update the shadowed value; then {action}"})
            continue

        source, state, values = found[0]
        _access, refresh, _expires, scopes, _email = state
        expires = values.get(f"{prefix}_TOKEN_EXPIRES_AT")
        expired = False
        invalid_expiry = False
        if _is_configured(expires):
            try:
                expired = float(str(expires)) <= now
            except ValueError:
                try:
                    parsed = datetime.datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                    expired = parsed.timestamp() <= now
                except ValueError:
                    invalid_expiry = True

        if not _is_configured(scopes):
            status = "incomplete (scopes missing)"
        elif invalid_expiry:
            status = "invalid expiry"
        elif expired and not _is_configured(refresh):
            status = "expired"
        elif expired:
            status = "refresh available"
        else:
            status = "connected"
        rows.append({"provider": provider, "status": status, "source": source, "action": action})
    return rows


def _show_credentials(reveal: bool = False) -> None:
    """Print provider credential availability and optionally full values."""
    status_style = {
        "configured": "green",
        "discovered · not loaded": "yellow",
        "conflict": "red",
        "missing": "dim",
    }
    table = Table(
        title="Credential Sources",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Provider")
    table.add_column("Credential")
    table.add_column("Status")
    table.add_column("Source")

    for row in _credential_rows():
        style = status_style[row["status"]]
        table.add_row(
            row["provider"],
            row["credential"],
            f"[{style}]{row['status']}[/{style}]",
            row["source"],
        )

    console.print()
    console.print(table)

    if not reveal:
        console.print(
            "[dim]Values hidden. Use [bold]co status --reveal[/bold] "
            "only when you intentionally need full credentials.[/dim]"
        )
        return

    revealed_rows = _revealed_credential_rows()
    if not revealed_rows:
        console.print("[dim]No credential values are available to reveal.[/dim]")
        return

    console.print(
        "\n[bold yellow]⚠ Secrets shown in full. "
        "Do not share this output or paste it into logs.[/bold yellow]"
    )
    revealed_table = Table(
        title="Revealed Credential Values",
        show_header=True,
        header_style="bold yellow",
    )
    revealed_table.add_column("Provider")
    revealed_table.add_column("Credential")
    revealed_table.add_column("Source")
    revealed_table.add_column("Value", overflow="fold", no_wrap=False)

    for row in revealed_rows:
        revealed_table.add_row(
            row["provider"],
            row["credential"],
            row["source"],
            Text(row["value"]),
        )

    console.print(revealed_table)


def _fetch_deployments(api_key: str):
    """Return deployments for the current account from ConnectOnion Cloud."""
    response = requests.get(
        f"{backend_url()}/api/v1/deployments",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if response.status_code != 200:
        console.print(f"\n[yellow]Could not load deployments: {response.status_code}[/yellow]")
        return []
    return response.json().get("deployments", [])


def _show_deployments(deployments):
    """Print a compact deployed-agent table."""
    if not deployments:
        # Which list this is. It comes from ConnectOnion Cloud; an agent put on
        # your own box with `co deploy --to` lives in ~/.co/servers.yaml and is
        # never in it. A bare "none" told an operator with four registered
        # servers and two running agents that they had nothing deployed —
        # answering the one question this command exists to answer, wrongly.
        console.print("\n[cyan]Deployed Agents (cloud):[/cyan] none")
        console.print("[dim]  agents on your own servers: co server ls[/dim]")
        return

    table = Table(title="Deployed Agents", show_header=True, header_style="bold cyan")
    table.add_column("Project")
    table.add_column("Status")
    table.add_column("Active")
    table.add_column("Container")
    table.add_column("URL")

    for deployment in deployments:
        is_active = "yes" if deployment.get("is_active") else "no"
        container = "running" if deployment.get("container_running") else "stopped"
        table.add_row(
            str(deployment.get("project_name") or ""),
            str(deployment.get("status") or "unknown"),
            is_active,
            container,
            str(deployment.get("url") or ""),
        )

    console.print()
    console.print(table)


def handle_status(reveal: bool = False):
    """Check canonical account status after redacted local diagnostics.

    Credential discovery itself is read-only. The subsequent account phase uses
    the ordinary CLI guard, which re-authenticates only to recover an explicit
    account mismatch.

    Args:
        reveal: If True, print full provider credential values.

    Shows:
    - Agent ID
    - Email address
    - Balance (remaining credits)
    - Total spent
    - Last seen
    - Warnings if balance is low
    """
    _show_credentials(reveal=reveal)

    # Load API key
    api_key = load_api_key()
    if not api_key:
        console.print("\n❌ [bold red]No API key found[/bold red]")
        console.print("\n[cyan]Authenticate first:[/cyan]")
        console.print("  [bold]co auth[/bold]     Authenticate with OpenOnion\n")
        return

    import time

    from ... import address

    # Sign as the same canonical identity the credential guard expects:
    # project key first (including from nested directories), global fallback.
    addr_data = project_identity()
    if not addr_data:
        console.print("\n❌ [bold red]No keys found[/bold red]")
        console.print("[yellow]Run 'co auth' first.[/yellow]\n")
        return

    # This key predates the SLIP-0010 switch, so the phrase saved beside it now
    # derives a different address. The key itself is fine and stays in use — the
    # warning is that recovering from those words lands somewhere else, which is
    # only discoverable at the moment someone tries it, on a new machine, with no
    # way back.
    if addr_data.get("legacy_derivation"):
        console.print(
            "\n[yellow]⚠ This identity was created before ConnectOnion adopted "
            "SLIP-0010 key derivation.[/yellow]"
        )
        console.print(
            "[dim]  It keeps working. But your recovery phrase now derives a "
            "different address,\n"
            "  so 'co auth recover' with those words gives you a new, empty "
            "agent — not this one.\n"
            "  Keep .co/keys/agent.key backed up; the phrase alone no longer "
            "restores it.[/dim]"
        )

    public_key = addr_data["address"]
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()

    # Call auth endpoint to get fresh user data
    response = requests.post(
        f"{backend_url()}/api/v1/auth",
        json={
            "public_key": public_key,
            "signature": signature,
            "message": message
        },
        timeout=15,
    )

    if response.status_code != 200:
        console.print(f"\n❌ [bold red]Error {response.status_code}[/bold red]")
        console.print(f"[yellow]{response.text}[/yellow]\n")
        return

    data = response.json()
    user = data.get("user", {})
    email_info = user.get("email") or {}

    # Compute short address from full address (first 6 chars + ... + last 4 chars)
    short_address = f"{public_key[:6]}...{public_key[-4:]}"

    info_lines = [
        f"[cyan]Agent Address:[/cyan] {public_key}",
        f"[cyan]Agent ID:[/cyan] {short_address}",
        f"[cyan]Email:[/cyan] {email_info.get('address') or os.getenv('AGENT_EMAIL', 'Not configured')}",
        f"[cyan]Balance:[/cyan] ${user.get('balance_usd', 0.0):.4f}",
        f"[cyan]Total Spent:[/cyan] ${user.get('total_cost_usd', 0.0):.4f}",
        f"[cyan]Credits:[/cyan] ${user.get('credits_usd', 0.0):.4f}",
    ]

    console.print("\n")
    console.print(Panel.fit(
        "\n".join(info_lines),
        title="📊 Account Status",
        border_style="cyan"
    ))

    _show_deployments(_fetch_deployments(api_key))

    if user.get('balance_usd', 0) <= 0:
        console.print("\n[yellow]⚠️  Low balance! Add credits at https://o.openonion.ai/purchase[/yellow]")

    console.print("\n[yellow]💡 Tips:[/yellow]")
    console.print("   • Add credits: https://o.openonion.ai/purchase")
    console.print("   • Use 'co auth' to refresh your token")
    console.print("   • Pricing: https://docs.connectonion.com/models/pricing\n")
