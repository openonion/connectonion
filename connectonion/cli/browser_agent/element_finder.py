"""
Purpose: Find interactive elements on web pages using natural language descriptions via vision LLM
LLM-Note:
  Dependencies: imports from [playwright.sync_api Page, connectonion llm_do, pydantic, pathlib] | imported by [cli/browser_agent/browser.py] | tested by [tests/cli/test_element_finder.py]
  Data flow: extract_elements(page) → evaluates extract_elements.js → injects data-browser-agent-id on all interactive elements → returns list[InteractiveElement] with locators | find_element(page, description, elements) → formats elements for LLM → calls llm_do with vision model + screenshot → LLM selects matching element by index → returns InteractiveElement with pre-built locator
  State/Effects: modifies DOM by injecting data-browser-agent-id attributes (temporary, removed on navigation) | takes screenshot for vision analysis | no persistent state
  Integration: exposes extract_elements(page) → list[InteractiveElement], find_element(page, description, elements, screenshot) → InteractiveElement|None, highlight_element(page, element) for visual feedback | InteractiveElement model has tag, text, role, aria_label, placeholder, x, y, width, height, locator | ElementMatch model for LLM response
  Performance: JavaScript extraction is fast | LLM matching uses vision model (slower) | pre-built locators (no retry needed)
  Errors: returns None if no matching element found | raises if Playwright page not available | element may be stale if page navigates
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
import json
import os


# Base directory for loading scripts and prompts
_BASE_DIR = Path(__file__).parent

# Reload prompts on each use (so changes are picked up without restart)
def _get_extract_js():
    """Load extract_elements.js fresh each time (no caching for development)."""
    return (_BASE_DIR / "scripts" / "extract_elements.js").read_text()

def _get_element_matcher_prompt():
    """Load element_matcher.md fresh each time (no caching for development)."""
    return (_BASE_DIR / "prompts" / "element_matcher.md").read_text()


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
    raw = page.evaluate(_get_extract_js())

    # Debug: Write all elements to file for inspection
    debug_dir = Path.home() / ".co" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / "elements.json"

    with open(debug_file, 'w') as f:
        json.dump(raw, f, indent=2)

    print(f"\n[element_finder] DEBUG: Extracted {len(raw)} raw elements from page")
    print(f"[element_finder] DEBUG: Wrote all elements to {debug_file}")

    # Show elements with placeholders
    placeholders = [el for el in raw if el.get('placeholder')]
    if placeholders:
        print(f"[element_finder] DEBUG: Found {len(placeholders)} elements with placeholders:")
        for el in placeholders[:5]:
            print(f"  - [{el['index']}] {el['tag']} placeholder=\"{el['placeholder']}\" at ({el['x']},{el['y']})")
    else:
        print("[element_finder] DEBUG: No elements with placeholder attribute found!")

    return [InteractiveElement(**el) for el in raw]


def format_elements_for_llm(elements: List[InteractiveElement]) -> str:
    """Format elements as compact list for LLM context.

    Format: [index] tag "text" pos=(x,y) {extra info}
    """
    lines = []
    for el in elements:
        parts = [f"[{el.index}]", el.tag]

        # Show text if present
        if el.text:
            parts.append(f'"{el.text}"')

        # ALWAYS show placeholder and aria-label if they exist (important for matching!)
        if el.placeholder:
            parts.append(f'placeholder="{el.placeholder}"')
        if el.aria_label:
            parts.append(f'aria="{el.aria_label}"')

        parts.append(f"pos=({el.x},{el.y})")

        # Show all available attributes that help with matching
        if el.input_type:
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

    # Debug: print element count
    print(f"\n[element_finder] DEBUG: Formatted {len(elements)} elements for LLM matching")

    # Build prompt from template
    prompt = _get_element_matcher_prompt().format(
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
        selected = elements[result.index]
        # Debug logging
        print(f"[element_finder] Looking for: '{description}'")
        print(f"[element_finder] Selected: [{selected.index}] {selected.tag} '{selected.text}' at ({selected.x},{selected.y})")
        print(f"[element_finder] Reasoning: {result.reasoning}")
        return selected

    return None
