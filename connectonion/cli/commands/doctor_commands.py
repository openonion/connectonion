"""
Purpose: Diagnose ConnectOnion installation and configuration issues
LLM-Note:
  Dependencies: imports from [sys, os, shutil, pathlib, requests, rich.console, rich.panel, rich.table, __version__] | imported by [cli/main.py via handle_doctor()] | checks local files and backend connectivity
  Data flow: receives no args → checks system info → checks config files → checks API key → tests backend connectivity → displays results with ✓/✗ indicators
  State/Effects: no state modifications | reads from filesystem | makes HTTP request | writes to stdout via rich.Console
  Integration: exposes handle_doctor() for CLI | helps users self-diagnose setup issues
  Performance: fast local checks (<100ms) | network check to backend (1-2s)
  Errors: lets errors crash naturally - no try-except unless absolutely needed
"""

import sys
import os
import shutil
from pathlib import Path

from ...project import project_co_dir
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def verdict(problems: list) -> int:
    """The last line, and the exit code, saying what the body already said.

    `co doctor` printed `✅ Diagnostics complete!` and exited 0 whatever it
    found — including, on a real project, right under its own
    `user/email-outreach ✗ broken symlink`. People read the last line, and a
    deploy script reads the exit code; both were told everything was fine.

    Five places add a `✗` row. They now record what they found, and this says
    it back.
    """
    if not problems:
        console.print("[bold green]✅ Diagnostics complete — nothing wrong[/bold green]\n")
        return 0

    console.print(f"[bold red]✗ Diagnostics complete — {len(problems)} problem"
                  f"{'s' if len(problems) > 1 else ''}[/bold red]")
    for problem in problems:
        console.print(f"  [red]•[/red] {problem}")
    console.print()
    return 1


def model_pricing_note(model) -> "str | None":
    """What to say about a model 1.6.0 no longer prices, or None.

    #603 dropped thirty pre-2025 models from the price table and deliberately
    left routing alone, so a project that still names `gpt-4o-mini` keeps
    working — but every cost shown for it is DEFAULT_PRICING now, six times the
    real figure in that example, marked only by a `~`.

    The `~` says the number is a guess. It does not say why, and `co doctor` —
    which is what people run after an upgrade when something looks off — said
    nothing at all.

    Not a problem row: the agent runs. A note, next to the model.
    """
    if not model or not model.strip():
        return None

    from ...core.usage import is_estimated_price

    model = model.strip()
    if not is_estimated_price(model):
        return None

    return (f"{model} is no longer in the price table — it still runs, "
            f"and costs shown for it are estimates")


def _shown(path: Path) -> str:
    """A path relative to where you are standing, so the panel stays readable.

    These rows used to interpolate a bare `Path(".co")/…`, which read as
    `.co/keys/agent.key` only because it was relative to begin with. Resolving
    the project properly made them absolute, and the panel started printing the
    machine's whole directory tree. Relative to the cwd it also says which way
    the project lies: `.co/…` at the root, `../.co/…` below it.
    """
    import os

    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return os.path.relpath(path, Path.cwd())


