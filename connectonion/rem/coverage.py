"""
Purpose: say, for each source, how much of it REM can actually read, so a gap is seen by the command, the night
and the owner instead of being found by chance (#3353; first case #3351: WeChat databases without a key).
LLM-Note:
  Dependencies: imports from [useful_tools/wechat] | imported by [cli/commands/rem_commands.py, cli/commands/rem_status.py, rem/onboard.py]
  Data flow: source_coverage(name, sub) -> {source, found, read, skipped: [{item, reason, fix}], missing_keys, line} or None
  State/Effects: read-only; never writes
"""

from __future__ import annotations


def source_coverage(name: str, sub: dict) -> dict | None:
    """What one enabled source has versus what REM reads, with the fix for any gap; None when not measured yet."""
    if not sub.get("enabled") or sub.get("unsubscribed"):
        return None
    if sub.get("kind") == "wechat":
        from ..useful_tools import wechat as engine
        db_storage = engine.db_storage_in_use()
        if db_storage is None:
            coverage = {"source": name, "found": 0, "read": 0, "missing_keys": 0,
                        "skipped": [{"item": "WeChat data folder", "reason": "not readable (no access, or WeChat not set up)",
                                     "fix": "co wechat doctor"}]}
            return {**coverage, "line": "微信：读不到数据文件夹 → co wechat doctor",
                    "line_en": "WeChat: its data folder can't be read → co wechat doctor"}
        coverage = engine.message_coverage(db_storage)
        text = coverage.get("text")
        # Implausibly little: fewer than half the friends have any readable chat. The history is on the phone.
        if text and text["friends"] and text["with_chats"] < text["friends"] / 2:
            coverage["skipped"] = coverage["skipped"] + [{
                "item": "friends without readable chats",
                "reason": f"{text['missing']} of {text['friends']} friends have no chat text on this Mac",
                "fix": "微信 → 设置 → 聊天 → 聊天记录迁移与备份 → 迁移到电脑"}]
        return {**coverage, "source": name, "line": engine.coverage_line(coverage),
                "line_en": engine.coverage_line(coverage, "en")}
    return None


def gaps(subscriptions: dict) -> list[dict]:
    """The coverage of every source that has something unread, for status and the night's one Today line."""
    found = (source_coverage(name, sub) for name, sub in subscriptions.items())
    return [coverage for coverage in found if coverage and coverage["skipped"]]


def record(root, subscriptions: dict) -> list[dict]:
    """The night's coverage check: every source with something unread, stored for Today's one line (#3353).

    Kept in .state/coverage.json so the reader shows it without opening WeChat on every page render. Only a step
    the owner must take (a key capture needs him at the computer) is asked; REM does the rest itself.
    """
    from .files import state_path, write_json
    from datetime import datetime, timezone
    found = [{"source": c["source"], "line": c["line"], "line_en": c["line_en"], "fix": c["skipped"][0]["fix"],
              "fix_kind": fix_kind(c), "found": c["found"], "read": c["read"],
              "unread": len(c["skipped"]), "missing_keys": c["missing_keys"]} for c in gaps(subscriptions)]
    write_json(state_path(root, "coverage.json"), {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                   "gaps": found})
    return found


def stored(root) -> list[dict]:
    """The gaps the last night found; [] before the first check."""
    from .files import read_json, state_path
    return read_json(state_path(root, "coverage.json"), {}).get("gaps", [])


# The one-click fixes Today's line offers, by kind. Fixed commands only: the request names a kind, never a command.
FIX_COMMANDS = {"key_capture": "co wechat key capture"}


def fix_kind(coverage: dict) -> str:
    """Which button fixes a gap: a new key capture when databases lack keys, else the phone-migration steps."""
    return "key_capture" if any(s["fix"] == "co wechat key capture" for s in coverage["skipped"]) else "phone_migration"


def open_fix(kind: str, *, session=None, runner=None, folder=None) -> dict:
    """Start a fix that needs the owner, in his own Terminal; or say plainly how to start it himself.

    A key capture opens a WeChat copy he must log into, so it can't run headless inside the Host. From the owner's
    GUI (Aqua) session the Host writes a one-line .command file and `open -a Terminal` runs it: no AppleScript, so no
    Automation prompt. A Host restarted by an upgrade runs in launchd's Background session (#3317) and cannot show
    windows; then, or if `open` fails, the reply carries the command for the page to copy ("在终端里粘贴运行").
    """
    import subprocess
    import tempfile
    from pathlib import Path
    from .files import RemError
    from .live_host import launch_session
    if kind not in FIX_COMMANDS:
        raise RemError(f"Unknown fix {kind!r}")
    command = FIX_COMMANDS[kind]
    if (session or launch_session)() != "Aqua":
        return {"opened": False, "command": command, "why": "background"}
    script = Path(folder or tempfile.mkdtemp(prefix="co-rem-fix-")) / "co-rem-fix.command"
    script.write_text(f"#!/bin/zsh -l\n{command}\n")
    script.chmod(0o700)
    done = (runner or subprocess.run)(["open", "-a", "Terminal", str(script)], capture_output=True, text=True, timeout=15)
    if done.returncode != 0:
        return {"opened": False, "command": command, "why": "open failed"}
    return {"opened": True, "command": command}
