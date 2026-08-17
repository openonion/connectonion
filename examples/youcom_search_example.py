"""
Example: Using YoucomSearch tool with ConnectOnion agents.

This demonstrates how to add You.com web search capabilities to your agents
for current information retrieval, URL content extraction, and research synthesis.
"""

import os
from connectonion import Agent
from connectonion.useful_tools import YoucomSearch


def create_research_agent():
    """Create an agent with You.com search capabilities."""
    search = YoucomSearch()
    
    agent = Agent(
        name="researcher",
        system_prompt="""You are a research assistant with access to current web information.
        
Use your search tools to find up-to-date information, extract content from 
specific URLs, and provide well-researched answers with citations.

Always cite your sources when using web search results.""",
        tools=[search]
    )
    
    return agent


def create_web_assistant():
    """Create a general assistant with web search for current information."""
    search = YoucomSearch()
    
    agent = Agent(
        name="web_assistant", 
        system_prompt="""You are a helpful assistant with web search capabilities.

When users ask about current events, recent developments, or need information
that might have changed since your training, use web search to provide 
accurate, up-to-date answers.""",
        tools=[search]
    )
    
    return agent


def main():
    """Demonstrate You.com search integration."""
    # Check for API key (optional but recommended)
    api_key = os.getenv('YDC_API_KEY')
    if not api_key:
        print("💡 Tip: Set YDC_API_KEY environment variable for full You.com features")
        print("   Without it, you'll have access to free search with limited functionality")
    else:
        print("✅ You.com API key found - full features available")
    
    print("\n🔍 Creating research agent with You.com search...")
    agent = create_research_agent()
    
    # Example: Current web search
    print("\n--- Example 1: Current Information Search ---")
    result = agent.input("What are the latest developments in AI agent frameworks?")
    print(f"Agent: {result}")
    
    # Example: URL content extraction
    print("\n--- Example 2: URL Content Analysis ---")
    result = agent.input("Analyze the content at https://docs.connectonion.com and summarize the key features")
    print(f"Agent: {result}")
    
    # Example: Research synthesis (requires API key)
    if api_key:
        print("\n--- Example 3: Research Synthesis ---")
        result = agent.input("Research and synthesize information about the current state of multi-agent AI systems")
        print(f"Agent: {result}")
    else:
        print("\n--- Example 3: Skipped (requires YDC_API_KEY for research synthesis)")
    
    print("\n✨ You.com integration complete!")


if __name__ == "__main__":
    # Example environment setup (uncomment to use)
    # os.environ['YDC_API_KEY'] = 'your-api-key-here'
    
    main()