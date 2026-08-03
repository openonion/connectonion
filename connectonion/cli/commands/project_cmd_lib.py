"""
Purpose: Shared utility functions for CLI project commands including validation, API key detection, template generation, and Rich UI helpers
LLM-Note:
  Dependencies: imports from [os, re, sys, time, shutil, rich.console, rich.prompt, rich.progress, rich.table, rich.panel, datetime, pathlib, __version__, address] | imported by [cli/commands/init.py, cli/commands/create.py] | calls LLM APIs for custom template generation | tested indirectly via test_cli_init.py and test_cli_create.py
  Data flow: provides utility functions called by init.py and create.py → validate_project_name() checks regex patterns → check_environment_for_api_keys() scans env vars for OpenAI/Anthropic/Google/Groq/Grok/OpenRouter keys → detect_api_provider() inspects key format to identify provider → api_key_setup_menu() displays interactive menu for key selection → generate_custom_template_with_name() calls LLM API with custom prompt to generate agent.py code → show_progress() displays Rich spinner → LoadingAnimation context manager for long operations → get_special_directory_warning() warns about home/root dirs
  State/Effects: no persistent state | reads from environment variables | writes to stdout via rich.Console | calls LLM APIs (OpenAI/Anthropic/Google) when generating custom templates | creates Rich UI elements (tables, panels, progress bars, prompts) | writes no files except create_host_yaml() (.co/host.yaml)
  Integration: exposes 16+ utility functions and 1 class (LoadingAnimation) | used by init.py and create.py for shared logic | validate_project_name() enforces naming conventions for the project/directory name (starts with letter, no spaces, max 50 chars) | normalize_deploy_name()/DEPLOY_NAME_PATTERN cover the separate, stricter rule for the deploy name written into host.yaml (a DNS label and Docker tag: lowercase, digits, hyphens), applied by create_host_yaml() and re-checked by deploy_commands.py | check_environment_for_api_keys() scans OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY, XAI_API_KEY, OPENROUTER_API_KEY | detect_api_provider() identifies provider by key prefix (sk- for OpenAI, sk-ant- for Anthropic, AIzaSy for Google, gsk- for Groq, xai- for Grok, sk-or- for OpenRouter) | generate_custom_template_with_name() uses LLM to create agent.py from natural language description
  Performance: environment scanning is O(n) env vars | regex validation is fast (<1ms) | LLM API calls for custom templates (5-15s) | Rich UI rendering is lightweight | LoadingAnimation runs in main thread (non-blocking spinner)
  Errors: validate_project_name() returns (False, error_msg) for invalid names | detect_api_provider() returns ("unknown", "unknown") for unrecognized keys | generate_custom_template_with_name() may fail if LLM API unreachable | api_key_setup_menu() catches KeyboardInterrupt and returns ("", "", None) | no try-except blocks (follows fail-fast principle)
"""

import base64
import binascii
import json
import os
import re
import sys
import time
import shutil
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel
from rich import box
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from ... import __version__
from ... import address

console = Console()


def mint_invite_code() -> str:
    """One code, for one agent, generated once.

    The alphabet drops O/0 and I/1 because this gets read off a screen and
    typed on a phone. Three groups of five is enough entropy for a door that
    also checks trust levels, and short enough to dictate over a call.

    Callers mint it only when the project has none: regenerating would silently
    lock out everyone already holding the old one.

    It replaced the shipped policy's literal `invite_code: [OpenOnion]` — one
    password for every deployment, published in this repository and printed by
    every agent on startup (#561). `co init` minted one from the start and
    `co create` did not, so the command the docs lead with produced a project
    that told its operator "no one can onboard" and pointed at the other
    command for the fix.
    """
    import secrets

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5))
                    for _ in range(3))


def get_docs_source() -> Path:
    """Get the docs directory path - works in both dev and installed package."""
    # After pip install: connectonion/docs/ exists (via force-include)
    package_dir = Path(__file__).parent.parent.parent  # connectonion/cli/commands/ → connectonion/
    docs_source = package_dir / "docs"

    # Fallback for editable install: docs are at project root
    if not docs_source.exists():
        project_root = package_dir.parent
        docs_source = project_root / "docs"

    return docs_source




