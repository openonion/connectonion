#!/usr/bin/env python3
"""
Interactive Multi-LLM Chat Demo

Chat with different AI models (OpenAI, Anthropic, Google) in real-time.
Switch between models seamlessly during your conversation.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent

# Load environment variables
env_path = Path(__file__).parent.parent / "tests" / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Available models organized by provider
MODELS = {
    "OpenAI": [
        ("gpt-4o", "GPT-4o (Latest)"),
        ("gpt-4o-mini", "GPT-4o Mini (Fast & Cheap)"),
        ("gpt-4-turbo", "GPT-4 Turbo"),
        ("gpt-3.5-turbo", "GPT-3.5 Turbo")
    ],
    "Anthropic": [
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (Latest)"),
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (Fast)"),
        ("claude-3-opus-20240229", "Claude 3 Opus (Powerful)")
    ],
    "Google": [
        ("gemini-1.5-pro", "Gemini 1.5 Pro"),
        ("gemini-1.5-flash", "Gemini 1.5 Flash (Fast)"),
        ("gemini-1.0-pro", "Gemini 1.0 Pro")
    ]
}

# Define some example tools
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except:
        return "Invalid expression"

def get_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def word_count(text: str) -> int:
    """Count the number of words in text."""
    return len(text.split())

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print the application header."""
    print("\n" + "=" * 60)
    print("🤖 ConnectOnion Interactive Multi-LLM Chat")
    print("=" * 60)

def select_model():
    """Interactive model selection menu."""
    print("\n📋 Available Models:\n")
    
    all_models = []
    for provider, models in MODELS.items():
        print(f"\n{provider}:")
        for i, (model_id, model_name) in enumerate(models, 1):
            idx = len(all_models) + 1
            all_models.append((model_id, model_name, provider))
            print(f"  {idx}. {model_name}")
    
    print("\n" + "-" * 40)
    
    while True:
        try:
            choice = input("\nSelect a model (1-{}) or 'q' to quit: ".format(len(all_models)))
            if choice.lower() == 'q':
                return None, None, None
            
            idx = int(choice) - 1
            if 0 <= idx < len(all_models):
                return all_models[idx]
            else:
                print("❌ Invalid choice. Please try again.")
        except ValueError:
            print("❌ Please enter a number or 'q'.")

def create_agent_with_model(model_id, model_name, provider):
    """Create an agent with the selected model."""
    print(f"\n🚀 Initializing {model_name} from {provider}...")
    
    try:
        agent = Agent(
            "interactive_demo",
            model=model_id,
            tools=[calculate, get_time, word_count]
        )
        print(f"✅ Connected to {model_name}!\n")
        return agent
    except Exception as e:
        print(f"❌ Failed to initialize: {str(e)[:100]}")
        return None

def print_commands():
    """Print available commands."""
    print("\n📖 Commands:")
    print("  /switch  - Switch to a different model")
    print("  /clear   - Clear the screen")
    print("  /help    - Show this help message")
    print("  /quit    - Exit the chat\n")

def chat_loop(agent, model_name, provider):
    """Main chat interaction loop."""
    print(f"💬 Chat started with {model_name}")
    print("   Type /help for commands\n")
    print("-" * 60)
    
    while True:
        try:
            # Get user input
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()
                
                if command == "/quit":
                    print("\n👋 Goodbye!")
                    return False
                
                elif command == "/switch":
                    print("\n🔄 Switching models...")
                    return True
                
                elif command == "/clear":
                    clear_screen()
                    print_header()
                    print(f"\n💬 Chatting with {model_name} ({provider})")
                    print("-" * 60)
                    continue
                
                elif command == "/help":
                    print_commands()
                    continue
                
                else:
                    print("❓ Unknown command. Type /help for available commands.")
                    continue
            
            # Get AI response
            print(f"\n🤖 {model_name}: ", end="", flush=True)
            response = agent.input(user_input)
            print(response)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Use /quit to exit properly")
            continue
        except Exception as e:
            print(f"\n❌ Error: {str(e)[:100]}")
            print("   Try again or use /switch to change models.")

def main():
    """Main application entry point."""
    clear_screen()
    print_header()
    
    print("\n👋 Welcome! This demo lets you chat with different AI models.")
    print("   You can switch between OpenAI, Anthropic, and Google models.")
    print("\n⚡ Available tools: calculate(), get_time(), word_count()")
    print("   Try asking: 'What's 25 * 4?' or 'What time is it?'")
    
    while True:
        # Select a model
        model_id, model_name, provider = select_model()
        
        if model_id is None:
            print("\n👋 Goodbye!")
            sys.exit(0)
        
        # Create agent
        agent = create_agent_with_model(model_id, model_name, provider)
        
        if agent is None:
            print("\n⚠️  Could not initialize the model. Please try another.")
            continue
        
        # Start chat loop
        should_continue = chat_loop(agent, model_name, provider)
        
        if not should_continue:
            break
        
        # If switching models, loop continues
        print("\n" + "=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)