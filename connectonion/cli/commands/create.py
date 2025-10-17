"""Create command for ConnectOnion CLI - handles 'co create'."""

import os
import signal
import sys
import shutil
import toml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from ... import __version__
from ... import address
from .auth_commands import authenticate

# Import shared functions from project_cmd_lib
from .project_cmd_lib import (
    Colors,
    LoadingAnimation,
    validate_project_name,
    check_environment_for_api_keys,
    api_key_setup_menu,
    detect_api_provider,
    get_template_info,
    interactive_menu,
    generate_custom_template_with_name,
    show_progress,
    configure_env_for_provider
)

console = Console()


def ensure_global_config() -> Dict[str, Any]:
    """Simple function to ensure ~/.co/ exists with global identity."""
    global_dir = Path.home() / ".co"
    config_path = global_dir / "config.toml"

    # If exists, just load and return
    if config_path.exists():
        with open(config_path, 'r') as f:
            return toml.load(f)

    # First time - create global config
    console.print(f"\n🚀 Welcome to ConnectOnion!")
    console.print(f"✨ Setting up global configuration...")

    # Create directories
    global_dir.mkdir(exist_ok=True)
    (global_dir / "keys").mkdir(exist_ok=True)
    (global_dir / "logs").mkdir(exist_ok=True)

    # Generate master keys - fail fast if libraries missing
    addr_data = address.generate()
    address.save(addr_data, global_dir)
    console.print(f"  ✓ Generated master keypair")
    console.print(f"  ✓ Your address: {addr_data['short_address']}")

    # Create config
    config = {
        "connectonion": {
            "framework_version": __version__,
            "created": datetime.now().isoformat(),
        },
        "cli": {
            "version": "1.0.0",
        },
        "agent": {
            "address": addr_data["address"],
            "short_address": addr_data["short_address"],
            "email": addr_data.get("email", f"{addr_data['address'][:10]}@mail.openonion.ai"),
            "email_active": False,
            "created_at": datetime.now().isoformat(),
            "algorithm": "ed25519",
            "default_model": "gpt-4o-mini",
            "max_iterations": 10,
        },
    }

    # Save config
    with open(config_path, 'w') as f:
        toml.dump(config, f)
    console.print(f"  ✓ Created ~/.co/config.toml")

    # Create empty keys.env
    keys_env = global_dir / "keys.env"
    if not keys_env.exists():
        keys_env.touch()
        os.chmod(keys_env, 0o600)
    console.print(f"  ✓ Created ~/.co/keys.env (add your API keys here)")

    return config


