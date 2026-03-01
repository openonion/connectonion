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
