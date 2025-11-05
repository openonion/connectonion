"""Meta-Agent - Your ConnectOnion development assistant with documentation expertise"""

from connectonion import Agent, xray
from connectonion import llm_do
import json
from pathlib import Path
import subprocess
import platform
import shutil

@xray
def extract_relevant_connectonion_text(question: str, docs_path: str = ".co/docs/connectonion.md") -> str:
    """Load docs and use llm_do to extract relevant text for the question."""
    try:
        with open(docs_path, 'r', encoding='utf-8') as f:
            docs = f.read()
    except FileNotFoundError:
        return "ConnectOnion documentation not found. Try running 'co init' again."
    # Use llm_do with a retrieval prompt file to select relevant content
    return llm_do(
        input=f"Question: {question}\n\nDocumentation:\n{docs}",
        system_prompt="prompts/docs_retrieve_prompt.md",
        model="co/gpt-4o",
        temperature=0.1,
    )


@xray
def answer_connectonion_question(question: str) -> str:
    """Answer a question using relevant text extracted from documentation via llm_do."""
    relevant = extract_relevant_connectonion_text(question)
    return llm_do(
        input=f"Question: {question}\n\nRelevant context:\n{relevant}",
        system_prompt="prompts/answer_prompt.md",
        model="co/gpt-4o",
        temperature=0.1,
    )



@xray
def think(context: str = "current situation") -> str:
    """Reflect using llm_do on a simple JSON dump of xray.messages."""
    transcript = json.dumps(xray.messages or [])
    return llm_do(
        input=f"Context: {context}\n\nMessages: {transcript}",
        system_prompt="prompts/think_prompt.md",
        model="co/gpt-4o",
        temperature=0.1,
    )
 


def add_todo(task: str) -> str:
    """Add a to-do item to todo.md as an unchecked task."""
    if not task or not task.strip():
        return "Please provide a non-empty task."
    path = Path(__file__).resolve().parent / "todo.md"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {task.strip()}\n")
    return f"Added to-do: {task.strip()}"


def delete_todo(task: str) -> str:
    """Delete the first matching to-do (checked or unchecked) from todo.md."""
    path = Path(__file__).resolve().parent / "todo.md"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    removed = False
    for line in lines:
        if (line.startswith("- [ ] ") or line.startswith("- [x] ")) and task in line and not removed:
            removed = True
            continue
        new_lines.append(line)
    if not removed:
        return "To-do not found."
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"Deleted to-do: {task}"


def list_todos() -> str:
    """Return the current contents of todo.md or a notice if empty."""
    path = Path(__file__).resolve().parent / "todo.md"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    content = path.read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln.strip()]
    if len(lines) == 0:
        return "No to-dos yet. Use add_todo(task) to add one."
    return content


@xray
def run_shell(command: str, timeout: int = 120, cwd: str = "") -> str:
    """Execute a shell command cross-platform and return output.
    
    Works on macOS/Linux and Windows. Uses bash/sh when available on *nix,
    and PowerShell (or cmd) on Windows.
    """
    cmd = command.strip()
    if not cmd:
        return "No command provided."
    system = platform.system()
    if system == "Windows":
        if shutil.which("powershell"):
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd]
        else:
            argv = ["cmd", "/c", cmd]
    else:
        if shutil.which("bash"):
            argv = ["bash", "-lc", cmd]
        else:
            argv = ["sh", "-lc", cmd]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=cwd or None,
            timeout=timeout
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return (
            f"exit_code: {proc.returncode}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}".rstrip()
        )
    except subprocess.TimeoutExpired as e:
        return f"Command timed out after {timeout}s. Partial output:\nstdout:\n{e.stdout or ''}\nstderr:\n{e.stderr or ''}"
    except Exception as e:
        return f"Error executing command: {e}"


 


# Create the meta-agent with comprehensive ConnectOnion knowledge
agent = Agent(
    name="meta_agent",
    system_prompt="prompts/metagent.md",
    tools=[
        answer_connectonion_question,  # Primary documentation tool
        think,                          # Self-reflection
        add_todo,
        delete_todo,
        list_todos,
        run_shell
    ],
    model="co/o4-mini",
    max_iterations=15  # More iterations for complex assistance
)


if __name__ == "__main__":
    print("🤖 ConnectOnion Meta-Agent initialized!")
    print("Your AI assistant for ConnectOnion development\n")
    print("Available capabilities:")
    print("📚 Documentation expert - Ask any question about ConnectOnion")
    print("🔧 Code generation - Create agents, tools, and tests")
    print("📝 Task planning - Break down complex projects")
    print("🏗️ Project structure - Get architecture recommendations")
    print("\nTry: 'How do tools work in ConnectOnion?'")
    print("     'Create a web scraper agent'")
    print("     'Generate a tool for sending emails'")
    
    # Interactive loop
    print("\nType 'exit' or 'quit' to end the conversation.")
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not user_input:
            continue
        assistant_reply = agent.input(user_input)
        print(f"\nAssistant: {assistant_reply}")