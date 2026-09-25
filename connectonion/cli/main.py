"""
Purpose: Entry point for ConnectOnion CLI application using Typer framework with Rich formatting
LLM-Note:
  Dependencies: imports from [typer, rich.console, typing, __version__ | lazy: discovery.command_tree for the bare screen and `co commands`] | imported by [__main__.py] | the `co` and `connectonion` commands come from pyproject.toml [project.scripts] -> connectonion.cli.main:cli; there is no setup.py in this repo | loads commands from [cli/commands/{init, create, deploy, auth, status, reset, doctor, browser}_commands.py] | tested by [tests/e2e/cli/test_cli_help.py]
  Data flow: cli() entry point → creates Typer app → registers command callbacks (init, create, deploy, auth, status, reset, doctor, browser) → Typer parses args (including status --reveal/-r) → invokes corresponding handle_*() function from commands module → command outputs via rich.Console
  State/Effects: no persistent state | writes to stdout via rich.Console | lazy imports command handlers on invocation | registers typer.Option and typer.Argument decorators | uses typer.Exit() for early termination
  Integration: exposes cli() entry point registered in pyproject.toml [project.scripts] as the 'co' and 'connectonion' commands | app() is the Typer instance | commands: init, create, deploy (-t/--template, --skills repeatable, --name for template deploys), auth [google|microsoft], status (--reveal/-r), reset, doctor, commands (every command path with its summary, from discovery.command_tree), browser | --version flag shows version | -b/--browser flag shortcuts browser command | no args shows custom help via _show_help()
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

# Package startup loads only global settings. --env-file replaces them explicitly.

console = Console()


from .typer_groups import NegativeIds, _OneSuggestion


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
    epilog="Example:  co create my-agent  |  co status  |  co gmail --help",
)


def version_callback(value: bool):
    if value:
        console.print(f"co {__version__}")
        raise typer.Exit()


def env_file_callback(ctx: typer.Context, value: Optional[Path]):
    """Select the env file before any command runs.

    A failure is recorded, not raised here: this eager callback runs before
    Typer knows which command was asked for, and `co env` must still run on a
    broken file — it is the command that says which line to fix. main() exits
    for every other command.
    """
    from ..environment import EnvironmentError, select_env_file
    try:
        select_env_file(value)
    except EnvironmentError:
        pass
    return value


# One text for both first screens. `co --help` said Start here: init, create,
# auth, and bare `co` said Quick Start: init, create, run, benchmark, eval -- two
# answers to "where do I start", and Rich wrapped bare co's eval line mid-sentence.
# Both now print these lines as they are, so they cannot drift apart again.
START_HERE = (
    ("Start here:", (
        "co init                  Set up your identity and keys (~/.co/keys.env)",
        "co create my-agent       New project; then: cd my-agent && python agent.py",
        "co auth                  Log in to OpenOnion for managed models and credits",
    )),
    ("Build or improve a skill:", (
        "1. Define the standard first: co benchmark --help",
        "2. Write/check >=5 distinct cases; then edit .co/skills/<name>/SKILL.md",
        "3. Run and score the real Agent: co eval --help",
        "4. Inspect failures, edit the skill, rerun the SAME benchmark",
    )),
)


def _start_here_help() -> str:
    """START_HERE as Click help: \\b keeps each block from being re-wrapped."""
    blocks = ["\b\n" + title + "\n" + "\n".join("  " + line for line in lines) for title, lines in START_HERE]
    return "ConnectOnion - A simple Python framework for creating AI agents.\n\n" + "\n\n".join(blocks)


@app.callback(invoke_without_command=True, help=_start_here_help())
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", callback=version_callback, is_eager=True),
    env_file: Optional[Path] = typer.Option(None, "--env-file", callback=env_file_callback,
        is_eager=True, help="Use this env file instead of global keys.env; put before the command. Process overrides win."),
    no_tips: bool = typer.Option(False, "--no-tips",
        help="Do not print the Next: line after the command (CO_TIPS=off does the same for every run)."),
):
    """The root of every co command; its help text is START_HERE."""
    from ..environment import selection_error
    error = selection_error()
    if error is not None and ctx.invoked_subcommand != "env":
        # Plain print: Rich would wrap the path and split the "Next:" tip.
        print(error)
        raise typer.Exit(2)
    if no_tips:
        from .commands.command_tips import suppress_tips
        suppress_tips()
    if ctx.invoked_subcommand is None:
        _show_help()


def _show_help():
    """Show help message."""
    console.print()
    console.print(f"[bold cyan]co[/bold cyan] - ConnectOnion v{__version__}")
    console.print()
    console.print("A simple Python framework for creating AI agents.")
    console.print()
    # The workflow, not just the commands: an agent handed "improve this skill"
    # must find that the test cases come first without being told a command
    # name (#1642). `co skills` manages skills and says so.
    for title, lines in START_HERE:
        console.print(f"[bold]{title}[/bold]")
        for line in lines:
            # soft_wrap: Rich folded the eval line at 80 columns into a stray "rerun".
            console.print(f"  {line}", markup=False, highlight=False, soft_wrap=True)
        console.print()
    # The register, not a selection. This list used to be typed by hand and
    # named 16 of 24 commands — ai, announce, call, reset, server, setup,
    # skills and sub were real and absent, and a hand-typed list has no way
    # to notice the ninth. Reading the Typer app means a command is on the
    # first screen the moment it is registered, with the same summary its
    # --help carries, and a test compares the two so this cannot silently
    # become a selection again.
    from rich.markup import escape
    from .discovery import command_tree
    top_level = [e for e in command_tree(app) if e.path.count(" ") == 1]
    width = max(len(e.path) for e in top_level) - len("co ")
    console.print("[bold]Commands:[/bold]")
    for entry in top_level:
        name = entry.path[len("co "):]
        # escape(): a summary that mentions `[path]` must not be read as markup.
        # soft_wrap: a pipe is 80 columns to Rich, and a wrapped summary reads
        # as two commands.
        console.print(f"  [green]{name.ljust(width)}[/green]  {escape(entry.summary)}",
                      highlight=False, soft_wrap=True)
    console.print()
    console.print("[bold]Configuration:[/bold]")
    console.print("  Global by default: ~/.co/keys.env", markup=False)
    console.print("  co env                           Inspect and edit selected settings", markup=False)
    console.print("  co init ./                       Set up a project explicitly", markup=False)
    console.print("  co --env-file .env <command>     Use a project env file", markup=False)
    console.print()
    console.print("  co commands                      Every subcommand, one per line", markup=False)
    console.print("  co --help                        All commands", markup=False)
    console.print("  co <command> --help              Command options", markup=False)
    console.print()
    console.print("[bold]Docs:[/bold] https://docs.connectonion.com")
    console.print("[bold]Discord:[/bold] https://discord.gg/4xfD9k8AUF")
    console.print()


@app.command(epilog="Example:  co init  |  co init ./ --template co-ai")
def init(
    path: Optional[Path] = typer.Argument(None, exists=True, file_okay=False, resolve_path=True,
                                         help="Existing project directory; omit for global ~/.co/keys.env"),
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Project template: co-ai, custom (default: config only)"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
):
    """Initialize global ~/.co/keys.env, or use co init ./ for a project. Creates your keypair and writes keys.env."""
    from .commands.init import handle_global_init, handle_init
    if path is None:
        from ..environment import explicit_env_file
        if explicit_env_file() is not None:
            console.print("Global initialization does not accept --env-file. Next: co init")
            raise typer.Exit(2)
        if template is not None or description is not None or force:
            console.print("[red]Project options require a path, for example: co init ./ --template co-ai[/red]")
            raise typer.Exit(2)
        handle_global_init(key=key)
        return
    handle_init(ai=None, key=key, template=template, description=description, yes=yes, force=force, path=path)


@app.command(epilog="Example:  co create my-agent")
def create(
    name: Optional[str] = typer.Argument(None, help="Project name"),
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Template: co-ai (default), custom"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
):
    """Create new project. Creates the <name>/ directory; the first run also sets up ~/.co/."""
    from .commands.create import handle_create
    # An explicit False means the project was not created — exit non-zero so a
    # script can tell. Other return values keep the previous behaviour.
    if handle_create(name=name, ai=None, key=key, template=template,
                     description=description, yes=yes) is False:
        raise typer.Exit(1)


@app.command(epilog="Example:  co deploy  |  co deploy --to prod")
def deploy(
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Create and deploy a template project"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skill directory (contains SKILL.md) or directory of skills to bundle into .co/skills/ (repeatable: --skills a --skills b)"),
    name: Optional[str] = typer.Option(None, "--name", help="Project name for template deploys (default: {template}-agent)"),
    to: Optional[str] = typer.Option(None, "--to", help="Deploy onto a server you own (see: co server ls)"),
    own_identity: bool = typer.Option(False, "--own-identity", help="With --to, let the agent mint its own identity instead of deriving it from your recovery phrase — for an agent you are handing to someone else"),
):
    """Deploy to ConnectOnion Cloud, or with --to onto a server you own. Deploys the project in this directory."""
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
    # Every refusal and failure in handle_deploy returns False; 1.8.8b9 dropped
    # it here, so "Entrypoint not found" exited 0.
    if handle_deploy(template=template, skills=skills, name=name) is False:
        raise typer.Exit(1)


@app.command(epilog="Example:  co auth  |  co auth status  |  co auth google")
def auth(service: Optional[str] = typer.Argument(None, help="login, status, logout, or a service: google, microsoft, feishu, lark"),
         scopes: Optional[str] = typer.Option(None, "--scopes", help="Google: comma-separated limited scopes. Default: Gmail, Calendar, Drive and YouTube."),
         app_id: Optional[str] = typer.Option(None, "--app-id", metavar="cli_…",
                                              help="Feishu/Lark: authorize an application you already have, keeping its groups and permissions")):
    """Sign in to OpenOnion (login, status, logout) or connect a service. Writes tokens to the env file; feishu and lark also create a Feishu application you own. status is Read-only."""
    if scopes is not None and service != "google":
        print("--scopes is only supported for Google. Next: co auth google --help")
        raise typer.Exit(2)
    if app_id is not None and service not in ("feishu", "lark"):
        print("--app-id is only supported for Feishu and Lark. Next: co auth feishu --help")
        raise typer.Exit(2)
    if service == "google":
        from .commands.auth_commands import handle_google_auth
        handle_google_auth(scopes=scopes)
    elif service == "microsoft":
        from .commands.auth_commands import handle_microsoft_auth
        handle_microsoft_auth()
    elif service in ("feishu", "lark"):
        from .commands.feishu_auth import handle_feishu_auth
        handle_feishu_auth(brand=service, app_id=app_id)
    elif service == "status":
        from .commands.auth_commands import handle_auth_status
        handle_auth_status()
    elif service == "logout":
        from .commands.auth_commands import handle_auth_logout
        handle_auth_logout()
    elif service in (None, "login"):
        from .commands.auth_commands import handle_auth
        handle_auth()
    else:
        # Any other word used to fall through to OpenOnion sign-in, so
        # `co auth status` minted a keypair and `co auth logout` logged you in.
        # A word we do not know must not do the one thing that writes secrets.
        from .commands.command_tips import print_tip
        print(f"Unknown auth target: {service}. Use one of: login, status, logout, "
              "google, microsoft, feishu, lark.")
        print_tip("Next: co auth status")
        raise typer.Exit(2)


@app.command(epilog="Example:  co keys  |  co keys --agent my-agent  |  co keys --ssh")
def keys(
    reveal: bool = typer.Option(False, "--reveal", "-r", help="Show full key values"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Print the address an agent of this name will have, before it is deployed"),
    ssh: bool = typer.Option(False, "--ssh", help="Print the SSH public key derived from your recovery phrase"),
    write: bool = typer.Option(False, "--write", help="With --ssh, also write the private half to ~/.co/ssh/"),
):
    """Show agent keys and credentials. Read-only; only --ssh --write writes key files under ~/.co/ssh/."""
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


@app.command(epilog="Example:  co status")
def status(
    reveal: bool = typer.Option(
        False,
        "--reveal",
        "-r",
        help="Show full provider credential values",
    ),
):
    """Show your credit balance, account, credential sources and deployments. Read-only."""
    from .commands.status_commands import handle_status
    handle_status(reveal=reveal)


@app.command(epilog="Example:  co reset")
def reset():
    """Reset account (destructive). Deletes ~/.co/keys/ and ~/.co/keys.env after you confirm, then creates a new account."""
    from .commands.reset_commands import handle_reset
    handle_reset()


@app.command(epilog="Example:  co doctor  |  co doctor --fix")
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Offer safe browser/runtime repairs"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve every offered repair"),
    json_output: bool = typer.Option(False, "--json", help="Emit stable machine-readable output"),
):
    """Diagnose installation. Read-only; --fix Changes the browser runtime only for repairs you approve."""
    if yes and not fix:
        console.print("[red]--yes requires --fix.[/red]")
        raise typer.Exit(2)
    from .commands.doctor_commands import handle_doctor
    # The exit code is the whole point of running this in a script: it used to
    # be 0 even under its own `✗ broken symlink`.
    if handle_doctor(fix=fix, yes=yes, json_output=json_output):
        raise typer.Exit(1)


@app.command(epilog="Example:  co commands")
def commands():
    """List every command, including subcommands, one per line with its summary. Read-only."""
    # `co --help` shows one level; `co gmail --help` the next; `co gmail draft
    # --help` the one below that. An agent looking for "the command that sends
    # a draft" has to guess which group to open, and a wrong guess is a round
    # trip — or an invented command. This is the whole tree in one call, in
    # the order --help prints it, plain text so it can be grepped. No Rich:
    # the audience is a pipe.
    from .discovery import command_tree
    entries = command_tree(app)
    width = max(len(e.path) for e in entries)
    for entry in entries:
        print(f"{entry.path.ljust(width)}  {entry.summary}")
    print()
    print("Options for one command: co <command> --help")
    print("Functions inside the browser: co browser help")


claude_app = _typer_app(help="Experimental — run Claude Code through the ConnectOnion session connector. "
                              "Preview only; its surface may change before 1.9.0. "
                              "Starts Claude's terminal and, unless --no-share, an OIP Work Room.",
                         epilog='Example:  co claude  |  co claude run "Summarise README.md"')
app.add_typer(claude_app, name="claude",
              short_help="Experimental: Run Claude Code through the ConnectOnion session connector.")


@claude_app.callback(invoke_without_command=True)
def claude_interactive(
    ctx: typer.Context,
    cwd: Path = typer.Option(Path("."), "--cwd", exists=True, file_okay=False, resolve_path=True, help="Workspace directory"),
    session_id: str = typer.Option("", "--resume", help="Claude session ID to resume"),
    model: str = typer.Option("", "--model", help="Claude model override"),
    share: bool = typer.Option(True, "--share/--no-share", help="Share this terminal through an OIP Work Room"),
):
    """Launch Claude's terminal and an OIP Work Room on the same session."""
    if ctx.invoked_subcommand is not None:
        return
    if share:
        from .co_ai.claude_station import StationFailed, launch_claude_station

        try:
            exit_code, owned_session = launch_claude_station(cwd, session_id, model)
        except StationFailed as exc:
            print(f"co claude: {exc}", file=sys.stderr)
            raise typer.Exit(1) from exc
    else:
        from ..useful_tools.claude_code import run_interactive_claude

        try:
            exit_code, owned_session = run_interactive_claude(str(cwd), session_id, model)
        except ValueError as exc:
            print(f"co claude: {exc}", file=sys.stderr)
            raise typer.Exit(1) from exc
    print(f"Claude session: {owned_session}", file=sys.stderr)
    from .commands.command_tips import print_tip
    print_tip(f"Next: co claude --resume {owned_session}")
    if exit_code:
        raise typer.Exit(exit_code)


