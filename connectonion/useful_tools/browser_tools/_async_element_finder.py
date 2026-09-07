"""
Purpose: Await DOM extraction and keep model-selected element matching off the browser event loop.
LLM-Note:
  Dependencies: asyncio plus the existing synchronous element_finder rules | imported by [_async_browser.py] | tested by [tests/unit/test_async_element_finder.py, tests/e2e/test_async_browser_core_real_driver.py]
  Data flow: async Page.evaluate(extract_elements.js) → InteractiveElement inventory → worker-thread element_finder.find_element → selected pre-built locator/coordinates
  State/Effects: injects data-browser-agent-id through the shared extraction script | writes ~/.co/debug/elements.json in a worker | synchronous provider call continues in its worker if the awaiting task is cancelled
  Integration: preserves the existing prompt, schemas, ambiguity errors, and selection rules; this module owns only the async scheduling boundary
  Errors: page and debug I/O errors bubble | no elements returns None through the existing matcher | model ambiguity/non-match errors remain ElementNotFoundError

Async DOM extraction with the established element-matching contract.

The matcher remains synchronous because it calls ``llm_do``. Run it in a
worker thread so a slow model response does not stall every browser tab on the
shared event loop. Cancellation stops waiting for the result, although Python
cannot forcibly stop the already-running worker thread.
"""

import asyncio
import json
from pathlib import Path
from typing import List

from . import element_finder as rules


def _write_debug_elements(raw) -> None:
    debug_dir = Path.home() / ".co" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "elements.json").write_text(
        json.dumps(raw, indent=2), encoding="utf-8"
    )


async def extract_elements(page) -> List[rules.InteractiveElement]:
    """Await extraction and keep the synchronous finder's debug artifact."""
    raw = await page.evaluate(rules._get_extract_js())
    await asyncio.to_thread(_write_debug_elements, raw)

    main_elements = [element for element in raw if element.get("frame") == "main"]
    other_elements = [element for element in raw if element.get("frame") != "main"]
    frame_names = {element.get("frame") for element in other_elements}
    print(
        "\n[element_finder] Extracted "
        f"{len(raw)} elements (main: {len(main_elements)}, "
        f"other: {len(other_elements)} [{', '.join(frame_names)}])"
    )
    return [rules.InteractiveElement(**element) for element in raw]


async def find_element(page, description: str, elements=None):
    """Select an extracted element without blocking the browser event loop."""
    if elements is None:
        elements = await extract_elements(page)
    return await asyncio.to_thread(rules.find_element, None, description, elements)
