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
import platform
import random
import shutil
import subprocess
import time
from weakref import WeakKeyDictionary

# Remember each page's cursor position so the next move starts from where the last one
# ended — real cursors travel between actions, they don't reappear on the target pixel.
_cursor = WeakKeyDictionary()

# One CDP session per page, reused for IME composition (see type_text/_type_ime).
_cdp = WeakKeyDictionary()


# A per-page "persona": one real user has one hand and one input device for a whole
# session, so their timing scale and scroll device are constant within a page but differ
# between pages/runs. This defeats a detector that would fingerprint the tool by its fixed
# timing envelope across every session.
_personas = WeakKeyDictionary()


def _persona(page):
    p = _personas.get(page)
    if p is None:
        p = {
            "speed": random.lognormvariate(0.0, 0.22),  # overall pace multiplier
            "wheel_notch": random.random() < 0.6,       # 60% wheel mouse, 40% trackpad
        }
        _personas[page] = p
    return p


def _pause(page, base, sigma=0.45):
    """Sleep a right-skewed (log-normal) time around `base` seconds, scaled by the page's
    persona. Human inter-event gaps have a fat right tail, not the flat plateau uniform()
    gives — and uniform's fixed min/max is itself a cross-session fingerprint."""
    time.sleep(max(0.004, base * random.lognormvariate(0.0, sigma) * _persona(page)["speed"]))


def _ease(u):
    """Minimum-jerk position profile (smootherstep): slow → fast → slow. Sampling Bézier t
    at _ease(i/steps) makes the cursor accelerate out of the start and decelerate into the
    target — a bell velocity curve, not the constant speed equal-t sampling would give."""
    return u * u * u * (u * (u * 6 - 15) + 10)


def _control_points(start, end):
    """Two Bézier control points bowed off the straight line so the path curves like a
    hand's rather than running ruler-straight."""
    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / dist, dx / dist  # unit normal to the direction of travel

    def control(along):
        off = random.uniform(-0.22, 0.22) * dist
        return x0 + dx * along + nx * off, y0 + dy * along + ny * off

    return control(random.uniform(0.2, 0.4)), control(random.uniform(0.6, 0.8))


def _cubic(p0, c1, c2, p3, t):
    mt = 1 - t
    return (
        mt ** 3 * p0[0] + 3 * mt ** 2 * t * c1[0] + 3 * mt * t ** 2 * c2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt ** 2 * t * c1[1] + 3 * mt * t ** 2 * c2[1] + t ** 3 * p3[1],
    )


def move(page, x, y):
    """Move the cursor to (x, y) along a curved path with a human velocity profile
    (accelerate out, decelerate in) and a small overshoot-and-settle at the end, emitting a
    real mousemove event at every step."""
    start = _cursor.get(page)
    if start is None:
        # First move of the session: start well off the target so there is a real approach
        # trajectory, never an instant appearance on the exact pixel.
        start = (x + random.uniform(-260, 260), y + random.uniform(-200, 200))

    dist = math.hypot(x - start[0], y - start[1])
    steps = max(10, min(48, int(dist / 10)))
    c1, c2 = _control_points(start, (x, y))
    for i in range(1, steps + 1):
        px, py = _cubic(start, c1, c2, (x, y), _ease(i / steps))
        page.mouse.move(px, py)
        _pause(page, 0.011, 0.5)
    _overshoot(page, x, y)
    _cursor[page] = (x, y)


def _overshoot(page, x, y):
    """Most human pointer landings overshoot by a few pixels and correct back — a tiny
    end submovement a straight glide-to-target never has."""
    if random.random() < 0.65:
        page.mouse.move(x + random.gauss(0, 3), y + random.gauss(0, 3))
        _pause(page, 0.03, 0.4)
        page.mouse.move(x, y)
        _pause(page, 0.02, 0.4)


def _point_in_box(box):
    """A point inside the element, gaussian-clustered near the centre — human click
    positions form a radial gaussian around the target, not a uniform rectangle. Clamped
    just inside the edges so we never fall outside the element."""
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    x = cx + random.gauss(0, box["width"] * 0.15)
    y = cy + random.gauss(0, box["height"] * 0.15)
    x = min(max(x, box["x"] + 1), box["x"] + box["width"] - 1)
    y = min(max(y, box["y"] + 1), box["y"] + box["height"] - 1)
    return x, y


def click(page, x, y, button="left", clicks=1, box=None):
    """Human click: curve to the target (jittered inside `box` when one is given), settle,
    then press with a short randomized dwell between down and up."""
    if box is not None:
        x, y = _point_in_box(box)
    move(page, x, y)
    _pause(page, 0.06, 0.5)  # settle before pressing
    for i in range(clicks):
        # click_count must increment (1, 2, ...) or Chromium never synthesizes a dblclick
        # from CDP-injected input — two count-1 presses are just two single clicks.
        page.mouse.down(button=button, click_count=i + 1)
        _pause(page, 0.06, 0.35)  # down→up dwell
        page.mouse.up(button=button, click_count=i + 1)
        if i + 1 < clicks:
            _pause(page, 0.08, 0.3)  # inter-click gap (double click)
    _cursor[page] = (x, y)


