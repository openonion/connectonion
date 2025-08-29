# Test Generation Prompt

You are a senior Python QA engineer. Generate pytest tests for a ConnectOnion Agent module.

Context:
- The Agent is created from `connectonion` and may expose tools.
- Tests should be self-contained; do not rely on network calls.
- Prefer simple, robust assertions.

Input to you:
- agent_file: the filename of the agent module (e.g., agent.py)

Requirements:
- Create a test module named `test_<agent_file_without_ext>.py`.
- Include tests for:
  - Agent initializes correctly
  - Tools list is retrievable (and non-empty if applicable)
  - Agent.input can be called; mock LLM calls appropriately
- Use `unittest.mock` to avoid real API calls.
- Output only the Python test code, nothing else.
