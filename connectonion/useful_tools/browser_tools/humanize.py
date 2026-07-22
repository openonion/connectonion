"""
Purpose: Humanize BrowserAutomation's pointer + keyboard events so clicks and typing survive
         BEHAVIORAL bot detection (mouse-trajectory entropy, click position, keystroke cadence)
LLM-Note:
  Dependencies: stdlib only [math, random, time, weakref] | imported by [useful_tools/browser_tools/browser.py — every click/hover/type path routes through here; scroll.py — wheel scroll] | tested by [tests/unit/test_browser_humanize.py]
  Data flow: browser.py/scroll.py call move/click/double_click/type_text/scroll(page, ...) on the browser worker thread → each remembers the page's last cursor position in the module-level WeakKeyDictionary `_cursor`, so the NEXT action starts its curve from where the last one ended (a real cursor never teleports between actions)
  State/Effects: drives the live page via page.mouse.* / page.keyboard.* and sleeps between events; the only retained state is `_cursor` (per-page last x/y, auto-dropped when the page is GC'd)
  Integration: Patchright already fixes the DRIVER-level tells (navigator.webdriver, Runtime.enable); this module fixes the layer above it — the shape of the events themselves. No public tool signatures change; only the low-level event generation.
  Errors: none — pure event emission; if the page is closed the underlying Playwright call raises and bubbles (fail fast)
"""

import math
import random
import time
from weakref import WeakKeyDictionary

# Remember each page's cursor position so the next move starts from where the last one
# ended — real cursors travel between actions, they don't reappear on the target pixel.
_cursor = WeakKeyDictionary()


def _bezier(start, end, steps):
    """Cubic Bézier from start to end with two random control points, sampled at `steps`
    points. The control points bow the path sideways off the straight line, giving the
    curvature a hand produces instead of a ruler-straight segment a detector flags."""
    (x0, y0), (x3, y3) = start, end
    dx, dy = x3 - x0, y3 - y0
    dist = math.hypot(dx, dy) or 1.0
    px, py = -dy / dist, dx / dist  # unit vector perpendicular to the travel direction

    def control(along):
        off = random.uniform(-0.22, 0.22) * dist
        return x0 + dx * along + px * off, y0 + dy * along + py * off

    c1 = control(random.uniform(0.2, 0.4))
    c2 = control(random.uniform(0.6, 0.8))

    points = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt ** 3 * x0 + 3 * mt ** 2 * t * c1[0] + 3 * mt * t ** 2 * c2[0] + t ** 3 * x3
        y = mt ** 3 * y0 + 3 * mt ** 2 * t * c1[1] + 3 * mt * t ** 2 * c2[1] + t ** 3 * y3
        points.append((x, y))
    return points


def move(page, x, y):
    """Move the cursor to (x, y) along a curved, variable-speed path, emitting a real
    mousemove event at every step."""
    start = _cursor.get(page)
    if start is None:
        # First move of the session: begin a little off the target so there is still a
        # short trajectory, never an instant appearance on the exact pixel.
        start = (x + random.uniform(-140, 140), y + random.uniform(-140, 140))

    dist = math.hypot(x - start[0], y - start[1])
    steps = max(8, min(40, int(dist / 12)))
    for px, py in _bezier(start, (x, y), steps):
        page.mouse.move(px, py)
        time.sleep(random.uniform(0.006, 0.02))
    _cursor[page] = (x, y)


def _point_in_box(box):
    """A point inside the element but off dead-center — humans don't hit the exact
    centroid. Kept within the inner 60% so we never fall outside the element."""
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    return (
        cx + random.uniform(-0.3, 0.3) * box["width"],
        cy + random.uniform(-0.3, 0.3) * box["height"],
    )


def click(page, x, y, button="left", clicks=1, box=None):
    """Human click: curve to the target (jittered inside `box` when one is given), settle,
    then press with a short randomized dwell between down and up."""
    if box is not None:
        x, y = _point_in_box(box)
    move(page, x, y)
    time.sleep(random.uniform(0.03, 0.12))  # settle before pressing
    for i in range(clicks):
        page.mouse.down(button=button)
        time.sleep(random.uniform(0.04, 0.11))  # down→up dwell
        page.mouse.up(button=button)
        if i + 1 < clicks:
            time.sleep(random.uniform(0.06, 0.12))  # inter-click gap (double click)
    _cursor[page] = (x, y)


def double_click(page, x, y, box=None):
    """Two human clicks close enough in time/position that the browser raises dblclick."""
    click(page, x, y, clicks=2, box=box)


def scroll(page, total_dy):
    """Human wheel scroll: cover `total_dy` pixels as many small mouse-wheel ticks with
    variable size and cadence (plus the odd longer reading pause), so the page emits real
    `wheel` events and `scrollY` moves incrementally — instead of the instant programmatic
    `scrollBy(0, 1000)` jump a detector flags (scrollY changes with zero wheel events)."""
    remaining = int(total_dy)
    sign = 1 if remaining >= 0 else -1
    while abs(remaining) > 2:
        step = sign * random.randint(90, 170)
        if abs(step) > abs(remaining):
            step = remaining
        page.mouse.wheel(0, step)
        remaining -= step
        time.sleep(random.uniform(0.03, 0.10))
        if random.random() < 0.1:
            time.sleep(random.uniform(0.2, 0.5))  # occasional reading pause


def type_text(page, text):
    """Type character by character with human cadence: most keys land quickly, word
    boundaries pause a little longer, and an occasional key hesitates the way a real
    typist does — instead of the whole string arriving with uniform zero-jitter timing."""
    for ch in text:
        page.keyboard.type(ch)
        delay = random.uniform(0.04, 0.14)
        if ch in " \t\n":
            delay += random.uniform(0.03, 0.12)  # word-boundary pause
        if random.random() < 0.03:
            delay += random.uniform(0.2, 0.5)  # occasional hesitation
        time.sleep(delay)
