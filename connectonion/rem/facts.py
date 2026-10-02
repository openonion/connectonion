"""The Facts block every page opens on: its shape, its upgrade, and what may not be lost (#2068).

The owner, many times: an investigation found too few facts, and on Ody's page
the phone number could not be found at a glance -- it was in a signature the
page never read, and "no phone appears in the material" sat in Uncertainties.
Facts are data, not prose, so they are one block with one grammar that the
validator, maintenance and the reader all read the same way:

    ## Facts
    - Email: mia.chen@harbour.example
    - Phone: +61 2 5550 0142 (work) [1]; +61 400 555 019 (mobile) [3]
    - Company: [Harbour Analytics](../orgs/harbour-analytics.md) [1]
    - Location: Unknown

- One line a field, `- <Label>: <value>`; every label of the page's kind is
  present, in the order of `FIELDS`, spelled exactly.
- An empty field is exactly `Unknown`.
- Several values are separated by `; `; each may end in a `(qualifier)`
  (work, mobile, personal) and then its citations `[n]`, numbers defined under
  `## Sources`. A value may be a Markdown link.
- Dates are `YYYY-MM-DD`. Every value is cited except the identity fields the
  map fills from addresses (`UNCITED`).

`parse(page)` returns `{label: [{"value", "qualifier", "citations"}]}` in field
order, `[]` for Unknown. A page written before 1.9.0a9 has `## Contact` with
eight of the person labels; `parse` reads it and `upgrade` rewrites it.
docs/cli/rem.md, "Facts and Insight on every page", is the user-facing contract.
"""

import re

FIELDS = {
    "people": ("Email", "Phone", "Company", "Role", "Location", "Time zone", "Links", "How we know them",
               "First contact", "Last contact", "Signing entity", "Handles", "Language", "Also known as"),
    "projects": ("Repository", "Stack", "Status", "People", "Organisation", "Started", "Last activity"),
    "orgs": ("What they do", "Website", "Location", "Legal entity", "Your contacts", "First contact",
             "Last contact"),
}
UNCITED = ("Email", "Handles", "Also known as")
# Fields that hold several values: a value the extractor found is added beside
# the model's. Single-valued fields (a date, a role) keep the model's word.
MULTI = ("Email", "Phone", "Links", "Handles", "Also known as")
# What the extractor reads with certainty. Company and role off a signature are
# a judgement, handed to the turn but never written back by code.
RESTORABLE = ("Email", "Phone", "Links", "First contact", "Last contact")
INSIGHT_KINDS = ("Now", "Changed", "At stake", "Pattern")
LEGACY = "Contact"
CITES = re.compile(r"((?:\s*\[W?\d+\])*)\s*$")
QUALIFIER = re.compile(r"(?<!\])\s*\(([^()]+)\)$")


def kind(record: str) -> str:
    return record.split("/", 1)[0] if record.split("/", 1)[0] in FIELDS else ""


def fields(record: str) -> tuple[str, ...]:
    return FIELDS.get(kind(record), ())


def _bounds(text: str, heading: str):
    """(start of the body, end of the section) of `## heading`, or None."""
    match = re.search(rf"(?m)^## {re.escape(heading)}[ \t]*$", text)
    if not match:
        return None
    following = re.search(r"(?m)^## ", text[match.end():])
    return match.end(), match.end() + following.start() if following else len(text)


def _lines(text: str) -> dict[str, str]:
    """The raw value of each `- Label:` line in the Facts (or legacy Contact) section."""
    span = _bounds(text, "Facts") or _bounds(text, LEGACY)
    if not span:
        return {}
    found = {}
    for line in text[span[0]:span[1]].splitlines():
        match = re.match(r"^- ([^:\n]{1,40}):[ \t]*(.*)$", line)
        if match and match[1] not in found:
            found[match[1]] = match[2].strip()
    return found


