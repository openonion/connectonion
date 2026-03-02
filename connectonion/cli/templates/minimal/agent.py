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
