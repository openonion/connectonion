"""Main CLI entry point for ConnectOnion."""

import os
import sys
import shutil
import toml
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from .. import __version__


def is_directory_empty(directory: str) -> bool:
    """Check if a directory is empty (only . and .. allowed)."""
    try:
        contents = os.listdir(directory)
        # Filter out . and .. which are always present
        meaningful_contents = [item for item in contents if item not in ['.', '..']]
        return len(meaningful_contents) == 0
    except (OSError, FileNotFoundError):
        return True


def is_special_directory(directory: str) -> bool:
    """Check if directory is a special system directory that should warn user."""
    abs_path = os.path.abspath(directory)
    
    # Home directory
    if abs_path == os.path.expanduser("~"):
        return True
    
    # Root directory
    if abs_path == "/":
        return True
    
    # Skip temp directories (common in tests)
    if "/tmp" in abs_path or "temp" in abs_path.lower():
        return False
    
    # System directories
    system_dirs = ["/usr", "/etc", "/bin", "/sbin", "/lib", "/opt"]
    for sys_dir in system_dirs:
        if abs_path.startswith(sys_dir + "/") or abs_path == sys_dir:
            return True
    
    return False


def get_special_directory_warning(directory: str) -> Optional[str]:
    """Get appropriate warning message for special directories."""
    abs_path = os.path.abspath(directory)
    
    if abs_path == os.path.expanduser("~"):
        return "⚠️  You're in your home directory. This will add ConnectOnion files to ~/"
    
    if abs_path == "/":
        return "⚠️  You're in the root directory! This is not recommended."
    
    # Skip temp directories (common in tests)
    if "/tmp" in abs_path or "temp" in abs_path.lower():
        return None
    
    system_dirs = ["/usr", "/etc", "/bin", "/sbin", "/lib", "/opt"]
    for sys_dir in system_dirs:
        if abs_path.startswith(sys_dir + "/") or abs_path == sys_dir:
            return f"⚠️  You're in a system directory ({sys_dir}). This is not recommended."
    
    return None


def get_template_content(template_name: str, file_type: str) -> str:
    """Get content for template files."""
    # Get template files from cli/templates folder
    cli_dir = Path(__file__).parent
    template_dir = cli_dir / "templates"
    
    # Map template combinations to file names
    template_map = {
        ("meta-agent", "agent"): "meta_agent.py",
        ("meta-agent", "prompt"): "meta_prompt.md",
        ("basic", "agent"): "meta_agent.py",  # Alias for backward compatibility
        ("basic", "prompt"): "meta_prompt.md",  # Alias for backward compatibility
        ("playwright", "agent"): "playwright_agent.py",
        ("playwright", "prompt"): "playwright_prompt.md",
    }
    
    # Shared files (used across all templates)
    shared_files = {
        "env": ".env.example",
        "gitignore": ".gitignore",
    }
    
    # Determine which file to read
    template_file = None
    
    # Check template-specific files
    if (template_name, file_type) in template_map:
        template_file = template_dir / template_map[(template_name, file_type)]
    # Check shared files
    elif file_type in shared_files:
        template_file = template_dir / shared_files[file_type]
    # Default prompt for unknown templates
    elif file_type == "prompt":
        template_file = template_dir / "meta_prompt.md"
    
    # Try to read template file
    if template_file and template_file.exists():
        try:
            return template_file.read_text()
        except Exception as e:
            print(f"Warning: Could not read template file {template_file}: {e}")
    
    # Return empty string if no template found
    return ""


def get_connectonion_docs() -> str:
    """Get ConnectOnion documentation content for embedding in projects."""
    # Read from the embedded docs.md file
    # This file is included in the package and works even when installed via pip
    docs_path = Path(__file__).parent / "docs.md"
    
    try:
        return docs_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        # Fallback if docs.md is missing
        return """# ConnectOnion Reference

ConnectOnion is a Python framework for creating AI agents with tools.

For full documentation, visit: https://github.com/connectonion/connectonion
"""


