"""
Purpose: Template entry point scaffolded by `co create --template browser` — a runnable browser-automation agent users edit in their own project.
LLM-Note:
  Dependencies: imports from [pathlib, dotenv, connectonion.Agent, connectonion.useful_plugins (image_result_formatter, ui_stream), connectonion.useful_tools.browser_tools.BrowserAutomation] | NOT imported by the connectonion package itself — this is a template file copied verbatim into user projects by cli/commands/create.py | no in-repo tests (template is exercised via tests/cli/test_create.py)
  Data flow: __main__ REPL → input() → agent.input(user_input) → Agent loops with BrowserAutomation tool → prints response
  State/Effects: launches headless Playwright browser (BrowserAutomation(headless=True)) | loads .env via dotenv | streams UI events via ui_stream plugin
  Integration: exposes create_agent() returning a configured Agent | system_prompt loaded from sibling prompts/agent.md
  Performance: max_iterations=200 to allow long browser sessions
  Errors: errors bubble up from Agent / BrowserAutomation; no try/except by design
NOTE: Edits here ship as the user-facing template — keep it minimal and copy-paste runnable.
"""

from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter, ui_stream
from connectonion.useful_tools.browser_tools import BrowserAutomation

load_dotenv()


def create_agent():
    system_prompt_path = Path(__file__).parent / "prompts" / "agent.md"

    browser = BrowserAutomation(headless=True)
    return Agent(
        name="browser_agent",
        model="co/gemini-2.5-pro",
        system_prompt=system_prompt_path,
        tools=[browser],
        plugins=[image_result_formatter, ui_stream],
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
