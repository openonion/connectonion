"""
Purpose: Template entry point scaffolded by `co create --template coder` — a runnable coding agent with file/shell tools that users edit in their own project.
LLM-Note:
  Dependencies: imports from [connectonion (Agent, bash, read_file, edit, glob, grep, write)] | NOT imported by the connectonion package itself — copied verbatim into user projects by cli/commands/create.py | exercised by [tests/cli/test_create.py]
  Data flow: __main__ REPL → input() → agent.input(user_input) → Agent loops invoking bash/read_file/edit/glob/grep/write tools → prints response
  State/Effects: tools mutate user's filesystem (write/edit) and run shell commands (bash) | system_prompt loaded from ./prompt.md alongside this file
  Integration: exposes module-level `agent` (model="co/gemini-2.5-pro", max_iterations=50)
  Performance: max_iterations=50 caps coding loops
  Errors: errors bubble from tools/Agent — no try/except by design
NOTE: Template ships as-is into user projects. Keep minimal.
"""

from connectonion import Agent, bash, read_file, edit, glob, grep, write


agent = Agent(
    name="coder",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write],
    model="co/gemini-3.5-flash",
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
