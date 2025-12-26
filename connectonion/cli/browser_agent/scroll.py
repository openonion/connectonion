"""
Unified scroll module - AI-powered with fallback strategies.

Usage:
    from scroll import scroll
    result = scroll(page, take_screenshot, times=5, description="the email list")
"""
from pathlib import Path
from pydantic import BaseModel
from connectonion import llm_do
import time

_PROMPT = (Path(__file__).parent / "prompts" / "scroll_strategy.md").read_text()


class ScrollStrategy(BaseModel):
    method: str  # "window", "element", "container"
    selector: str
    javascript: str
    explanation: str


def scroll(page, take_screenshot, times: int = 5, description: str = "the main content area") -> str:
    """Universal scroll with AI strategy and fallback.

    Tries: AI-generated → Element scroll → Page scroll
    Verifies success with screenshot comparison.
    """
    if not page:
        return "Browser not open"

    timestamp = int(time.time())
    before = f"scroll_before_{timestamp}.png"
    take_screenshot(path=before)

    strategies = [
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
