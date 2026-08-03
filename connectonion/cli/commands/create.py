"""
Purpose: Create new ConnectOnion project in new directory with template files, authentication, and configuration
LLM-Note:
  Dependencies: imports from [os, signal, sys, shutil, yaml, datetime, pathlib, rich.console, rich.prompt, rich.panel, __version__, address, auth_commands.authenticate, project_cmd_lib] | imported by [cli/main.py via handle_create()] | uses templates from [cli/templates/co-ai] | tested by [tests/e2e/cli/test_cli_create.py]
  Data flow: receives args (name, ai, key, template, description, yes) from CLI parser → validate_project_name() checks name validity → ensure_global_config() creates ~/.co/ with master keypair if needed → check_environment_for_api_keys() detects existing keys → interactive_menu() or api_key_setup_menu() gets user choices → generate_custom_template_with_name() if template='custom' → create new directory with project name → copy template files from cli/templates/{template}/ to new dir → authenticate() to get OPENONION_API_KEY → create .env with API keys → create .co/host.yaml with project metadata and global identity → copy vibe coding docs → create .gitignore → display success message with next steps
  State/Effects: modifies ~/.co/ (host.yaml, keys.env, keys/, logs/) on first run | creates new directory {name}/ in current dir | writes to {name}/: .co/host.yaml, .env, agent.py (if template), .gitignore | calls authenticate() which writes OPENONION_API_KEY to ~/.co/keys.env | copies template files | writes to stdout via rich.Console
  Integration: exposes handle_create(name, ai, key, template, description, yes) | similar to init.py but creates new directory first | calls ensure_global_config() for global identity | calls authenticate(global_co_dir, save_to_project=False) for managed keys | uses template files from cli/templates/ | relies on project_cmd_lib for shared functions | uses address.generate() for Ed25519 keypair | template options: 'co-ai' (default), 'custom'
  Performance: authenticate() makes network call (2-5s) | generate_custom_template_with_name() calls LLM API if template='custom' | directory creation is O(1) | template file copying is O(n) files
  Errors: fails if project name invalid (spaces, special chars) | fails if directory already exists | fails if cli/templates/{template}/ not found | fails if API key invalid during authenticate() | catches KeyboardInterrupt during interactive menus (cleans up partial state)
"""

import os
import shutil
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.syntax import Syntax

from .auth_commands import authenticate

# Import shared functions from project_cmd_lib
from .project_cmd_lib import (
    PROVIDER_TO_ENV,
    mint_invite_code,
    ensure_global_config,
    copy_docs,
    create_host_yaml,
    setup_gitignore,
    print_resources,
    LoadingAnimation,
    validate_project_name,
    check_environment_for_api_keys,
    detect_api_provider,
    generate_custom_template_with_name,
    get_template_suggested_name,
    unknown_template_message,
)

console = Console()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def copy_template_files(template: str, project_dir: Path, files_created: list) -> None:
    """Copy one template into a new project, source only.

    `pip install` byte-compiles every .py in the wheel, and the template's
    agent.py is a .py under the package even though nothing imports it — so an
    installed copy carries
    `templates/co-ai/__pycache__/agent.cpython-3xx.pyc`, compiled by whichever
    interpreter did the installing. Copying the directory as found handed that
    to every new project: a `__pycache__` for code the user has not run yet.

    Nothing breaks — a mismatched magic number is ignored, and .gitignore covers
    the directory — but the first thing someone sees in their first project
    should not need explaining.
    """
    for item in template_dir_for(template).iterdir():
        if item.name.startswith('.') and item.name != '.env.example':
            continue
        if item.name == '.env.example':
            continue
        # The installer's leftovers, at this level and every level below.
        if item.name == '__pycache__' or item.suffix in ('.pyc', '.pyo'):
            continue

        dest_path = project_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest_path,
                            ignore=shutil.ignore_patterns('__pycache__', '*.py[cod]'))
            files_created.append(f"{item.name}/")
        else:
            shutil.copy2(item, dest_path)
            files_created.append(item.name)


def template_dir_for(template: str) -> Path:
    """Where a template lives. Read through TEMPLATES_DIR so a test can move it."""
    return TEMPLATES_DIR / template


