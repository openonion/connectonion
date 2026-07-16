"""
Purpose: Create new ConnectOnion project in new directory with template files, authentication, and configuration
LLM-Note:
  Dependencies: imports from [os, signal, sys, shutil, yaml, datetime, pathlib, rich.console, rich.prompt, rich.panel, __version__, address, auth_commands.authenticate, project_cmd_lib] | imported by [cli/main.py via handle_create()] | uses templates from [cli/templates/{minimal,browser,hosted-browser,coder,co-ai,web-research}] | tested by [tests/e2e/cli/test_cli_create.py]
  Data flow: receives args (name, ai, key, template, description, yes) from CLI parser → validate_project_name() checks name validity → ensure_global_config() creates ~/.co/ with master keypair if needed → check_environment_for_api_keys() detects existing keys → interactive_menu() or api_key_setup_menu() gets user choices → generate_custom_template_with_name() if template='custom' → create new directory with project name → copy template files from cli/templates/{template}/ to new dir → authenticate() to get OPENONION_API_KEY → create .env with API keys → create .co/host.yaml with project metadata and global identity → copy vibe coding docs → create .gitignore → display success message with next steps
  State/Effects: modifies ~/.co/ (host.yaml, keys.env, keys/, logs/) on first run | creates new directory {name}/ in current dir | writes to {name}/: .co/host.yaml, .env, agent.py (if template), .gitignore | calls authenticate() which writes OPENONION_API_KEY to ~/.co/keys.env | copies template files | writes to stdout via rich.Console
  Integration: exposes handle_create(name, ai, key, template, description, yes) | similar to init.py but creates new directory first | calls ensure_global_config() for global identity | calls authenticate(global_co_dir, save_to_project=False) for managed keys | uses template files from cli/templates/ | relies on project_cmd_lib for shared functions | uses address.generate() for Ed25519 keypair | template options: 'minimal' (default), 'browser', 'hosted-browser', 'coder', 'co-ai', 'web-research', 'custom'
  Performance: authenticate() makes network call (2-5s) | generate_custom_template_with_name() calls LLM API if template='custom' | directory creation is O(1) | template file copying is O(n) files
  Errors: fails if project name invalid (spaces, special chars) | fails if directory already exists | fails if cli/templates/{template}/ not found | fails if API key invalid during authenticate() | catches KeyboardInterrupt during interactive menus (cleans up partial state)
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.syntax import Syntax

from .auth_commands import authenticate

# Import shared functions from project_cmd_lib
from .project_cmd_lib import (
    PROVIDER_TO_ENV,
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
)

console = Console()


def handle_create(name: Optional[str], ai: Optional[bool], key: Optional[str],
                  template: Optional[str], description: Optional[str], yes: bool,
                  parent_dir: Optional[Path] = None):
    """Create a new ConnectOnion project in a new directory."""
    # Ensure global config exists first
    ensure_global_config()

    # Header removed for cleaner output

    # Template selection - default to minimal unless --template provided
    if not template:
        template = 'minimal'
    # Silent - no verbose messages

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
    already_authed = global_keys_env.exists() and "OPENONION_API_KEY=" in global_keys_env.read_text()

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
            # For non-custom templates, use template name directly
            name = f"{template}-agent"

        # Validate project name
        is_valid, error_msg = validate_project_name(name)
        while not is_valid:
            console.print(f"[red]❌ {error_msg}[/red]")
            name = Prompt.ask("[cyan]Project name[/cyan]", default="my-agent")
            is_valid, error_msg = validate_project_name(name)
    elif not name:
        # Auto mode - use template name for non-custom, AI suggestion for custom
        if template != 'custom':
            name = f"{template}-agent"
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

    # Get template files
    cli_dir = Path(__file__).parent.parent
    template_dir = cli_dir / "templates" / template

    if not template_dir.exists() and template != 'custom':
        console.print(f"[red]❌ Template '{template}' not found![/red]")
        shutil.rmtree(project_dir)
        return

    # Copy template files
    files_created = []

    if template != 'custom' and template_dir.exists():
        for item in template_dir.iterdir():
            if item.name.startswith('.') and item.name != '.env.example':
                continue

            dest_path = project_dir / item.name

            if item.is_dir():
                shutil.copytree(item, dest_path)
                files_created.append(f"{item.name}/")
            else:
                if item.name != '.env.example':
                    shutil.copy2(item, dest_path)
                    files_created.append(item.name)

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
        with open(global_keys_env, 'r', encoding='utf-8') as f:
            env_content = f.read()

        # Add config path and default model comment if not already present
        lines_to_add = []
        if "AGENT_CONFIG_PATH=" not in env_content:
            lines_to_add.append(f"AGENT_CONFIG_PATH={Path.home() / '.co'}\n")
        if "# Default model:" not in env_content:
            lines_to_add.append("# Default model: co/gemini-3.5-flash (managed keys with free credits)\n")

        if lines_to_add:
            # Add blank line after comments if we're adding any
            lines_to_add.append("\n")
            env_content = "".join(lines_to_add) + env_content
    else:
        # Fallback - create minimal .env with detected keys
        env_lines = [
            f"AGENT_CONFIG_PATH={Path.home() / '.co'}",
            "# Default model: co/gemini-3.5-flash (managed keys with free credits)",
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
