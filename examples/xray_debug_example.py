"""
ConnectOnion Debugging Example - @xray and @replay Decorators

This example demonstrates how to use ConnectOnion's powerful debugging decorators
to understand and debug AI agent tool execution.

Key Features:
- @xray: See complete Agent context (agent, task, messages, iteration, etc.)
- @replay: Re-execute tools with different parameters during debugging
- Combined usage for comprehensive debugging

Prerequisites:
- Set OPENAI_API_KEY in your .env file
- Install ConnectOnion: pip install -e .

Debugging Instructions:
1. Set breakpoints in decorated functions (marked with 🎯)
2. Run this script in debug mode (F5 in VS Code, or use your IDE's debugger)
3. When breakpoint hits:
   - Type 'xray' to see full context
   - Type 'xray.agent', 'xray.task', etc. for specific values
   - Type 'replay(param=value)' to re-run with different parameters
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent
from connectonion.decorators import xray, replay


# =============================================================================
# Example Tools with Debugging Decorators
# =============================================================================

@xray
def analyze_text(text: str) -> dict:
    """
    Analyze text and return insights.
    
    With @xray decorator, you can access:
    - xray.agent: The Agent instance
    - xray.task: Original user request
    - xray.messages: Full conversation history
    - xray.iteration: Current iteration number
    - xray.previous_tools: Previously called tools
    """
    # 🎯 SET BREAKPOINT HERE to explore xray context
    # Debug console examples:
    # >>> xray
    # <XrayContext active>
    #   agent: 'analyzer'
    #   task: 'Analyze this text...'
    #   iteration: 1
    #   messages: 3 items
    #   Access values with: xray.agent, xray.task, etc.
    #
    # >>> xray.agent.name
    # 'analyzer'
    #
    # >>> len(xray.messages)
    # 3
    #
    # >>> xray()  # Get full context as dict
    # {'agent': <Agent>, 'task': '...', 'messages': [...]}
    
    word_count = len(text.split())
    char_count = len(text)
    unique_words = len(set(text.lower().split()))
    
    return {
        "word_count": word_count,
        "char_count": char_count,
        "unique_words": unique_words,
        "analysis_time": datetime.now().isoformat()
    }


@replay
def calculate_score(text: str, weights: dict = None) -> float:
    """
    Calculate a score based on text features.
    
    With @replay decorator, you can re-execute with different parameters:
    - replay(): Re-run with original parameters
    - replay(weights={'length': 0.5}): Override specific parameters
    """
    # 🎯 SET BREAKPOINT HERE to test replay functionality
    # Debug console examples:
    # >>> replay()
    # 🔄 Replaying calculate_score()
    # ✅ Result: 0.65
    #
    # >>> replay(weights={'length': 0.8, 'complexity': 0.2})
    # 🔄 Replaying calculate_score()
    #    Modified parameters: {'weights': {'length': 0.8, 'complexity': 0.2}}
    # ✅ Result: 0.82
    
    default_weights = {'length': 0.3, 'complexity': 0.7}
    weights = weights or default_weights
    
    # Simple scoring based on text length and complexity
    length_score = min(len(text) / 100, 1.0)
    unique_ratio = len(set(text.split())) / len(text.split()) if text else 0
    
    score = (
        weights.get('length', 0.3) * length_score + 
        weights.get('complexity', 0.7) * unique_ratio
    )
    
    print(f"Calculated score: {score:.2f} (weights: {weights})")
    return round(score, 2)


@xray
@replay
def generate_summary(text: str, max_words: int = 10, style: str = "brief") -> str:
    """
    Generate a summary with both debugging capabilities.
    
    Combining @xray and @replay gives you:
    - Full context visibility (xray.agent, xray.task, etc.)
    - Ability to retry with different parameters
    """
    # 🎯 SET BREAKPOINT HERE for complete debugging power
    # You can:
    # 1. Inspect Agent context:
    #    >>> xray.task
    #    'Generate a summary of...'
    #    >>> xray.iteration
    #    2
    #
    # 2. Retry with different parameters:
    #    >>> replay(max_words=20, style="detailed")
    #    🔄 Replaying generate_summary()
    #       Modified parameters: {'max_words': 20, 'style': 'detailed'}
    
    # Show that we can access context during execution
    if xray.agent:
        print(f"[{xray.agent.name}] Generating {style} summary (max {max_words} words)")
    
    words = text.split()
    
    if style == "brief":
        summary_words = words[:max_words]
    elif style == "detailed":
        # Take more words and add context
        summary_words = words[:min(max_words * 2, len(words))]
    else:
        summary_words = words[:max_words]
    
    summary = ' '.join(summary_words)
    if len(words) > len(summary_words):
        summary += '...'
    
    return f"[{style.upper()}] {summary}"


@xray
def debug_info() -> str:
    """
    Tool that demonstrates programmatic access to xray context.
    
    This shows how tools can use debugging context in their logic.
    """
    # This tool actually uses the xray context in its implementation
    info_parts = []
    
    if xray.agent:
        info_parts.append(f"Agent: {xray.agent.name}")
        info_parts.append(f"Task: '{xray.task[:50]}...'")
        info_parts.append(f"Iteration: {xray.iteration}")
        info_parts.append(f"Messages: {len(xray.messages)}")
        
        # Show message types
        message_types = {}
        for msg in xray.messages:
            role = msg.get('role', 'unknown')
            message_types[role] = message_types.get(role, 0) + 1
        info_parts.append(f"Message types: {message_types}")
        
        if xray.previous_tools:
            info_parts.append(f"Previous tools: {', '.join(xray.previous_tools)}")
            
        # Demonstrate xray.trace() - shows execution flow up to this point
        print("\n=== Execution Trace ===")
        xray.trace()
        print("===================\n")
    else:
        info_parts.append("No active Agent context")
    
    return " | ".join(info_parts)


# =============================================================================
# Main Demo Function
# =============================================================================

def main():
    """Run the debugging demonstration."""
    print("🧅 ConnectOnion Debugging Example - @xray and @replay")
    print("=" * 60)
    
    # Load environment variables
    load_dotenv()
    
    if not os.getenv('OPENAI_API_KEY'):
        print("\n❌ Error: OPENAI_API_KEY not found")
        print("\nTo set up:")
        print("1. Create a .env file in the project root")
        print("2. Add: OPENAI_API_KEY=sk-your-key-here")
        print("3. Get your key from: https://platform.openai.com/api-keys")
        return
    
    # Create agent with debugging tools
    agent = Agent(
        name="debug_demo",
        tools=[
            analyze_text,
            calculate_score,
            generate_summary,
            debug_info
        ],
        model="gpt-5-mini"  # Using gpt-5-mini for balanced performance
    )
    
    print(f"✅ Created agent '{agent.name}' with {len(agent.tools)} tools")
    print(f"🛠️  Available tools: {', '.join(agent.list_tools())}")
    
    # Show debugging instructions
    print("\n" + "=" * 60)
    print("📖 DEBUGGING INSTRUCTIONS:")
    print("=" * 60)
    print("1. Set breakpoints at lines marked with 🎯")
    print("2. Run this script in debug mode")
    print("3. When breakpoint hits, try these in debug console:")
    print()
    print("   For @xray decorated functions:")
    print("   >>> xray                    # See full context")
    print("   >>> xray.agent.name         # Agent name")
    print("   >>> xray.task               # Original request")
    print("   >>> xray.messages[0]        # First message")
    print("   >>> xray.iteration          # Current iteration")
    print("   >>> xray()                  # Get context as dict")
    print()
    print("   For @replay decorated functions:")
    print("   >>> replay()                # Re-run with same params")
    print("   >>> replay(param=new_value) # Re-run with changes")
    print("=" * 60)
    
    # Run example tasks
    print("\n🚀 Running example tasks...\n")
    
    tasks = [
        ("Text analysis", 
         "Analyze this text: 'ConnectOnion makes debugging AI agents incredibly easy with xray decorators.'"),
        
        ("Score calculation",
         "Calculate the score for: 'The quick brown fox jumps over the lazy dog'"),
        
        ("Summary generation",
         "Generate a brief summary of: 'Artificial intelligence is transforming how we interact with technology. "
         "From virtual assistants to autonomous vehicles, AI is becoming increasingly integrated into our daily lives. "
         "The future promises even more innovative applications.'"),
        
        ("Debug information",
         "Show me the current debugging information")
    ]
    
    for i, (description, task) in enumerate(tasks, 1):
        print(f"\n{i}. {description}:")
        print(f"   Task: {task[:80]}...")
        try:
            result = agent.run(task)
            print(f"   Result: {result}")
        except Exception as e:
            print(f"   Error: {e}")
    
    print("\n" + "=" * 60)
    print("✨ Debugging Tips:")
    print("- Set breakpoints to pause execution and explore context")
    print("- Use xray to understand what the Agent is thinking")
    print("- Use replay to test different parameters without restarting")
    print("- Combine both decorators for maximum debugging power")
    print("=" * 60)
    
    # Demonstrate xray.trace()
    print("\n" + "=" * 60)
    print("🔍 Tool Execution Trace (xray.trace()):")
    print("=" * 60)
    print("\nThe xray.trace() method shows the complete execution flow.")
    print("Let's run a task that uses multiple tools and then trace it:\n")
    
    # Run a task that will use multiple tools
    trace_task = """First analyze the text 'ConnectOnion is amazing', 
    then calculate its score, and finally generate a brief summary."""
    
    print(f"Running task: {trace_task[:60]}...")
    result = agent.run(trace_task)
    print(f"Result: {result[:100]}...\n")
    
    # Note: xray.trace() can only be called from within @xray decorated functions
    print("\nTo see execution traces, add xray.trace() inside your @xray decorated tools.")


if __name__ == "__main__":
    main()