@claude_app.command("run", epilog='Example:  co claude run "Summarise README.md" --timeout 300')
def claude_run(
    prompt: str = typer.Argument(..., help="Task for Claude Code"),
    cwd: Path = typer.Option(Path("."), "--cwd", exists=True, file_okay=False, resolve_path=True, help="Workspace directory"),
    session_id: str = typer.Option("", "--session", help="Claude session ID to resume"),
    model: str = typer.Option("", "--model", help="Claude model override"),
    timeout: int = typer.Option(600, "--timeout", min=1, help="Maximum run time in seconds"),
):
    """Experimental: start or resume one Claude Code turn and print its session envelope. Runs Claude Code in --cwd."""
    from ..useful_tools.claude_code import run_co_claude

    result = run_co_claude(
        prompt=prompt,
        cwd=str(cwd),
        session_id=session_id,
        model=model,
        timeout=timeout,
        workspace=cwd,
    )
    print(result)
    import json
    if json.loads(result)["status"] != "completed":
        raise typer.Exit(1)


def _closes_only(args: List[str]) -> bool:
    """`close`, `-t NAME close` or `tab close NAME`: verbs that never open a window."""
    from .commands.browser_commands import _extract_tab

    _, verb = _extract_tab(args)
    return bool(verb) and (verb[0] == "close" or verb[:2] == ["tab", "close"])


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
             epilog='Example:  co browser go_to example.com  |  co browser do "find the pricing page"')
def browser(
    headless: Optional[bool] = typer.Option(
        None, "--headless/--no-headless",
        help="Run browser headless. Default: headed, or headless on Linux with no display.",
    ),
    engine: str = typer.Option(
        None,
        "--engine",
        help="wtf (the paid WTF Browser), system (free Chrome), or auto. "
             "Overrides the default from `co browser config`, in both directions.",
    ),
    args: List[str] = typer.Argument(None, help="Browser function + args, or: do \"<instruction>\""),
):
    """Drive one persistent browser. Starts it on first use; a WTF Browser session is billed.

    Run a function directly (co browser go_to x.com),
    use `do` for the AI agent (co browser do "..."), or `co browser help` to list functions.

    Also: -t TAB to target your own tab · tab open|ls|close · status · network ·
    cookies · close. `co browser help` shows how to use each one."""
    # `config` is a setting, not a browser verb: it must not reach the daemon
    # or start anything, so it is answered before the engine is resolved.
    if args and args[0] == "config":
        if len(args) > 2:
            print("usage: co browser config [wtf|system|auto]")
            raise typer.Exit(2)
        from .commands.browser_config import handle_browser_config
        raise typer.Exit(handle_browser_config(args[1] if len(args) > 1 else None))

    from ..useful_tools.browser_tools._async_browser import has_display
    from ..useful_tools.browser_tools.engine import effective_mode
    from .commands.browser_commands import handle_browser

    # An explicit --no-headless used to be indistinguishable from the default,
    # so with no display it was quietly launched headless — and headless Chrome
    # says `HeadlessChrome` in its User-Agent, which is what the caller was
    # avoiding by asking for a window. Asked for a window, get one or a refusal
    # (#1339). Only a command that can open a window is refused: closing a
    # browser or a tab opens nothing, and refusing it left a headless box with
    # a running browser that `--no-headless close` could not reach.
    if headless is False and not has_display() and not _closes_only(args or []):
        print("--no-headless needs a display, and this machine has none "
              "(DISPLAY and WAYLAND_DISPLAY are unset).")
        print("Give it a virtual one:  xvfb-run -a co browser --no-headless <command>")
        print("Or accept headless:     co browser <command>")
        raise typer.Exit(2)
    try:
        mode = effective_mode(engine)
    except ValueError as error:
        print(str(error))
        print("Next: co browser config")
        raise typer.Exit(2)
    raise typer.Exit(handle_browser(args or [], headless=bool(headless), engine_mode=mode))


@app.command(
    "remote-browser",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    epilog="Example:  co remote-browser config 0xabc... --proxy shared  |  co remote-browser start",
)
def remote_browser(
    args: List[str] = typer.Argument(
        None, help="config <address> [--proxy shared] | [<address>] <start|status|sessions|stop|diagnose>"
    ),
):
    """Manage an owner-bound browser session on a remote agent over OIP. Starts and stops it there; config writes ~/.co/remote-browser.json."""
    from .commands.remote_browser_commands import handle_remote_browser

    raise typer.Exit(handle_remote_browser(args or []))


@app.command(
    "proxy",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    # --help belongs to handle_proxy: Click's own printed the generic help for
    # `co proxy diagnose --help`, though `co proxy` promises that diagnose has one.
    add_help_option=False,
)
def proxy(
    args: List[str] = typer.Argument(
        None, help="share to <address> | status | stop <address> | diagnose <address>"
    ),
):
    """Share this computer's internet connection with an authorized agent. Starts or stops sharing it."""
    from .commands.proxy_commands import handle_proxy

    raise typer.Exit(handle_proxy(args or []))


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
             epilog="Example:  co call 0x3d40... co status")
def call(
    args: List[str] = typer.Argument(None, help="[--out F] [--timeout S] [--relay U] <address> <command...>"),
):
    """Run one command on a remote agent and print the result (no LLM). Runs it there as bash.

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


@app.command(epilog='Example:  co ai "explain what agent.py does"  |  co ai --port 8000')
def ai(
    prompt: Optional[str] = typer.Argument(None, help="One-shot prompt (runs and exits)"),
    port: int = typer.Option(8000, "--port", "-p", help="Port for web server"),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", show_default=DEFAULT_MODEL,
        help="Model to use; unset means the harness's own default",
    ),
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
    # Channels are configured in .co/host.yaml, beside `name` and `trust`, so
    # that `co ai` needs no flags and one file shows every channel at a glance.
    # These two override that file for one run and nothing else.
    listen: Optional[str] = typer.Option(
        None, "--listen", metavar="feishu[,lark]",
        help="Answer these channels instead of the ones in .co/host.yaml",
    ),
    no_listen: bool = typer.Option(
        False, "--no-listen", help="Do not answer any channel this run"
    ),
    sandbox: str = typer.Option(
        "workspace-write", "--sandbox",
        metavar="read-only|workspace-write|danger-full-access",
        help="What a delegated Codex run may write. workspace-write is cwd and "
             "TMPDIR only; reads are unrestricted at every level.",
    ),
    harness: str = typer.Option(
        "ours", "--harness", metavar="ours|codex|claude-code",
        help="Which agent loop runs the task. A delegated harness runs on its own "
             "subscription with its own tools, and spends none of our tokens "
             "deciding to delegate.",
    ),
    permission_mode: str = typer.Option(
        "default", "--permission-mode",
        help="Claude Code headless permissions. The default is manual; select a broader mode explicitly.",
    ),
    timeout: int = typer.Option(600, "--timeout", min=1, help="Delegated harness task timeout, in seconds"),
):
    """Start AI coding agent or run one-shot prompt. Runs an agent whose tools can edit files and run commands here, with approval."""
    from .commands.ai_commands import handle_ai
    if listen and no_listen:
        raise typer.BadParameter("--listen and --no-listen contradict each other")
    channels = [] if no_listen else ([c.strip() for c in listen.split(",") if c.strip()]
                                     if listen else None)
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
        listen=channels,
        harness=harness,
        sandbox=sandbox,
        permission_mode=permission_mode,
        timeout=timeout,
    )


@app.command(epilog="Example:  co copy --list  |  co copy gmail")
def copy(
    names: List[str] = typer.Argument(None, help="Tool or plugin names to copy"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List available items"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Custom destination path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
):
    """Copy built-in tools/plugins to customize. Writes them into ./tools/, ./plugins/ or ./prompts/."""
    from .commands.copy_commands import handle_copy
    handle_copy(names=names or [], list_all=list_all, path=path, force=force)


# ---- skill benchmarks (#1642) ------------------------------------------------
#
# `co benchmark` authors and checks the standard and never runs an Agent;
# `co eval run|report` runs the real Agent on it and keeps the scored report.
# The old `co eval [NAME]` over .co/evals/*.yaml keeps working unchanged: a
# first word that is not `run` or `report` is routed to it, so no existing
# invocation changes meaning and no old file is read as a benchmark.

BENCHMARK_HELP = """Author the standard BEFORE editing a skill. Never runs an Agent.

\b
Files: .co/benchmarks/<name>.yaml
A suite needs at least 5 distinct cases, with both kinds:
  kind: normal          the task should simply succeed
  kind: counterexample  the right answer is to refuse, stop or flag
Each case: id, kind, input, expect.must (outcomes that must happen);
a counterexample also needs expect.must_not (outcomes that must not).
given and fixture are optional context. Write outcomes a user could
observe, not exact wording or a prescribed tool route. No agent: or
skill: field — the same cases must be able to compare two of them.

\b
  - id: title-mismatch
    kind: counterexample
    given: "One invoice's buyer title differs from the company name"
    input: "Please process this batch"
    expect:
      must: ["The mismatched invoice and its discrepancy reach the user"]
      must_not: ["The mismatched invoice is submitted"]

\b
Next after `co benchmark check <name>` passes:
  1. write or edit .co/skills/<skill>/SKILL.md (the skill is the deliverable)
  2. co eval run <name> --agent agent.py --skill <skill> --runs 1
  3. co eval report <name> --latest, edit only the skill, rerun the same benchmark
"""

benchmark_app = _typer_app(help=BENCHMARK_HELP, invoke_without_command=True,
                           epilog="Example:  co benchmark check invoice-batch")


@benchmark_app.callback()
def _benchmark(ctx: typer.Context):
    # Bare `co benchmark` is discovery only: it never runs anything.
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@benchmark_app.command("list", epilog="Example:  co benchmark list --json")
def benchmark_list(json_out: bool = typer.Option(False, "--json", help="Structured list for coding agents")):
    """Show authored suites, their paths and whether they are valid. Read-only."""
    from .commands.benchmark_commands import handle_benchmark_list
    raise typer.Exit(code=handle_benchmark_list(as_json=json_out))


@benchmark_app.command("check", epilog="Example:  co benchmark check invoice-batch")
def benchmark_check(
    name: str = typer.Argument(..., help="File stem of .co/benchmarks/<name>.yaml, not a path"),
    json_out: bool = typer.Option(False, "--json", help="Structured errors: case_id, field, reason, fix"),
):
    """Validate one suite: at least 5 distinct cases, both kinds, must/must_not. Never calls an Agent. Read-only.

    Exit 0 valid; 2 missing or invalid suite, with every problem and its fix.
    """
    from .commands.benchmark_commands import handle_benchmark_check
    raise typer.Exit(code=handle_benchmark_check(name, as_json=json_out))


app.add_typer(benchmark_app, name="benchmark")


class _EvalGroup(_OneSuggestion):
    """`co eval run|report` are subcommands; any other first word is the old `co eval NAME`."""

    def resolve_command(self, ctx, args):
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            args = ["legacy", *args]
        return super().resolve_command(ctx, args)


EVAL_HELP = """Run a benchmark with the real Agent and inspect scored reports.