def _split(value: str) -> list[str]:
    """Split on `;` outside brackets and parentheses, so a link or qualifier stays whole."""
    parts, depth, current = [], 0, ""
    for char in value:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == ";" and depth <= 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [part.strip() for part in [*parts, current] if part.strip()]


def values(raw: str) -> list[dict]:
    if not raw or raw.casefold().startswith("unknown"):
        return []
    result = []
    for part in _split(raw):
        part = part.rstrip(" .")   # `… [9].`: a sentence's full stop after its citation
        cites = CITES.search(part)
        body = part[:cites.start()].strip()
        qualifier = QUALIFIER.search(body)
        result.append({"value": body[:qualifier.start()].strip() if qualifier else body,
                       "qualifier": qualifier[1].strip() if qualifier else "",
                       "citations": re.findall(r"\[(W?\d+)\]", cites[1])})
    # A citation covers the uncited values before it: `UNSW Founders; [UNSW](…) [12]`
    # is one claim cited once, how a real Tamara candidate wrote it (2026-10-02).
    for index in range(len(result) - 2, -1, -1):
        if not result[index]["citations"]:
            result[index]["citations"] = list(result[index + 1]["citations"])
    return result


def parse(text: str, record: str = "") -> dict[str, list[dict]]:
    """Every field of the page's kind, in order; `[]` is Unknown or a missing line."""
    raw = _lines(text)
    labels = fields(record) or max(FIELDS.values(), key=lambda labels: len(set(labels) & set(raw)))
    return {label: values(raw.get(label, "")) for label in labels}


def coverage(text: str, record: str) -> dict:
    parsed = parse(text, record)
    return {"filled": sum(1 for found in parsed.values() if found), "fields": len(parsed)}


def _block(record: str, raw_lines: list[str]) -> str:
    """The Facts lines in field order: a label's line with its indented continuation, then anything else."""
    owned, extra, current = {}, [], None
    for line in raw_lines:
        match = re.match(r"^- ([^:\n]{1,40}):", line)
        if match and match[1] in fields(record) and match[1] not in owned:
            current = owned.setdefault(match[1], [line])
        elif current is not None and line.startswith((" ", "\t")) and line.strip():
            current.append(line)
        elif line.strip():
            current = None
            extra.append(line)
    out = [line for label in fields(record) for line in owned.get(label, [f"- {label}: Unknown"])]
    return "\n".join(out + extra)


def upgrade(record: str, text: str, insight: str = "- Unknown") -> str:
    """Bring a page to the Facts shape without dropping a word: rename a legacy
    `## Contact`, add a missing Facts section or label as `Unknown`, and give a
    person or project page its Insight section. A page already in shape is returned as is."""
    labels = fields(record)
    if not labels:
        return text
    if _bounds(text, "Facts") is None and _bounds(text, LEGACY) is not None:
        text = re.sub(rf"(?m)^## {LEGACY}[ \t]*$", "## Facts", text, count=1)
    span = _bounds(text, "Facts")
    if span is None:
        after = _bounds(text, "Domains") if kind(record) == "orgs" else None
        first = re.search(r"(?m)^## ", text)
        at = after[1] if after else first.start() if first else len(text)
        text = text[:at].rstrip("\n") + "\n\n## Facts\n" + _block(record, []) + "\n\n" + text[at:].lstrip("\n")
    else:
        body = text[span[0]:span[1]]
        original = body
        for label in labels:
            plain = rf"(?m)^{re.escape(label)}:[ \t]*(.*)$"
            if re.search(plain, body):
                body = re.sub(rf"(?m)^- {re.escape(label)}:[ \t]*Unknown[ \t]*\n?", "", body)
                body = re.sub(plain, rf"- {label}: \1", body)
        present = set(re.findall(r"(?m)^- ([^:\n]{1,40}):", body))
        if body != original or not set(labels) <= present:
            block = _block(record, body.strip("\n").splitlines())
            text = text[:span[0]] + "\n" + block + "\n\n" + text[span[1]:].lstrip("\n")
    if kind(record) in ("people", "projects") and _bounds(text, "Insight") is None:
        end = _bounds(text, "Facts")[1]
        text = text[:end].rstrip("\n") + "\n\n## Insight\n" + insight + "\n\n" + text[end:].lstrip("\n")
    return text


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)[-9:]


