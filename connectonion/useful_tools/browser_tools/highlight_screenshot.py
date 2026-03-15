"""
Purpose: Draw bounding boxes and element indices on screenshots for visual element identification
LLM-Note:
  Dependencies: imports from [PIL Image/ImageDraw/ImageFont, pathlib, cli/browser_agent/element_finder] | imported by [cli/browser_agent/browser.py] | tested by [tests/cli/test_highlight.py]
  Data flow: highlight_screenshot(screenshot_path, elements) → loads PNG image → iterates InteractiveElement list → draws dashed rectangle around each element → draws index label with colored background → saves highlighted image | highlight_current_page(page) → takes screenshot → extracts elements → calls highlight_screenshot() → returns path
  State/Effects: reads screenshot PNG from disk | writes highlighted PNG to disk | deletes raw screenshot after highlighting | creates screenshots/ directory if missing
  Integration: exposes highlight_screenshot(screenshot_path, elements, output_path) → str, highlight_current_page(page, output_path) → str | ELEMENT_COLORS dict maps tag names to hex colors | get_font(size) → ImageFont for cross-platform text rendering | draw_dashed_rect() utility for styled boxes
  Performance: PIL image processing (fast for typical webpage screenshots) | processes all elements in one pass | minimal memory (single image in RAM)
  Errors: skips elements with width/height < 5px (too small to render) | falls back to default font if system fonts unavailable | raises if PIL/Pillow not installed
Screenshot highlighting - draw bounding boxes and indices on screenshots.
Inspired by browser-use's python_highlights.py approach.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import List
from . import element_finder

# Color scheme for different element types
ELEMENT_COLORS = {
    'button': '#FF6B6B',  # Red
    'input': '#4ECDC4',   # Teal
    'select': '#45B7D1',  # Blue
    'a': '#96CEB4',       # Green
    'textarea': '#FF8C42', # Orange
    'div': '#DDA0DD',     # Light purple
    'span': '#FFD93D',    # Yellow
    'default': '#9B59B6', # Purple
}


def get_font(size: int = 14):
    """Get a cross-platform font."""
    font_paths = [
        '/System/Library/Fonts/Arial.ttf',  # macOS
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
        'C:\\Windows\\Fonts\\arial.ttf',  # Windows
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_dashed_rect(draw: ImageDraw.Draw, bbox: tuple, color: str, dash: int = 4, gap: int = 4):
    """Draw a dashed rectangle."""
    x1, y1, x2, y2 = bbox

    def draw_dashed_line(start, end, is_horizontal: bool):
        if is_horizontal:
            x, y = start
            while x < end[0]:
                end_x = min(x + dash, end[0])
                draw.line([(x, y), (end_x, y)], fill=color, width=2)
                x += dash + gap
        else:
            x, y = start
            while y < end[1]:
                end_y = min(y + dash, end[1])
                draw.line([(x, y), (x, end_y)], fill=color, width=2)
                y += dash + gap

    # Draw four sides
    draw_dashed_line((x1, y1), (x2, y1), True)   # Top
    draw_dashed_line((x2, y1), (x2, y2), False)  # Right
    draw_dashed_line((x1, y2), (x2, y2), True)   # Bottom
    draw_dashed_line((x1, y1), (x1, y2), False)  # Left


def highlight_screenshot(
    screenshot_path: str,
    elements: List[element_finder.InteractiveElement],
    output_path: str = None
) -> str:
    """Draw bounding boxes and indices on a screenshot.

    Args:
        screenshot_path: Path to the screenshot image
        elements: List of InteractiveElement objects with bounding boxes
        output_path: Optional output path (defaults to {original}_highlighted.png)

    Returns:
        Path to the highlighted screenshot
    """
    # Load image
    image = Image.open(screenshot_path).convert('RGBA')
    draw = ImageDraw.Draw(image)
    font = get_font(14)
    small_font = get_font(11)

    for el in elements:
        # Skip elements with no size
        if el.width < 5 or el.height < 5:
            continue

        # Get color based on tag
        color = ELEMENT_COLORS.get(el.tag, ELEMENT_COLORS['default'])

        # Calculate bounding box
        x1, y1 = el.x, el.y
        x2, y2 = el.x + el.width, el.y + el.height

        # Draw dashed bounding box
        draw_dashed_rect(draw, (x1, y1, x2, y2), color)

        # Draw index label
        label = str(el.index)
        bbox = draw.textbbox((0, 0), label, font=font)
        label_w = bbox[2] - bbox[0]
        label_h = bbox[3] - bbox[1]
        padding = 3

        # Position: top-center of element, or above if small
        label_x = x1 + (el.width - label_w) // 2 - padding
        if el.height < 40:
            label_y = max(0, y1 - label_h - padding * 2 - 2)
        else:
            label_y = y1 + 2

        # Draw label background
        draw.rectangle(
            [label_x, label_y,
             label_x + label_w + padding * 2,
             label_y + label_h + padding * 2],
            fill=color,
            outline='white',
            width=1
        )

        # Draw label text
        draw.text(
            (label_x + padding, label_y + padding),
            label,
            fill='white',
            font=font
        )

    # Save output
    if not output_path:
        p = Path(screenshot_path)
        output_path = str(p.parent / f"{p.stem}_highlighted{p.suffix}")

    image.save(output_path)
    return output_path


def highlight_current_page(page, output_path: str = "screenshots/highlighted.png") -> str:
    """Take a screenshot and highlight all interactive elements.

    Args:
        page: Playwright page object
        output_path: Path to save the highlighted screenshot

    Returns:
        Path to the highlighted screenshot
    """
    import os
    from datetime import datetime

    # Ensure directory exists
    os.makedirs("screenshots", exist_ok=True)

    # Take screenshot
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = f"screenshots/raw_{timestamp}.png"
    page.screenshot(path=screenshot_path)

    # Extract elements
    elements = element_finder.extract_elements(page)

    # Generate output path
    output_path = f"screenshots/highlighted_{timestamp}.png"

    # Create highlighted version
    result = highlight_screenshot(screenshot_path, elements, output_path)

    # Clean up raw screenshot
    os.remove(screenshot_path)

    return result
