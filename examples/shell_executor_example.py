"""Interactive shell executor example for Linux and macOS using Anthropic Claude Sonnet 4.

This example demonstrates:
1. Using llm_do to intelligently generate shell commands
2. Using Claude Sonnet 4 in an Agent for orchestration
3. Safe command execution with basic security checks
4. Interactive chat interface for shell tasks
"""

import os
import sys
import subprocess
import platform
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path to import connectonion
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent, llm_do


class ShellCommand(BaseModel):
    """Simple model for shell command generation."""
    command: str
    explanation: str
    safe: bool


def generate_command(task: str) -> str:
    """Use llm_do to generate a shell command for a task."""
    try:
        result = llm_do(
            input=f"Generate a safe shell command for: {task}",
            output=ShellCommand,
            system_prompt=f"""Generate safe shell commands for {platform.system()}. 
            Only suggest read-only commands or safe operations. 
            Mark dangerous commands as unsafe.""",
            model="gpt-4o-mini"
        )
        
        if not result.safe:
            return f"❌ Unsafe command blocked: {result.command}\nReason: {result.explanation}"
        
        return f"💡 Generated: {result.command}\n📝 {result.explanation}"
    except Exception as e:
        return f"❌ Command generation failed: {e}"


def execute_command(command: str) -> str:
    """Execute a shell command safely."""
    # Basic safety check
    dangerous = ['rm -rf', 'sudo', 'format', 'dd if=']
    if any(bad in command.lower() for bad in dangerous):
        return f"❌ Blocked dangerous command: {command}"
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30,
            check=False
        )
        
        output = f"💻 Command: {command}\n"
        if result.stdout:
            output += f"📤 Output:\n{result.stdout.strip()}\n"
        if result.stderr:
            output += f"⚠️ Error:\n{result.stderr.strip()}\n"
        output += f"✅ Exit code: {result.returncode}"
        
        return output
    except subprocess.TimeoutExpired:
        return f"⏰ Command timed out: {command}"
    except Exception as e:
        return f"❌ Execution failed: {e}"


def smart_execute(task: str) -> str:
    """Generate and execute a command for a task."""
    # Step 1: Generate command using llm_do
    generation_result = generate_command(task)
    
    if "❌" in generation_result:
        return generation_result
    
    # Extract command (simple parsing)
    lines = generation_result.split('\n')
    command_line = lines[0].replace('💡 Generated: ', '')
    
    # Step 2: Execute the command
    execution_result = execute_command(command_line)
    
    return f"{generation_result}\n\n{execution_result}"


def print_header():
    """Print the application header."""
    os.system('clear' if platform.system() != 'Windows' else 'cls')
    print("=" * 60)
    print("🐚 Interactive Shell Assistant")
    print("Powered by Claude Sonnet 4 + llm_do")
    print("=" * 60)
    print(f"📍 Platform: {platform.system()}")
    print(f"📂 Current Directory: {os.getcwd()}")
    print("=" * 60)


def print_help():
    """Print available commands."""
    print("\n📚 Available Commands:")
    print("  • Type any task or shell command")
    print("  • /help    - Show this help message")
    print("  • /clear   - Clear the screen")
    print("  • /cd PATH - Change directory")
    print("  • /pwd     - Show current directory")
    print("  • /quit    - Exit the program")
    print("\n💡 Examples:")
    print("  • 'List all Python files'")
    print("  • 'Show system memory usage'")
    print("  • 'Count lines in all .py files'")
    print("  • 'ls -la' (direct command)")
    print()


def handle_cd(path: str):
    """Handle directory change."""
    try:
        os.chdir(os.path.expanduser(path))
        return f"📂 Changed directory to: {os.getcwd()}"
    except Exception as e:
        return f"❌ Failed to change directory: {e}"


def main():
    # Check platform
    current_os = platform.system()
    if current_os not in ['Linux', 'Darwin']:
        print(f"❌ Unsupported OS: {current_os}")
        print("This tool only works on Linux and macOS")
        return
    
    print_header()
    
    # Create interactive agent with Claude Sonnet 4
    print("🤖 Initializing Claude Sonnet 4 agent...")
    
    try:
        agent = Agent(
            name="shell_assistant",
            system_prompt="""You are an expert shell assistant for Unix-like systems.
            
            When the user asks for a task:
            1. Use smart_execute for tasks that need shell commands to be generated
            2. Use execute_command for direct commands the user provides
            
            Be helpful, concise, and safety-conscious. Explain what commands do when executed.""",
            model="claude-sonnet-4-0",
            tools=[smart_execute, execute_command],
            max_iterations=10
        )
        print("✅ Agent ready!\n")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        print("\nMake sure you have set your ANTHROPIC_API_KEY in the .env file")
        return
    
    print_help()
    
    # Interactive loop
    session_count = 0
    
    while True:
        try:
            # Get user input
            user_input = input("🔹 You: ").strip()
            
            if not user_input:
                continue
            
            # Handle special commands
            if user_input.lower() == '/quit':
                print("\n👋 Goodbye!")
                break
            
            elif user_input.lower() == '/help':
                print_help()
                continue
            
            elif user_input.lower() == '/clear':
                print_header()
                print_help()
                continue
            
            elif user_input.lower() == '/pwd':
                print(f"📂 Current directory: {os.getcwd()}")
                continue
            
            elif user_input.lower().startswith('/cd '):
                path = user_input[4:].strip()
                result = handle_cd(path)
                print(result)
                continue
            
            # Process with agent
            print("\n🔸 Assistant: ", end="", flush=True)
            
            # Check if it looks like a direct command
            if any(user_input.startswith(cmd) for cmd in ['ls', 'pwd', 'cat', 'grep', 'find', 'ps', 'df', 'du', 'top', 'which']):
                # Direct command execution
                response = agent.input(f"Execute this command directly: {user_input}")
            else:
                # Task that needs command generation
                response = agent.input(user_input)
            
            print(response)
            
            session_count += 1
            
            # Add separator for readability
            print("\n" + "-" * 60)
            
        except KeyboardInterrupt:
            print("\n\n⚠️ Use /quit to exit properly")
            continue
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Try again or use /quit to exit")
    
    # Show session summary
    if session_count > 0:
        print(f"\n📊 Session Summary:")
        print(f"  • Commands executed: {session_count}")
        print(f"  • History saved to: {agent.history.history_file}")
        print("\nThanks for using Shell Assistant! 🚀")


if __name__ == "__main__":
    main()