\b
  co eval run <name> --agent agent.py [--skill NAME] [--invoke auto|explicit] [--runs N]
              [--max-iterations N]
  co eval report <name> [--latest | --run ID]

\b
Each expectation is PASS, FAIL or UNVERIFIED, with the reason and evidence.
A must_not that happened is a hard FAIL. An outside effect (sent, submitted,
paid) the Agent only claims, with no tool result showing it, is UNVERIFIED.
Reports are kept under .co/eval-runs/<name>/<run-id>/ and never overwritten.
Write the benchmark first: co benchmark --help.

\b
Older evals: `co eval [NAME] [--agent FILE]` still runs .co/evals/*.yaml
exactly as before (docs/debug/eval.md); those files are not benchmarks.
"""

eval_app = typer.Typer(cls=_EvalGroup, help=EVAL_HELP, invoke_without_command=True,
                       epilog="Example:  co eval run invoice-batch --agent agent.py --runs 1")


@eval_app.callback()
def _eval(
    ctx: typer.Context,
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Older evals: agent file (overrides YAML)"),
):
    if ctx.invoked_subcommand is None:
        # The exit code is the point of #682: `co eval` returned 0 after a run
        # where nothing executed. Discarding it here would leave that fix
        # unreachable from a shell, which is where CI reads it.
        raise typer.Exit(code=_legacy_eval(None, agent))
    ctx.obj = {"agent": agent}


@eval_app.command("run", epilog="Example:  co eval run invoice-batch --agent agent.py --skill invoice-check --runs 1")
def eval_run(
    name: str = typer.Argument(..., help="Benchmark name: .co/benchmarks/<name>.yaml; must pass co benchmark check"),
    agent: str = typer.Option(..., "--agent", "-a", help="The real Agent entry point, e.g. agent.py"),
    skill: Optional[str] = typer.Option(None, "--skill", help="Skill under test; its invocation must be observed"),
    invoke: str = typer.Option("auto", "--invoke",
                               help="auto: send the input unchanged, the Agent must choose the skill. "
                                    "explicit: send /<skill> <input>"),
    runs: int = typer.Option(1, "--runs", min=1, help="Repeat each case on a fresh session. Start with 1"),
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", min=1,
        help="Steps one attempt may take before it is stopped (default 10); each step is paid for"),
    json_out: bool = typer.Option(False, "--json", help="Summary and report path as JSON"),
    live: bool = typer.Option(False, "--live",
                              help="Allow outside effects. Without it the run sets CO_EVAL_LIVE=0 "
                                   "and unproven effects stay UNVERIFIED"),
    judge_model: Optional[str] = typer.Option(None, "--judge-model", help="Model that judges outcomes"),
):
    """Run every case on the real Agent and score each expectation. Runs the Agent; Writes an immutable report.

    Exit 0 all expectations pass; 1 any FAIL, UNVERIFIED, STOPPED or skill not invoked;
    2 bad benchmark, agent path, skill or option; 3 the Agent or runner broke (never a pass).
    """
    from .commands.benchmark_commands import handle_eval_run
    raise typer.Exit(code=handle_eval_run(name, agent, skill_name=skill, invoke=invoke, runs=runs,
                                          as_json=json_out, live=live, judge_model=judge_model,
                                          max_iterations=max_iterations))


@eval_app.command("report", epilog="Example:  co eval report invoice-batch --latest")
def eval_report(
    name: str = typer.Argument(..., help="Benchmark name"),
    latest: bool = typer.Option(False, "--latest", help="The most recent run (the default)"),
    run_id: Optional[str] = typer.Option(None, "--run", help="A saved run id"),
    json_out: bool = typer.Option(False, "--json", help="The full saved report as JSON"),
):
    """Reopen a saved run: case by case, and what changed since the run before. Read-only.

    Exit 0 report found; 2 no such benchmark run.
    """
    if latest and run_id:
        console.print("--latest and --run are exclusive")
        raise typer.Exit(code=2)
    from .commands.benchmark_commands import handle_eval_report
    raise typer.Exit(code=handle_eval_report(name, run_id=run_id, as_json=json_out))


@eval_app.command("legacy", epilog="Example:  co eval legacy my-eval --agent agent.py")
def eval_legacy(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None, help="Specific eval name"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent file (overrides YAML)"),
):
    """Run the older .co/evals/*.yaml, unchanged. Runs the agent on each. `co eval <name>` still reaches it.

    Visible rather than hidden: a command only reachable by guessing is one an
    agent cannot find (tests/unit/test_cli_discovery.py).
    """
    raise typer.Exit(code=_legacy_eval(name, agent or (ctx.obj or {}).get("agent")))


LEGACY_EVAL_TIP = 'Fix what failed with the AI:  co ai "<what to fix>"'


def _legacy_eval(name: Optional[str], agent: Optional[str]) -> int:
    """The older `co eval [NAME]`, unchanged, with the tip it has always ended on."""
    import sys

    from .commands.command_tips import tips_enabled
    from .commands.eval_commands import handle_eval

    code = handle_eval(name=name, agent_file=agent) or 0
    if code == 0 and tips_enabled():
        print(LEGACY_EVAL_TIP, file=sys.stderr)
    return code


app.add_typer(eval_app, name="eval")


@app.command(epilog='Example:  co setup --bio "Builds invoice agents"')
def setup(
    bio: Optional[str] = typer.Option(None, "--bio", "-b", help="One-line bio for ~/.co/agent.json"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Alias/name for ~/.co/agent.json (default: $USER)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing ~/.co/agent.json (backs up to .bak)"),
    skip_skills: bool = typer.Option(False, "--no-skills", help="Skip ~/.co/skills/ library refresh"),
):
    """Set up your global ~/.co/ — identity, agent.json, and skill library. Writes ~/.co/agent.json and ~/.co/skills/."""
    from .commands.setup_commands import handle_setup
    handle_setup(name=name, bio=bio, force=force, skip_skills=skip_skills)


@app.command(epilog="Example:  co announce --dry-run  |  co announce")
def announce(
    relay: Optional[str] = typer.Option(None, "--relay", "-r", help="Relay URL (default: configured backend)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the signed message, don't send"),
):
    """Publish ~/.co/agent.json + SKILL.md bodies (publish:true) to the relay. Publishes them; --dry-run sends nothing."""
    from .commands.announce_commands import handle_announce
    handle_announce(relay=relay, dry_run=dry_run)


# Server command group — the machines `co deploy --to` can target
env_app = _typer_app(help="Show, set and remove settings in the selected env file (global ~/.co/keys.env unless --env-file was given). Bare 'co env' shows them.",
                     epilog="Example:  co env  |  co env set OPENAI_API_KEY sk-...")
app.add_typer(env_app, name="env")


@env_app.callback(invoke_without_command=True)
def env_callback(ctx: typer.Context, json_output: bool = typer.Option(False, "--json", help="Redacted configuration provenance as JSON")):
    """Show, set and remove settings in the selected env file."""
    if ctx.invoked_subcommand is None:
        from .commands.env_commands import handle_env_show
        handle_env_show(reveal=False, json_output=json_output)
    elif json_output:
        raise typer.BadParameter("Put --json on bare co env or after env show.")


@env_app.command("show", epilog="Example:  co env show  |  co env show --json")
def env_show(reveal: bool = typer.Option(False, "--reveal", "-r", help="Show full values"),
             json_output: bool = typer.Option(False, "--json", help="Redacted configuration provenance as JSON")):
    """List setting sources; all values stay hidden unless --reveal is explicit. Read-only."""
    from .commands.env_commands import handle_env_show
    handle_env_show(reveal=reveal, json_output=json_output)


@env_app.command("path", epilog="Example:  co env path")
def env_path():
    """Print the selected env file's path and nothing else, for $(co env path). Read-only."""
    from .commands.env_commands import handle_env_path
    handle_env_path()


@env_app.command("get", epilog="Example:  co env get OPENAI_API_KEY")
def env_get(key: str = typer.Argument(..., help="Setting name, e.g. OPENAI_API_KEY")):
    """Print one value as a command would see it: the process wins, then the file. Read-only."""
    from .commands.env_commands import handle_env_get
    handle_env_get(key)


@env_app.command("set", epilog="Example:  co env set OPENAI_API_KEY sk-...  |  "
                                "co env set GITHUB_TOKEN ghp_... --secret")
def env_set(key: str = typer.Argument(..., help="Setting name, e.g. OPENAI_API_KEY"),
            value: str = typer.Argument(..., help="Value; quote it if it has spaces"),
            from_console: bool = typer.Option(
                False, "--from-console",
                help="For FEISHU_/LARK_ app credentials copied from the Developer Console, "
                     "when co auth cannot create the application for your tenant",
            ),
            secret: bool = typer.Option(
                False, "--secret",
                help="Encrypt it instead of writing it in plain text. The key is derived "
                     "from this agent's own key and stored nowhere; rotate with co env rotate",
            )):
    """Save one setting to ~/.co/keys.env, which every project reads, or to --env-file. Writes that file."""
    from .commands.env_commands import handle_env_set
    handle_env_set(key, value, from_console=from_console, secret=secret)


@env_app.command("rotate", epilog="Example:  co env rotate LARK_APP_SECRET")
def env_rotate(key: str = typer.Argument(..., help="An encrypted setting, e.g. LARK_APP_SECRET")):
    """Re-encrypt one stored secret at the next derivation index. Writes the new value to the env file."""
    from .commands.env_commands import handle_env_rotate
    handle_env_rotate(key)


@env_app.command("unset", epilog="Example:  co env unset OPENAI_API_KEY")
def env_unset(key: str = typer.Argument(..., help="Setting name; a GOOGLE_*/MICROSOFT_* account field removes the whole record")):
    """Remove one setting from the selected file. Removes it from that file only; your shell is untouched."""
    from .commands.env_commands import handle_env_unset
    handle_env_unset(key)


server_app = _typer_app(help="Register, list and preflight the servers you can deploy to",
                        epilog="Example:  co server add prod --ssh ubuntu@203.0.113.10  |  co server check prod")
app.add_typer(server_app, name="server")


@server_app.callback(invoke_without_command=True)
def server_callback(ctx: typer.Context):
    """Deploy targets."""
    if ctx.invoked_subcommand is None:
        from .commands.server_commands import handle_server_list
        handle_server_list()


@server_app.command("add", epilog="Example:  co server add prod --ssh ubuntu@203.0.113.10")
def server_add(
    name: str = typer.Argument(..., help="Short name you will pass to co deploy --to"),
    ssh: str = typer.Option(..., "--ssh", help="ssh target, e.g. user@1.2.3.4 or a Host from ~/.ssh/config"),
):
    """Register a machine. Writes a name → ssh target mapping to ~/.co/servers.yaml, no credential."""
    from .commands.server_commands import handle_server_add
    if not handle_server_add(name=name, ssh_target=ssh):
        raise typer.Exit(1)


@server_app.command("ls", epilog="Example:  co server ls")
def server_ls():
    """Show what you can deploy to. Read-only."""
    from .commands.server_commands import handle_server_list
    handle_server_list()


