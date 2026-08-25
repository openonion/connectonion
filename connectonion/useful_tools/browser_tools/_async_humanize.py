"""
Purpose: Non-blocking humanized pointer, keyboard, and wheel input for AsyncBrowserCore.
LLM-Note:
  Dependencies: asyncio + stdlib-only humanize rules; no Patchright sync API | imported by [_async_browser.py] | tested by [tests/unit/test_async_browser_humanize.py]
  Data flow: known target → shared geometry/persona rules → awaited mouse/keyboard/CDP events with asyncio sleeps between events
  State/Effects: per-page cursor/CDP state | temporary OS clipboard mutation for CJK paste, serialized by the runtime clipboard lock and restored on cancellation
  Integration: internal 1.8 async driver only; synchronous BrowserAutomation continues to use humanize.py until #500
  Errors: browser/CDP errors bubble; clipboard absence falls back to IME composition

The synchronous input layer intentionally sleeps between low-level events. Calling
it from the async driver would block every session on the event loop. This module
keeps the same geometry, timing distributions, segmentation, and clipboard rules
while awaiting every browser operation and pause.
"""

import asyncio
import math
import platform
import random
from weakref import WeakKeyDictionary

from . import humanize as rules

_cursor = WeakKeyDictionary()
_cdp = WeakKeyDictionary()


async def _pause(page, base, sigma=0.45):
    delay = max(
        0.004,
        base * random.lognormvariate(0.0, sigma) * rules._persona(page)["speed"],
    )
    await asyncio.sleep(delay)


async def move(page, x, y):
    """Move along the synchronous layer's curved, minimum-jerk path."""
    start = _cursor.get(page)
    if start is None:
        start = (x + random.uniform(-260, 260), y + random.uniform(-200, 200))

    distance = math.hypot(x - start[0], y - start[1])
    steps = max(10, min(48, int(distance / 10)))
    control_1, control_2 = rules._control_points(start, (x, y))
    for index in range(1, steps + 1):
        point_x, point_y = rules._cubic(
            start,
            control_1,
            control_2,
            (x, y),
            rules._ease(index / steps),
        )
        await page.mouse.move(point_x, point_y)
        await _pause(page, 0.011, 0.5)
    await _overshoot(page, x, y)
    _cursor[page] = (x, y)


async def _overshoot(page, x, y):
    if random.random() < 0.65:
        await page.mouse.move(x + random.gauss(0, 3), y + random.gauss(0, 3))
        await _pause(page, 0.03, 0.4)
        await page.mouse.move(x, y)
        await _pause(page, 0.02, 0.4)


async def click(page, x, y, button="left", clicks=1, box=None):
    """Humanized click with awaited travel, dwell, and incrementing click count."""
    if box is not None:
        x, y = rules._point_in_box(box)
    await move(page, x, y)
    await _pause(page, 0.06, 0.5)
    for index in range(clicks):
        click_count = index + 1
        await page.mouse.down(button=button, click_count=click_count)
        await _pause(page, 0.06, 0.35)
        await page.mouse.up(button=button, click_count=click_count)
        if click_count < clicks:
            await _pause(page, 0.08, 0.3)
    _cursor[page] = (x, y)


async def double_click(page, x, y, box=None):
    await click(page, x, y, clicks=2, box=box)


async def scroll(page, total_dy):
    """Emit awaited wheel ticks with the same device persona and net distance."""
    persona = rules._persona(page)
    low, high = (100, 130) if persona["wheel_notch"] else (8, 28)
    sign = 1 if total_dy >= 0 else -1
    target = int(total_dy)
    overshoot = (
        sign * random.randint(low, high) if target and random.random() < 0.6 else 0
    )
    await _wheel(page, target + overshoot, sign, low, high)
    if overshoot:
        await _wheel(page, -overshoot, -sign, low, high)


async def _wheel(page, amount, sign, low, high):
    remaining = amount
    while remaining != 0:
        step = sign * random.randint(low, high)
        if abs(step) > abs(remaining):
            step = remaining
        await page.mouse.wheel(0, step)
        remaining -= step
        await _pause(page, 0.045, 0.4)
        if random.random() < 0.08:
            await _pause(page, 0.3, 0.5)


async def _active_text_len(page) -> int:
    return await page.evaluate(
        "() => { const e = document.activeElement;"
        " return e ? ((e.value != null ? e.value : e.textContent) || '').length : 0; }"
    )


async def _restore_clipboard(value):
    task = asyncio.create_task(asyncio.to_thread(rules._clipboard_set, value))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def _set_clipboard_before_paste(value) -> bool:
    """Finish an in-flight set and report cancellation for deferred delivery."""
    task = asyncio.create_task(asyncio.to_thread(rules._clipboard_set, value))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        return True
    return False


async def _paste(page, text, clipboard_lock):
    if rules._clipboard_set_argv(text) is None:
        return False

    async with clipboard_lock:
        saved = await asyncio.to_thread(rules._clipboard_get)
        interrupted = await _set_clipboard_before_paste(text)
        try:
            if interrupted:
                raise asyncio.CancelledError
            before = await _active_text_len(page)
            modifier = "Meta" if platform.system() == "Darwin" else "Control"
            await page.keyboard.press(f"{modifier}+v")
            await _pause(page, 0.12, 0.4)
            return await _active_text_len(page) >= before + len(text)
        finally:
            await _restore_clipboard(saved)


async def _type_ime(page, run):
    session = _cdp.get(page)
    if session is None:
        session = await page.context.new_cdp_session(page)
        _cdp[page] = session
    for character in run:
        await session.send(
            "Input.imeSetComposition",
            {"text": character, "selectionStart": 1, "selectionEnd": 1},
        )
        await _pause(page, 0.10, 0.4)
        await session.send("Input.insertText", {"text": character})
        await _pause(page, 0.12, 0.5)
        if random.random() < 0.05:
            await _pause(page, 0.3, 0.5)


async def type_text(page, text, clipboard_lock):
    """Type Latin text per key and route CJK through paste or awaited CDP IME."""
    for needs_ime, run in rules._segments(text):
        if needs_ime:
            if not await _paste(page, run, clipboard_lock):
                await _type_ime(page, run)
            continue
        for character in run:
            await page.keyboard.type(character)
            await _pause(page, 0.09, 0.5)
            if character in " \t\n":
                await _pause(page, 0.06, 0.5)
            if random.random() < 0.03:
                await _pause(page, 0.3, 0.5)
