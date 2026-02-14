# image_result_formatter

Automatically formats base64 image results for vision models.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter

agent = Agent("assistant", tools=[take_screenshot], plugins=[image_result_formatter])

agent.input("Take a screenshot and describe what you see")
# 🖼️  Formatted 'take_screenshot' result as image
# Agent can now see and analyze the image visually
```

## How It Works

When a tool returns base64 encoded image data:

1. Detects base64 image in tool result
2. Converts to OpenAI vision format for LLM consumption
3. Sends image to frontend via WebSocket (if hosted with `agent.io`)
4. Allows LLM to see image visually (not as text)

## Supported Formats

- PNG
- JPEG/JPG
- WebP
- GIF

## Detection Patterns

The plugin detects:

```python
# Data URL format
"data:image/png;base64,iVBORw0KGgo..."

# Plain base64 (defaults to PNG)
"iVBORw0KGgoAAAANSUhEUgAA..."
```

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `_format_image_result` | `after_tools` | Format base64 images after all tools complete |

Uses `after_tools` because it modifies messages (see [Event Lifecycle](README.md#why-this-matters)).

## Use Cases

- Screenshot tools (browser automation)
- Image generation tools (charts, QR codes, diagrams)
- Camera/webcam capture
- PDF to image conversion
- Any tool returning visual data

## Hosted Agent Integration

When using with `host()`, images are automatically sent to the frontend:

```python
from connectonion import Agent
from connectonion.network import host
from connectonion.useful_plugins import image_result_formatter

def create_agent():
    return Agent("vision", tools=[take_screenshot], plugins=[image_result_formatter])

# Images will be sent to oo-chat or SDK clients automatically
host(create_agent, port=8000, trust="open")
```

The plugin detects `agent.io` and sends images via WebSocket for real-time display.

## Customizing

Need to modify image_result_formatter's behavior? Copy the source to your project:

```bash
co copy image_result_formatter
```

Then import from your local copy:

```python
# from connectonion.useful_plugins import image_result_formatter  # Before
from plugins.image_result_formatter import image_result_formatter  # After
```