@server_app.command("check", epilog="Example:  co server check prod")
def server_check(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Preflight a target and name the requirement that failed. Writes the result to ~/.co/servers.yaml."""
    from .commands.server_commands import handle_server_check
    if not handle_server_check(name=name):
        raise typer.Exit(1)


@server_app.command("new", epilog="Example:  co server new prod")
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


@server_app.command("ssh", epilog='Example:  co server ssh prod  |  co server ssh prod "systemctl status my-agent"')
def server_ssh(
    name: str = typer.Argument(..., help="Registered server name"),
    command: Optional[str] = typer.Argument(None, help="Command to run instead of opening a shell"),
):
    """Open a shell on a registered server, or run one command there. Runs whatever you type on that machine."""
    from .commands.server_commands import handle_server_ssh
    if not handle_server_ssh(name=name, command=command):
        raise typer.Exit(1)


@server_app.command("fix-key", epilog="Example:  co server fix-key prod")
def server_fix_key(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Reinstall your SSH key on a server you own, without recreating it. Changes the key it accepts; the disk is kept."""
    from .commands.server_commands import handle_server_fix_key
    if not handle_server_fix_key(name=name):
        raise typer.Exit(1)


@server_app.command("forget", epilog="Example:  co server forget prod")
def server_forget(
    name: str = typer.Argument(..., help="Registered server name"),
):
    """Drop the local entry. Removes it from ~/.co/servers.yaml; does NOT touch the machine or stop any billing."""
    from .commands.server_commands import handle_server_forget
    if not handle_server_forget(name=name):
        raise typer.Exit(1)


@server_app.command("destroy", epilog="Example:  co server destroy prod")
def server_destroy(
    name: str = typer.Argument(..., help="Server to tear down"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation"),
):
    """Destroy the machine and stop the billing. Deletes the machine and its disk; the unused term is refunded."""
    from .commands.server_commands import handle_server_destroy
    if not handle_server_destroy(name=name, yes=yes):
        raise typer.Exit(1)


# Experimental: the Personal Wiki targets 1.9.0 and its acceptance gates are
# open, so the command list says so wherever `co --help` is read.
schedule_app = _typer_app(
    help="This agent's own recurring work, from .co/schedule.yaml: see it, check it, run an entry now, "
         "pause or resume one. Bare 'co schedule' lists entries. Reads and writes .co/schedule-state.json only; "
         "never edits schedule.yaml.",
    epilog='Example:  co schedule run "morning report"  |  '
           "Workflow:  co schedule check  →  co schedule  →  co schedule run <name>  |  "
           "The running agent acts on run/pause/resume at its next tick (within a minute).  |  "
           "Back: co --help",
)
app.add_typer(schedule_app, name="schedule")


@schedule_app.callback(invoke_without_command=True)
def schedule_callback(ctx: typer.Context,
                      json_output: bool = typer.Option(False, "--json", help="Entries and problems as JSON")):
    """List scheduled entries: cadence, next run, last run, status, paused."""
    if ctx.invoked_subcommand is None:
        from .commands.schedule_commands import handle_list
        handle_list(json_output)
    elif json_output:
        raise typer.BadParameter("Put --json on bare co schedule or after co schedule list.")


@schedule_app.command("list", epilog="Example:  co schedule list --json  |  Back: co schedule --help")
def schedule_list(json_output: bool = typer.Option(False, "--json", help="Entries and problems as JSON")):
    """List each entry: cadence, next run, last run and status, reason, session, paused. Read-only."""
    from .commands.schedule_commands import handle_list
    handle_list(json_output)


@schedule_app.command("check", epilog="Example:  co schedule check  |  Back: co schedule --help")
def schedule_check():
    """Validate schedule.yaml the way the scheduler reads it; exit 1 naming each ignored entry. Read-only."""
    from .commands.schedule_commands import handle_check
    handle_check()


@schedule_app.command("run", epilog='Example:  co schedule run "morning report"  |  Back: co schedule --help')
def schedule_run(name: str = typer.Argument(..., help="Entry name, as co schedule lists it")):
    """Ask the running agent to run one entry at its next tick, even if paused. Writes schedule state."""
    from .commands.schedule_commands import handle_run
    handle_run(name)


@schedule_app.command("pause", epilog='Example:  co schedule pause "morning report"  |  Back: co schedule --help')
def schedule_pause(name: str = typer.Argument(..., help="Entry name, as co schedule lists it")):
    """Stop an entry firing without editing schedule.yaml; survives restarts and deploys. Writes schedule state."""
    from .commands.schedule_commands import handle_pause
    handle_pause(name)


@schedule_app.command("resume", epilog='Example:  co schedule resume "morning report"  |  Back: co schedule --help')
def schedule_resume(name: str = typer.Argument(..., help="Entry name, as co schedule lists it")):
    """Put a paused entry back on its schedule. Writes schedule state."""
    from .commands.schedule_commands import handle_resume
    handle_resume(name)


from .commands.wiki_commands import make_wiki_app

app.add_typer(make_wiki_app(_typer_app), name="wiki",
              short_help="Experimental: Personal Wiki — map first, investigate next. Targets 1.9.0.")


# Skills command group
skills_app = _typer_app(help=(
    "Your own SKILL.md files: discover them in ~/.claude, ~/.codex, ~/.cursor and ~/.kiro, copy, list "
    "and link them. Another person's published skills come from co sub instead. "
    "This group does not author or benchmark them.\n\n"
    "Project skills live in .co/skills/<name>/SKILL.md. Creating or improving a skill? "
    "Define its test cases first: co benchmark --help. Then write SKILL.md and score it: co eval --help.\n\n"
    "Bare co skills lists installed skills. Read-only."
), epilog="Example:  co skills discover  |  co skills copy invoice-check --to-project")
app.add_typer(skills_app, name="skills")


@skills_app.callback(invoke_without_command=True)
def skills_callback(ctx: typer.Context):
    """Skill discovery and management."""
    if ctx.invoked_subcommand is None:
        from .commands.skills_commands import handle_skills_list
        handle_skills_list()


@skills_app.command("discover", epilog="Example:  co skills discover --json --no-save")
def skills_discover(
    no_save: bool = typer.Option(False, "--no-save", help="Don't write ~/.co/skills/index.json"),
    json_out: bool = typer.Option(False, "--json", help="Print index as JSON"),
    include_namespaced: bool = typer.Option(False, "--include-namespaced", help="Include plugin-namespaced skills (names with ':')"),
):
    """Scan ~/.claude, ~/.codex, ~/.cursor, ~/.kiro, .co/skills for SKILL.md files. Writes ~/.co/skills/index.json unless --no-save."""
    from .commands.skills_commands import handle_skills_discover
    handle_skills_discover(save=not no_save, json_out=json_out, include_namespaced=include_namespaced)


@skills_app.command("copy", epilog="Example:  co skills copy invoice-check --to-project")
def skills_copy(
    names: List[str] = typer.Argument(None, help="Skill names to copy into ~/.co/skills/"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Restrict to a specific source (claude, codex, cursor, kiro, co-user, co-project)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skill"),
    all_: bool = typer.Option(False, "--all", "-a", help="Copy every discovered skill (dedupe by SOURCES priority)"),
    to_project: bool = typer.Option(False, "--to-project", help="Copy into this project's .co/skills/ — the only tier that deploys"),
):
    """Copy a discovered skill into ~/.co/skills/<name>/, or --to-project to ship it. Writes the copy there."""
    from .commands.skills_commands import handle_skills_copy
    handle_skills_copy(names=names or [], source=source, force=force, all_=all_,
                       to_project=to_project)


@skills_app.command("manifest", epilog="Example:  co skills manifest --stdout")
def skills_manifest(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Skills directory to scan (default: ~/.co/skills/)"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write to file (default: merge into ~/.co/agent.json); if path ends in agent.json, merge into its skills[] key"),
    stdout: bool = typer.Option(False, "--stdout", help="Print JSON to stdout instead of writing"),
):
    """Build skill metadata for oo-publish. Writes it into ~/.co/agent.json unless --stdout or --out."""
    from .commands.skills_commands import handle_skills_manifest
    handle_skills_manifest(path=path, out=out, stdout=stdout)


@skills_app.command("list", epilog="Example:  co skills list")
def skills_list():
    """List skills currently installed in ~/.co/skills/. Read-only."""
    from .commands.skills_commands import handle_skills_list
    handle_skills_list()


@skills_app.command("link", epilog="Example:  co skills link")
def skills_link(
    force: bool = typer.Option(False, "--force", help="Replace directories you own"),
):
    """Link ConnectOnion's bundled skills into Claude Code and Codex. Creates symlinks in ~/.claude/skills and ~/.codex/skills."""
    from .commands.skills_commands import handle_skills_link
    handle_skills_link(force=force)


# Trust command group
trust_app = _typer_app(
    help="Who may call your agent: contacts, whitelist, blocklist and admins, kept in this project's .co/. "
         "trust='careful' admits contacts and the whitelist; trust='strict' admits only the whitelist.",
    epilog="Example:  co trust add 0xabc...  |  co trust level 0xabc...",
)
app.add_typer(trust_app, name="trust")


@trust_app.callback(invoke_without_command=True)
def trust_callback(ctx: typer.Context):
    """Trust list management."""
    if ctx.invoked_subcommand is None:
        # Default to list
        from .commands.trust_commands import handle_trust_list
        handle_trust_list()


@trust_app.command("list", epilog="Example:  co trust list")
def trust_list():
    """List every address on each trust list. Read-only."""
    from .commands.trust_commands import handle_trust_list
    handle_trust_list()


@trust_app.command("level", epilog="Example:  co trust level 0xabc...")
def trust_level(address: str = typer.Argument(..., help="Address to check")):
    """Show whether an address is a stranger, contact, whitelisted or blocked. Read-only."""
    from .commands.trust_commands import handle_trust_level
    handle_trust_level(address)


@trust_app.command("add", epilog="Example:  co trust add 0xabc...  |  co trust add 0xabc... --whitelist")
def trust_add(
    address: str = typer.Argument(..., help="Address to add"),
    whitelist: bool = typer.Option(False, "-w", "--whitelist", help="Add to whitelist instead of contacts"),
):
    """Let an address call your agent: adds it to contacts, or --whitelist for trust='strict'. Writes the trust list."""
    from .commands.trust_commands import handle_trust_add
    handle_trust_add(address, whitelist)


@trust_app.command("remove", epilog="Example:  co trust remove 0xabc...")
def trust_remove(address: str = typer.Argument(..., help="Address to remove")):
    """Make an address a stranger again. Removes it from every trust list."""
    from .commands.trust_commands import handle_trust_remove
    handle_trust_remove(address)


@trust_app.command("block", epilog='Example:  co trust block 0xabc... --reason "spam"')
def trust_block(
    address: str = typer.Argument(..., help="Address to block"),
    reason: str = typer.Option("", "-r", "--reason", help="Reason for blocking"),
):
    """Refuse every call from an address. Writes the blocklist."""
    from .commands.trust_commands import handle_trust_block
    handle_trust_block(address, reason)


@trust_app.command("unblock", epilog="Example:  co trust unblock 0xabc...")
def trust_unblock(address: str = typer.Argument(..., help="Address to unblock")):
    """Accept calls from a blocked address again. Removes it from the blocklist."""
    from .commands.trust_commands import handle_trust_unblock
    handle_trust_unblock(address)


# Admin subcommand group
admin_app = _typer_app(help="Addresses that may command your agent (super admin only).",
                       epilog="Example:  co trust admin add 0xabc...")
trust_app.add_typer(admin_app, name="admin")


@admin_app.command("add", epilog="Example:  co trust admin add 0xabc...")
def admin_add(address: str = typer.Argument(..., help="Address to add as admin")):
    """Let an address command your agent. Writes .co/admins.txt."""
    from .commands.trust_commands import handle_admin_add
    handle_admin_add(address)


@admin_app.command("remove", epilog="Example:  co trust admin remove 0xabc...")
def admin_remove(address: str = typer.Argument(..., help="Address to remove from admins")):
    """Stop an address commanding your agent. Removes it from .co/admins.txt."""
    from .commands.trust_commands import handle_admin_remove
    handle_admin_remove(address)


# SMS command group. `co sms` (no args) shows the inbox without changing state.
sms_app = _typer_app(
    help="Pair a phone and read the Agent's encrypted SMS inbox. Bare 'co sms' shows the inbox (Read-only).",
    epilog="Example:  co sms inbox --pending",
)
app.add_typer(sms_app, name="sms")


@sms_app.callback(invoke_without_command=True)
def sms_callback(ctx: typer.Context):
    """With no subcommand, show the inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.sms_commands import handle_sms_inbox
        handle_sms_inbox()


@sms_app.command("pair", epilog="Example:  co sms pair --expires 900")
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
    """Create an Agent-signed QR challenge for one Android phone. Creates a one-time pairing; approving its code lets that phone upload SMS."""
    from .commands.sms_commands import handle_sms_pair
    handle_sms_pair(expires=expires, wait=wait and not json_output, json_output=json_output)


@sms_app.command("inbox", epilog="Example:  co sms inbox --pending -n 20")
def sms_inbox(
    last: int = typer.Option(10, "--last", "-n", min=1, max=100),
    pending: bool = typer.Option(False, "--pending", help="Only unacknowledged messages"),
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON"),
):
    """List decrypted SMS without acknowledging them. Read-only."""
    from .commands.sms_commands import handle_sms_inbox
    handle_sms_inbox(last=last, pending=pending, json_output=json_output)


sms_devices_app = _typer_app(
    help="List and revoke paired SMS phones. Bare 'co sms devices' lists them (Read-only).",
    epilog="Example:  co sms devices --json",
)
sms_app.add_typer(sms_devices_app, name="devices")


@sms_devices_app.callback(invoke_without_command=True)
def sms_devices_callback(ctx: typer.Context, json_output: bool = typer.Option(False, "--json")):
    """With no subcommand, list paired phones."""
    if ctx.invoked_subcommand is None:
        from .commands.sms_commands import handle_sms_devices
        handle_sms_devices(json_output=json_output)


@sms_devices_app.command("revoke", epilog="Example:  co sms devices revoke <device-id> --yes")
def sms_devices_revoke(
    device_id: str = typer.Argument(..., help="Device UUID from co sms devices"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
):
    """Revoke one phone's upload credential. Removes that phone's access; asks first unless --yes."""
    from .commands.sms_commands import handle_sms_revoke
    handle_sms_revoke(device_id, yes=yes)


# Email command group. `co email` (no args) shows the inbox.
email_app = _typer_app(
    help="Send and read email from the agent's address. Bare 'co email' shows the inbox (Read-only).",
    epilog="Example:  co email inbox --unread",
)
app.add_typer(email_app, name="email")


@email_app.callback(invoke_without_command=True)
def email_callback(ctx: typer.Context):
    """With no subcommand, show the inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.email_commands import handle_email_inbox
        handle_email_inbox()


@email_app.command("send", epilog="Example:  co email send you@example.com \"Weekly report\" \"Numbers are below.\"")
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
    """Send an email from the agent's address. Sends immediately."""
    from .commands.email_commands import handle_email_send
    handle_email_send(
        to, subject, message,
        idempotency_key=idempotency_key, from_address=from_address,
    )


@email_app.command("inbox", epilog="Example:  co email inbox --unread -n 20")
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
    address: str = typer.Option(
        None,
        "--address",
        "-a",
        help="Only mail delivered to this address (default: every address you can read)",
    ),
):
    """List recent received emails, across every address this account can read. Read-only."""
    from .commands.email_commands import handle_email_inbox
    handle_email_inbox(last=last, offset=offset, unread=unread, address=address)


@email_app.command("read", epilog="Example:  co email read 3")
def email_read(
    email_id: str = typer.Argument(..., help="Email # from the inbox list"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
):
    """Show one email's body without changing its unread state. Read-only unless --mark-read."""
    from .commands.email_commands import handle_email_read
    handle_email_read(email_id, mark_read=mark_read)


sent_app = _typer_app(
    help="List and read emails the agent has sent. Read-only.",
    epilog="Example:  co email sent --to you@example.com",
)
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


@sent_app.command("read", epilog="Example:  co email sent read 2")
def email_sent_read(email_id: str = typer.Argument(..., help="Email # from the sent list")):
    """Show one sent email's body. Read-only."""
    from .commands.email_commands import handle_email_sent_read
    handle_email_sent_read(email_id)


@email_app.command("addresses", epilog="Example:  co email addresses")
def email_addresses():
    """List every email address this account owns, marking the default sender. Read-only."""
    from .commands.email_commands import handle_email_addresses
    handle_email_addresses()


@email_app.command("default", epilog="Example:  co email default you@mail.openonion.ai")
def email_default(
    address: str = typer.Argument(..., help="One of your own addresses, e.g. aaron@mail.openonion.ai"),
):
    """Choose which of your addresses is the default sender. Changes your account's default."""
    from .commands.email_commands import handle_email_default
    handle_email_default(address)


@email_app.command("name", epilog="Examples:  co email name aaron  |  co email name aaron --buy")
def email_name(
    name: str = typer.Argument(..., help="Desired name, e.g. 'aaron' → aaron@openonion.ai"),
    buy: bool = typer.Option(False, "--buy", help="Claim it (deducts the price from your credits)"),
):
    """Check a custom email name's availability, or --buy to claim it. Read-only; --buy Charges your credits."""
    from .commands.email_commands import handle_email_name
    handle_email_name(name, buy=buy)


@email_app.command("share", epilog="Examples:  co email share you@mail.openonion.ai --with teammate@example.com --can send,read  |  co email share --list")
def email_share(
    address: Optional[str] = typer.Argument(None, help="One of your addresses (omit with --list)"),
    with_: Optional[str] = typer.Option(None, "--with", help="Grantee: public key or one of their addresses"),
    can: Optional[str] = typer.Option(None, "--can", help="Comma-separated capabilities: send,read"),
    list_: bool = typer.Option(False, "--list", help="Show what you've shared, and what's shared with you"),
):
    """Let another account send and/or read as one of your addresses, without moving it. Changes who can use it; --list is Read-only."""
    from .commands.email_commands import handle_email_share
    handle_email_share(address, with_=with_, can=can, list_=list_)


@email_app.command("unshare", epilog="Example:  co email unshare you@mail.openonion.ai --with teammate@example.com")
def email_unshare(
    address: str = typer.Argument(..., help="One of your addresses"),
    with_: str = typer.Option(..., "--with", help="Grantee to revoke: public key or one of their addresses"),
):
    """Revoke a grant. Removes that account's access. No key rotation — the address was never shared, only access to it."""
    from .commands.email_commands import handle_email_unshare
    handle_email_unshare(address, with_=with_)


@email_app.command("upgrade", epilog="Example:  co email upgrade plus --keep-address")
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
    """Upgrade email tier. Charges: deducts the monthly price from your credits."""
    from .commands.email_commands import handle_email_upgrade
    handle_email_upgrade(tier, domain=domain, alias=alias, keep_address=keep_address)


# One command, not a group: a group callback with positional arguments would
# swallow "list" as the address ('co transfer list' parses the group args
# first), so the listing mode is the literal address "list" instead.
@app.command("transfer", epilog='Example:  co transfer 0xabc... 5.00 --memo "May invoice"  |  co transfer list --sent')
def transfer(
    address: str = typer.Argument(..., help="Recipient 0x… address, or 'list' for your transfer history"),
    amount: Optional[float] = typer.Argument(None, help="Amount in USD credits, e.g. 5.00"),
    memo: Optional[str] = typer.Option(None, "--memo", help="Note stored with the transfer"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Send without the interactive confirmation"),
    sent: bool = typer.Option(False, "--sent", help="With list: only transfers you sent"),
    received: bool = typer.Option(False, "--received", help="With list: only transfers you received"),
    last: int = typer.Option(50, "--last", "-n", help="With list: how many to show"),
):
    """Send credits to another agent address, or list transfers. Sends irreversibly from your balance, confirming first unless --yes; list is Read-only."""
    from .commands.transfer_commands import handle_transfer_list, handle_transfer_send
    if address == "list":
        handle_transfer_list(sent=sent, received=received, last=last)
    else:
        handle_transfer_send(address, amount, memo=memo, yes=yes)


# Telegram command group. The bot is the user's own (@BotFather), so the token
# lives in their keys.env -- no OpenOnion credential and nothing billed.
telegram_app = _typer_app(
    help="Telegram bot: send, plus experimental listen, receive and reply. Sends as your bot.",
    epilog='Example:  co telegram send -1001234567890 "Hello"  |  co telegram check  |  co telegram receive -t 60')
# send has shipped since 1.7.0; the inbox verbs (#1671) have not met a live bot yet.
app.add_typer(telegram_app, name="telegram",
              short_help="Telegram bot: send, plus experimental listen, receive and reply.")


# NegativeIds: a Telegram group is `-100123`, and `send -100123 hi` was
# "No such option: -1".
@telegram_app.command("send", cls=NegativeIds,
                      epilog='Example:  co telegram send -1001234567890 "Hello"  |  co telegram send @mychannel "Hello"')
def telegram_send(
    chat: str = typer.Argument(..., help="Chat id, or @channelname for a channel"),
    message: str = typer.Argument(..., help="The text to send"),
):
    """Send a Telegram message. Sends it as your bot."""
    from .commands.telegram_commands import handle_telegram_send
    handle_telegram_send(chat, message)


# The ids each provider's help examples use: (chat, message).
_INBOX_IDS = {
    "feishu": ("oc_abc...", "om_abc..."),
    "lark": ("oc_abc...", "om_abc..."),
    "whatsapp": ("61412345678@s.whatsapp.net", "<message-id>"),
    "telegram": ("-1001234567890", "<message-id>"),
    "discord": ("<channel-id>", "<message-id>"),
}


# Inbox providers: feishu, lark, whatsapp, telegram. One directory per provider under
# ~/.co/inbox/, the same nine verbs on each. The tool knows nothing about
# agents; anything that can read a file consumes it (DD-063).
def _inbox_group(name: str, help_text: str, *, group: Optional[typer.Typer] = None,
                 with_send: bool = True, writes: bool = False) -> typer.Typer:
    """The inbox verbs on a fresh group, or on an existing one that already has
    its own `send`: `co telegram send` shipped first, and its output is part of
    its contract, so Telegram gains the other verbs beside it.

    `writes`: the provider implements edit, delete and react. Only WhatsApp
    does; elsewhere the verbs stay (one set of verbs everywhere) but their help
    says they refuse, instead of promising an id they never print."""
    co, chat, msg = f"co {name}", *_INBOX_IDS[name]
    group = group if group is not None else _typer_app(
        help=help_text,
        epilog=f'Example:  {co} check  |  {co} receive -t 60  |  {co} reply {msg} "On it"')
    refuses = None if writes else ("Not implemented for this provider yet; says which endpoint would do it. "
                                   "Read-only: it refuses and sends nothing.")

    @group.command("listen", epilog=f"Example:  {co} listen  |  {co} listen --raw")
    def _listen(raw: bool = typer.Option(False, "--raw", help="Keep the provider payload in inbox.jsonl")):
        """Hold the connection; write every message to the inbox. Ctrl-C stops. Runs in the foreground and writes to ~/.co/inbox/."""
        from .commands.listen_commands import handle_listen
        handle_listen(name, raw=raw)

    @group.command("receive", epilog=f"Example:  {co} receive -t 60  |  {co} receive -t 0 --no-start  |  {co} receive --context 5")
    def _receive(
        timeout: Optional[float] = typer.Option(None, "--timeout", "-t", help="Seconds to wait; 0 looks once. Exit 124 if none."),
        no_start: bool = typer.Option(False, "--no-start", help="Do not start a background listener"),
        context: int = typer.Option(0, "--context", min=0, max=200, metavar="N",
                                    help="Also include the N turns before it in that chat"),
    ):
        """Print the next message as one JSON line, taking it from the queue. Changes the queue; starts a background listener unless --no-start."""
        from .commands.listen_commands import handle_receive
        handle_receive(name, timeout=timeout, start=not no_start, context=context)

    def _send(
        chat: str = typer.Argument(..., help="Chat id"),
        text: Optional[str] = typer.Argument(None, help="The text; omitted means stdin"),
        reply_to: Optional[str] = typer.Option(None, "--reply-to", help="Message id to reply to"),
        plain: bool = typer.Option(False, "--plain", help="Send the text as typed, without reading it as Markdown"),
    ):
        """Send text to a chat. Prints the new message id. Sends a message to the chat."""
        from .commands.listen_commands import handle_send
        handle_send(name, chat, text, reply_to=reply_to, plain=plain)

    if with_send:
        group.command("send", cls=NegativeIds,
                      epilog=f'Example:  {co} send {chat} "Hello"  |  echo "Hello" | {co} send {chat}  |  '
                             f'{co} send {chat} "Thanks" --reply-to {msg}')(_send)

    # Every verb that takes a chat or message id parses with NegativeIds:
    # Telegram ids start with "-" for groups and channels.
    @group.command("reply", cls=NegativeIds,
                   epilog=f'Example:  {co} reply {msg} "On it"  |  {co} reply {msg} "One more thing" --again')
    def _reply(
        message_id: str = typer.Argument(..., help="Id of a received message"),
        text: Optional[str] = typer.Argument(None, help="The text; omitted means stdin"),
        again: bool = typer.Option(False, "--again", help="Reply even if this message was already answered"),
        plain: bool = typer.Option(False, "--plain", help="Send the text as typed, without reading it as Markdown"),
    ):
        """Reply where a received message was asked. Prints the new id. Sends a message to that chat."""
        from .commands.listen_commands import handle_reply
        handle_reply(name, message_id, text, again=again, plain=plain)

    @group.command("edit", cls=NegativeIds, help=refuses,
                   epilog=f'Example:  {co} edit {msg} "Fixed typo"  |  echo "Fixed typo" | {co} edit {msg}')
    def _edit(
        message_id: str = typer.Argument(..., help="Id of a message this account sent"),
        text: Optional[str] = typer.Argument(None, help="The new text; omitted means stdin"),
        plain: bool = typer.Option(False, "--plain", help="Send the text as typed, without reading it as Markdown"),
    ):
        """Replace the text of a message this account sent. Prints the edit's id. Changes it for everyone in the chat."""
        from .commands.listen_commands import handle_edit
        handle_edit(name, message_id, text, plain=plain)

    @group.command("delete", cls=NegativeIds, help=refuses, epilog=f"Example:  {co} delete {msg}")
    def _delete(message_id: str = typer.Argument(..., help="Id of a message to delete for everyone")):
        """Delete a message for everyone. Prints the deletion's id. Deletes it from the chat."""
        from .commands.listen_commands import handle_delete
        handle_delete(name, message_id)

    @group.command("react", cls=NegativeIds, help=refuses,
                   epilog=f'Example:  {co} react {msg} "👍"  |  {co} react {msg} ""')
    def _react(
        message_id: str = typer.Argument(..., help="Id of any message, received or sent"),
        emoji: str = typer.Argument(..., help='The emoji; "" removes our reaction'),
    ):
        """React to a message, anyone's. Prints the reaction's id. Sends a reaction; "" removes ours."""
        from .commands.listen_commands import handle_react
        handle_react(name, message_id, emoji)

    @group.command("done", cls=NegativeIds, epilog=f"Example:  {co} done {msg}")
    def _done(message_id: str = typer.Argument(..., help="Id of a taken message")):
        """Forget a taken message without replying, so it does not come back in an hour. Changes the local queue; sends nothing."""
        from .commands.listen_commands import handle_done
        handle_done(name, message_id)

    @group.command("check", epilog=f"Example:  {co} check")
    def _check():
        """Credentials, connectivity, listener state, unread count. Exit 3 on a problem. Changes nothing in the chat or the queue."""
        from .commands.listen_commands import handle_check
        handle_check(name)

    @group.command("ls", epilog=f"Example:  {co} ls")
    def _ls():
        """Unread messages: id, chat, sender, text. Nothing is taken from the queue; malformed queue files are moved to quarantine. Changes nothing in the chat."""
        from .commands.listen_commands import handle_ls
        handle_ls(name)

    @group.command("chats", epilog=f"Example:  {co} chats")
    def _chats():
        """Conversations seen: chat id, kind, messages, for-us, last activity. Read-only."""
        from .commands.listen_commands import handle_chats
        handle_chats(name)

    @group.command("log", epilog=f"Example:  {co} log -f  |  {co} log --chat {chat} --since 7d  |  {co} log -n 20")
    def _log(
        follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing new messages"),
        chat: Optional[str] = typer.Option(None, "--chat", help="Only this conversation; ids come from `chats`"),
        sender: Optional[str] = typer.Option(None, "--sender", help="Only this sender, by id or name"),
        since: Optional[str] = typer.Option(None, "--since", metavar="30d|2026-06-01",
                                            help="Only what arrived in this window"),
        last: Optional[int] = typer.Option(None, "--last", "-n", min=1,
                                           help="Keep only the most recent N"),
    ):
        """Every message ever received, one JSON line each. Changes nothing in the chat or the queue."""
        from .commands.listen_commands import handle_log
        handle_log(name, follow=follow, chat=chat, sender=sender, since=since, last=last)

    # `consume`, not `serve`. Nothing here serves anything — it takes messages
    # off a queue and hands each to a command, which is what DD-063 calls a
    # consumer throughout, and what `lark-cli event consume` calls it too. A
    # verb an agent can guess is worth more than one it has to be told.
    @group.command("consume", context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
                   epilog=f"Example:  {co} consume python3 bot.py  |  {co} consume --once ./answer.sh  |  "
                          f"{co} consume --workers 4 --context 5 python3 bot.py")
    def _consume(
        command: List[str] = typer.Argument(..., help="Command run per message: message on stdin, reply on stdout"),
        once: bool = typer.Option(False, "--once", help="Handle one message and exit"),
        workers: int = typer.Option(1, "--workers", min=1,
                                    help="Conversations to answer at once (default 1, one after another)"),
        context: int = typer.Option(0, "--context", min=0, max=200, metavar="N",
                                    help="Also give the command the N turns before each message"),
    ):
        """Loop: receive, run COMMAND with the message on stdin, reply with its stdout. Runs COMMAND and sends its output as the reply."""
        from .commands.listen_commands import handle_consume
        handle_consume(name, command, once=once, workers=workers, context=context)

    return group


app.add_typer(_inbox_group("feishu", "Feishu bot as an inbox: listen, receive, send, reply. Sends as your bot."), name="feishu")
app.add_typer(_inbox_group("lark", "Lark (global Feishu) bot as an inbox: listen, receive, send, reply. Sends as your bot."), name="lark")
# Discord too: its Gateway client is `websockets`, already a core dependency.
# Experimental: ported in #1674 and tested against fakes only, never a live Gateway.
app.add_typer(_inbox_group("discord", "Experimental: Discord bot as an inbox: listen, receive, send, reply. Sends as your bot."), name="discord",
              short_help="Experimental: Discord bot as an inbox: listen, receive, send, reply.")
_whatsapp_app = _inbox_group("whatsapp", "WhatsApp as an inbox: listen, receive, send, reply. Sends as your linked account.",
                             writes=True)
_whatsapp_groups = _typer_app(
    help="Start a group, or add people to one. One line per person. Creates or changes WhatsApp groups.",
    epilog='Example:  co whatsapp group create "Acme onboarding" 61412345678 61498765432  |  '
           'co whatsapp group add 120363012345678901@g.us 61412345678')


@_whatsapp_groups.command(
    "create", epilog='Example:  co whatsapp group create "Acme onboarding" 61412345678 61498765432')
def _whatsapp_group_create(
    subject: str = typer.Argument(..., help="The group's name"),
    phones: List[str] = typer.Argument(..., help="Phone numbers with country code, e.g. 61412345678"),
):
    """Create a group with these people. Prints its chat id, then one line per person. Creates the group and adds them."""
    from .commands.listen_commands import handle_group
    handle_group("whatsapp", phones, subject=subject)


@_whatsapp_groups.command("add", epilog="Example:  co whatsapp group add 120363012345678901@g.us 61412345678 61498765432")
def _whatsapp_group_add(
    chat: str = typer.Argument(..., help="The group's chat id, from `co whatsapp chats`"),
    phones: List[str] = typer.Argument(..., help="Phone numbers with country code"),
):
    """Add people to a group this account administers. One line per person. Changes the group's members."""
    from .commands.listen_commands import handle_group
    handle_group("whatsapp", phones, chat=chat)


_whatsapp_app.add_typer(_whatsapp_groups, name="group")
app.add_typer(_whatsapp_app, name="whatsapp")
# Telegram keeps the `send` it shipped with and gains every other inbox verb on
# the same group, with the same TELEGRAM_BOT_TOKEN.
_inbox_group("telegram", "", group=telegram_app, with_send=False)


# Gmail command group. `co gmail` (no args) shows the Gmail inbox.
# Uses the GOOGLE_* OAuth tokens saved to .env by `co auth google`.
from .commands.gmail_mailbox_registration import MailboxCommand, register_mailbox_commands

gmail_app = _typer_app(
    help="Send and read email from your Gmail account. Bare 'co gmail' shows the inbox (Read-only).",
    epilog="Example:  co gmail inbox --unread  |  co gmail send you@example.com \"Hi\" \"Quick note\"")
app.add_typer(gmail_app, name="gmail")


@gmail_app.callback(invoke_without_command=True)
def gmail_callback(ctx: typer.Context, json_output: bool = typer.Option(False, "--json")):
    """With no subcommand, show the Gmail inbox."""
    if ctx.invoked_subcommand is None:
        if json_output:
            from .commands.gmail_mailbox_commands import handle_mailbox
            return handle_mailbox("inbox", json_output=True, last=10, unread=False, cursor=None)
        from .commands.gmail_commands import handle_gmail_inbox
        handle_gmail_inbox()
    elif json_output:
        from .commands.gmail_mailbox_registration import usage_error
        usage_error("Put --json after the leaf command, or use it with bare co gmail.", "", True)


@gmail_app.command("inbox", cls=MailboxCommand,
                   epilog="Example:  co gmail inbox --unread -n 20  |  co gmail inbox --since 7d")
def gmail_inbox(
    last: int = typer.Option(10, "--last", "-n", min=1, max=500, help="How many emails to show"),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread emails"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="Continuation from the same account, query and limit (15 minute expiry)"),
    since: str = typer.Option(
        None, "--since", metavar="30d|2026-06-01",
        help="Everything in a window instead of the last -n. Nd/Nw/Nm/Ny or a date.",
    ),
    until: str = typer.Option(None, "--until", help="End of the window; defaults to now"),
):
    """List recent inbox emails, numbered for read/reply. Read-only."""
    if json_output or cursor:
        # The window composes by narrowing the query the envelope already pages
        # through, so the cursor, the cap and `complete` keep the meanings they
        # had: a cursor is bound to its query, and a different window is a
        # different query.
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("inbox", json_output=json_output, last=last, unread=unread,
                              cursor=cursor, since=since, until=until)
    from .commands.gmail_commands import handle_gmail_inbox
    handle_gmail_inbox(last=last, unread=unread, since=since, until=until)


@gmail_app.command("read", cls=MailboxCommand,
                   epilog="Example:  co gmail read <message-id>  |  co gmail read 3 --listing <listing-id>")
def gmail_read(
    email_id: str = typer.Argument(..., help="Full message ID, or row # together with --listing ID"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
):
    """Show one email's full body without changing its unread state. Read-only unless --mark-read."""
    if json_output:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("read", json_output=json_output, email_id=email_id, mark_read=mark_read, listing=listing)
    from .commands.gmail_commands import handle_gmail_read
    handle_gmail_read(email_id, mark_read=mark_read, listing=listing)


@gmail_app.command("reply", epilog="Example:  co gmail reply <message-id> \"Sounds good\"  |  "
                                    "co gmail reply 3 \"Sounds good\" --listing <listing-id>")
def gmail_reply(
    email_id: str = typer.Argument(..., help="Full message ID, or row # together with --listing ID"),
    message: str = typer.Argument(..., help="Reply body, or '-' to read stdin"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
):
    """Reply to an email from the last listing. Sends immediately, without a preview."""
    from .commands.gmail_commands import handle_gmail_reply
    handle_gmail_reply(email_id, message, listing=listing)


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
    """Send an email from your Gmail account. Sends immediately, without a preview."""
    from .commands.gmail_commands import handle_gmail_send
    handle_gmail_send(to, subject, message, cc=cc, bcc=bcc, attachments=attach)


@gmail_app.command("sent", cls=MailboxCommand, epilog="Example:  co gmail sent -n 5")
def gmail_sent(
    last: int = typer.Option(10, "--last", "-n", min=1, max=500, help="How many emails to show"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="Continuation from the same account, query and limit (15 minute expiry)"),
):
    """List recently sent emails. Read-only."""
    if json_output or cursor:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("sent", json_output=json_output, last=last, cursor=cursor)
    from .commands.gmail_commands import handle_gmail_sent
    handle_gmail_sent(last=last)


@gmail_app.command("search", cls=MailboxCommand,
                   epilog="Example:  co gmail search \"from:alice@example.com is:unread\" -n 20")
def gmail_search(
    query: str = typer.Argument(..., help="Gmail search query, e.g. 'from:alice@example.com'"),
    last: int = typer.Option(10, "--last", "-n", min=1, max=500, help="How many matches to show"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="Continuation from the same account, query and limit (15 minute expiry)"),
):
    """Search your mail with Gmail query syntax. Read-only."""
    if json_output or cursor:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("search", json_output=json_output, query=query, last=last, cursor=cursor)
    from .commands.gmail_commands import handle_gmail_search
    handle_gmail_search(query, last=last)


# Drafts are a nested, explicit workflow: editing never sends, and the send
# command always previews and confirms. Keeping these under `co gmail draft`
# makes the safe path discoverable without changing the immediate-send command.
gmail_draft_app = _typer_app(
    help="Create, inspect, and edit Gmail drafts; sending always asks for confirmation. Only draft send Sends mail.",
    epilog="Example:  co gmail draft create you@example.com \"Hi\" \"Quick note\"  |  co gmail draft review <draft-id>")
gmail_app.add_typer(gmail_draft_app, name="draft")


@gmail_draft_app.command("list", cls=MailboxCommand, epilog="Example:  co gmail draft list -n 5")
def gmail_draft_list(
    last: int = typer.Option(20, "--last", "-n", min=1, max=500, help="How many drafts to show"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
    cursor: Optional[str] = typer.Option(None, "--cursor", help="Continuation from the same account, query and limit (15 minute expiry)"),
):
    """List Gmail drafts, numbered for later draft commands. Read-only."""
    if json_output or cursor:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("draft.list", json_output=json_output, last=last, cursor=cursor)
    from .commands.gmail_commands import handle_gmail_draft_list
    handle_gmail_draft_list(last=last)


@gmail_draft_app.command("create", epilog="Example:  co gmail draft create you@example.com \"Hi\" \"Quick note\" --cc team@example.com")
def gmail_draft_create(
    to: str = typer.Argument(..., help="Recipient address (comma-separated for several)"),
    subject: str = typer.Argument(..., help="Email subject"),
    message: str = typer.Argument(..., help="Email body, or '-' to read stdin"),
    cc: str = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: str = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
):
    """Create an unsent Gmail draft. Creates it in Gmail; nothing is sent."""
    from .commands.gmail_commands import handle_gmail_draft_create
    handle_gmail_draft_create(to, subject, message, cc=cc, bcc=bcc)


@gmail_draft_app.command("attach", epilog="Example:  co gmail draft attach <draft-id> report.pdf  |  "
                                           "co gmail draft attach <draft-id> <file-id> --drive --link")
def gmail_draft_attach(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row # together with --listing ID"),
    source: str = typer.Argument(..., help="Local path, or Drive file #/id with --drive"),
    drive: bool = typer.Option(False, "--drive", help="Read the source from the last Drive listing or a Drive id"),
    link: bool = typer.Option(False, "--link", help="With --drive, append its web link instead of attaching bytes"),
    drive_listing: Optional[str] = typer.Option(None, "--drive-listing", help="Drive listing token required for a Drive row number"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
):
    """Stage a local/Drive file, or append a Drive link, without sending. Changes the draft only."""
    from .commands.gmail_commands import handle_gmail_draft_attach
    handle_gmail_draft_attach(draft_id, source, drive=drive, link=link, listing=listing, drive_listing=drive_listing)


@gmail_draft_app.command("remove", epilog="Example:  co gmail draft remove <draft-id> 2")
def gmail_draft_remove(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row # together with --listing ID"),
    attachment: int = typer.Argument(..., min=1, help="Attachment # from draft preview"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
):
    """Remove one staged attachment; the draft remains unsent. Changes the draft only."""
    from .commands.gmail_commands import handle_gmail_draft_remove
    handle_gmail_draft_remove(draft_id, attachment, listing=listing)


@gmail_draft_app.command("replace", epilog="Example:  co gmail draft replace <draft-id> 1 report-v2.pdf")
def gmail_draft_replace(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row # together with --listing ID"),
    attachment: int = typer.Argument(..., min=1, help="Attachment # from draft preview"),
    source: str = typer.Argument(..., help="Local path, or Drive file #/id with --drive"),
    drive: bool = typer.Option(False, "--drive", help="Read the replacement from Drive"),
    link: bool = typer.Option(False, "--link", help="Replace with a managed Drive link; requires --drive"),
    drive_listing: Optional[str] = typer.Option(None, "--drive-listing", help="Drive listing token required for a Drive row number"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
):
    """Atomically replace one staged attachment without sending. Changes the draft only."""
    from .commands.gmail_commands import handle_gmail_draft_replace
    handle_gmail_draft_replace(draft_id, attachment, source, drive=drive, link=link, listing=listing, drive_listing=drive_listing)


@gmail_draft_app.command("preview", cls=MailboxCommand, epilog="Example:  co gmail draft preview <draft-id>")
def gmail_draft_preview(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row # together with --listing ID"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
    json_output: bool = typer.Option(False, "--json", help="Versioned result envelope with full IDs and account context"),
):
    """Print recipients, body, and the final attachment manifest. Read-only."""
    if json_output:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("draft.preview", json_output=json_output, draft_id=draft_id, listing=listing)
    from .commands.gmail_commands import handle_gmail_draft_preview
    handle_gmail_draft_preview(draft_id, listing=listing)


@gmail_draft_app.command("review", cls=MailboxCommand, epilog="Example:  co gmail draft review <draft-id>")
def gmail_draft_review(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row with --listing"),
    listing: Optional[str] = typer.Option(None, "--listing"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Review the complete outgoing content and produce its confirmation token. Read-only."""
    if json_output:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("draft.review", draft_id=draft_id, listing=listing, json_output=True)
    from .commands.gmail_commands import handle_gmail_draft_review
    handle_gmail_draft_review(draft_id, listing=listing)


@gmail_draft_app.command("send", cls=MailboxCommand,
                         epilog="Example:  co gmail draft send <draft-id>  |  co gmail draft send <draft-id> --confirm <token>")
def gmail_draft_send(
    draft_id: str = typer.Argument(..., help="Full draft ID, or row # together with --listing ID"),
    listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed beside row numbers; required when using a number"),
    confirm: Optional[str] = typer.Option(None, "--confirm", help="Token from draft review; required without a real TTY"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Send reviewed MIME; require a token or default-No interactive confirmation. Sends the draft once confirmed."""
    if json_output:
        from .commands.gmail_mailbox_commands import handle_mailbox
        return handle_mailbox("draft.send", draft_id=draft_id, listing=listing, confirm=confirm, json_output=True)
    from .commands.gmail_commands import handle_gmail_draft_send
    if confirm is None:
        handle_gmail_draft_send(draft_id, listing=listing)
    else:
        handle_gmail_draft_send(draft_id, listing=listing, confirm=confirm)


register_mailbox_commands(gmail_app, _OneSuggestion)


# Google Drive command group. `co gdrive` (no args) lists recent files.
# Uses the GOOGLE_* OAuth tokens saved to .env by `co auth google`.
gdrive_app = _typer_app(
    help="List, search, download, and upload Google Drive files. Bare 'co gdrive' lists recent files (Read-only).",
    epilog="Example:  co gdrive search \"Q3 report\"  |  co gdrive get <file-id> --to ~/Downloads")
app.add_typer(gdrive_app, name="gdrive")


@gdrive_app.callback(invoke_without_command=True)
def gdrive_callback(ctx: typer.Context):
    """With no subcommand, list recent Drive files."""
    if ctx.invoked_subcommand is None:
        from .commands.gdrive_commands import handle_gdrive_list
        handle_gdrive_list()


@gdrive_app.command("list", epilog="Example:  co gdrive list -n 50")
def gdrive_list(
    last: int = typer.Option(20, "--last", "-n", help="How many files to show"),
):
    """List recently modified files, numbered for get/rm. Read-only."""
    from .commands.gdrive_commands import handle_gdrive_list
    handle_gdrive_list(last=last)


@gdrive_app.command("search", epilog="Example:  co gdrive search \"Q3 report\" -n 10")
def gdrive_search(
    query: str = typer.Argument(..., help="Text to look for in file names"),
    last: int = typer.Option(20, "--last", "-n", help="How many matches to show"),
):
    """Search Drive by file name. Read-only."""
    from .commands.gdrive_commands import handle_gdrive_search
    handle_gdrive_search(query, last=last)


from .commands.gmail_mailbox_registration import DriveInfoCommand


@gdrive_app.command("info", cls=DriveInfoCommand,
                    epilog="Example:  co gdrive info <file-id>  |  co gdrive info 2 --listing <listing-id>")
def gdrive_info(
    listing: Optional[str] = typer.Option(None, "--listing", help="Frozen Drive listing token required for a row number"),
    file_id: str = typer.Argument(..., help="Full Drive ID, or row with --listing"),
    json_output: bool = typer.Option(False, "--json", help="Versioned inspection result"),
):
    """Inspect metadata and export format without downloading or changing sharing. Read-only."""
    from .commands.gdrive_commands import handle_gdrive_info
    handle_gdrive_info(file_id, listing=listing, json_output=json_output)


@gdrive_app.command("get", epilog="Example:  co gdrive get <file-id> --to ~/Downloads  |  "
                                  "co gdrive get 2 --listing <listing-id>")
def gdrive_get(
    listing: Optional[str] = typer.Option(None, "--listing", help="Frozen Drive listing token required for a row number"),
    file_id: str = typer.Argument(..., help="Full Drive ID, or row with --listing"),
    dest: str = typer.Option(".", "--to", help="Destination directory or file path"),
):
    """Download a file (Google Docs/Sheets/Slides are exported). Writes a local file; Drive is unchanged."""
    from .commands.gdrive_commands import handle_gdrive_get
    handle_gdrive_get(file_id, dest=dest, listing=listing)


@gdrive_app.command("put", epilog="Example:  co gdrive put report.pdf --name \"Q3 report.pdf\"")
def gdrive_put(
    path: str = typer.Argument(..., help="Local file to upload"),
    name: str = typer.Option(None, "--name", help="Name to give it in Drive"),
):
    """Upload a local file to Drive. Uploads it immediately."""
    from .commands.gdrive_commands import handle_gdrive_put
    handle_gdrive_put(path, name=name)


@gdrive_app.command("rm", epilog="Example:  co gdrive rm <file-id>  |  co gdrive rm 2 --listing <listing-id>")
def gdrive_rm(
    listing: Optional[str] = typer.Option(None, "--listing", help="Frozen Drive listing token required for a row number"),
    file_id: str = typer.Argument(..., help="Full Drive ID, or row with --listing"),
):
    """Move a file to the Drive trash (recoverable). Removes it at once; Drive deletes it after 30 days."""
    from .commands.gdrive_commands import handle_gdrive_rm
    handle_gdrive_rm(file_id, listing=listing)


_YOUTUBE_AUTH_HELP = (
    "Connect once with co auth google, then use the saved Google login like co gmail. "
    "Tokens refresh automatically through the existing Google OAuth broker. "
    "YouTube operations use the official Data API. Uploads default to private; "
    "unverified API projects can force private visibility. --confirm is an external write."
)
youtube_app = _typer_app(help="YouTube Data API using your saved Google login. Writes preview by default.",
                         epilog=f"Example:  co youtube list -n 5  |  {_YOUTUBE_AUTH_HELP}")
app.add_typer(youtube_app, name="youtube")


@youtube_app.callback(invoke_without_command=True)
def youtube_callback(ctx: typer.Context,
                     json_output: bool = typer.Option(False, "--json", help="Emit one JSON object")):
    if ctx.invoked_subcommand is None:
        from .commands.youtube_commands import handle_youtube_list
        handle_youtube_list(json_output=json_output)
    elif json_output:
        raise typer.BadParameter("Place --json after the subcommand; see co youtube --help.")


@youtube_app.command("channel", epilog=f"Example:  co youtube channel @yourhandle  |  {_YOUTUBE_AUTH_HELP}")
def youtube_channel(target: Optional[str] = typer.Argument(None, help="UC channel ID, @handle, or channel URL; default is your channel"),
                    json_output: bool = typer.Option(False, "--json")):
    """Read a channel and its uploads playlist ID. Read-only."""
    from .commands.youtube_commands import handle_youtube_channel
    handle_youtube_channel(target, json_output=json_output)


@youtube_app.command("list", epilog=f"Example:  co youtube list @yourhandle -n 10  |  {_YOUTUBE_AUTH_HELP}")
def youtube_list(target: Optional[str] = typer.Argument(None, help="Channel ID, @handle or URL; default is your channel"),
                 last: int = typer.Option(20, "--last", "-n", min=1, max=200),
                 json_output: bool = typer.Option(False, "--json")):
    """List recent uploads; numbers refer to this exact listing. Read-only."""
    from .commands.youtube_commands import handle_youtube_list
    handle_youtube_list(target, last, json_output=json_output)


@youtube_app.command("video", epilog=f"Example:  co youtube video <video-id>  |  co youtube video 3  |  {_YOUTUBE_AUTH_HELP}")
def youtube_video(item: str = typer.Argument(..., help="Number from your last listing, video ID, or URL; no media download"),
                  json_output: bool = typer.Option(False, "--json")):
    """Read one video's metadata and returned counts. Read-only."""
    from .commands.youtube_commands import handle_youtube_video
    handle_youtube_video(item, json_output=json_output)


@youtube_app.command("put", epilog=(
    "Example:  co youtube put talk.mp4 --title \"Launch talk\" --channel <channel-id>  |  "
    f"co youtube put talk.mp4 --title \"Launch talk\" --channel <channel-id> --confirm <digest>  |  {_YOUTUBE_AUTH_HELP}"))
def youtube_put(path: str = typer.Argument(..., help="Local video file"),
                title: str = typer.Option(..., "--title"),
                channel: str = typer.Option(..., "--channel", help="Exact UC channel ID, checked again before upload"),
                description: str = typer.Option("", "--description"),
                privacy: str = typer.Option("private", "--privacy", help="private, unlisted, or public"),
                category: str = typer.Option("22", "--category"),
                dry_run: bool = typer.Option(False, "--dry-run", help="Explicit preview; also the default without --confirm"),
                confirm: Optional[str] = typer.Option(None, "--confirm", help="Exact preview digest; consumes this plan once and uploads"),
                json_output: bool = typer.Option(False, "--json")):
    """Preview locally; upload only with the current plan's --confirm digest. Uploads only with --confirm."""
    from .commands.youtube_commands import handle_youtube_put
    handle_youtube_put(path, title, channel, description, privacy, category, dry_run, confirm, json_output)


@youtube_app.command("update", epilog=(
    "Example:  co youtube update <video-id> --title \"New title\"  |  "
    f"co youtube update <video-id> --title \"New title\" --confirm <digest>  |  {_YOUTUBE_AUTH_HELP}"))
def youtube_update(item: str = typer.Argument(..., help="Listing number, video ID, or URL"),
                   title: Optional[str] = typer.Option(None, "--title"),
                   description: Optional[str] = typer.Option(None, "--description"),
                   dry_run: bool = typer.Option(False, "--dry-run", help="Explicit preview; also the default without --confirm"),
                   confirm: Optional[str] = typer.Option(None, "--confirm", help="Exact digest of the current metadata preview; performs one update"),
                   json_output: bool = typer.Option(False, "--json")):
    """Preview title/description edits without changing privacy or other parts. Changes the video only with --confirm."""
    from .commands.youtube_commands import handle_youtube_update
    handle_youtube_update(item, title, description, dry_run, confirm, json_output)


# TikTok stops short of TikTok itself. `post` seals a local plan and `inspect`
# reads login evidence from a browser tab the caller already owns. There is no
# submission adapter: nobody has yet seen the logged-in upload form, and a
# publish button written from guesses would be a publish button nobody tested.
tiktok_app = _typer_app(
    help="Experimental: TikTok local post plans and read-only browser readiness. Upload/publish is not implemented. "
         "Read-only on TikTok.",
    epilog="Example:  co tiktok post clip.mp4 --caption \"Launch day\" --account @yourhandle")
app.add_typer(tiktok_app, name="tiktok",
              short_help="Experimental: TikTok post plans and read-only readiness. Nothing is uploaded.")


@tiktok_app.callback(invoke_without_command=True)
def tiktok_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        print("Start a local post plan: co tiktok post --help")


@tiktok_app.command("post", epilog="Example:  co tiktok post clip.mp4 --caption \"Launch day\" --account @yourhandle")
def tiktok_post(path: str = typer.Argument(..., help="Local video file; preview never uploads it"),
                caption: str = typer.Option(..., "--caption"),
                account: str = typer.Option(..., "--account", help="Intended @handle; not an authenticated identity assertion"),
                dry_run: bool = typer.Option(False, "--dry-run", help="Explicit local preview (the default)"),
                confirm: Optional[str] = typer.Option(None, "--confirm", help="Validate a plan digest, then refuse submission until the browser adapter is verified"),
                json_output: bool = typer.Option(False, "--json")):
    """Prepare a local plan. No TikTok draft, upload, or post is created. Read-only: the plan is printed, not saved."""
    from .commands.tiktok_commands import handle_tiktok_post
    handle_tiktok_post(path, caption, account, dry_run, confirm, json_output)


@tiktok_app.command("inspect", epilog="Example:  co tiktok inspect --tab <tab-id>")
def tiktok_inspect(tab: str = typer.Option(..., "--tab", help="An existing co browser tab owned by this task"),
                   json_output: bool = typer.Option(False, "--json")):
    """Capture and verify login/readiness evidence; never click or upload. Writes local evidence: screenshots and a saved page context."""
    from .commands.tiktok_browser_commands import handle_inspect
    handle_inspect(tab, json_output)

from .commands.gcalendar_commands import gcalendar_app
gcalendar_app.info.cls = _OneSuggestion
app.add_typer(gcalendar_app, name="gcalendar")

from .commands.synology_cli import syno_app
app.add_typer(syno_app, name="syno")


# Outlook command group. `co outlook` (no args) shows the Outlook inbox.
# Uses the MICROSOFT_* OAuth tokens saved to .env by `co auth microsoft`.
outlook_app = _typer_app(
    help="Your Outlook account: mail, scheduled sends, contacts and calendar. Bare 'co outlook' shows the inbox (Read-only).",
    epilog="Example:  co outlook inbox --unread",
)
app.add_typer(outlook_app, name="outlook")


@outlook_app.callback(invoke_without_command=True)
def outlook_callback(ctx: typer.Context):
    """With no subcommand, show the Outlook inbox."""
    if ctx.invoked_subcommand is None:
        from .commands.outlook_commands import handle_outlook_inbox
        handle_outlook_inbox()


outlook_contact_app = _typer_app(
    help="Add, list, and search Outlook contacts. list and search are Read-only.",
    epilog="Example:  co outlook contact search sam",
    no_args_is_help=True,
)
outlook_app.add_typer(outlook_contact_app, name="contact", rich_help_panel="Contacts")

# Outlook is one product with three panes: Mail, Calendar, People. The
# calendar therefore lives here beside `contact`, not as a fourth top-level
# name an agent would have to guess (#816). Its leaves mirror `co gcalendar`.
from .commands.outlook_calendar_commands import outlook_calendar_app
outlook_app.add_typer(outlook_calendar_app, name="calendar", rich_help_panel="Calendar")


@outlook_contact_app.command("add", epilog="Example:  co outlook contact add \"Sam Lee\" sam@example.com")
def outlook_contact_add(
    name: str = typer.Argument(..., help="Contact display name"),
    email: str = typer.Argument(..., help="Contact email address"),
):
    """Save a contact with a name and email address. Creates it in your Outlook contacts."""
    from .commands.outlook_commands import handle_outlook_contact_add
    handle_outlook_contact_add(name, email)


@outlook_contact_app.command("list", epilog="Example:  co outlook contact list -n 50")
def outlook_contact_list(
    last: int = typer.Option(25, "--last", "-n", help="How many contacts to show"),
):
    """List saved Outlook contacts. Read-only."""
    from .commands.outlook_commands import handle_outlook_contact_list
    handle_outlook_contact_list(last=last)


@outlook_contact_app.command("search", epilog="Example:  co outlook contact search sam@example.com")
def outlook_contact_search(
    query: str = typer.Argument(..., help="Name or email substring"),
    last: int = typer.Option(25, "--last", "-n", help="How many matches to show"),
):
    """Search saved Outlook contacts by name or email. Read-only."""
    from .commands.outlook_commands import handle_outlook_contact_search
    handle_outlook_contact_search(query, last=last)


@outlook_app.command("send", rich_help_panel="Send", epilog="Examples:  co outlook send a@b.com \"Hi\" \"Quick note\"  |  "
                                    "cat body.txt | co outlook send a@b.com \"Report\" -  |  "
                                    "co outlook send a@b.com \"Invoice\" \"Attached\" --attach invoice.pdf --at +2h")
def outlook_send(
    to: str = typer.Argument(..., help="Recipient email address (comma-separated for multiple)"),
    subject: str = typer.Argument(..., help="Subject line"),
    message: str = typer.Argument(..., help="Body (plain text, or '-' to read from stdin)"),
    cc: Optional[str] = typer.Option(None, "--cc", help="CC recipients (comma-separated)"),
    bcc: Optional[str] = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a", help="File to attach (repeat for multiple)"),
    at: Optional[str] = typer.Option(None, "--at", help="Schedule delivery: +30m, +2h, or UTC ISO time (2026-07-06T15:30:00Z); cancel before it goes out with co outlook cancel <#>"),
):
    """Send an email from your Outlook account, now or scheduled with --at. Sends as you."""
    from .commands.outlook_commands import handle_outlook_send
    handle_outlook_send(to, subject, message, cc=cc, bcc=bcc, attachments=attach, at=at)


@outlook_app.command("inbox", rich_help_panel="Mail", epilog="Example:  co outlook inbox --unread -n 20")
def outlook_inbox(
    last: int = typer.Option(10, "--last", "-n", help="How many emails to show"),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread emails"),
    since: str = typer.Option(
        None, "--since", metavar="30d|2026-06-01",
        help="Everything in a window instead of the last -n. Nd/Nw/Nm/Ny or a date.",
    ),
    until: str = typer.Option(None, "--until", help="End of the window; defaults to now"),
    json_output: bool = typer.Option(
        False, "--json", help="One JSON array of the provider's own fields, for a caller to parse",
    ),
):
    """List recent emails in your Outlook inbox. Read-only."""
    from .commands.outlook_commands import handle_outlook_inbox
    handle_outlook_inbox(last=last, unread=unread, since=since, until=until,
                         json_output=json_output)


@outlook_app.command("read", rich_help_panel="Mail", epilog="Example:  co outlook read 3")
def outlook_read(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing (re-run to refresh numbers)"),
    mark_read: bool = typer.Option(False, "--mark-read", help="Mark the email as read after showing it"),
):
    """Show one email's body without changing its unread state. Read-only unless --mark-read."""
    from .commands.outlook_commands import handle_outlook_read
    handle_outlook_read(email_id, mark_read=mark_read)


@outlook_app.command("download", rich_help_panel="Mail", epilog="Example:  co outlook download 3 --to ./attachments")
def outlook_download(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing"),
    out_dir: str = typer.Option(".", "--to", help="Directory to save attachments into"),
    include_inline: bool = typer.Option(
        False, "--include-inline",
        help="Also save embedded signature images and logos (skipped by default)",
    ),
):
    """Save an email's attachments to disk. Writes files into --to (default: this directory)."""
    from .commands.outlook_commands import handle_outlook_download
    handle_outlook_download(email_id, out_dir, include_inline=include_inline)


@outlook_app.command("reply", rich_help_panel="Send", epilog="Examples:  co outlook reply 3 \"Sounds good\"  |  "
                                     "cat notes.txt | co outlook reply 3 -  |  "
                                     "co outlook reply 3 \"Looping in Sam\" --cc sam@example.com  |  "
                                     "co outlook reply 3 \"Signed copy attached\" --attach signed.pdf")
def outlook_reply(
    email_id: str = typer.Argument(..., help="Email # from your last inbox/search listing"),
    message: str = typer.Argument(..., help="Reply body (plain text, or '-' to read from stdin)"),
    cc: Optional[str] = typer.Option(None, "--cc", help="CC recipients (comma-separated); the reply stays in its thread"),
    bcc: Optional[str] = typer.Option(None, "--bcc", help="BCC recipients (comma-separated)"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a", help="File to attach (repeat for multiple)"),
    at: Optional[str] = typer.Option(None, "--at", help="Schedule delivery: +30m, +2h, or UTC ISO time (2026-07-06T15:30:00Z); cancel before it goes out with co outlook cancel <#>"),
):
    """Reply to an email (threaded), now or scheduled with --at. Sends from your Outlook account."""
    from .commands.outlook_commands import handle_outlook_reply
    handle_outlook_reply(email_id, message, attachments=attach, at=at, cc=cc, bcc=bcc)


@outlook_app.command("scheduled", rich_help_panel="Scheduled sends", epilog="Example:  co outlook scheduled")
def outlook_scheduled():
    """List emails waiting for scheduled delivery. Read-only."""
    from .commands.outlook_commands import handle_outlook_scheduled
    handle_outlook_scheduled()


@outlook_app.command("cancel", rich_help_panel="Scheduled sends", epilog="Example:  co outlook cancel 1")
def outlook_cancel(email_id: str = typer.Argument(..., help="Email # from 'co outlook scheduled' (or a full message ID)")):
    """Cancel a scheduled email before it goes out. Deletes the pending message, so it is never sent."""
    from .commands.outlook_commands import handle_outlook_cancel
    handle_outlook_cancel(email_id)


@outlook_app.command("sent", rich_help_panel="Mail", epilog="Example:  co outlook sent -n 20")
def outlook_sent(last: int = typer.Option(10, "--last", "-n", help="How many emails to show")):
    """List recently sent Outlook emails. Read-only."""
    from .commands.outlook_commands import handle_outlook_sent
    handle_outlook_sent(last=last)


@outlook_app.command("search", rich_help_panel="Mail", epilog="Example:  co outlook search \"from:sam@example.com invoice\"")
def outlook_search(
    query: str = typer.Argument(..., help="Search query: words match subject and body; "
                                        "from:<address>, to:<address> and participants:<address> "
                                        "narrow by who (measured to work on Graph $search)"),
    last: int = typer.Option(10, "--last", "-n", help="How many results to show"),
):
    """Search your Outlook emails. Read-only."""
    from .commands.outlook_commands import handle_outlook_search
    handle_outlook_search(query, last=last)


# Subscription command group. `co sub` (no args) syncs every subscription.
# `co sub sync <addr>` syncs one. `list` and `remove` are the secondary verbs.
sub_app = _typer_app(
    help="Install another person's published skills: co sub sync <0xaddress> once, then bare co sub "
         "refreshes every publisher you follow. Installs their skills into ~/.co/subs/ and your coding "
         "agents. Your own skills are co skills.",
    epilog="Example:  co sub sync 0xabc...",
)
app.add_typer(sub_app, name="sub")


@sub_app.callback(invoke_without_command=True)
def sub_callback(
    ctx: typer.Context,
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: configured backend)"),
):
    """Refresh every saved subscription; stop and report the first failure."""
    if ctx.invoked_subcommand is None:
        from .commands.sub_commands import handle_sub_sync_all
        handle_sub_sync_all(relay=relay)


@sub_app.command("sync", epilog="Example:  co sub sync 0xabc...  |  Next, to ship one of its skills with this project: co skills copy <name> --to-project")
def sub_sync(
    target: str = typer.Argument(..., help="0x address (or locally-pinned alias) to sync"),
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: configured backend)"),
):
    """Follow or refresh one publisher's public skills. Installs them into ~/.co/subs/ and your coding agents.

    First follow needs the full 0x address from the publisher. A local alias
    works only after that address is saved; see `co sub list` for saved aliases.
    Public subscriptions need no local signing key or publisher acceptance.

    The publisher's Ed25519 profile-v2 signature and monotonic revision are
    verified before anything is written. Unsigned, profile-v1, rolled-back, or
    equivocating profiles stay uninstalled. Skills land in ~/.co/subs/ and are
    fanned out to ~/.claude, ~/.codex, ~/.openclaw, ~/.cursor and ~/.kiro.

    A subscribed skill's `tools:` grant is removed on sync, so it cannot
    pre-authorise anything (#654). Its instructions are kept. Read mirrored
    and installed counts: zero installed skills means no agent restart is needed.
    """
    from .commands.sub_commands import handle_sub_sync_one
    handle_sub_sync_one(target, relay=relay)


@sub_app.command("list", epilog="Example:  co sub list")
def sub_list():
    """List locally pinned addresses and aliases; no relay calls. Read-only.

    The Skills column counts profile entries, including withheld bodies. Use
    the last sync's installed count to see what reached coding agents.
    """
    from .commands.sub_commands import handle_sub_list
    handle_sub_list()


@sub_app.command("remove", epilog="Example:  co sub remove 0xabc...")
def sub_remove(target: str = typer.Argument(..., help="Alias or 0x address to unsubscribe from")):
    """Unsubscribe locally. Removes its skills from ~/.co/subs/ and your coding agents; keeps the signed revision history."""
    from .commands.sub_commands import handle_sub_remove
    handle_sub_remove(target)


@app.command(epilog="Example:  co audit co  |  co audit co gmail --review  |  co audit yt-dlp  |  "
                    "co audit co --inventory > base.json  |  co audit co --since base.json --review")
def audit(
    command: List[str] = typer.Argument(..., help="The command to audit, as you would type it: co, co gmail, yt-dlp, gh pr"),
    review: bool = typer.Option(False, "--review", help="After the hard rules pass, have a model judge each page: clear, accurate, realistic example, simple. Calls a model"),
    since: Optional[Path] = typer.Option(None, "--since", help="Only commands added or changed since an inventory from co audit --inventory"),
    inventory: bool = typer.Option(False, "--inventory", help="Print each command's help fingerprint as JSON, for --since"),
    json_output: bool = typer.Option(False, "--json", help="Findings as JSON"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Model for --review; pin it so reruns compare like with like"),
):
    """Is a CLI fit for an agent harness? Runs its --help pages and scores them: usage, examples, documented flags, every subcommand reachable. Read-only; --review calls a model."""
    from .commands.audit_commands import handle_audit
    handle_audit(command, review, since, inventory, json_output, model)


from .typer_groups import name_the_way_back  # noqa: E402 — needs every command registered

name_the_way_back(app)


def cli():
    """Entry point."""
    from ..environment import EnvironmentError
    from ..credentials import AmbientCredentialError
    from ..provider_credentials import ProviderCredentialError
    try:
        app()
    except (EnvironmentError, AmbientCredentialError, ProviderCredentialError) as error:
        console.print(str(error), markup=False)
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
