"""
Purpose: Entry point for ConnectOnion CLI application using Typer framework with Rich formatting
LLM-Note:
  Dependencies: imports from [typer, rich.console, typing, __version__] | imported by [__main__.py] | the `co` and `connectonion` commands come from pyproject.toml [project.scripts] -> connectonion.cli.main:cli; there is no setup.py in this repo | loads commands from [cli/commands/{init, create, deploy, auth, status, reset, doctor, browser}_commands.py] | tested by [tests/e2e/cli/test_cli_help.py]
  Data flow: cli() entry point → creates Typer app → registers command callbacks (init, create, deploy, auth, status, reset, doctor, browser) → Typer parses args (including status --reveal/-r) → invokes corresponding handle_*() function from commands module → command outputs via rich.Console
  State/Effects: no persistent state | writes to stdout via rich.Console | lazy imports command handlers on invocation | registers typer.Option and typer.Argument decorators | uses typer.Exit() for early termination
  Integration: exposes cli() entry point registered in pyproject.toml [project.scripts] as the 'co' and 'connectonion' commands | app() is the Typer instance | commands: init, create, deploy (-t/--template, --skills repeatable, --name for template deploys), auth [google|microsoft], status (--reveal/-r), reset, doctor, browser | --version flag shows version | -b/--browser flag shortcuts browser command | no args shows custom help via _show_help()
  Performance: fast startup (lazy imports) | Typer arg parsing is O(n) args | Rich console initialization is lightweight
  Errors: typer.Exit() on --version or --browser | invalid commands show Typer error with suggestions | command-specific errors handled in respective handlers
"""

import sys

# Windows consoles and pipes default to a legacy codepage (cp1252): any emoji or
# box-drawing character in CLI output then raises UnicodeEncodeError and crashes
# the command — including when co is driven through a pipe by another tool
# (Claude Code, codex, CI). Reconfigure this CLI process's own streams to UTF-8
# with replacement before anything prints. Caught by the windows-e2e CI job.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

import re
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

# From _version, not from the package: `from .. import __version__` pulled in
# the OpenAI and Anthropic SDKs before the CLI had parsed an argument, which
# is what every command handler being imported inside its function was for.
from .._version import __version__
from ..core.usage import DEFAULT_MODEL

# Package startup already loads project-root .env, then global keys.env,
# without overriding the process environment. Do not reload cwd/.env here:
# inside a subdirectory it belongs to neither the selected project nor identity.

console = Console()


class _OneSuggestion(typer.core.TyperGroup):
    """Answer a mistyped command once (#714).

        $ co skil
        No such command 'skil'. Did you mean 'skills'? Did you mean 'skills'?

    Two layers each append one: Click builds the message with its own suggestion
    and Typer's resolve_command adds a second to whatever Click produced. It read
    that way at every level, including the nested `co outlook contact` group.

    The two arrive by different routes, which is why this does not just switch a
    layer off. Click 8.4's NoSuchCommand keeps `possibilities` and appends the
    clause when the message is *rendered*:

        def format_message(self):
            if not self.possibilities:
                return self.message
            return f"{self.message} {_format_possibilities(self.possibilities)}"

    while Typer writes its own copy into `.message` beforehand. So the fix is to
    drop the text copy exactly when the exception is going to render one of its
    own, and to leave it alone when it is not.

    Which layer speaks is not stable: turning Typer's `suggest_commands` off
    fixed this on typer 0.20 and left plain `No such command 'skil'.` on 0.27,
    where Typer's is the only clause because Click gets no possibilities.
    pyproject asks for `typer>=0.20.0`, so a user has either.
    """

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except Exception as error:
            # Not `except click.UsageError`: typer 0.27 vendors its own Click
            # (typer._click), so the exception it raises is a different class from
            # the installed click's and the handler would silently never run —
            # inert in exactly the version where CI runs. Catching broadly is safe
            # because this always re-raises and only touches an object carrying
            # both of the attributes it is about to use.
            if getattr(error, "possibilities", None) and hasattr(error, "message"):
                error.message = _SUGGESTION_RE.sub("", error.message).rstrip()
            raise


_SUGGESTION_RE = re.compile(r"\s*Did you mean [^?]*\?")


def _typer_app(**kwargs) -> typer.Typer:
    """Every group in this CLI. One place, so no sub-app is left behind.

    The doubling above was present on all twelve groups, and a fix applied at
    the call sites is a fix that the thirteenth group will not get.
    """
    return typer.Typer(cls=_OneSuggestion, **kwargs)


# pretty_exceptions_show_locals defaults to True in Typer, which dumps every
# local variable of every frame on an uncaught exception. The OAuth paths hold
# OPENONION_API_KEY, refresh tokens and access tokens in locals, so a routine
# "session expired" crash printed live credentials into the terminal — and from
# there into scrollback, CI logs, and any error output a user pastes into a
# chat or an issue.
app = _typer_app(
    add_completion=False,
    no_args_is_help=False,
    pretty_exceptions_show_locals=False,
)


def version_callback(value: bool):
    if value:
        console.print(f"co {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", callback=version_callback, is_eager=True),
):
    """ConnectOnion - A simple Python framework for creating AI agents."""
    if ctx.invoked_subcommand is None:
        _show_help()


def _show_help():
    """Show help message."""
    console.print()
    console.print(f"[bold cyan]co[/bold cyan] - ConnectOnion v{__version__}")
    console.print()
    console.print("A simple Python framework for creating AI agents.")
    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print("  [cyan]co create my-agent[/cyan]                Create new agent project")
    console.print("  [cyan]cd my-agent && python agent.py[/cyan]   Run your agent")
    console.print()
    # A selection, not the register. Eight real commands are not here — ai,
    # announce, call, reset, server, setup, skills, sub — and calling this
    # "Commands:" read as the whole list. `co --help` is generated from the
    # commands themselves and does show all of them, so the honest fix is to
    # say which of the two this is and point at the other. Which of the eight
    # belong on a new user's first screen is a product call, not this one's.
    console.print("[bold]Common commands:[/bold]")
    console.print("  [green]create[/green]  <name>     Create new project")
    console.print("  [green]init[/green]   [path]     Set up global keys, or an explicit project directory")
    console.print("  [green]copy[/green]   <name>     Copy tool/plugin source to project")
    console.print("  [green]eval[/green]              Run evals and show status")
    console.print("  [green]trust[/green]             Manage trust lists")
    console.print("  [green]deploy[/green]            Deploy to ConnectOnion Cloud")
    console.print("  [green]auth[/green]              Authenticate for managed keys")
    console.print("  [green]email[/green]             Send and read agent email")
    console.print("  [green]sms[/green]               Pair a phone and read encrypted SMS")
    console.print("  [green]transfer[/green]          Send credits to another agent address")
    console.print("  [green]gmail[/green]             Send and read Gmail (co auth google)")
    console.print("  [green]telegram[/green]          Telegram bot as a mailbox: listen, receive, send, reply")
    console.print("  [green]feishu[/green]            Feishu bot as a mailbox: listen, receive, send, reply")
    console.print("  [green]gdrive[/green]            List and transfer Google Drive files (co auth google)")
    console.print("  [green]syno[/green]              Browse and transfer Synology NAS files (co syno login)")
    console.print("  [green]outlook[/green]           Manage Outlook email and contacts (co auth microsoft)")
    console.print("  [green]browser[/green]           Drive a browser (run: co browser help)")
    console.print("  [green]keys[/green]              Show agent keys and credentials")
    console.print("  [green]status[/green]            Check credentials, account, and deployments")
    console.print("  [green]doctor[/green]            Diagnose installation")
    console.print()
    console.print("  [dim]co --help[/dim]         All commands")
    console.print()
    console.print("[bold]Docs:[/bold] https://docs.connectonion.com")
    console.print("[bold]Discord:[/bold] https://discord.gg/4xfD9k8AUF")
    console.print()


