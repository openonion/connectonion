# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **natural language browser automation agent** built with ConnectOnion and Playwright. It transforms natural language commands like "go to Google and search for AI news" into executable browser actions. The agent follows the ConnectOnion philosophy: "Keep simple things simple, make complicated things possible."

## Core Architecture

### Two-Layer Design

1. **Web Automation Layer** (`web_automation.py`):
   - `WebAutomation` class provides browser control primitives
   - All methods decorated with `@xray` for behavior tracking
   - AI-powered element finding using `find_element_by_description()`
   - Form handling, screenshots, navigation, data extraction

2. **Agent Layer** (`agent.py`):
   - ConnectOnion Agent orchestrates tool calls
   - Natural language understanding via LLM (gemini-2.5-flash by default)
   - System prompt defines agent personality (`prompt.md`)
   - Interactive CLI and automated task modes

### Key Design Pattern

**Functions as Tools**: All `WebAutomation` methods automatically become agent tools. No manual tool registration needed - just pass the class instance:

```python
web = WebAutomation()
agent = Agent(
    name="playwright_agent",
    tools=web,  # All methods become tools
    max_iterations=20
)
```

## Development Commands

### Setup
```bash
# Install dependencies
pip install python-dotenv playwright connectonion
playwright install

# Authenticate with ConnectOnion (creates .env with OPENONION_API_KEY)
co auth
```

### Running the Agent

```bash
# Interactive mode - starts a chat session
python agent.py

# Automated task from command line
python agent.py "Open browser, go to news.ycombinator.com, take a screenshot"
```

### Testing

```bash
# Run complete test suite (4 tests: auth, browser, agent control, search)
python tests/test_all.py

# Run from project root
python -m tests.test_all

# Individual test files
python tests/direct_test.py
```

## Key Implementation Details

### Natural Language Element Finding (browser-use inspired)

Architecture in `dom_service.py`:
1. JavaScript injects `data-browser-agent-id` attribute into each interactive element
2. Extract elements with bounding boxes and text content
3. LLM SELECTS from indexed list (by index), never GENERATES CSS selectors
4. Click using the injected attribute: `[data-browser-agent-id="42"]`
5. Coordinate-based clicking as fallback (fresh bounding box from locator)

Why this approach?
- LLMs generate invalid CSS like `:contains()` (jQuery, not valid CSS)
- Pre-built locators are guaranteed to work
- Injected IDs are unique and stable during the session

### Visual Debugging

`highlight_screenshot.py` provides browser-use style visual debugging:
- Takes screenshot with colored bounding boxes around interactive elements
- Index numbers displayed on each element
- Different colors for different element types (buttons=red, inputs=teal, links=green)

```python
# Generate highlighted screenshot
path = highlight_screenshot.highlight_current_page(web.page)
```

### AI-Powered Tools Pattern

The agent uses ConnectOnion's `llm_do()` helper for intelligent operations:
- `dom_service.find_element()`: Find element from indexed list (LLM selects, not generate CSS)
- `analyze_page()`: Answer questions about page content
- `smart_fill_form()`: Generate appropriate form values from user info

These tools combine traditional automation (Playwright) with AI reasoning.

### Screenshot Workflow

Per `prompt.md` guidelines, the agent should:
1. Take screenshots after navigation
2. Take screenshots of empty forms before filling
3. Take screenshots after filling forms
4. Take screenshots after submission
5. Save all screenshots to `screenshots/` directory (auto-created)

### Browser Lifecycle

- Browser opens on first navigation command
- Stays open during interactive sessions
- Auto-closes at end of automated tasks
- Manual close via `close()` tool or "Close the browser" command

## Environment Configuration

### Required
```bash
# Created automatically by `co auth`
OPENONION_API_KEY=your_token_here
```

### ConnectOnion Project Metadata
- Stored in `.co/config.toml`
- Agent address, email, default model settings
- Do not modify manually - managed by `co` CLI

## Code Patterns to Follow

### Adding New Browser Tools

1. Add method to `WebAutomation` class
2. Decorate with `@xray` for behavior tracking
3. Return descriptive strings, not just success/failure
4. Handle `self.page is None` gracefully

Example:
```python
@xray
def hover_over(self, description: str) -> str:
    """Hover over an element using natural language description."""
    if not self.page:
        return "Browser not open"

    try:
        selector = self.find_element_by_description(description)
        if selector.startswith("Could not"):
            return selector

        self.page.hover(selector)
        return f"Hovered over '{description}'"
    except Exception as e:
        return f"Hover failed: {str(e)}"
```

### Error Handling Philosophy

