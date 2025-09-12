"""Main CLI entry point for ConnectOnion - Simplified version."""

import os
import shutil
import toml
from datetime import datetime
from pathlib import Path

import click

from .. import __version__
from .. import address
from .auth_commands import handle_auth, handle_register, do_auth_flow
from .utils import Colors, show_progress, is_directory_empty, get_special_directory_warning, validate_project_name, detect_api_provider, configure_env_for_provider

import re
from typing import Optional, Tuple
import sys
import time


def get_template_preview(template: str) -> str:
    """Get a preview of what the template includes."""
    previews = {
        'minimal': """  📦 Minimal - Simple starting point
    ├── agent.py (50 lines) - Basic agent with example tool
    ├── .env - API key configuration
    ├── README.md - Quick start guide
    └── .co/ - Agent identity & metadata""",
        
        'web-research': """  🔍 Web Research - Data analysis & web scraping
    ├── agent.py (100+ lines) - Agent with web tools
    ├── tools/ - Web scraping & data extraction
    ├── .env - API key configuration
    ├── README.md - Usage examples
    └── .co/ - Agent identity & metadata""",
        
        'custom': """  ✨ Custom - AI generates based on your needs
    ├── agent.py - Tailored to your description
    ├── tools/ - Custom tools for your use case
    ├── .env - API key configuration
    ├── README.md - Custom documentation
    └── .co/ - Agent identity & metadata""",
        
        'meta-agent': """  🤖 Meta-Agent - ConnectOnion development assistant
    ├── agent.py - Advanced agent with llm_do
    ├── prompts/ - System prompts (4 files)
    ├── .env - API key configuration
    ├── README.md - Comprehensive guide
    └── .co/ - Agent identity & metadata""",
        
        'playwright': """  🎭 Playwright - Browser automation
    ├── agent.py - Browser control agent
    ├── prompt.md - System prompt
    ├── .env - API key configuration
    ├── README.md - Setup instructions
    └── .co/ - Agent identity & metadata"""
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
        ('GOOGLE_API_KEY', 'google'),
        ('GEMINI_API_KEY', 'google'),
        ('GROQ_API_KEY', 'groq'),
    ]
    
    for env_var, provider in checks:
        api_key = os.environ.get(env_var)
        if api_key and api_key != 'your-api-key-here' and not api_key.startswith('sk-your'):
            return provider, api_key
    
    return None


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


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option('-b', '--browser', help='Browser command - guide browser to do something (e.g., "screenshot localhost:3000")')
@click.pass_context
def cli(ctx, browser):
    """ConnectOnion - A simple Python framework for creating AI agents."""
    if browser:
        # Handle browser command immediately
        from .browser_agent.browser import execute_browser_command
        result = execute_browser_command(browser)
        # Simply output the agent's natural language response as-is
        click.echo(result)
        ctx.exit(0)
    elif ctx.invoked_subcommand is None:
        # No subcommand and no browser flag, show help
        click.echo(ctx.get_help())


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
    project_name = os.path.basename(current_dir) or "connectonion-agent"
    
    # Welcome banner
    if not yes:
        click.echo(f"\n{Colors.CYAN}{Colors.BOLD}🧅 ConnectOnion Project Initializer{Colors.END}")
        click.echo(f"{Colors.CYAN}{'=' * 40}{Colors.END}")
        click.echo(f"\n📁 Initializing: {Colors.BOLD}{project_name}{Colors.END}")
        click.echo(f"📍 Location: {Colors.BOLD}{current_dir}{Colors.END}\n")
    
    # Check for special directories
    warning = get_special_directory_warning(current_dir)
    if warning:
        click.echo(f"{Colors.YELLOW}{warning}{Colors.END}")
        if not yes and not click.confirm(f"{Colors.YELLOW}Continue anyway?{Colors.END}"):
            click.echo(f"{Colors.YELLOW}Initialization cancelled.{Colors.END}")
            return
    
    # Check if directory is empty
    if not is_directory_empty(current_dir) and not force and not yes:
        click.echo(f"{Colors.YELLOW}⚠️  Directory not empty{Colors.END}")
        existing_files = [f for f in os.listdir(current_dir) 
                         if f not in ['.', '..', '.git', '.gitignore']]
        click.echo(f"{Colors.YELLOW}Existing files: {', '.join(existing_files[:5])}{Colors.END}")
        if len(existing_files) > 5:
            click.echo(f"{Colors.YELLOW}... and {len(existing_files) - 5} more{Colors.END}")
        
        if not click.confirm(f"\n{Colors.YELLOW}Add ConnectOnion to existing project?{Colors.END}"):
            click.echo(f"{Colors.YELLOW}Initialization cancelled.{Colors.END}")
            return
    
    # Get AI preference if not specified
    if ai is None and not yes:
        # Check for environment variables first
        env_result = check_environment_for_api_keys()
        if env_result:
            env_provider, env_key = env_result
            click.echo(f"{Colors.GREEN}✓ Found {env_provider.title()} API key in environment{Colors.END}")
            ai = click.confirm("Enable AI features using this key?", default=True)
            if ai:
                api_key = env_key
                provider = env_provider
            else:
                api_key = None
                provider = None
        else:
            ai = click.confirm("\nEnable AI features?", default=True)
            api_key = None
            provider = None
    elif ai is None:
        ai = False
        api_key = key
        provider = None
    else:
        api_key = key
        provider = None
    
    # Get API key if AI enabled and no key yet
    if ai and not api_key and not yes:
        click.echo(f"\n{Colors.CYAN}📝 API Key Setup{Colors.END}")
        click.echo("Paste your API key (or press Enter to skip):")
        click.echo(f"{Colors.YELLOW}Supported: OpenAI, Anthropic, Google, Groq{Colors.END}")
        api_key = click.prompt("", default="", hide_input=True, show_default=False)
        if api_key:
            provider, key_type = detect_api_provider(api_key)
            click.echo(f"{Colors.GREEN}✓ Detected {provider.title()} API key{Colors.END}")
    elif ai and api_key and not provider:
        provider, key_type = detect_api_provider(api_key)
    
    # Handle backward compatibility for meta-agent and playwright
    if template in ['meta-agent', 'playwright']:
        # Use existing template directly
        pass
    else:
        # Get template choice using new interactive system
        if not template and not yes:
            templates = ['minimal', 'web-research']
            if ai:
                templates.append('custom')
            
            # Show template menu with previews
            click.echo(f"\n{Colors.CYAN}📂 Choose a template:{Colors.END}\n")
            for t in templates:
                click.echo(get_template_preview(t))
                click.echo()  # Add spacing
            
            template = click.prompt(f"\n{Colors.YELLOW}Select template{Colors.END}", 
                                   type=click.Choice(templates),
                                   default=templates[0])
        elif not template:
            template = 'minimal'
    
    # Handle custom template
    custom_code = None
    if template == 'custom':
        if not ai:
            click.echo(f"{Colors.RED}❌ Custom template requires AI to be enabled!{Colors.END}")
            return
        
        if not description and not yes:
            click.echo(f"\n{Colors.CYAN}🤖 Custom Template Generator{Colors.END}")
            description = click.prompt(f"{Colors.YELLOW}Describe what you want to build{Colors.END}")
        elif not description:
            description = "A general purpose agent"
        
        show_progress("Generating custom template with AI", 2.0)
        custom_code = generate_custom_template(description, api_key or "")
        click.echo(f"{Colors.GREEN}✓ Custom template generated{Colors.END}")
    
    # Get template directory
    cli_dir = Path(__file__).parent
    
    # Map new template names to existing ones for backward compatibility
    template_map = {
        'minimal': 'meta-agent',
        'web-research': 'playwright',
        'custom': 'meta-agent'
    }
    
    actual_template = template_map.get(template, template)
    template_dir = cli_dir / "templates" / actual_template
    
    if not template_dir.exists():
        click.echo(f"{Colors.RED}❌ Template '{template}' not found!{Colors.END}")
        return
    
    # Show confirmation summary for init
    if not yes and not force:
        click.echo(f"\n{Colors.CYAN}📋 Initialization Summary{Colors.END}")
        click.echo(f"{Colors.CYAN}{'─' * 40}{Colors.END}")
        click.echo(f"  📁 Project: {Colors.BOLD}{project_name}{Colors.END}")
        click.echo(f"  📦 Template: {Colors.BOLD}{template}{Colors.END}")
        if ai:
            click.echo(f"  🤖 AI: {Colors.GREEN}Enabled{Colors.END} ({provider.title() if provider else 'No key'})")
        else:
            click.echo(f"  🤖 AI: {Colors.YELLOW}Disabled{Colors.END}")
        
        if custom_code and description:
            click.echo(f"  ✨ Custom: {description[:50]}...")
        
        click.echo(f"\n{Colors.CYAN}Files to add:{Colors.END}")
        files_preview = ["agent.py", ".env", ".co/config.toml", ".co/keys/"]
        if template in ['web-research', 'playwright', 'meta-agent']:
            files_preview.append("prompts/" if template == 'meta-agent' else "tools/")
        for f in files_preview:
            click.echo(f"  • {f}")
        
        if not click.confirm(f"\n{Colors.YELLOW}Initialize project?{Colors.END}", default=True):
            click.echo(f"{Colors.YELLOW}Initialization cancelled.{Colors.END}")
            return
    
    # Show progress
    if not yes:
        show_progress("Initializing project", 0.5)
    
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
    
    # Create custom agent.py if custom template
    if custom_code:
        agent_file = Path(current_dir) / "agent.py"
        if not agent_file.exists() or force:
            agent_file.write_text(custom_code)
            files_created.append("agent.py")
    
    # Create .env file with proper API configuration
    env_path = Path(current_dir) / ".env"
    if not env_path.exists() or force:
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
    else:
        files_skipped.append(".env (already exists)")
    
    # Create .co directory with metadata
    co_dir = Path(current_dir) / ".co"
    co_dir.mkdir(exist_ok=True)
    
    # Create docs directory and copy documentation
    docs_dir = co_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Copy VibeCoding principles, docs and contexts all-in-one documentation
    # First try new filename, then fall back to old
    template_docs_new = template_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md"
    template_docs_old = template_dir / "connectonion.md"
    
    if template_docs_new.exists():
        shutil.copy2(template_docs_new, docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md")
        files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")
    elif template_docs_old.exists():
        # Fall back to old file for backward compatibility
        shutil.copy2(template_docs_old, docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md")
        files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")
    
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
            "short_address": "0x0000...0000",
            "email": "0x00000000@mail.openonion.ai"
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
    
    # Show results with beautiful formatting
    click.echo(f"\n{Colors.GREEN}{Colors.BOLD}✅ Project initialized successfully!{Colors.END}")
    click.echo(f"{Colors.GREEN}{'=' * 40}{Colors.END}")
    
    click.echo(f"\n📁 Project: {Colors.BOLD}{project_name}{Colors.END}")
    click.echo(f"📦 Template: {Colors.BOLD}{template.title()}{Colors.END}")
    
    if custom_code and description:
        click.echo(f"\n✨ {Colors.CYAN}Custom agent generated from:{Colors.END}")
        click.echo(f"   {description[:60]}...")
    
    # Show agent address and email
    if 'addr_data' in locals() and addr_data.get('short_address'):
        click.echo(f"\n🔑 Agent address: {Colors.CYAN}{addr_data['short_address']}{Colors.END}")
        if addr_data.get('email'):
            email_status = " (inactive)" if not addr_data.get('email_active', False) else " (active)"
            click.echo(f"📧 Agent email: {Colors.CYAN}{addr_data['email']}{Colors.END}{Colors.YELLOW}{email_status}{Colors.END}")
            
            # Ask if user wants to activate email now
            if not addr_data.get('email_active', False) and not yes:
                click.echo(f"\n{Colors.CYAN}💌 Your agent can send emails!{Colors.END}")
                click.echo(f"   Email address: {Colors.BOLD}{addr_data['email']}{Colors.END}")
                if click.confirm(f"\n{Colors.YELLOW}Would you like to activate your agent's email now?{Colors.END}"):
                    click.echo(f"\n{Colors.CYAN}Launching authentication...{Colors.END}")
                    if do_auth_flow(co_dir):
                        # Email is now activated
                        click.echo(f"{Colors.GREEN}✨ Email activated! Your agent can now send emails.{Colors.END}")
                    else:
                        click.echo(f"{Colors.YELLOW}You can activate later with 'co auth'{Colors.END}")
    
    if files_created:
        click.echo(f"\n{Colors.CYAN}📂 Files created:{Colors.END}")
        for file in files_created:
            if file == "agent.py":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - Main agent implementation")
            elif file == "prompts/":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - System prompts directory")
            elif file == ".env":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - Environment configuration")
            elif file == "README.md":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - Project documentation")
            elif file == ".co/":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - ConnectOnion metadata")
            elif file == ".co/keys/":
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END} - Agent cryptographic keys")
            else:
                click.echo(f"  • {Colors.GREEN}{file}{Colors.END}")
    
    if files_skipped:
        click.echo(f"\n{Colors.YELLOW}📌 Files skipped (already exist):{Colors.END}")
        for file in files_skipped:
            click.echo(f"  • {Colors.YELLOW}{file}{Colors.END}")
    
    # Next steps with color coding
    click.echo(f"\n{Colors.CYAN}🚀 Next steps:{Colors.END}")
    click.echo(f"{Colors.CYAN}{'─' * 40}{Colors.END}")
    
    step = 1
    if not api_key:
        click.echo(f"\n{step}️⃣  Add your API key to .env:")
        click.echo(f"    {Colors.BOLD}nano .env{Colors.END}")
        click.echo(f"    {Colors.YELLOW}# Replace 'sk-your-api-key-here' with your key{Colors.END}")
        step += 1
    
    click.echo(f"\n{step}️⃣  Install dependencies:")
    click.echo(f"    {Colors.BOLD}pip install python-dotenv{Colors.END}")
    step += 1
    
    if template in ['web-research', 'playwright'] or actual_template == "playwright":
        click.echo(f"\n{step}️⃣  Install browser automation:")
        click.echo(f"    {Colors.BOLD}pip install playwright{Colors.END}")
        click.echo(f"    {Colors.BOLD}playwright install{Colors.END}")
        step += 1
    
    click.echo(f"\n{step}️⃣  Run your agent:")
    click.echo(f"    {Colors.BOLD}python agent.py{Colors.END}")
    
    click.echo(f"\n{Colors.CYAN}📚 Resources:{Colors.END}")
    click.echo(f"   Documentation: {Colors.UNDERLINE}https://github.com/wu-changxing/connectonion{Colors.END}")
    click.echo(f"   Discord: {Colors.UNDERLINE}https://discord.gg/4xfD9k8AUF{Colors.END}")
    click.echo()


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
    
    # Welcome banner
    if not yes:
        click.echo(f"\n{Colors.CYAN}{Colors.BOLD}🧅 ConnectOnion Project Creator{Colors.END}")
        click.echo(f"{Colors.CYAN}{'=' * 40}{Colors.END}\n")
    
    # Get and validate project name
    if not name and not yes:
        while True:
            name = click.prompt(f"{Colors.YELLOW}Project name{Colors.END}", default="my-agent")
            is_valid, error_msg = validate_project_name(name)
            if is_valid:
                break
            click.echo(f"{Colors.RED}❌ {error_msg}{Colors.END}")
    elif not name:
        name = "my-agent"
    else:
        # Validate provided name
        is_valid, error_msg = validate_project_name(name)
        if not is_valid:
            click.echo(f"{Colors.RED}❌ {error_msg}{Colors.END}")
            return
    
    # Check if directory exists with better error message
    project_dir = Path(name)
    if project_dir.exists():
        click.echo(f"\n{Colors.RED}❌ Directory '{name}' already exists!{Colors.END}")
        click.echo(f"{Colors.YELLOW}💡 Suggestions:{Colors.END}")
        click.echo(f"   • Use a different name: co create {name}-v2")
        click.echo(f"   • Remove existing directory: rm -rf {name}")
        click.echo(f"   • Initialize existing directory: cd {name} && co init")
        return
    
    # Get AI preference
    if ai is None and not yes:
        # Check for environment variables first
        env_result = check_environment_for_api_keys()
        if env_result:
            env_provider, env_key = env_result
            click.echo(f"\n{Colors.GREEN}✓ Found {env_provider.title()} API key in environment{Colors.END}")
            ai = click.confirm("Enable AI features using this key?", default=True)
            if ai:
                api_key = env_key
                provider = env_provider
            else:
                api_key = None
                provider = None
        else:
            ai = click.confirm("\nEnable AI features?", default=True)
            api_key = None
            provider = None
    elif ai is None:
        ai = False
        api_key = key
        provider = None
    else:
        api_key = key
        provider = None
    
    # Get API key if AI enabled and no key yet
    if ai and not api_key and not yes:
        click.echo(f"\n{Colors.CYAN}📝 API Key Setup{Colors.END}")
        click.echo("Paste your API key (or press Enter to skip):")
        click.echo(f"{Colors.YELLOW}Supported: OpenAI, Anthropic, Google, Groq{Colors.END}")
        api_key = click.prompt("", default="", hide_input=True, show_default=False)
        if api_key:
            provider, key_type = detect_api_provider(api_key)
            click.echo(f"{Colors.GREEN}✓ Detected {provider.title()} API key{Colors.END}")
    elif ai and api_key and not provider:
        provider, key_type = detect_api_provider(api_key)
    
    # Get template choice with preview
    if not template and not yes:
        templates = ['minimal', 'web-research']
        if ai:
            templates.append('custom')
        
        # Show template menu with previews
        click.echo(f"\n{Colors.CYAN}📂 Choose a template:{Colors.END}\n")
        for t in templates:
            click.echo(get_template_preview(t))
            click.echo()  # Add spacing between templates
        
        template = click.prompt(f"\n{Colors.YELLOW}Select template{Colors.END}", 
                               type=click.Choice(templates),
                               default=templates[0])
    elif not template:
        template = 'minimal'
    
    # Handle custom template
    custom_code = None
    if template == 'custom':
        if not ai:
            click.echo(f"{Colors.RED}❌ Custom template requires AI to be enabled!{Colors.END}")
            return
        
        if not description and not yes:
            click.echo(f"\n{Colors.CYAN}🤖 Custom Template Generator{Colors.END}")
            description = click.prompt(f"{Colors.YELLOW}Describe what you want to build{Colors.END}")
        elif not description:
            description = "A general purpose agent"
        
        show_progress("Generating custom template with AI", 2.0)
        custom_code = generate_custom_template(description, api_key or "")
        click.echo(f"{Colors.GREEN}✓ Custom template generated{Colors.END}")
    
    # Show confirmation summary
    if not yes:
        click.echo(f"\n{Colors.CYAN}📋 Project Summary{Colors.END}")
        click.echo(f"{Colors.CYAN}{'─' * 40}{Colors.END}")
        click.echo(f"  📁 Name: {Colors.BOLD}{name}{Colors.END}")
        click.echo(f"  📍 Location: {Colors.BOLD}{project_dir.absolute()}{Colors.END}")
        click.echo(f"  📦 Template: {Colors.BOLD}{template}{Colors.END}")
        if ai:
            click.echo(f"  🤖 AI: {Colors.GREEN}Enabled{Colors.END} ({provider.title() if provider else 'No key'})") 
        else:
            click.echo(f"  🤖 AI: {Colors.YELLOW}Disabled{Colors.END}")
        
        if custom_code and description:
            click.echo(f"  ✨ Custom: {description[:50]}...")
        
        click.echo(f"\n{Colors.CYAN}Files to create:{Colors.END}")
        files_preview = [
            "agent.py", ".env", ".co/config.toml", ".co/keys/", "README.md"
        ]
        if template in ['web-research', 'playwright']:
            files_preview.append("tools/")
        for f in files_preview:
            click.echo(f"  • {f}")
        
        if not click.confirm(f"\n{Colors.YELLOW}Create project?{Colors.END}", default=True):
            click.echo(f"{Colors.YELLOW}Project creation cancelled.{Colors.END}")
            return
    
    # Show progress while creating
    if not yes:
        show_progress("Creating project directory", 0.5)
    
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
    
    # Copy VibeCoding principles, docs and contexts all-in-one documentation
    if template_dir and template_dir.exists():
        # First try new filename, then fall back to old
        template_docs_new = template_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md"
        template_docs_old = template_dir / "connectonion.md"
        
        if template_docs_new.exists():
            shutil.copy2(template_docs_new, docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md")
            files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")
        elif template_docs_old.exists():
            # Fall back to old file for backward compatibility
            shutil.copy2(template_docs_old, docs_dir / "co-vibecoding-principles-docs-contexts-all-in-one.md")
            files_created.append(".co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md")
    
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
    
    # Success message with beautiful formatting
    click.echo(f"\n{Colors.GREEN}{Colors.BOLD}✅ Project created successfully!{Colors.END}")
    click.echo(f"{Colors.GREEN}{'=' * 40}{Colors.END}")
    
    click.echo(f"\n📁 Created: {Colors.BOLD}{name}{Colors.END}")
    click.echo(f"📦 Template: {Colors.BOLD}{template.title()}{Colors.END}")
    
    if custom_code and description:
        click.echo(f"\n✨ {Colors.CYAN}Custom agent generated from:{Colors.END}")
        click.echo(f"   {description[:60]}...")
    
    # Show agent address and email
    if 'addr_data' in locals() and addr_data.get('short_address'):
        click.echo(f"\n🔑 Agent address: {Colors.CYAN}{addr_data['short_address']}{Colors.END}")
        if addr_data.get('email'):
            email_status = " (inactive)" if not addr_data.get('email_active', False) else " (active)"
            click.echo(f"📧 Agent email: {Colors.CYAN}{addr_data['email']}{Colors.END}{Colors.YELLOW}{email_status}{Colors.END}")
            
            # Ask if user wants to activate email now
            if not addr_data.get('email_active', False) and not yes:
                click.echo(f"\n{Colors.CYAN}💌 Your agent can send emails!{Colors.END}")
                click.echo(f"   Email address: {Colors.BOLD}{addr_data['email']}{Colors.END}")
                if click.confirm(f"\n{Colors.YELLOW}Would you like to activate your agent's email now?{Colors.END}"):
                    click.echo(f"\n{Colors.CYAN}Launching authentication...{Colors.END}")
                    if do_auth_flow(co_dir):
                        # Email is now activated
                        click.echo(f"{Colors.GREEN}✨ Email activated! Your agent can now send emails.{Colors.END}")
                    else:
                        click.echo(f"{Colors.YELLOW}You can activate later with 'co auth'{Colors.END}")
    
    # Next steps with color coding
    click.echo(f"\n{Colors.CYAN}🚀 Next steps:{Colors.END}")
    click.echo(f"{Colors.CYAN}{'─' * 40}{Colors.END}")
    
    click.echo(f"\n1️⃣  Enter project directory:")
    click.echo(f"    {Colors.BOLD}cd {name}{Colors.END}")
    
    if not api_key:
        click.echo(f"\n2️⃣  Add your API key to .env:")
        click.echo(f"    {Colors.BOLD}nano .env{Colors.END}")
        click.echo(f"    {Colors.YELLOW}# Replace 'sk-your-api-key-here' with your key{Colors.END}")
        step = 3
    else:
        step = 2
    
    if template in ['web-research', 'playwright']:
        click.echo(f"\n{step}️⃣  Install browser automation:")
        click.echo(f"    {Colors.BOLD}pip install playwright{Colors.END}")
        click.echo(f"    {Colors.BOLD}playwright install{Colors.END}")
        step += 1
    
    click.echo(f"\n{step}️⃣  Run your agent:")
    click.echo(f"    {Colors.BOLD}python agent.py{Colors.END}")
    
    click.echo(f"\n{Colors.CYAN}📚 Resources:{Colors.END}")
    click.echo(f"   Documentation: {Colors.UNDERLINE}https://github.com/wu-changxing/connectonion{Colors.END}")
    click.echo(f"   Discord: {Colors.UNDERLINE}https://discord.gg/4xfD9k8AUF{Colors.END}")
    click.echo()


def do_auth_flow(co_dir: Path = None) -> bool:
    """Helper function to perform authentication flow.
    
    Args:
        co_dir: Path to .co directory (defaults to current directory)
        
    Returns:
        True if authentication successful, False otherwise
    """
    import webbrowser
    import time
    import json
    import requests
    from pathlib import Path
    
    if co_dir is None:
        co_dir = Path(".co")
    
    # Check if we're in a ConnectOnion project
    if not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return False
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return False
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return False
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Authenticating with OpenOnion...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Build authentication URL - goes to frontend purchase page
    auth_url = f"https://openonion.ai/purchase?key={public_key}&message={message}&signature={signature}"
    
    click.echo(f"\n{Colors.CYAN}Opening browser for authentication...{Colors.END}")
    click.echo(f"   URL: {auth_url[:80]}...")
    
    # Open browser
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        click.echo(f"{Colors.YELLOW}⚠️  Could not open browser automatically{Colors.END}")
        click.echo(f"Please visit: {Colors.CYAN}{auth_url}{Colors.END}")
    
    # Poll for authentication status
    click.echo(f"\n{Colors.YELLOW}⏳ Waiting for authentication...{Colors.END}")
    click.echo(f"   (This may take up to 2 minutes)")
    
    backend_url = "https://oo.openonion.ai"  # Production backend
    
    max_attempts = 24  # 2 minutes with 5-second intervals
    for attempt in range(max_attempts):
        try:
            # Check authentication status
            response = requests.get(f"{backend_url}/auth/status/{public_key}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "authenticated":
                    token = data.get("token")
                    email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                    
                    # Save token to config
                    config_path = co_dir / "config.toml"
                    import toml
                    config = toml.load(config_path) if config_path.exists() else {}
                    config["auth"] = {"token": token}
                    if "agent" not in config:
                        config["agent"] = {}
                    config["agent"]["email"] = email
                    config["agent"]["email_active"] = True  # Activate email after authentication
                    
                    with open(config_path, "w") as f:
                        toml.dump(config, f)
                    
                    click.echo(f"\n{Colors.GREEN}✅ Authentication successful!{Colors.END}")
                    click.echo(f"   Token saved to .co/config.toml")
                    click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                    click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                    return True
                elif data.get("status") == "pending":
                    # Still waiting
                    time.sleep(5)
            else:
                # Not authenticated yet
                time.sleep(5)
        except Exception:
            # Backend might not be reachable, continue polling
            time.sleep(5)
    
    click.echo(f"\n{Colors.RED}❌ Authentication timed out{Colors.END}")
    click.echo(f"   Please try running {Colors.CYAN}co auth{Colors.END} again")
    return False

@cli.command()
def auth():
    """Authenticate with OpenOnion for managed keys (co/ models).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Open your browser to complete authentication
    4. Save the token for future use
    """
    import webbrowser
    import time
    import json
    import requests
    from pathlib import Path
    
    # Check if we're in a ConnectOnion project
    co_dir = Path(".co")
    if not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Authenticating with OpenOnion...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Build authentication URL - goes to frontend purchase page
    # Frontend will handle the authentication and payment flow
    auth_url = f"http://localhost:3002/purchase?key={public_key}&message={message}&signature={signature}"
    
    # For production, use:
    # auth_url = f"https://openonion.ai/purchase?key={public_key}&message={message}&signature={signature}"
    
    click.echo(f"\n{Colors.CYAN}🌐 Opening browser for token purchase...{Colors.END}")
    click.echo(f"   Purchase tokens to use co/ models:")
    click.echo(f"   • $0.99 for 100K tokens")
    click.echo(f"   • $9.99 for 1M tokens")
    click.echo(f"\n   If browser doesn't open, visit:")
    click.echo(f"   {Colors.UNDERLINE}{auth_url}{Colors.END}")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Poll for authentication completion
    click.echo(f"\n{Colors.CYAN}⏳ Waiting for authentication...{Colors.END}")
    
    poll_url = f"http://localhost:8000/auth/poll/{public_key}"
    # For production: poll_url = f"https://api.openonion.ai/auth/poll/{public_key}"
    
    max_attempts = 60  # 5 minutes (60 * 5 seconds)
    for i in range(max_attempts):
        try:
            response = requests.get(poll_url)
            if response.status_code == 200:
                data = response.json()
                if "token" in data:
                    # Authentication successful!
                    token = data["token"]
                    email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                    
                    # Save token and email to config.toml
                    config_path = co_dir / "config.toml"
                    config = toml.load(config_path)
                    config["auth"] = {"token": token}
                    if "agent" not in config:
                        config["agent"] = {}
                    config["agent"]["email"] = email
                    config["agent"]["email_active"] = True  # Activate email after authentication
                    
                    with open(config_path, "w") as f:
                        toml.dump(config, f)
                    
                    click.echo(f"\n{Colors.GREEN}✅ Authentication successful!{Colors.END}")
                    click.echo(f"   Token saved to .co/config.toml")
                    click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                    click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                    return
                elif data.get("status") == "pending":
                    # Still waiting
                    time.sleep(5)
                    continue
                else:
                    click.echo(f"{Colors.RED}❌ Authentication failed: {data.get('error', 'Unknown error')}{Colors.END}")
                    return
        except requests.exceptions.ConnectionError:
            click.echo(f"{Colors.RED}❌ Cannot connect to authentication server{Colors.END}")
            click.echo(f"{Colors.YELLOW}Is the backend running? For development, start with:{Colors.END}")
            click.echo(f"   cd oo-api && uvicorn main:app --reload")
            return
        except Exception as e:
            click.echo(f"{Colors.RED}❌ Error: {e}{Colors.END}")
            return
    
    click.echo(f"{Colors.YELLOW}⏱️ Authentication timed out. Please try again.{Colors.END}")


@cli.command()
def register():
    """Register/authenticate in headless mode (no browser needed).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Directly authenticate with the backend
    4. Save the token for future use
    """
    import time
    import requests
    from pathlib import Path
    
    # Check if we're in a ConnectOnion project
    co_dir = Path(".co")
    if not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Registering with OpenOnion (headless mode)...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Directly call auth endpoint
    auth_url = "http://localhost:8000/auth"
    # For production: auth_url = "https://api.openonion.ai/auth"
    
    click.echo(f"\n{Colors.CYAN}📡 Authenticating directly...{Colors.END}")
    
    try:
        response = requests.post(auth_url, json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        })
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            
            if token:
                email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                
                # Save token and email to config.toml
                config_path = co_dir / "config.toml"
                config = toml.load(config_path)
                config["auth"] = {"token": token}
                if "agent" not in config:
                    config["agent"] = {}
                config["agent"]["email"] = email
                
                with open(config_path, "w") as f:
                    toml.dump(config, f)
                
                click.echo(f"\n{Colors.GREEN}✅ Registration successful!{Colors.END}")
                click.echo(f"   Token saved to .co/config.toml")
                click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                click.echo(f"\n{Colors.CYAN}Example:{Colors.END}")
                click.echo(f"   from connectonion import llm_do")
                click.echo(f"   response = llm_do('Hello', model='co/gpt-4o-mini')")
                return
        else:
            error = response.json().get("detail", "Unknown error")
            click.echo(f"\n{Colors.RED}❌ Registration failed: {error}{Colors.END}")
            
    except requests.exceptions.ConnectionError:
        click.echo(f"{Colors.RED}❌ Cannot connect to authentication server{Colors.END}")
        click.echo(f"{Colors.YELLOW}Is the backend running? For development, start with:{Colors.END}")
        click.echo(f"   cd oo-api && uvicorn main:app --reload")
    except Exception as e:
        click.echo(f"\n{Colors.RED}❌ Error during registration: {e}{Colors.END}")


@cli.command()
@click.argument('command')
def browser(command):
    """Execute browser automation commands - guide browser to do something.
    
    This is an alternative to the -b flag. Both 'co -b' and 'co browser' are supported.
    """
    from .browser_agent.browser import execute_browser_command
    result = execute_browser_command(command)
    click.echo(result)


# Entry points for both 'co' and 'connectonion' commands
def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()