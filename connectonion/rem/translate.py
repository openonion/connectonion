"""A page read in another language: a cached co ai translation, never the page.

The Markdown page stays the one canonical record. A translation lives at
`.state/translations/<language>/<record>` and starts with a line naming the
record and the hash of the prompt version and text it was made from; once either
changes, the hash no longer matches and the translation is stale, so it is made
again on the next request instead of being shown.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import re
import shutil
import tempfile
import sys
from time import monotonic
from uuid import uuid4
from pathlib import Path

from .config import LANGUAGE
from .files import Notebook, RemError, atomic_write, state_path, write_json

# Glossary and preservation rules apply to new translations. Keep the version:
# invalidating every cache would leave existing notebooks in English until retranslated.
PROMPT_VERSION = 2
HEADER = re.compile(r"<!-- co rem translation of (\S+) sha256:([0-9a-f]{64}) -->\n")
CITATION = re.compile(r"[\[［](W?\d{1,3})[\]］]")
# Keep this set in step with reader.html hasPrivacy/privatePassages.
PRIVACY_TAG = re.compile(r"[\[［](personal|sensitive)[\]］]", re.I)
# English phrases the reader parses inside prose; translated, a closed thread reads as open.
MARKERS = ("Unknown", "None as of", "Nothing open as of", "Now:", "Changed:", "At stake:", "Pattern:")
# The page's last line, which the reader reads for its status. Not prose: it is
# never sent to the model (Codex translated its label) and is put back as written.
STAMP = re.compile(r"^Investigation:[^\n]*$", re.M)


def digest(text: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{text}".encode("utf-8")).hexdigest()


def checked_language(language: str) -> str:
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language):
        raise RemError("language must be a language tag such as en, zh, zh-TW or ja")
    return language


def translation_path(root: Path, record: str, language: str) -> Path:
    return state_path(root, f"translations/{checked_language(language)}/{record}")


def cached(root: Path, record: str, language: str) -> str | None:
    """The translation of the page as it is now, or None when missing or stale."""
    path = translation_path(root, record, language)
    if not path.is_file():
        return None
    saved = path.read_text(encoding="utf-8")
    match = HEADER.match(saved)
    if not match or match.group(2) != digest(Notebook(root).read(record)):
        return None
    return saved[match.end():]


def cached_languages(root: Path, record: str) -> dict[str, str]:
    """{language: text} for every translation of this record that is still current."""
    directory = state_path(root, "translations")
    if not directory.is_dir():
        return {}
    found = {}
    for language in sorted(path.name for path in directory.iterdir() if LANGUAGE.fullmatch(path.name)):
        text = cached(root, record, language)
        if text is not None:
            found[language] = text
    return found


def prompt(language: str, quotes=(), terms=(), names=()) -> str:
    from .runner import language_rules
    # Named one by one: told only the rule, the model still translated “zero-risk things”.
    keep = "".join(f"\n- {quote}" for quote in dict.fromkeys(quotes))
    keep_names = "".join(f"\n- {name}" for name in dict.fromkeys(names))
    return ("Translate page.md, a Markdown notebook page, into the language tagged "
            f"`{language}` and write the result to translation.md in this folder. Do not edit "
            "page.md and do not read anything else. Translate the prose only: add nothing, drop "
            "nothing, keep every line's Markdown, every link target and every source id like [3] "
            "where it is. Keep every amount, number and currency symbol exactly as written "
            "(`$50,000`, `A$1,200`, `¥300`); never convert or name a currency the original doesn't name. "
            "Keep names of people, organisations, projects, products, repositories and tools exactly as written, "
            "including lowercase project names. The page's own title and every link text name a thing "
            "and stay as written. Keep email addresses, URLs, file paths, issue/PR numbers (#2345), "
            "version numbers and code spans unchanged; a line that only lists source ids, such as "
            "`Sources: codex:…`, stays exactly as written, label included. "
            "Keep every privacy label such as [personal] and [sensitive] on the same line, "
            "following the same passage; never add, drop or translate a label. "
            "This page is about the reader's own work. Translate \"the user\", \"the owner\" and \"you\" "
            "referring to the notebook owner as the second person of the target language "
            "(Chinese: 你; never 用户). This applies only to surrounding prose; quotes stay untouched. "
            "Keep every quoted passage (text inside “…”, \"…\", 「…」, and Markdown "
            "> blockquote lines) exactly as written, in its original language; translate only the "
            "surrounding prose; keep the ASCII colon after a leading date like `2026-10-15:`. " + language_rules() + "These stay in English even mid-sentence: "
            "`Nothing open as of 2026-09-29; Theo canceled` becomes `Nothing open as of 2026-09-29；"
            "Theo 取消了` in Chinese." + (f" These quoted words must appear unchanged:{keep}\n" if keep else "")
            + (f" Keep these names exactly as written:{keep_names}\n" if keep_names else "")
            + (" Keep these terms in English, as the owner writes them: " + ", ".join(terms) + "." if terms else "")
            + " Then reply DONE.")


def page_names(text: str) -> list[str]:
    """The title and link labels are explicit names, including lowercase repositories."""
    title = re.search(r"^# ([^\n]+)", text, re.M)
    links = re.findall(r"\[([^\]\n]+)\](?:\([^\n]*?\)|\[[^\]\n]*\])", text)
    return list(dict.fromkeys(([title.group(1)] if title else []) + links))[:40]


def quoted_passages(text: str) -> Counter:
    """The reader's six-character quotations, including Markdown evidence lines."""
    # The words, not the marks: “Hi Mara,” may come back as “Hi Mara”, in Chinese punctuation.
    quotes = [quote[1:-1].rstrip(",.;:!?，。；：！？ ")
              for quote in re.findall(r'“[^”\n]{6,}”|"[^"\n]{6,}"|「[^」\n]{6,}」', text)]
    quotes += re.findall(r"^[ \t]*>[^\n]{6,}$", text, re.M)
    return Counter(quotes)


