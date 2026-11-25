"""Measure a reader at 390px in Chrome, with 4x CPU throttling.

uv run --python 3.13 --extra dev --with playwright python scripts/measure_rem_reader.py
Pass --root for a notebook (read only), or --html for an already rendered page.
Output is numbers only; temporary HTML and notebooks never enter the repository.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PAINT_PROBE = """{let scheduled = false; new MutationObserver(() => {
  if (!document.querySelector('.brief-header h1') || scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.dataset.briefPaint = performance.now();
  }));
}).observe(document, {childList: true, subtree: true});}"""
METRICS = """({url: location.href, h1_paint_ms: Number(document.documentElement.dataset.briefPaint),
  first_contentful_paint_ms: performance.getEntriesByName('first-contentful-paint')[0]?.startTime,
  cards: document.querySelectorAll('.qcard').length,
  first_card_actions: document.querySelector('.qcard')?.querySelectorAll('button:not(:disabled), a').length,
  overflow_px: document.documentElement.scrollWidth - innerWidth})"""


def measure(path, runs, cpu):
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for _ in range(runs):
            page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True,
                                    device_scale_factor=3, has_touch=True)
            page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": cpu})
            page.add_init_script(PAINT_PROBE)
            page.goto(path.as_uri(), wait_until="commit", timeout=120_000)
            page.wait_for_function("Number(document.documentElement.dataset.briefPaint) > 0", timeout=120_000)
            results.append(page.evaluate(METRICS))
            page.close()
        browser.close()
    return results


def measure_existing(path, runs, tab, directory):
    """Explicit fallback for a sandbox where Chrome cannot launch; no CPU throttle."""
    env = {**os.environ, 'CO_WHO': os.environ.get('CO_WHO', 'rem-measure'), 'CO_TIPS': '0'}
    command = ['co', 'browser', '-t', tab]
    def call(*args, check=True):
        return subprocess.run([*command, *args], env=env, capture_output=True, text=True,
                              check=check, timeout=150).stdout
    instrumented = Path(directory) / 'measured.html'
    instrumented.write_text(path.read_text().replace('<head>', '<head><script>' + PAINT_PROBE + '</script>', 1))
    probe = Path(directory) / 'metrics.js'
    probe.write_text('() => ' + METRICS)
    call('set_viewport', '390', '844')
    results = []
    for _ in range(runs):
        call('go_to', instrumented.as_uri(), check=False)
        result = json.loads(call('run_page_script', str(probe)))
        if result['url'] != instrumented.as_uri() or not result['h1_paint_ms']:
            raise RuntimeError('Browser did not measure the requested page')
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--root", type=Path)
    source.add_argument("--html", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cpu", type=float, default=4)
    parser.add_argument("--co-tab", help="existing co browser tab; fallback only, requires --cpu 1")
    parser.add_argument("--live", action="store_true", help="measure the live shell instead of the offline snapshot")
    args = parser.parse_args()
    if args.co_tab and args.cpu != 1:
        parser.error('--co-tab cannot throttle CPU; pass --cpu 1 explicitly')
    with tempfile.TemporaryDirectory(prefix="rem-measure-") as directory:
        path = args.html
        generation = None
        if path is None:
            from connectonion.rem.reader import render
            root = args.root
            if root is None:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests/fixtures"))
                from rem_reader_notebook import build
                root = build(Path(directory) / "rem")
            started = time.perf_counter()
            html = render(root, local=True, live=args.live)
            generation = time.perf_counter() - started
            path = Path(directory) / "reader.html"
            path.write_text(html, encoding="utf-8")
        results = (measure_existing(path.resolve(), args.runs, args.co_tab, directory) if args.co_tab
                   else measure(path.resolve(), args.runs, args.cpu))
        print(json.dumps({"html_bytes": path.stat().st_size, "render_seconds": generation,
                          "cpu_rate": args.cpu, "existing_browser": bool(args.co_tab), "phone": results}, indent=2))


if __name__ == "__main__":
    main()
