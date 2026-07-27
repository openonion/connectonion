"""Manual probe for the humanized browser input layer (issue #222).

Two independent checks, because they measure different things:

  1. EVENT SHAPE (IP-independent, the real test of humanize.py): drive a local
     event-recorder page with humanize.move/click/type_text and assert the emitted
     events look human — many mousemove steps, a non-zero mousedown→mouseup dwell,
     and variable inter-keystroke timing. This proves the change works regardless of
     where it runs.

  2. ENVIRONMENT CHECKERS (needs network; validates Patchright + headful, NOT our
     input change): visit public fingerprint pages, read their verdict, screenshot.

NOTE: the behavioral vendors (reCAPTCHA v3, Cloudflare, DataDome) also weigh IP
reputation, so a datacenter IP scores as bot no matter how human the cursor is —
they are listed for a residential-IP run, not asserted here.

Run headful under a virtual display:
    xvfb-run -a python3 tests/e2e/manual/browser_fingerprint_probe.py
"""

import statistics
import sys
import tempfile
from pathlib import Path

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from connectonion.useful_tools.browser_tools import humanize  # noqa: E402

RECORDER_HTML = (
    '<input id=box style="position:absolute;left:200px;top:300px;width:240px;height:40px">'
    '<button id=btn style="position:absolute;left:500px;top:300px;width:120px;height:40px">Click me</button>'
    '<b id=rec></b>'
)

# Patchright runs page.evaluate in an ISOLATED world, so a variable an inline page
# <script> sets on window is invisible to evaluate. Attach the recorders from evaluate
# and store counts in the shared DOM (dataset) so any world can read them back.
INSTALL_RECORDER = """() => {
    const rec = document.getElementById('rec');
    addEventListener('mousemove', () => { rec.dataset.moves = (+rec.dataset.moves || 0) + 1; });
    addEventListener('mousedown', e => { rec.dataset.down = e.timeStamp; });
    addEventListener('mouseup',   e => { rec.dataset.up   = e.timeStamp; });
    document.getElementById('box').addEventListener('keydown', e => {
        rec.dataset.keys = (rec.dataset.keys ? rec.dataset.keys + ',' : '') + e.timeStamp;
    });
}"""

# Direct in-page tells that headless/automation detectors check — IP- and
# third-party-uptime-independent. We load a real page first so the checks run in a
# normal document context.
HEADLESS_TELLS = """() => {
    const ua = navigator.userAgent;
    return {
        'navigator.webdriver falsy': !navigator.webdriver,
        'UA is not Headless': !/Headless/i.test(ua),
        'window.chrome present': typeof window.chrome === 'object',
        'has plugins': navigator.plugins.length > 0,
        'has languages': (navigator.languages || []).length > 0,
    };
}"""

ENV_CHECKS = [
    ("sannysoft", "https://bot.sannysoft.com/",
     "() => !navigator.webdriver"),
]


def check_event_shape(page):
    page.set_content(RECORDER_HTML)
    page.evaluate(INSTALL_RECORDER)
    # click the button (curved move + dwell), then type into the box.
    btn = page.locator("#btn").bounding_box()
    humanize.click(page, 0, 0, box=btn)
    box = page.locator("#box").bounding_box()
    humanize.click(page, 0, 0, box=box)
    humanize.type_text(page, "hello human typing")

    data = page.evaluate("() => ({...document.getElementById('rec').dataset})")
    moves = int(data.get("moves", 0))
    dwell = float(data.get("up", 0)) - float(data.get("down", 0))
    key_times = [float(t) for t in data.get("keys", "").split(",") if t]
    gaps = [b - a for a, b in zip(key_times, key_times[1:])]
    jitter = statistics.pstdev(gaps) if len(gaps) > 1 else 0
    ev = {"moves": moves, "keyTimes": key_times}

    results = {
        "mousemove events >= 8 (curved path)": ev["moves"] >= 8,
        "mousedown->up dwell > 10ms": dwell > 10,
        "keystrokes recorded": len(ev["keyTimes"]) > 5,
        "keystroke timing has jitter (>5ms stdev)": jitter > 5,
    }
    print(f"\n  [event shape] moves={ev['moves']} dwell={dwell:.0f}ms "
          f"keys={len(ev['keyTimes'])} gap_stdev={jitter:.0f}ms")
    return results


def check_environment(page):
    results = {}
    for name, url, probe in ENV_CHECKS:
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(2500)
        passed = bool(page.evaluate(probe))
        page.screenshot(path=f"/tmp/probe_{name}.png", full_page=True)
        results[f"{name} verdict"] = passed
        print(f"  [env] {name}: {'PASS' if passed else 'FAIL'}  (shot /tmp/probe_{name}.png)")

    # Direct headless/automation tells, evaluated on the last-loaded real page.
    for name, passed in page.evaluate(HEADLESS_TELLS).items():
        results[name] = bool(passed)
        print(f"  [tell] {name}: {'PASS' if passed else 'FAIL'}")
    return results


def main():
    all_results = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=tempfile.mkdtemp(prefix="co_probe_"),
            headless=False,
            args=["--disable-dev-shm-usage", "--enable-unsafe-swiftshader"],
        )
        page = ctx.new_page()
        print("== 1. EVENT SHAPE (humanize.py — the change under test) ==")
        all_results.update(check_event_shape(page))
        print("\n== 2. ENVIRONMENT CHECKERS (Patchright + headful) ==")
        all_results.update(check_environment(page))
        ctx.close()

    print("\n==================== REPORT ====================")
    passed = sum(all_results.values())
    for name, ok in all_results.items():
        print(f"  {'✅' if ok else '❌'}  {name}")
    print(f"\n  {passed}/{len(all_results)} checks passed")
    sys.exit(0 if passed == len(all_results) else 1)


if __name__ == "__main__":
    main()
