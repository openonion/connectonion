"""
Purpose: Humanize BrowserAutomation's pointer + keyboard events so clicks and typing survive
         BEHAVIORAL bot detection (mouse-trajectory entropy, click position, keystroke cadence)
LLM-Note:
  Dependencies: stdlib only [math, random, time, weakref] | imported by [useful_tools/browser_tools/browser.py — every click/hover/type path routes through here; scroll.py — wheel scroll] | tested by [tests/unit/test_browser_humanize.py]
  Data flow: browser.py/scroll.py call move/click/double_click/type_text/scroll(page, ...) on the browser worker thread → each remembers the page's last cursor position in the module-level WeakKeyDictionary `_cursor`, so the NEXT action starts its curve from where the last one ended (a real cursor never teleports between actions)
  State/Effects: drives the live page via page.mouse.* / page.keyboard.* and (for CJK) a CDP session's Input.imeSetComposition, sleeping between events; retained state is `_cursor` (per-page last x/y) and `_cdp` (per-page CDP session for IME) — both auto-dropped when the page is GC'd
  Integration: Patchright already fixes the DRIVER-level tells (navigator.webdriver, Runtime.enable); this module fixes the layer above it — the shape of the events themselves (curved cursor paths, keystroke cadence, real wheel events, and IME composition for CJK). No public tool signatures change; only the low-level event generation.
  Errors: none — pure event emission; if the page is closed the underlying Playwright/CDP call raises and bubbles (fail fast)
"""

import math
import random
import time
from weakref import WeakKeyDictionary

# Remember each page's cursor position so the next move starts from where the last one
# ended — real cursors travel between actions, they don't reappear on the target pixel.
_cursor = WeakKeyDictionary()

# One CDP session per page, reused for IME composition (see type_text/_type_ime).
_cdp = WeakKeyDictionary()


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
        # click_count must increment (1, 2, ...) or Chromium never synthesizes a dblclick
        # from CDP-injected input — two count-1 presses are just two single clicks.
        page.mouse.down(button=button, click_count=i + 1)
        time.sleep(random.uniform(0.04, 0.11))  # down→up dwell
        page.mouse.up(button=button, click_count=i + 1)
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
    while remaining != 0:
        step = sign * random.randint(90, 170)
        if abs(step) > abs(remaining):
            step = remaining  # final tick lands exactly on the target
        page.mouse.wheel(0, step)
        remaining -= step
        time.sleep(random.uniform(0.03, 0.10))
        if random.random() < 0.1:
            time.sleep(random.uniform(0.2, 0.5))  # occasional reading pause


def _needs_ime(ch):
    """True for characters a human types through an IME (composition), not direct keys —
    CJK ideographs, Japanese kana, Korean hangul. `page.keyboard.type` drops these as a
    bare insertText with NO composition events, which is an obvious tell on IME-aware
    (Chinese/Japanese/Korean) sites: a real typist always produces compositionstart/
    update/end while choosing candidates."""
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF or   # hiragana + katakana
            0x3400 <= o <= 0x4DBF or   # CJK ext A
            0x4E00 <= o <= 0x9FFF or   # CJK unified ideographs
            0xAC00 <= o <= 0xD7A3 or   # hangul syllables
            0xF900 <= o <= 0xFAFF)     # CJK compatibility ideographs


def _segments(text):
    """Split text into (needs_ime, run) chunks so each run is typed with the right
    mechanism — direct keystrokes for Latin, IME composition for CJK."""
    runs = []
    for ch in text:
        ime = _needs_ime(ch)
        if runs and runs[-1][0] == ime:
            runs[-1][1].append(ch)
        else:
            runs.append((ime, [ch]))
    return [(ime, "".join(chars)) for ime, chars in runs]


def _type_ime(page, run):
    """Type a CJK run through the browser's real IME path via CDP: each character is shown
    composing (underlined) and then committed, firing compositionstart/update/end and
    inputType=insertCompositionText the way pinyin/romaji + candidate selection does —
    instead of the bare insertText page.keyboard.type emits, which has no composition."""
    session = _cdp.get(page)
    if session is None:
        session = page.context.new_cdp_session(page)
        _cdp[page] = session
    for ch in run:
        session.send("Input.imeSetComposition",
                     {"text": ch, "selectionStart": 1, "selectionEnd": 1})
        time.sleep(random.uniform(0.06, 0.16))   # candidate appears / gets chosen
        # insertText commits the candidate: fires compositionend + inputType
        # insertCompositionText. (compositionstart is a trusted event; compositionend from
        # this commit is not — a minor Chrome/CDP quirk, still far better than the bare
        # insertText with zero composition events that keyboard.type would emit.)
        session.send("Input.insertText", {"text": ch})
        delay = random.uniform(0.08, 0.20)
        if random.random() < 0.05:
            delay += random.uniform(0.2, 0.5)    # occasional hesitation
        time.sleep(delay)


def type_text(page, text):
    """Type with human cadence. Latin text goes key-by-key (most land quickly, word
    boundaries pause, an occasional key hesitates). CJK runs go through the IME
    composition path so they look like real pinyin/romaji input, not a bare insertText."""
    for is_ime, run in _segments(text):
        if is_ime:
            _type_ime(page, run)
            continue
        for ch in run:
            page.keyboard.type(ch)
            delay = random.uniform(0.04, 0.14)
            if ch in " \t\n":
                delay += random.uniform(0.03, 0.12)  # word-boundary pause
            if random.random() < 0.03:
                delay += random.uniform(0.2, 0.5)  # occasional hesitation
            time.sleep(delay)
