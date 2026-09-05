"""
Example: You.com search tools with ConnectOnion agents.

Three plain functions — youcom_search, youcom_contents, youcom_research —
give an agent current web search, URL content extraction, and cited
research synthesis. All are opt-in through YDC_API_KEY.
"""

import os

from connectonion import Agent, youcom_contents, youcom_research, youcom_search


def create_research_agent():
    """Create an agent with You.com search capabilities."""
    return Agent(
        name="researcher",
        system_prompt="""You are a research assistant with access to current web information.

Use youcom_search for up-to-date information, youcom_contents to read
specific URLs, and youcom_research for a cited synthesis. Always cite
your sources.""",
        tools=[youcom_search, youcom_contents, youcom_research],
    )


def main():
    """Demonstrate the You.com tools."""
    if not os.getenv("YDC_API_KEY"):
        print("YDC_API_KEY is not set — the tools will return auth_required.")
        print("Create a key at you.com/platform/api-keys and export it to run this example.")
        return

    agent = create_research_agent()

    print("\n--- Example 1: Current information search ---")
    print(agent.input("What are the latest developments in AI agent frameworks?"))

    print("\n--- Example 2: URL content analysis ---")
    print(agent.input("Analyze the content at https://docs.connectonion.com and summarize the key features"))

    print("\n--- Example 3: Cited research synthesis ---")
    print(agent.input("Research the current state of multi-agent AI systems, with citations"))


if __name__ == "__main__":
    main()