From global CLAUDE.md: Try-except is sometimes over-engineering. Only catch exceptions when you need to provide user-friendly error messages. Otherwise, let errors bubble up to the agent for retry.

### Model Selection

- Default: `gemini-2.5-flash` (fast, cost-effective)
- For complex HTML analysis: `co/gpt-4o` (higher accuracy)
- For testing: `co/o4-mini` (cheapest option)
- All models use ConnectOnion managed keys (`co/` prefix)

## Testing Strategy

### Test Structure (`tests/test_all.py`)

Four-stage validation:
1. **Authentication**: Verify ConnectOnion tokens work
2. **Direct Browser**: Test `WebAutomation` methods directly
3. **Agent Browser**: Test agent tool orchestration
4. **Google Search**: End-to-end complex workflow

Each test is independent and reports pass/fail clearly.

### Adding New Tests

Follow the pattern:
```python
def test_feature_name():
    """Test 5: Description of what this tests."""
    print("\n5️⃣  Testing Feature Name")
    print("-" * 40)

    try:
        # Setup
        web = WebAutomation()
        agent = Agent(name="test", model="co/o4-mini", tools=web)

        # Execute
        result = agent.input("task description")
        print(f"✅ Success: {result[:100]}...")

        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
```

Then add to `tests` list in `main()`.

## Project Structure

```
browser-agent/
├── agent.py              # Main entry point, Agent setup, CLI
├── web_automation.py     # WebAutomation class, all browser tools
├── element_finder.py     # Element extraction + LLM matching (clean Python)
├── highlight_screenshot.py # Visual debugging with colored bounding boxes
├── scroll.py             # Unified scroll with AI + fallback (~100 lines)
├── prompts/             # LLM prompts (separated from code)
│   ├── agent.md         # Agent system prompt
│   ├── element_matcher.md # Element matching prompt
│   ├── scroll_strategy.md # AI scroll strategy prompt
│   └── form_filler.md   # Smart form filling prompt
├── scripts/             # JavaScript files
│   └── extract_elements.js # DOM extraction with injected IDs
├── tests/
│   ├── test_all.py      # Complete test suite (recommended)
│   ├── test_element_finder.py # Element finder + click test
│   ├── test_direct.py   # Direct browser tests
│   └── README.md        # Test documentation
├── .co/
│   ├── config.toml      # ConnectOnion project config
│   ├── evals/           # Eval logs (YAML format)
│   └── keys/            # Agent keypair (gitignored)
├── screenshots/         # Auto-generated screenshots (gitignored)
└── .env                 # API keys (gitignored, created by co auth)
```

## Common Workflows

### Interactive Session
```python
python agent.py
# User types: "Go to example.com and take a screenshot"
# Agent opens browser → navigates → screenshots → reports
```

### Automated Task
```python
python agent.py "Fill out the contact form at example.com/contact with name: John Doe, email: john@example.com"
# Agent completes full workflow → closes browser → exits
```

### Adding Custom Tools
```python
# In web_automation.py
@xray
def scroll_to_bottom(self) -> str:
    """Scroll to the bottom of the page."""
    if not self.page:
        return "Browser not open"
    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    return "Scrolled to bottom"

# Agent automatically uses this when user says "scroll down"
```

## Important Behaviors

### Agent Philosophy (from prompt.md)
- **Understand intent, not syntax**: "sign in to GitHub" means navigate + find button + click
- **Report what you do**: Clear status updates at each step
- **Handle errors gracefully**: Try alternatives before giving up
- **Be proactive**: Take screenshots, extract data automatically

### What NOT to Do
- Don't expose CSS selectors to users
- Don't ask users for technical details
- Don't leave browsers open after automated tasks
- Don't use try-except everywhere (see philosophy above)

## Troubleshooting

### "No authentication token found"
Run `co auth` - this creates `.env` with `OPENONION_API_KEY`

### "Playwright not installed"
```bash
pip install playwright
playwright install
```

### Browser doesn't appear
- Tests run in headless mode by default
- For debugging: `WebAutomation(headless=False)` in agent.py

### Element not found errors
- AI element finder works ~80% of time
- Falls back to text matching automatically
- Complex dynamic sites may need custom selectors

## Design Philosophy Alignment

This project embodies ConnectOnion principles:

1. **Simple things simple**: `agent.input("search for AI news")` just works
2. **Complicated things possible**: Custom tools, AI-powered selectors, multi-step workflows
3. **Functions as primitives**: All tools are just Python methods
4. **Behavior tracking**: `@xray` decorator logs all actions to `~/.connectonion/`

The user should feel like they're talking to a helpful assistant, not programming a robot.
