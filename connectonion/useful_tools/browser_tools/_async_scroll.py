"""
Purpose: Preserve browser scroll strategy behavior without blocking the AsyncBrowserCore event loop.
LLM-Note:
  Dependencies: asyncio plus synchronous scroll.py rules/schema/prompt and _async_humanize | imported by [_async_browser.py] | tested by [tests/unit/test_async_scroll.py, tests/e2e/test_async_browser_core_real_driver.py]
  Data flow: awaited before screenshot → human wheel / worker-thread model strategy / element JS / page JS → awaited after screenshot → worker-thread pixel comparison → exact strategy result
  State/Effects: writes uniquely named screenshots under the runtime screenshot directory | dispatches trusted wheel input first | fallback JavaScript mutates element/window scroll position
  Integration: reuses scroll.ScrollStrategy, prompt, llm_do call shape, screenshot threshold, strategy order, and public result strings
  Errors: each strategy error is reported and falls through | cancellation is never swallowed and stops remaining mutations | all failed strategies return the existing failure string

The synchronous scroll module contains reusable policy but also synchronous Page
calls, sleeps, screenshots, model I/O, and image I/O. This module keeps the policy
while giving every blocking boundary an explicit async execution path.
"""

import asyncio
import random
import uuid
from pathlib import Path

from . import _async_humanize as humanize
from . import scroll as rules

_pause = asyncio.sleep


async def scroll(
    page,
    take_screenshot,
    times: int = 5,
    description: str = "the main content area",
    screenshots_dir: Path = Path("screenshots"),
) -> str:
    """Try the established scroll strategies in order and verify each visually."""
    if not page:
        return "Browser not open"

    capture_id = uuid.uuid4().hex
    before = f"scroll_before_{capture_id}.png"
    await take_screenshot(path=before)
    strategies = [
        ("Human wheel", lambda: _human_scroll(page, times)),
        ("AI strategy", lambda: _ai_scroll(page, times, description)),
        ("Element scroll", lambda: _element_scroll(page, times)),
        ("Page scroll", lambda: _page_scroll(page, times)),
    ]

    for attempt, (name, execute) in enumerate(strategies, start=1):
        print(f"  Trying: {name}...")
        try:
            await execute()
            await _pause(0.5)
            after = f"scroll_after_{capture_id}_{attempt}.png"
            await take_screenshot(path=after)
            changed = await asyncio.to_thread(
                _screenshots_different,
                before,
                after,
                screenshots_dir,
            )
            if changed:
                print(f"  ✅ {name} worked")
                return f"Scrolled using {name}"
            print(f"  ⚠️ {name} didn't change content")
            before = after
        except Exception as exc:
            print(f"  ❌ {name} failed: {exc}")

    return "All scroll strategies failed"


def _screenshots_different(file1: str, file2: str, base_dir: Path) -> bool:
    return rules._screenshots_different(file1, file2, str(base_dir))


async def _human_scroll(page, times: int) -> None:
    width, height = await page.evaluate("() => [window.innerWidth, window.innerHeight]")
    await humanize.move(page, width // 2, height // 2)
    for _ in range(times):
        await humanize.scroll(
            page,
            random.randint(int(height * 0.7), int(height * 0.95)),
        )
        await _pause(random.uniform(0.3, 0.7))


def _choose_strategy(description, scrollable, html):
    return rules.llm_do(
        rules._PROMPT.format(
            description=description,
            scrollable_elements=scrollable,
            simplified_html=html,
        ),
        output=rules.ScrollStrategy,
        model="co/gemini-3.7-flash",
        temperature=0.1,
    )


async def _ai_scroll(page, times: int, description: str) -> None:
    scrollable = await page.evaluate("""
        (() => Array.from(document.querySelectorAll('*'))
            .filter(el => {
                const s = window.getComputedStyle(el);
                return (s.overflow === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight;
            })
            .slice(0, 3)
            .map(el => ({tag: el.tagName, classes: el.className, id: el.id})))()
        """)
    html = await page.evaluate("""
        (() => {
            const c = document.body.cloneNode(true);
            c.querySelectorAll('script,style,img,svg').forEach(e => e.remove());
            return c.innerHTML.substring(0, 5000);
        })()
        """)
    strategy = await asyncio.to_thread(_choose_strategy, description, scrollable, html)
    print(f"    AI: {strategy.explanation}")
    for _ in range(times):
        await page.evaluate(strategy.javascript)
        await _pause(1)


async def _element_scroll(page, times: int) -> None:
    for _ in range(times):
        await page.evaluate("""
            (() => {
                const el = Array.from(document.querySelectorAll('*')).find(e => {
                    const s = window.getComputedStyle(e);
                    return (s.overflow === 'auto' || s.overflowY === 'scroll') &&
                        e.scrollHeight > e.clientHeight;
                });
                if (el) el.scrollTop += 1000;
            })()
            """)
        await _pause(0.8)


async def _page_scroll(page, times: int) -> None:
    for _ in range(times):
        await page.evaluate("window.scrollBy(0, 1000)")
        await _pause(0.8)
