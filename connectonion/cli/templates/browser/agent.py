"""
Purpose: Template entry point scaffolded by `co create --template browser` — a runnable browser-automation agent users edit in their own project.
LLM-Note:
  Dependencies: imports from [pathlib, dotenv, connectonion (Agent, bash), connectonion.useful_plugins (image_result_formatter, tool_approval, ui_stream)] | NOT imported by the connectonion package itself — this is a template file copied verbatim into user projects by cli/commands/create.py | no in-repo tests (template is exercised via tests/cli/test_create.py)
  Data flow: __main__ REPL → input() → agent.input(user_input) → Agent loops, driving the browser as bash("co browser <verb>") against the shared daemon → prints response
  State/Effects: no browser is started in-process — `co browser` talks to the shared daemon, which owns the profile and tabs | loads .env via dotenv | tool_approval gates non-whitelisted shell | streams UI events via ui_stream plugin
  Integration: exposes create_agent() returning a configured Agent | system_prompt loaded from sibling prompts/agent.md
  Performance: max_iterations=200 to allow long browser sessions
  Errors: errors bubble up from Agent / the co browser CLI (non-zero exit); no try/except by design
NOTE: Edits here ship as the user-facing template — keep it minimal and copy-paste runnable.
"""

from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent, bash
from connectonion.useful_plugins import image_result_formatter, tool_approval, ui_stream

load_dotenv()


def create_agent():
    system_prompt_path = Path(__file__).parent / "prompts" / "agent.md"

    return Agent(
        name="browser_agent",
        model="co/gemini-3.6-flash",
        system_prompt=system_prompt_path,
        # The browser is driven through the `co browser` CLI, so the agent needs
        # a shell. tool_approval keeps that from being a blank cheque: the
        # default whitelist allows `co *` and prompts for anything else.
        tools=[bash],
        plugins=[image_result_formatter, tool_approval, ui_stream],
        max_iterations=200,
    )


if __name__ == "__main__":
    print("🌐 Browser Agent")
    print("Type 'quit' to exit\n")

    agent = create_agent()

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("👋 Goodbye!")
            break

        if not user_input:
            continue

        response = agent.input(user_input)
        print(f"Agent: {response}\n")
