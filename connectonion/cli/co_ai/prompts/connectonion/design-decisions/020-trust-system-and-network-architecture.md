# The Architecture of Trust: Designing ConnectOnion's Network Layer

*December 2025*

Every complex system we build eventually teaches us the same lesson: we should have made it simpler. This is the story of how we designed ConnectOnion's trust and network architecture—the wrong turns, the breakthroughs, and what we learned about building systems that are both powerful and usable.

---

## Part I: The Problem

We had a trust system that couldn't enforce anything.

Three levels—`open`, `careful`, `strict`. Whitelists stored in `~/.connectonion/trusted.txt`. Trust agents that could verify capabilities. Natural language policies. It looked sophisticated.

But when an agent passed verification, it got full access. There was no sandbox. No resource limits. No actual enforcement. Our trust system asked "who should I trust?" but never answered "what happens when trust is violated?"

Meanwhile, our threat model identified three high-priority attacks:

1. **Capability Fraud**: Agents claiming they use GPT-4 but actually using GPT-3.5
2. **Data Harvesting**: "Free" services that collect and sell your data
3. **Cost Manipulation**: Malicious tasks that drain your token budget

All three require enforcement, not just verification. We needed to add teeth.

---

## Part II: Trust Is Not One Thing

The first insight came from mapping out who asks what, when:

```
OUTBOUND TRUST (you're sending a task)
├── Question: "Should I send my data to this agent?"
├── Concerns: Data leakage, overcharging, capability fraud
└── Example: Sending confidential documents for translation

INBOUND TRUST (you're receiving a task)
├── Question: "Should I accept this task? With what limits?"
├── Concerns: Resource drain, prompt injection, abuse
└── Example: Unknown agent asking you to process large data

EXECUTION TRUST (you're running a task)
├── Question: "What can this code actually do on my machine?"
├── Concerns: System access, network calls, file operations
└── Example: Running a tool that might make external API calls
```

Each direction has different risks and needs different policies. An inbound policy might say "reject large tasks from strangers." An outbound policy might say "don't send financial data to unverified agents." An execution policy might say "no network access for this task."

We initially designed three separate trust agents. Then four, when we added a Communication Agent for routing. Each was elegant in isolation. Together, they were a nightmare to explain.

**Lesson learned**: Comprehensiveness is the enemy of usability. Users don't want to understand four agents to use one feature.

---

## Part III: Where Should Trust Decisions Happen?

We debated three architectures:

**Centralized (Server-Client)**
```
┌─────────────────┐
│  Trust Server   │ ← Central authority
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
Agent A    Agent B    ← Agents query server
```

A server maintains global reputation. Revocation is instant. Cold start is easy—the server bootstraps new agents.

But: single point of failure. Privacy concerns (server sees all queries). Doesn't work offline. Creates dependency.

**Decentralized (Client-Side Only)**
```
┌─────────────┐         ┌─────────────┐
│  Agent A    │         │  Agent B    │
│             │         │             │
│ whitelist   │         │ whitelist   │
│ blacklist   │         │ blacklist   │
│ contacts    │         │ contacts    │
└─────────────┘         └─────────────┘
      ↑                       ↑
      └── No connection ──────┘
```

Full privacy. Works offline. No dependencies.

But: cold start problem. When you know no one, how do you start? No shared learning across the network.

**Peer-to-Peer (Behavioral)**
```
┌─────────────┐ ◄──── 47 successful tasks ────► ┌─────────────┐
│  Agent A    │                                  │  Agent B    │
│             │ ◄──── Trust: 0.95 ───────────── │             │
│ contacts:   │                                  │ contacts:   │
│  B: trusted │                                  │  A: trusted │
└─────────────┘                                  └─────────────┘
```

Trust emerges from behavior. No central authority. Natural and organic.

But: slow to build. Sybil attacks (fake identities gaming the system). Cold start still unsolved.

**The resolution**: these aren't mutually exclusive.

```python
# Trust resolution order (first match wins)
def resolve_trust(peer):
    # 1. Local rules (highest priority - user explicit)
    if peer in local_blacklist: return REJECT
    if peer in local_whitelist: return ACCEPT

    # 2. Behavioral history (P2P)
    contact = contacts.get(peer)
    if contact and contact.reliability > 0.8:
        return TRUST_CAREFUL

    # 3. Same network detection
    if is_localhost(peer) or is_same_lan(peer):
        return TRUST_CAREFUL

    # 4. Server fallback (optional, for cold start)
    if trust_server:
        info = trust_server.query(peer)
        if info: return info.trust_level

    # 5. Default: treat as stranger
    return TRUST_STRICT
```

**Local always works.** Server accelerates but isn't required. P2P accumulates naturally over time. New users get help from the server; experienced users rely on their own contacts.

---

## Part IV: Hard Limits vs Soft Policy

The critical question: what MUST be code versus what CAN be prompt?

