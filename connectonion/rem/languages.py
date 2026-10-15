"""The languages the owner uses, from the owner's own words only.

Read from mail the owner sent (quoted replies and headers cut off) and the
coding-session messages the owner typed (the session windows hold only typed
turns: automated, sidechain and REM's own prompts are dropped when they are
collected, source.py). Each message votes for its main script; a language with
at least a tenth of the votes is kept, most used first. The reader's "Read in"
menu offers these first, so a Chinese-and-English owner switches between 中文
and English, not a list of eight.
"""

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from .files import read_json, state_path, write_json

SHARE = 0.10
# A Han character is about a word; Latin, Cyrillic and Arabic are counted in words.
SCRIPTS = {"ja": r"[぀-ヿ]", "ko": r"[가-힯]", "zh": r"[一-鿿]",
           "ru": r"[Ѐ-ӿ]+", "ar": r"[؀-ۿ]+", "en": r"[A-Za-z]+"}
SCRIPTS = {language: re.compile(pattern) for language, pattern in SCRIPTS.items()}
MIN_WORDS = 3
# Where a reply's own words end and the quoted thread begins.
QUOTED = re.compile(r"^(?:On .{4,200} wrote:|在.{2,200}写道[:：]|-----\s*Original Message|_{8,}|"
                    r"From: .+|发件人[:：].+|>.*)$", re.M)
HEADER = re.compile(r"^(?:From|To|Cc|Bcc|Date|Subject|Sent|Reply-To): .*$")


def language_of(text: str) -> str | None:
    """The language of one message, by its script; Japanese kana outrank shared Han."""
    words = {language: len(pattern.findall(text)) for language, pattern in SCRIPTS.items()}
    if sum(words.values()) < MIN_WORDS:
        return None
    if words["ja"]:
        words["ja"] += words.pop("zh")
    return max(words, key=words.get)


def own_words(body: str) -> str:
    """A sent mail's body without its header block and the thread it quotes."""
    lines = body.splitlines()
    while lines and (HEADER.match(lines[0]) or not lines[0].strip()):
        lines.pop(0)
    text = "\n".join(lines)
    quoted = QUOTED.search(text)
    return text[:quoted.start()] if quoted else text


def sent_mail(root: Path, addresses: list[str]) -> list[str]:
    path = state_path(root, "rem.db")
    if not addresses or not path.is_file():
        return []
    mine = {address.casefold() for address in addresses}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = db.execute("select sender, body_path from messages where body_path is not null").fetchall()
    db.close()
    bodies = []
    for sender, body_path in rows:
        if (sender or "").casefold() in mine and (file := state_path(root, body_path)).is_file():
            bodies.append(own_words(str(json.loads(file.read_text(encoding="utf-8")).get("body") or "")))
    return bodies


def typed(root: Path) -> list[str]:
    directory = state_path(root, "session-windows")
    seen = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        for item in read_json(path, {}).get("items", []):
            if item.get("role") == "user" and isinstance(item.get("text"), str):
                seen[item.get("source") or item["text"]] = item["text"]
    return list(seen.values())


def detect(root: Path, addresses: list[str]) -> dict:
    """{"languages": [...], "shares": {language: share}, "messages": n} from the owner's own words."""
    votes = Counter(filter(None, map(language_of, sent_mail(root, addresses) + typed(root))))
    total = sum(votes.values())
    shares = {language: round(count / total, 3) for language, count in votes.most_common()} if total else {}
    return {"languages": [language for language, share in shares.items() if share >= SHARE],
            "shares": shares, "messages": total}


def refresh(root: Path, report: dict | None = None) -> dict | None:
    """Detect again and keep it on map.json's owner; the owner page's empty Language line is filled.
    The caller holds the maintenance lock (map, daily round). A map passes the
    report it is about to save; otherwise map.json is updated here."""
    path = state_path(root, "map.json")
    saved = report if report is not None else read_json(path, {})
    owner = saved.get("owner")
    if not owner:
        return None
    owner["languages"] = detect(root, owner.get("addresses") or [])
    if report is None:
        write_json(path, saved)
    _fill_language_fact(root, owner["record"], owner["languages"]["languages"])
    return owner["languages"]


def _fill_language_fact(root: Path, record: str, languages: list[str]) -> None:
    from .files import Notebook
    notebook = Notebook(root)
    if not languages or not notebook.path(record).is_file():
        return
    text = notebook.read(record)
    names = ", ".join(native_name(language) for language in languages)
    filled = re.sub(r"^- Language:[ \t]*(?:Unknown)?[ \t]*$", f"- Language: {names} (detected from your own mail "
                    "and sessions)", text, count=1, flags=re.M)
    if filled != text:
        notebook.write(record, filled)


# What a page's Facts `Language:` line says, in the words pages use.
NAMES = {"english": "en", "chinese": "zh", "mandarin": "zh", "cantonese": "zh", "中文": "zh", "japanese": "ja",
         "日本語": "ja", "korean": "ko", "russian": "ru", "arabic": "ar", "spanish": "es", "french": "fr",
         "german": "de", "italian": "it", "portuguese": "pt", "hindi": "hi", "vietnamese": "vi"}
LANGUAGE_FACT = re.compile(r"^- Language:[ \t]*(.+)$", re.M)


def spoken(page: str) -> list[str]:
    """The languages a person's Facts `Language:` line names, in its order."""
    fact = LANGUAGE_FACT.search(page)
    words = re.findall(r"[^\W\d_]+", fact.group(1).casefold()) if fact else []
    return list(dict.fromkeys(NAMES[word] for word in words if word in NAMES))


NATIVE = {"zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어", "ru": "Русский", "ar": "العربية"}


def native_name(language: str) -> str:
    return NATIVE.get(language, language)


def owner_languages(root: Path) -> dict:
    """What the reader offers first: the configured list, else the detected one."""
    from .config import read_config
    configured = read_config(root, validated=False).get("languages") or []
    detected = (read_json(state_path(root, "map.json"), {}).get("owner") or {}).get("languages") or {}
    if configured:
        return {"languages": list(configured), "from": "set (co rem config set languages)",
                "detected": detected.get("languages", [])}
    return {"languages": detected.get("languages", []),
            "from": "detected from your own mail and sessions" if detected else "not detected yet",
            "shares": detected.get("shares", {})}
