# Sub-Agent Mechanism

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Request                                 │
│              "Find all authentication-related files"                 │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Main Agent                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ System Prompt: "You are a coding agent..."                    │  │
│  │ Tools: [task, glob, grep, read_file, write, edit, bash]      │  │
│  │ Model: co/claude-opus-4-5                                     │  │
│  │ Plugins: [eval, tool_approval, auto_compact]                 │  │
│  │ Session: {messages: [...], trace: [...], turn: 3}            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Decision: "This needs exploration, use task() tool"                 │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Tool Call:                                                   │    │
│  │ task(                                                        │    │
│  │   prompt="Find all files with auth, login, session, jwt",   │    │
│  │   agent_type="explore"                                       │    │
│  │ )                                                            │    │
│  └───────────────────────┬─────────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────┘
                             │
                             │ (1) Calls task() function
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Sub-Agent Factory                                 │
│                   (registry.py)                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ SUBAGENTS = {                                                 │  │
│  │   "explore": {                                                │  │
│  │     "description": "Fast codebase exploration",               │  │
│  │     "tools": [FileTools],  # glob, grep, read_file only      │  │
│  │     "model": "co/gemini-2.5-flash",  # Fast & cheap          │  │
│  │     "max_iterations": 15,                                     │  │
│  │   },                                                          │  │
│  │   "plan": {                                                   │  │
│  │     "description": "Design implementation plans",             │  │
│  │     "tools": [FileTools],  # Read-only                       │  │
│  │     "model": "co/gemini-2.5-pro",  # Smart                   │  │
│  │     "max_iterations": 10,                                     │  │
│  │   },                                                          │  │
│  │ }                                                             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ def get_subagent(agent_type):                                 │  │
│  │   config = SUBAGENTS[agent_type]                              │  │
│  │   prompt = load_prompt(f"agents/{agent_type}.md")            │  │
│  │   return Agent(                                               │  │
│  │     name=f"oo-{agent_type}",                                  │  │
│  │     tools=config["tools"],                                    │  │
│  │     plugins=[],  # NO plugins!                                │  │
│  │     system_prompt=prompt,                                     │  │
│  │     model=config["model"],                                    │  │
│  │     max_iterations=config["max_iterations"]                   │  │
│  │   )                                                           │  │
│  └───────────────────────┬───────────────────────────────────────┘  │
└────────────────────────────┼────────────────────────────────────────┘
                             │ (2) Creates fresh Agent instance
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Sub-Agent (Explore)                             │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Name: "oo-explore"                                            │  │
│  │ System Prompt: prompts/agents/explore.md                      │  │
│  │   ┌────────────────────────────────────────────────────────┐  │  │
│  │   │ # Explore Agent                                        │  │  │
│  │   │ ## CRITICAL: READ-ONLY MODE                            │  │  │
│  │   │ PROHIBITED: creating/modifying/deleting files          │  │  │
│  │   │ ALLOWED: glob, grep, read_file only                    │  │  │
│  │   │ ## Strategy: broad → narrow → read → summarize        │  │  │
│  │   └────────────────────────────────────────────────────────┘  │  │
│  │                                                               │  │
│  │ Tools: [glob, grep, read_file]  # Read-only                  │  │
│  │ Model: co/gemini-2.5-flash                                    │  │
│  │ Plugins: []  # None                                           │  │
│  │ Max Iterations: 15                                            │  │
│  │ Session: FRESH - no memory of parent conversation            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Execution Loop (autonomous):                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Iteration 1:                                                  │  │
│  │   LLM → "I'll start with glob to find auth files"            │  │
│  │   Tool: glob("**/*auth*")                                     │  │
│  │   Result: [src/auth.py, src/middleware/auth.py, ...]         │  │
│  │                                                               │  │
│  │ Iteration 2:                                                  │  │
│  │   LLM → "Now search for login, session, jwt patterns"        │  │
│  │   Tool: grep("login|session|jwt")                            │  │
│  │   Result: [matches in 12 files]                              │  │
│  │                                                               │  │
│  │ Iteration 3:                                                  │  │
│  │   LLM → "Read the main auth file"                            │  │
│  │   Tool: read_file("src/auth.py")                             │  │
│  │   Result: [file contents]                                    │  │
│  │                                                               │  │
│  │ Iteration 4:                                                  │  │
│  │   LLM → "I have enough info, summarizing..."                 │  │
│  │   NO TOOLS → Returns final response                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Final Response:                                               │  │
│  │                                                               │  │
│  │ ## Files Found                                                │  │
│  │ - src/auth.py - Main authentication logic                    │  │
│  │ - src/middleware/auth.py - JWT verification middleware       │  │
│  │ - src/models/user.py - User model with auth methods          │  │
│  │                                                               │  │
│  │ ## Key Findings                                               │  │
│  │ - JWT-based authentication using jose library                │  │
│  │ - Tokens stored in HTTP-only cookies                         │  │
│  │ - Password hashing with bcrypt                               │  │
│  │                                                               │  │
│  │ ## Recommended Actions                                        │  │
│  │ - Review token expiration settings (currently 24h)           │  │
│  │ - Consider adding refresh token mechanism                    │  │
│  └───────────────────────┬───────────────────────────────────────┘  │
└────────────────────────────┼────────────────────────────────────────┘
                             │ (3) Returns string result
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Main Agent (resumed)                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Receives tool result:                                         │  │
│  │ {                                                             │  │
│  │   "name": "task",                                             │  │
│  │   "result": "## Files Found\n- src/auth.py...\n..."          │  │
│  │ }                                                             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Next Iteration:                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ LLM sees sub-agent's findings in context                      │  │
│  │ Decides next action based on structured response              │  │
│  │                                                               │  │
│  │ Option 1: "I'll read the auth files to analyze them"         │  │
│  │   Tool: read_file("src/auth.py")                             │  │
│  │                                                               │  │
│  │ Option 2: "Based on findings, I'll create a fix"             │  │
│  │   Tool: write("fix_auth.py", ...)                            │  │
│  │                                                               │  │
│  │ Option 3: "I need more planning"                             │  │
│  │   Tool: task("Design a plan to add refresh tokens", "plan")  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Final Response to User:                                             │
│  "I found your authentication system uses JWT with these files..."   │
└─────────────────────────────────────────────────────────────────────┘
```

## State Isolation

```
┌──────────────────────────────────────────────────────────────────┐
│                     Main Agent State                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Session:                                                    │  │
│  │   messages: [                                               │  │
│  │     {role: "system", content: "You are a coding agent..."}  │  │
│  │     {role: "user", content: "Find auth files"}             │  │
│  │     {role: "assistant", tool_calls: [task(...)]}           │  │
│  │     {role: "tool", content: "## Files Found..."}           │  │
│  │   ]                                                         │  │
│  │   trace: [...]                                              │  │
│  │   turn: 3                                                   │  │
│  │   todo_list: [...]                                          │  │
│  │   plan_mode: false                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ NO SHARING
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Sub-Agent State (Fresh)                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Session:                                                    │  │
│  │   messages: [                                               │  │
│  │     {role: "system", content: "# Explore Agent..."}        │  │
│  │     {role: "user", content: "Find all files with auth..."}│  │
│  │     {role: "assistant", tool_calls: [glob(...)]}           │  │
│  │     {role: "tool", content: "[src/auth.py, ...]"}          │  │
│  │     {role: "assistant", tool_calls: [grep(...)]}           │  │
│  │     {role: "tool", content: "[matches]"}                   │  │
│  │   ]                                                         │  │
│  │   trace: [new trace]                                        │  │
│  │   turn: 1                                                   │  │
│  │   # NO todo_list, NO plan_mode, NO parent context         │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Logging Flow

