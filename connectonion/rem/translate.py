"""A page read in another language: a cached co ai translation, never the page.

The Markdown page stays the one canonical record. A translation lives at
`.state/translations/<language>/<record>` and starts with a line naming the
record and the hash of the prompt version and text it was made from; once either
changes, the hash no longer matches and the translation is stale, so it is made
again on the next request instead of being shown.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import re
import os
import shutil
import tempfile
import sys
import threading
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
    original = Notebook(root).read(record)
    if not match or match.group(1) != record or match.group(2) != digest(original):
        return None
    translation = saved[match.end():]
    if _reader_sources(translation) != _reader_sources(original):
        return None
    return translation


def _reader_sources(text: str) -> str:
    # Match reader.html rawSection, including comments and nonstandard headings.
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    match = re.search(r"^## Sources[^\n]*\n([\s\S]*?)(?=^## |^Investigation:|\Z)", text, re.M | re.I)
    return match.group(1).strip() if match else ""


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


def translate(root: Path, record: str, language: str, *, on_run=None) -> str:
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
    return _run_translation(root, record, language, config, text, on_run=on_run)


def _run_translation(root, record, language, config, text, *, on_run=None):
    from .inquiry import stage_config
    from .service import now
    config = stage_config(root, config, "translate")
    from .languages import owner_languages
    from .runner import _add_usage
    tasks = state_path(root, "tasks")
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="translate-", dir=tasks))
    task = prepare(root, record, language, directory=workspace, text=text)
    prose = task["prose"]
    run = {"id": "run_" + uuid4().hex, "started_at": now().isoformat(),
           "phase": "translate", "record": record, "language": language, "outcome": "failed",
           "usage": None, "harness": config["runner"], "model": config["model"], "runner_attempts": 0}
    if on_run:
        on_run(run["id"])
    started = monotonic()
    try:
        translation = _translate_prose(workspace, prose, task["prompt"], config, run)
        translation = check(task, {"result": translation})
        run["outcome"] = "completed"
        return translation
    finally:
        error = sys.exc_info()[1]
        if error:
            run.update(error=str(error), usage=_add_usage(run["usage"], getattr(error, "usage", None)))
        run.update(finished_at=now().isoformat(), seconds=round(monotonic() - started, 3))
        write_json(state_path(root, f"runs/{run['id']}.json"), run)
        shutil.rmtree(workspace)


def prepare(root, record, language, *, directory, text=None, native=False):
    from .languages import owner_languages
    text = Notebook(root).read(record) if text is None else text
    prose, sources, stamp = _page_parts(text)
    (directory / "page.md").write_text(prose, encoding="utf-8")
    terms = (owner_languages(root).get("english_terms") or []) if language.split("-")[0] == "zh" else []
    instruction = prompt(language, quoted_passages(prose), terms, page_names(prose))
    if native:
        from .files import write_json
        constraints = {"quotes": list(quoted_passages(prose)), "terms": terms, "names": page_names(prose)}
        write_json(directory / "translation-constraints.json", constraints, readable=True)
        instruction = prompt(language).replace("and do not read anything else.", "and read only the supplied constraints file as well.") + f"\nRead {directory / 'translation-constraints.json'} for exact quotes, terms and names to preserve."
    return {"root": str(root), "record": record, "language": language, "directory": str(directory),
            "before": {record: text}, "prose": prose, "sources": sources, "stamp": stamp.group(0) if stamp else "",
            "candidate": str(directory / "translation.md"),
            "prompt": instruction}


def check(task, output):
    original = task["before"][task["record"]]
    translation = checked(task["prose"], output["result"])
    translation += ("\n" + task["sources"] if task["sources"] else "")
    translation += (("" if task["sources"] else "\n") + task["stamp"] + "\n" if task["stamp"] else "")
    atomic_write(translation_path(Path(task["root"]), task["record"], task["language"]),
                 f"<!-- co rem translation of {task['record']} sha256:{digest(original)} -->\n" + translation)
    return translation


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


def translate_pages(root: Path, language: str, records, say=None, workers=1, *, translate_one=None,
                    stop=None, on_row=None, floor=None) -> dict:
    """Translate independent pages in input order; a failed page does not stop the queue.
    Once `stop` (a threading.Event) is set, the pages not yet begun are left as they are. `floor`
    is asked before every page; when it names a reason (the quota floor), nothing more begins."""
    checked_language(language)
    halted = []

    def one(record):
        row = {"page": record, "outcome": "cached"}
        if stop is not None and stop.is_set() or halted:
            return {"page": record, "outcome": "stopped"}
        if floor and (reason := floor()):
            halted.append(reason)
            return {"page": record, "outcome": "stopped"}
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
            if on_row:
                on_row(row)
            if say and row["outcome"] != "stopped":
                say(f"{row['page']}: {row['outcome']}" + (f": {row['error']}" if "error" in row else ""))
    counts = Counter(row["outcome"] for row in rows)
    return {"language": language, "pages": rows,
            **{outcome: counts[outcome] for outcome in ("translated", "cached", "failed")},
            **({"stopped": counts["stopped"]} if stop is not None or floor else {}),
            **({"halted": halted[0]} if halted else {})}


def quota_floor(root: Path, config: dict):
    """The night's own guard for a one-click job: the week's floor kept for the owner's own work."""
    from . import quota
    return lambda: quota.floor_block(quota.meter(root, config), config["limits"])