@app.command()
def init(
    path: Optional[Path] = typer.Argument(None, exists=True, file_okay=False, resolve_path=True,
                                         help="Existing project directory; omit for global ~/.co/keys.env"),
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Project template: co-ai, custom (default: config only)"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
):
    """Initialize global ~/.co/keys.env, or use co init ./ for a project."""
    from .commands.init import handle_global_init, handle_init
    if path is None:
        if template is not None or description is not None or force:
            console.print("[red]Project options require a path, for example: co init ./ --template co-ai[/red]")
            raise typer.Exit(2)
        handle_global_init(key=key)
        return
    handle_init(ai=None, key=key, template=template, description=description, yes=yes, force=force, path=path)


@app.command()
def create(
    name: Optional[str] = typer.Argument(None, help="Project name"),
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Template: co-ai (default), custom"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
):
    """Create new project."""
    from .commands.create import handle_create
    # An explicit False means the project was not created — exit non-zero so a
    # script can tell. Other return values keep the previous behaviour.
    if handle_create(name=name, ai=None, key=key, template=template,
                     description=description, yes=yes) is False:
        raise typer.Exit(1)


@app.command()
def deploy(
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Create and deploy a template project"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skill directory (contains SKILL.md) or directory of skills to bundle into .co/skills/ (repeatable: --skills a --skills b)"),
    name: Optional[str] = typer.Option(None, "--name", help="Project name for template deploys (default: {template}-agent)"),
    to: Optional[str] = typer.Option(None, "--to", help="Deploy onto a server you own (see: co server ls)"),
    own_identity: bool = typer.Option(False, "--own-identity", help="With --to, let the agent mint its own identity instead of deriving it from your recovery phrase — for an agent you are handing to someone else"),
):
    """Deploy to ConnectOnion Cloud, or with --to onto a server you own."""
    if to:
        # A different destination, not a variant of the same one: this path holds
        # no container and never touches the server's .co/ state.
        if template or skills or name:
            console.print("[red]--to cannot be combined with --template, --skills or --name.[/red]")
            console.print("[dim]Those belong to the cloud deploy. --to syncs the project you are in.[/dim]")
            raise typer.Exit(2)
        from .commands.deploy_to_server import handle_deploy_to
        if not handle_deploy_to(server=to, own_identity=own_identity):
            raise typer.Exit(1)
        return

    if own_identity:
        console.print("[red]--own-identity only applies with --to.[/red]")
        console.print("[dim]A Cloud deploy does not carry an identity you derived.[/dim]")
        raise typer.Exit(2)

    from .commands.deploy_commands import handle_deploy
    handle_deploy(template=template, skills=skills, name=name)


@app.command()
def auth(service: Optional[str] = typer.Argument(None, help="Service: google, microsoft")):
    """Authenticate with OpenOnion."""
    if service == "google":
        from .commands.auth_commands import handle_google_auth
        handle_google_auth()
    elif service == "microsoft":
        from .commands.auth_commands import handle_microsoft_auth
        handle_microsoft_auth()
    else:
        from .commands.auth_commands import handle_auth
        handle_auth()


@app.command()
def keys(
    reveal: bool = typer.Option(False, "--reveal", "-r", help="Show full key values"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Print the address an agent of this name will have, before it is deployed"),
    ssh: bool = typer.Option(False, "--ssh", help="Print the SSH public key derived from your recovery phrase"),
    write: bool = typer.Option(False, "--write", help="With --ssh, also write the private half to ~/.ssh/"),
):
    """Show agent keys and credentials."""
    if agent:
        from .commands.server_commands import derived_agent_identity
        identity = derived_agent_identity(agent)
        if not identity:
            console.print("\n[red]No recovery phrase to derive from.[/red]")
            console.print("[cyan]co init[/cyan] first.\n")
            raise typer.Exit(1)
        console.print(f"\n[cyan]{identity['address']}[/cyan]")
        console.print(f"[dim]agent://{agent} — the address this name will have, "
                      f"on any machine, before or after it exists[/dim]\n")
        return

    from .commands.keys_commands import handle_keys
    handle_keys(reveal=reveal, ssh=ssh, write=write)


@app.command()
def status(
    reveal: bool = typer.Option(
        False,
        "--reveal",
        "-r",
        help="Show full provider credential values",
    ),
):
    """Check credential sources, account status, and deployments."""
    from .commands.status_commands import handle_status
    handle_status(reveal=reveal)


@app.command()
def reset():
    """Reset account (destructive)."""
    from .commands.reset_commands import handle_reset
    handle_reset()


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Offer safe browser/runtime repairs"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve every offered repair"),
    json_output: bool = typer.Option(False, "--json", help="Emit stable machine-readable output"),
):
    """Diagnose installation."""
    if yes and not fix:
        console.print("[red]--yes requires --fix.[/red]")
        raise typer.Exit(2)
    from .commands.doctor_commands import handle_doctor
    # The exit code is the whole point of running this in a script: it used to
    # be 0 even under its own `✗ broken symlink`.
    if handle_doctor(fix=fix, yes=yes, json_output=json_output):
        raise typer.Exit(1)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def browser(
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser headless"),
    engine: str = typer.Option("auto", "--engine", help="Browser engine: auto, system, or onion"),
    args: List[str] = typer.Argument(None, help="Browser function + args, or: do \"<instruction>\""),
):
    """Drive one persistent browser. Run a function directly (co browser go_to x.com),
    use `do` for the AI agent (co browser do "..."), or `co browser help` to list functions."""
    from .commands.browser_commands import handle_browser
    raise typer.Exit(handle_browser(args or [], headless=headless, engine_mode=engine))