```
Main Agent Log: ~/.co/logs/coder.log
├─ Turn 1: User input "Find auth files"
├─ Tool: task(agent_type="explore")
│  └─ Result: "## Files Found..."
└─ Turn 1 complete

Sub-Agent Log: ~/.co/logs/oo-explore.log (separate file)
├─ Turn 1: User input "Find all files with auth..."
├─ Tool 1: glob("**/*auth*")
├─ Tool 2: grep("login|session|jwt")
├─ Tool 3: read_file("src/auth.py")
└─ Turn 1 complete: "## Files Found..."

Main Agent Eval: ~/.co/evals/coder.yaml
Sub-Agent Eval: ~/.co/evals/oo-explore.yaml (separate file)
```

## Communication Protocol

```
┌──────────────────────────────────────────────────────────────────┐
│                   Communication Flow                              │
└──────────────────────────────────────────────────────────────────┘

Main Agent                    task() function                Sub-Agent
    │                              │                             │
    │  Call tool: task(           │                             │
    │    prompt="Find auth...",   │                             │
    │    agent_type="explore"     │                             │
    │  )                          │                             │
    ├─────────────────────────────>│                             │
    │                              │                             │
    │                              │  get_subagent("explore")    │
    │                              │  Creates Agent instance     │
    │                              ├─────────────────────────────>│
    │                              │                             │
    │                              │  subagent.input(prompt)     │
    │                              ├─────────────────────────────>│
    │                              │                             │
    │                              │         Autonomous          │
    │                              │         Execution           │
    │                              │         (multiple           │
    │                              │         iterations)         │
    │                              │                             │
    │                              │  return final_response      │
    │                              │<─────────────────────────────┤
    │                              │                             │
    │  return result               │  (Agent discarded)          │
    │<─────────────────────────────┤                             │
    │                              │                             │
    │  Continue with result        │                             │
    │  in context                  │                             │
    │                              │                             │
```

