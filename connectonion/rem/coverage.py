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
            return {**coverage, "line": "微信：读不到数据文件夹 → co wechat doctor"}
        coverage = engine.message_coverage(db_storage)
        return {**coverage, "source": name, "line": engine.coverage_line(coverage)}
    return None


def gaps(subscriptions: dict) -> list[dict]:
    """The coverage of every source that has something unread, for status and the night's one Today line."""
    found = (source_coverage(name, sub) for name, sub in subscriptions.items())
    return [coverage for coverage in found if coverage and coverage["skipped"]]