def validate_project_name(name: str) -> Tuple[bool, str]:
    """Validate project name for common issues.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Project name cannot be empty"

    if ' ' in name:
        return False, "Project name cannot contain spaces. Try using hyphens instead (e.g., 'my-agent')"

    if not re.match(r'^[a-zA-Z][a-zA-Z0-9-_]*$', name):
        return False, "Project name must start with a letter and contain only letters, numbers, hyphens, and underscores"

    if len(name) > 50:
        return False, "Project name is too long (max 50 characters)"

    return True, ""


def show_progress(message: str, duration: float = 0.5):
    """Show a brief progress spinner using Rich."""
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        task_id = progress.add_task(message, total=None)
        end_time = time.time() + duration
        while time.time() < end_time:
            time.sleep(0.05)
        progress.remove_task(task_id)


class LoadingAnimation:
    """Context manager for showing loading animation during long operations."""

    def __init__(self, message: str):
        self.message = message
        self.progress = None
        self.task_id = None

    def __enter__(self):
        from rich.progress import Progress, SpinnerColumn, TextColumn
        self.progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[cyan]{task.description}"),
            transient=False,
            console=console,
        )
        self.progress.start()
        self.task_id = self.progress.add_task(self.message, total=None)
        return self

    def update(self, new_message: str):
        """Update the loading message."""
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, description=new_message)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.progress:
            self.progress.stop()


def get_template_info() -> list:
    """Get template information for display.

    One template. `co-ai` is the same agent as `co ai` — files, shell, browser,
    planning, sub-agents — and you specialise it with skills in .co/skills/
    rather than by starting from a different skeleton.
    """
    return [
        ('co-ai', '🚀 Agent', 'The co ai agent, hosted — specialise it with skills'),
        ('custom', '✨ Custom', 'AI-generated agent'),
    ]


def unknown_template_message(template: str) -> str:
    """Explain an unknown --template, naming the ones that exist.

    The retired names (minimal, coder, browser, hosted-browser, web-research)
    are still in scripts and blog posts, so this has to say where they went
    rather than only that the name is wrong.
    """
    available = ", ".join(name for name, _, _ in get_template_info())
    retired = {"minimal", "coder", "browser", "hosted-browser", "web-research"}

    lines = [f"[red]❌ Template '{template}' not found.[/red]", f"   Available: {available}"]
    if template in retired:
        lines.append(
            "   That template was retired: co-ai is the same agent with more "
            "tools. Specialise it with skills in .co/skills/ instead of a "
            "separate starting point."
        )
    return "\n".join(lines)


def get_template_suggested_name(template: str) -> str:
    """Get suggested project name for a template."""
    suggestions = {
        'co-ai': 'my-agent',
        'custom': None  # Will be generated by AI
    }
    return suggestions.get(template, 'my-agent')


def api_key_setup_menu(temp_project_dir: Optional[Path] = None) -> Tuple[str, str, Path]:
    """Show API key setup options to the user.

    Args:
        temp_project_dir: Optional temporary project directory to use for auth

    Returns:
        Tuple of (api_key, provider, temp_dir) where temp_dir is the temporary project created for auth
    """
    from ... import address  # Import address module for key generation

    try:
        import questionary
        from questionary import Style

        custom_style = Style([
            ('question', 'fg:#00ffff bold'),
            ('pointer', 'fg:#00ff00 bold'),
            ('highlighted', 'fg:#00ff00 bold'),
            ('selected', 'fg:#00ffff'),
            ('separator', 'fg:#808080'),
            ('instruction', 'fg:#808080'),
        ])

        choices = [
            questionary.Choice(
                title="🔑 BYO API key (OpenAI, Anthropic, Gemini)",
                value="own_key"
            ),
            questionary.Choice(
                title="⭐ Star for $1 OpenOnion credit (100k free tokens)",
                value="star"
            ),
            questionary.Choice(
                title="⏭️  Skip (get $0.1 OpenOnion credit 10k free tokens)",
                value="skip"
            ),
        ]

        result = questionary.select(
            "How would you like to set up API access?",
            choices=choices,
            style=custom_style,
            instruction="(Use ↑/↓ arrows, press Enter to confirm)",
        ).ask()

        if result == "own_key":
            # Ask for their API key
            console.print("\n[cyan]Paste your API key (we'll detect the provider)[/cyan]")
            api_key = questionary.password("API key:").ask()
            if api_key:
                provider, key_type = detect_api_provider(api_key)
                console.print(f"[green]✓ {provider.title()} API key configured[/green]")
                return api_key, provider, None  # No temp dir for own keys
            return "", "", None

        elif result == "star":
            # Star for free credits - create temp project and authenticate immediately
            import webbrowser
            import shutil
            from pathlib import Path

            console.print("\n[cyan]⭐ Get 100k Free Tokens[/cyan]")
            console.print("\nOpening GitHub in your browser...")

            # Try to open the GitHub repo for starring
            github_url = "https://github.com/openonion/connectonion"
            try:
                webbrowser.open(github_url)
            except:
                pass  # Browser opening might fail in some environments

            # Keep asking until they confirm they've starred
            while True:
                already_starred = questionary.confirm(
                    "\nHave you starred our repository?",
                    default=False
                ).ask()

                if already_starred:
                    console.print("[green]✓ Thank you for your support![/green]")

                    # Create temporary project directory
                    temp_name = "connectonion-temp-project"
                    temp_dir = Path(temp_name)
                    counter = 1
                    while temp_dir.exists():
                        temp_dir = Path(f"{temp_name}-{counter}")
                        counter += 1

                    console.print(f"\n[yellow]Setting up temporary project for authentication...[/yellow]")
                    temp_dir.mkdir(parents=True)

                    # Create .co directory and generate keys
                    co_dir = temp_dir / ".co"
                    co_dir.mkdir()

                    try:
                        # Generate keys for this project
                        addr_data = address.generate()
                        address.save(addr_data, co_dir)

                        # Run direct registration with the project keys (no browser)
                        console.print("\n[yellow]Activating your free credits...[/yellow]\n")

                        from .auth_commands import authenticate
                        if authenticate(co_dir):
                            console.print("\n[green]✓ We verified your star. Thanks for supporting us![/green]")
                            console.print("[green]You now have 100k free tokens![/green]")
                            console.print("\n[cyan]You can use ConnectOnion models with the 'co/' prefix:[/cyan]")
                            console.print("  • co/gemini-3.6-flash")
                            console.print("  • co/gemini-3-pro-preview")
                            console.print("  • co/gpt-5")
                            console.print("  • co/claude-sonnet-4")

                            return "star", "connectonion", temp_dir  # Return the temp directory
                        else:
                            # Auth failed, clean up
                            shutil.rmtree(temp_dir)
                            console.print("[yellow]Authentication failed. Please try again.[/yellow]")
                            return "", "", None
                    except Exception as e:
                        # Clean up on error
                        if temp_dir.exists():
                            shutil.rmtree(temp_dir)
                        console.print(f"[red]Error: {e}[/red]")
                        return "", "", None

                    break  # Exit the loop
                else:
                    console.print("\n[yellow]Please star the repository to get your free tokens![/yellow]")
                    console.print(f"\nIf the browser didn't open, visit: [cyan]{github_url}[/cyan]")
                    console.print("You can copy and paste this URL into your browser.")
                    console.print("\n[dim]We'll wait for you to star the repository...[/dim]")
                    # Loop will continue to ask again

            return "star", "connectonion", None  # Should not reach here

        elif result == "skip":
            # User chose to skip API setup
            console.print("\n[yellow]⏭️  Skipping API setup[/yellow]")
            console.print("[dim]You can add your API key later in the .env file[/dim]")
            return "skip", "", None  # Return "skip" as api_key to indicate skip choice

        else:
            raise KeyboardInterrupt()

    except ImportError:
        # Fallback to simple menu
        console.print("\n[cyan]🔑 API Key Setup[/cyan]")
        console.print("1. BYO API key (OpenAI, Anthropic, Gemini)")
        console.print("2. Star for $1 OpenOnion credit (100k free tokens)")
        console.print("3. Skip (get $0.1 OpenOnion credit 10k free tokens)")

        choice = IntPrompt.ask("Select option", choices=["1", "2", "3"], default="3")
        choice = int(choice)

        if choice == 1:
            api_key = Prompt.ask("API key", password=True, default="")
            if api_key:
                provider, key_type = detect_api_provider(api_key)
                console.print(f"[green]✓ {provider.title()} API key configured[/green]")
                return api_key, provider, False  # No auth needed for own keys
            return "", "", False
        elif choice == 2:
            import webbrowser

            console.print("\n[cyan]⭐ Get 100k Free Tokens[/cyan]")
            console.print("\nOpening GitHub in your browser...")

            # Try to open the GitHub repo for starring
            github_url = "https://github.com/openonion/connectonion"
            try:
                webbrowser.open(github_url)
            except:
                pass  # Browser opening might fail in some environments

            # Keep asking until they confirm they've starred
            while True:
                already_starred = Confirm.ask("\nHave you starred our repository?", default=False)

                if already_starred:
                    console.print("[green]✓ Thank you for your support![/green]")
                    console.print("\n[yellow]Authenticating to activate your free credits...[/yellow]\n")

                    try:
                        from .auth_commands import authenticate
                        authenticate(Path(".co"))
                        console.print("\n[green]✓ We verified your star. Thanks for supporting us![/green]")
                        console.print("[green]You now have 100k free tokens![/green]")
                        console.print("\n[cyan]You can use ConnectOnion models with the 'co/' prefix:[/cyan]")
                        console.print("  • co/gemini-3.6-flash")
                        console.print("  • co/gemini-3-pro-preview")
                        console.print("  • co/gpt-5")
                        console.print("  • co/claude-sonnet-4")
                        break  # Success, exit the loop
                    except Exception as e:
                        console.print(f"\n[red]Authentication failed: {e}[/red]")
                        console.print("[yellow]Please try running: [bold]co auth[/bold][/yellow]")
                        break  # Exit on auth failure
                else:
                    console.print("\n[yellow]Please star the repository to get your free tokens![/yellow]")
                    console.print(f"\nIf the browser didn't open, visit: [cyan]{github_url}[/cyan]")
                    console.print("You can copy and paste this URL into your browser.")
                    console.print("\n[dim]We'll wait for you to star the repository...[/dim]")
                    # Loop will continue to ask again

            return "star", "connectonion", None

        elif choice == 3:
            # Skip - user will get free tokens
            console.print("\n[yellow]⏭️  Skipping API setup[/yellow]")
            console.print("[dim]You'll get $0.1 OpenOnion credit (10k tokens) to get started[/dim]")
            console.print("[dim]Add your own API key to .env later for unlimited usage[/dim]")
            return "skip", "", None

        else:
            return "", "", None


def interactive_menu(options: List[Tuple[str, str, str]], prompt: str = "Choose an option:") -> str:
    """Interactive menu with arrow key navigation using questionary.

    Args:
        options: List of (key, emoji+name, description) tuples
        prompt: Menu prompt text

    Returns:
        Selected option key
    """
    try:
        import questionary
        from questionary import Style

        # Custom style using questionary's styling
        custom_style = Style([
            ('question', 'fg:#00ffff bold'),
            ('pointer', 'fg:#00ff00 bold'),  # The > pointer
            ('highlighted', 'fg:#00ff00 bold'),  # Currently selected item
            ('selected', 'fg:#00ffff'),  # Selected item after pressing enter
            ('separator', 'fg:#808080'),
            ('instruction', 'fg:#808080'),  # (Use arrow keys)
        ])

        # Create choices with formatted strings
        choices = []
        for key, name, desc in options:
            # Format: "📦 Minimal - Basic agent"
            choice_text = f"{name} - {desc}"
            choices.append(questionary.Choice(title=choice_text, value=key))

        # Show the selection menu
        result = questionary.select(
            prompt,
            choices=choices,
            style=custom_style,
            instruction="(Use ↑/↓ arrows, press Enter to confirm)",
        ).ask()

        if result:
            # Find the selected option name for confirmation
            for key, name, _ in options:
                if key == result:
                    console.print(f"[green]✓ Selected:[/green] {name}")
                    break
            return result
        else:
            # User cancelled (pressed Ctrl+C or Escape)
            raise KeyboardInterrupt()

    except ImportError:
        # Fallback to the original Rich + Click implementation
        console.print()
        console.print(Panel.fit(prompt, style="cyan", border_style="cyan", title="Templates"))

        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("No.", justify="right", style="bold")
        table.add_column("Template", style="white")
        table.add_column("Description", style="dim")

        for i, (_, name, desc) in enumerate(options, 1):
            table.add_row(str(i), name, desc)

        console.print(table)

        choices = [str(i) for i in range(1, len(options) + 1)]
        selected = IntPrompt.ask(
            "Select [number]",
            choices=choices,
            default="1"
        )

        idx = int(selected) - 1
        selected_option = options[idx]
        console.print(f"[green]✓ Selected:[/green] {selected_option[1]}")
        return selected_option[0]


def get_template_preview(template: str) -> str:
    """Get a preview of what the template includes."""
    previews = {
        'co-ai': """  🚀 Agent - the co ai agent, hosted
    ├── agent.py - create_agent() + host(), ~5 lines
    ├── Dockerfile - Chrome under Xvfb, so browser skills work deployed
    ├── requirements.txt
    ├── .env - API key configuration
    └── .co/ - identity, host.yaml, and skills/ (where you specialise it)""",

        'custom': """  ✨ Custom - AI generates based on your needs
    ├── agent.py - Tailored to your description
    ├── tools/ - Custom tools for your use case
    ├── .env - API key configuration
    ├── README.md - Custom documentation
    └── .co/ - Agent identity & metadata""",
    }

    return previews.get(template, f"  📄 {template.title()} template")


def check_environment_for_api_keys() -> Optional[Tuple[str, str]]:
    """Check environment variables for API keys.

    Returns:
        Tuple of (provider, api_key) if found, None otherwise
    """
    import os

    # Check for various API key environment variables
    checks = [
        ('OPENAI_API_KEY', 'openai'),
        ('ANTHROPIC_API_KEY', 'anthropic'),
        ('GEMINI_API_KEY', 'google'),
        ('GOOGLE_API_KEY', 'google'),
        ('GROQ_API_KEY', 'groq'),
        ('XAI_API_KEY', 'grok'),
        ('OPENROUTER_API_KEY', 'openrouter'),
    ]

    for env_var, provider in checks:
        api_key = os.environ.get(env_var)
        if api_key and api_key != 'your-api-key-here' and not api_key.startswith('sk-your'):
            return provider, api_key

    return None


def detect_api_provider(api_key: str) -> Tuple[str, str]:
    """Detect API provider from key format.

    Returns:
        Tuple of (provider, key_type)
    """
    # Check Anthropic first (more specific prefix)
    if api_key.startswith('sk-ant-'):
        return 'anthropic', 'claude'

    # OpenAI formats
    if api_key.startswith('sk-proj-'):
        return 'openai', 'project'
    elif api_key.startswith('sk-'):
        return 'openai', 'user'

    # Google (Gemini)
    if api_key.startswith('AIza'):
        return 'google', 'gemini'

    # Groq
    if api_key.startswith('gsk_'):
        return 'groq', 'groq'

    # xAI Grok
    if api_key.startswith('xai-'):
        return 'grok', 'xai'

    # OpenRouter
    if api_key.startswith('sk-or-'):
        return 'openrouter', 'openrouter'

    # Default to OpenAI if unsure
    return 'openai', 'unknown'


def configure_env_for_provider(provider: str, api_key: str) -> str:
    """Generate .env content based on provider.

    Args:
        provider: API provider name
        api_key: The API key

    Returns:
        .env file content
    """
    configs = {
        'openai': {
            'var': 'OPENAI_API_KEY',
            'model': 'o4-mini'
        },
        'anthropic': {
            'var': 'ANTHROPIC_API_KEY',
            'model': 'claude-sonnet-4-20250514'
        },
        'google': {
            'var': 'GEMINI_API_KEY',
            'model': 'gemini-2.5-flash'
        },
        'groq': {
            'var': 'GROQ_API_KEY',
            'model': 'groq/llama-3.3-70b-versatile'
        },
        'grok': {
            'var': 'XAI_API_KEY',
            'model': 'grok/grok-4'
        },
        'openrouter': {
            'var': 'OPENROUTER_API_KEY',
            'model': 'openrouter/openai/o4-mini'
        },
        'connectonion': {
            'var': 'CONNECTONION_API_KEY',
            'model': 'co/gemini-3.6-flash'  # Prefixed models for managed keys
        }
    }

    config = configs.get(provider, configs['openai'])

    # Special handling for ConnectOnion managed keys
    if provider == 'connectonion':
        if api_key == 'managed':
            return f"""# ConnectOnion Managed Keys Configuration