def _on_page(row: dict, text: str) -> bool:
    text = text.partition("\n## Sources\n")[0]   # a source's date is not a contact date
    if row["field"] == "Phone":
        return _digits(row["value"]) in {_digits(m) for m in re.findall(r"\+?\d[\d\s().-]{6,}\d", text)}
    return row["value"].casefold().rstrip("/") in text.casefold()


def _cite(text: str, row: dict) -> tuple[str, str]:
    """The number of the Sources entry for this row's source, adding one if the page has none."""
    head, marker, tail = text.partition("\n## Sources\n")
    found = re.search(rf"(?m)^\s*- \[(\d+)\][^\n]*{re.escape(row['source'])}", tail)
    if found:
        return text, found[1]
    number = str(max([int(n) for n in re.findall(r"\[(\d+)\]", text)] or [0]) + 1)
    entry = f"- [{number}] {row['source']} — {row['date']}\n"
    if not marker:
        return text.rstrip("\n") + "\n\n## Sources\n" + entry, number
    after = re.search(r"(?m)^(?:## |Investigation:)", tail)
    sources, rest = (tail[:after.start()], tail[after.start():]) if after else (tail, "")
    sources = re.sub(r"(?m)^- \(none yet\)\n?", "", sources).rstrip("\n")
    return head + marker + (sources + "\n" if sources else "") + entry + ("\n" + rest if rest else ""), number


def drop_uncited(record: str, text: str, original: str = "") -> tuple[str, list[str]]:
    """A new fact value with no citation goes, instead of refusing the page for it.

    "A sentence you cannot number is not kept" applies to a field too. Refused
    whole, a real Tamara investigation was paid for twice (217k, then 144k input
    tokens) for one uncited line. A value the page already carried, and the
    map's own identity fields, stay as they are. Returns the page and the labels touched.
    """
    before = parse(original, record) if original else {}
    touched = []
    for label in fields(record):
        if label in UNCITED:
            continue
        line = re.search(rf"(?m)^- {re.escape(label)}:[ \t]*(.*)$", text)
        if not line:
            continue
        carried = {v["value"] for v in before.get(label, [])}
        parts, found = _split(line[1]), values(line[1])
        if len(parts) != len(found) or all(v["citations"] or v["value"] in carried for v in found):
            continue
        kept = [part for part, v in zip(parts, found) if v["citations"] or v["value"] in carried]
        text = text[:line.start()] + f"- {label}: {'; '.join(kept) or 'Unknown'}" + text[line.end():]
        touched.append(label)
    return text, touched


def keep_extracted(record: str, text: str, rows: list[dict]) -> tuple[str, list[dict]]:
    """Put back a certain fact the extractor found that appears nowhere on the page.

    Only into an `Unknown` field, or beside the model's values in a field that
    holds several; a date or role the model wrote is its reading of the
    material and stays. Returns the page and the rows put back.
    """
    restored = []
    for row in rows:
        if row["field"] not in RESTORABLE or row["field"] not in fields(record) or _on_page(row, text):
            continue
        line = re.search(rf"(?m)^- {re.escape(row['field'])}:[ \t]*(.*)$", text)
        if not line or (values(line[1]) and row["field"] not in MULTI):
            continue
        text, number = _cite(text, row)
        line = re.search(rf"(?m)^- {re.escape(row['field'])}:[ \t]*(.*)$", text)
        value = row["value"] + (f" ({row['qualifier']})" if row.get("qualifier") else "") + f" [{number}]"
        joined = f"{line[1]}; {value}" if values(line[1]) else value
        text = text[:line.start()] + f"- {row['field']}: {joined}" + text[line.end():]
        restored.append(row)
    return text, restored
