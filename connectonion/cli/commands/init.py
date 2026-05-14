"""
Purpose: Initialize ConnectOnion project in current directory with template files, authentication, and configuration
LLM-Note:
  Dependencies: imports from [os, sys, shutil, subprocess, yaml, datetime, pathlib, rich.console, rich.prompt, __version__, address, auth_commands.authenticate, project_cmd_lib] | imported by [cli/main.py via handle_init()] | uses templates from [cli/templates/{minimal,playwright}] | tested by [tests/e2e/cli/test_cli_init.py]
  Data flow: receives args (ai, key, template, description, yes, force) from CLI parser → ensure_global_config() creates ~/.co/ with master keypair if needed → check_environment_for_api_keys() detects existing keys → api_key_setup_menu() or detect_api_provider() validates API key → generate_custom_template() if template='custom' → copy template files from cli/templates/{template}/ to current dir → authenticate() to get OPENONION_API_KEY → create/update .env with API keys from ~/.co/keys.env → create .co/host.yaml with project metadata and global identity → copy vibe coding docs to .co/docs/ and project root → update .gitignore if git repo → display success message with next steps
  State/Effects: modifies ~/.co/ (host.yaml, keys.env, keys/, logs/) on first run | writes to current dir: .co/host.yaml, .env, agent.py (if template), .gitignore | calls authenticate() which writes OPENONION_API_KEY to ~/.co/keys.env | copies template files (agent.py, requirements.txt, etc.) | creates temp_project_dir during auth flow (cleaned up at end) | writes to stdout via rich.Console
  Integration: exposes handle_init(ai, key, template, description, yes, force) | calls ensure_global_config() to create global identity | calls authenticate(global_co_dir, save_to_project=False) for managed keys | uses template files from cli/templates/ | relies on project_cmd_lib for shared functions | uses address.generate() and address.save() for Ed25519 keypair | template options: 'minimal', 'playwright', 'custom', 'none' (default)
  Performance: authenticate() makes network call to backend (2-5s) | generate_custom_template() calls LLM API if template='custom' | template file copying is O(n) files | config/env file operations are I/O bound
  Errors: fails if cli/templates/{template}/ not found | fails if API key invalid during authenticate() | warns if directory not empty (requires --force or confirmation) | warns for special directories (home, root, system dirs) | skips duplicate .env keys (safe append) | creates temp_project_dir but cleans up on completion
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm
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
    get_special_directory_warning,
    is_directory_empty,
    check_environment_for_api_keys,
    detect_api_provider,
    generate_custom_template,
    show_progress,
)

console = Console()


def handle_init(ai: Optional[bool], key: Optional[str], template: Optional[str],
                description: Optional[str], yes: bool, force: bool):
    """Initialize a ConnectOnion project in the current directory."""
    # Ensure global config exists first
    ensure_global_config()

    current_dir = os.getcwd()
    project_name = os.path.basename(current_dir) or "my-agent"

    # Track temp directory for cleanup
    temp_project_dir = None

    # Header removed for cleaner output

    # Check for special directories
    warning = get_special_directory_warning(current_dir)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
        if not yes and not Confirm.ask("[yellow]Continue anyway?[/yellow]"):
            console.print("[yellow]Initialization cancelled.[/yellow]")
            return

    # Check if directory is empty
    if not is_directory_empty(current_dir) and not force:
        existing_files = os.listdir(current_dir)[:5]
        console.print("[yellow]⚠️  Directory not empty[/yellow]")
        console.print(f"[yellow]Existing files: {', '.join(existing_files[:5])}[/yellow]")
        if not yes and not Confirm.ask("\n[yellow]Add ConnectOnion to existing project?[/yellow]"):
            console.print("[yellow]Initialization cancelled.[/yellow]")
            return

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

    # Template selection - default to 'none' (just add .co folder) unless --template provided
    if not template:
        # No --template flag provided, just add ConnectOnion config
        template = 'none'
        if not yes:
            console.print("\n[green]✓ Adding ConnectOnion config (.co folder)[/green] (use --template <name> for full templates)")
    # else: template has a specific value from --template <name>

    # Handle custom template
    custom_code = None
    if template == 'custom':
        if not description and not yes:
            console.print("\n[cyan]🤖 Describe your agent:[/cyan]")
            description = Prompt.ask("  What should your agent do?")
        elif not description:
            description = "A general purpose agent"

        show_progress("Generating custom template with AI...", 2.0)
        # Use detected key or empty string (will use OPENONION_API_KEY after auth)
        template_key = list(detected_keys.values())[0] if detected_keys else ""
        custom_code = generate_custom_template(description, template_key)

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
        agent_file.write_text(custom_code, encoding='utf-8')
        files_created.append("agent.py")

    # AUTHENTICATE FIRST - so we have OPENONION_API_KEY to add to .env
    global_co_dir = Path.home() / ".co"

    # Authenticate to get OPENONION_API_KEY (always, for everyone)
    auth_success = authenticate(global_co_dir, save_to_project=False)

    # Handle .env file - append API keys from global config
    env_path = Path(current_dir) / ".env"
    global_dir = Path.home() / ".co"
    global_keys_env = global_dir / "keys.env"

    # Identity keys: always overwrite from global (co reset must propagate)
    IDENTITY_KEYS = {'AGENT_CONFIG_PATH', 'AGENT_ADDRESS', 'OPENONION_API_KEY',
                     'AGENT_EMAIL', 'IS_EMAIL_ACTIVE'}

    # Read global keys.env into a dict
    global_keys = {}  # key -> "KEY=value" line
    if global_keys_env.exists():
        with open(global_keys_env, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key = line.split('=')[0].strip()
                    global_keys[key] = line

    # Read existing .env: overwrite identity keys, track existing keys
    existing_keys = set()
    updated_lines = []
    env_existed = env_path.exists()
    if env_existed:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if '=' in stripped and not stripped.startswith('#'):
                    key = stripped.split('=')[0].strip()
                    existing_keys.add(key)
                    if key in IDENTITY_KEYS and key in global_keys:
                        # Overwrite with global value
                        updated_lines.append(global_keys[key] + '\n')
                        continue
                updated_lines.append(line)

    # Collect keys to append (not already in .env)
    keys_to_add = []
    for key, line in global_keys.items():
        if key not in existing_keys:
            keys_to_add.append(line)
    for prov, key_value in detected_keys.items():
        env_var = PROVIDER_TO_ENV.get(prov, f"{prov.upper()}_API_KEY")
        if env_var not in existing_keys:
            keys_to_add.append(f"{env_var}={key_value}")

    # Write .env
    if not env_existed:
        if keys_to_add or global_keys:
            env_content = f"AGENT_CONFIG_PATH={Path.home() / '.co'}\n"
            env_content += "# Default model: co/gemini-2.5-pro (managed keys with free credits)\n\n"
            # Add all global keys + detected keys
            all_keys = list(global_keys.values()) + [k for k in keys_to_add if k not in global_keys.values()]
            env_content += '\n'.join(all_keys) + '\n'
            env_path.write_text(env_content, encoding='utf-8')
            console.print(f"[green]✓ Saved to {env_path}[/green]")
        else:
            env_content = """# Add your LLM API key(s) below (uncomment one and set value)
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
# GROQ_API_KEY=
# XAI_API_KEY=
# OPENROUTER_API_KEY=