# Authenticate with: co auth
# Purchase credits at: https://o.openonion.ai
# Same pricing as OpenAI/Anthropic

# Model Configuration (use co/ prefix for managed models)
MODEL=co/gemini-3.6-flash
# Available models: co/gemini-3.6-flash, co/gemini-3-pro-preview, co/gpt-5, co/claude-sonnet-4

# No API key needed - authentication handled via JWT token from 'co auth'

# Optional: Override default settings
# MAX_TOKENS=2000
# TEMPERATURE=0.7
"""
        elif api_key == 'star':
            return f"""# ConnectOnion Free Credits (100k tokens)
# 1. Star us: https://github.com/openonion/connectonion
# 2. Authenticate with: co auth
# 3. Your GitHub star will be verified automatically

# Model Configuration (use co/ prefix for managed models)
MODEL=co/gemini-3.6-flash

# No API key needed - authentication handled via JWT token from 'co auth'

# Optional: Override default settings
# MAX_TOKENS=2000
# TEMPERATURE=0.7
"""

    return f"""# {provider.title()} API Configuration
{config['var']}={api_key}

# Model Configuration
MODEL={config['model']}

# Optional: Override default settings
# MAX_TOKENS=2000
# TEMPERATURE=0.7
"""


def generate_custom_template_with_name(description: str, api_key: str, model: str = None, loading_animation=None) -> Tuple[str, str]:
    """Generate custom agent template and suggested name using AI.

    Args:
        description: What the agent should do
        api_key: API key or token for LLM
        model: Optional model to use (e.g., "co/gemini-3.6-flash")
        loading_animation: Optional LoadingAnimation instance to update

    Returns:
        Tuple of (agent_code, suggested_name)
    """
    import re

    # Default fallback values
    suggested_name = "custom-agent"

    # Try to use AI to generate name and code
    if model or api_key:
        try:
            from ...core.llm import create_llm

            # Use the model specified or default to co/gemini-3.6-flash
            llm_model = model if model else "co/gemini-3.6-flash"

            if loading_animation:
                loading_animation.update(f"Connecting to {llm_model}...")

            # Create LLM instance
            if model and model.startswith("co/"):
                # Using ConnectOnion managed keys - api_key is actually the JWT token
                llm = create_llm(model=llm_model, api_key=api_key)
            else:
                # Using user's API key
                llm = create_llm(model=llm_model, api_key=api_key if api_key else None)

            # Generate project name and code with AI
            prompt = f"""Based on this description: "{description}"

