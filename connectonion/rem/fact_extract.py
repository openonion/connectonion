"""Read the facts a page needs out of the gathered material, with no model (#2068).

The phone number on Ody's page was in a signature block; the turn searched its
evidence files for what it thought to look for and wrote "no phone number
appears in the material". A signature, a From address and the dates of the
first and last message are text a regular expression reads exactly, so they
are read here and handed to the turn as one `investigation:facts` item, each
with the source id to cite. What only a reader can judge -- which signature
line is a title, which domain is the employer -- is handed over as the lines
themselves (`Signature`, `Calendar`, `Company domain`), never as a field value.

Each row: {"field", "value", "qualifier", "source", "date"}; `field` is a
Facts label (see facts.FIELDS) or one of the context kinds above.
"""

import re
from zoneinfo import ZoneInfo

from .files import EMAIL, RemError, is_address
from .map import MACHINE, RELAY
from .source import timestamp

WEBMAIL = ("gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
           "me.com", "qq.com", "163.com", "126.com", "proton.me", "protonmail.com", "gmx.com", "foxmail.com")
# A sign-off is a short line of its own. "Thank you for your understanding as we
# continue…" opened a "signature" on Nina's forwarded estate notice, and the
# facilities manager's mobile under it became hers (contacts audit P1, #2348).
SIGN_OFF = re.compile(r"^(best|best regards|kind regards|regards|warm regards|thanks|thank you|cheers|sincerely|"
                      r"many thanks|all the best|谢谢|此致)[\s,.!]*$", re.I)