def handle_create(name: Optional[str], ai: Optional[bool], key: Optional[str],
                  template: Optional[str], description: Optional[str], yes: bool):
    """Create a new ConnectOnion project in a new directory."""
    # Ensure global config exists first
    global_config = ensure_global_config()
    global_identity = global_config.get("agent", {})

    # Track temp directory for cleanup
    temp_project_dir = None

    def cleanup_on_exit(signum=None, frame=None):
        """Clean up temp directory on exit."""
        if temp_project_dir and temp_project_dir.exists():
            try:
                if Confirm.ask(f"\n{Colors.YELLOW}Remove temporary project directory '{temp_project_dir}'?{Colors.END}", default=True):
                    import shutil
                    shutil.rmtree(temp_project_dir)
                    console.print(f"{Colors.GREEN}✓ Temporary directory removed.{Colors.END}")
            except Exception:
                pass
        sys.exit(0)

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, cleanup_on_exit)

    # Header removed for cleaner output

    # Template selection - default to minimal unless --template provided
    if not template:
        template = 'minimal'
    # Silent - no verbose messages

    # ALL templates need AI to function (agents need LLMs!)
    provider = None
    api_key = key
    ai = True  # Always true - all agents need AI

    # Check for environment API keys first
    if not api_key and not yes:
        env_api = check_environment_for_api_keys()
        if env_api:
            provider, env_key = env_api
            console.print(f"\n{Colors.GREEN}✓ Found {provider.title()} API key in environment{Colors.END}")
            if not api_key:
                api_key = env_key

    # Check global keys.env first
    global_dir = Path.home() / ".co"
    global_keys_env = global_dir / "keys.env"

    # Try to load existing keys from global config
    if global_keys_env.exists() and not api_key:
        with open(global_keys_env, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    env_key, env_value = line.split('=', 1)
                    if env_key == "OPENAI_API_KEY" and env_value.strip():
                        api_key = env_value.strip()
                        provider = "openai"
                        console.print(f"\n{Colors.GREEN}✓ Found OpenAI API key in ~/.co/keys.env{Colors.END}")
                        break

    # API key setup (temp_project_dir already declared above for signal handler)
    if ai and not api_key and not yes:
        api_key, provider, temp_project_dir = api_key_setup_menu()
        if api_key == "skip":
            # User chose to skip
            api_key = None
            ai = False  # Disable AI features since no API key
        elif not api_key and not provider:
            # User cancelled (Ctrl+C or similar)
            console.print(f"{Colors.YELLOW}API key setup cancelled.{Colors.END}")
            return
    elif ai and api_key:
        provider, key_type = detect_api_provider(api_key)

    # Save API key to global config if provided
    if api_key and api_key != "skip" and provider:
        # Map provider to env variable name
        provider_to_env = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
        }
        env_var = provider_to_env.get(provider, f"{provider.upper()}_API_KEY")

        # Check if key already exists in global config
        key_exists = False
        if global_keys_env.exists():
            with open(global_keys_env, 'r') as f:
                content = f.read()
                if f"{env_var}=" in content:
                    key_exists = True

        # Save to global keys.env if not exists
        if not key_exists:
            with open(global_keys_env, 'a') as f:
                if global_keys_env.stat().st_size > 0:
                    f.write('\n')
                f.write(f"{env_var}={api_key}\n")
            console.print(f"{Colors.GREEN}✓ Saved to ~/.co/keys.env for future projects{Colors.END}")

    # Handle custom template
    custom_code = None
    ai_suggested_name = None
    if template == 'custom':
        # Custom template requires AI
        if not ai or not api_key:
            console.print(f"{Colors.RED}❌ Custom template requires an API key for AI generation{Colors.END}")
            console.print(f"{Colors.YELLOW}Please run 'co create' again and provide an API key{Colors.END}")
            return
        if not description and not yes:
            console.print(f"\n{Colors.CYAN}🤖 Describe your agent:{Colors.END}")
            description = Prompt.ask("  What should your agent do?")
        elif not description:
            description = "A general purpose agent"

        # Use loading animation for AI generation
        console.print(f"\n{Colors.CYAN}🤖 AI is generating your custom agent...{Colors.END}")

        with LoadingAnimation("Preparing AI generation...") as loading:
            # Use ConnectOnion model if available (user just got 100k tokens!)
            if provider == "connectonion" and temp_project_dir:
                # Load the JWT token from the temp project
                config_path = temp_project_dir / ".co" / "config.toml"
                jwt_token = None
                if config_path.exists():
                    config = toml.load(config_path)
                    jwt_token = config.get("auth", {}).get("token")

                model_to_use = "co/gpt-4o-mini"
                loading.update(f"Using {model_to_use} to analyze: {description[:40]}...")

                # Pass JWT token as api_key for co/ models
                custom_code, ai_suggested_name = generate_custom_template_with_name(
                    description, jwt_token, model=model_to_use, loading_animation=loading
                )
            else:
                # Use user's API key and model
                loading.update(f"Analyzing: {description[:40]}...")
                custom_code, ai_suggested_name = generate_custom_template_with_name(
                    description, api_key or "", model=None, loading_animation=loading
                )

        console.print(f"{Colors.GREEN}✓ Generated custom agent code{Colors.END}")
        console.print(f"{Colors.GREEN}✓ Suggested project name: {ai_suggested_name}{Colors.END}")

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
                        name = Prompt.ask(f"{Colors.CYAN}Project name{Colors.END}")
                    else:
                        name = result

                    console.print(f"{Colors.GREEN}✓ Project name:{Colors.END} {name}")

                except ImportError:
                    # Fallback to numbered menu
                    console.print(f"\n{Colors.CYAN}Choose a project name:{Colors.END}")
                    console.print(f"  1. {Colors.GREEN}{ai_suggested_name}{Colors.END} (AI suggested)")
                    console.print(f"  2. Type your own")

                    choice = IntPrompt.ask("Select [1-2]", choices=["1", "2"], default="1")

                    if choice == 1:
                        name = ai_suggested_name
                    else:
                        name = Prompt.ask(f"{Colors.CYAN}Project name{Colors.END}")
            else:
                # No AI suggestion, ask for name
                name = Prompt.ask(f"\n{Colors.CYAN}Project name{Colors.END}", default="custom-agent")
        else:
            # For non-custom templates, use template name directly
            name = f"{template}-agent"

        # Validate project name
        is_valid, error_msg = validate_project_name(name)
        while not is_valid:
            console.print(f"{Colors.RED}❌ {error_msg}{Colors.END}")
            name = Prompt.ask(f"{Colors.CYAN}Project name{Colors.END}", default="my-agent")
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
            console.print(f"{Colors.RED}❌ {error_msg}{Colors.END}")
            return

    # Handle temp directory or create new project directory
    project_dir = Path(name)

    # Check if directory exists and suggest alternative
    if project_dir.exists():
        base_name = name
        counter = 2
        suggested_name = f"{base_name}-{counter}"
        while Path(suggested_name).exists():
            counter += 1
            suggested_name = f"{base_name}-{counter}"

        # Show error with suggestion
        console.print(f"\n[red]❌ '{base_name}' exists. Try: [bold]co create {suggested_name}[/bold][/red]\n")
        return

    if temp_project_dir:
        # Rename temp directory to final project name
        temp_project_dir.rename(project_dir)
    else:
        # Create project directory
        project_dir.mkdir(parents=True, exist_ok=True)

    # Get template files
    cli_dir = Path(__file__).parent.parent
    template_dir = cli_dir / "templates" / template

    if not template_dir.exists() and template != 'custom':
        console.print(f"{Colors.RED}❌ Template '{template}' not found!{Colors.END}")
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
        agent_file.write_text(custom_code)
        files_created.append("agent.py")

    # Create .co directory (skip if it already exists from temp project)
    co_dir = project_dir / ".co"
    if not co_dir.exists():
        co_dir.mkdir(exist_ok=True)

    # Create docs directory
    docs_dir = co_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Copy ConnectOnion documentation from single master source
    cli_dir = Path(__file__).parent.parent

    # Copy the main vibe-coding documentation - keep original filename
    master_vibe_doc = cli_dir / "docs" / "co-vibecoding-principles-docs-contexts-all-in-one.md"
    if master_vibe_doc.exists():
        # Copy to .co/docs/ (project metadata)
        shutil.copy2(master_vibe_doc, docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md")
        files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")

        # ALSO copy to project root (always visible, easier to find)
        root_doc = project_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md"
        shutil.copy2(master_vibe_doc, root_doc)
        files_created.append("co-vibecoding-principles-docs-contexts-all-in-one.md")
    else:
        console.print(f"[yellow]⚠️  Warning: Vibe coding documentation not found at {master_vibe_doc}[/yellow]")

    # Use global identity instead of generating project keys
    # NO PROJECT KEYS - we use global address/email
    addr_data = global_identity  # Use the global identity we loaded earlier

    # Note: We're NOT creating project-specific keys anymore
    # If user wants project-specific keys, they'll use 'co address' command

    # Create config.toml
    config = {
        "project": {
            "name": name,
            "created": datetime.now().isoformat(),
            "framework_version": __version__,
        },
        "cli": {
            "version": "1.0.0",
            "command": f"co create {name}",
            "template": template,
        },
        "agent": {
            "address": addr_data["address"],
            "short_address": addr_data["short_address"],
            "email": addr_data.get("email", f"{addr_data['address'][:10]}@mail.openonion.ai"),
            "email_active": addr_data.get("email_active", False),
            "created_at": datetime.now().isoformat(),
            "algorithm": "ed25519",
            "default_model": "gpt-4o-mini" if provider == 'openai' else "gpt-4o-mini",
            "max_iterations": 10,
        },
    }

    config_path = co_dir / "config.toml"
    with open(config_path, "w") as f:
        toml.dump(config, f)
    files_created.append(".co/config.toml")

    # Create .env file - copy from global keys.env
    env_path = project_dir / ".env"
    env_has_keys = False

    # Try to copy from global keys.env first
    if global_keys_env.exists() and global_keys_env.stat().st_size > 0:
        # Copy global keys to project
        with open(global_keys_env, 'r') as f:
            env_content = f.read()
        console.print(f"{Colors.GREEN}✓ Copied API keys from ~/.co/keys.env{Colors.END}")
        env_has_keys = True
    elif api_key and provider:
        # Use the key just provided
        env_content = configure_env_for_provider(provider, api_key)
        env_has_keys = True
    else:
        # Default comments-only template (no fake keys)
        env_content = """# Add your LLM API key(s) below (uncomment one and set value)
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
# GROQ_API_KEY=

# Optional: Override default model
# MODEL=gpt-4o-mini
"""

    env_path.write_text(env_content)
    files_created.append(".env")

    # Create .gitignore if in git repo
    if (project_dir / ".git").exists() or (Path.cwd() / ".git").exists():
        gitignore_path = project_dir / ".gitignore"
        gitignore_content = """
# ConnectOnion
.env
.co/keys/
.co/cache/
.co/logs/
.co/history/
*.py[cod]
__pycache__/
todo.md
"""
        gitignore_path.write_text(gitignore_content.lstrip())
        files_created.append(".gitignore")

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
    console.print(f"   [cyan]co-vibecoding-principles-docs-contexts-all-in-one.md[/cyan]")
    console.print()

    # Resources - clean format with arrows for better alignment
    console.print("[bold cyan]📚 Resources:[/bold cyan]")
    console.print(f"   Docs    [dim]→[/dim] [link=https://docs.connectonion.com][blue]https://docs.connectonion.com[/blue][/link]")
    console.print(f"   Discord [dim]→[/dim] [link=https://discord.gg/4xfD9k8AUF][blue]https://discord.gg/4xfD9k8AUF[/blue][/link]")
    console.print(f"   GitHub  [dim]→[/dim] [link=https://github.com/openonion/connectonion][blue]https://github.com/openonion/connectonion[/blue][/link] [dim](⭐ star us!)[/dim]")
    console.print()
