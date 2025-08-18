"""Advanced ConnectOnion example with various tool types and features."""

import os
import sys
import json
from dotenv import load_dotenv
from typing import Dict, List

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent


# Advanced tool examples with different return types and error handling
def web_search(query: str, max_results: int = 5) -> str:
    """Advanced web search with result limiting."""
    # Simulate web search
    results = [
        f"Result {i+1}: Information about {query}" 
        for i in range(min(max_results, 3))
    ]
    return f"Web search for '{query}':\n" + "\n".join(results)


def data_analyzer(data: str, operation: str = "summarize") -> str:
    """Analyze data with different operations."""
    operations = {
        "summarize": f"Summary of data: {len(data)} characters analyzed",
        "count": f"Data contains {len(data.split())} words",
        "extract": f"Key terms extracted from data: {', '.join(data.split()[:5])}"
    }
    
    if operation not in operations:
        available = ", ".join(operations.keys())
        return f"Invalid operation '{operation}'. Available: {available}"
    
    return operations[operation]


def json_processor(json_data: str, action: str = "parse") -> str:
    """Process JSON data with error handling."""
    try:
        if action == "parse":
            data = json.loads(json_data)
            return f"Parsed JSON with {len(data)} top-level keys: {list(data.keys())}"
        elif action == "validate":
            json.loads(json_data)
            return "✅ Valid JSON format"
        else:
            return f"Unknown action: {action}. Available: parse, validate"
    except json.JSONDecodeError as e:
        return f"❌ JSON Error: {str(e)}"


def file_manager(action: str, filename: str, content: str = "") -> str:
    """File operations with proper error handling."""
    try:
        if action == "write":
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"✅ Written {len(content)} characters to {filename}"
        
        elif action == "read":
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                return f"📄 File content ({len(content)} chars): {content[:100]}..." if len(content) > 100 else content
            else:
                return f"❌ File {filename} not found"
        
        elif action == "delete":
            if os.path.exists(filename):
                os.remove(filename)
                return f"🗑️ Deleted {filename}"
            else:
                return f"❌ File {filename} not found"
        
        else:
            return f"❌ Unknown action: {action}. Available: write, read, delete"
    
    except Exception as e:
        return f"❌ File operation error: {str(e)}"


def system_info(info_type: str = "basic") -> str:
    """Get system information."""
    import platform
    import datetime
    
    if info_type == "basic":
        return f"System: {platform.system()} {platform.release()}, Python: {platform.python_version()}"
    elif info_type == "time":
        return f"Current time: {datetime.datetime.now().isoformat()}"
    elif info_type == "environment":
        return f"Platform: {platform.platform()}, Architecture: {platform.architecture()[0]}"
    else:
        return f"Unknown info type: {info_type}. Available: basic, time, environment"


