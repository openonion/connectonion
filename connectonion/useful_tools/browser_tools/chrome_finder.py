"""
Purpose: Locate desktop Google Chrome for the explicit Chrome compatibility engine.
LLM-Note:
  Dependencies: imports from [os, platform] | imported by [browser_tools/browser.py (open_browser), cli/browser_agent/client.py (first-run auto-install pre-flight)] | tested by [tests/unit/test_chrome_autoinstall.py]
  Data flow: find_system_chrome() → probe the fixed per-OS absolute paths → first existing path or None
  State/Effects: none (read-only os.path.exists probes)
  Integration: exposes find_system_chrome() -> Optional[str] | detection is by fixed absolute path only (no PATH/registry lookup); Chrome compatibility can provision Onionwright's pinned Chromium when absent
  Performance: a handful of stat calls
  Errors: none — absence is the None return, not an error
"""

import os
import platform


def find_system_chrome():
    """The path of an installed desktop Google Chrome, or None.

    Chrome compatibility pins this path when present. When absent, its CLI path
    can install Onionwright's pinned Chromium without changing the WTFbrowser default.
    """
    candidates = {
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Linux": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                  "/opt/google/chrome/chrome"],
        "Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    }.get(platform.system(), [])
    return next((p for p in candidates if os.path.exists(p)), None)
