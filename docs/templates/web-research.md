# Web Research Template

Research and data extraction agent for gathering and analyzing web content.

## Quick Start

```bash
co create researcher --template web-research
cd researcher
pip install requests
python agent.py
```

## What You Get

```
researcher/
├── agent.py            # Research agent with 4 tools
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

| Tool | Description |
|------|-------------|
| `search_web(query)` | Web search (needs API integration) |
| `extract_data(url, data_type)` | Fetch content from URLs |
| `analyze_data(data, analysis_type)` | LLM-powered content analysis |
| `save_research(topic, findings, filename)` | Save findings to JSON |

## Example Usage

```python
# Extract content from URL
result = agent.input("Extract the main content from https://example.com")

# Analyze content
result = agent.input("Analyze this article and summarize the key points")

# Save research
result = agent.input("Save our findings about AI trends to a file")
```

Interactive mode:

```
You: Get the content from this blog post and summarize it
Agent: [Fetches URL content]
       [Analyzes with LLM]
       Here's a summary of the article...

You: Save this research to ai-trends.json
Agent: Research saved to ai-trends.json with timestamp
```

## Use Cases

- Web content extraction
- Research documentation
- Content analysis and summarization
- Data gathering projects
- Knowledge base building

## Dependencies

- `connectonion`
- `requests`
- `python-dotenv`

## Customization

### Add Real Search API

The `search_web` tool is a placeholder. Integrate with search APIs:

```python
import requests

def search_web(query: str) -> str:
    """Search the web using Google Custom Search."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cx = os.getenv("GOOGLE_CX")

    response = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cx, "q": query}
    )
    return response.json()
```

Other search API options:
- Google Custom Search
- Bing Search API
- SerpAPI
- Tavily

### Add More Analysis Types

```python
def analyze_data(data: str, analysis_type: str = "summary") -> str:
    """Analyze data with different strategies."""
    prompts = {
        "summary": "Summarize this content:",
        "sentiment": "Analyze the sentiment:",
        "entities": "Extract key entities:",
        "facts": "List key facts:",
    }
    prompt = prompts.get(analysis_type, prompts["summary"])
    return llm_do(f"{prompt}\n\n{data}")
```

### Structured Output

```python
from typing import Dict, List

def save_research(topic: str, findings: str, filename: str = None) -> Dict:
    """Save research with structured metadata."""
    research = {
        "topic": topic,
        "findings": findings,
        "timestamp": datetime.now().isoformat(),
        "sources": [],  # Add source tracking
        "tags": [],     # Add categorization
    }
    # Save to JSON
    return research
```

## Tips

- Add error handling for failed HTTP requests
- Implement rate limiting for API calls
- Cache results to avoid duplicate requests
- Track sources for citation

## Next Steps

- [Tools](../concepts/tools.md) - Add custom tools
- [llm_do](../concepts/llm_do.md) - One-shot LLM calls
- [Playwright Template](playwright.md) - For dynamic content