def main():
    print("🔧 ConnectOnion Advanced Example")
    print("=" * 50)
    
    # Create agent with advanced tools and professional system prompt
    agent = Agent(
        name="advanced_assistant",
        system_prompt="""You are an advanced AI assistant with specialized capabilities in data analysis, 
        file management, and system operations. You are professional, thorough, and provide detailed 
        explanations when working with complex tasks. Always prioritize accuracy and safety in your operations.""",
        tools=[web_search, data_analyzer, json_processor, file_manager, system_info],
        model="gpt-5-mini",
        max_iterations=20  # Higher limit for complex multi-tool workflows
    )
    
    print(f"🤖 Agent: {agent.name}")
    print(f"🛠️  Tools: {', '.join(agent.list_tools())}")
    print(f"🔄 Max iterations: {agent.max_iterations} (allows complex multi-step workflows)")
    
    # Example 1: Complex search with parameters
    print("\n1️⃣ Advanced web search:")
    result = agent.input("Search for 'machine learning tutorials' and limit to 3 results")
    print(f"Result: {result}")
    
    # Example 2: Data analysis
    print("\n2️⃣ Data analysis:")
    sample_data = "artificial intelligence machine learning deep learning neural networks"
    result = agent.input(f"Analyze this data and count the words: '{sample_data}'")
    print(f"Result: {result}")
    
    # Example 3: JSON processing
    print("\n3️⃣ JSON processing:")
    sample_json = '{"name": "ConnectOnion", "version": "0.1.0", "tools": ["search", "calculate"]}'
    result = agent.input(f"Parse this JSON data: {sample_json}")
    print(f"Result: {result}")
    
    # Example 4: File operations
    print("\n4️⃣ File operations:")
    result = agent.input("Write 'Hello from ConnectOnion advanced example!' to 'demo.txt'")
    print(f"Write result: {result}")
    
    result = agent.input("Read the content of 'demo.txt'")
    print(f"Read result: {result}")
    
    # Example 5: System information
    print("\n5️⃣ System information:")
    result = agent.input("Tell me about the current system and time")
    print(f"Result: {result}")
    
    # Example 6: Complex multi-tool workflow
    print("\n6️⃣ Complex workflow:")
    result = agent.input(
        "Search for Python frameworks, analyze the system info, "
        "and write a summary to 'summary.txt'"
    )
    print(f"Result: {result}")
    
    # Example 7: Error handling demonstration
    print("\n7️⃣ Error handling:")
    result = agent.input("Try to parse this invalid JSON: '{invalid json}'")
    print(f"Result: {result}")
    
    # Example 8: Iteration control for different complexity levels
    print("\n8️⃣ Iteration Control Examples:")
    
    # Simple agent with lower iteration limit
    simple_agent = Agent(
        name="simple_processor",
        tools=[json_processor, system_info],
        max_iterations=5  # Simpler tasks need fewer iterations
    )
    
    result = simple_agent.input("Get basic system info")
    print(f"Simple task result: {result}")
    
    # Ultra-complex task with increased iteration limit
    ultra_complex_result = agent.input(
        "Search for AI frameworks, analyze system environment, create a JSON report with all findings, and save it to a timestamped file",
        max_iterations=30  # Override for this very complex task
    )
    print(f"Ultra-complex task result: {ultra_complex_result}")
    
    # Demonstrate hitting the iteration limit
    limited_agent = Agent(
        name="limited_bot",
        tools=[web_search, data_analyzer, json_processor, file_manager],
        max_iterations=3  # Very low limit to demonstrate the behavior
    )
    
    result = limited_agent.input("Search for multiple topics, analyze each one, create JSON reports for all, and save to separate files")
    print(f"Limited agent result: {result}")
    
    # Clean up files
    for filename in ['demo.txt', 'summary.txt']:
        if os.path.exists(filename):
            os.remove(filename)
    
    # Show detailed history
    print("\n" + "=" * 50)
    print("📊 Detailed History Analysis:")
    
    total_tools_used = sum(len(record.tool_calls) for record in agent.history.records)
    avg_duration = sum(record.duration_seconds for record in agent.history.records) / len(agent.history.records)
    
    print(f"📈 Statistics:")
    print(f"   - Total tasks: {len(agent.history.records)}")
    print(f"   - Total tool calls: {total_tools_used}")
    print(f"   - Average duration: {avg_duration:.2f}s")
    
    # Tool usage breakdown
    tool_usage = {}
    for record in agent.history.records:
        for tool_call in record.tool_calls:
            tool_name = tool_call.get('name', 'unknown')
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
    
    if tool_usage:
        print(f"   - Most used tools: {sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)}")
    
    print(f"\n💾 Full history saved to: {agent.history.history_file}")
    print("\n✨ Advanced features demonstrated successfully!")
    print("\n💡 Key takeaways about iteration control:")
    print("   - Default 10 iterations work for most tasks")
    print("   - Increase max_iterations for complex multi-step workflows")
    print("   - Use per-request override for occasional complex tasks")
    print("   - Lower limits provide safety for simple automation")


if __name__ == "__main__":
    main()