| Aspect | Must Be Code | Can Be Prompt |
|--------|-------------|---------------|
| Max tokens | ✅ LLM might ignore | |
| Timeout | ✅ Can't trust LLM to stop | |
| Rate limiting | ✅ Security-critical | |
| Blacklist enforcement | ✅ Must be absolute | |
| "Is this appropriate?" | | ✅ Needs judgment |
| "Which limit to apply?" | | ✅ Context-dependent |
| "Priority?" | | ✅ Subjective |

You cannot ask an LLM to enforce a 1000-token limit. It might comply, might not, might misunderstand. Security properties require deterministic code.

But you CAN ask an LLM: "Given this sender's reputation and task complexity, should the limit be 1000 or 10000 tokens?"

This led to our key insight: **soft policy invokes hard limits.**

```python
# Hard limits are functions
def set_max_tokens(n: int) -> str:
    """Set token budget for this task."""
    _limits["max_tokens"] = n
    return f"Max tokens set to {n}"

def set_timeout(seconds: int) -> str:
    """Set time limit for this task."""
    _limits["timeout"] = seconds
    return f"Timeout set to {seconds}s"

# Soft policy is a prompt that calls these functions
TRUST_POLICY = """
You decide resource limits for incoming tasks.

For unknown senders: set_max_tokens(1000), set_timeout(10)
For known contacts with good history: set_max_tokens(10000), set_timeout(60)
For whitelisted agents: set_max_tokens(50000), set_timeout(300)

Always end with accept() or reject().
"""
```

The prompt reasons. The code enforces. Neither alone is sufficient.

---

## Part V: The Trust Agent Trap

We designed a unified trust agent with these tools:

```python
trust_tools = [
    check_reputation,    # Query contact history
    check_whitelist,     # Check explicit allow list
    check_blacklist,     # Check explicit deny list
    set_max_tokens,      # Set token budget
    set_timeout,         # Set time limit
    set_allowed_tools,   # Restrict available tools
    accept,              # Approve the task
    reject,              # Deny the task
]
```

The policy prompt would reason about the context and call appropriate functions. Elegant, flexible, powerful.

Also: overkill for 90% of users.

Most users don't need sophisticated multi-factor trust decisions. They need:

```python
host(agent)  # Just work
```

This is where progressive disclosure became our guiding principle:

```python
# Level 0: Beginner (just works)
host(agent)

# Level 1: Basic control
host(agent, trust="strict")
host(agent, port=9000)

# Level 2: Simple rules (code-enforced)
host(agent, blacklist=["bad_actor_xyz"])
host(agent, whitelist=["partner_abc"])

# Level 3: Custom policy (LLM-interpreted)
host(agent, trust_policy="Only accept from known contacts. Reject tasks over 1000 tokens.")

# Level 4: Full control (custom trust agent)
my_trust = Agent("trust", MY_POLICY, tools=trust_tools)
host(agent, trust_agent=my_trust)
```

Most users stay at Level 0 or 1. Some never leave Level 0. The complexity exists for those who need it, invisible to those who don't.

**Progressive disclosure isn't just UI—it's architecture.** Design systems where the simple path is genuinely simple, not just hiding complexity behind defaults.

---

## Part VI: Should Network Code Live in Agent?

We had `agent.serve()` as a method on the Agent class. It seemed natural.

But the Agent class was growing:
- LLM integration
- Tool execution
- Message history
- Event system
- Trust handling
- And now network serving?

Each feature added methods, state, complexity. The class was becoming a god object.

We asked: what IS an Agent, essentially?

```python
# An agent is a decision maker
class Agent:
    def input(self, prompt: str) -> str:
        """Receive input, reason with tools, return output."""
```

That's the core job. Receive input. Make decisions. Return output.

Does an Agent need to know about TCP? About WebSocket handshakes? About relay servers and NAT traversal?

No. Those are implementation details of a different concern.

**The Agent decides. The network executes.**

```python
# agent.py - Decision maker
class Agent:
    def input(self, prompt): ...  # Core: make decisions

# network.py - Executor
def host(agent): ...    # Make agent available
def ask(peer, task): ...  # Request from another agent
def find(capability): ...  # Discover agents
```

The Agent doesn't know HOW it's hosted. The network module doesn't know HOW decisions are made. Each does one job well.

Benefits:
- Test agents without networks
- Test networks without agents
- Same agent works locally or networked
- Clear mental model

---

## Part VII: Functions Over Classes

Once network operations were separate, we needed to decide their form.

Option A: NetworkManager class
```python
manager = NetworkManager(agent, trust_config, network_config)
manager.serve(port=8000)
manager.connect("peer_xyz")
```

Option B: Plain functions
```python
host(agent)
ask("peer_xyz", "do something")
find("can translate Japanese")
```

We chose functions. Here's why:

**Classes accumulate state.** Each method might depend on internal state set by previous methods. Order matters. Interactions are implicit.

**Functions are explicit.** Everything needed is in the parameters. No hidden state. No implicit order.

**Classes invite configuration.** You add a config object, then config options, then config validation, then config migration...

**Functions invite simplicity.** Pass what you need. Get what you want. Done.

```python
# The entire network API
from connectonion.network import host, ask, find

host(agent)                         # Make available
result = ask("peer", "translate X") # Request from peer
agents = find("translation")        # Discover by capability
```

