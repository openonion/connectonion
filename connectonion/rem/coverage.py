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
              "unread": len(c["skipped"]), "missing_keys": c["missing_keys"]} for c in gaps(subscriptions)]
    write_json(state_path(root, "coverage.json"), {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                   "gaps": found})
    return found


def stored(root) -> list[dict]:
    """The gaps the last night found; [] before the first check."""
    from .files import read_json, state_path
    return read_json(state_path(root, "coverage.json"), {}).get("gaps", [])
