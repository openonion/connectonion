# You.com Search Integration

The You.com search integration provides ConnectOnion agents with current web search, URL content extraction, and research synthesis capabilities through the You.com API.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools import YoucomSearch

# Create agent with You.com search
search = YoucomSearch()
agent = Agent("researcher", tools=[search])

# Agent can now search the web for current information
result = agent.input("What are the latest developments in AI?")
```

## Features

- **Web Search**: Current web search with snippets, titles, and URLs
- **Content Extraction**: Extract and parse content from specific URLs  
- **Research Synthesis**: One-shot cited research with source attribution (requires API key)
- **Graceful Fallback**: Falls back to free search when authentication fails
- **Safety**: Handles rate limits, payment challenges, and network errors

## Environment Variables

### `YDC_API_KEY` (Optional)
Your You.com API key for authenticated access and full features.

```bash
export YDC_API_KEY="your-api-key-here"
```

**Without API key**: Basic free search functionality
**With API key**: Full search, content extraction, and research synthesis

### `YOUCOM_BASE_URL` (Optional) 
Override the API base URL (default: `https://api.you.com`)

```bash
export YOUCOM_BASE_URL="https://custom.api.com"
```

## Methods

### `search(query, count=10, safesearch='moderate', freshness=None, livecrawl=None)`

Search the web for current information.

**Parameters:**
- `query` (str): Search query string
- `count` (int): Number of results (1-20, default: 10)
- `safesearch` (str): Filter ('strict', 'moderate', 'off', default: 'moderate') 
- `freshness` (str): Time filter ('day', 'week', 'month', 'year', optional)
- `livecrawl` (str): Live crawl mode ('web' for full content, optional)

**Returns:** JSON string with search results

```python
# Basic search
agent.input("Search for recent AI breakthroughs")

# Search with filters  
agent.input("Search for 'climate change' from the past week")
```

### `get_contents(urls, include_raw_html=False)`

Extract content from specific URLs.

**Parameters:**
- `urls` (str or list): URL(s) to extract content from (max 10)
- `include_raw_html` (bool): Include raw HTML in response (default: False)

**Returns:** JSON string with extracted content and metadata

```python
# Extract content from URLs
agent.input("Get the content from https://example.com and summarize it")

# Multiple URLs
agent.input("Compare the content from these URLs: https://site1.com, https://site2.com")
```

### `research(query, count=10)`

Get cited research synthesis (requires API key).

**Parameters:**
- `query` (str): Research question or topic
- `count` (int): Number of sources to synthesize (1-20, default: 10)

**Returns:** JSON string with synthesized research and citations

```python
# Requires YDC_API_KEY
agent.input("Research the current state of renewable energy adoption")
```

## Error Handling

The integration gracefully handles various error conditions:

- **Authentication Required**: Falls back to free search when possible
- **Payment Required (402)**: Supports x402-aware clients for payment challenges  
- **Rate Limiting**: Returns clear error messages with retry suggestions
- **Network Errors**: Provides helpful debugging information

## Usage Examples

### Research Agent

```python
from connectonion import Agent
from connectonion.useful_tools import YoucomSearch

def create_researcher():
    search = YoucomSearch()
    return Agent(
        name="researcher",
        system_prompt="""You are a research assistant with web search capabilities.
        Use search for current information and always cite your sources.""",
        tools=[search]
    )

agent = create_researcher()
result = agent.input("What are the latest trends in sustainable technology?")
```

### Content Analyst

```python
def create_analyst():
    search = YoucomSearch()
    return Agent(
        name="analyst", 
        system_prompt="""You analyze web content and provide insights.
        Extract content from URLs and provide detailed analysis.""",
        tools=[search]
    )

agent = create_analyst()
result = agent.input("Analyze the content at https://docs.example.com")
```

### Current Events Assistant

```python
def create_news_assistant():
    search = YoucomSearch()
    return Agent(
        name="news_assistant",
        system_prompt="""You provide current news and event information.
        Use web search for the most recent information.""",
        tools=[search]
    )

agent = create_news_assistant()
result = agent.input("What happened in tech news today?")
```

## Integration with ConnectOnion Features

### With Approval System

```python
from connectonion.useful_plugins import tool_approval

agent = Agent(
    "careful_researcher",
    tools=[YoucomSearch()], 
    plugins=[tool_approval]
)
# Web searches will require approval before execution
```

### With Skills System

Create a research skill in `.co/skills/web-research/SKILL.md`:

```markdown
# Web Research Skill

Use You.com search to conduct thorough web research on any topic.

## Usage
/research [topic] - Comprehensive research with citations
/search [query] - Quick web search  
/analyze [url] - Extract and analyze URL content
```

### With Memory

```python
from connectonion.useful_tools import Memory

agent = Agent(
    "persistent_researcher",
    tools=[YoucomSearch(), Memory()],
    system_prompt="Remember previous research and build on it."
)
```

## API Compatibility

This integration follows the You.com API patterns from the official MCP servers:

- Compatible with `you-web`, `you-search`, and `you-contents` MCP tools
- Supports x402 payment challenges for advanced features
- Falls back gracefully when authentication is unavailable
- Follows You.com's rate limiting and usage guidelines

## Security Considerations

- API keys are loaded from environment variables only
- No API keys are logged or exposed in error messages
- All web content is treated as untrusted external data
- Network requests include appropriate User-Agent headers
- Respects You.com's terms of service and rate limits

## Troubleshooting

### "auth_required" errors
Set the `YDC_API_KEY` environment variable with your You.com API key.

### "payment_required" responses  
Some queries require payment. If you have an x402-aware MCP client, it will handle payment automatically.

### "network_error" responses
Check your internet connection and ensure `https://api.you.com` is accessible.

### Free search limitations
Without an API key, you'll have access to basic search only. Content extraction and research synthesis require authentication.