@app.command(
    "remote-browser",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def remote_browser(
    args: List[str] = typer.Argument(
        None, help="config <address> [--proxy shared] | [<address>] <start|status|sessions|stop|diagnose>"
    ),
):
    """Manage an owner-bound browser session on a remote agent over OIP."""
    from .commands.remote_browser_commands import handle_remote_browser

    raise typer.Exit(handle_remote_browser(args or []))


@app.command(
    "proxy",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def proxy(
    args: List[str] = typer.Argument(
        None, help="share to <address> | status | stop <address> | diagnose <address>"
    ),
):
    """Share this computer's internet connection with an authorized agent."""
    from .commands.proxy_commands import handle_proxy

    raise typer.Exit(handle_proxy(args or []))


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def call(
    args: List[str] = typer.Argument(None, help="[--out F] [--timeout S] [--relay U] <address> <command...>"),
):
    """Run one command on a remote agent and print the result (no LLM).

    The remote twin of `co browser` — everything after the address runs on the
    remote agent as a bash command, gated by its .co/host.yaml whitelist:

        co call 0x3d40... co status
        co call --out shot.png 0x3d40... co browser take_screenshot

    Bare `co`, not `.venv/bin/co`: the whitelist entry is `Bash(co *)`, and the
    unit file puts the venv on PATH so that name resolves. The path form is the
    one that gets refused.

    Note this sends bash, not a tool call: a whitelist entry for the `read` TOOL
    does not permit a `read` command, and vice versa.
    """
    from .commands.call_commands import handle_call
    raise typer.Exit(handle_call(args or []))


@app.command()
def ai(
    prompt: Optional[str] = typer.Argument(None, help="One-shot prompt (runs and exits)"),
    port: int = typer.Option(8000, "--port", "-p", help="Port for web server"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    max_iterations: int = typer.Option(100, "--max-iterations", "-i", help="Max iterations"),
    full_access: bool = typer.Option(
        False,
        "--full-access",
        help="Bypass tool approvals for this bounded user-driven turn budget",
    ),
    full_access_turns: int = typer.Option(
        100,
        "--full-access-turns",
        min=1,
        help="User-driven turns before Full access expires to Auto",
    ),
    evaluate: bool = typer.Option(
        False,
        "--eval",
        help="Score task completion with two extra model calls",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit one machine-readable JSON result"
    ),
    resume: Optional[str] = typer.Option(
        None, "--resume", help="Resume a prior one-shot session"
    ),
    invite_code: Optional[str] = typer.Option(
        None, "--invite-code", help="Invite code for this web-server run only"
    ),
    invite_code_file: Optional[Path] = typer.Option(
        None, "--invite-code-file", help="Read this run's invite code from a file"
    ),
):
    """Start AI coding agent or run one-shot prompt."""
    from .commands.ai_commands import handle_ai
    handle_ai(
        prompt=prompt,
        port=port,
        model=model,
        max_iterations=max_iterations,
        full_access=full_access,
        full_access_turns=full_access_turns,
        evaluate=evaluate,
        json_output=json_output,
        resume=resume,
        invite_code=invite_code,
        invite_code_file=invite_code_file,
    )


@app.command()
def copy(
    names: List[str] = typer.Argument(None, help="Tool or plugin names to copy"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List available items"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Custom destination path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
):
    """Copy built-in tools/plugins to customize."""
    from .commands.copy_commands import handle_copy
    handle_copy(names=names or [], list_all=list_all, path=path, force=force)


@app.command()
def eval(
    name: Optional[str] = typer.Argument(None, help="Specific eval name"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent file (overrides YAML)"),
):
    """Run evals and show results."""
    from .commands.eval_commands import handle_eval

    # The exit code is the point of #682: `co eval` returned 0 after a run
    # where nothing executed. Discarding it here would leave that fix
    # unreachable from a shell, which is where CI reads it.
    raise typer.Exit(code=handle_eval(name=name, agent_file=agent) or 0)


@app.command()
def setup(
    bio: Optional[str] = typer.Option(None, "--bio", "-b", help="One-line bio for ~/.co/agent.json"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Alias/name for ~/.co/agent.json (default: $USER)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing ~/.co/agent.json (backs up to .bak)"),
    skip_skills: bool = typer.Option(False, "--no-skills", help="Skip ~/.co/skills/ library refresh"),
):
    """Set up your global ~/.co/ — identity, agent.json, and skill library."""
    from .commands.setup_commands import handle_setup
    handle_setup(name=name, bio=bio, force=force, skip_skills=skip_skills)


@app.command()
def announce(
    relay: Optional[str] = typer.Option(None, "--relay", "-r", help="Relay URL (default: configured backend)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the signed message, don't send"),
):
    """Publish ~/.co/agent.json + SKILL.md bodies (publish:true) to the relay."""
    from .commands.announce_commands import handle_announce
    handle_announce(relay=relay, dry_run=dry_run)


# Server command group — the machines `co deploy --to` can target
server_app = _typer_app(help="Register, list and preflight the servers you can deploy to")
app.add_typer(server_app, name="server")


@server_app.callback(invoke_without_command=True)
def server_callback(ctx: typer.Context):
    """Deploy targets."""
    if ctx.invoked_subcommand is None:
        from .commands.server_commands import handle_server_list
        handle_server_list()


@server_app.command("add")
def server_add(
    name: str = typer.Argument(..., help="Short name you will pass to co deploy --to"),
    ssh: str = typer.Option(..., "--ssh", help="ssh target, e.g. user@1.2.3.4 or a Host from ~/.ssh/config"),
):
    """Register a machine. Stores a name → ssh target mapping, no credential."""
    from .commands.server_commands import handle_server_add
    if not handle_server_add(name=name, ssh_target=ssh):
        raise typer.Exit(1)


@server_app.command("ls")
def server_ls():
    """Show what you can deploy to."""
    from .commands.server_commands import handle_server_list
    handle_server_list()


@server_app.command("check")
def server_check(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Preflight a target and name the requirement that failed."""
    from .commands.server_commands import handle_server_check
    if not handle_server_check(name=name):
        raise typer.Exit(1)


@server_app.command("new")
def server_new(
    name: str = typer.Argument(..., help="Short name you will pass to co deploy --to"),
    machine: Optional[str] = typer.Option(None, "--machine", help="Machine type (default: the smallest)"),
    region: Optional[str] = typer.Option(None, "--region",
                                         help="Where to provision (default: australia-southeast1)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the price confirmation"),
):
    """Have a server created for you. Charges 12 months of credit up front."""
    from .commands.server_commands import handle_server_new
    if not handle_server_new(name=name, machine_type=machine, region=region, yes=yes):
        raise typer.Exit(1)


@server_app.command("ssh")
def server_ssh(
    name: str = typer.Argument(..., help="Registered server name"),
    command: Optional[str] = typer.Argument(None, help="Command to run instead of opening a shell"),
):
    """Open a shell on a registered server, or run one command there."""
    from .commands.server_commands import handle_server_ssh
    if not handle_server_ssh(name=name, command=command):
        raise typer.Exit(1)


@server_app.command("fix-key")
def server_fix_key(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Reinstall your SSH key on a server you own, without recreating it."""
    from .commands.server_commands import handle_server_fix_key
    if not handle_server_fix_key(name=name):
        raise typer.Exit(1)


@server_app.command("forget")
def server_forget(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Drop the local entry. Does NOT touch the machine or stop any billing."""
    from .commands.server_commands import handle_server_forget
    if not handle_server_forget(name=name):
        raise typer.Exit(1)


@server_app.command("destroy")
def server_destroy(
    name: str = typer.Argument(..., help="Server to tear down"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation"),
):
    """Destroy the machine and stop the billing. The unused term is refunded."""
    from .commands.server_commands import handle_server_destroy
    if not handle_server_destroy(name=name, yes=yes):
        raise typer.Exit(1)


# Skills command group
skills_app = _typer_app(help="Discover, copy, and list SKILL.md files from agent tool directories")
app.add_typer(skills_app, name="skills")


@skills_app.callback(invoke_without_command=True)
def skills_callback(ctx: typer.Context):
    """Skill discovery and management."""
    if ctx.invoked_subcommand is None:
        from .commands.skills_commands import handle_skills_list
        handle_skills_list()


@skills_app.command("discover")
def skills_discover(
    no_save: bool = typer.Option(False, "--no-save", help="Don't write ~/.co/skills/index.json"),
    json_out: bool = typer.Option(False, "--json", help="Print index as JSON"),
    include_namespaced: bool = typer.Option(False, "--include-namespaced", help="Include plugin-namespaced skills (names with ':')"),
):
    """Scan ~/.claude, ~/.codex, ~/.cursor, ~/.kiro, .co/skills for SKILL.md files."""
    from .commands.skills_commands import handle_skills_discover
    handle_skills_discover(save=not no_save, json_out=json_out, include_namespaced=include_namespaced)


@skills_app.command("copy")
def skills_copy(
    names: List[str] = typer.Argument(None, help="Skill names to copy into ~/.co/skills/"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Restrict to a specific source (claude, codex, cursor, kiro, co-user, co-project)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skill"),
    all_: bool = typer.Option(False, "--all", "-a", help="Copy every discovered skill (dedupe by SOURCES priority)"),
    to_project: bool = typer.Option(False, "--to-project", help="Copy into this project's .co/skills/ — the only tier that deploys"),
):
    """Copy a discovered skill into ~/.co/skills/<name>/, or --to-project to ship it."""
    from .commands.skills_commands import handle_skills_copy
    handle_skills_copy(names=names or [], source=source, force=force, all_=all_,
                       to_project=to_project)


@skills_app.command("manifest")
def skills_manifest(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Skills directory to scan (default: ~/.co/skills/)"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write to file (default: merge into ~/.co/agent.json); if path ends in agent.json, merge into its skills[] key"),
    stdout: bool = typer.Option(False, "--stdout", help="Print JSON to stdout instead of writing"),
):
    """Build skill metadata for oo-publish."""
    from .commands.skills_commands import handle_skills_manifest
    handle_skills_manifest(path=path, out=out, stdout=stdout)


@skills_app.command("list")
def skills_list():
    """List skills currently installed in ~/.co/skills/."""
    from .commands.skills_commands import handle_skills_list
    handle_skills_list()


@skills_app.command("link")
def skills_link(
    force: bool = typer.Option(False, "--force", help="Replace directories you own"),
):
    """Link ConnectOnion's bundled skills into Claude Code and Codex."""
    from .commands.skills_commands import handle_skills_link
    handle_skills_link(force=force)


# Trust command group
trust_app = _typer_app(help="Manage trust lists (contacts, whitelist, blocklist, admins)")
app.add_typer(trust_app, name="trust")


@trust_app.callback(invoke_without_command=True)
def trust_callback(ctx: typer.Context):
    """Trust list management."""
    if ctx.invoked_subcommand is None:
        # Default to list
        from .commands.trust_commands import handle_trust_list
        handle_trust_list()


@trust_app.command("list")
def trust_list():
    """List all trust lists."""
    from .commands.trust_commands import handle_trust_list
    handle_trust_list()


@trust_app.command("level")
def trust_level(address: str = typer.Argument(..., help="Address to check")):
    """Check trust level of an address."""
    from .commands.trust_commands import handle_trust_level
    handle_trust_level(address)


@trust_app.command("add")
def trust_add(
    address: str = typer.Argument(..., help="Address to add"),
    whitelist: bool = typer.Option(False, "-w", "--whitelist", help="Add to whitelist instead of contacts"),
):
    """Add address to contacts (default) or whitelist."""
    from .commands.trust_commands import handle_trust_add
    handle_trust_add(address, whitelist)


@trust_app.command("remove")
def trust_remove(address: str = typer.Argument(..., help="Address to remove")):
    """Remove address from all lists (demote to stranger)."""
    from .commands.trust_commands import handle_trust_remove
    handle_trust_remove(address)


@trust_app.command("block")
def trust_block(
    address: str = typer.Argument(..., help="Address to block"),
    reason: str = typer.Option("", "-r", "--reason", help="Reason for blocking"),
):
    """Block an address."""
    from .commands.trust_commands import handle_trust_block
    handle_trust_block(address, reason)


@trust_app.command("unblock")
def trust_unblock(address: str = typer.Argument(..., help="Address to unblock")):
    """Unblock an address."""
    from .commands.trust_commands import handle_trust_unblock
    handle_trust_unblock(address)


# Admin subcommand group
admin_app = _typer_app(help="Manage admins (super admin only)")
trust_app.add_typer(admin_app, name="admin")


@admin_app.command("add")
def admin_add(address: str = typer.Argument(..., help="Address to add as admin")):
    """Add an admin."""
    from .commands.trust_commands import handle_admin_add
    handle_admin_add(address)


@admin_app.command("remove")
def admin_remove(address: str = typer.Argument(..., help="Address to remove from admins")):
    """Remove an admin."""
    from .commands.trust_commands import handle_admin_remove
    handle_admin_remove(address)


# SMS command group. `co sms` (no args) shows the inbox without changing state.
sms_app = _typer_app(help="Pair a phone and read the Agent's encrypted SMS inbox")
app.add_typer(sms_app, name="sms")


@sms_app.callback(invoke_without_command=True)
def sms_callback(ctx: typer.Context):
    """With no subcommand, show the inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.sms_commands import handle_sms_inbox
        handle_sms_inbox()


@sms_app.command("pair")
def sms_pair(
    expires: int = typer.Option(
        600, "--expires", min=60, max=1800,
        help="One-time challenge lifetime in seconds",
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait",
        help="Wait to compare and approve the phone's six-digit code",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON and do not wait"),
):
    """Create an Agent-signed QR challenge for one Android phone."""
    from .commands.sms_commands import handle_sms_pair
    handle_sms_pair(expires=expires, wait=wait and not json_output, json_output=json_output)


@sms_app.command("inbox")
def sms_inbox(
    last: int = typer.Option(10, "--last", "-n", min=1, max=100),
    pending: bool = typer.Option(False, "--pending", help="Only unacknowledged messages"),
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON"),
):
    """List decrypted SMS without acknowledging them."""
    from .commands.sms_commands import handle_sms_inbox
    handle_sms_inbox(last=last, pending=pending, json_output=json_output)


sms_devices_app = _typer_app(help="List and revoke paired SMS phones")
sms_app.add_typer(sms_devices_app, name="devices")


@sms_devices_app.callback(invoke_without_command=True)
def sms_devices_callback(ctx: typer.Context, json_output: bool = typer.Option(False, "--json")):
    """With no subcommand, list paired phones."""
    if ctx.invoked_subcommand is None:
        from .commands.sms_commands import handle_sms_devices
        handle_sms_devices(json_output=json_output)


@sms_devices_app.command("revoke")
def sms_devices_revoke(
    device_id: str = typer.Argument(..., help="Device UUID from co sms devices"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
):
    """Revoke one phone's upload credential."""
    from .commands.sms_commands import handle_sms_revoke
    handle_sms_revoke(device_id, yes=yes)


# Email command group. `co email` (no args) shows the inbox.
email_app = _typer_app(help="Send and read email from the agent's address")
app.add_typer(email_app, name="email")


@email_app.callback(invoke_without_command=True)
def email_callback(ctx: typer.Context):
    """With no subcommand, show the inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.email_commands import handle_email_inbox
        handle_email_inbox()


@email_app.command("send")
def email_send(
    to: str = typer.Argument(..., help="Recipient email address"),
    subject: str = typer.Argument(..., help="Subject line"),
    message: str = typer.Argument(..., help="Body (plain text or HTML)"),
    idempotency_key: Optional[str] = typer.Option(
        None,
        "--idempotency-key",
        help="Reuse a failed send's key to retry without sending twice",
    ),
    from_address: Optional[str] = typer.Option(
        None,
        "--from",
        help="Send as one of your owned addresses (server checks ownership)",
    ),
):
    """Send an email from the agent's address."""
    from .commands.email_commands import handle_email_send
    handle_email_send(
        to, subject, message,
        idempotency_key=idempotency_key, from_address=from_address,
    )


@email_app.command("inbox")
def email_inbox(
    last: int = typer.Option(
        10,
        "--last",
        "-n",
        min=1,
        max=1000,
        help="How many received emails to show in this page (1-1000)",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
        help="Skip this many newer emails",
    ),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread emails"),
):
    """List recent received emails."""
    from .commands.email_commands import handle_email_inbox
    handle_email_inbox(last=last, offset=offset, unread=unread)


@email_app.command("read")
def email_read(
    email_id: str = typer.Argument(..., help="Email # from the inbox list"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
):
    """Show one email's body without changing its unread state."""
    from .commands.email_commands import handle_email_read
    handle_email_read(email_id, mark_read=mark_read)


sent_app = _typer_app(help="List and read emails the agent has sent")
email_app.add_typer(sent_app, name="sent")


@sent_app.callback(invoke_without_command=True)
def email_sent(
    ctx: typer.Context,
    last: int = typer.Option(10, "--last", "-n", help="How many emails to show"),
    to: str = typer.Option(None, "--to", help="Only emails sent to this address"),
):
    """With no subcommand, list recent sent emails."""
    if ctx.invoked_subcommand is None:
        from .commands.email_commands import handle_email_sent
        handle_email_sent(last=last, to=to)


@sent_app.command("read")
def email_sent_read(email_id: str = typer.Argument(..., help="Email # from the sent list")):
    """Show one sent email's body."""
    from .commands.email_commands import handle_email_sent_read
    handle_email_sent_read(email_id)


@email_app.command("addresses")
def email_addresses():
    """List every email address this account owns, marking the default sender."""
    from .commands.email_commands import handle_email_addresses
    handle_email_addresses()


@email_app.command("name")
def email_name(
    name: str = typer.Argument(..., help="Desired name, e.g. 'aaron' → aaron@openonion.ai"),
    buy: bool = typer.Option(False, "--buy", help="Claim it (deducts the price from your credits)"),
):
    """Check a custom email name's availability, or --buy to claim it."""
    from .commands.email_commands import handle_email_name
    handle_email_name(name, buy=buy)


@email_app.command("share")
def email_share(
    address: Optional[str] = typer.Argument(None, help="One of your addresses (omit with --list)"),
    with_: Optional[str] = typer.Option(None, "--with", help="Grantee: public key or one of their addresses"),
    can: Optional[str] = typer.Option(None, "--can", help="Comma-separated capabilities: send,read"),
    list_: bool = typer.Option(False, "--list", help="Show what you've shared, and what's shared with you"),
):
    """Let another account send and/or read as one of your addresses, without moving it."""
    from .commands.email_commands import handle_email_share
    handle_email_share(address, with_=with_, can=can, list_=list_)


@email_app.command("unshare")
def email_unshare(
    address: str = typer.Argument(..., help="One of your addresses"),
    with_: str = typer.Option(..., "--with", help="Grantee to revoke: public key or one of their addresses"),
):
    """Revoke a grant. No key rotation — the address was never shared, only access to it."""
    from .commands.email_commands import handle_email_unshare
    handle_email_unshare(address, with_=with_)


@email_app.command("upgrade")
def email_upgrade(
    tier: str = typer.Argument(..., help="Tier: plus or pro"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Sending domain (plus/pro)"),
    alias: Optional[str] = typer.Option(None, "--alias", "-a", help="Mailbox alias, e.g. 'aaron'"),
    keep_address: bool = typer.Option(
        False,
        "--keep-address",
        help="Increase quota while preserving an existing @mail.openonion.ai address (plus only)",
    ),
):
    """Upgrade email tier — deducts the monthly price from your credits."""
    from .commands.email_commands import handle_email_upgrade
    handle_email_upgrade(tier, domain=domain, alias=alias, keep_address=keep_address)


# One command, not a group: a group callback with positional arguments would
# swallow "list" as the address ('co transfer list' parses the group args
# first), so the listing mode is the literal address "list" instead.
@app.command("transfer")
def transfer(
    address: str = typer.Argument(..., help="Recipient 0x… address, or 'list' for your transfer history"),
    amount: Optional[float] = typer.Argument(None, help="Amount in USD credits, e.g. 5.00"),
    memo: Optional[str] = typer.Option(None, "--memo", help="Note stored with the transfer"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Send without the interactive confirmation"),
    sent: bool = typer.Option(False, "--sent", help="With list: only transfers you sent"),
    received: bool = typer.Option(False, "--received", help="With list: only transfers you received"),
    last: int = typer.Option(50, "--last", "-n", help="With list: how many to show"),
):
    """Send credits to another agent address (irreversible, confirms first), or list transfers."""
    from .commands.transfer_commands import handle_transfer_list, handle_transfer_send
    if address == "list":
        handle_transfer_list(sent=sent, received=received, last=last)
    else:
        handle_transfer_send(address, amount, memo=memo, yes=yes)


# Telegram command group. The bot is the user's own (@BotFather), so the token
# lives in their keys.env -- no OpenOnion credential and nothing billed.
telegram_app = _typer_app(help="Telegram bot as a mailbox: listen, receive, send, reply.")
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("send")
def telegram_send(
    chat: str = typer.Argument(..., help="Chat id, or @channelname for a channel"),
    message: str = typer.Argument(..., help="The text to send"),
):
    """Send a Telegram message."""
    from .commands.telegram_commands import handle_telegram_send
    handle_telegram_send(chat, message)


# Mailbox providers: feishu, lark. One directory per provider under ~/.co/,
# the same eight verbs on each. The tool knows nothing about agents; anything
# that can read a file consumes it (DD-063).
def _mailbox_group(name: str, help_text: str, *, group=None, with_send: bool = True) -> typer.Typer:
    """The eight verbs on a fresh group, or on an existing one that already
    has its own `send` (Telegram shipped `co telegram send` first)."""
    group = group if group is not None else _typer_app(help=help_text)

    @group.command("listen")
    def _listen(raw: bool = typer.Option(False, "--raw", help="Keep the provider payload in inbox.jsonl")):
        """Hold the connection; write every message to the mailbox. Ctrl-C stops."""
        from .commands.listen_commands import handle_listen
        handle_listen(name, raw=raw)

    @group.command("receive")
    def _receive(
        timeout: Optional[float] = typer.Option(None, "--timeout", "-t", help="Seconds to wait; 0 looks once. Exit 124 if none."),
        no_start: bool = typer.Option(False, "--no-start", help="Do not start a background listener"),
    ):
        """Print the next message as one JSON line, taking it from the queue."""
        from .commands.listen_commands import handle_receive
        handle_receive(name, timeout=timeout, start=not no_start)

    def _send(
        chat: str = typer.Argument(..., help="Chat id"),
        text: Optional[str] = typer.Argument(None, help="The text; omitted means stdin"),
        reply_to: Optional[str] = typer.Option(None, "--reply-to", help="Message id to reply to"),
    ):
        """Send text to a chat. Prints the new message id."""
        from .commands.listen_commands import handle_send
        handle_send(name, chat, text, reply_to=reply_to)

    if with_send:
        group.command("send")(_send)

    @group.command("reply")
    def _reply(
        message_id: str = typer.Argument(..., help="Id of a received message"),
        text: Optional[str] = typer.Argument(None, help="The text; omitted means stdin"),
        again: bool = typer.Option(False, "--again", help="Reply even if this message was already answered"),
    ):
        """Reply where a received message was asked. Prints the new id."""
        from .commands.listen_commands import handle_reply
        handle_reply(name, message_id, text, again=again)

    @group.command("done")
    def _done(message_id: str = typer.Argument(..., help="Id of a taken message")):
        """Forget a taken message without replying, so it does not come back in an hour."""
        from .commands.listen_commands import handle_done
        handle_done(name, message_id)

    @group.command("check")
    def _check():
        """Credentials, connectivity, listener state, unread count. Exit 3 on a problem."""
        from .commands.listen_commands import handle_check
        handle_check(name)

    @group.command("ls")
    def _ls():
        """Unread messages: id, chat, sender, text."""
        from .commands.listen_commands import handle_ls
        handle_ls(name)

    @group.command("log")
    def _log(follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing new messages")):
        """Every message ever received, one JSON line each."""
        from .commands.listen_commands import handle_log
        handle_log(name, follow=follow)

    @group.command("serve", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def _serve(
        command: List[str] = typer.Argument(..., help="Command run per message: message on stdin, reply on stdout"),
        once: bool = typer.Option(False, "--once", help="Handle one message and exit"),
    ):
        """Loop: receive, run COMMAND with the message on stdin, reply with its stdout."""
        from .commands.listen_commands import handle_serve
        handle_serve(name, command, once=once)

    return group


app.add_typer(_mailbox_group("feishu", "Feishu bot as a mailbox: listen, receive, send, reply."), name="feishu")
app.add_typer(_mailbox_group("lark", "Lark (global Feishu) bot as a mailbox: listen, receive, send, reply."), name="lark")
# Telegram keeps the `send` it shipped with (its output is part of its contract)
# and gains the other seven verbs on the same group, same token.
_mailbox_group("telegram", "", group=telegram_app, with_send=False)


# Gmail command group. `co gmail` (no args) shows the Gmail inbox.
# Uses the GOOGLE_* OAuth tokens saved to .env by `co auth google`.
gmail_app = _typer_app(help="Send and read email from your Gmail account. Bare 'co gmail' shows the inbox.")
app.add_typer(gmail_app, name="gmail")


@gmail_app.callback(invoke_without_command=True)
def gmail_callback(ctx: typer.Context):
    """With no subcommand, show the Gmail inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.gmail_commands import handle_gmail_inbox
        handle_gmail_inbox()


@gmail_app.command("inbox")
def gmail_inbox(
    last: int = typer.Option(10, "--last", "-n", help="How many emails to show"),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread emails"),
):
    """List recent inbox emails, numbered for read/reply."""
    from .commands.gmail_commands import handle_gmail_inbox
    handle_gmail_inbox(last=last, unread=unread)


@gmail_app.command("read")
def gmail_read(
    email_id: str = typer.Argument(..., help="Email # from the last listing, or a full message id"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
):
    """Show one email's full body without changing its unread state."""
    from .commands.gmail_commands import handle_gmail_read
    handle_gmail_read(email_id, mark_read=mark_read)


@gmail_app.command("reply")
def gmail_reply(
    email_id: str = typer.Argument(..., help="Email # from the last listing, or a full message id"),
    message: str = typer.Argument(..., help="Reply body, or '-' to read stdin"),
):
    """Reply to an email from the last listing."""
    from .commands.gmail_commands import handle_gmail_reply
    handle_gmail_reply(email_id, message)


@gmail_app.command("send", epilog="Examples:  co gmail send a@b.com \"Hi\" \"Quick note\"  |  "
                                  "cat body.txt | co gmail send a@b.com \"Report\" -")
def gmail_send(
    to: str = typer.Argument(..., help="Recipient address (comma-separated for several)"),
    subject: str = typer.Argument(..., help="Email subject"),
    message: str = typer.Argument(..., help="Email body, or '-' to read stdin"),
    cc: str = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: str = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    attach: list[str] = typer.Option(None, "--attach", "-a",
                                     help="File to attach (repeat for several)"),
):
    """Send an email from your Gmail account."""
    from .commands.gmail_commands import handle_gmail_send
    handle_gmail_send(to, subject, message, cc=cc, bcc=bcc, attachments=attach)


@gmail_app.command("sent")
def gmail_sent(
    last: int = typer.Option(10, "--last", "-n", help="How many emails to show"),
):
    """List recently sent emails."""
    from .commands.gmail_commands import handle_gmail_sent
    handle_gmail_sent(last=last)


@gmail_app.command("search")
def gmail_search(
    query: str = typer.Argument(..., help="Gmail search query, e.g. 'from:alice@example.com'"),
    last: int = typer.Option(10, "--last", "-n", help="How many matches to show"),
):
    """Search your mail with Gmail query syntax."""
    from .commands.gmail_commands import handle_gmail_search
    handle_gmail_search(query, last=last)
# Google Drive command group. `co gdrive` (no args) lists recent files.
# Uses the GOOGLE_* OAuth tokens saved to .env by `co auth google`.
gdrive_app = _typer_app(help="List, search, download, and upload Google Drive files. Bare 'co gdrive' lists recent files.")
app.add_typer(gdrive_app, name="gdrive")


@gdrive_app.callback(invoke_without_command=True)
def gdrive_callback(ctx: typer.Context):
    """With no subcommand, list recent Drive files."""
    if ctx.invoked_subcommand is None:
        from .commands.gdrive_commands import handle_gdrive_list
        handle_gdrive_list()


@gdrive_app.command("list")
def gdrive_list(
    last: int = typer.Option(20, "--last", "-n", help="How many files to show"),
):
    """List recently modified files, numbered for get/rm."""
    from .commands.gdrive_commands import handle_gdrive_list
    handle_gdrive_list(last=last)


@gdrive_app.command("search")
def gdrive_search(
    query: str = typer.Argument(..., help="Text to look for in file names"),
    last: int = typer.Option(20, "--last", "-n", help="How many matches to show"),
):
    """Search Drive by file name."""
    from .commands.gdrive_commands import handle_gdrive_search
    handle_gdrive_search(query, last=last)


@gdrive_app.command("get")
def gdrive_get(
    file_id: str = typer.Argument(..., help="File # from the last listing, or a full file id"),
    dest: str = typer.Option(".", "--to", help="Destination directory or file path"),
):
    """Download a file (Google Docs/Sheets/Slides are exported)."""
    from .commands.gdrive_commands import handle_gdrive_get
    handle_gdrive_get(file_id, dest=dest)


@gdrive_app.command("put")
def gdrive_put(
    path: str = typer.Argument(..., help="Local file to upload"),
    name: str = typer.Option(None, "--name", help="Name to give it in Drive"),
):
    """Upload a local file to Drive."""
    from .commands.gdrive_commands import handle_gdrive_put
    handle_gdrive_put(path, name=name)


@gdrive_app.command("rm")
def gdrive_rm(
    file_id: str = typer.Argument(..., help="File # from the last listing, or a full file id"),
):
    """Move a file to the Drive trash (recoverable)."""
    from .commands.gdrive_commands import handle_gdrive_rm
    handle_gdrive_rm(file_id)


# Synology command group. `co syno` (no args) lists your shared folders.
# Uses the SYNOLOGY_* credentials saved to keys.env by `co syno login`.
syno_app = _typer_app(help="Browse, search, download, upload, and share Synology NAS files. Bare 'co syno' lists shared folders.")
app.add_typer(syno_app, name="syno")


@syno_app.callback(invoke_without_command=True)
def syno_callback(ctx: typer.Context):
    """With no subcommand, list your NAS shared folders."""
    if ctx.invoked_subcommand is None:
        from .commands.synology_commands import handle_syno_list
        handle_syno_list()


@syno_app.command("login")
def syno_login(
    url: str = typer.Option(None, "--url", help="Connect directly, e.g. https://nas.local:5001 (skips QuickConnect)"),
):
    """Connect your NAS by QuickConnect ID, or directly with --url."""
    from .commands.synology_commands import handle_syno_login
    handle_syno_login(url=url)


@syno_app.command("ls")
def syno_ls(
    path: str = typer.Argument(None, help="Folder path, e.g. /home/photos. Omit to list shared folders."),
    last: int = typer.Option(20, "--last", "-n", help="How many entries to show"),
):
    """List shared folders, or the contents of one folder."""
    from .commands.synology_commands import handle_syno_list
    handle_syno_list(path=path, last=last)


@syno_app.command("search")
def syno_search(
    query: str = typer.Argument(..., help="Text or glob to look for in file names"),
    path: str = typer.Option("/", "--in", help="Folder to search under"),
    last: int = typer.Option(20, "--last", "-n", help="How many matches to show"),
):
    """Search the NAS by file name."""
    from .commands.synology_commands import handle_syno_search
    handle_syno_search(query, path=path, last=last)


@syno_app.command("get")
def syno_get(
    ref: str = typer.Argument(..., help="File # from the last listing, or a full NAS path"),
    dest: str = typer.Option(".", "--to", help="Destination directory or file path"),
):
    """Download a file from the NAS."""
    from .commands.synology_commands import handle_syno_get
    handle_syno_get(ref, dest=dest)


@syno_app.command("put")
def syno_put(
    local_path: str = typer.Argument(..., help="Local file to upload"),
    path: str = typer.Argument(..., help="Destination NAS folder, e.g. /home/photos"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing file of the same name"),
):
    """Upload a local file to the NAS."""
    from .commands.synology_commands import handle_syno_put
    handle_syno_put(local_path, path, overwrite=overwrite)


@syno_app.command("share")
def syno_share(
    ref: str = typer.Argument(..., help="File # from the last listing, or a full NAS path"),
):
    """Create a public sharing link for a file or folder."""
    from .commands.synology_commands import handle_syno_share
    handle_syno_share(ref)


# Outlook command group. `co outlook` (no args) shows the Outlook inbox.
# Uses the MICROSOFT_* OAuth tokens saved to .env by `co auth microsoft`.
outlook_app = _typer_app(help="Send and read email from your Outlook account. Bare 'co outlook' shows the inbox.")
app.add_typer(outlook_app, name="outlook")


@outlook_app.callback(invoke_without_command=True)
def outlook_callback(ctx: typer.Context):
    """With no subcommand, show the Outlook inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.outlook_commands import handle_outlook_inbox
        handle_outlook_inbox()


outlook_contact_app = _typer_app(
    help="Add, list, and search Outlook contacts.",
    no_args_is_help=True,
)
outlook_app.add_typer(outlook_contact_app, name="contact")


@outlook_contact_app.command("add")
def outlook_contact_add(
    name: str = typer.Argument(..., help="Contact display name"),
    email: str = typer.Argument(..., help="Contact email address"),
):
    """Save a contact with a name and email address."""
    from .commands.outlook_commands import handle_outlook_contact_add
    handle_outlook_contact_add(name, email)


@outlook_contact_app.command("list")
def outlook_contact_list(
    last: int = typer.Option(25, "--last", "-n", help="How many contacts to show"),
):
    """List saved Outlook contacts."""
    from .commands.outlook_commands import handle_outlook_contact_list
    handle_outlook_contact_list(last=last)


@outlook_contact_app.command("search")
def outlook_contact_search(
    query: str = typer.Argument(..., help="Name or email substring"),
    last: int = typer.Option(25, "--last", "-n", help="How many matches to show"),
):
    """Search saved Outlook contacts by name or email."""
    from .commands.outlook_commands import handle_outlook_contact_search
    handle_outlook_contact_search(query, last=last)


@outlook_app.command("send", epilog="Examples:  co outlook send a@b.com \"Hi\" \"Quick note\"  |  "
                                    "cat body.txt | co outlook send a@b.com \"Report\" -  |  "
                                    "co outlook send a@b.com \"Invoice\" \"Attached\" --attach invoice.pdf --at +2h")
def outlook_send(
    to: str = typer.Argument(..., help="Recipient email address (comma-separated for multiple)"),
    subject: str = typer.Argument(..., help="Subject line"),
    message: str = typer.Argument(..., help="Body (plain text, or '-' to read from stdin)"),
    cc: Optional[str] = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: Optional[str] = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a", help="File to attach (repeat for multiple)"),
    at: Optional[str] = typer.Option(None, "--at", help="Schedule delivery: +30m, +2h, or UTC ISO time (2026-07-06T15:30:00Z)"),
):
    """Send an email from your Outlook account, now or scheduled with --at."""
    from .commands.outlook_commands import handle_outlook_send
    handle_outlook_send(to, subject, message, cc=cc, bcc=bcc, attachments=attach, at=at)


@outlook_app.command("inbox")
def outlook_inbox(
    last: int = typer.Option(10, "--last", "-n", help="How many emails to show"),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread emails"),
):
    """List recent emails in your Outlook inbox."""
    from .commands.outlook_commands import handle_outlook_inbox
    handle_outlook_inbox(last=last, unread=unread)


@outlook_app.command("read")
def outlook_read(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing (re-run to refresh numbers)"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
):
    """Show one email's body without changing its unread state."""
    from .commands.outlook_commands import handle_outlook_read
    handle_outlook_read(email_id, mark_read=mark_read)


@outlook_app.command("download")
def outlook_download(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing"),
    out_dir: str = typer.Option(".", "--to", help="Directory to save attachments into"),
    include_inline: bool = typer.Option(
        False, "--include-inline",
        help="Also save embedded signature images and logos (skipped by default)",
    ),
):
    """Save an email's attachments to disk."""
    from .commands.outlook_commands import handle_outlook_download
    handle_outlook_download(email_id, out_dir, include_inline=include_inline)


@outlook_app.command("reply", epilog="Examples:  co outlook reply 3 \"Sounds good\"  |  "
                                     "cat notes.txt | co outlook reply 3 -  |  "
                                     "co outlook reply 3 \"Signed copy attached\" --attach signed.pdf")
def outlook_reply(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing"),
    message: str = typer.Argument(..., help="Reply body (plain text, or '-' to read from stdin)"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a", help="File to attach (repeat for multiple)"),
    at: Optional[str] = typer.Option(None, "--at", help="Schedule delivery: +30m, +2h, or UTC ISO time (2026-07-06T15:30:00Z)"),
):
    """Reply to an email (threaded), now or scheduled with --at."""
    from .commands.outlook_commands import handle_outlook_reply
    handle_outlook_reply(email_id, message, attachments=attach, at=at)


@outlook_app.command("scheduled")
def outlook_scheduled():
    """List emails waiting for scheduled delivery."""
    from .commands.outlook_commands import handle_outlook_scheduled
    handle_outlook_scheduled()


@outlook_app.command("cancel")
def outlook_cancel(email_id: str = typer.Argument(..., help="Email # from 'co outlook scheduled' (or a full message ID)")):
    """Cancel a scheduled email before it goes out."""
    from .commands.outlook_commands import handle_outlook_cancel
    handle_outlook_cancel(email_id)


@outlook_app.command("sent")
def outlook_sent(last: int = typer.Option(10, "--last", "-n", help="How many emails to show")):
    """List recently sent Outlook emails."""
    from .commands.outlook_commands import handle_outlook_sent
    handle_outlook_sent(last=last)


@outlook_app.command("search")
def outlook_search(
    query: str = typer.Argument(..., help="Search query (matches subject and body)"),
    last: int = typer.Option(10, "--last", "-n", help="How many results to show"),
):
    """Search your Outlook emails."""
    from .commands.outlook_commands import handle_outlook_search
    handle_outlook_search(query, last=last)


# Subscription command group. `co sub` (no args) syncs every subscription.
# `co sub sync <addr>` syncs one. `list` and `remove` are the secondary verbs.
sub_app = _typer_app(help="Subscribe to published agents — sync skills from the relay into your coding agents")
app.add_typer(sub_app, name="sub")


@sub_app.callback(invoke_without_command=True)
def sub_callback(
    ctx: typer.Context,
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: configured backend)"),
):
    """With no subcommand, sync every subscription in ~/.co/subscriptions.txt."""
    if ctx.invoked_subcommand is None:
        from .commands.sub_commands import handle_sub_sync_all
        handle_sub_sync_all(relay=relay)


@sub_app.command("sync")
def sub_sync(
    target: str = typer.Argument(..., help="0x address (or locally-pinned alias) to sync"),
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: configured backend)"),
):
    """Sync one publisher: fetch profile, mirror skills, fan out to coding agents.

    The publisher's Ed25519 profile-v2 signature and monotonic revision are
    verified before anything is written. Unsigned, profile-v1, rolled-back, or
    equivocating profiles stay uninstalled. Skills land in ~/.co/subs/ and are
    fanned out to ~/.claude, ~/.codex, ~/.openclaw, ~/.cursor and ~/.kiro.

    A subscribed skill's `tools:` grant is removed on sync, so it cannot
    pre-authorise anything (#654). Its instructions are kept.
    """
    from .commands.sub_commands import handle_sub_sync_one
    handle_sub_sync_one(target, relay=relay)


@sub_app.command("list")
def sub_list():
    """List subscriptions (local only — no relay calls)."""
    from .commands.sub_commands import handle_sub_list
    handle_sub_list()


@sub_app.command("remove")
def sub_remove(target: str = typer.Argument(..., help="Alias or 0x address to unsubscribe from")):
    """Unsubscribe: drop record, uninstall fanout, remove mirrored bundle."""
    from .commands.sub_commands import handle_sub_remove
    handle_sub_remove(target)


def cli():
    """Entry point."""
    app()


if __name__ == "__main__":
    cli()
