"""TikTok post preparation deliberately stops before any upload or submission."""

from .creator_commands import run
from ...useful_tools.creator_plan import CreatorError, confirm_plan
from ...useful_tools.tiktok import prepare_post


def handle_tiktok_post(path: str, caption: str, account: str, dry_run: bool = False,
                       confirm: str | None = None, json_output: bool = False) -> None:
    def action():
        if dry_run and confirm is not None:
            raise CreatorError("conflicting_mode", "--dry-run and --confirm cannot be combined.")
        plan = prepare_post(path, caption, account)
        if confirm is not None:
            confirm_plan(plan, confirm)
            raise CreatorError("submit_unavailable", "TikTok submission is not implemented: the logged-in upload form and final publish gate still need validation. No file was uploaded.")
        command = "co tiktok inspect --help"
        return {"mode": "preview", "plan": plan, "note": "Local plan only; no TikTok draft, upload, or post was created."}, command, f"Check browser prerequisites: {command}"
    run("tiktok", action, json_output, recovery="co tiktok inspect --help")
