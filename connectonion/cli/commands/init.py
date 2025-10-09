"""Initialize command for ConnectOnion CLI - handles 'co init'."""

import os
import shutil
import subprocess
import toml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.prompt import Prompt, Confirm

from ... import __version__
from ... import address
from .auth_commands import authenticate

# Import shared functions from project_cmd_lib
from .project_cmd_lib import (
    Colors,
    get_special_directory_warning,
    is_directory_empty,
    check_environment_for_api_keys,
    api_key_setup_menu,
    detect_api_provider,
    get_template_info,
    interactive_menu,
    generate_custom_template,
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


def handle_init(ai: Optional[bool], key: Optional[str], template: Optional[str],
                description: Optional[str], yes: bool, force: bool):
    """Initialize a ConnectOnion project in the current directory."""
    # Ensure global config exists first
    global_config = ensure_global_config()
    global_identity = global_config.get("agent", {})

    current_dir = os.getcwd()
    project_name = os.path.basename(current_dir) or "my-agent"

    # Track temp directory for cleanup
    temp_project_dir = None

    # Header with color
    if not yes:
        console.print("\n[bold cyan]🧅 ConnectOnion Project Initializer[/bold cyan]")
        console.print("[cyan]" + "=" * 40 + "[/cyan]")
        console.print(f"\n📁 Initializing: [bold]{project_name}[/bold]")
        console.print(f"📍 Location: [bold]{current_dir}[/bold]\n")

    # Check for special directories
    warning = get_special_directory_warning(current_dir)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
        if not yes and not Confirm.ask(f"{Colors.YELLOW}Continue anyway?{Colors.END}"):
            console.print("[yellow]Initialization cancelled.[/yellow]")
            return

    # Check if directory is empty
    if not is_directory_empty(current_dir) and not force:
        existing_files = os.listdir(current_dir)[:5]
        console.print("[yellow]⚠️  Directory not empty[/yellow]")
        console.print(f"[yellow]Existing files: {', '.join(existing_files[:5])}[/yellow]")
        if not yes and not Confirm.ask(f"\n{Colors.YELLOW}Add ConnectOnion to existing project?{Colors.END}"):
            console.print("[yellow]Initialization cancelled.[/yellow]")
            return

    # AI setup
    provider = None
    if ai is None:
        if not yes:
            # Interactive mode - check environment and ask
            env_api = check_environment_for_api_keys()
            if env_api:
                provider, env_key = env_api
                console.print(f"\n[green]✓ Found {provider.title()} API key in environment[/green]")
                ai = True
                if not key:
                    key = env_key
            else:
                ai = Confirm.ask(f"\n{Colors.CYAN}Enable AI features?{Colors.END}", default=True)
        else:
            # Non-interactive mode - enable AI if key provided
            ai = bool(key or check_environment_for_api_keys())

    # API key setup - use the unified menu for consistency
    api_key = key
    if ai and not api_key and not yes:
        api_key, provider, temp_project_dir = api_key_setup_menu()
        if api_key == "skip":
            # User chose to skip
            api_key = None
            ai = False  # Disable AI features since no API key
        elif not api_key and not provider:
            # User cancelled
            console.print("[yellow]API key setup cancelled.[/yellow]")
            return
    elif api_key:
        # Detect provider from the provided key
        provider, key_type = detect_api_provider(api_key)

    # Template selection
    if not template and not yes:
        # Check if directory has existing files
        has_existing_files = not is_directory_empty(current_dir)

        if has_existing_files:
            # For existing projects, offer option to just add ConnectOnion config
            template_info = [
                ('none', '⚙️  Just add ConnectOnion config', 'Add .co folder and .env without any template files'),
                ('minimal', '📦 Minimal', 'Basic agent structure'),
                ('playwright', '🎭 Playwright', 'Browser automation agent'),
            ]
            if ai:
                template_info.append(('custom', '✨ Custom', 'AI-generated agent'))
        else:
            # For empty directories, use normal template options
            template_info = get_template_info()
            # Filter out custom if AI is disabled
            if not ai:
                template_info = [t for t in template_info if t[0] != 'custom']

        template = interactive_menu(template_info, "Choose a template:")
    elif not template:
        # Default to 'none' for existing projects, 'minimal' for new
        template = 'none' if not is_directory_empty(current_dir) else 'minimal'

    # Handle custom template
    custom_code = None
    if template == 'custom':
        if not ai:
            console.print("[red]❌ Custom template requires AI to be enabled![/red]")
            return

        if not description and not yes:
            console.print("\n[cyan]🤖 Describe your agent:[/cyan]")
            description = Prompt.ask("  What should your agent do?")
        elif not description:
            description = "A general purpose agent"

        show_progress("Generating custom template with AI...", 2.0)
        custom_code = generate_custom_template(description, api_key or "")

    # Start initialization
    show_progress("Initializing ConnectOnion project...", 1.0)

    # Get template directory
    cli_dir = Path(__file__).parent.parent
    template_dir = cli_dir / "templates" / template if template != 'none' else None

    if template_dir and not template_dir.exists() and template not in ['custom', 'none']:
        console.print(f"[red]❌ Template '{template}' not found![/red]")
        return

    # Copy template files
    files_created = []
    files_skipped = []

    if template not in ['custom', 'none'] and template_dir and template_dir.exists():
        for item in template_dir.iterdir():
            # Skip hidden files except .env.example
            if item.name.startswith('.') and item.name != '.env.example':
                continue

            dest_path = Path(current_dir) / item.name

            if item.is_dir():
                # Copy directory
                if dest_path.exists() and not force:
                    files_skipped.append(f"{item.name}/ (already exists)")
                else:
                    if dest_path.exists():
                        shutil.rmtree(dest_path)
                    shutil.copytree(item, dest_path)
                    files_created.append(f"{item.name}/")
            else:
                # Skip .env.example, we'll create .env directly
                if item.name == '.env.example':
                    continue
                # Copy file
                if dest_path.exists() and not force:
                    files_skipped.append(f"{item.name} (already exists)")
                else:
                    shutil.copy2(item, dest_path)
                    files_created.append(item.name)

    # Create custom agent.py if custom template
    if custom_code:
        agent_file = Path(current_dir) / "agent.py"
        agent_file.write_text(custom_code)
        files_created.append("agent.py")

    # AUTHENTICATE FIRST - so we have OPENONION_API_KEY to add to .env
    global_co_dir = Path.home() / ".co"
    if not global_co_dir.exists():
        ensure_global_config()

    # Authenticate to get OPENONION_API_KEY (always, for everyone)
    auth_success = authenticate(global_co_dir, save_to_project=False)

    # Handle .env file - append API keys from global config
    env_path = Path(current_dir) / ".env"
    global_dir = Path.home() / ".co"
    global_keys_env = global_dir / "keys.env"

    # Read existing .env if it exists
    existing_env_content = ""
    existing_keys = set()
    if env_path.exists():
        with open(env_path, 'r') as f:
            existing_env_content = f.read()
            # Parse existing keys
            for line in existing_env_content.split('\n'):
                if '=' in line and not line.strip().startswith('#'):
                    key = line.split('=')[0].strip()
                    existing_keys.add(key)

    # Read global keys (now includes OPENONION_API_KEY from auth)
    keys_to_add = []
    if global_keys_env.exists():
        with open(global_keys_env, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key = line.split('=')[0].strip()
                    if key not in existing_keys:
                        keys_to_add.append(line)

    # If API key provided, add it if not exists
    if api_key and provider:
        provider_to_env = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
        }
        env_var = provider_to_env.get(provider, f"{provider.upper()}_API_KEY")
        if env_var not in existing_keys:
            keys_to_add.append(f"{env_var}={api_key}")

    # Write or append to .env
    if not env_path.exists():
        # Create new .env
        if keys_to_add:
            env_path.write_text('\n'.join(keys_to_add) + '\n')
            console.print(f"{Colors.GREEN}✓ Created .env with API keys{Colors.END}")
        else:
            # Fallback - should not happen now that we always auth
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
    elif keys_to_add:
        # Append missing keys to existing .env
        with open(env_path, 'a') as f:
            if not existing_env_content.endswith('\n'):
                f.write('\n')
            f.write('\n# API Keys\n')
            f.write('\n'.join(keys_to_add) + '\n')
        console.print(f"{Colors.GREEN}✓ Updated .env with API keys{Colors.END}")
        files_created.append(".env (updated)")
    else:
        console.print(f"{Colors.GREEN}✓ .env already contains all necessary keys{Colors.END}")

    # Create .co directory with metadata
    co_dir = Path(current_dir) / ".co"
    co_dir.mkdir(exist_ok=True)

    # Create docs directory and copy documentation (always overwrite for latest version)
    docs_dir = co_dir / "docs"
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(exist_ok=True)

    # Copy ConnectOnion documentation
    cli_dir = Path(__file__).parent.parent

    # Always copy the vibe coding doc for all templates - it's the master reference doc
    master_doc = cli_dir / "docs" / "co-vibecoding-principles-docs-contexts-all-in-one.md"

    if master_doc.exists():
        # Copy to .co/docs/ (project metadata)
        target_doc = docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md"
        shutil.copy2(master_doc, target_doc)
        files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")

        # ALSO copy to project root (always visible, easier to find)
        root_doc = Path(current_dir) / "co-vibecoding-principles-docs-contexts-all-in-one.md"
        shutil.copy2(master_doc, root_doc)
        files_created.append("co-vibecoding-principles-docs-contexts-all-in-one.md")
    else:
        console.print(f"[yellow]⚠️  Warning: Vibe coding documentation not found at {master_doc}[/yellow]")

    # Use global identity instead of generating project keys
    # NO PROJECT KEYS - we use global address/email
    # Reload global config to get updated email_active after authentication
    global_config = toml.load(global_co_dir / "config.toml") if (global_co_dir / "config.toml").exists() else global_config
    addr_data = global_config.get("agent", global_identity)  # Use updated global identity

    # Note: We're NOT creating project-specific keys anymore
    # If user wants project-specific keys, they'll use 'co address' command

    # Create config.toml
    config = {
        "project": {
            "name": os.path.basename(current_dir) or "connectonion-agent",
            "created": datetime.now().isoformat(),
            "framework_version": __version__,
        },
        "cli": {
            "version": "1.0.0",
            "command": "co init",
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

    # Handle .gitignore if in git repo
    if (Path(current_dir) / ".git").exists():
        gitignore_path = Path(current_dir) / ".gitignore"
        gitignore_content = """
# ConnectOnion
.env
.co/keys/
.co/cache/
.co/logs/
.co/history/
co-vibecoding-principles-docs-contexts-all-in-one.md
*.py[cod]
__pycache__/
todo.md
"""
        if gitignore_path.exists():
            with open(gitignore_path, "a") as f:
                if "# ConnectOnion" not in gitignore_path.read_text():
                    f.write(gitignore_content)
            files_created.append(".gitignore (updated)")
        else:
            gitignore_path.write_text(gitignore_content.lstrip())
            files_created.append(".gitignore")

    # Success message
    console.print(f"\n{Colors.GREEN}✅ ConnectOnion project initialized!{Colors.END}")

    console.print(f"\n📁 Project: {Colors.BOLD}{project_name}{Colors.END}")
    if template == 'none':
        console.print(f"⚙️  Configuration: {Colors.BOLD}ConnectOnion config added{Colors.END}")
    else:
        console.print(f"📦 Template: {Colors.BOLD}{template.title()}{Colors.END}")

    if custom_code and description:
        console.print(f"\n✨ {Colors.CYAN}Custom agent generated from:{Colors.END}")
        console.print(f"   {description[:60]}...")

    # Show agent address and email (using global)
    if 'addr_data' in locals() and addr_data.get('address'):
        console.print(f"\n🔑 Agent address: {Colors.CYAN}{addr_data['address']}{Colors.END} (global)")
        if addr_data.get('email'):
            console.print(f"📧 Agent email: {Colors.CYAN}{addr_data['email']}{Colors.END} (global)")

        console.print(f"\n💡 {Colors.CYAN}Using global identity. Run 'co address' to create project-specific identity.{Colors.END}")

    if files_created:
        console.print(f"\n{Colors.CYAN}📂 Files created:{Colors.END}")
        for file in files_created:
            if file == "agent.py":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - Main agent implementation")
            elif file == "prompts/":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - System prompts directory")
            elif file == ".env":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - Environment configuration (add your API key)")
            elif file == "README.md":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - Project documentation")
            elif file == ".co/":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - ConnectOnion metadata")
            elif file == ".co/keys/":
                console.print(f"  • {Colors.GREEN}{file}{Colors.END} - Agent cryptographic keys")
            else:
                console.print(f"  • {Colors.GREEN}{file}{Colors.END}")

    if files_skipped:
        console.print(f"\n{Colors.YELLOW}⚠️  Skipped (already exist):{Colors.END}")
        for file in files_skipped:
            console.print(f"  • {file}")

    # Show .env info
    console.print("")
    if auth_success:
        console.print(f"💡 {Colors.CYAN}Your .env is ready with API keys{Colors.END}")
        if api_key and provider:
            console.print(f"   • Using your {provider.title()} key")
        console.print(f"   • OPENONION_API_KEY also available (use 'co/' model prefix)")
    else:
        if api_key and provider:
            console.print(f"💡 {Colors.CYAN}API key saved to .env{Colors.END}")
        else:
            console.print(f"💡 {Colors.YELLOW}Add your API key to .env to enable AI features{Colors.END}")

    # Next steps with color coding
    console.print(f"\n{Colors.CYAN}🚀 Next steps:{Colors.END}")
    console.print(f"{Colors.CYAN}{'─' * 40}{Colors.END}")

    step = 1
    if not api_key:
        console.print(f"\n{step}️⃣  Add your API key to .env:")
        console.print(f"    Open {Colors.BOLD}.env{Colors.END} and replace 'sk-your-api-key-here'")
        step += 1

    console.print(f"\n{step}️⃣  Install dependencies:")
    console.print(f"    {Colors.BOLD}pip install python-dotenv{Colors.END}")
    step += 1

    if template == "playwright":
        console.print(f"    {Colors.BOLD}pip install playwright{Colors.END}")
        console.print(f"    {Colors.BOLD}playwright install{Colors.END}")
        step += 1

    console.print(f"\n{step}️⃣  Run your agent:")
    console.print(f"    {Colors.BOLD}python agent.py{Colors.END}")

    console.print(f"\n{Colors.CYAN}📚 Resources:{Colors.END}")
    console.print(f"   Documentation: {Colors.UNDERLINE}https://docs.connectonion.com{Colors.END}")
    console.print(f"   Discord: {Colors.UNDERLINE}https://discord.gg/4xfD9k8AUF{Colors.END}")

    # GitHub star request
    console.print(f"\n{Colors.CYAN}⭐ Support ConnectOnion:{Colors.END}")
    console.print(f"   Get 100K free tokens by starring our GitHub repo!")

    # Check if gh CLI is installed and star the repo
    try:
        # Check if gh is installed
        gh_check = subprocess.run(["which", "gh"], capture_output=True, text=True)
        if gh_check.returncode == 0:
            # Check if already starred
            star_check = subprocess.run(
                ["gh", "api", "user/starred/openonion/connectonion"],
                capture_output=True,
                text=True
            )

            if star_check.returncode != 0:
                # Not starred yet, star it
                console.print(f"   {Colors.YELLOW}Starring the ConnectOnion repo...{Colors.END}")
                star_result = subprocess.run(
                    ["gh", "api", "--method", "PUT", "user/starred/openonion/connectonion"],
                    capture_output=True,
                    text=True
                )
                if star_result.returncode == 0:
                    console.print(f"   {Colors.GREEN}✅ Thank you for starring ConnectOnion!{Colors.END}")
                    console.print(f"   {Colors.GREEN}🎁 Your 100K tokens will be credited shortly.{Colors.END}")
                else:
                    console.print(f"   {Colors.YELLOW}⚠️  Couldn't star automatically. Please star manually:{Colors.END}")
                    console.print(f"   {Colors.UNDERLINE}https://github.com/openonion/connectonion{Colors.END}")
            else:
                console.print(f"   {Colors.GREEN}✅ You've already starred ConnectOnion. Thank you!{Colors.END}")
        else:
            # gh CLI not installed
            console.print(f"   {Colors.YELLOW}Star us on GitHub:{Colors.END} {Colors.UNDERLINE}https://github.com/openonion/connectonion{Colors.END}")
    except Exception:
        # Fallback if any error occurs
        console.print(f"   {Colors.YELLOW}Star us on GitHub:{Colors.END} {Colors.UNDERLINE}https://github.com/openonion/connectonion{Colors.END}")

    console.print()

    # Clean up temporary project directory if created for authentication
    if temp_project_dir and temp_project_dir.exists():
        # Copy the auth token to the current project
        temp_config = temp_project_dir / ".co" / "config.toml"
        current_config = Path(current_dir) / ".co" / "config.toml"
        if temp_config.exists() and current_config.exists():
            temp_data = toml.load(temp_config)
            current_data = toml.load(current_config)
            if "auth" in temp_data:
                current_data["auth"] = temp_data["auth"]
                with open(current_config, "w") as f:
                    toml.dump(current_data, f)

        # Remove the temp directory
        shutil.rmtree(temp_project_dir)
