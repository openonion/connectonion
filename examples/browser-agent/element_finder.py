"""
Element Finder - Find interactive elements by natural language description.

Inspired by browser-use (https://github.com/browser-use/browser-use).

Architecture:
1. JavaScript injects `data-browser-agent-id` into each interactive element
2. LLM SELECTS from indexed element list, never GENERATES CSS selectors
3. Pre-built locators are guaranteed to work

Usage:
    elements = extract_elements(page)
    element = find_element(page, "the login button", elements)
    page.locator(element.locator).click()
"""

from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from connectonion import llm_do


# Load JavaScript and prompt from files
_BASE_DIR = Path(__file__).parent
_EXTRACT_JS = (_BASE_DIR / "scripts" / "extract_elements.js").read_text()
_ELEMENT_MATCHER_PROMPT = (_BASE_DIR / "prompts" / "element_matcher.md").read_text()


class InteractiveElement(BaseModel):
    """An interactive element on the page with pre-built locator."""
    index: int
    tag: str
    text: str = ""
    role: Optional[str] = None
    aria_label: Optional[str] = None
    placeholder: Optional[str] = None
    input_type: Optional[str] = None
    href: Optional[str] = None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    locator: str = ""


class ElementMatch(BaseModel):
    """LLM's element selection result."""
    index: int = Field(..., description="Index of the matching element")
    confidence: float = Field(..., description="Confidence 0-1")
    reasoning: str = Field(..., description="Why this element matches")


def extract_elements(page) -> List[InteractiveElement]:
    """Extract all interactive elements from the page.

    Returns elements with:
    - Bounding boxes (for position matching with screenshot)
    - Pre-built Playwright locators (guaranteed to work)
    - Text/aria/placeholder for LLM matching
    """
    raw = page.evaluate(_EXTRACT_JS)
    return [InteractiveElement(**el) for el in raw]


def format_elements_for_llm(elements: List[InteractiveElement], max_count: int = 150) -> str:
    """Format elements as compact list for LLM context.

    Format: [index] tag "text" pos=(x,y) {extra info}
    """
    lines = []
    for el in elements[:max_count]:
        parts = [f"[{el.index}]", el.tag]

        if el.text:
            parts.append(f'"{el.text}"')
        elif el.placeholder:
            parts.append(f'placeholder="{el.placeholder}"')
        elif el.aria_label:
            parts.append(f'aria="{el.aria_label}"')

        parts.append(f"pos=({el.x},{el.y})")

        if el.input_type and el.tag == 'input':
            parts.append(f"type={el.input_type}")

        if el.role:
            parts.append(f"role={el.role}")

        if el.href:
            href_short = el.href.split('?')[0][-30:]
            parts.append(f"href=...{href_short}")

        lines.append(' '.join(parts))

    return '\n'.join(lines)


def find_element(
    page,
    description: str,
    elements: List[InteractiveElement] = None
) -> Optional[InteractiveElement]:
    """Find an interactive element by natural language description.

    This is the core function. LLM SELECTS from pre-built options.

    Args:
        page: Playwright page
        description: Natural language like "the login button" or "email field"
        elements: Pre-extracted elements (will extract if not provided)

    Returns:
        Matching InteractiveElement with pre-built locator, or None
    """
    if elements is None:
        elements = extract_elements(page)

    if not elements:
        return None

    element_list = format_elements_for_llm(elements)

    # Build prompt from template
    prompt = _ELEMENT_MATCHER_PROMPT.format(
        description=description,
        element_list=element_list
    )

    result = llm_do(
        prompt,
        output=ElementMatch,
        model="co/gemini-2.5-flash",
        temperature=0.1
    )

    if 0 <= result.index < len(elements):
        return elements[result.index]

    return None
