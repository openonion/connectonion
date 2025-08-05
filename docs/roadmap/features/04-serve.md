# serve

Share your agents with one command.

## Usage

```bash
# Make your agents available
$ connectonion serve my_agent.py

Serving 2 agents:
- translate() on port 8001
- summarize() on port 8001
Other agents can now discover you!
```

## Auto-discovery

```python
# my_agent.py
from connectonion import agent

@agent
def process_data(data: dict) -> dict:
    """I process data efficiently"""
    return transformed_data

@agent
def analyze_text(text: str) -> dict:
    """I analyze text for insights"""
    return analysis
```

```bash
$ connectonion serve my_agent.py
# Both functions automatically available
```

## Serve Options

```bash
# Local network only (default)
$ connectonion serve agent.py

# Specific port
$ connectonion serve agent.py --port 9000

# With monitoring dashboard
$ connectonion serve agent.py --dashboard

# Production mode
$ connectonion serve agent.py --production
```

## Docker Support

```dockerfile
FROM python:3.11
COPY my_agent.py .
RUN pip install connectonion
CMD ["connectonion", "serve", "my_agent.py"]
```