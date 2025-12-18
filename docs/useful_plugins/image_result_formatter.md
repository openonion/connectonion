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
2. Converts to OpenAI vision format
3. Allows LLM to see image visually (not as text)

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

- Screenshot tools
- Image generation tools
- Camera/webcam capture
- PDF to image conversion
- Any tool returning visual data

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