# Held while a translate-every-page job runs (the CLI or the Host's), so a second one and the night's
# translation pass leave it alone. An OS lock (flock), not a pid in a file: the OS lets it go when the
# process dies, so a kill -9 or a reboot never leaves it stuck, and taking it is one atomic step. The
# status file beside it only says since when, for the words shown; it never decides anything.
LOCK, STATUS = "translate-all.lock", "translate-all.json"
HELD: dict[str, int] = {}


def _lock_fd(root: Path) -> int:
    path = state_path(root, LOCK)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)


def claimed(root: Path) -> dict | None:
    """What the running job's status file says ({} when unreadable), or None when no job holds the lock."""
    from .files import _try_lock, read_json
    if str(Path(root).resolve()) in HELD:
        return read_json(state_path(root, STATUS), {})
    fd = _lock_fd(root)
    try:
        _try_lock(fd)
    except BlockingIOError:
        return read_json(state_path(root, STATUS), {})
    finally:
        os.close(fd)  # closing lets go of a lock just taken to look
    return None


def claim(root: Path) -> None:
    from .files import _try_lock, read_json
    from .service import now
    fd = _lock_fd(root)
    try:
        _try_lock(fd)
    except BlockingIOError:
        os.close(fd)
        since = read_json(state_path(root, STATUS), {}).get("started_at", "earlier")
        raise RemError(f"REM is already translating every page (since {since}); it stops by itself when done") from None
    HELD[str(Path(root).resolve())] = fd
    write_json(state_path(root, STATUS), {"pid": os.getpid(), "started_at": now().isoformat(timespec="seconds")})


def release(root: Path) -> None:
    fd = HELD.pop(str(Path(root).resolve()), None)
    if fd is not None:
        state_path(root, STATUS).unlink(missing_ok=True)
        os.close(fd)