PHONE = re.compile(r"(?<![\d/])(\+?\(?\d[\d ().-]{6,20}\d)(?![\d/])")
MOBILE = re.compile(r"\b(m|mob|mobile|cell|手机)\b\s*[:.]?", re.I)
WORK = re.compile(r"\b(t|tel|ph|phone|p|w|work|office|direct|d|电话)\b\s*[:.]?", re.I)
LINKEDIN = re.compile(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/[\w%-]+/?", re.I)
INVITE = re.compile(r"^(invitation|updated invitation|invitation updated|accepted|meeting)\b|BEGIN:VCALENDAR|"
                    r"Join with Google Meet|Microsoft Teams meeting|Join Zoom Meeting|One tap mobile|"
                    r"Dial by your location|dial[ -]?in|scheduled Zoom meeting|"
                    r"iPhone one[ -]tap|\bzoom\.us/j/|Australian Toll number", re.I | re.M)
MAIL_SOURCES = ("gmail:", "outlook:", "email:")
# "call Larry 0405…", "contact a facilities manager … Ph 0466…": a number someone else is
# named beside is that person's (contacts audit P1/P2, #2348).
OTHER_PERSON = re.compile(r"(?i:\b(?:call|ring|contact|text|reach|phone|ask for|speak to|talk to))\s+"
                          r"(?!(?i:me|us|our|the|a|an)\b)([A-Z][\w'’-]+)")
# A notice passed on, or a platform's message: not the sender's own words.
# Nina forwarded an "Important Notice"; Luma's "[Host Copy] New message in …".
NOTICE = re.compile(r"\bnotice\b|\[host copy\]|\bnew message in\b|you(?:['’]ve| have) got a new message", re.I)
# Recipients past which a mail is a broadcast, not contact: Tamara's kitchen
# etiquette note to about 30 startups became her Last contact (claims audit T2).
BROADCAST = 5


def _date(item: dict, zone: ZoneInfo) -> str:
    try:
        return timestamp(item["timestamp"]).astimezone(zone).date().isoformat()
    except (RemError, KeyError, TypeError, ValueError):
        return ""


def _row(field, value, item, zone, qualifier=""):
    return {"field": field, "value": value, "qualifier": qualifier, "source": item["source"], "date": _date(item, zone)}


def _body(item: dict) -> list[str]:
    """The message's own lines: after the header block when the provider wrote one."""
    text = item.get("text") or ""
    head, marker, rest = text.partition("--- Email Body ---")
    return [line.strip() for line in (rest if marker else head).splitlines()]


def signature(lines: list[str], names: list[str]) -> list[str]:
    """The block under the sign-off: from the last line that is the sender's name
    (or follows a sign-off) in the last fifteen lines, at most eight lines."""
    text = [line for line in lines if line]
    if len(text) <= 2 and text and len(text[-1]) > 200:
        # Outlook hands some bodies over as one line, the quoted thread glued
        # on (the owner's real mail, 2026-10-02: every message from one
        # correspondent, her mobile mid-line). A signature then starts at the
        # sender's own full name after the greeting; another person's quoted
        # signature starts at theirs, so it is not taken.
        flat = text[-1]
        full = [n for n in names if " " in n] or names
        starts = sorted({m.start() for n in full for m in re.finditer(re.escape(n), flat, re.I) if m.start() > 40})
        return [flat[at:at + 240].strip() for at in starts[:3]]
    tail = lines[-15:]
    start = None
    for index, line in enumerate(tail):
        low = line.casefold().strip(" ,.-")
        if low and any(low == n or low.startswith(n + " ") for n in names) and len(line) <= 60:
            start = index
        elif SIGN_OFF.match(line) and index + 1 < len(tail):
            start = index + 1
    return [line for line in tail[start:] if line][:8] if start is not None else []


def _someone_else(lines: list[str], index: int, at: int, names: list[str]) -> bool:
    """The text before a number -- on its line, or the lines above back to another
    number -- names a person to call who is not the subject."""
    context = lines[index][:at]
    for line in reversed(lines[max(0, index - 2):index]):
        if PHONE.search(line):
            break
        context = line + " " + context
    return any(match[1].casefold() not in names for match in OTHER_PERSON.finditer(context))


def _phones(block: list[str], item: dict, zone: ZoneInfo, names: list[str]) -> list[dict]:
    rows = []
    for index, line in enumerate(block):
        for match in PHONE.finditer(line):
            value = match[1].strip()
            digits = re.sub(r"\D", "", value)
            before = line[max(0, match.start() - 16):match.start()]   # the label sits just before
            labelled = MOBILE.search(before) or WORK.search(before)
            if not 8 <= len(digits) <= 15 or re.search(r"\d{4}-\d\d-\d\d", value):
                continue
            if not (labelled or value.startswith(("+", "(", "0"))):
                continue
            if _someone_else(block, index, match.start(), names):
                continue
            qualifier = "mobile" if MOBILE.search(before) else "work" if WORK.search(before) else ""
            rows.append(_row("Phone", value, item, zone, qualifier))
    return rows


def _signed(block: list[str], names: list[str]) -> bool:
    """The block opens on the sender's own name: their signature, not text after a thank-you."""
    head = block[0].casefold()[:60] if block else ""
    return any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", head) for n in names)


def _subject(item: dict, addresses: set, names: list[str]) -> bool:
    speaker = item.get("speaker") or ""
    found = {a.casefold() for a in EMAIL.findall(speaker)}
    if found:
        return bool(found & addresses)
    return speaker.strip().casefold() in names


def notice(item: dict) -> bool:
    """A relay, a system sender or a notice passed on: the sender's facts are not in it (#2348).

    Ody's Luma host copy read "call Larry 0405…" under his name, and the
    relay address joined his page by its display name (contacts audit P2, E2).
    """
    senders = [a.casefold() for a in EMAIL.findall(item.get("speaker") or "")]
    return bool(any(RELAY.search(a) or MACHINE.search(a) for a in senders) or NOTICE.search(item.get("subject") or ""))


def _contact(item: dict, addresses: set, names: list[str]) -> bool:
    """Human mail between the user and the subject: they wrote it, or the user wrote to them."""
    people = item.get("participants") or {}
    recipients = [*(people.get("to") or []), *(people.get("cc") or [])]
    if notice(item) or len(recipients) > BROADCAST:
        return False
    if item["role"] == "other":
        return _subject(item, addresses, names)
    return not people or bool(addresses & {a.casefold() for r in recipients for a in EMAIL.findall(str(r))})


def gave_number(item: dict, value: str, addresses: set, names: list[str]) -> bool:
    """Did the subject give this number in this mail (or its attachment) as their own?

    They sent it, it is not an invitation or a notice, and nobody else is named
    to call beside it. Through a relay (Airbnb, Luma) their name is a line of its
    own just over or under the number: the platform's header ("Andrew Roth -
    Coastal Homies / Sure my number is …", "Tracy / Yes 1pm works- 0403…") or
    their sign-off ("give me a call on 0457… / Thanks / Dannielle").
    """
    senders = {a.casefold() for a in EMAIL.findall(item.get("speaker") or "")}
    relayed = any(RELAY.search(a) for a in senders)
    if not (relayed or senders & addresses) or (notice(item) and not relayed) or INVITE.search(
            item.get("subject", "") + "\n" + (item.get("text") or "")):
        return False
    lines = [line for line in _body(item) if line]
    for index, line in enumerate(lines):
        for match in PHONE.finditer(line):
            if re.sub(r"\D", "", match[1])[-9:] != re.sub(r"\D", "", value)[-9:]:
                continue
            if _someone_else(lines, index, match.start(), names):
                continue
            near = lines[max(0, index - 3):index + 4]
            if not relayed or any(len(text) <= 60 and re.match(rf"{re.escape(n)}(?!\w)", text.casefold())
                                  for text in near for n in names):
                return True
    return False


def extract(items: list[dict], handles: list[str], *, owner: bool = False, timezone: str = "UTC") -> list[dict]:
    """Facts the material states outright about the subject, newest signature first.

    `owner` is the user's own page: the user's own messages are the subject's,
    and a first or last contact with oneself means nothing.
    """
    addresses = {h.strip().casefold() for h in handles if is_address(h)}
    words = [h.strip() for h in handles if not is_address(h) and len(h.strip()) >= 3]
    names = sorted({w.casefold() for w in words} | {w.split()[0].casefold() for w in words if len(w.split()[0]) >= 3})
    zone = ZoneInfo(timezone)
    mail = sorted((i for i in items if str(i.get("source", "")).startswith(MAIL_SOURCES)
                   and i.get("role") in ("user", "other") and _date(i, zone)),
                  key=lambda i: timestamp(i["timestamp"]))
    rows, seen = [], set()

    def add(row):
        value = row["value"].casefold()
        key = (row["field"], re.sub(r"\D", "", value)[-9:] if row["field"] == "Phone" else re.sub(r"\W", "", value))
        if key not in seen:
            seen.add(key)
            rows.append(row)

    for item in reversed(mail):
        if not (item["role"] == "user" if owner else item["role"] == "other" and _subject(item, addresses, names)):
            continue
        if notice(item):
            continue
        # `own`: the subject wrote this mail from it, or signed it; only these are put back (facts.keep_extracted).
        for address in EMAIL.findall(item.get("speaker") or ""):
            add(_row("Email", address.casefold(), item, zone) | {"own": True})
            domain = address.casefold().rsplit("@", 1)[1]
            if domain not in WEBMAIL:
                add(_row("Company domain", domain, item, zone))
        block = signature(_body(item), names)
        if block and sum(1 for r in rows if r["field"] == "Signature") < 3:
            add(_row("Signature", " | ".join(block)[:300], item, zone))
        # An organiser's name above dial-in instructions looks like a signature.
        # Invitation numbers need attribution by the reader, not automatic restoration.
        if _signed(block, names) and not INVITE.search(item.get("subject", "") + "\n" + (item.get("text") or "")):
            for row in _phones(block, item, zone, names):
                add(row | {"own": True})
        for link in LINKEDIN.findall("\n".join(block)):
            add(_row("Links", link if link.startswith("http") else "https://" + link, item, zone))
    for item in reversed(mail):
        if INVITE.search(item.get("subject", "") + "\n" + (item.get("text") or "")):
            for line in _body(item):
                low = line.casefold()
                at = min([low.find(n) for n in [*names, *addresses] if n in low], default=-1)
                if at >= 0:   # a flattened invite is one long line: the window around the name
                    add(_row("Calendar", line[max(0, at - 60):at + 140] if len(line) > 200 else line, item, zone))
    if not owner:
        for row in _others_phones(mail, addresses, names, zone):
            add(row)
        contact = [item for item in mail if _contact(item, addresses, names)]
        if contact:
            add(_row("Last contact", _date(contact[-1], zone), contact[-1], zone))
    return rows


OTHERS_PHONE = "Someone else's phone"


def _others_phones(mail: list[dict], addresses: set, names: list[str], zone: ZoneInfo) -> list[dict]:
    """Phones in the signatures of the other people writing in the subject's threads (#2348).

    David Burt's office line, from his own signature, sat on two colleagues'
    pages; the turn is told whose it is, and code takes it off if it lands anyway.
    """
    rows = []
    for item in reversed(mail):
        speaker = item.get("speaker") or ""
        if item["role"] != "other" or _subject(item, addresses, names) or notice(item) or INVITE.search(
                item.get("subject", "") + "\n" + (item.get("text") or "")):
            continue
        name = re.sub(r"\s*<[^>]*>", "", speaker).strip().strip('"')
        own = [n.casefold() for n in [name, name.split()[0] if name.split() else ""] if len(n) >= 3]
        for row in _phones(signature(_body(item), own), item, zone, own) if own else []:
            rows.append({**row, "field": OTHERS_PHONE, "qualifier": name})
    return rows


ORDER = ("Email", "Phone", "Links", "Last contact", "Company domain", "Signature", "Calendar", OTHERS_PHONE)


def facts_item(rows: list[dict], timezone: str = "UTC") -> dict:
    """The rows as the one item the turn reads, sources named per line."""
    lines = [f"- {r['field']}: {r['value']}" + (f" ({r['qualifier']})" if r["qualifier"] else "")
             + f" — {r['source']}, {r['date']}"
             for r in sorted(rows, key=lambda r: ORDER.index(r["field"]))]
    return {"role": "facts", "source": "investigation:facts", "facts": rows,
            "text": "Facts our code read from the material, with no model. Each names the message it came "
                    "from: put it in its Facts field and cite that source id, not this item. Signature and "
                    "Calendar lines are the text itself: read the role, company, location or time zone from "
                    "them. Correct a fact only where the material contradicts it, and say so in "
                    "Uncertainties. Phone and Email here are the person's own: their signature or From line. "
                    "After the turn code takes off any phone or address that no mail the person sent shows as "
                    "theirs, and puts back a link or last-contact date left off the page. "
                    f"\"{OTHERS_PHONE}\" is a number in another person's own signature, named beside it: it "
                    f"is never this person's. Dates use {timezone}; event dates are separate. The earliest "
                    "retained mail does not establish first contact.\n"
                    + "\n".join(lines)}
