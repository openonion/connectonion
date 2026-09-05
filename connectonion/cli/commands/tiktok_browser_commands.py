"""Orchestrate generic browser primitives; all site DOM logic lives in the skill."""

import json
import re
import shlex
import subprocess
from pathlib import Path
from uuid import uuid4

from .creator_commands import run
from ...useful_tools.creator_plan import CreatorError


def _send(tab: str, *args: str) -> str:
    # Use the public CLI paired with the installed browser, not a private
    # client protocol from a development checkout. Never execute a shell string.
    try:
        result = subprocess.run(["co", "browser", "-t", tab, *args],
                                capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        raise CreatorError("browser_timeout", "Browser inspection timed out. Check the tab board; no automatic retry was made.") from None
    if result.returncode:
        raise CreatorError("browser_unavailable", "The browser tab is unavailable or busy. Check the browser tab board.")
    return result.stdout.strip()


def inspect_page(tab: str) -> dict:
    """Save evidence before deterministic extraction, then verify the same items."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tab):
        raise CreatorError("invalid_tab", "Supply an existing named tab using letters, numbers, underscores, or hyphens.")
    scripts = Path(__file__).resolve().parents[2] / "useful_skills" / "co-creator" / "scripts"
    evidence_name = f"tiktok_inspect_{uuid4().hex[:12]}"
    screenshot = Path.cwd() / ".tmp" / f"{evidence_name}_before.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = _send(tab, "take_screenshot", str(screenshot))
    if f"Screenshot saved to: {screenshot}" not in output:
        raise CreatorError("evidence_failed", "The browser did not confirm the screenshot; extraction was stopped.")
    context = _send(tab, "save_page_context", evidence_name)
    match = re.search(r"^Saved page context to (.+)$", context, re.MULTILINE)
    if not match:
        raise CreatorError("evidence_failed", "The browser did not confirm saved context; extraction was stopped.")
    extracted = json.loads(_send(tab, "run_page_script", str(scripts / "extract-tiktok.js"), "{}"))
    evidence = {"screenshot": str(screenshot), "context": match.group(1)}
    result = {**extracted, "mode": "read", "evidence": evidence, "verified": False}
    if extracted.get("reason") == "login_required" and extracted.get("selected_item"):
        args = {"expected_item": extracted["selected_item"]}
    else:
        return result
    verified = json.loads(_send(tab, "run_page_script", str(scripts / "verify-tiktok.js"), json.dumps(args)))
    result["verified"] = verified.get("ok") is True
    if not result["verified"]:
        result.update(ok=False, reason="identity_changed")
    elif extracted.get("selected_item", {}).get("text_hash"):
        identity_hash = extracted["selected_item"]["text_hash"]
        if not re.fullmatch(r"[a-f0-9]{8}", identity_hash):
            raise CreatorError("evidence_failed", "The scanner returned an invalid evidence hash.")
        completed = screenshot.with_name(f"{evidence_name}_verified_{identity_hash}.png")
        output = _send(tab, "take_screenshot", str(completed))
        if f"Screenshot saved to: {completed}" not in output:
            result.update(ok=False, reason="completion_evidence_failed")
        else:
            evidence["verified_screenshot"] = str(completed)
    return result


def handle_inspect(tab: str, json_output: bool = False) -> None:
    def action():
        result = inspect_page(tab)
        command = f"co browser -t {shlex.quote(tab)} get_current_url"
        result["note"] = "Login or unverified upload surface: no file was uploaded and no publish action was attempted."
        return result, command, f"Check the current page: {command}"
    run("tiktok", action, json_output, recovery="co browser tab ls")
