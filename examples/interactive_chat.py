"""Interactive chat example - type questions and get agent responses in real-time."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent


# Define helpful tools for the interactive session
def search(query: str) -> str:
    """Search for information on any topic."""
    # Simulate search results
    return f"Search results for '{query}': Found relevant information about {query}. This includes latest updates, tutorials, and best practices."

def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    try:
        # Safe evaluation
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return eval(expression)
        else:
            raise ValueError("Invalid characters - only basic math operations allowed")
    except Exception as e:
        raise Exception(f"Math error: {str(e)}")

def get_time(format: str = "default") -> str:
    """Get current date and time in various formats."""
    from datetime import datetime
    
    formats = {
        "default": "%Y-%m-%d %H:%M:%S",
        "date": "%Y-%m-%d", 
        "time": "%H:%M:%S",
        "full": "%A, %B %d, %Y at %I:%M %p",
        "iso": "%Y-%m-%dT%H:%M:%S"
    }
    
    fmt = formats.get(format, formats["default"])
    return datetime.now().strftime(fmt)

def weather(city: str) -> str:
    """Get weather information for a city."""
    # Simulate weather data
    import random
    temps = [18, 22, 25, 28, 20, 15, 30]
    conditions = ["Sunny", "Cloudy", "Rainy", "Partly cloudy", "Clear"]
    
    temp = random.choice(temps)
    condition = random.choice(conditions)
    
    return f"Weather in {city}: {condition}, {temp}°C"

def write_note(content: str, filename: str = "note.txt") -> str:
    """Write a note to a file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ Note saved to {filename}"
    except Exception as e:
        return f"❌ Error saving note: {str(e)}"

def read_note(filename: str = "note.txt") -> str:
    """Read a note from a file."""
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"📄 Content of {filename}:\n{content}"
        else:
            return f"❌ File {filename} not found"
    except Exception as e:
        return f"❌ Error reading note: {str(e)}"

def help_commands() -> str:
    """Show available commands and examples."""
    return """
🤖 ConnectOnion Interactive Chat - Available Commands:

📊 CALCULATIONS:
   "What is 25 * 4 + 10?"
   "Calculate the square root of 64"
   "What's 15% of 200?"

🔍 SEARCH:
   "Search for Python tutorials"
   "Look up information about AI"
   "Find details about machine learning"

🌤️ WEATHER:
   "What's the weather in Paris?"
   "Check weather for Tokyo"

⏰ TIME:
   "What time is it?"
   "Show me the current date"
   "Get time in full format"

📝 NOTES:
   "Write a note: Remember to buy milk"
   "Save this to grocery.txt: eggs, bread, milk"
   "Read my note"
   "Read grocery.txt"

💬 GENERAL:
   Just ask anything! I can help with questions, explanations, and more.

Type 'quit', 'exit', or 'bye' to end the session.
    """


def print_banner():
    """Print the welcome banner."""
    print("🧅 =" * 25)
    print("🤖 ConnectOnion Interactive Chat")
    print("🧅 =" * 25)
    print("Type your questions and I'll help you!")
    print("Type 'help' for examples or 'quit' to exit.\n")


def main():
    print_banner()
    
    # Create the interactive agent with a conversational personality
    agent = Agent(
        name="interactive_assistant",
        system_prompt="""You are ConnectOnion, a friendly and conversational AI assistant. 
        You love helping users with their questions and tasks. Be engaging, helpful, and 
        occasionally use emojis to make the conversation more lively. When using tools, 
        explain what you're doing in a natural, conversational way.""",
        tools=[search, calculate, get_time, weather, write_note, read_note, help_commands]
    )
    
    print(f"✅ Agent ready with tools: {', '.join(agent.list_tools())}")
    print(f"🔑 Using OpenAI API key: {os.getenv('OPENAI_API_KEY', 'Not found')[:10]}...\n")
    
    # Interactive loop
    session_count = 0
    
    while True:
        try:
            # Get user input
            user_input = input("🧅 You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                print("\n👋 Thanks for using ConnectOnion! Goodbye!")
                break
            
            # Skip empty inputs
            if not user_input:
                continue
            
            # Process the query
            print("\n🤖 Thinking...")
            
            try:
                response = agent.run(user_input)
                print(f"🤖 Assistant: {response}\n")
                session_count += 1
                
            except Exception as e:
                print(f"❌ Sorry, I encountered an error: {str(e)}")
                print("Please try rephrasing your question.\n")
        
        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        
        except EOFError:
            print("\n\n👋 Session ended. Goodbye!")
            break
    
    # Show session summary
    if session_count > 0:
        print("📊 Session Summary:")
        print(f"   - Questions answered: {session_count}")
        print(f"   - Total interactions: {len(agent.history.records)}")
        print(f"   - History saved to: {agent.history.history_file}")
        
        # Show recent interactions
        if agent.history.records:
            print("\n📝 Your recent questions:")
            for i, record in enumerate(agent.history.get_recent(3), 1):
                print(f"   {i}. {record.task[:50]}{'...' if len(record.task) > 50 else ''}")


if __name__ == "__main__":
    main()