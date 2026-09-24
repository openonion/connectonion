"""TikTok local post preparation. No OAuth, HTTP, browser actions, or posting."""

import re

from .creator_plan import CreatorError, media_file, seal_plan


def prepare_post(path: str, caption: str, account: str) -> dict:
    """Prepare a reviewable local plan; this does not create a TikTok draft.

    The logged-in upload form and its per-account settings must be observed
    before a submission adapter can be implemented. See co-creator/SKILL.md.
    """
    if not re.fullmatch(r"@[A-Za-z0-9._]{2,24}", account):
        raise CreatorError("invalid_account", "Supply the intended TikTok @handle for the local plan.")
    if not caption.strip() or len(caption) > 2200:
        raise CreatorError("invalid_caption", "Use a nonempty caption of at most 2200 characters for this preview.")
    return seal_plan({
        "schema_version": 1, "operation": "tiktok.post", "account": account,
        "file": media_file(path), "caption": caption,
        "privacy": "must be selected in the verified upload form",
        "submit_supported": False,
        "upload_url": "https://www.tiktok.com/tiktokstudio/upload",
    })
