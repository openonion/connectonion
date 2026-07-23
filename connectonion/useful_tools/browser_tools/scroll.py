"""
Purpose: Page scrolling that looks human (real mouse-wheel events) first, with AI/JS fallbacks
LLM-Note:
  Dependencies: imports from [connectonion llm_do, pydantic, pathlib, PIL Image, . humanize] | imported by [useful_tools/browser_tools/browser.py] | tested by [tests/unit/test_scroll.py]
  Data flow: scroll(page, take_screenshot, times, description) → takes before screenshot → tries strategies IN ORDER: Human wheel (humanize.scroll emits real mouse-wheel events) → AI-generated JS → element scroll → page scroll → takes after screenshot → compares via _screenshots_different() → returns on first successful change | _ai_scroll() extracts scrollable elements + HTML → llm_do generates ScrollStrategy → executes JS | JS strategies use scrollTop/scrollBy
  State/Effects: writes before/after screenshots to screenshots/ directory | Human wheel dispatches real wheel events over the content; JS fallbacks modify scrollTop or window.scrollY | no persistent state
  Integration: exposes scroll(page, take_screenshot, times, description) → str | ScrollStrategy Pydantic model with method, selector, javascript, explanation | uses scroll_strategy.md prompt for LLM | verifies success via pixel difference (>1% change threshold)
  Performance: Human wheel is the default and needs no LLM | AI strategy (slower) only runs if wheel didn't change the page | 0.3-0.7s between scrolls for content loading | PIL pixel comparison (fast for typical screenshots)
  Errors: returns "Browser not open" if page None | returns "All scroll strategies failed" if no strategy changes content | prints strategy attempts for debugging | catches exceptions per strategy and continues
Unified scroll module - humanized mouse-wheel first, AI/JS fallbacks.

Usage:
    from scroll import scroll
    result = scroll(page, take_screenshot, times=5, description="the email list")
"""
from pathlib import Path
from pydantic import BaseModel
from connectonion import llm_do
from . import humanize
import random
import time

_PROMPT = (Path(__file__).parent / "prompts" / "scroll_strategy.md").read_text()


class ScrollStrategy(BaseModel):
    method: str  # "window", "element", "container"
    selector: str
    javascript: str
    explanation: str


def scroll(page, take_screenshot, times: int = 5, description: str = "the main content area") -> str:
    """Universal scroll, humanized first.

    Tries: Human wheel (real mouse-wheel events) → AI-generated → Element scroll → Page scroll
    Verifies success with screenshot comparison.
    """
    if not page:
        return "Browser not open"

    timestamp = int(time.time())
    before = f"scroll_before_{timestamp}.png"
    take_screenshot(path=before)

    strategies = [
        ("Human wheel", lambda: _human_scroll(page, times)),
        ("AI strategy", lambda: _ai_scroll(page, times, description)),
        ("Element scroll", lambda: _element_scroll(page, times)),
        ("Page scroll", lambda: _page_scroll(page, times)),
    ]

    for name, execute in strategies:
        print(f"  Trying: {name}...")
        try:
            execute()
            time.sleep(0.5)
            after = f"scroll_after_{timestamp}.png"
            take_screenshot(path=after)

            if _screenshots_different(before, after):
                print(f"  ✅ {name} worked")
                return f"Scrolled using {name}"
            print(f"  ⚠️ {name} didn't change content")
            before = after
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")

    return "All scroll strategies failed"


def _human_scroll(page, times: int):
    """Scroll with real mouse-wheel events. Tried FIRST because it is the only strategy
    that looks human — the JS strategies below move scrollTop directly and emit no wheel
    event. Move the cursor over the content so the wheel targets the page/container, then
    roll it a screenful at a time."""
    w, h = page.evaluate("() => [window.innerWidth, window.innerHeight]")
    humanize.move(page, w // 2, h // 2)
    for _ in range(times):
        humanize.scroll(page, random.randint(int(h * 0.7), int(h * 0.95)))
        time.sleep(random.uniform(0.3, 0.7))


def _ai_scroll(page, times: int, description: str):
    """AI-generated scroll strategy."""
    scrollable = page.evaluate("""
        (() => {
            return Array.from(document.querySelectorAll('*'))
                .filter(el => {
                    const s = window.getComputedStyle(el);
                    return (s.overflow === 'auto' || s.overflowY === 'scroll') &&
                           el.scrollHeight > el.clientHeight;
                })
                .slice(0, 3)
                .map(el => ({tag: el.tagName, classes: el.className, id: el.id}));
        })()
    """)

    html = page.evaluate("""
        (() => {
            const c = document.body.cloneNode(true);
            c.querySelectorAll('script,style,img,svg').forEach(e => e.remove());
            return c.innerHTML.substring(0, 5000);
        })()
    """)

    strategy = llm_do(
        _PROMPT.format(description=description, scrollable_elements=scrollable, simplified_html=html),
        output=ScrollStrategy,
        model="co/gemini-2.5-flash",
        temperature=0.1
    )
    print(f"    AI: {strategy.explanation}")

    for _ in range(times):
        page.evaluate(strategy.javascript)
        time.sleep(1)


def _element_scroll(page, times: int):
    """Scroll first scrollable element found."""
    for _ in range(times):
        page.evaluate("""
            (() => {
                const el = Array.from(document.querySelectorAll('*')).find(e => {
                    const s = window.getComputedStyle(e);
                    return (s.overflow === 'auto' || s.overflowY === 'scroll') &&
                           e.scrollHeight > e.clientHeight;
                });
                if (el) el.scrollTop += 1000;
            })()
        """)
        time.sleep(0.8)


def _page_scroll(page, times: int):
    """Scroll window."""
    for _ in range(times):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.8)


def _screenshots_different(file1: str, file2: str) -> bool:
    """Compare screenshots using PIL pixel difference."""
    try:
        from PIL import Image
        import os

        img1 = Image.open(os.path.join("screenshots", file1)).convert('RGB')
        img2 = Image.open(os.path.join("screenshots", file2)).convert('RGB')

        diff = sum(
            abs(a - b)
            for p1, p2 in zip(img1.getdata(), img2.getdata())
            for a, b in zip(p1, p2)
        )
        threshold = img1.size[0] * img1.size[1] * 3 * 0.01  # 1%
        return diff > threshold
    except Exception:
        return True  # Assume different if comparison fails