def double_click(page, x, y, box=None):
    """Two human clicks close enough in time/position that the browser raises dblclick."""
    click(page, x, y, clicks=2, box=box)


def scroll(page, total_dy):
    """Human wheel scroll: emit real `wheel` events sized like the page's scroll device (a
    wheel mouse fires near-constant ~120px notches; a trackpad fires many small deltas),
    with variable cadence and a small overshoot-and-correct at the end — instead of the
    instant programmatic `scrollBy(0, 1000)` jump a detector flags (scrollY changes with
    zero wheel events)."""
    p = _persona(page)
    lo, hi = (100, 130) if p["wheel_notch"] else (8, 28)
    sign = 1 if total_dy >= 0 else -1
    target = int(total_dy)
    # Overshoot a little past the target then correct back — net displacement == target,
    # the way a human stops short of or past a mark and nudges into place.
    overshoot = sign * random.randint(lo, hi) if target and random.random() < 0.6 else 0
    _wheel(page, target + overshoot, sign, lo, hi)
    if overshoot:
        _wheel(page, -overshoot, -sign, lo, hi)


def _wheel(page, amount, sign, lo, hi):
    remaining = amount
    while remaining != 0:
        step = sign * random.randint(lo, hi)
        if abs(step) > abs(remaining):
            step = remaining  # last tick lands exactly
        page.mouse.wheel(0, step)
        remaining -= step
        _pause(page, 0.045, 0.4)
        if random.random() < 0.08:
            _pause(page, 0.3, 0.5)  # occasional reading pause


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


def _clipboard_cmds():
    """(set_argv, get_argv) for the OS clipboard, or None if no tool is available. A real
    user pastes Chinese far more than they hand-type it, and paste is a fully trusted event
    with none of the IME path's residual tells (see type_text)."""
    system = platform.system()
    if system == "Darwin":
        return (["pbcopy"], ["pbpaste"])
    if system == "Windows":
        return (["clip"], ["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
    if shutil.which("xclip"):
        return (["xclip", "-selection", "clipboard"],
                ["xclip", "-selection", "clipboard", "-o"])
    if shutil.which("xsel"):
        return (["xsel", "--clipboard", "--input"], ["xsel", "--clipboard", "--output"])
    return None


def _active_text_len(page):
    return page.evaluate(
        "() => { const e = document.activeElement;"
        " return e ? ((e.value != null ? e.value : e.textContent) || '').length : 0; }")


def _paste(page, text):
    """Put `text` on the OS clipboard and Ctrl/Cmd+V it into the focused field, then restore
    the user's clipboard. Returns True only if the field actually took the paste — some
    inputs (password fields, paste-blocked forms) reject it, and the caller then falls back
    to the IME path."""
    cmds = _clipboard_cmds()
    if cmds is None:
        return False
    set_argv, get_argv = cmds
    saved = subprocess.run(get_argv, capture_output=True).stdout
    subprocess.run(set_argv, input=text.encode())
    before = _active_text_len(page)
    modifier = "Meta" if platform.system() == "Darwin" else "Control"
    page.keyboard.press(f"{modifier}+v")
    _pause(page, 0.12, 0.4)
    grew = _active_text_len(page) >= before + len(text)
    subprocess.run(set_argv, input=saved)  # restore the user's clipboard
    return grew


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
        _pause(page, 0.10, 0.4)   # candidate appears / gets chosen
        # insertText commits the candidate: fires compositionend + inputType
        # insertCompositionText. (compositionstart is a trusted event; compositionend from
        # this commit is not — a minor Chrome/CDP quirk, still far better than the bare
        # insertText with zero composition events that keyboard.type would emit.)
        session.send("Input.insertText", {"text": ch})
        _pause(page, 0.12, 0.5)
        if random.random() < 0.05:
            _pause(page, 0.3, 0.5)   # occasional hesitation


def type_text(page, text):
    """Type with human cadence. Latin text goes key-by-key (most land quickly, word
    boundaries pause, an occasional key hesitates). CJK runs are PASTED (a trusted paste
    event — how people usually enter Chinese, and free of the IME path's zero-keydown /
    untrusted-compositionend tells); if the field blocks paste we fall back to the IME."""
    for is_ime, run in _segments(text):
        if is_ime:
            if not _paste(page, run):
                _type_ime(page, run)
            continue
        for ch in run:
            page.keyboard.type(ch)
            _pause(page, 0.09, 0.5)  # inter-key gap (log-normal, persona-scaled)
            if ch in " \t\n":
                _pause(page, 0.06, 0.5)  # word-boundary pause
            if random.random() < 0.03:
                _pause(page, 0.3, 0.5)  # occasional hesitation