Generate:
1. A short, descriptive project name (lowercase, hyphenated, max 30 chars, no spaces)
2. Python code for a ConnectOnion agent that implements this functionality

Respond in this exact format:
PROJECT_NAME: your-suggested-name
CODE:
```python
# Your generated code here
```"""

            messages = [
                {"role": "system", "content": "You are an AI assistant that generates ConnectOnion agent code and project names."},
                {"role": "user", "content": prompt}
            ]

            if loading_animation:
                loading_animation.update(f"Generating agent code...")

            response = llm.complete(messages)

            if response.content:
                # Parse the response
                lines = response.content.split('\n')
                for line in lines:
                    if line.startswith("PROJECT_NAME:"):
                        suggested_name = line.replace("PROJECT_NAME:", "").strip()
                        # Validate name format
                        suggested_name = re.sub(r'[^a-z0-9-]', '', suggested_name.lower())
                        if len(suggested_name) > 30:
                            suggested_name = suggested_name[:30]
                        break

                # Extract code between ```python and ```
                if "```python" in response.content and "```" in response.content:
                    code_start = response.content.find("```python") + 9
                    code_end = response.content.find("```", code_start)
                    if code_end > code_start:
                        agent_code = response.content[code_start:code_end].strip()
                        return agent_code, suggested_name

        except Exception as e:
            # If AI generation fails, fall back to simple generation
            print(f"AI generation failed: {e}, using fallback")

    # Fallback: Simple name generation from description
    words = description.lower().split()[:3]
    suggested_name = "-".join(re.sub(r'[^a-z0-9]', '', word) for word in words if word)
    if not suggested_name:
        suggested_name = "custom-agent"
    else:
        suggested_name = suggested_name + "-agent"

    if len(suggested_name) > 30:
        suggested_name = suggested_name[:30]

    # Fallback agent code
    agent_code = f"""# {description}