def create_co_metadata(directory: str, template: str = "basic") -> None:
    """Create .co directory with metadata and documentation."""
    co_dir = os.path.join(directory, ".co")
    os.makedirs(co_dir, exist_ok=True)
    
    # Create docs directory
    docs_dir = os.path.join(co_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    
    # Save ConnectOnion documentation
    docs_file = os.path.join(docs_dir, "connectonion.md")
    docs_content = get_connectonion_docs()
    with open(docs_file, "w") as f:
        f.write(docs_content)
    
    # Create config.toml with better structure
    config = {
        "project": {
            "name": os.path.basename(directory) or "connectonion-agent",
            "created": datetime.now().isoformat(),
            "framework_version": __version__,
        },
        "cli": {
            "version": "1.0.0",
            "command": f"co init --template {template}",
            "template": template,
        },
        "agent": {
            "default_model": "gpt-4",
            "max_iterations": 10,
        },
        "docs": {
            "version": "1.0.0",
            "embedded": True,
        }
    }
    
    config_file = os.path.join(co_dir, "config.toml")
    with open(config_file, "w") as f:
        toml.dump(config, f)


def create_file_if_not_exists(file_path: str, content: str, force: bool = False) -> bool:
    """
    Create a file with content if it doesn't exist.
    
    Returns:
        True if file was created, False if it already existed
    """
    if os.path.exists(file_path) and not force:
        return False
    
    with open(file_path, "w") as f:
        f.write(content)
    return True


def append_to_gitignore(directory: str, content: str) -> None:
    """Append ConnectOnion-specific entries to existing .gitignore."""
    gitignore_path = os.path.join(directory, ".gitignore")
    
    if os.path.exists(gitignore_path):
        # Read existing content
        with open(gitignore_path, "r") as f:
            existing_content = f.read()
        
        # Check if our content is already there
        if "# ConnectOnion" not in existing_content:
            # Append our content
            with open(gitignore_path, "a") as f:
                if not existing_content.endswith("\n"):
                    f.write("\n")
                f.write(content)
    else:
        # Create new .gitignore
        with open(gitignore_path, "w") as f:
            f.write(content.lstrip())


@click.group()
@click.version_option(version=__version__)
def cli():
    """ConnectOnion - A simple Python framework for creating AI agents."""
    pass


@cli.command()
@click.option('--template', '-t', default='meta-agent', 
              type=click.Choice(['meta-agent', 'playwright', 'basic']),
              help='Template to use for the agent (default: meta-agent)')
@click.option('--with-examples', is_flag=True,
              help='Include additional example tools')
@click.option('--force', is_flag=True,
              help='Overwrite existing files')
def init(template: str, with_examples: bool, force: bool):
    """Initialize a ConnectOnion project in the current directory."""
    current_dir = os.getcwd()
    
    # Map "basic" to "meta-agent" for backward compatibility
    if template == "basic":
        template = "meta-agent"
    
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
    
    # Files to create
    files_created = []
    files_skipped = []
    
    try:
        # Create agent.py
        agent_content = get_template_content(template, "agent")
        agent_path = os.path.join(current_dir, "agent.py")
        
        if create_file_if_not_exists(agent_path, agent_content, force):
            files_created.append("agent.py")
        else:
            files_skipped.append("agent.py (already exists)")
        
        # Create prompt.md - ConnectOnion best practice: system prompts in markdown
        prompt_content = get_template_content(template, "prompt")
        prompt_path = os.path.join(current_dir, "prompt.md")
        
        if create_file_if_not_exists(prompt_path, prompt_content, force):
            files_created.append("prompt.md")
        else:
            files_skipped.append("prompt.md (already exists)")
        
        # Create .env.example
        env_content = get_template_content(template, "env")
        env_path = os.path.join(current_dir, ".env.example")
        
        if create_file_if_not_exists(env_path, env_content, force):
            files_created.append(".env.example")
        else:
            files_skipped.append(".env.example (already exists)")
        
        # Create .co metadata with docs
        create_co_metadata(current_dir, template)
        files_created.append(".co/")
        files_created.append(".co/docs/connectonion.md")
        
        # Handle .gitignore if in git repo
        if os.path.exists(os.path.join(current_dir, ".git")):
            gitignore_content = get_template_content(template, "gitignore")
            append_to_gitignore(current_dir, gitignore_content)
            gitignore_path = os.path.join(current_dir, ".gitignore")
            if os.path.exists(gitignore_path):
                files_created.append(".gitignore (updated)")
            else:
                files_created.append(".gitignore")
        
        # Add example tools if requested
        if with_examples:
            examples_dir = os.path.join(current_dir, "examples")
            os.makedirs(examples_dir, exist_ok=True)
            
            # Copy examples_tools.py
            examples_content = get_template_content("basic", "examples")
            if not examples_content:
                # Fallback content
                examples_content = "# Additional example tools would go here\\n"
            
            examples_path = os.path.join(examples_dir, "tools.py")
            if create_file_if_not_exists(examples_path, examples_content, force):
                files_created.append("examples/tools.py")
        
        # Show results
        click.echo("\\n✅ ConnectOnion project initialized!")
        
        if files_created:
            click.echo("\\nCreated:")
            for file in files_created:
                # Add descriptions for each file type
                if file == "agent.py":
                    click.echo(f"   ├── {file} (Agent implementation with tools)")
                elif file == "prompt.md":
                    click.echo(f"   ├── {file} (System prompt - edit this to customize agent behavior)")
                elif file == ".env.example":
                    click.echo(f"   ├── {file} (API key configuration template)")
                elif file == ".co/":
                    click.echo(f"   ├── {file} (ConnectOnion metadata)")
                elif file == ".co/docs/connectonion.md":
                    click.echo(f"   ├── {file} (ConnectOnion reference documentation)")
                elif ".gitignore" in file:
                    click.echo(f"   ├── {file} (Git ignore rules)")
                elif "examples/" in file:
                    click.echo(f"   ├── {file} (Additional example tools)")
                else:
                    click.echo(f"   ├── {file}")
        
        if files_skipped:
            click.echo("\\nSkipped (already exists):")
            for file in files_skipped:
                click.echo(f"   ├── {file}")
        
        # Show next steps
        click.echo(f"\\n🚀 Next steps:")
        click.echo("   1. Copy .env.example to .env and add your API keys")
        click.echo("   2. Edit prompt.md to customize your agent's personality")
        click.echo("   3. Run: python agent.py")
        click.echo("   4. Start building your agent!")
        
        if template != "meta-agent":
            click.echo(f"\\n💡 You're using the '{template}' template with specialized tools.")
        
    except PermissionError:
        click.echo("❌ Error: Permission denied. Cannot write to this directory.")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error initializing project: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    cli()