def handle_doctor():
    """Run comprehensive diagnostics on ConnectOnion installation.

    TODO: Replace manual checks with `co ai` powered diagnosis —
    let an LLM agent inspect the environment, interpret errors,
    and suggest fixes conversationally.
    """
    # `found`, not `problems`: find_skill_problems() already puts a list of
    # (location, name, reason) tuples in a local called `problems`, and
    # shadowing it made the loop below unpack my strings into three names.
    # The real CLI caught that; the unit tests could not see it.
    found: list[str] = []
    from ... import __version__

    console.print("\n[bold cyan]🔍 ConnectOnion Diagnostics[/bold cyan]\n")

    # System checks
    system_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    system_table.add_column("Check", style="cyan")
    system_table.add_column("Status")

    # Version
    system_table.add_row("Version", f"[green]✓[/green] {__version__}")

    # Python
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_path = sys.executable
    system_table.add_row("Python", f"[green]✓[/green] {python_version}")
    system_table.add_row("Python Path", f"[dim]{python_path}[/dim]")

    # Virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    venv_status = "[green]✓[/green] Virtual environment" if in_venv else "[yellow]○[/yellow] Global Python"
    system_table.add_row("Environment", venv_status)
    if in_venv:
        system_table.add_row("Venv Path", f"[dim]{sys.prefix}[/dim]")

    # Command location
    co_path = shutil.which('co')
    if co_path:
        system_table.add_row("Command", f"[green]✓[/green] {co_path}")
    else:
        system_table.add_row("Command", "[red]✗[/red] 'co' not found in PATH")
        found.append("'co' is not on PATH")

    # Package location
    import connectonion
    package_path = Path(connectonion.__file__).parent
    system_table.add_row("Package", f"[dim]{package_path}[/dim]")

    console.print(Panel(system_table, title="[bold]System[/bold]", border_style="blue"))
    console.print()

    # Configuration checks
    config_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    config_table.add_column("Check", style="cyan")
    config_table.add_column("Status")

    # Check for host.yaml (project config)
    # The project's, found by walking up -- the rule since #660. As a bare
    # Path(".co") every one of these answered for whatever directory `co doctor`
    # was run from, so a subdirectory of a project was diagnosed as a different
    # project: no config, and the machine's key reported as this agent's with a
    # green tick beside it.
    local_config = project_co_dir() / "host.yaml"
    config = {}

    if local_config.exists():
        config_table.add_row("Config", f"[green]✓[/green] {_shown(local_config)}")
        import yaml
        with open(local_config, 'r', encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        agent_name = config.get("name", "Not set")
        config_table.add_row("Agent Name", f"[dim]{agent_name}[/dim]")

    # The model this project would use, and whether 1.6.0 still prices it.
    #
    # MODEL comes from the environment because connectonion/__init__.py loads
    # the project .env at import and cli/main.py loads it again — both happen
    # before this runs. The explicit load_dotenv further down is for the API
    # key and comes later; do not reorder this above it expecting to find the
    # value there.
    model = os.getenv("MODEL") or config.get("model")
    if model:
        note = model_pricing_note(model)
        if note:
            config_table.add_row("Model", f"[yellow]○[/yellow] {note}")
        else:
            config_table.add_row("Model", f"[green]✓[/green] {model}")
    else:
        config_table.add_row("Config", "[yellow]○[/yellow] Not found (optional)")

    # Check for keys
    local_keys = project_co_dir() / "keys" / "agent.key"
    global_keys = Path.home() / ".co" / "keys" / "agent.key"

    if local_keys.exists():
        config_table.add_row("Keys", f"[green]✓[/green] {_shown(local_keys)}")
    elif global_keys.exists():
        config_table.add_row("Keys", f"[green]✓[/green] {global_keys}")
    else:
        config_table.add_row("Keys", "[yellow]○[/yellow] Not found (run 'co auth' to create)")

    # Check for API key
    api_key = os.getenv("OPENONION_API_KEY")
    if api_key:
        api_key_display = f"{api_key[:20]}..." if len(api_key) > 20 else api_key
        config_table.add_row("API Key", f"[green]✓[/green] Found in environment")
        config_table.add_row("Key Preview", f"[dim]{api_key_display}[/dim]")
    else:
        # Check .env files
        from dotenv import load_dotenv
        local_env = Path(".env")
        global_env = Path.home() / ".co" / "keys.env"

        if local_env.exists():
            load_dotenv(local_env)
            api_key = os.getenv("OPENONION_API_KEY")
            if api_key:
                config_table.add_row("API Key", f"[green]✓[/green] Found in .env")

        if not api_key and global_env.exists():
            load_dotenv(global_env)
            api_key = os.getenv("OPENONION_API_KEY")
            if api_key:
                config_table.add_row("API Key", f"[green]✓[/green] Found in ~/.co/keys.env")

        if not api_key:
            config_table.add_row("API Key", "[yellow]○[/yellow] Not configured (run 'co auth')")

    console.print(Panel(config_table, title="[bold]Configuration[/bold]", border_style="green"))
    console.print()

    # Browser checks (stealth driver integrity)
    browser_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    browser_table.add_column("Check", style="cyan")
    browser_table.add_column("Status")

    from ...useful_tools.browser_tools.browser import driver_stealth_status
    status, browser_version, detail = driver_stealth_status()
    if status == "ok":
        browser_table.add_row("Patchright", f"[green]✓[/green] {browser_version}")
        browser_table.add_row("Stealth driver", f"[green]✓[/green] {detail}")
    elif status == "broken":
        browser_table.add_row("Patchright", f"[yellow]○[/yellow] {browser_version}")
        browser_table.add_row("Stealth driver", f"[red]✗[/red] {detail}")
        found.append(f"stealth driver: {detail}")
    else:  # missing
        browser_table.add_row("Patchright", f"[yellow]○[/yellow] {detail}")

    console.print(Panel(browser_table, title="[bold]Browser[/bold]", border_style="cyan"))
    console.print()

    # Skills — which tier each came from, because that decides whether it survives
    # a deploy. A user-tier skill works for months and is simply absent everywhere
    # else, and nothing in the agent's output ever says so.
    from ...useful_plugins.skills import (
        _discover_all_skills, find_skill_problems, TRAVELS_ON_DEPLOY,
    )

    skills = _discover_all_skills()
    problems = find_skill_problems()

    skills_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    skills_table.add_column("Check", style="cyan")
    skills_table.add_column("Status")

    counts = {}
    for skill in skills:
        counts[skill.location] = counts.get(skill.location, 0) + 1
    for location, count in sorted(counts.items()):
        mark = "[green]✓[/green]" if location in TRAVELS_ON_DEPLOY else "[yellow]○[/yellow]"
        note = "" if location in TRAVELS_ON_DEPLOY else "  [dim]stays on this machine[/dim]"
        skills_table.add_row(location, f"{mark} {count}{note}")
    if not counts:
        skills_table.add_row("Skills", "[dim]none found[/dim]")

    for location, name, reason in problems:
        skills_table.add_row(f"{location}/{name}", f"[red]✗[/red] {reason}")
        found.append(f"skill {location}/{name}: {reason}")

    console.print(Panel(skills_table, title="[bold]Skills[/bold]", border_style="yellow"))
    console.print()

    # Connectivity checks (only if API key exists)
    if api_key:
        connectivity_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        connectivity_table.add_column("Check", style="cyan")
        connectivity_table.add_column("Status")

        # Check backend reachability
        response = requests.get("https://oo.openonion.ai/health", timeout=5)
        if response.status_code == 200:
            connectivity_table.add_row("Backend", "[green]✓[/green] https://oo.openonion.ai")
        else:
            connectivity_table.add_row("Backend", f"[yellow]⚠[/yellow] Status {response.status_code}")

        # Check authentication (if keys exist)
        if local_keys.exists() or global_keys.exists():
            from ... import address
            import time

            co_dir = project_co_dir() if local_keys.exists() else Path.home() / ".co"
            addr_data = address.load(co_dir)

            public_key = addr_data["address"]
            timestamp = int(time.time())
            message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
            signature = address.sign(addr_data, message.encode()).hex()

            response = requests.post(
                "https://oo.openonion.ai/api/v1/auth",
                json={
                    "public_key": public_key,
                    "signature": signature,
                    "message": message
                },
                timeout=5
            )

            if response.status_code == 200:
                connectivity_table.add_row("Authentication", "[green]✓[/green] Valid credentials")
            else:
                connectivity_table.add_row("Authentication", f"[red]✗[/red] Failed (status {response.status_code})")
                found.append(f"authentication failed (status {response.status_code})")

        console.print(Panel(connectivity_table, title="[bold]Connectivity[/bold]", border_style="magenta"))
        console.print()

    code = verdict(found)
    console.print("[dim]Run 'co auth' if you need to authenticate[/dim]\n")
    return code