# Generated with ConnectOnion

from connectonion import Agent

def process_request(query: str) -> str:
    '''Process user queries for: {description}'''
    return f"Processing: {{query}}"

# Create agent
agent = Agent(
    name="{suggested_name.replace('-', '_')}",
    model="{model if model and model.startswith('co/') else 'co/gemini-3.6-flash'}",
    system_prompt=\"\"\"You are an AI agent designed to: {description}

    Provide helpful, accurate, and concise responses.\"\"\",
    tools=[process_request]
)

if __name__ == "__main__":
    print(f"🤖 {suggested_name.replace('-', ' ').title()} Ready!")
    print("Type 'exit' to quit\\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break

        response = agent.input(user_input)
        print(f"Agent: {{response}}\\n")
"""

    return agent_code, suggested_name


def generate_custom_template(description: str, api_key: str) -> str:
    """Generate custom agent template using AI.

    This is a placeholder - actual implementation would call AI API.
    """
    # TODO: Implement actual AI generation
    return f"""# Custom Agent Generated from: {description}

from connectonion import Agent

def custom_tool(param: str) -> str:
    '''Custom tool for: {description}'''
    return f"Processing: {{param}}"

agent = Agent(
    name="custom_agent",
    system_prompt="You are a custom agent designed for: {description}",
    tools=[custom_tool]
)

if __name__ == "__main__":
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'quit':
            break
        response = agent.input(user_input)
        print(f"Agent: {{response}}")
"""


def is_directory_empty(directory: str) -> bool:
    """Check if a directory is empty (ignoring .git directory)."""
    contents = os.listdir(directory)
    # Ignore '.', '..', and '.git' directory
    meaningful_contents = [item for item in contents if item not in ['.', '..', '.git']]
    return len(meaningful_contents) == 0


def is_special_directory(directory: str) -> bool:
    """Check if directory is a special system directory."""
    abs_path = os.path.abspath(directory)

    if abs_path == os.path.expanduser("~"):
        return True
    if abs_path == "/":
        return True
    if "/tmp" in abs_path or "temp" in abs_path.lower():
        return False

    system_dirs = ["/usr", "/etc", "/bin", "/sbin", "/lib", "/opt"]
    for sys_dir in system_dirs:
        if abs_path.startswith(sys_dir + "/") or abs_path == sys_dir:
            return True

    return False


def get_special_directory_warning(directory: str) -> str:
    """Get warning message for special directories."""
    abs_path = os.path.abspath(directory)

    if abs_path == os.path.expanduser("~"):
        return "⚠️  You're in your HOME directory. Consider creating a project folder first."
    elif abs_path == "/":
        return "⚠️  You're in the ROOT directory. This is not recommended!"
    elif any(abs_path.startswith(d) for d in ["/usr", "/etc", "/bin", "/sbin", "/lib", "/opt"]):
        return "⚠️  You're in a SYSTEM directory. This could affect system files!"

    return ""


GITIGNORE_CONTENT = """\
# ConnectOnion
.env*
.git/
.co/keys/
.co/cache/
.co/logs/
.co/history/
.co/docs/
*.py[cod]
__pycache__/
node_modules/
dist/
build/
todo.md
"""

PROVIDER_TO_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "grok": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openonion": "OPENONION_API_KEY",
}


def copy_docs(co_dir: Path) -> bool:
    """Copy documentation to .co/docs/. Returns True if docs were copied."""
    docs_dir = co_dir / "docs"
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(exist_ok=True)

    docs_source = get_docs_source()

    if docs_source.exists() and docs_source.is_dir():
        for item in docs_source.iterdir():
            if item.name.startswith('.') or item.name == 'archive':
                continue
            dest = docs_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        return True
    else:
        console.print(f"[yellow]⚠️  Warning: Documentation not found at {docs_source}[/yellow]")
        return False


# The name in host.yaml becomes a DNS label and a Docker image tag when the
# project is deployed, so `co deploy` and the backend both reject anything
# outside this set. Kept here because host.yaml is written here.
DEPLOY_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")


def normalize_deploy_name(name: str) -> Optional[str]:
    """Nearest deployable form of `name`, or None if nothing usable is left."""
    if DEPLOY_NAME_PATTERN.match(name or ""):
        return name
    candidate = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:39].rstrip("-")
    return candidate if DEPLOY_NAME_PATTERN.match(candidate) else None


def create_host_yaml(co_dir: Path, project_name: str) -> bool:
    """Create .co/host.yaml from template. Returns True if created, False if already exists."""
    host_yaml_path = co_dir / "host.yaml"
    if host_yaml_path.exists():
        return False

    template_path = Path(__file__).parent.parent.parent / "network" / "host" / "host.yaml"
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # A directory name is chosen for people, not for DNS — `co init` inside
    # "My_Agent" would otherwise write a name that can never deploy. Adjust it
    # here rather than refusing to create the project, and say so, since the
    # folder keeps its own name either way.
    deploy_name = normalize_deploy_name(project_name) or "agent"
    if deploy_name != project_name:
        console.print(
            f"  [yellow]Deployment name set to[/yellow] {deploy_name} "
            f"[dim](from '{project_name}'; must be lowercase letters, digits, and hyphens)[/dim]"
        )

    project_header = f"""name: {deploy_name}
entrypoint: agent.py
"""
    with open(host_yaml_path, "w", encoding='utf-8') as f:
        f.write(project_header + template_content)

    console.print(f"  [green]Created[/green] .co/host.yaml")
    return True


def setup_gitignore(project_dir: Path) -> Optional[str]:
    """Write .gitignore. Returns a description of what was done, or None.

    Written whether or not this is a git repo yet, because the ordinary order
    is the other way round:

        co create my-agent      # .env: OPENONION_API_KEY, CO_INVITE_CODE
        cd my-agent
        git init && git add . && git commit

    A project is made first and versioned once it works. Waiting for `.git` to
    exist meant the file that excludes `.env` was never written, and `git add .`
    took the agent's API token and the code that lets a stranger onboard.

    An unused .gitignore in a directory that never becomes a repo costs a few
    bytes. A missing one costs a published token, and the recovery is rotating
    every key in the file.
    """
    gitignore_path = project_dir / ".gitignore"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding='utf-8')
        if "# ConnectOnion" not in existing:
            with open(gitignore_path, "a", encoding='utf-8') as f:
                f.write("\n" + GITIGNORE_CONTENT)
            return ".gitignore (updated)"
        return None
    else:
        gitignore_path.write_text(GITIGNORE_CONTENT, encoding='utf-8')
        return ".gitignore"


def print_resources():
    """Print the standard resources/links block."""
    console.print("[bold cyan]📚 Resources:[/bold cyan]")
    console.print(f"   Docs    [dim]→[/dim] [link=https://docs.connectonion.com][blue]https://docs.connectonion.com[/blue][/link]")
    console.print(f"   Discord [dim]→[/dim] [link=https://discord.gg/4xfD9k8AUF][blue]https://discord.gg/4xfD9k8AUF[/blue][/link]")
    console.print(f"   GitHub  [dim]→[/dim] [link=https://github.com/openonion/connectonion][blue]https://github.com/openonion/connectonion[/blue][/link] [dim](⭐ star us!)[/dim]")
    console.print()


def load_api_key() -> Optional[str]:
    """Load OPENONION_API_KEY from environment.

    Checks in order:
    1. Environment variable
    2. Local .env file
    3. Global ~/.co/keys.env file

    Returns:
        API key if found, None otherwise
    """
    from dotenv import load_dotenv

    if api_key := os.getenv("OPENONION_API_KEY"):
        return api_key

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)
            if api_key := os.getenv("OPENONION_API_KEY"):
                return _token_for_this_account(api_key)
    return None


def account_in_token(token: str) -> Optional[str]:
    """The public key a JWT claims, read without verifying it.

    Not authentication — the server does that. This is only to notice that the
    token in hand names a different account than the key on disk, which the
    server cannot tell us until we have already asked it the wrong question.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)          # base64url, padding stripped
    try:
        return json.loads(base64.urlsafe_b64decode(payload)).get("public_key")
    except (ValueError, binascii.Error):
        return None