# The owner (2026-11-13): «有的页面是中文，有的是英文，有的是中英文混合，一键让 Codex 全部都翻译。»
# A page is already in a language when every line of its own prose is: quotes, names, link texts,
# code, source ids, privacy labels, Facts labels and the reader's English markers are left out first,
# because they stay as written in any translation. For Chinese a line is Chinese once it holds two Han
# characters in a row (the reader's rowMark rule): names and English terms inside a Chinese sentence
# ("跟进 Jordan Lee 的 Q3 pricing proposal") would outvote its Han characters in a script count. Any
# other line of three words or more is another language, so one English paragraph in a Chinese page
# makes it mixed, and a mixed page is translated. Erring that way costs one model turn; erring the
# other way would leave English the owner cannot read.
HAN_PAIR = re.compile(r"[一-鿿]{2}")
QUOTED = re.compile(r'“[^”\n]*”|"[^"\n]*"|「[^」\n]*」|`[^`\n]*`')
LINK = re.compile(r"!?\[[^\]\n]*\](?:\([^)\n]*\)|\[[^\]\n]*\])")
# URLs, emails, paths and ids (any token with a digit, like a session id): kept as written, never prose.
# ASCII classes: \w would also take the Han characters beside them (`三月2026年`).
ADDRESS = re.compile(r"https?://\S+|[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+|(?<![A-Za-z0-9])~?/[A-Za-z0-9_./-]+|[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*")
FACT_LABEL = re.compile(r"^(?:[-*+]|\d+\.)?\s*(?:\[[ xX]\]\s*)?[A-Za-z][A-Za-z /&'-]{0,40}:\s")


def foreign_lines(text: str, language: str) -> list[str]:
    """The lines of the page's own prose that are not in `language` (see HAN_PAIR above)."""
    ours, found, worded = _prose_lines(text, language)
    # A short page whose lines are each under three words ("- Role: founder") is still not in the
    # language when not one of its lines is.
    return found or ([] if ours else worded)


def in_language(text: str, language: str) -> bool:
    """Written in `language` to begin with: some of its own prose is, and none is in another. A page
    with no prose of its own is not (it is translated as before, and costs next to nothing)."""
    ours, found, _ = _prose_lines(text, language)
    return bool(ours) and not found


def _prose_lines(text, language):
    from .languages import language_of
    prose, _, _ = _page_parts(re.sub(r"<!--[\s\S]*?-->", "", text))
    prose = re.sub(r"^```[\s\S]*?^```[ \t]*$", "", prose, flags=re.M)
    base, names = language.split("-")[0].lower(), page_names(prose)
    found, ours, worded = [], 0, []
    for line in prose.splitlines():
        if re.match(r"\s*(?:#|>)", line):
            continue
        words = FACT_LABEL.sub("", ADDRESS.sub(" ", LINK.sub(" ", QUOTED.sub(" ", line.strip()))))
        words = PRIVACY_TAG.sub(" ", CITATION.sub(" ", words))
        for kept in (*MARKERS, *names):
            words = words.replace(kept, " ")
        if base == "zh" and HAN_PAIR.search(words) or base != "zh" and language_of(words) == base:
            ours += 1
        elif language_of(words) is not None:
            found.append(line)
        elif re.search(r"[^\W\d_]{2,}", words):
            worded.append(line)
    return ours, found, worded


def current(root: Path, record: str, language: str) -> bool:
    """The page reads in `language` now: a current translation, or written in it to begin with."""
    return cached(root, record, language) is not None or in_language(Notebook(root).read(record), language)


def readable(root: Path) -> list[str]:
    """The pages translated at all: not logs (the maps' run records), not the skills catalog's index,
    not pages held for review, services or duplicate installations (census.listed). Sessions, agenda,
    knowledge and AI-note pages are read, so they are translated (the night always translated notes)."""
    from .census import listed, pages
    found = pages(root)
    return [record for record in Notebook(root).list()
            if record.split("/")[0] != "logs" and record != "skills/catalog/index.md"
            and (record not in found or listed(found[record]))]


def plan(root: Path, language: str, category: str = "") -> tuple[int, list[str]]:
    """The readable pages (co rem status's coverage counts the same), and the ones not yet current
    in `language`, Today's first: the night's own queue (backlog), so both agree on what is left."""
    pages = [record for record in readable(root) if not category or record.split("/")[0] == category]
    pending = backlog(root, language, shown=shown_today(root))
    return len(pages), [record for record in pending if record in set(pages)]


