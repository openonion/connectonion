"""Main CLI entry point for ConnectOnion - Simplified version."""

import os
import shutil
import toml
from datetime import datetime
from pathlib import Path

import click

from .. import __version__
from .. import address

import re
from typing import Optional, Tuple


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
            'model': 'gpt-4o-mini'
        },
        'anthropic': {
            'var': 'ANTHROPIC_API_KEY', 
            'model': 'claude-3-haiku-20240307'
        },
        'google': {
            'var': 'GOOGLE_API_KEY',
            'model': 'gemini-pro'
        },
        'groq': {
            'var': 'GROQ_API_KEY',
            'model': 'llama3-70b-8192'
        }
    }
    
    config = configs.get(provider, configs['openai'])
    
    return f"""# {provider.title()} API Configuration
{config['var']}={api_key}

# Model Configuration
MODEL={config['model']}

# Optional: Override default settings
# MAX_TOKENS=2000
# TEMPERATURE=0.7
"""


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


@click.group()
@click.version_option(version=__version__)
def cli():
    """ConnectOnion - A simple Python framework for creating AI agents."""
    pass


@cli.command()
@click.option('--ai/--no-ai', default=None,
              help='Enable or disable AI features')
@click.option('--key', help='API key for AI provider')
@click.option('--template', '-t',
              type=click.Choice(['minimal', 'web-research', 'custom', 'meta-agent', 'playwright']),
              help='Template to use')
@click.option('--description', help='Description for custom template (requires AI)')
@click.option('--yes', '-y', is_flag=True, help='Skip all prompts, use defaults')
@click.option('--force', is_flag=True,
              help='Overwrite existing files')