def _token_for_this_account(token: str) -> str:
    """Re-authenticate when the stored token names an account we are not.

    `co server new` and `co deploy` bill whatever the token says; `co status`
    signs fresh and reads the key on disk. After `co account migrate` those are
    two different accounts, and nothing fails — `/api/v1/auth` creates an
    account for any key that authenticates, so the old address quietly becomes a
    fresh, empty, working one. The operator sees a balance that is not theirs
    and spends credit they did not migrate. One $180 server was bought that way.

    The CLI holds the signing key, so it can see the mismatch itself rather than
    waiting for a balance to look wrong. Cheap: a local decode, and a network
    call only when the two disagree.
    """
    from .auth_commands import authenticate

    co_dir = Path.home() / ".co"
    identity = address.load(co_dir)
    if not identity:
        return token

    claimed = account_in_token(token)
    if not claimed or claimed == identity["address"]:
        return token

    console.print(f"[dim]Your saved token is for {claimed[:16]}…, but this "
                  f"machine is {identity['address'][:16]}…. "
                  f"Authenticating again.[/dim]")
    if authenticate(co_dir, save_to_project=False, quiet=True):
        from dotenv import load_dotenv
        load_dotenv(co_dir / "keys.env", override=True)
        return os.getenv("OPENONION_API_KEY", token)
    return token