# Optional: Override default model
# MODEL=gpt-4o-mini
"""
            env_path.write_text(env_content, encoding='utf-8')
        files_created.append(".env")
    else:
        # Write back with identity keys overwritten + append missing keys
        content = ''.join(updated_lines)
        if keys_to_add:
            if not content.endswith('\n'):
                content += '\n'
            content += '\n# API Keys\n'
            content += '\n'.join(keys_to_add) + '\n'
        env_path.write_text(content, encoding='utf-8')
        if keys_to_add or any(k in IDENTITY_KEYS for k in existing_keys):
            console.print(f"[green]✓ Updated {env_path}[/green]")
            files_created.append(".env (updated)")
        else:
            console.print("[green]✓ .env already contains all necessary keys[/green]")

    # Create .co directory with metadata
    co_dir = Path(current_dir) / ".co"
    co_dir.mkdir(exist_ok=True)

    # Copy documentation to .co/docs/
    if copy_docs(co_dir):
        files_created.append(".co/docs/ (full documentation)")

    # NO PROJECT KEYS - we use global address/email

    # Note: We're NOT creating project-specific keys anymore
    # If user wants project-specific keys, they'll use 'co address' command

    # Create host.yaml from template (unified config for host() and co deploy)
    host_name = os.path.basename(current_dir) or "connectonion-agent"
    if create_host_yaml(co_dir, host_name):
        files_created.append(".co/host.yaml")

    # Handle .gitignore if in git repo
    gi_result = setup_gitignore(Path(current_dir))
    if gi_result:
        files_created.append(gi_result)

    # Success message with Rich formatting
    console.print()
    console.print(f"[bold green]✅ Initialized ConnectOnion in {project_name}[/bold green]")
    console.print()

    # Show different message based on whether agent.py exists
    if template != 'none' and (Path(current_dir) / "agent.py").exists():
        # Command with syntax highlighting - compact design
        command = "python agent.py"
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
    else:
        # Vibe Coding hint for building from scratch
        console.print("[bold yellow]💡 Vibe Coding:[/bold yellow] Use Claude/Cursor/Codex with")
        console.print(f"   [cyan].co/docs/[/cyan] to build your agent")

    # Resources
    console.print()
    print_resources()

    # Clean up temporary project directory if created for authentication
    if temp_project_dir and temp_project_dir.exists():
        shutil.rmtree(temp_project_dir)
