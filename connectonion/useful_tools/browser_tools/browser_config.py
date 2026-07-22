"""
Purpose: Chrome launch flags for BrowserAutomation. Anti-detection is now Patchright's job, so this is only the handful of flags about the run environment.
LLM-Note:
  Dependencies: pure data, no imports | imported by [useful_tools/browser_tools/browser.py (passes CHROME_DEFAULT_ARGS / IGNORE_DEFAULT_ARGS to launch_persistent_context)] | no direct tests (behavior covered by tests/e2e/cli/test_browser_agent.py)
  Data flow: module-level constants only — read once when BrowserAutomation builds launch options
  Integration: exposes CHROME_DEFAULT_ARGS (list[str], passed as launch args), IGNORE_DEFAULT_ARGS (list[str], removed from Playwright's defaults; browser.py also appends --use-mock-keychain for the macOS cookie fix)
  State/Effects: none
  Errors: none

Patchright ships correct anti-detection defaults (it drops --enable-automation, adds
--disable-blink-features=AutomationControlled, and patches the driver-level tells that
flags can't reach) and its docs warn that over-configuring launch args can DEFEAT those
patches. So we no longer mirror browser-use's 53-flag / 30-disabled-feature stack — that
mirror was a standing sync burden and a regression risk. What stays here is only flags
about the run environment, which are invisible to bot-detection.
"""

# These are run-environment flags, not anti-detection spoofs — both make a GPU-less server
# behave like an ordinary desktop Chrome, which is exactly what bot-detectors expect to see.
CHROME_DEFAULT_ARGS = [
    # Chrome crashes on the small default /dev/shm inside Docker (the co-ai deploy runs
    # headful under Xvfb in a container).
    '--disable-dev-shm-usage',
    # Permit SwiftShader as the WebGL backend when no GPU is present (headless servers,
    # Xvfb, containers). Without it WebGL is simply absent — "Canvas has no webgl context"
    # on sannysoft, an obvious tell, since every real browser has WebGL. This is a FALLBACK:
    # a machine with a real GPU keeps using it and reports its true vendor/renderer.
    #
    # NOTE: Patchright recommends minimal launch args (custom headers/user_agent/automation
    # flags can defeat its patches). This is the one deliberate exception — a GPU-rendering
    # flag, not an automation flag. Verified it does NOT defeat the patches: with it enabled
    # rebrowser's runtimeEnableLeak stays clean and deviceandbrowserinfo reports WebGL
    # consistent. Patchright's other recommendations (channel=chrome via find_system_chrome,
    # headless=False, no_viewport, persistent user_data_dir, no custom UA) are all honored.
    '--enable-unsafe-swiftshader',
]

# Nothing to strip from Patchright's defaults: it already omits the automation markers we
# used to remove here. browser.py appends '--use-mock-keychain' (the macOS cookie-persistence
# fix) to this list at launch, so keep it as an empty list rather than deleting the symbol.
IGNORE_DEFAULT_ARGS = []