# One translate-every-page job per notebook in this process (the Host the reader talks to).
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def every_page(root: Path, action: str, language: str = "") -> dict:
    """The reader's «全部翻译成中文»: start, status or stop the job `co rem translate` runs.

    It answers at once; the job runs on a thread of its own, one page at a time across
    limits.workers lanes, and Stop lets the pages already begun finish (each is one model turn)."""
    key = str(Path(root).resolve())
    with JOBS_LOCK:
        job = JOBS.get(key)
        busy = job is not None and job["state"] in ("starting", "running", "stopping")
        if action == "stop" and busy:
            job["stop"].set()
            if job["state"] == "running":
                job["state"] = "stopping"
        if action == "start" and not busy:
            job = JOBS[key] = {"state": "starting", "language": _job_language(root, language),
                               "done": None, "total": None, "translated": 0, "failed": 0,
                               "error": None, "stop": threading.Event()}
            threading.Thread(target=_run_job, args=(root, job), daemon=True).start()
            busy = True
        if busy:
            return {name: value for name, value in job.items() if name != "stop"}
    # Idle or finished: the counts as the notebook stands now (the night may have changed pages since).
    last = {name: value for name, value in (job or {"state": "idle", "translated": 0, "failed": 0, "error": None}).items()
            if name in ("state", "translated", "failed", "error", "halted")}
    language = job["language"] if job and not language else _job_language(root, language)
    # Counts only: plan's Today-first order reads the whole queue (~5 s on a real notebook).
    records = readable(root)
    return {**last, "language": language, "done": sum(current(root, record, language) for record in records),
            "total": len(records)}


def _job_language(root, language):
    from .languages import owner_language
    return checked_language(language or owner_language(root) or "zh")


def _run_job(root, job):
    from .config import read_config
    from .reader import owner_changed
    from .runner import ready

    def counted(row):
        if row["outcome"] in ("translated", "cached"):
            job["done"] += 1
        job["translated"] += row["outcome"] == "translated"
        job["failed"] += row["outcome"] == "failed"

    mine = False
    try:
        config = read_config(root)
        problem, _ = ready(config)
        if problem:
            # The reader shows this; the fix command stays in the terminal's words (D-60).
            job.update(state="failed", error=problem)
            return
        claim(root)  # refused, in words, while the CLI is already translating every page
        mine = True
        total, pending = plan(root, job["language"])
        job.update(total=total, done=total - len(pending), state="stopping" if job["stop"].is_set() else "running")
        result = translate_pages(root, job["language"], pending, workers=config["limits"]["workers"],
                                 stop=job["stop"], on_row=counted, floor=quota_floor(root, config))
        if result.get("halted"):
            job["halted"] = result["halted"]
        job["state"] = "stopped" if job["stop"].is_set() or result.get("halted") else "done"
    except RemError as error:
        job.update(state="failed", error=str(error))
    finally:
        if mine:
            release(root)
        # Anything unexpected still reaches the Host's log; the button must not wait on a dead thread.
        if job["state"] not in ("done", "stopped", "failed"):
            job.update(state="failed", error="The translation stopped unexpectedly")
        # The reader rebuilds with the new translations and the open page reloads (/rem/version).
        owner_changed(root)


def written_pages(root: Path) -> list[str]:
    """Listed reader pages with prose, including decisions and principles outside the census."""
    from .census import listed, pages, written
    found = pages(root)
    notebook = Notebook(root)
    return [record for record in notebook.list()
            if (record in found and found[record]["category"] != "sessions"
                and listed(found[record]) and found[record]["written"])
            or (record.split("/")[0] in ("decisions", "principles") and written(notebook.read(record)))]


