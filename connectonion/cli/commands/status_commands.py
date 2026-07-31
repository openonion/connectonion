"""
Purpose: Display account status, deployments, and credential-source diagnostics without re-authenticating
LLM-Note:
  Dependencies: imports from [os, requests, pathlib, dotenv.dotenv_values, rich.console, rich.panel, rich.table, rich.text, address] | imported by [cli/main.py via handle_status()] | calls backend at [https://oo.openonion.ai/api/v1/auth] | tested by [tests/e2e/cli/test_cli_status.py]
  Data flow: receives reveal=False by default → inspects supported provider variable names in process env/local .env/global ~/.co/keys.env without loading values → displays redacted name/status/source table → if reveal=True, displays full values in a separate warning-marked table → load_api_key() resolves OPENONION_API_KEY → address.load() reads Ed25519 keypair → creates fresh auth message with timestamp → address.sign() creates signature → POST to /api/v1/auth → displays account and deployments
  State/Effects: no state modifications | makes network requests to oo.openonion.ai after local diagnostics | reads env vars, .env, ~/.co/keys.env without exporting them | default output contains no secret material; explicit --reveal writes full values to the terminal | does NOT update any files
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

from .project_cmd_lib import load_api_key

console = Console()

API_BASE = "https://oo.openonion.ai"

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


def _read_credential_file(path: Path) -> dict[str, str]:
    """Read supported key entries without mutating ``os.environ``."""
    if not path.is_file():
        return {}
    try:
        values = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError):
        return {}
    supported = {name for name, _provider in CREDENTIAL_ENV_VARS}
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
) -> tuple[tuple[str, Mapping[str, str]], ...]:
    """Return supported credential values grouped by privacy-safe source."""
    project_dir = (project_dir or Path.cwd()).resolve()
    home = (home or Path.home()).resolve()
    environ = os.environ if environ is None else environ

    return (
        ("process environment", environ),
        ("<project>/.env", _read_credential_file(project_dir / ".env")),
        ("~/.co/keys.env", _read_credential_file(home / ".co" / "keys.env")),
    )


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
        elif len(unique_values) > 1:
            status = "conflict"
            source = " + ".join(source_names)
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
        f"{API_BASE}/api/v1/deployments",
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
        console.print("\n[cyan]Deployed Agents:[/cyan] none")
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
    """Check account status without re-authenticating.

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

    # Load keys to re-sign
    co_dir = Path(".co")
    if not (co_dir.exists() and (co_dir / "keys" / "agent.key").exists()):
        co_dir = Path.home() / ".co"

    addr_data = address.load(co_dir)
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
        "https://oo.openonion.ai/api/v1/auth",
        json={
            "public_key": public_key,
            "signature": signature,
            "message": message
        }
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
