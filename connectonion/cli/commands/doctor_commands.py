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
from ...backend import backend_url
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


EVALS_NOTE_THRESHOLD_MB = 20


def disk_usage_note() -> "str | None":
    """What to say about the space `co` has taken, or None.

    One eval per distinct first prompt, plus a directory of runs for it. Runs
    inside an eval are capped at KEEP_RUNS_PER_EVAL and trimmed after every
    write, so a repeated prompt stays bounded. The number of evals is not capped
    by anything: a one-off prompt leaves its directory for good.

    Two directories grow this way, and only one used to be reported. `co ai`
    writes to ~/.co/evals; the library's logger writes to the PROJECT's
    .co/evals whenever an agent runs inside a project, which is the normal case
    for `Agent(...)` — the shipped quickstart from a fresh `co init` put its eval
    in <project>/.co/evals/.

    On the machine this was written on, ~/.co/evals held 857 evals across 227 MB
    and nothing in `co doctor` or `co status` mentioned it — the largest thing
    `co` writes was the one thing the diagnostic did not report.

    A note, not a problem row, and not a deletion: which evals are worth keeping
    is the user's call. Not being able to see the size is what stops them making
    it. Quiet below the threshold, because a line printed every run is a line
    nobody reads.
    """
    # Both places, because they are different growths. `co ai` writes to
    # ~/.co/evals, and the library's logger writes to the PROJECT's .co/evals
    # whenever an agent runs inside a project — which is the normal case for
    # `Agent(...)`. Measured on this machine: ~/.co/evals held 1085 evals across
    # 237 MB while the project directory beside it held its own, and only the
    # first was ever reported. A project that crossed the threshold said nothing.
    candidates = [("~/.co/evals", Path.home() / ".co" / "evals")]
    project = project_co_dir()
    if project:
        here = project / "evals"
        if here.resolve() != (Path.home() / ".co" / "evals").resolve():
            # _shown, not the absolute path: this panel is narrow, and the helper
            # exists because resolving the project properly once made these rows
            # print the machine's whole directory tree. An absolute path here
            # wrapped so far that the note began mid-sentence with "holds 3
            # evals across 42 MB" and never said which directory.
            candidates.append((_shown(here), here))

    notes = [_evals_note(label, path) for label, path in candidates]
    notes = [n for n in notes if n]
    return "  ".join(notes) if notes else None


def _evals_note(label: str, evals: Path) -> "str | None":
    """The note for one evals directory, or None if it is absent or small."""
    if not evals.is_dir():
        return None

    # scandir, not rglob+stat: the directory entry already carries the size, so
    # this does not stat() every file. 0.05s against 0.145s on the 227 MB that
    # prompted this — and the cost grows with the directory, which is exactly the
    # case this note exists for.
    total = 0
    count = 0
    stack = [str(evals)]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                    if entry.name.endswith(".yaml") and Path(entry.path).parent == evals:
                        count += 1

    megabytes = total / (1024 * 1024)
    if megabytes < EVALS_NOTE_THRESHOLD_MB:
        return None

    return (f"{label} holds {count} evals across {megabytes:.0f} MB — "
            f"runs within one eval are capped, the number of evals is not. "
            f"Delete the ones you no longer want.")


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

    disk = disk_usage_note()
    if disk:
        config_table.add_row("Disk", f"[yellow]○[/yellow] {disk}")

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

    from ...useful_tools.browser_tools.browser import (
        driver_stealth_status, installed_browser_path,
    )
    status, browser_version, detail = driver_stealth_status()
    # The package being healthy says nothing about there being a browser to
    # launch. A deployed agent reported "Patchright ✓ / Stealth driver ✓ /
    # nothing wrong" while every browser command answered "Executable doesn't
    # exist at .../chromium-1228/chrome-linux64/chrome".
    browser_binary = installed_browser_path() if status != "missing" else None
    if status == "ok":
        browser_table.add_row("Patchright", f"[green]✓[/green] {browser_version}")
        browser_table.add_row("Stealth driver", f"[green]✓[/green] {detail}")
    elif status == "broken":
        browser_table.add_row("Patchright", f"[yellow]○[/yellow] {browser_version}")
        browser_table.add_row("Stealth driver", f"[red]✗[/red] {detail}")
        found.append(f"stealth driver: {detail}")
    else:  # missing
        browser_table.add_row("Patchright", f"[yellow]○[/yellow] {detail}")

    if status != "missing":
        if browser_binary:
            browser_table.add_row("Browser binary", f"[green]✓[/green] {browser_binary}")
        else:
            browser_table.add_row(
                "Browser binary",
                "[red]✗[/red] none installed — run: patchright install chromium")
            found.append("no browser is installed — run: patchright install chromium")

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
        selected_backend = backend_url()
        try:
            response = requests.get(f"{selected_backend}/health", timeout=5)
        except requests.exceptions.RequestException as exc:
            connectivity_table.add_row("Backend", f"[red]✗[/red] Could not reach {selected_backend}")
            found.append(f"backend unreachable ({type(exc).__name__})")
        else:
            if response.status_code == 200:
                connectivity_table.add_row("Backend", f"[green]✓[/green] {selected_backend}")
            else:
                connectivity_table.add_row("Backend", f"[yellow]⚠[/yellow] Status {response.status_code}")

        # Signed as whoever this project acts as. This worked the same rule
        # out a second time, in the same file -- so the identity the panel
        # names above and the identity it authenticates as here were decided
        # independently, and doctor could report on an account that is not the
        # one in question.
        from ...project import project_identity

        addr_data = project_identity()
        if addr_data:
            from ... import address
            import time


            public_key = addr_data["address"]
            timestamp = int(time.time())
            message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
            signature = address.sign(addr_data, message.encode()).hex()

            try:
                response = requests.post(
                    f"{selected_backend}/api/v1/auth",
                    json={
                        "public_key": public_key,
                        "signature": signature,
                        "message": message
                    },
                    timeout=5
                )
            except requests.exceptions.RequestException:
                connectivity_table.add_row("Authentication", "[red]✗[/red] Backend unreachable")
            else:
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
