from connectonion import Agent, bash, read_file, edit, glob, grep, write


agent = Agent(
    name="coder",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write],
    model="co/gemini-2.5-pro",
    max_iterations=50,
)


if __name__ == "__main__":
    print("🤖 Coder Agent")
    print("Type 'quit' to exit\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("👋 Goodbye!")
            break

        if not user_input:
            continue

        response = agent.input(user_input)
        print(f"Agent: {response}\n")