def upsert_env(env_path: Path, updates: dict, *, strip_prefix: str = None) -> None:
    """Read .env, replace/append key=value pairs, write back with 0600.

    Args:
        env_path: Path to .env file
        updates: {KEY: value} to upsert. None values are skipped.
        strip_prefix: Remove ALL lines starting with this prefix first
                      (for GOOGLE_*, MICROSOFT_* OAuth credential replacement)
    """
    # Filter out None values
    updates = {k: v for k, v in updates.items() if v is not None}

    lines = []
    found = set()

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines(keepends=True):
            stripped = line.strip()
            if strip_prefix and stripped.startswith(strip_prefix):
                continue
            if '=' in stripped and not stripped.startswith('#'):
                key = stripped.split('=')[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}\n")
                    found.add(key)
                    continue
            lines.append(line)

    # A file whose last line has no newline would otherwise get the first
    # appended key glued onto it (FOO=barBAZ=qux).
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    for key, value in updates.items():
        if key not in found:
            lines.append(f"{key}={value}\n")

    env_path.write_text(''.join(lines), encoding="utf-8")
    if sys.platform != 'win32':
        env_path.chmod(0o600)


def ensure_global_config() -> None:
    """Ensure ~/.co/ exists with global identity (keys + keys.env).

    Creates the global config directory, generates an Ed25519 keypair,
    and writes keys.env with AGENT_CONFIG_PATH and AGENT_ADDRESS.
    No-op if ~/.co/keys/agent.key already exists.
    """
    global_dir = Path.home() / ".co"
    key_file = global_dir / "keys" / "agent.key"

    # If keys exist, already initialized
    if key_file.exists():
        return

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

    # Create keys.env with config path and agent address
    keys_env = global_dir / "keys.env"
    if not keys_env.exists():
        with open(keys_env, 'w', encoding='utf-8') as f:
            f.write(f"AGENT_CONFIG_PATH={global_dir}\n")
            f.write(f"AGENT_ADDRESS={addr_data['address']}\n")
            f.write("# Your agent address (Ed25519 public key) is used for:\n")
            f.write("#   - Secure agent communication (encrypt/decrypt with private key)\n")
            f.write("#   - Authentication with OpenOnion managed LLM provider\n")
            f.write(f"#   - Email address: {addr_data['address'][:10]}@mail.openonion.ai\n")
        if sys.platform != 'win32':
            os.chmod(keys_env, 0o600)  # Read/write for owner only (Unix/Mac only)
    else:
        # keys.env exists but agent.key was missing — update address to match new keypair
        lines = []
        config_path_found = False
        address_updated = False
        for line in keys_env.read_text(encoding="utf-8").splitlines(keepends=True):
            if line.strip().startswith('AGENT_ADDRESS='):
                lines.append(f"AGENT_ADDRESS={addr_data['address']}\n")
                address_updated = True
            elif line.strip().startswith('AGENT_CONFIG_PATH='):
                config_path_found = True
                lines.append(line)
            else:
                lines.append(line)
        if not config_path_found:
            lines.insert(0, f"AGENT_CONFIG_PATH={global_dir}\n")
        if not address_updated:
            lines.append(f"AGENT_ADDRESS={addr_data['address']}\n")
        keys_env.write_text(''.join(lines), encoding="utf-8")
        if sys.platform != 'win32':
            os.chmod(keys_env, 0o600)
    console.print(f"  ✓ Created ~/.co/keys.env")


# Export shared utilities for use by init.py and create.py
__all__ = [
    'GITIGNORE_CONTENT',
    'PROVIDER_TO_ENV',
    'copy_docs',
    'create_host_yaml',
    'normalize_deploy_name',
    'DEPLOY_NAME_PATTERN',
    'setup_gitignore',
    'print_resources',
    'load_api_key',
    'upsert_env',
    'ensure_global_config',
    'LoadingAnimation',
    'validate_project_name',
    'get_special_directory_warning',
    'is_special_directory',
    'is_directory_empty',
    'check_environment_for_api_keys',
    'detect_api_provider',
    'configure_env_for_provider',
    'api_key_setup_menu',
    'get_template_info',
    'unknown_template_message',
    'get_template_suggested_name',
    'get_template_preview',
    'interactive_menu',
    'show_progress',
    'generate_custom_template',
    'generate_custom_template_with_name',
    'get_docs_source',
]

# All the handle_init and handle_create code has been moved to init.py and create.py
# This file now only contains shared utilities