def _count_changes(before: Counter, after: Counter) -> str:
    return "; ".join(f"{label} {item} ({count} time(s))"
                     for label, counts in (("missing", before - after), ("extra", after - before))
                     for item, count in counts.items())


def _check_citations(original: str, translation: str) -> None:
    before = Counter(f"[{item}]" for item in CITATION.findall(original))
    after = Counter(f"[{item}]" for item in CITATION.findall(translation))
    problem = _count_changes(before, after)
    if problem:
        raise RemError(f"The translation changed the page's source ids: {problem}; every [n]/[Wn] must appear "
                       "exactly as many times as in page.md; nothing was cached. Translate again")


def checked(original: str, translation: str) -> str:
    """Keep headings, sources, privacy labels and reader markers intact."""
    # A Markdown heading has a space after its hashes; "#1037 was fixed" is prose.
    heading = re.compile(r"#{1,6}\s")
    headings = [line for line in original.splitlines() if heading.match(line)]
    translated_headings = [line for line in translation.splitlines() if heading.match(line)]
    if translated_headings != headings:
        detail = _count_changes(Counter(headings), Counter(translated_headings)) or "headings are out of order"
        raise RemError(f"The translation changed the page's headings: {detail}; "
                       "keep page.md's headings in their original order; nothing was cached. Translate again")
    _check_citations(original, translation)

    def privacy_lines(text):
        return Counter(f"[{tag.lower()}] on line {number}"
                       for number, line in enumerate(text.splitlines(), 1) for tag in PRIVACY_TAG.findall(line))

    if privacy_lines(original) != privacy_lines(translation):
        detail = _count_changes(privacy_lines(original), privacy_lines(translation))
        raise RemError(f"The translation changed privacy tags or moved them between lines: {detail}; "
                       "nothing was cached. Translate again")
    missing_quotes = quoted_passages(original) - quoted_passages(translation)
    if missing_quotes:
        detail = "; ".join(f"missing quoted passage ({count} time(s)) from page.md line "
                           f"{original[:original.index(quote)].count(chr(10)) + 1}"
                           for quote, count in missing_quotes.items())
        raise RemError(f"The translation changed or dropped a quoted passage: {detail}; "
                       "keep quoted passages exactly as written; nothing was cached. Translate again")
    for marker in MARKERS:
        if translation.count(marker) < original.count(marker):
            missing = original.count(marker) - translation.count(marker)
            raise RemError(f"The translation dropped `{marker}` ({missing} time(s)), which the reader reads; nothing was cached. "
                           "Translate again")
    return translation


