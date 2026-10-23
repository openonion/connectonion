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

# Owner glossary changes apply to new translations without invalidating every cached page.
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
    original = Notebook(root).read(record)
    if not match or match.group(1) != record or match.group(2) != digest(original):
        return None
    try:
        return checked(original, saved[match.end():])
    except RemError:
        return None  # Keep the bytes for diagnosis; reading never starts a model.


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


def prompt(language: str, quotes=(), terms=()) -> str:
    from .runner import language_rules
    # Named one by one: told only the rule, the model still translated “zero-risk things”.
    keep = "".join(f"\n- {quote}" for quote in dict.fromkeys(quotes))
    return ("Translate page.md, a Markdown notebook page, into the language tagged "
            f"`{language}` and write the result to translation.md in this folder. Do not edit "
            "page.md and do not read anything else. Translate the prose only: add nothing, drop "
            "nothing, keep every line's Markdown, every link target and every source id like [3] "
            "where it is. Keep each numbered Sources target, including file paths/revisions/hashes "
            "and URL queries/fragments, unchanged; translate only its explanatory caption. "
            "Do not move a citation to another claim line. Keep every privacy label such as "
            "[personal] and [sensitive] on the same line, "
            "following the same passage; never add, drop or translate a label. "
            "This page is about the reader's own work. Translate \"the user\", \"the owner\" and \"you\" "
            "referring to the notebook owner as the second person of the target language "
            "(Chinese: 你; never 用户). This applies only to surrounding prose; quotes stay untouched. "
            "Keep every quoted passage (text inside “…”, \"…\", 「…」, and Markdown "
            "> blockquote lines) exactly as written, in its original language; translate only the "
            "surrounding prose; keep the ASCII colon after a leading date like `2026-10-15:`. " + language_rules() + "These stay in English even mid-sentence: "
            "`Nothing open as of 2026-09-29; Theo canceled` becomes `Nothing open as of 2026-09-29；"
            "Theo 取消了` in Chinese." + (f" These quoted words must appear unchanged:{keep}\n" if keep else "")
            + (" Keep these terms in English, as the owner writes them: " + ", ".join(terms) + "." if terms else "")
            + " Then reply DONE.")


def quoted_passages(text: str) -> Counter:
    """The reader's six-character quotations, including Markdown evidence lines."""
    # The words, not the marks: “Hi Mara,” may come back as “Hi Mara”, in Chinese punctuation.
    quotes = [quote[1:-1].rstrip(",.;:!?，。；：！？ ")
              for quote in re.findall(r'“[^”\n]{6,}”|"[^"\n]{6,}"|「[^」\n]{6,}」', text)]
    quotes += re.findall(r"^[ \t]*>[^\n]{6,}$", text, re.M)
    return Counter(quotes)


def source_definitions(text: str) -> list:
    """Literal routing identities; captions only split at the existing source delimiter."""
    from .reader_model import SOURCE
    blocks = re.findall(r"^## Sources[^\n]*\n([\s\S]*?)(?=^## |^Investigation:|\Z)", text, re.M | re.I)
    if len(blocks) > 1:
        raise RemError("Ambiguous source definitions: multiple Sources sections")
    rows, seen = [], set()
    for line in (blocks[0] if blocks else "").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?[\[［](W?\d{1,3})[\]］][ \t]+(.*)", line)
        if not match:
            rows.append(("literal", line))
            continue
        number, payload = match.groups()
        if number in seen:
            raise RemError("Ambiguous source definition: duplicate citation number")
        seen.add(number)
        route = SOURCE.match(f"- [{number}] {payload}")
        rows.append((number, "target", route.group(2)) if route else (number, "literal", payload))
    return rows


def citation_lines(text: str) -> list:
    """The prompt requires every line to stay; global counts cannot bind a claim."""
    return [(index, Counter(CITATION.findall(line))) for index, line in enumerate(text.splitlines())
            if CITATION.search(line)]


def checked(original: str, translation: str) -> str:
    """Keep headings, sources, privacy labels and reader markers intact."""
    headings = [line for line in original.splitlines() if line.startswith("#")]
    if [line for line in translation.splitlines() if line.startswith("#")] != headings:
        raise RemError("The translation changed the page's headings; nothing was cached. Translate again")
    if sorted(CITATION.findall(translation)) != sorted(CITATION.findall(original)):
        raise RemError("The translation changed the page's source ids; nothing was cached. Translate again")

    if source_definitions(original) != source_definitions(translation):
        raise RemError("The translation changed a source target or source definition; nothing was cached. Translate again")
    if citation_lines(original) != citation_lines(translation):
        raise RemError("The translation moved citations between lines; nothing was cached. Translate again")

    def privacy_lines(text):
        return [(number, Counter(tag.lower() for tag in PRIVACY_TAG.findall(line)))
                for number, line in enumerate(text.splitlines()) if PRIVACY_TAG.search(line)]

    if privacy_lines(original) != privacy_lines(translation):
        raise RemError("The translation changed privacy tags or moved them between lines; nothing was cached. "
                       "Translate again")
    if quoted_passages(original) - quoted_passages(translation):
        raise RemError("The translation changed or dropped a quoted passage; nothing was cached. Translate again")
    for marker in MARKERS:
        if translation.count(marker) < original.count(marker):
            raise RemError(f"The translation dropped `{marker}`, which the reader reads; nothing was cached. "
                           "Translate again")
    return translation


def translate(root: Path, record: str, language: str) -> str:
    """The cached translation when current, else one co ai turn on the notebook's runner."""
    from .config import read_config
    from .runner import ready
    text = Notebook(root).read(record)
    if (hit := cached(root, record, language)) is not None:
        return hit
    source_definitions(text)  # Reject ambiguous input before any paid turn.
    config = read_config(root)
    problem, fix = ready(config)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and translate again")
    return _run_translation(root, record, language, config, text)


def _run_translation(root, record, language, config, text):
    from .languages import owner_languages
    from .runner import run_task
    tasks = state_path(root, "tasks")
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="translate-", dir=tasks))
    prose, stamp = STAMP.sub("", text).rstrip() + "\n", STAMP.search(text)
    (workspace / "page.md").write_text(prose, encoding="utf-8")
    terms = (owner_languages(root).get("english_terms") or []) if language.split("-")[0] == "zh" else []
    run = {"id": "run_" + uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
           "phase": "translate", "record": record, "language": language, "outcome": "failed",
           "usage": None, "harness": config["runner"], "model": config["model"], "runner_attempts": 0}
    started = monotonic()
    try:
        envelope = run_task(workspace, prompt(language, quoted_passages(prose), terms), config, "abstract")
        run["usage"] = envelope.get("usage")
        translation = _read_translation(workspace, prose, stamp)
        atomic_write(translation_path(root, record, language),
                     f"<!-- co rem translation of {record} sha256:{digest(text)} -->\n" + translation)
        run["outcome"] = "completed"
        return translation
    finally:
        error = sys.exc_info()[1]
        if error:
            run.update(error=str(error), usage=getattr(error, "usage", None) or run["usage"])
        run.update(finished_at=datetime.now(timezone.utc).isoformat(), seconds=round(monotonic() - started, 3))
        write_json(state_path(root, f"runs/{run['id']}.json"), run)
        shutil.rmtree(workspace)


def _read_translation(workspace, prose, stamp):
    output = workspace / "translation.md"
    answer = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
    if not answer:
        raise RemError("co ai finished without writing a translation; nothing was cached. Translate again")
    return checked(prose, answer + "\n") + (f"\n{stamp.group(0)}\n" if stamp else "")


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