def handle_create(name: Optional[str], ai: Optional[bool], key: Optional[str],
                  template: Optional[str], description: Optional[str], yes: bool,
                  parent_dir: Optional[Path] = None):
    """Create a new ConnectOnion project in a new directory."""
    # Ensure global config exists first
    ensure_global_config()

    # Header removed for cleaner output

    # One template: co-ai. `custom` still generates an agent.py from a description.
    if not template:
        template = 'co-ai'

    # Check the name here, not after the work. This used to be validated only
    # once we had already authenticated over the network and created the project
    # directory, so a typo — or a script still passing a retired template — paid
    # for a round trip and a mkdir/rmtree before being told the name was wrong.
    if template != 'custom' and not (TEMPLATES_DIR / template).exists():
        console.print(unknown_template_message(template))
        raise typer.Exit(1)

    # Auto-detect API keys from environment (no menu, just detect)
    detected_keys = {}
    provider = None

    # Check for API keys in environment
    env_api = check_environment_for_api_keys()
    if env_api:
        provider, env_key = env_api
        detected_keys[provider] = env_key
        if not yes:
            console.print(f"[green]✓ Detected {provider.title()} API key[/green]")

    # If --key provided via flag, use it
    if key:
        provider, key_type = detect_api_provider(key)
        detected_keys[provider] = key

    # Authenticate only if OPENONION_API_KEY not already in global keys.env
    global_dir = Path.home() / ".co"
    global_keys_env = global_dir / "keys.env"
    already_authed = global_keys_env.exists() and "OPENONION_API_KEY=" in global_keys_env.read_text(encoding="utf-8")

    if not already_authed:
        if not yes:
            console.print("\n[cyan]🔐 Authenticating with OpenOnion for managed keys...[/cyan]")
        success = authenticate(global_dir, save_to_project=False)
        if not success and not yes:
            console.print("[yellow]⚠️  Authentication failed - you can still use your own API keys[/yellow]")

    # Check global keys.env for API keys
    if global_keys_env.exists():
        with open(global_keys_env, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    env_key_name, env_value = line.split('=', 1)
                    # Detect provider from key name
                    if env_key_name == "OPENAI_API_KEY" and env_value.strip():
                        detected_keys["openai"] = env_value.strip()
                    elif env_key_name == "ANTHROPIC_API_KEY" and env_value.strip():
                        detected_keys["anthropic"] = env_value.strip()
                    elif env_key_name == "GEMINI_API_KEY" and env_value.strip():
                        detected_keys["google"] = env_value.strip()
                    elif env_key_name == "GROQ_API_KEY" and env_value.strip():
                        detected_keys["groq"] = env_value.strip()
                    elif env_key_name == "XAI_API_KEY" and env_value.strip():
                        detected_keys["grok"] = env_value.strip()
                    elif env_key_name == "OPENROUTER_API_KEY" and env_value.strip():
                        detected_keys["openrouter"] = env_value.strip()
                    elif env_key_name == "OPENONION_API_KEY" and env_value.strip():
                        detected_keys["openonion"] = env_value.strip()

    # Use first detected key for template generation if needed
    if detected_keys and not provider:
        provider = list(detected_keys.keys())[0]

    # For custom template generation, we need an API key
    template_key = ""
    if template == 'custom':
        if detected_keys:
            # Prefer OpenAI for custom generation, fallback to first available
            if "openai" in detected_keys:
                template_key = detected_keys["openai"]
                provider = "openai"
            else:
                template_key = list(detected_keys.values())[0]
                provider = list(detected_keys.keys())[0]

    # Handle custom template
    custom_code = None
    ai_suggested_name = None
    if template == 'custom':
        # Custom template requires AI
        if not template_key:
            console.print("[red]❌ Custom template requires an API key for AI generation[/red]")
            console.print("[yellow]Please run 'co create' again and provide an API key[/yellow]")
            return
        if not description and not yes:
            console.print("\n[cyan]🤖 Describe your agent:[/cyan]")
            description = Prompt.ask("  What should your agent do?")
        elif not description:
            description = "A general purpose agent"

        # Use loading animation for AI generation
        console.print("\n[cyan]🤖 AI is generating your custom agent...[/cyan]")

        with LoadingAnimation("Preparing AI generation...") as loading:
            # Use detected API key for generation
            loading.update(f"Analyzing: {description[:40]}...")
            custom_code, ai_suggested_name = generate_custom_template_with_name(
                description, template_key, model=None, loading_animation=loading
            )

        console.print("[green]✓ Generated custom agent code[/green]")
        console.print(f"[green]✓ Suggested project name: {ai_suggested_name}[/green]")

    # Get project name
    if not name and not yes:
        if template == 'custom':
            # For custom template, ask for project name using AI suggestion
            if ai_suggested_name:
                # Use arrow key navigation for name selection
                try:
                    import questionary
                    from questionary import Style

                    custom_style = Style([
                        ('question', 'fg:#00ffff bold'),
                        ('pointer', 'fg:#00ff00 bold'),
                        ('highlighted', 'fg:#00ff00 bold'),
                        ('selected', 'fg:#00ffff'),
                    ])

                    choices = [
                        questionary.Choice(
                            title=f"🤖 {ai_suggested_name} (AI suggested)",
                            value=ai_suggested_name
                        ),
                        questionary.Choice(
                            title="✏️  Type your own name",
                            value="custom"
                        )
                    ]

                    result = questionary.select(
                        "\nChoose a project name:",
                        choices=choices,
                        style=custom_style,
                        instruction="(Use ↑/↓ arrows, press Enter to confirm)",
                        default=choices[0]  # Default to AI suggestion
                    ).ask()

                    if result == "custom":
                        name = Prompt.ask("[cyan]Project name[/cyan]")
                    else:
                        name = result

                    console.print(f"[green]✓ Project name:[/green] {name}")

                except ImportError:
                    # Fallback to numbered menu
                    console.print("\n[cyan]Choose a project name:[/cyan]")
                    console.print(f"  1. [green]{ai_suggested_name}[/green] (AI suggested)")
                    console.print("  2. Type your own")

                    choice = IntPrompt.ask("Select [1-2]", choices=["1", "2"], default="1")

                    if choice == 1:
                        name = ai_suggested_name
                    else:
                        name = Prompt.ask("[cyan]Project name[/cyan]")
            else:
                # No AI suggestion, ask for name
                name = Prompt.ask("\n[cyan]Project name[/cyan]", default="custom-agent")
        else:
            # One template, so its name says nothing useful about the project.
            name = get_template_suggested_name(template)

        # Validate project name
        is_valid, error_msg = validate_project_name(name)
        while not is_valid:
            console.print(f"[red]❌ {error_msg}[/red]")
            name = Prompt.ask("[cyan]Project name[/cyan]", default="my-agent")
            is_valid, error_msg = validate_project_name(name)
    elif not name:
        # Auto mode - suggested name for the template, AI suggestion for custom
        if template != 'custom':
            name = get_template_suggested_name(template)
        elif ai_suggested_name:
            # Use AI-suggested name for custom template
            name = ai_suggested_name
        else:
            name = "my-agent"
    else:
        # Validate provided name
        is_valid, error_msg = validate_project_name(name)
        if not is_valid:
            console.print(f"[red]❌ {error_msg}[/red]")
            return

    # Create new project directory. CLI calls use cwd; template deploy can pass
    # a temporary parent without changing the process-wide working directory.
    base_dir = Path.cwd() if parent_dir is None else parent_dir
    project_dir = base_dir / name

    # Check if directory exists and suggest alternative
    if project_dir.exists():
        base_name = name
        counter = 2
        suggested_name = f"{base_name}-{counter}"
        while (base_dir / suggested_name).exists():
            counter += 1
            suggested_name = f"{base_name}-{counter}"

        # Show error with suggestion
        console.print(f"\n[red]❌ '{base_name}' exists. Try: [bold]co create {suggested_name}[/bold][/red]\n")
        return

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Get template files. The name was validated before any network or
    # filesystem work; this stays as a guard for a template deleted mid-run.
    template_dir = TEMPLATES_DIR / template

    if not template_dir.exists() and template != 'custom':
        console.print(unknown_template_message(template))
        shutil.rmtree(project_dir)
        raise typer.Exit(1)

    # Copy template files
    files_created = []

    if template != 'custom' and template_dir.exists():
        copy_template_files(template, project_dir, files_created)

    # Create custom agent.py if custom template
    if custom_code:
        agent_file = project_dir / "agent.py"
        agent_file.write_text(custom_code, encoding='utf-8')
        files_created.append("agent.py")

    # Create .co directory (skip if it already exists from temp project)
    co_dir = project_dir / ".co"
    if not co_dir.exists():
        co_dir.mkdir(exist_ok=True)

    # Copy documentation to .co/docs/
    if copy_docs(co_dir):
        files_created.append(".co/docs/ (full documentation)")

    # Create host.yaml from template (unified config for host() and co deploy)
    if create_host_yaml(co_dir, name):
        files_created.append(".co/host.yaml")

    # Create .env file - copy from global keys.env
    env_path = project_dir / ".env"

    # Always copy from global keys.env (includes AGENT_ADDRESS, AGENT_EMAIL, and API keys)
    if global_keys_env.exists() and global_keys_env.stat().st_size > 0:
        # Copy global keys to project
        from .env_inheritance import (
            describes_this_machine,
            is_personal_account_credential,
        )

        def inherited(line: str) -> bool:
            key = line.strip().split('=', 1)[0]
            return not (is_personal_account_credential(key) or describes_this_machine(key))

        with open(global_keys_env, 'r', encoding='utf-8') as f:
            env_content = "".join(line for line in f if inherited(line))

        # AGENT_CONFIG_PATH is deliberately not written here. Every tool that
        # reads it already falls back to ~/.co on the machine it is running on
        # (gmail.py, outlook.py, gdrive.py, synology.py and both calendars all
        # spell the same default), so writing it buys nothing — and it is an
        # absolute path in a file that gets copied. Deployed, cloned or handed to
        # a colleague, it names a home directory that does not exist there, and
        # every one of those tools then looks for keys.env somewhere it can never
        # be. `co deploy --to` still sets it in the unit's environment, where it
        # describes the machine it is on rather than the one that made the file.
        lines_to_add = []
        if "# Default model:" not in env_content:
            lines_to_add.append("# Default model: co/gemini-3.6-flash (managed keys with free credits)\n")

        if lines_to_add:
            # Add blank line after comments if we're adding any
            lines_to_add.append("\n")
            env_content = "".join(lines_to_add) + env_content
    else:
        # Fallback - create minimal .env with detected keys
        env_lines = [
            "# Default model: co/gemini-3.6-flash (managed keys with free credits)",
            "",
        ]

        # Add detected API keys
        for prov, key_value in detected_keys.items():
            env_var = PROVIDER_TO_ENV.get(prov, f"{prov.upper()}_API_KEY")
            env_lines.append(f"{env_var}={key_value}")

        if len(env_lines) == 3:  # Only header, no keys added
            # No keys at all - create template
            env_lines.extend([
                "# Add your LLM API key(s) below",
                "# OPENAI_API_KEY=",
                "# ANTHROPIC_API_KEY=",
                "# GEMINI_API_KEY=",
                "# XAI_API_KEY=",
                "# OPENROUTER_API_KEY=",
            ])

        env_content = "\n".join(env_lines) + "\n"

    # The agent's own way in. Without it the host starts up saying "no one can
    # onboard" and points at `co init` — a different command, for a directory
    # that is already a project. Minted only when absent: regenerating would
    # lock out everyone holding the old one.
    if "CO_INVITE_CODE" not in env_content:
        if env_content and not env_content.endswith("\n"):
            env_content += "\n"
        env_content += f"CO_INVITE_CODE={mint_invite_code()}\n"

    env_path.write_text(env_content, encoding='utf-8')
    files_created.append(".env")

    # Show where the .env file was saved
    if not yes:
        console.print(f"[green]✓ Saved to {env_path}[/green]")

    # Create .gitignore if in git repo
    gi_result = setup_gitignore(project_dir)
    if gi_result:
        files_created.append(gi_result)

    # Success message with Rich formatting
    console.print()
    console.print(f"[bold green]✅ Created {name}[/bold green]")
    console.print()

    # Command with syntax highlighting - compact design
    command = f"cd {name} && python agent.py"
    syntax = Syntax(
        command,
        "bash",
        theme="monokai",
        background_color="#272822",  # Monokai background color
        padding=(0, 1)  # Minimal padding for tight fit
    )
    console.print(syntax)
    console.print()

    # Vibe Coding hint - clean formatting with proper spacing
    console.print("[bold yellow]💡 Vibe Coding:[/bold yellow] Use Claude/Cursor/Codex with")
    console.print(f"   [cyan].co/docs/[/cyan] for full documentation")
    console.print()

    # Resources
    print_resources()