## Tool Access Matrix

```
┌────────────────────────┬──────────────┬─────────────┬─────────────┐
│ Tool                   │ Main Agent   │ Explore     │ Plan        │
├────────────────────────┼──────────────┼─────────────┼─────────────┤
│ glob                   │ ✓            │ ✓           │ ✓           │
│ grep                   │ ✓            │ ✓           │ ✓           │
│ read_file              │ ✓            │ ✓           │ ✓           │
│ edit                   │ ✓            │ ✗           │ ✗           │
│ write                  │ ✓            │ ✗           │ ✗           │
│ bash                   │ ✓ (approval) │ ✗           │ ✗           │
│ task (sub-agents)      │ ✓            │ ✗           │ ✗           │
│ ask_user               │ ✓            │ ✗           │ ✗           │
│ enter_plan_mode        │ ✓            │ ✗           │ ✗           │
└────────────────────────┴──────────────┴─────────────┴─────────────┘

Legend:
✓ = Available
✗ = Not available (by design)
```

## Performance Characteristics

```
┌──────────────────────────────────────────────────────────────────┐
│                    Performance Profile                            │
└──────────────────────────────────────────────────────────────────┘

Main Agent (co/claude-opus-4-5)
├─ Input cost: $15 / 1M tokens
├─ Output cost: $75 / 1M tokens
├─ Speed: ~500 tokens/sec
├─ Context: 200k tokens
└─ Use case: Complex reasoning, code generation

Explore Sub-Agent (co/gemini-2.5-flash)
├─ Input cost: $0.15 / 1M tokens  (100x cheaper!)
├─ Output cost: $0.60 / 1M tokens  (125x cheaper!)
├─ Speed: ~2000 tokens/sec  (4x faster!)
├─ Context: 1M tokens
└─ Use case: Fast file finding, simple searches

Plan Sub-Agent (co/gemini-2.5-pro)
├─ Input cost: $2.50 / 1M tokens  (6x cheaper)
├─ Output cost: $10 / 1M tokens   (7.5x cheaper)
├─ Speed: ~1000 tokens/sec  (2x faster)
├─ Context: 2M tokens
└─ Use case: Planning, architecture design

Example Task Breakdown:
┌────────────────────────────────────────────────────────────────┐
│ Task: "Find all API endpoints and create documentation"        │
├────────────────────────────────────────────────────────────────┤
│ Step 1: Main agent → task("Find all API endpoints", "explore")│
│         Sub-agent uses 50k tokens @ $0.15/1M = $0.0075         │
│         Time: ~25 seconds                                      │
│                                                                │
│ Step 2: Main agent processes findings                         │
│         Uses 10k tokens @ $15/1M = $0.15                       │
│                                                                │
│ Step 3: Main agent generates documentation                    │
│         Outputs 5k tokens @ $75/1M = $0.375                    │
│                                                                │
│ Total cost: $0.5325                                            │
│ Total time: ~40 seconds                                        │
│                                                                │
│ Without sub-agent (all with opus-4-5):                        │
│ Total cost: $3.75  (7x more expensive!)                        │
│ Total time: ~60 seconds  (1.5x slower)                         │
└────────────────────────────────────────────────────────────────┘
```

## Key Principles Summary

1. **Isolation**: Sub-agents have NO access to parent state
2. **Stateless**: Each task() call creates fresh agent instance
3. **Specialized**: Different prompts, tools, models per agent type
4. **Simple**: String in → autonomous work → string out
5. **No plugins**: Keep sub-agents focused and fast
6. **Cost optimization**: Use cheap models for simple tasks
7. **Tool restriction**: Read-only for exploration
8. **Self-contained prompts**: Include all context in task description
9. **Separate logging**: Independent log files and evals
10. **Synchronous**: Parent waits for result (no async complexity)
