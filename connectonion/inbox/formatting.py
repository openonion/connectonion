"""Markdown in, the chat platform's own formatting out.

An agent writes Markdown — that is what every model emits when asked for a
paragraph with emphasis in it. WhatsApp does not read Markdown. `**ready**`
arrives as four literal asterisks around a word, `[the run](https://…)` arrives
as punctuation nobody can tap, and a heading arrives as a stray `#`. The reply
is correct and looks like a leaked template.

The conversion is small on purpose. WhatsApp's vocabulary is four marks and a
bullet, so anything Markdown can say that WhatsApp cannot is flattened into
something a reader can still act on (a link keeps its URL) rather than dropped.
"""

import re

# Fences and inline code are literal by definition, so they are lifted out
# before anything else runs and put back at the end. Everything in between is
# the only text these rules are allowed to touch.
_FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]+`")


def to_whatsapp(text: str) -> str:
    """Markdown as WhatsApp renders it.

    Bold, italic and strikethrough change marker; headings become bold because
    WhatsApp has no headings; links keep the URL because a label alone is not
    clickable; bullets become the character WhatsApp would have drawn anyway.
    """
    if not text:
        return text

    kept: list[str] = []

    def park(match: re.Match) -> str:
        kept.append(match.group(0))
        # \x00 cannot appear in a chat message, so the placeholder can never
        # collide with the text it is standing in for.
        return f"\x00{len(kept) - 1}\x00"

    # A fence first: an inline span inside a fence is part of the code. The
    # language tag goes with it — WhatsApp's monospace block has no languages,
    # and `python` left on the opening line reads as the first line of output.
    text = _FENCE.sub(lambda m: park_text(kept, f"```\n{m.group(1)}```"), text)
    text = _INLINE.sub(park, text)

    text = _emphasis(text)
    text = _blocks(text)
    text = _links(text)

    for index, original in enumerate(kept):
        text = text.replace(f"\x00{index}\x00", original)
    return text


def park_text(kept: list, literal: str) -> str:
    """Set a span aside under a placeholder, and answer with the placeholder."""
    kept.append(literal)
    return f"\x00{len(kept) - 1}\x00"


# One alternation, scanned once, so every span is consumed exactly once. Two
# passes would not do: the bold rule turns `**x**` into `*x*`, which is
# precisely what the italic rule is looking for, and the word comes out italic.
# The two-character markers lead, or `**x**` reads as `*x*` in stray asterisks.
_EMPHASIS = re.compile(
    r"\*\*(?=\S)(.+?)(?<=\S)\*\*"
    r"|__(?=\S)(.+?)(?<=\S)__"
    r"|~~(?=\S)(.+?)(?<=\S)~~"
    # Single `*` is italic in Markdown and bold on WhatsApp, so it has to move
    # to `_` or the sentence quietly changes what it stresses. The lookarounds
    # keep `2 * 3 = 6` and a bullet's leading `* ` out of it.
    r"|(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])",
    re.DOTALL,
)


def _emphasis(text: str) -> str:
    def one(match: re.Match) -> str:
        bold_stars, bold_bars, struck, italic = match.groups()
        if bold_stars is not None:
            return f"*{bold_stars}*"
        if bold_bars is not None:
            return f"*{bold_bars}*"
        if struck is not None:
            return f"~{struck}~"
        return f"_{italic}_"

    return _EMPHASIS.sub(one, text)


def _blocks(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if heading and heading.group(1):
            lines.append(f"*{heading.group(1)}*")
            continue
        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if bullet:
            lines.append(f"{bullet.group(1)}• {bullet.group(2)}")
            continue
        if re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            # A rule is a visual break, and WhatsApp will not draw one. Box
            # drawing survives every client we can see it in.
            lines.append("──────")
            continue
        lines.append(line)
    return "\n".join(lines)


def _links(text: str) -> str:
    def one(match: re.Match) -> str:
        label, url = match.group(1).strip(), match.group(2).strip()
        # A label that is already the URL would otherwise be printed twice.
        if not label or label == url:
            return url
        return f"{label}: {url}"

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)", lambda m: m.group(2), text)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)", one, text)