def translate(root: Path, record: str, language: str) -> str:
    """The cached translation when current, else one co ai turn on the notebook's runner."""
    from .config import read_config
    from .runner import ready
    text = Notebook(root).read(record)
    if (hit := cached(root, record, language)) is not None:
        return hit
    config = read_config(root)
    problem, fix = ready(config)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and translate again")
    return _run_translation(root, record, language, config, text)


def _run_translation(root, record, language, config, text):
    from .languages import owner_languages
    from .runner import _add_usage
    tasks = state_path(root, "tasks")
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="translate-", dir=tasks))
    prose, sources, stamp = _page_parts(text)
    (workspace / "page.md").write_text(prose, encoding="utf-8")
    terms = (owner_languages(root).get("english_terms") or []) if language.split("-")[0] == "zh" else []
    run = {"id": "run_" + uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
           "phase": "translate", "record": record, "language": language, "outcome": "failed",
           "usage": None, "harness": config["runner"], "model": config["model"], "runner_attempts": 0}
    started = monotonic()
    try:
        task_prompt = prompt(language, quoted_passages(prose), terms, page_names(prose))
        translation = _translate_prose(workspace, prose, task_prompt, config, run)
        translation += ("\n" + sources if sources else "")
        translation += (("" if sources else "\n") + stamp.group(0) + "\n" if stamp else "")
        atomic_write(translation_path(root, record, language),
                     f"<!-- co rem translation of {record} sha256:{digest(text)} -->\n" + translation)
        run["outcome"] = "completed"
        return translation
    finally:
        error = sys.exc_info()[1]
        if error:
            run.update(error=str(error), usage=_add_usage(run["usage"], getattr(error, "usage", None)))
        run.update(finished_at=datetime.now(timezone.utc).isoformat(), seconds=round(monotonic() - started, 3))
        write_json(state_path(root, f"runs/{run['id']}.json"), run)
        shutil.rmtree(workspace)


def _page_parts(text):
    stamp = STAMP.search(text)
    body = text[:stamp.start()] if stamp else text
    sources = re.search(r"^## Sources[ \t]*$", body, re.M)
    prose, tail = (body[:sources.start()], body[sources.start():]) if sources else (body, "")
    return prose.rstrip() + "\n", tail, stamp


def _translate_prose(workspace, prose, task_prompt, config, run):
    from .runner import _add_usage, run_task
    repair = ""
    for attempt in range(2):
        run["runner_attempts"] += 1
        envelope = run_task(workspace, task_prompt + repair, config, "abstract")
        run["usage"] = _add_usage(run["usage"], envelope.get("usage"))
        answer = _read_translation(workspace)
        # Only a completed translation's structural errors get one repair turn.
        try:
            return checked(prose, answer)
        except RemError as error:
            if attempt:
                raise
            repair = f"\n\nYour translation.md failed validation: {error}. Fix translation.md in place using page.md."


def _read_translation(workspace):
    output = workspace / "translation.md"
    answer = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
    if not answer:
        raise RemError("co ai finished without writing a translation; nothing was cached. Translate again")
    return answer + "\n"


def translate_pages(root: Path, language: str, records, say=None, workers=1, *, translate_one=None) -> dict:
    """Translate independent pages in input order; a failed page does not stop the queue."""
    checked_language(language)

    def one(record):
        row = {"page": record, "outcome": "cached"}
        try:
            if cached(root, record, language) is None:
                (translate_one or translate)(root, record, language)
                row["outcome"] = "translated"
        except RemError as error:
            row.update(outcome="failed", error=str(error))
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, records):
            rows.append(row)
            if say:
                say(f"{row['page']}: {row['outcome']}" + (f": {row['error']}" if "error" in row else ""))
    counts = Counter(row["outcome"] for row in rows)
    return {"language": language, "pages": rows,
            **{outcome: counts[outcome] for outcome in ("translated", "cached", "failed")}}


def written_pages(root: Path) -> list[str]:
    """Listed reader pages with prose, including decisions and principles outside the census."""
    from .census import listed, pages, written
    found = pages(root)
    notebook = Notebook(root)
    return [record for record in notebook.list()
            if (record in found and found[record]["category"] != "sessions"
                and listed(found[record]) and found[record]["written"])
            or (record.split("/")[0] in ("decisions", "principles") and written(notebook.read(record)))]
