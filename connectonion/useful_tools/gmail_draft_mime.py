"""Bound the complete draft before a provider write or reviewed send."""
from email import policy

MIME_LIMIT = 35_000_000
ATTACHMENT_LIMIT = 25_000_000


class DraftFormatError(ValueError):
    """A locally generated, safe draft validation error."""


def validate_message(gmail, message) -> bytes:
    attachments = [gmail._attachment_dict(part) for _, part in gmail._attachment_parts(message)]
    if sum(item['size'] for item in attachments) > ATTACHMENT_LIMIT:
        raise DraftFormatError('Attachments exceed the 25,000,000-byte limit.')
    raw = message.as_bytes(policy=policy.SMTP)
    if len(raw) > MIME_LIMIT:
        raise DraftFormatError('Final MIME exceeds the 35,000,000-byte limit.')
    return raw
