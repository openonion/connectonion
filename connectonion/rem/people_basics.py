"""The archive owns contact dates; certain location and domain facts fill blanks."""

import re
from collections import Counter
from datetime import datetime

from . import facts, store
from .files import EMAIL, Notebook
from .page_review import timezone_from_location

# A country suffix is useful only when it has one civil time zone. No .au/.us.
DOMAIN_ZONES = {"sg": "Asia/Singapore", "hk": "Asia/Hong_Kong", "cn": "Asia/Shanghai",
                "jp": "Asia/Tokyo", "uk": "Europe/London"}
SHARED = re.compile(r"\b(?:shared|role|team|family|assistant|delegate)\b", re.I)


def own_addresses(book: Notebook, record="", text="", *, excluding=()) -> dict:
    """A page's Email values, excluding marked shared/role mail and addresses shared by pages."""
    from .map import AGENT_ADDRESS, MACHINE, RELAY
    from .scan import AUTOMATED_HINT
    found, counts = {}, Counter()
    for page in sorted(set(book.list("people")) | ({record} if record else set())):
        if page in excluding:
            continue
        values = facts._lines(text if page == record else book.read(page)).get("Email", "")
        counts.update({address.casefold() for address in EMAIL.findall(values)})
        found[page] = {address.casefold() for part in facts._split(values) if not SHARED.search(part)
                         for address in EMAIL.findall(part)
                         if not any(pattern.search(address) for pattern in
                                    (AGENT_ADDRESS, MACHINE, RELAY, AUTOMATED_HINT))}
    return {record: {address for address in addresses if counts[address] == 1}
            for record, addresses in found.items()}


def _set(text, label, value, message, zone):
    day = datetime.fromisoformat(message["time"]).astimezone(zone).date().isoformat()
    text, number = facts._cite(text, {"source": message["id"], "date": day})
    span = facts._bounds(text, "Facts")
    body = re.sub(rf"(?m)^- {re.escape(label)}:[^\n]*$", lambda _: f"- {label}: {value} [{number}]",
                  text[span[0]:span[1]])
    return text[:span[0]] + body + text[span[1]:]


def _company(book, domains):
    from .investigate import org_domains
    matches = {}
    for record in book.list("orgs"):
        page = book.read(record)
        known = org_domains(page)
        matched = {domain for domain in domains if any(domain == org or domain.endswith("." + org) for org in known)}
        if matched:
            title = next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), "")
            if title:
                matches[record] = f"[{title}](../{record}) (from email domain)", matched
    return next(iter(matches.values())) if len(matches) == 1 else ("", set())


def _domain_mail(rows, addresses, domains):
    held = {address for address in addresses if address.rsplit("@", 1)[1] in domains}
    return [row for row in rows if held & {row["sender"].casefold(), *(a.casefold() for a in row["recipients"])}]


def _fill_domains(book, text, addresses, rows, zone):
    from .scan import personal_mailbox
    domains = {a.rsplit("@", 1)[1] for a in addresses if not personal_mailbox(a.rsplit("@", 1)[1])}
    # Domain inferences need a message carrying that address, not just a page label.
    evidence = _domain_mail(rows, addresses, domains)
    if not evidence:
        return text
    raw = facts._lines(text)
    if not facts.values(raw.get("Company", "")):
        company, matched = _company(book, domains)
        supporting = _domain_mail(rows, addresses, matched)
        if company and supporting:
            text = _set(text, "Company", company, supporting[-1], zone)
    zones = {DOMAIN_ZONES.get(domain.rsplit(".", 1)[-1], "") for domain in domains}
    if (not facts.values(raw.get("Location", "")) and not facts.values(raw.get("Time zone", ""))
            and len(zones) == 1 and "" not in zones):
        text = _set(text, "Time zone", next(iter(zones)) + " (from email domain)", evidence[-1], zone)
    return text


def fill(book: Notebook, record: str, text: str, *, addresses=None) -> str:
    """After promotion, fill four Facts using indexed mail. Populated company/zone wins.

    First and Last contact count mail the person or the owner sent; company
    and time zone still read any mail that carries the address."""
    if not record.startswith("people/"):
        return text
    addresses = own_addresses(book, record, text).get(record, set()) if addresses is None else addresses
    if not addresses:
        return text
    rows = _mail_rows(book, addresses)
    text = facts.upgrade(record, text)
    from .config import read_config
    from .service import notebook_zone
    zone = notebook_zone(read_config(book.root, validated=False))
    contact = _contact(book, rows, addresses)
    for label, message in zip(("First contact", "Last contact"), (contact[0], contact[-1]) if contact else ()):
        day = datetime.fromisoformat(message["time"]).astimezone(zone).date().isoformat()
        text = _set(text, label, day, message, zone)
    if rows and not contact:
        span = facts._bounds(text, "Facts")
        body = re.sub(r"(?m)^- (First contact|Last contact):[^\n]*$",
                      r"- \1: Unknown", text[span[0]:span[1]])
        text = text[:span[0]] + body + text[span[1]:]
    text = timezone_from_location(record, text)
    return _fill_domains(book, text, addresses, rows, zone)


def _mail_rows(book: Notebook, addresses) -> list:
    clauses = " or ".join(["lower(sender) = ? or exists (select 1 from json_each(recipients) "
                           "where lower(value) = ?)"] * len(addresses))
    return store._rows(book.root, "select * from messages where thread like 'mail:%' and time != '' "
                       f"and ({clauses}) order by time, id", [a for a in sorted(addresses) for _ in range(2)])


def _contact(book: Notebook, rows, addresses) -> list:
    """Mail the person or the owner sent. A third party's notice to forty addresses moved
    every recipient's Last contact past their own timeline (#2951): not contact."""
    from .store_messages import owner_addresses
    writers = addresses | owner_addresses(book.root)
    return [row for row in rows if row["sender"].casefold() in writers]


def contact_facts(book: Notebook, record: str, text: str) -> list[dict]:
    """First and Last contact as `fill` computes them from the whole archive, for the claim audit."""
    addresses = own_addresses(book, record, text).get(record, set()) if record.startswith("people/") else set()
    contact = _contact(book, _mail_rows(book, addresses), addresses) if addresses else []
    if not contact:
        return []
    from .config import read_config
    from .service import notebook_zone
    zone = notebook_zone(read_config(book.root, validated=False))
    return [{"field": label, "value": datetime.fromisoformat(message["time"]).astimezone(zone).date().isoformat(),
             "source": message["id"]} for label, message in (("First contact", contact[0]), ("Last contact", contact[-1]))]


def refresh(root) -> list[str]:
    """Every sync, including one with no model work; caller holds the notebook lock."""
    store.refresh(root)
    book, changed = Notebook(root), []
    for record, addresses in own_addresses(book).items():
        before = book.read(record)
        after = fill(book, record, before, addresses=addresses)
        if after != before and book.write(record, after):
            changed.append(record)
    if changed:
        store.refresh(root)
    return changed
