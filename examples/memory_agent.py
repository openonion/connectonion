"""
Memory Agent Example

Demonstrates how to use the Memory system to give your agent persistent knowledge.
"""

from connectonion import Agent, Memory


def main():
    print("=== Memory Agent Example ===\n")

    # Create memory instance
    memory = Memory(memory_dir="example_memories")

    # Create agent with memory
    agent = Agent(
        name="memory-assistant",
        system_prompt="""You are a helpful assistant with persistent memory.
When users tell you important information, save it to memory.
When users ask questions, check your memory first.

Memory keys should be descriptive, like:
- "alice-contact-info"
- "project-alpha-status"
- "meeting-notes-2025-11-20"
""",
        tools=[memory],
        max_iterations=10
    )

    # Example 1: Saving information
    print("1. Saving information to memory...")
    result = agent.input(
        "Remember that Alice from TechCorp prefers email communication "
        "and is interested in our API product. She has a budget of $50k."
    )
    print(result)
    print("\n" + "="*60 + "\n")

    # Example 2: Recalling information
    print("2. Recalling information from memory...")
    result = agent.input("What do I know about Alice?")
    print(result)
    print("\n" + "="*60 + "\n")

    # Example 3: Saving multiple pieces of information
    print("3. Saving more information...")
    agent.input("Remember that Bob from Marketing prefers phone calls")
    agent.input("Remember that Project Alpha is 80% complete and needs final testing")
    print("\n" + "="*60 + "\n")

    # Example 4: Listing all memories
    print("4. Listing all stored memories...")
    result = agent.input("What memories do I have?")
    print(result)
    print("\n" + "="*60 + "\n")

    # Example 5: Searching memories
    print("5. Searching across memories...")
    result = agent.input("Search for anything related to 'email'")
    print(result)
    print("\n" + "="*60 + "\n")

    # Example 6: Direct memory access (bypassing agent)
    print("6. Direct memory access (for testing)...")
    print("\nDirect write:")
    print(memory.write_memory("test-direct", "This was written directly"))

    print("\nDirect read:")
    print(memory.read_memory("test-direct"))

    print("\nDirect search:")
    print(memory.search_memory("direct"))

    print("\n" + "="*60 + "\n")
    print("Example complete! Check the 'example_memories/' directory to see saved files.")


if __name__ == "__main__":
    main()
