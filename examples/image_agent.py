"""
Example agent that demonstrates sending and receiving images.

This example shows:
1. Receiving images from the user (via images parameter)
2. Sending images back to the user (via agent.io.send_image())

Usage:
    # As a hosted agent with WebSocket
    python examples/image_agent.py

    # Then connect via oo-chat or TypeScript SDK client
"""

import base64
from pathlib import Path
from connectonion import Agent
from connectonion.network import host


def generate_placeholder_image() -> str:
    """Generate a tiny 1x1 red PNG as base64 data URL.

    In a real app, you might:
    - Generate charts/plots with matplotlib
    - Create QR codes
    - Render diagrams
    - Return screenshots from browser automation
    """
    # 1x1 red pixel PNG (base64)
    red_pixel = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\r\xa2\x00\x00\x00\x00IEND\xaeB`\x82'
    encoded = base64.b64encode(red_pixel).decode('ascii')
    return f"data:image/png;base64,{encoded}"


def describe_image(image_data: str, agent: Agent) -> str:
    """Tool for describing images received from the user.

    Args:
        image_data: Base64-encoded image data URL
        agent: Agent instance (auto-injected for io access)

    Returns:
        Description of the image
    """
    # In a real app, you might use vision API like GPT-4V or Claude Vision
    # For this example, we just detect the format
    if image_data.startswith("data:image/png"):
        return "Received a PNG image"
    elif image_data.startswith("data:image/jpeg"):
        return "Received a JPEG image"
    elif image_data.startswith("data:image/"):
        format = image_data.split(";")[0].split("/")[1]
        return f"Received a {format.upper()} image"
    else:
        return "Received an unknown format"


def send_red_pixel(agent: Agent) -> str:
    """Tool for sending a test image to the user.

    Args:
        agent: Agent instance (auto-injected for io access)

    Returns:
        Confirmation message
    """
    if agent.io:
        image_data = generate_placeholder_image()
        agent.io.send_image(image_data)
        return "Sent a 1x1 red pixel image"
    else:
        return "Cannot send image: no IO connection (not hosted)"


def create_agent():
    """Create an agent that can send and receive images."""
    return Agent(
        name="image_agent",
        model="gpt-4o-mini",
        system_prompt="""You are a helpful assistant that can work with images.

You have two tools:
1. describe_image() - Analyze images sent by the user
2. send_red_pixel() - Send a test image to the user

When users send images, use describe_image() to analyze them.
When asked to send images, use send_red_pixel() as a demonstration.

In a real application, you might:
- Generate charts with matplotlib
- Create QR codes
- Render diagrams with graphviz
- Capture screenshots
- Process and return modified images
""",
        tools=[describe_image, send_red_pixel]
    )


if __name__ == "__main__":
    # Host the agent on port 8000
    # Connect via:
    # - oo-chat: https://chat.openonion.ai/<address>
    # - TypeScript SDK: connect('<address>')
    # - Python SDK: connect('<address>')

    print("Starting image agent...")
    print("Try these prompts:")
    print("  - Send me an image")
    print("  - (Upload an image and say) What is this?")
    print()

    host(
        create_agent,
        port=8000,
        trust="open",
    )
