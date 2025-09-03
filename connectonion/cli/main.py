"""Main CLI entry point for ConnectOnion - Simplified version."""

import os
import shutil
import toml
from datetime import datetime
from pathlib import Path

import click

from .. import __version__
from .. import address


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
@click.option('--template', '-t', default='meta-agent', 
              type=click.Choice(['meta-agent', 'playwright']),
              help='Template to use for the agent (default: meta-agent)')
@click.option('--force', is_flag=True,
              help='Overwrite existing files')
def init(template: str, force: bool):
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
                # Copy file
                if dest_path.exists() and not force:
                    files_skipped.append(f"{item.name} (already exists)")
                else:
                    shutil.copy2(item, dest_path)
                    files_created.append(item.name)
        except Exception as e:
            click.echo(f"❌ Error copying {item.name}: {e}")
    
    # Create .co directory with metadata
    co_dir = Path(current_dir) / ".co"
    co_dir.mkdir(exist_ok=True)
    
    # Create docs directory and copy documentation
    docs_dir = co_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Copy ConnectOnion documentation if it exists in template
    template_docs = template_dir / "connectonion.md"
    if template_docs.exists():
        shutil.copy2(template_docs, docs_dir / "connectonion.md")
        files_created.append(".co/docs/connectonion.md")
    
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
            elif file == ".env.example":
                click.echo(f"  • {file} - Environment variables template")
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
    click.echo("1. Copy .env.example to .env and add your OpenAI API key:")
    click.echo("   cp .env.example .env")
    click.echo("   # Then edit .env to add your key")
    click.echo("\n2. Install dependencies:")
    click.echo("   pip install python-dotenv")
    if template == "playwright":
        click.echo("   pip install playwright")
        click.echo("   playwright install")
    click.echo("\n3. Run your agent:")
    click.echo("   python agent.py")
    click.echo("\n📚 Documentation: https://github.com/wu-changxing/connectonion")
    click.echo("💬 Discord: https://discord.gg/4xfD9k8AUF")


# Entry points for both 'co' and 'connectonion' commands
def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()