Three functions. That's it.

---

## Part VIII: Naming the Host Function

What do you call a function that makes an agent available on the network?

| Candidate | Problem |
|-----------|---------|
| `serve(agent)` | Who serves what? Ambiguous subject |
| `listen(agent)` | Listen to what? Usually expects port |
| `run(agent)` | Run locally? On network? Too vague |
| `start(agent)` | Start what? Too generic |
| `launch(agent)` | Implies one-time, not ongoing |
| `publish(agent)` | Sounds like one-time action |
| `expose(agent)` | Less familiar term |

We applied the sentence test:

- "I **host** my agent on the network" ✅ Natural
- "I **serve** my agent on the network" ❓ Awkward
- "I **launch** my agent on the network" ⚠️ Sounds one-time

And the pair test (with `ask` for requesting):

- `host` / `ask`: "I host, you ask" ✅ Symmetric, clear
- `serve` / `request`: "I serve, you request" ⚠️ But serve(agent) is still weird
- `launch` / `ask`: "I launched, you ask" ⚠️ Tense mismatch

`host` won because:
1. **Clear subject**: YOU host the AGENT
2. **Familiar metaphor**: web hosting, hosting a party
3. **Implies continuity**: hosting is ongoing, not one-time
4. **Natural pair**: host/ask is symmetric

**Good names eliminate documentation.** If users need docs to understand what a function does, the name failed.

---

## Part IX: The Final Architecture

After all the exploration, wrong turns, and simplification, here's what we built:

### The Network API (Three Functions)

```python
from connectonion.network import host, ask, find

# Make your agent available
host(agent)

# Ask another agent
result = ask("translator_xyz", "translate: hello world")

# Find agents by capability
translators = find("can translate Japanese to English")
```

### The Host Function (Progressive Disclosure)

```python
def host(
    agent: Agent,

    # Level 1: Basic
    trust: str = "careful",      # "open" | "careful" | "strict"
    port: int = 8000,

    # Level 2: Rules
    blacklist: list = None,      # Always reject these
    whitelist: list = None,      # Always accept these

    # Level 3: Policy
    trust_policy: str = None,    # Natural language policy

    # Level 4: Full control
    trust_agent: Agent = None,   # Custom trust agent
):
```

### The Trust Flow

```
Task arrives
     │
     ▼
┌─────────────────────┐
│ Blacklist check     │──── In blacklist? ──► REJECT
│ (code-enforced)     │
└─────────────────────┘
     │ not in blacklist
     ▼
┌─────────────────────┐
│ Whitelist check     │──── In whitelist? ──► ACCEPT (open limits)
│ (code-enforced)     │
└─────────────────────┘
     │ not in whitelist
     ▼
┌─────────────────────┐
│ Trust agent/policy  │──── Has trust_agent? ──► Agent decides
│ (if configured)     │──── Has trust_policy? ──► LLM decides
└─────────────────────┘
     │ no custom config
     ▼
┌─────────────────────┐
│ Default limits      │──── Apply limits from trust level
│ (code-enforced)     │
└─────────────────────┘
     │
     ▼
Execute with limits
```

### Trust Levels (Predefined Limits)

```python
TRUST_LIMITS = {
    "open": {
        "max_tokens": None,      # Unlimited
        "timeout": None,         # No timeout
        "max_iterations": None,
    },
    "careful": {
        "max_tokens": 10000,
        "timeout": 60,
        "max_iterations": 10,
    },
    "strict": {
        "max_tokens": 1000,
        "timeout": 10,
        "max_iterations": 3,
    },
}
```

---

## Part X: Principles We Discovered

### 1. Local First, Server Optional
Local mode must always work. Server accelerates but never gates functionality.

### 2. Hard Limits in Code, Soft Policy in Prompts
Security-critical properties are code-enforced. Context-dependent judgments can use LLM reasoning.

### 3. Progressive Disclosure Is Architecture
Design systems where `host(agent)` genuinely works—not as a facade hiding complexity, but as a complete solution for simple cases.

### 4. Agent Decides, Module Executes
Keep the Agent class focused on decisions. Network, storage, and other concerns belong in separate modules.

### 5. Functions Over Classes
When unsure, use a function. Classes are for state that truly lives over time, not for grouping related operations.

### 6. Names That Need No Documentation
If you have to explain what a function does, rename it until you don't.

---

## Conclusion

We started with grand ambitions: multiple specialized trust agents, layered verification systems, sophisticated policy engines.

We ended with three functions: `host()`, `ask()`, `find()`.

The journey taught us that complexity is easy. Anyone can add features, options, and flexibility. The hard part is removing them—finding what's essential and letting go of the rest.

A beginner writes `host(agent)` and it works. An expert configures custom trust agents with specialized tools. Both use the same API, both get what they need, neither suffers for the other.

That's what "keep simple things simple, make complicated things possible" actually means in practice.

---

*The best architecture is invisible. It does its job, stays out of your way, and lets you focus on what actually matters. If you're thinking about the architecture while using it, it's not done yet.*
