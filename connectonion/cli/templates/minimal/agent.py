"""
Purpose: Default template scaffolded by `co create` — a minimal, single-shot agent demonstrating tool + plugin wiring users can copy and modify.
LLM-Note:
  Dependencies: imports from [connectonion (Agent, bash, read_file, edit, glob, grep, write), connectonion.useful_tools.browser_tools.BrowserAutomation, connectonion.useful_plugins (image_result_formatter, tool_approval)] | NOT imported by the connectonion package itself — copied into user projects by cli/commands/create.py | exercised by [tests/cli/test_create.py]
  Data flow: module load → agent.input("what is your task?") → prints result; user is expected to replace this with their own prompt loop
  State/Effects: spins up headless Playwright browser (BrowserAutomation(headless=True)) at import time | tool_approval plugin gates side-effecting tools | system_prompt loaded from ./prompt.md
  Integration: exposes module-level `agent` and `result`
  Errors: errors bubble — no try/except by design
NOTE: Template ships as-is into user projects. Keep minimal and copy-paste runnable.
"""

from connectonion import Agent, bash, read_file, edit, glob, grep, write
from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_plugins import image_result_formatter, tool_approval

browser = BrowserAutomation(headless=True)

agent = Agent(
    name="my-agent",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write, browser],
    plugins=[image_result_formatter, tool_approval],
    model="co/gemini-2.5-pro",
)

result = agent.input("what is your task?")
print(result)
