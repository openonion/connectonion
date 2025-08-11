"""Examples showing different agent personalities with system prompts."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent


# Simple tool for all agents to use
def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    try:
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return eval(expression)
        else:
            raise ValueError("Invalid characters in expression")
    except Exception as e:
        raise Exception(f"Math error: {str(e)}")


def get_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    print("🎭 ConnectOnion Agent Personality Examples")
    print("=" * 50)
    
    # Create agents with different personalities
    agents = {
        "Professional Assistant": Agent(
            name="professional",
            system_prompt="""You are a highly professional business assistant. 
            Provide clear, concise, and formal responses. Always maintain a professional tone 
            and focus on efficiency and accuracy.""",
            tools=[calculate, get_time]
        ),
        
        "Friendly Teacher": Agent(
            name="teacher",
            system_prompt="""You are an enthusiastic and patient teacher who loves to educate. 
            Explain concepts clearly, use analogies when helpful, and encourage learning. 
            Always be supportive and positive in your responses.""",
            tools=[calculate, get_time]
        ),
        
        "Casual Buddy": Agent(
            name="buddy",
            system_prompt="""You are a laid-back, casual friend who's always ready to help. 
            Use informal language, be conversational, and don't be afraid to use slang or 
            casual expressions. Keep things light and fun! 😎""",
            tools=[calculate, get_time]
        ),
        
        "Technical Expert": Agent(
            name="expert",
            system_prompt="""You are a highly technical expert with deep knowledge in 
            mathematics, engineering, and computer science. Provide detailed, technical 
            explanations with precision. Use technical terminology appropriately and 
            show your working when solving problems.""",
            tools=[calculate, get_time]
        ),
        
        "Creative Storyteller": Agent(
            name="storyteller",
            system_prompt="""You are a creative storyteller who sees everything as an 
            opportunity for narrative. Frame your responses as mini-stories or adventures. 
            Be imaginative, use vivid descriptions, and make even simple tasks sound 
            interesting and engaging.""",
            tools=[calculate, get_time]
        )
    }
    
    # Test task
    test_task = "Calculate 15 * 8 and tell me what time it is"
    
    print(f"🎯 Test Task: '{test_task}'")
    print()
    
    # Run the same task with different agents
    for personality, agent in agents.items():
        print(f"🎭 {personality} ({agent.name}):")
        print(f"System Prompt: {agent.system_prompt[:100]}...")
        print()
        
        try:
            result = agent.input(test_task)
            print(f"Response: {result}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        print("\n" + "-" * 50 + "\n")
    
    # Show how personalities affect different types of tasks
    print("🔍 Testing Different Task Types:")
    print("=" * 50)
    
    tasks = [
        "Explain what 2 + 2 equals",
        "Help me understand why we need to calculate things",
        "What's the current time and why might that be important?"
    ]
    
    # Test with just a few different personalities for variety
    selected_agents = {
        "Teacher": agents["Friendly Teacher"],
        "Buddy": agents["Casual Buddy"],
        "Expert": agents["Technical Expert"]
    }
    
    for task in tasks:
        print(f"\n📝 Task: '{task}'\n")
        
        for name, agent in selected_agents.items():
            print(f"🎭 {name}: ", end="")
            try:
                result = agent.input(task)
                print(result[:150] + "..." if len(result) > 150 else result)
            except Exception as e:
                print(f"❌ Error: {str(e)}")
            print()
    
    print("\n✨ System Prompt Tips:")
    print("=" * 30)
    print("• Be specific about the desired tone and style")
    print("• Define the agent's expertise and knowledge areas") 
    print("• Specify how they should interact with users")
    print("• Include any special behaviors or preferences")
    print("• Consider the context where the agent will be used")
    print("• Test different prompts to find what works best!")


if __name__ == "__main__":
    main()