def _waiting_pages(root):
    """Pages behind the reader's active owner obligations, including their copies."""
    from . import census, threads
    from .files import read_json
    from .service import notebook_today
    book = Notebook(root)
    owner = (read_json(state_path(root, "map.json"), {}).get("owner") or {}).get("record")
    title = book.read(owner).splitlines()[0].lstrip("# ") if owner and book.exists(owner) else ""
    first = (title.split() or [""])[0]
    states, today = threads.listing(root), notebook_today(root)
    return {row["path"] for row, text, _ in census._thread_items(book, census.pages(root), first)
            if census.direction(text, first) == "mine" and not census._quiet(text, today)
            and not threads.blocked(root, threads.done_key(row["path"], text), states=states)}


# Today shows nine rows or so; the pages behind them come first, in the order shown. Waiting alone
# was ~90 pages on a real notebook, more than a night translates, so Today stayed English.
TODAY_FIRST = 8


def shown_today(root):
    """The pages behind the rows Today shows, in its order, at most TODAY_FIRST. today.queue reads
    the whole notebook (~5 s on a real one), so a round computes this once and hands it to backlog."""
    from .today import queue
    return list(dict.fromkeys(row["record"] for row in queue(root) if row["section"]))[:TODAY_FIRST]


def backlog(root, language, *, changed=(), shown=()):
    """The pages behind Today's visible rows (`shown`, from shown_today) first, then the other waiting-on-you pages, then
    newest page edits; omit current translations.

    Both scheduled paths use this order before applying the shared daily cap.
    Explicit requests and this round's changes break equal modification times.
    """
    from .files import read_json
    book = Notebook(root)
    requested = read_json(state_path(root, "translation-requests.json"), {}).get(language, [])
    requested = {record: position for position, record in enumerate(requested)}
    waiting, changed = _waiting_pages(root), set(changed)
    shown = {record: position for position, record in enumerate(shown)}
    records = sorted(readable(root), key=lambda record: (
        shown.get(record, len(shown)), record not in waiting, -book.path(record).stat().st_mtime_ns,
        record not in changed, requested.get(record, len(requested)), record))
    return [record for record in records if not current(root, record, language)]


def attempts_today(root):
    from . import service
    from .config import read_config
    _, runs = service.runs_today(service.run_logs(root), service.notebook_zone(read_config(root)))
    # Summary records describe the same work as their individual translate runs.
    return sum(row.get('runner_attempts', 0) for row in runs
               if row.get('phase') in ('daily-translation', 'translate'))


def languages(root):
    """The languages pages are translated into: the owner's own first (languages.owner_language,
    the one the reader and drafts use), then the reader's requests, then the configured list, or
    when that is empty the languages the owner writes, detected (D-103)."""
    from .files import read_json
    from .languages import owner_language, owner_languages
    requested = read_json(state_path(root, 'translation-requests.json'), {})
    return list(dict.fromkeys(filter(None, [owner_language(root), *requested, *owner_languages(root)['languages']])))


def coverage(root, *, next_run=None):
    """Current coverage and what is queued: every missing page of a requested language (D-104)."""
    records, targets = readable(root), languages(root)
    directory = state_path(root, "translations")
    saved = sorted(path.name for path in directory.iterdir()
                   if path.is_dir() and LANGUAGE.fullmatch(path.name)) if directory.is_dir() else []
    report = {}
    for language in dict.fromkeys([*targets, *saved, "zh"]):
        if language.split("-")[0].lower() == "en":
            continue
        done = sum(current(root, record, language) for record in records)
        report[language] = {"total": len(records), "translated": done,
                            "requested": language in targets, "queued": len(records) - done if language in targets else 0}
    return report


def request(root, record, language):
    from .files import maintenance_lock, read_json
    checked_language(language)
    if record not in Notebook(root).list():
        raise RemError('No such page')
    with maintenance_lock(root):
        pending = read_json(state_path(root, 'translation-requests.json'), {})
        pending[language] = list(dict.fromkeys([record, *pending.get(language, [])]))
        write_json(state_path(root, 'translation-requests.json'), pending)
