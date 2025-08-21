"""Chat Agent Template - Focused on conversation"""

from connectonion import Agent


def remember_info(key: str, value: str) -> str:
    """Remember information for later use in conversation."""
    # In a real implementation, this might use a database or file
    return f"I'll remember that {key} is {value}"


def search_memory(query: str) -> str:
    """Search previously remembered information."""
    # Simulate memory search
    return f"Searching memory for '{query}'... (This is a simulated result)"


def get_weather(location: str = "current location") -> str:
    """Get weather information for a location."""
    # Simulate weather API call
    return f"The weather in {location} is sunny with a temperature of 72°F"


def set_reminder(message: str, time: str = "later") -> str:
    """Set a reminder for the user."""
    return f"I'll remind you to '{message}' {time}"


# Create a conversational agent
# System prompt is loaded from prompt.md for better maintainability
agent = Agent(
    name="chat_assistant",
    system_prompt="prompt.md",  # Always use markdown files for system prompts
    tools=[remember_info, search_memory, get_weather, set_reminder]
)


if __name__ == "__main__":
    print("💬 Chat Assistant Ready!")
    print("I'm here to chat and help you with anything you need.")
    print("Available tools:", agent.list_tools())
    
    # Start an interactive conversation
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("Chat Assistant: Goodbye! Have a great day! 👋")
                break
            
            response = agent.input(user_input)
            print(f"Chat Assistant: {response}")
            
        except KeyboardInterrupt:
            print("\nChat Assistant: Goodbye! Have a great day! 👋")
            break