def init(ai: Optional[bool], key: Optional[str], template: Optional[str],
         description: Optional[str], yes: bool, force: bool):
    """Initialize a ConnectOnion project in the current directory."""
    current_dir = os.getcwd()
    
    # Check for special directories
    warning = get_special_directory_warning(current_dir)
    if warning:
        click.echo(warning)
        if not click.confirm("Continue anyway?"):
            click.echo("Initialization cancelled.")
            return
    
    # Check if directory is empty
    if not is_directory_empty(current_dir) and not force:
        click.echo("⚠️  Directory not empty. Add ConnectOnion to existing project?")
        if not click.confirm("Continue?"):
            click.echo("Initialization cancelled.")
            return
    
    # Get template directory
    cli_dir = Path(__file__).parent
    template_dir = cli_dir / "templates" / template
    
    if not template_dir.exists():
        click.echo(f"❌ Template '{template}' not found!")
        return
    
    # Copy all files from template directory
    files_created = []
    files_skipped = []
    
    for item in template_dir.iterdir():
        # Skip hidden files except .env.example
        if item.name.startswith('.') and item.name != '.env.example':
            continue
            
        dest_path = Path(current_dir) / item.name
        
        try:
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
        except Exception as e:
            click.echo(f"❌ Error copying {item.name}: {e}")
    
    # Create .env file directly (not .env.example)
    env_path = Path(current_dir) / ".env"
    if not env_path.exists() or force:
        env_content = """# OpenAI API Key
OPENAI_API_KEY=sk-your-api-key-here

# Optional: Override default model
# MODEL=gpt-4o-mini
"""
        env_path.write_text(env_content)
        files_created.append(".env")
    else:
        files_skipped.append(".env (already exists)")
    
    # Create .co directory with metadata
    co_dir = Path(current_dir) / ".co"
    co_dir.mkdir(exist_ok=True)
    
    # Create docs directory and copy documentation
    docs_dir = co_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Copy ConnectOnion documentation if it exists in template
    template_docs = template_dir / "connectonion.md"
    if template_docs.exists():
        shutil.copy2(template_docs, docs_dir / "co-vibe-coding-all-in-one.md")
        files_created.append(".co/docs/co-vibe-coding-all-in-one.md")
    
    # Generate agent address silently
    try:
        # Try to load existing keys first
        existing_address = address.load(co_dir)
        if existing_address:
            addr_data = existing_address
            # Don't show any message - completely silent
        else:
            # Generate new keys
            addr_data = address.generate()
            # Save keys to .co/keys/
            address.save(addr_data, co_dir)
            files_created.append(".co/keys/")
    except ImportError:
        # If cryptography libraries not installed, generate placeholder
        addr_data = {
            "address": "0x" + "0" * 64,
            "short_address": "0x0000...0000"
        }
        # Silent fallback - no message
    
    # Create config.toml
    config = {
        "project": {
            "name": os.path.basename(current_dir) or "connectonion-agent",
            "created": datetime.now().isoformat(),
            "framework_version": __version__,
        },
        "cli": {
            "version": "1.0.0",
            "command": f"co init --template {template}",
            "template": template,
        },
        "agent": {
            "address": addr_data["address"],
            "short_address": addr_data["short_address"],
            "created_at": datetime.now().isoformat(),
            "algorithm": "ed25519",
            "default_model": "o4-mini" if template == "meta-agent" else "gpt-4o-mini",
            "max_iterations": 15 if template == "meta-agent" else 10,
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
    
    # Show results
    click.echo("\n✅ ConnectOnion project initialized!")
    
    if files_created:
        click.echo("\nCreated:")
        for file in files_created:
            if file == "agent.py":
                click.echo(f"  • {file} - Main agent implementation")
            elif file == "prompts/":
                click.echo(f"  • {file} - System prompts directory")
            elif file == ".env":
                click.echo(f"  • {file} - Environment configuration (add your API key)")
            elif file == "README.md":
                click.echo(f"  • {file} - Project documentation")
            elif file == ".co/":
                click.echo(f"  • {file} - ConnectOnion metadata")
            else:
                click.echo(f"  • {file}")
    
    if files_skipped:
        click.echo("\nSkipped (already exist):")
        for file in files_skipped:
            click.echo(f"  • {file}")
    
    # Next steps
    click.echo("\n📝 Next steps:")
    click.echo("1. Add your OpenAI API key to .env:")
    click.echo("   Open .env and replace 'sk-your-api-key-here' with your actual key")
    click.echo("\n2. Install dependencies:")
    click.echo("   pip install python-dotenv")
    if template == "playwright":
        click.echo("   pip install playwright")
        click.echo("   playwright install")
    click.echo("\n3. Run your agent:")
    click.echo("   python agent.py")
    click.echo("\n📚 Documentation: https://github.com/wu-changxing/connectonion")
    click.echo("💬 Discord: https://discord.gg/4xfD9k8AUF")


@cli.command()
@click.argument('name', required=False)
@click.option('--ai/--no-ai', default=None, 
              help='Enable or disable AI features')
@click.option('--key', help='API key for AI provider')
@click.option('--template', '-t',
              type=click.Choice(['minimal', 'web-research', 'custom', 'meta-agent', 'playwright']),
              help='Template to use')
@click.option('--description', help='Description for custom template (requires AI)')
@click.option('--yes', '-y', is_flag=True, help='Skip all prompts, use defaults')
def create(name: Optional[str], ai: Optional[bool], key: Optional[str], 
           template: Optional[str], description: Optional[str], yes: bool):
    """Create a new ConnectOnion project in a new directory."""
    
    # Get project name
    if not name and not yes:
        name = click.prompt("Project name", default="my-agent")
    elif not name:
        name = "my-agent"
    
    # Check if directory exists
    project_dir = Path(name)
    if project_dir.exists():
        click.echo(f"❌ Directory '{name}' already exists!")
        return
    
    # Get AI preference
    if ai is None and not yes:
        ai = click.confirm("Enable AI features?", default=True)
    elif ai is None:
        ai = False
    
    # Get API key if AI enabled
    api_key = key
    provider = None
    if ai and not api_key and not yes:
        api_key = click.prompt("Paste your API key (or Enter to skip)", 
                              default="", hide_input=True, show_default=False)
        if api_key:
            provider, key_type = detect_api_provider(api_key)
            click.echo(f"  ✓ Detected {provider.title()} API key")
    elif ai and api_key:
        provider, key_type = detect_api_provider(api_key)
    
    # Get template choice
    if not template and not yes:
        templates = ['minimal', 'web-research']
        if ai:
            templates.append('custom')
        
        # Show template menu
        click.echo("\nChoose a template:")
        for i, t in enumerate(templates):
            descriptions = {
                'minimal': 'Simple starting point',
                'web-research': 'Data analysis & web scraping',
                'custom': 'AI generates based on your needs'
            }
            marker = "❯" if i == 0 else " "
            click.echo(f"  {marker} {t.title()} - {descriptions.get(t, '')}")
        
        template = click.prompt("Template", 
                               type=click.Choice(templates),
                               default=templates[0])
    elif not template:
        template = 'minimal'
    
    # Handle custom template
    custom_code = None
    if template == 'custom':
        if not ai:
            click.echo("❌ Custom template requires AI to be enabled!")
            return
        
        if not description and not yes:
            description = click.prompt("Describe what you want to build")
        elif not description:
            description = "A general purpose agent"
        
        click.echo("⚡ Generating custom template with AI...")
        custom_code = generate_custom_template(description, api_key or "")
    
    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Get template files
    cli_dir = Path(__file__).parent
    
    # Map new template names to existing ones for backward compatibility
    template_map = {
        'minimal': 'meta-agent',  # Use meta-agent as minimal for now
        'web-research': 'playwright',  # Use playwright as web-research for now
        'custom': 'meta-agent'  # Base custom on meta-agent
    }
    
    actual_template = template_map.get(template, template)
    template_dir = cli_dir / "templates" / actual_template
    
    if not template_dir.exists() and template != 'custom':
        click.echo(f"❌ Template '{template}' not found!")
        shutil.rmtree(project_dir)
        return
    
    # Copy template files
    files_created = []
    
    if template != 'custom':
        for item in template_dir.iterdir():
            if item.name.startswith('.') and item.name != '.env.example':
                continue
            
            dest_path = project_dir / item.name
            
            try:
                if item.is_dir():
                    shutil.copytree(item, dest_path)
                    files_created.append(f"{item.name}/")
                else:
                    if item.name != '.env.example':
                        shutil.copy2(item, dest_path)
                        files_created.append(item.name)
            except Exception as e:
                click.echo(f"❌ Error copying {item.name}: {e}")
    
    # Create custom agent.py if custom template
    if custom_code:
        agent_file = project_dir / "agent.py"
        agent_file.write_text(custom_code)
        files_created.append("agent.py")
    
    # Create .co directory
    co_dir = project_dir / ".co"
    co_dir.mkdir(exist_ok=True)
    
    # Create docs directory
    docs_dir = co_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Copy documentation
    if template_dir and template_dir.exists():
        template_docs = template_dir / "connectonion.md"
        if template_docs.exists():
            shutil.copy2(template_docs, docs_dir / "co-vibe-coding-all-in-one.md")
            files_created.append(".co/docs/co-vibe-coding-all-in-one.md")
    
    # Generate agent keys
    try:
        addr_data = address.generate()
        address.save(addr_data, co_dir)
        files_created.append(".co/keys/")
    except ImportError:
        addr_data = {
            "address": "0x" + "0" * 64,
            "short_address": "0x0000...0000"
        }
    
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
    
    # Create .env file
    env_path = project_dir / ".env"
    if api_key and provider:
        env_content = configure_env_for_provider(provider, api_key)
    else:
        env_content = """# OpenAI API Key
OPENAI_API_KEY=sk-your-api-key-here

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
    
    # Success message
    click.echo(f"\n✅ Created '{name}' with {template.title()} template")
    
    if custom_code and description:
        click.echo("\nYour custom agent includes:")
        click.echo(f"  • Generated from: {description[:50]}...")
    
    click.echo("\nNext steps:")
    click.echo(f"  cd {name}")
    
    if not api_key:
        click.echo("  # Add your API key to .env")
    
    click.echo("  python agent.py")
    
    click.echo("\n📚 Documentation: https://github.com/wu-changxing/connectonion")
    click.echo("💬 Discord: https://discord.gg/4xfD9k8AUF")


# Entry points for both 'co' and 'connectonion' commands
def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()